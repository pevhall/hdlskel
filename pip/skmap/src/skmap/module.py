from enum import Enum, auto, IntEnum
from typing import Optional, Type, Literal, Union
from abc import ABC, abstractmethod

# import rich
from rich.table import Table

from .console import console
from .regio import Regio
from .head import Head, SIZE_HEAD, SIZE_WORD, SYNC
from .basic_types import Acc, Ass, ValueKind, ValueType, value_type_u8, value_type_x32
from .basic import ceil_log2, ceil_div, ceil_multiple, promote_to_sw_w, bytes_to_list_int, list_int_to_bytes, cast_uint_to_sint

# class Fmt(Enum):
#     default = auto()
#     hex = auto()
#

def to_rich_str(s : str, color : Optional[str]=None):
    if color is not None:
        s = f'[{color}]{s}[/]'
    return s


class Reg:
    def __init__(self, module : "Module", name : str, value_type : ValueType, acc : Acc, desc : str): #, fmt : Fmt = Fmt.default): #, ass : Ass = Ass.none):
        # assert (ass != ass.passed)
        self.module = module
        self.name   = name
        self.value_type  = value_type
        self.acc    = acc
        # self.ass    = ass
        self.desc   = desc
        # self.fmt    = fmt
        self.size   = promote_to_sw_w(value_type.width)>>3
        self.elem_size = self.size
        self.addr : Optional[int]  = None

    def value_type_str(self) -> str:
        return f'{self.value_type}'

    def read_bytes_cached(self) -> bytes:
        assert isinstance(self.addr, int)
        return self.module.read_cache(self.addr, self.size)

    async def read_bytes(self) -> bytes:
        assert isinstance(self.addr, int)
        if self.acc == Acc.k:
            return self.read_bytes_cached()
        return await self.module.read_bytes(self.addr, self.size)

    def _bytes_to_uint(self, b:bytes) -> int:
        value_int = int.from_bytes(b, byteorder='little')
        if self.value_type.width != (self.size*8):
            mask = (1<<self.value_type.width)-1
            value_int &= mask
        return value_int

    def _bytes_to_sint(self, b:bytes) -> int:
        value_int = self._bytes_to_uint(b)
        sgn_bit = (1<<(self.value_type.width-1))
        if value_int >= sgn_bit:
            value_int -= sgn_bit*2
        return value_int

    def read_uint_cached(self) -> int:
        b = self.read_bytes_cached()
        return self._bytes_to_uint(b)

    def read_sint_cached(self) -> int:
        b = self.read_bytes_cached()
        return self._bytes_to_sint(b)

    def read_char_cached(self) -> str:
        assert self.value_type.width == 8
        value_uint = self.read_uint_cached()
        return chr(value_uint)

    def read_cached(self):
        match self.value_type.kind:
            case ValueKind.uint:
                return self.read_uint_cached()
            case ValueKind.sint:
                return self.read_sint_cached()
            case ValueKind.bits:
                return self.read_uint_cached()
            case ValueKind.flag:
                return self.read_uint_cached()
            case ValueKind.char:
                return self.read_char_cached()

    async def read_uint(self) -> int:
        b = await self.read_bytes()
        value_int = int.from_bytes(b, byteorder='little')
        # print(f'{value_int=:x} = int.from_bytes({b=})')
        return value_int

    async def read_sint(self) -> int:
        value_uint = await self.read_uint()
        return cast_uint_to_sint(value_uint, self.value_type.width)

    async def read_char(self) -> str:
        assert self.value_type.width == 8
        value_uint = await self.read_uint()
        return chr(value_uint)

    def read_rich_str_cached(self) -> str:
        match self.value_type.kind:
            case ValueKind.uint:
                value_str = str(self.read_uint_cached())
            case ValueKind.sint:
                value_str = str(self.read_sint_cached())
            case ValueKind.bits:
                value_str = f'0x{self.read_uint_cached():0{ceil_div(self.value_type.width,8)}X}'
            case ValueKind.flag:
                value_str = f'0b{self.read_uint_cached():0{self.value_type.width}b}'
            case ValueKind.char:
                value_str = self.read_char_cached()

        # print(f'{value_int=:x} = int.from_bytes({b=})')
        #TODO change to hex for bits / x
        return value_str

    async def write_bytes(self, b : bytes):
        assert self.acc in (Acc.rw, Acc.wt)
        assert isinstance(self.addr, int)
        assert len(b) <= self.size
        assert len(b) >= ceil_div(self.value_type.width, 8)
        return await self.module.write_bytes(self.addr, b)

    async def write_uint(self, v : int):
        b = v.to_bytes(self.size, byteorder='little', signed=False)
        return await self.write_bytes(b)

    async def write_sint(self, v : int):
        b = v.to_bytes(self.size, byteorder='little', signed=True)
        return await self.write_bytes(b)

    def add_to_table(self, table):
        table.add_row(str(self.addr), self.value_type_str(),  str(self.acc),  self.name, self.read_rich_str_cached(), self.desc)

