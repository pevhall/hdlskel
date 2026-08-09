from .regio import Regio
from .basic_types import Acc,  ValueType

class ExternalMem(Regio):
    def __init__(self, regio : Regio, base_addr : int, size : int):
        Regio.__init__(self)
        self._regio      = regio
        self._base_addr  = base_addr
        self._size       = size
        self._name       = None
        self._value_type = None
        self._acc        = None
        self._desc       = None

    def details(self, name : str, value_type : ValueType, acc : Acc, desc : str):
        self._name       = name
        self._value_type = value_type
        self._acc        = acc
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
        assert self._acc is not None
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
    def __init__( self, regio : Regio, base_addr : int, size_bytes : int):
        ExternalMem.__init__(self, regio, base_addr, size_bytes)
        self.cache = bytearray(size_bytes)

    def write_cached(self, addr : int, data : bytes) -> None:
        self.check_size(addr, len(data))
        self.cache[addr:addr+len(data)] = data

    def read_cached(self, addr : int, size : int) -> bytes:
        self.check_size(addr, size)
        return bytes(self.cache[addr:addr+size])
