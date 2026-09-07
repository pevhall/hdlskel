from .regio import Regio
from .basic import cast_uint_to_sint, ceil_div
from .basic_types import Acc, ValueType, ValueKind

class ExternalMem(Regio):
    def __init__(self, regio : Regio, base_addr : int, size : int, acc : Acc = Acc.na):
        Regio.__init__(self)
        self._regio      = regio
        self._base_addr  = base_addr
        self._size       = size
        self._acc        = acc
        self._name       = None
        self._value_type = None
        self._desc       = None

    def details(self, name : str, value_type : ValueType, acc : Acc, desc : str):
        self._name       = name
        self._value_type = value_type
        assert self._size == self._value_type.total_size
        if self._acc == Acc.na:
            self._acc        = acc
        else:
            assert self._acc == acc
        self._desc       = desc

    @property
    def name(self) -> str:
        assert self._name is not None
        return self._name

    @property
    def value_type(self) -> ValueType:
        assert self._value_type is not None
        return self._value_type

    def value_type_str(self) -> str:
        return f'{self._value_type}'

    @property
    def acc(self) -> Acc:
        return self._acc

    @property
    def desc(self) -> str:
        assert self._desc is not None
        return self._desc

    @property
    def base_addr(self) -> int:
        return self._base_addr

    @property
    def size(self) -> int:
        return self._size

    def regio_addr(self, addr:int) -> int:
        return addr + self._base_addr

    def check_size(self, addr:int, size : int):
        assert addr + size <= self._size;

    async def dev_write(self, addr : int, data : bytes) -> None:
        self.check_size(addr, len(data))
        a = self.regio_addr(addr)
        await self._regio.dev_write(a, data)

    async def dev_read(self, addr : int, size : int) -> bytes:
        self.check_size(addr, size)
        a = self.regio_addr(addr)
        return await self._regio.dev_read(a, size)

class ExternalMemCached(ExternalMem):
    def __init__( self, regio : Regio, base_addr : int, size_bytes : int, acc = Acc.na):
        ExternalMem.__init__(self, regio, base_addr, size_bytes, acc)
        self._cache = bytearray(size_bytes)
        self._cache_loaded = True

    @property
    def cache_loaded(self):
        return self._cache_loaded

    def write_cached(self, addr : int, data : bytes) -> None:
        self.check_size(addr, len(data))
        self._cache[addr:addr+len(data)] = data
        if addr == 0 and len(data) == self.size:
            self._cache_loaded=True

    def read_cached(self, addr : int, size : int) -> bytes:
        self.check_size(addr, size)
        return bytes(self._cache[addr:addr+size])

    async def dev_write(self, addr : int, data : bytes) -> None:
        await ExternalMem.dev_write(self, addr, data)
        self.write_cached(addr, data)

    async def dev_read(self, addr : int, size : int) -> bytes:
        data = await ExternalMem.dev_read(self, addr, size)
        self.write_cached(addr, data)
        return data

class ExternalMemVec(ExternalMemCached):

    @property
    def elem_size(self) -> int:
        assert self._value_type is not None
        return self._value_type.elem_size

    def vec_len(self) -> int:
        assert self._value_type is not None
        assert self._value_type.vec_len is not None
        return self._value_type.vec_len

    def read_idx_bytes_cached(self, idx : int) -> bytes:
        addr = self.elem_size * idx
        return self.read_cached(addr, self.elem_size)

    async def read_idx_bytes(self, idx : int) -> bytes:
        addr = self.elem_size * idx
        return await self.read(addr, self.elem_size)

    def read_idx_uint_cached(self, idx : int) -> int:
        b = self.read_idx_bytes_cached(idx)
        return int.from_bytes(b, byteorder='little')

    async def read_idx_uint(self, idx : int) -> int:
        _ = await self.read_idx_bytes(idx)
        return self.read_idx_uint_cached(idx)

    def read_idx_sint_cached(self, idx : int) -> int:
        assert self._value_type is not None
        value_int = self.read_idx_uint_cached(idx)
        return cast_uint_to_sint(value_int, self._value_type.width)

    async def read_idx_sint(self, idx : int) -> int:
        _ = await self.read_idx_bytes(idx)
        return self.read_idx_sint_cached(idx)

    def read_idx_value_cached(self, idx : int):
        assert self._value_type is not None
        match self._value_type.kind:
            case ValueKind.uint: return self.read_idx_uint_cached(idx)
            case ValueKind.sint: return self.read_idx_sint_cached(idx)
            case ValueKind.bits: return self.read_idx_uint_cached(idx)
            case ValueKind.flag: assert(False)
            case ValueKind.char: assert(False)

    def read_idx_rich_str_cached(self, idx : int) -> str:
        base = 10
        match self.value_type.kind:
            case ValueKind.uint:
                value = self.read_idx_uint_cached(idx)
            case ValueKind.sint:
                value = self.read_idx_sint_cached(idx)
            case ValueKind.bits:
                value = self.read_idx_uint_cached(idx)
                base = 16
            case ValueKind.flag: assert(False)
            case ValueKind.char: assert(False)

        match (base):
            # case 2:  return f'0b{value:0{self.value_type.width}b}'
            case 10: return str(value)
            case 16: return f'0x{value:0{ceil_div(self.value_type.width,8)}X}'

    async def write_idx_cache(self, idx : int):
        b = self.read_idx_bytes_cached(idx)
        addr = self.elem_size * idx
        await self.write(addr, b)

    def write_idx_bytes_cached(self, idx : int, b : bytes):
        assert(len(b) == self.elem_size)
        addr = self.elem_size * idx
        self.write_cached(addr, b)

    async def write_idx_bytes(self, idx : int, b : bytes):
        self.write_idx_bytes_cached(idx, b)
        await self.write_idx_cache(idx)

    def write_idx_uint_cached(self, idx : int, val : int):
        b = val.to_bytes(self.elem_size, byteorder='little', signed=False)
        self.write_idx_bytes_cached(idx, b)

    async def write_idx_uint(self, idx : int, val : int):
        self.write_idx_uint_cached(idx, val)
        await self.write_idx_cache(idx)

    def write_idx_sint_cached(self, idx : int, val : int):
        b = val.to_bytes(self.elem_size, byteorder='little', signed=True)
        self.write_idx_bytes_cached(idx, b)

    async def write_idx_sint(self, idx : int, val : int):
        self.write_idx_sint_cached(idx, val)
        await self.write_idx_cache(idx)


def external_mem_cast_to_derived_if_possible(mem : ExternalMem) -> ExternalMem:
    if not isinstance(mem, ExternalMemCached):
        return mem

    assert mem._value_type is not None

    if not mem._value_type.is_vec:
        return mem
    
    assert (mem.size == mem._value_type.total_size)
    mem.__class__ = ExternalMemVec # just convert the class as not extra data is added
    return mem