class RegVec(Reg):

    def __init__(self,  *args, **kwargs):
        super().__init__(*args, **kwargs)
        assert isinstance(self.value_type.vec_len, int)
        self.elem_offset = self.size
        self.size  *= self.value_type.vec_len

    def _bytes_to_list_uint(self, b:bytes) -> list[int]:
        value_vec_int = bytes_to_list_int(b, self.elem_offset)
        if self.elem_size != (self.value_type.width*8):
            mask = (1<<self.value_type.width)-1
            for ii in range(len(value_vec_int)):
                value_vec_int[ii] &= mask
        return value_vec_int

    def _bytes_to_list_sint(self, b:bytes) -> list[int]:
        value_vec_int = self._bytes_to_list_uint(b)
        for ii in range(len(value_vec_int)):
            value_vec_int[ii] = cast_uint_to_sint(value_vec_int[ii], self.elem_size)
        return value_vec_int

    def read_vec_uint_cached(self) -> list[int]:
        b = self.read_bytes_cached()
        return self._bytes_to_list_uint(b)

    def read_vec_sint_cached(self) -> list[int]:
        b = self.read_bytes_cached()
        return self._bytes_to_list_sint(b)

    async def read_vec_uint(self) -> list[int]:
        b = self.read_bytes_cached()
        return self._bytes_to_list_uint(b)

    async def read_vec_sint(self) -> list[int]:
        b = await self.read_bytes()
        return self._bytes_to_list_sint(b)

    def read_idx_bytes_cached(self, idx : int) -> bytes:
        assert isinstance(self.addr, int)
        return self.module.read_cache(self.addr+idx*self.elem_offset, self.elem_size)

    async def read_idx_bytes(self, idx : int) -> bytes:
        assert isinstance(self.addr, int)
        if self.acc == Acc.k:
            return self.read_idx_bytes_cached(idx)
        return await self.module.read_bytes(self.addr+idx*self.elem_offset, self.elem_size)

    async def write_idx_bytes(self, idx : int, b : bytes):
        assert self.acc in (Acc.rw, Acc.wt)
        assert isinstance(self.addr, int)
        assert len(b) <= self.elem_size
        assert len(b) >= ceil_div(self.value_type.width, 8)
        return await self.module.write_bytes(self.addr+idx*self.elem_offset, b)

    def read_idx_uint_cached(self, idx : int) -> int:
        b = self.read_idx_bytes_cached(idx)
        return self._bytes_to_uint(b)

    def read_idx_sint_cached(self, idx : int) -> int:
        b = self.read_idx_bytes_cached(idx)
        return self._bytes_to_sint(b)

    async def read_idx_uint(self, idx : int) -> int:
        b = await self.read_idx_bytes(idx)
        return self._bytes_to_uint(b)

    async def read_idx_sint(self, idx : int) -> int:
        b = await self.read_idx_bytes(idx)
        return self._bytes_to_sint(b)

    async def write_idx_uint(self, idx : int, val : int):
        b = val.to_bytes(self.elem_size, byteorder='little', signed=False)
        await self.write_idx_bytes(idx, b)

    async def write_idx_sint(self, idx : int, val : int):
        b = val.to_bytes(self.elem_size, byteorder='little', signed=True)
        await self.write_idx_bytes(idx, b)

    def _vec_uint_to_str(self, value_vec_uint) -> str:
        assert self.elem_size==8
        assert self.elem_offset==8
        value_str = ''.join([chr(uint) for uint in value_vec_uint])
        return value_str

    def read_str_cached(self)  -> str:
        value_vec_uint = self.read_vec_uint_cached()
        return self._vec_uint_to_str(value_vec_uint)

    async def read_str(self)  -> str:
        value_vec_uint = await self.read_vec_uint()
        return self._vec_uint_to_str(value_vec_uint)

    async def write_vec_uint(self, value_vec_uint : list[int]):
        b = list_int_to_bytes(value_vec_uint, self.elem_size, endian='little', signed=False)
        await self.write_bytes(b)

    async def write_vec_sint(self, value_vec_uint : list[int]):
        b = list_int_to_bytes(value_vec_uint, self.elem_size, endian='little', signed=True)
        await self.write_bytes(b)

    # def value_type_str(self) -> str:
    #     return f'{super().value_type_str()}[{self.value_type.vec_len}]'

    def read_rich_str_cached(self) -> str:
        # assert self.fmt == Fmt.hex
        value_vec_int = self.read_vec_uint_cached()
        return str(value_vec_int)

