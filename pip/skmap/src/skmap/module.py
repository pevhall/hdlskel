import logging
from enum import Enum, auto, IntEnum
from typing import Optional, Type, Literal, Union
from abc import ABC, abstractmethod

# import rich
from rich.table import Table

from .console import console
from .regio import Regio
from .head import Head, SIZE_HEAD, SIZE_WORD, SYNC
from .basic_types import Acc, Ass, ValueKind, ValueType, value_type_u8, value_type_x32
from .basic import ceil_log2, ceil_div, ceil_multiple, promote_to_sw_w, bytes_to_list_int, list_int_to_bytes, cast_uint_to_sint, to_rich_str
from .reg import Reg, RegVec, RegK, RegVecK, RegFlags, RegFlagsK

# class Fmt(Enum):
#     default = auto()
#     hex = auto()
#



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

    def write_bytes_cache(self, addr:int, b:bytes):
        cache_addr = self._cache_addr(addr)
        self.cache[cache_addr:cache_addr + len(b)] = b

    async def write_bytes(self, addr:int, b : bytes):
        # print(f'self.regio.write({addr}, {b})')
        await self.regio.write(addr, b)
        self.write_bytes_cache(addr, b)

    async def read_cache_all(self):
        assert not self.use_cache
        _ = await self.read_bytes(self.base_addr_var, self.size_var)

    async def write_cache_all(self):
        cache_addr = self._cache_addr(self.base_addr_var)
        assert not self.use_cache
        await self.write_bytes(self.base_addr_var, bytes(self.cache[cache_addr:cache_addr+self.size_var]))

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

    def write_zero_all_rc_cached(self):
        for reg_var in self.arr_reg_var:
            reg_var.write_zero_cache()

    async def write_zero_all_rc(self):
        for reg_var in self.arr_reg_var:
            if reg_var.acc == Acc.rc:
                await reg_var.write_zero()

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
    def version(cls) -> int:
        pass

    @classmethod
    @abstractmethod
    def checksum(cls) -> int:
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
    def version(cls) -> int:
        assert False

    @classmethod
    def checksum(cls) -> int:
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

        assert module_class.version() not in module_lookup
        module_lookup[module_class.version()] = module_class

    async def make_Module(self, regio : Regio, addr : int, allow_unknowen = False) -> Module:
        head_data = await regio.read(addr, SIZE_HEAD)
        module_head = Head(head_data)
        logging.info('module_head =  %s', module_head)
        module_size = module_head.module_size()
        module_data = bytearray(head_data + await regio.read(addr+SIZE_HEAD, module_size-SIZE_HEAD))
        # print(f"{module_data=}")
        if module_head.id in self.lookup:
            module_lookup = self.lookup[module_head.id]
            if module_head.version in module_lookup:
                module_class = module_lookup[module_head.version]
                if module_head.checksum == module_class.checksum():
                    return module_class(regio, addr, module_head, module_data)
                else:
                    logging.error('Bad check sum for %s v%d, module_head.checksum =  %s, module_class.checksum = %s', module_class.name(), module_class.version(), module_head.checksum, module_class.checksum())



        assert allow_unknowen
        return ModuleUnkowen(regio, addr, module_head, module_data)

async def make_Module(regio : Regio, addr : int, allow_unknowen = False) -> Module:
    factory = ModuleFactory()
    return await factory.make_Module(regio, addr, allow_unknowen)

def register_Module(module_class : Type[Module]):
    factory = ModuleFactory()
    factory.register_module(module_class)

