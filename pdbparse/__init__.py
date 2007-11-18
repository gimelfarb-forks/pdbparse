#!/usr/bin/env python

from struct import unpack,calcsize

PDB_STREAM_ROOT   = 0 # PDB root directory
PDB_STREAM_PDB    = 1 # PDB stream info
PDB_STREAM_TPI    = 2 # type info
PDB_STREAM_DBI    = 3 # debug info

_PDB2_SIGNATURE = "Microsoft C/C++ program database 2.00\r\n\032JG\0\0"
_PDB2_SIGNATURE_LEN = len(_PDB2_SIGNATURE)
_PDB2_FMT = "<%dsLHHLL" % _PDB2_SIGNATURE_LEN
_PDB2_FMT_SIZE = calcsize(_PDB2_FMT)

_PDB7_SIGNATURE = 'Microsoft C/C++ MSF 7.00\r\n\x1ADS\0\0\0'
_PDB7_SIGNATURE_LEN = len(_PDB7_SIGNATURE)
_PDB7_FMT = "<%dsLLLLLL" % _PDB7_SIGNATURE_LEN
_PDB7_FMT_SIZE = calcsize(_PDB7_FMT)

# Internal method to calculate the number of pages required
# to store a stream of size "length", given a page size of
# "pagesize"
def _pages(length, pagesize):
    num_pages = length / pagesize
    if (length % pagesize): num_pages += 1
    return num_pages

class StreamFile:
    def __init__(self, fp, pages, size=-1, page_size=0x1000):
        self.fp = fp
        self.pages = pages
        self.page_size = page_size
        if size == -1: self.end = len(pages)*page_size
        else: self.end = size
        self.pos = 0
    def read(self, size=-1):
        if size == -1:
            pn_start, off_start = self._get_page(self.pos)
            pdata = self._read_pages(self.pages[pn_start:])
            self.pos = self.end
            return pdata[off_start:self.end-off_start]
        else:
            pn_start, off_start = self._get_page(self.pos)
            pn_end, off_end = self._get_page(self.pos + size)
            pdata = self._read_pages(self.pages[pn_start:pn_end+1])
            self.pos += size

            return pdata[off_start:-(self.page_size - off_end)]
    def seek(self, offset, whence=0):
        if whence == 0:
            self.pos = offset
        elif whence == 1:
            self.pos += offset
        elif whence == 2:
            self.pos = self.end + offset
        
        if self.pos < 0: self.pos = 0
        if self.pos > self.end: self.pos = self.end
    def tell(self):
        return self.pos
    def close(self):
        self.fp.close()

    # Private helper methods
    def _get_page(self, offset):
        return (offset / self.page_size, offset % self.page_size)
    def _read_pages(self, pages):
        s = ''
        for pn in pages:
           self.fp.seek(pn*self.page_size)
           s += self.fp.read(self.page_size)
        return s

class PDBStream:
    """Base class for PDB stream types.

    data: the data that makes up this stream
    index: the index of this stream in the file
    page_size: the size of a page, in bytes, of the PDB file
        containing this stream

    The constructor signature here is valid for all subclasses.

    """
    def _get_data(self):
        pos = self.stream_file.tell()
        data = self.stream_file.read()
        self.stream_file.seek(pos)
        return data
    data = property(fget=_get_data)

    def __init__(self, fp, pages, index, size=-1, page_size=0x1000, fast_load=False):
        self.pages = pages
        self.index = index
        self.page_size = page_size
        if size == -1: self.size = len(pages)*page_size
        else: self.size = size
        self.stream_file = StreamFile(fp, pages, size=size, page_size=page_size)

class PDB7RootStream(PDBStream):
    """Class representing the root stream of a PDB file.
    
    Parsed streams are available as a tuple of (size, [list of pages])
    describing each stream in the "streams" member of this class.

    """
    def __init__(self, fp, pages, index=PDB_STREAM_ROOT, size=-1,
            page_size=0x1000, fast_load=False):
        PDBStream.__init__(self, fp, pages, index, size=size, page_size=page_size)

        data = self.data
        
        (self.num_streams,) = unpack("<L", data[:4])
        
        # num_streams dwords giving stream sizes
        rs = data[4:]
        sizes = []
        for i in range(0,self.num_streams*4,4):
            (stream_size,) = unpack("<L",rs[i:i+4])
            sizes.append(stream_size)
        
        # Next comes a list of the pages that make up each stream
        rs = rs[self.num_streams*4:]
        page_lists = []
        pos = 0
        for i in range(self.num_streams):
            num_pages = _pages(sizes[i], self.page_size)

            if num_pages != 0:
                pages = unpack("<" + ("%sL" % num_pages),
                               rs[pos:pos+(num_pages*4)])
                page_lists.append(pages)
                pos += num_pages*4
            else:
                page_lists.append(())
        
        self.streams = zip(sizes, page_lists)

class PDB2RootStream(PDBStream):
    """Class representing the root stream of a PDBv2 file.
    
    Parsed streams are available as a tuple of (size, [list of pages])
    describing each stream in the "streams" member of this class.

    """
    def __init__(self, fp, pages, index=PDB_STREAM_ROOT, size=-1,
            page_size=0x1000, fast_load=False):
        PDBStream.__init__(self, fp, pages, index, size=size, page_size=page_size)
        data = self.data
        
        (self.num_streams, reserved) = unpack("<HH", data[:4])
        
        # num_streams 
        rs = data[4:]
        sizes = []
        for i in range(0,self.num_streams*8,8):
            (stream_size,ptr_reserved) = unpack("<LL",rs[i:i+8])
            sizes.append(stream_size)
        
        # Next comes a list of the pages that make up each stream
        rs = rs[self.num_streams*8:]
        page_lists = []
        pos = 0
        for i in range(self.num_streams):
            num_pages = _pages(sizes[i], self.page_size)

            if num_pages != 0:
                pages = unpack("<" + ("%dH" % num_pages),
                               rs[pos:pos+(num_pages*2)])
                page_lists.append(pages)
                pos += num_pages*2
            else:
                page_lists.append(())
        
        self.streams = zip(sizes, page_lists)