class RegK(Reg):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs, acc = Acc.k) #, ass = Ass.none)

    async def read_int(self)  -> int:
        return self.read_uint_cached()

class RegVecK(RegVec):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs, acc = Acc.k) #, ass = Ass.none)

    async def read_int(self)  -> int:
        return self.read_uint_cached()

class RFlag:
    def __init__(self, name : str, bit : int, ass : Ass, desc : str, vec_len:Optional[int]=None):
        self.name = name
        self.bit  = bit
        self.ass  = ass
        self.desc = desc
        self.vec_len = vec_len

    def assign(self, reg_flags : 'RegFlags'):
        self.reg_flags = reg_flags

    def _ass_check(self, v : Union[list[bool], bool]) -> Ass:
        if self.ass == Ass.none:
            return Ass.none
        if isinstance(v, (list, tuple)):
            v = any(v)
        if not v:
            return Ass.passed
        return self.ass

    def _value_rich_str(self):
        if self.vec_len is None:
            v = self.read_bool_cached()
            ass_checked = self._ass_check(v)
            if self.ass == Ass.none:
                return f'{v}'
            return to_rich_str(f'{self.ass}: {v}', ass_checked.color)

        lv = self.read_list_bool_cached()
        ass_checked = self._ass_check(lv)
        s = ''
        if self.ass != Ass.none:
           s += to_rich_str(f'{self.ass}: ', ass_checked.color) 
        s = '0b'
        for v in lv:
            v = str(int(v))
            s += to_rich_str(v, ass_checked.color) 
        return s

    async def read_bool(self) -> bool:
        assert self.vec_len is None or self.vec_len == 1
        return (await self.reg_flags.read_uint() & (1<<self.bit)) != 0

    def read_bool_cached(self) -> bool:
        assert self.vec_len is None or self.vec_len == 1
        return (self.reg_flags.read_uint_cached() & (1<<self.bit)) != 0

    async def read_list_bool(self) -> list[bool]:
        assert self.vec_len is not None
        value_list_bool = []
        value_uint = await self.reg_flags.read_uint()
        for ii in range(self.vec_len):
            value_list_bool.append(value_uint & ((ii+1)<<self.bit) != 0)
        return value_list_bool

    def read_list_bool_cached(self) -> list[bool]:
        assert self.vec_len is not None
        value_list_bool = []
        value_uint =  self.reg_flags.read_uint_cached()
        for ii in range(self.vec_len):
            value_list_bool.append(value_uint & ((ii+1)<<self.bit) != 0)
        return value_list_bool

    async def ass_check(self) -> Ass:
        return self._ass_check(await self.read_bool())

    def ass_check_cached(self) -> Ass:
        return self._ass_check(self.read_bool_cached())

class RFlagK(RFlag):

    def __init__(self,  *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def read_bool(self) -> bool:
        return self.read_bool_cached()

    async def ass_check(self) -> Ass:
        return self.ass_check_cached()

class RegFlags(Reg):

    def __init__(self, *args, width : int, flags: list[RFlag], **kwargs):
        # assert 'value_type' not in kwargs
        # kwargs['value_type'] = ValueType(kind=ValueKind.flag, width=width)
        super().__init__(*args, value_type=ValueType(kind=ValueKind.flag, width=width), **kwargs) #, ass = Ass.none)
        self.flags = flags
        self.bit_flags = {}
        self.name_flags = {}
        for f in flags:
            f.assign(self)
            self.bit_flags[f.bit] = f
            self.name_flags[f.name] = f

    def add_to_table(self, table):
        Reg.add_to_table(self, table)
        # value_int = self.read_uint_cached()
        for f in self.flags:
            # b = f.bit
            # v = bool((value_int >> b) & 1)
            table.add_row('-', 'b',  f'{f.bit}',  f.name, f._value_rich_str(), f.desc)

        # table.add_row(str(self.addr), self.value_type_str(),  str(self.acc),  self.name, self.read_rich_str_cached(), self.desc)

    def ass_check(self) -> Ass:
        result : Ass = Ass.none
        value_int = self.read_uint_cached()
        for f in self.flags:
            v = bool((value_int >> f.bit) & 1)
            ass = f._ass_check(v)
            if ass > result:
                result = ass
        return Ass(result)

class RegFlagsK(RegFlags):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, acc = Acc.k, **kwargs) #, ass = Ass.none)

