from enum import Enum, auto, IntEnum
from typing import Optional, Type, Literal
from abc import ABC, abstractmethod

import rich
from rich.table import Table

from .console import console
from .regio import Regio
from .head import Head, SIZE_HEAD, SIZE_WORD, SYNC

def ceil_log2(x : int) -> int:
    return (x - 1).bit_length() if x > 0 else 0

def ceil_div(n : int, d : int) -> int:
    return (n + d - 1) // d

def ceil_multiple(num : int, multiple : int) -> int:
    return ceil_div(num, multiple)*multiple

def promote_to_sw_w(w : int) -> int:
    return 2**ceil_log2(ceil_multiple(w, 8))

def bytearray_to_int_list(ba:bytearray, size:int, endian : Literal['little','big']='little') -> list[int]:
    if len(ba) % size != 0:
        raise ValueError("bytearray length must be a multiple of size")

    out = []
    for i in range(0, len(ba), size):
        chunk = ba[i:i+size]
        out.append(int.from_bytes(chunk, endian))
    return out

class Acc(Enum):
    na = auto()
    k  = auto()
    ro = auto()
    rc = auto()
    rw = auto()
    ws = auto()

    def __str__(self):
        return self.name

class Ass(IntEnum):
    none    = -1
    passed  = 0
    debug   = 1
    info    = 2
    warn    = 3
    error   = 4
    failure = 5

    def __str__(self):
        if self.name == 'none':
            return '-'
        return self.name

    @property
    def color(self)->str:
        return {
            Ass.none:    "white",
            Ass.passed:  "green",
            Ass.debug:   "cyan",
            Ass.info:    "yellow",
            Ass.warn:    "orange",
            Ass.error:   "red",
            Ass.failure: "bright_red",
        }[self]

class ValueKind(Enum):
    uint = auto()
    sint = auto()
    char = auto()
    bits = auto()
    flag = auto()

    @property
    def char_str(self):
        return {
            ValueKind.bits: "x",
            ValueKind.uint: "u",
            ValueKind.sint: "s",
            ValueKind.char: "c",
            ValueKind.flag: "b",
        }[self]

class ValueType:
    def __init__(self, kind : ValueKind, width : int):
        assert(width >= 0)
        self.kind = kind
        self.width = width

    def __repr__(self):
        return f'{self.kind.char_str}{self.width}'

value_type_u8 = ValueType(kind=ValueKind.uint, width=8)
value_type_x32 = ValueType(kind=ValueKind.uint, width=8)

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
        self.value_type = value_type
        self.size   = promote_to_sw_w(value_type.width)>>3
        self.elem_size = self.size
        self.addr : Optional[int]  = None
        self.vec_len  = 1


    def value_type_str(self) -> str:
        return f'{self.value_type}'

    def value_bytearray_from_cache(self) -> bytearray:
        assert isinstance(self.addr, int)
        return self.module.read_cache(self.addr, self.size)

    def value_int_from_cache(self)  -> int:
        b = self.value_bytearray_from_cache()
        value_int = int.from_bytes(b, byteorder='little')
        print(f'{value_int=:x} = int.from_bytes({b=})')
        return value_int

    def value_rich_str(self) -> str:
        value_int = self.value_int_from_cache()
        #TODO change to hex for bits / x
        return str(value_int)

    def add_to_table(self, table):
        table.add_row(str(self.addr), self.value_type_str(),  str(self.acc),  self.name, self.value_rich_str(), self.desc)

class RegVec(Reg):

    def __init__(self,  *args, vec_len:Optional[int]=None, **kwargs):
        super().__init__(*args, **kwargs)
        assert(vec_len is not None)
        self.vec_len = vec_len
        self.size  *= vec_len

    def value_vec_int_from_cache(self)  -> list[int]:
        b = self.value_bytearray_from_cache()
        value_vec_int = bytearray_to_int_list(b, self.elem_size)
        # print(f'{value_int=:x} = int.from_bytes({b=})')
        return value_vec_int

    def value_type_str(self) -> str:
        return f'{super().value_type_str()}[{self.vec_len}]'

    def value_rich_str(self) -> str:
        # assert self.fmt == Fmt.hex
        value_vec_int = self.value_vec_int_from_cache()
        return str(value_vec_int)


class RegK(Reg):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs, acc = Acc.k) #, ass = Ass.none)

    def value_int(self)  -> int:
        return self.value_int_from_cache()

class RegVecK(RegVec):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs, acc = Acc.k) #, ass = Ass.none)

    def value_vec_int(self)  -> int:
        return self.value_int_from_cache()