class PDBInfoStream(PDBStream):
    pass

class PDBTypeStream(PDBStream):
    def __init__(self, fp, pages, index=PDB_STREAM_ROOT, size=-1,
            page_size=0x1000, fast_load=False):
        PDBStream.__init__(self, fp, pages, index, size=size, page_size=page_size)
        if fast_load: return
        else: self.load()
    def load(self):
        import tpi
        tpis = tpi.parse_stream(self.stream_file)
        self.header = tpis.TPIHeader
        self.num_types = self.header.ti_max - self.header.ti_min
        self.types = tpis.types
        self.structures = dict((s.name, s) for s in tpis.types.values()
            if s.leaf_type == "LF_STRUCTURE" or s.leaf_type == "LF_STRUCTURE_ST")
        del tpis

class PDBDebugStream(PDBStream):
    pass

# Class mappings for the stream types
_stream_types7 = {
    PDB_STREAM_ROOT: PDB7RootStream,
    PDB_STREAM_TPI: PDBTypeStream,
    #PDB_STREAM_PDB: PDBInfoStream,
    #PDB_STREAM_DBI: PDBDebugStream
}

_stream_types2 = {
    PDB_STREAM_ROOT: PDB2RootStream,
    PDB_STREAM_TPI: PDBTypeStream,
}

class PDB:
    def __init__(self, fp, fast_load=False):
        self.fp = fp
        self.fast_load = fast_load

    def read(self, pages, size=-1):
        """Read a portion of this PDB file, given a list of pages.
        
        pages: a list of page numbers that make up the data requested
        size: the number of bytes requested. Must be <= len(pages)*self.page_size
        
        """
        
        assert size <= len(pages)*self.page_size

        pos = self.fp.tell()
        s = ''
        for pn in pages:
           self.fp.seek(pn*self.page_size)
           s += self.fp.read(self.page_size)
        self.fp.seek(pos)
        if size == -1:
            return s
        else:
            return s[:size]

    def read_root(self, rs):
        self.streams = []
        for i in range(len(rs.streams)):
            try:
                pdb_cls = self._stream_map[i]
            except KeyError:
                pdb_cls = PDBStream
            stream_size, stream_pages = rs.streams[i]
            self.streams.append(
                pdb_cls(self.fp, stream_pages, i, size=stream_size,
                    page_size=self.page_size, fast_load=self.fast_load))

class PDB7(PDB):
    """Class representing a Microsoft PDB file, version 7.

    This class loads and parses each stream contained in the
    file, and places it in the "streams" member.

    """

    def __init__(self, fp, fast_load=False):
        PDB.__init__(self, fp, fast_load)
        (self.signature, self.page_size, alloc_table_ptr,
         self.num_file_pages, root_size, reserved,
         root_index) = unpack(_PDB7_FMT, self.fp.read(_PDB7_FMT_SIZE))
        
        if self.signature != _PDB7_SIGNATURE:
            raise ValueError("Invalid signature for PDB version 7")
        
        self._stream_map = _stream_types7

        # Read in the root stream
        num_root_pages = _pages(root_size, self.page_size)
        
        self.fp.seek(root_index * self.page_size)
        page_list_fmt = "<" + ("%dL" % num_root_pages)
        root_page_list = unpack(page_list_fmt,
            self.fp.read(num_root_pages * 4))
        root_stream_data = self.read(root_page_list, root_size)

        self.root_stream = PDB7RootStream(self.fp, root_page_list,
            index=PDB_STREAM_ROOT, size=root_size, page_size=self.page_size)

        self.read_root(self.root_stream)


class PDB2(PDB):
    def __init__(self, fp, fast_load=False):
        PDB.__init__(self, fp, fast_load)
        (self.signature, self.page_size, start_page,
         self.num_file_pages, root_size, reserved) = unpack(_PDB2_FMT, 
                 self.fp.read(_PDB2_FMT_SIZE))
        
        if self.signature != _PDB2_SIGNATURE:
            raise ValueError("Invalid signature for PDB version 2")
        
        self._stream_map = _stream_types2

        # Read in the root stream
        num_root_pages = _pages(root_size, self.page_size)
        
        page_list_fmt = "<" + ("%dH" % num_root_pages)
        root_page_list = unpack(page_list_fmt,
            self.fp.read(num_root_pages * 2))

        self.root_stream = PDB2RootStream(self.fp, root_page_list,
            index=PDB_STREAM_ROOT, page_size=self.page_size)

        self.read_root(self.root_stream)

def parse(filename, fast_load=False):
    "Open a PDB file and autodetect its version"
    f = open(filename, 'rb')
    sig = f.read(_PDB7_SIGNATURE_LEN)
    f.seek(0)
    if sig == _PDB7_SIGNATURE:
        return PDB7(f, fast_load)
    else:
        sig = f.read(_PDB2_SIGNATURE_LEN)
        if sig == _PDB2_SIGNATURE:
            f.seek(0)
            return PDB2(f, fast_load)
    raise ValueError("Unsupported file type")