RegKTypes = Union[RegK, RegFlagsK]
class Module(ABC):

    def __init__(self, regio : Regio, addr : int, module_head : Head, module_data : bytearray):
        self.regio     = regio
        self.base_addr = addr
        self.head      = module_head
        self.cache     = module_data
        self.kids      = [0] * self.head.len_k
        self.arr_reg_k   : list[RegKTypes] = []
        self.arr_reg_var : list[Reg]  = []
        self.map_reg_k   : dict[str, RegKTypes] = {}
        self.map_reg_var : dict[str, Reg]  = {}
        self.use_cache = True
        self.byte_align = 0

        assert(self.head.sync == SYNC)
        assert(self.head.flags == 0)

        self.byte_idx = SIZE_HEAD
        assert(self.head.len_sub == 0)
        self.byte_idx += self.head.len_sub*SIZE_WORD

        for kk in range(self.head.len_kids):
            self.kids[kk] = int.from_bytes(module_data[self.byte_idx:self.byte_idx+SIZE_WORD])
            self.byte_idx += SIZE_WORD

        byte_idx_expected = self.byte_idx + self.head.len_k * SIZE_WORD
        self._init_reg_map_k()
        self.byte_idx = ceil_div(self.byte_idx, SIZE_WORD) * SIZE_WORD
        # print(f'{byte_idx_expected=} {self.byte_idx=}, {self.head.len_k=}')
        assert(byte_idx_expected == self.byte_idx)

        self.base_addr_var = self.byte_idx
        self.size_var = self.head.len_var * SIZE_WORD
        byte_idx_expected = self.byte_idx + self.size_var
        self._init_reg_map_var()
        # print(f'{byte_idx_expected=} {self.byte_idx=}, {self.head.len_var=}')
        self.byte_idx = ceil_div(self.byte_idx, SIZE_WORD) * SIZE_WORD
        assert byte_idx_expected == self.byte_idx, f'head var len = {self.head.len_var=}, map var len {self.byte_idx/SIZE_WORD-self.base_addr_var/SIZE_WORD}'

        self.use_cache = False

    def _cache_addr(self, addr:int) -> int:
        return addr - self.base_addr

    def read_cache(self, addr:int, size : int) -> bytes:
        cache_addr = self._cache_addr(addr)
        ba = self.cache[cache_addr:cache_addr + size]
        # print(f'{ba=}, {addr=}, {cache_addr=}, {size=}')
        return bytes(ba)

    async def read_bytes(self, addr:int, size : int) -> bytes:
        if self.use_cache:
            return self.read_cache(addr, size)
        else:
            cache_addr = self._cache_addr(addr)
            # print(f'self.regio.read({addr}, {size})')
            b = await self.regio.read(addr, size)
            self.cache[cache_addr:cache_addr + size] = b
            return b

    async def write_bytes(self, addr:int, b : bytes):
        cache_addr = self._cache_addr(addr)
        # print(f'self.regio.write({addr}, {b})')
        await self.regio.write(addr, b)
        self.cache[cache_addr:cache_addr + len(b)] = b

    async def update_cache(self):
        assert not self.use_cache
        _ = await self.read_bytes(self.base_addr_var, self.size_var)
        # self.read_bytes(self.base_addr+


    def _byte_idx_add_reg(self, reg):
        self.byte_idx += reg.size

    def _byte_idx_align_addr_width(self, width):
        if self.byte_align == 0:
            align_bytes = promote_to_sw_w(width)//8
        else:
            assert self.byte_align > 0
            align_bytes = self.byte_align
        print(f'{ceil_multiple(self.byte_idx, align_bytes)} = ceil_multiple({self.byte_idx}, {align_bytes})')
        self.byte_idx = ceil_multiple(self.byte_idx, align_bytes)

    def _add_reg_k(self, reg : RegKTypes):
        self._byte_idx_align_addr_width(reg.value_type.width)
        reg.addr = self.byte_idx + self.base_addr
        self.arr_reg_k.append(reg)
        self.map_reg_k[reg.name] = reg
        self._byte_idx_add_reg(reg)
        self._byte_idx_align_addr_width(reg.value_type.width)

    def _add_reg_var(self, reg : Reg):
        self._byte_idx_align_addr_width(reg.value_type.width)

        reg.addr = self.byte_idx + self.base_addr
        self.arr_reg_var.append(reg)
        self.map_reg_var[reg.name] = reg
        self._byte_idx_add_reg(reg)

        self._byte_idx_align_addr_width(reg.value_type.width)
        print(f'map var {reg.name} at {self.byte_idx=} {self.byte_align=} {reg.value_type.width=}')

    @classmethod
    @abstractmethod
    def name(cls) -> str:
        pass

    @classmethod
    @abstractmethod
    def id(cls) -> str:
        pass

    @classmethod
    @abstractmethod
    def ver_major(cls) -> int:
        pass

    @abstractmethod
    def _init_reg_map_k(self) -> None:
        pass

    @abstractmethod
    def _init_reg_map_var(self) -> None:
        pass

    def _init_post_reg_maps(self) -> None:
        pass

    def reg_map_table(self) -> Table:
        table = Table(title=f"skmap {self.name} {self.head}")
        table.add_column("Addr",        justify="right", style="cyan", no_wrap=True)
        # table.add_column("W",           justify="right", style="blue", no_wrap=True)
        table.add_column("T",           justify="right", style="blue", no_wrap=True)
        table.add_column("Acc",         justify="left",  style="blue", no_wrap=True)
        # table.add_column("Ass",         justify="left",                no_wrap=True)
        table.add_column("Name",        justify="left",  style="cyan")
        table.add_column("Value",       justify="right", style=Ass.none.color)
        table.add_column("Description", justify="left",  style="blue")

        for reg in self.arr_reg_k:
            reg.add_to_table(table)

        for reg in self.arr_reg_var:
            reg.add_to_table(table)

        return table

    def reg_map_print(self) :
        table = self.reg_map_table()
        console.print(table)

