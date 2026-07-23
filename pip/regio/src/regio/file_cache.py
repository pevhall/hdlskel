"""
file_cache.py

Implements FileCache, a Regio-derived sparse memory cache.

- Writes are stored as an ordered list of (address, bytearray) "regions".
- Overlapping or byte-adjacent writes are automatically merged into a
  single region.
- Reads reconstruct requested bytes from whatever regions overlap the
  requested range; any bytes not covered by a region will raise an
  ValueError.
- The whole cache can be serialized to / loaded from a simple custom
  binary file format:

    Header:
        ascii "skregmap"      (8 bytes, no null terminator)
                           (short for hdlskel register file map)
    Then, repeated until EOF, one entry per stored region:
        uint32_t address           (little-endian)
        uint32_t size              (little-endian)
        uint8_t  data[size]

"""

import struct
from bisect import bisect_left

from .regio import Regio

UINT32_MAX = 0xFFFF_FFFF

FILE_HEADER = b"skregmap"
FILE_EXTENSION =  FILE_HEADER.decode("utf-8")

# Regions are packed as little-endian uint32 address + uint32 size
_REGION_HDR_STRUCT = struct.Struct("<II")


class FileCache(Regio):
    """
    Sparse memory-space cache with merge-on-write semantics and a
    simple binary file persistence format.

    Internal representation
    ------------------------
    self._regions is a list of (address, bytearray) tuples, always kept
    sorted by address, where no two regions overlap or are adjacent
    (any such regions get merged immediately on write).
    """

    def __init__(self):
        self._regions: list[tuple[int, bytearray]] = []

    # ------------------------------------------------------------------
    # Regio interface
    # ------------------------------------------------------------------

    async def dev_write(self, addr: int, data: bytes) -> None:
        self.dev_write_cached(addr, data)

    async def dev_read(self, addr: int, size: int) -> bytes:
        return self.dev_read_cached(addr, size)

    # ------------------------------------------------------------------
    # non async version of read and write
    # ------------------------------------------------------------------

    def dev_write_cached(self, addr: int, data: bytes) -> None:
        """Write `data` at byte address `addr`, merging with any
        overlapping or adjacent existing regions."""
        self._validate_addr_size(addr, len(data))
        if len(data) == 0:
            return
        self._merge_write(addr, bytes(data))

    def dev_read_cached(self, addr: int, size: int) -> bytes:
        """Read `size` bytes starting at byte address `addr`.

        Any byte not covered by a previously written will raise
        ValueError."""
        self._validate_addr_size(addr, size)
        if size == 0:
            return b""

        read_start = addr
        read_end = addr + size

        starts = [r[0] for r in self._regions]
        idx = bisect_left(starts, read_start)
        # i = bisect.bisect_left(a, x)
        if idx > 0 and starts[idx] != read_start:
            idx -= 1

        rstart, rdata = self._regions[idx]

        rend = rstart + len(rdata)
        if read_end > rend or read_start < rstart:
            print(f'{read_end} > {rend} or {read_start} < {rstart}')
            raise ValueError(f"Not all data has been previously written")

        result = rdata[read_start - rstart : read_end - rstart]
        return bytes(result)

    def _merge_write(self, addr: int, data: bytes) -> None:
        "Perform a write and merge regsions if required"
        new_start = addr
        new_end = addr + len(data)

        merged_start = new_start
        merged_end = new_end

        overlapping: list[tuple[int, bytearray]] = []
        remaining: list[tuple[int, bytearray]] = []

        for rstart, rdata in self._regions:
            rend = rstart + len(rdata)
            # Touching (rend == new_start or rstart == new_end) counts
            # as adjacent and must be merged, hence strict < / > below.
            if rend < new_start or rstart > new_end:
                remaining.append((rstart, rdata))
            else:
                overlapping.append((rstart, rdata))
                merged_start = min(merged_start, rstart)
                merged_end = max(merged_end, rend)

        merged_buf = bytearray(merged_end - merged_start)

        # Lay down old (overlapping) data first...
        for rstart, rdata in overlapping:
            off = rstart - merged_start
            merged_buf[off:off + len(rdata)] = rdata

        # ...then overlay the new write so it takes precedence on
        # overlapping bytes.
        off = new_start - merged_start
        merged_buf[off:off + len(data)] = data

        remaining.append((merged_start, merged_buf))
        remaining.sort(key=lambda r: r[0])
        self._regions = remaining

    @staticmethod
    def _validate_addr_size(addr: int, size: int) -> None:
        if addr < 0 or size < 0:
            raise ValueError("addr and size must be non-negative")
        if addr > UINT32_MAX or (addr + size) > (UINT32_MAX + 1):
            raise ValueError("addr/size exceed 32-bit address space")

    def regions(self) -> list[tuple[int, bytes]]:
        """Return a read-only snapshot of the current regions as
        (address, bytes) tuples, sorted by address."""
        return [(addr, bytes(data)) for addr, data in self._regions]

    def clear(self) -> None:
        """Discard all cached data."""
        self._regions = []

    def __repr__(self) -> str:
        spans = ", ".join(
            f"0x{a:X}+{len(d)}" for a, d in self._regions
        )
        return f"FileCache({spans})"

    # ------------------------------------------------------------------
    # File persistence
    # ------------------------------------------------------------------

    def save_to_file(self, path: str) -> None:
        f"""Serialize the current cache contents to `path` using the
        {FILE_HEADER} binary format."""
        with open(path, "wb") as f:
            f.write(FILE_HEADER)
            for addr, data in self._regions:
                if len(data) > UINT32_MAX:
                    raise ValueError("region too large to serialize (>4GiB)")
                f.write(_REGION_HDR_STRUCT.pack(addr, len(data)))
                f.write(data)

    def load_from_file(self, path: str, replace: bool = True) -> None:
        """Load cache contents from `path`.

        Args:
            path: file to read.
            replace: if True (default), any existing cached data is
                discarded first. If False, loaded regions are merged
                into the existing cache using normal write-merge rules.
        """
        with open(path, "rb") as f:
            header = f.read(len(FILE_HEADER))
            if header != FILE_HEADER:
                raise ValueError( f"Not a valid skmap_cache_a file (bad header: {header!r})")

            loaded: list[tuple[int, bytearray]] = []
            while True:
                hdr = f.read(_REGION_HDR_STRUCT.size)
                if len(hdr) == 0:
                    break
                if len(hdr) != _REGION_HDR_STRUCT.size:
                    raise ValueError("Truncated file: incomplete region header")
                addr, size = _REGION_HDR_STRUCT.unpack(hdr)
                data = f.read(size)
                if len(data) != size:
                    raise ValueError("Truncated file: incomplete region data")
                loaded.append((addr, bytearray(data)))

        if replace:
            self._regions = loaded
        else:
            for addr, data in loaded:
                self._merge_write(addr, bytes(data))