class RFlag:
    def __init__(self, name : str, ass : Ass, desc : str):
        self.name = name
        self.ass  = ass
        self.desc = desc

    def ass_check(self, v : bool) -> Ass:
        if self.ass == Ass.none:
            return Ass.none
        if not v:
            return Ass.passed
        return self.ass

    def value_rich_str(self, v : bool):
        if self.ass == Ass.none:
            return f'{v}'
        ass_checked = self.ass_check(v)
        return to_rich_str(f'{self.ass}: {v}', ass_checked.color)


class RegFlags(Reg):

    def __init__(self, *args, width : int, flags: dict[int, RFlag], **kwargs):
        # assert 'value_type' not in kwargs
        # kwargs['value_type'] = ValueType(kind=ValueKind.flag, width=width)
        super().__init__(*args, value_type=ValueType(kind=ValueKind.flag, width=width), **kwargs) #, ass = Ass.none)
        self.flags = flags

    def add_to_table(self, table):
        Reg.add_to_table(self, table)
        value_vec_int = self.value_int_from_cache()
        for b, f in self.flags.items():
            v = bool((value_vec_int >> b) & 1)
            table.add_row('-', 'b',  f'{b}',  f.name, f.value_rich_str(v), f.desc)

        table.add_row(str(self.addr), self.value_type_str(),  str(self.acc),  self.name, self.value_rich_str(), self.desc)

    def ass_check(self) -> Ass:
        result : Ass = Ass.none
        value_vec_int = self.value_int_from_cache()
        for b, f in self.flags.items():
            v = bool((value_vec_int >> b) & 1)
            ass = f.ass_check(v)
            if ass > result:
                result = ass
        return Ass(result)


class Module(ABC):

    def __init__(self, regio : Regio, addr : int, module_head : Head, module_data : bytearray):
        self.regio     = regio
        self.base_addr = addr
        self.head      = module_head
        self.cache     = module_data
        self.kids      = [0] * self.head.len_k
        self.arr_reg_k   : list[RegK] = []
        self.arr_reg_var : list[Reg]  = []
        self.map_reg_k   : dict[str, RegK] = {}
        self.map_reg_var : dict[str, Reg]  = {}
        self.use_cache = True
        self.byte_align = 1

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
        print(f'{byte_idx_expected=} {self.byte_idx=}, {self.head.len_k=}')
        assert(byte_idx_expected == self.byte_idx)

        byte_idx_expected = self.byte_idx + self.head.len_var * SIZE_WORD
        self._init_reg_map_var()
        print(f'{byte_idx_expected=} {self.byte_idx=}, {self.head.len_var=}')
        self.byte_idx = ceil_div(self.byte_idx, SIZE_WORD) * SIZE_WORD
        assert(byte_idx_expected == self.byte_idx)

        self.use_cache = False

    def _cache_addr(self, addr:int) -> int:
        return addr - self.base_addr

    def read_cache(self, addr:int, size : int) -> bytearray:
        cache_addr = self._cache_addr(addr)
        ba = self.cache[cache_addr:cache_addr + size]
        print(f'{ba=}, {addr=}, {cache_addr=}, {size=}')
        return ba

    async def read(self, addr:int, size : int) -> bytearray:
        if self.use_cache:
            return self.read_cache(addr, size)
        else:
            cache_addr = self._cache_addr(addr)
            b = await self.regio.read(addr, size)
            self.cache[cache_addr:cache_addr + size] = b
            return b
    def _byte_idx_add_reg(self, reg):
        print(f'{reg.size=}')
        self.byte_idx += reg.size

    def _add_reg_k(self, reg : RegK):
        reg.addr = self.byte_idx + self.base_addr
        self.arr_reg_k.append(reg)
        self.map_reg_k[reg.name] = reg
        self._byte_idx_add_reg(reg)

    def _add_reg_var(self, reg : Reg):
        reg.addr = self.byte_idx + self.base_addr
        self.arr_reg_var.append(reg)
        self.map_reg_var[reg.name] = reg
        self._byte_idx_add_reg(reg)
        print(f'{self.byte_idx=}')

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
            # table.add_row(str(reg.addr), reg.value_type_str(),  str(reg.acc),  reg.name, reg.value_rich_str(), reg.desc)
        for reg in self.arr_reg_var:
            reg.add_to_table(table)
            # table.add_row(str(reg.addr), reg.value_type_str(),  str(reg.acc),  reg.name, reg.value_rich_str(), reg.desc)
            # table.add_row(str(reg.addr), reg.vec_len_str(), str(reg.width), str(reg.acc), reg.ass_rich_str(), reg.name, reg.value_rich_str(), reg.desc)


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
            reg = RegK(self, name=f'UNKOWN_K_{ii}', value_type=value_type_x32, desc="Unkowen constant {ii}")
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