class ModuleUnkowen(Module):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @classmethod
    def name(cls) -> str:
        return "Unkowen";

    @classmethod
    def id(cls) -> str:
        assert False

    @classmethod
    def ver_major(cls) -> int:
        assert False

    def _init_reg_map_k(self):
        for ii in range(self.head.len_k):
            reg = RegK(self, name=f'UNKOWN_K_{ii}', value_type=value_type_x32, desc=f"Unkowen constant {ii}")
            self._add_reg_k(reg)

    def _init_reg_map_var(self):
        for ii in range(self.head.len_var):
            reg = Reg(self, name=f'UNKOWN_VAR_{ii}', value_type=value_type_x32, desc=f"Unkowen variable {ii}", acc=Acc.na)
            self._add_reg_var(reg)


# async def read_init_module_data(regio : Regio, addr : int):
#     head_data = await regio.read(addr, SIZE_HEAD)
#     module_head = Head(head_data)
#     print(f"{module_head=}")
#     module_size = module_head.module_size()
#     module_data = bytearray(head_data + await regio.read(addr+SIZE_HEAD, module_size-SIZE_HEAD))
#     print(f"{module_data=}")
#     return regio, addr, module_head, module_data

def singleton(cls):
    instances = {}

    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]

    return get_instance

@singleton
class ModuleFactory():


    def __init__(self):
        self.lookup : dict[str, dict[int, Type[Module]]] = {}

    def register_module(self, module_class : Type[Module]):
        if module_class.id() not in self.lookup:
            self.lookup[module_class.id()] = {}
        module_lookup = self.lookup[module_class.id()]

        assert module_class.ver_major() not in module_lookup
        module_lookup[module_class.ver_major()] = module_class

    async def make_Module(self, regio : Regio, addr : int, allow_unknowen = False) -> Module:
        head_data = await regio.read(addr, SIZE_HEAD)
        module_head = Head(head_data)
        print(f"{module_head=}")
        module_size = module_head.module_size()
        module_data = bytearray(head_data + await regio.read(addr+SIZE_HEAD, module_size-SIZE_HEAD))
        print(f"{module_data=}")
        if module_head.id in self.lookup:
            module_lookup = self.lookup[module_head.id]
            if module_head.ver_major in module_lookup:
                return module_lookup[module_head.ver_major](regio, addr, module_head, module_data)


        assert allow_unknowen
        return ModuleUnkowen(regio, addr, module_head, module_data)

async def make_Module(regio : Regio, addr : int, allow_unknowen = False) -> Module:
    factory = ModuleFactory()
    return await factory.make_Module(regio, addr, allow_unknowen)

def register_Module(module_class : Type[Module]):
    factory = ModuleFactory()
    factory.register_module(module_class)

