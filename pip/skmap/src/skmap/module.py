from enum import Enum, auto
from typing import Optional
from abc import ABC, abstractmethod


import rich
from rich.table import Table

from .console import console
from .regio import Regio
from .head import Head, SIZE_HEAD, SIZE_WORD, SYNC

def ceil_log2(x):
    return (x - 1).bit_length() if x > 0 else 0

def ceil_div(n, d):
    return (n + d - 1) // d

class Acc(Enum):
    na = auto()
    k  = auto()
    ro = auto()
    rc = auto()
    rw = auto()
    ws = auto()

class Ass(Enum):
    none    = auto()
    debug   = auto()
    info    = auto()
    warn    = auto()
    error   = auto()
    failure = auto()

class Fmt(Enum):
    hex = auto()

class Reg:
    def __init__(self, module : "Module", name : str, width : int, desc : str, acc : Acc, fmt : Fmt = Fmt.hex, ass : Ass = Ass.none):
        self.module = module
        self.name   = name
        self.width  = width
        self.acc    = acc
        self.ass    = ass
        self.desc   = desc
        self.fmt    = fmt
        self.size   = ceil_div(width, 8)
        print(f'{width=}, {self.size=}')
        self.addr : Optional[int]  = None

    def value_str(self) -> str:
        assert isinstance(self.addr, int)
        assert self.fmt == Fmt.hex
        b = self.module.read_cache(self.addr, self.size)
        value = int.from_bytes(b, byteorder='little')
        print(f'{value=:x} = int.from_bytes({b=})')
        return f"0x{value:x}"

    def ass_str(self) -> str:
        return str(self.ass)

class RegK(Reg):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs, acc = Acc.k, ass = Ass.none)

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
        assert(byte_idx_expected == self.byte_idx)
        print(f'{byte_idx_expected=} {self.byte_idx=}, {self.head.len_k=}')

        byte_idx_expected = self.byte_idx + self.head.len_var * SIZE_WORD
        self._init_reg_map_var()
        print(f'{byte_idx_expected=} {self.byte_idx=}, {self.head.len_var=}')
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

    def _add_reg_k(self, reg : RegK):
        reg.addr = self.byte_idx + self.base_addr
        self.arr_reg_k.append(reg)
        self.map_reg_k[reg.name] = reg
        self.byte_idx += reg.size

    def _add_reg_var(self, reg : Reg):
        reg.addr = self.byte_idx + self.base_addr
        self.arr_reg_var.append(reg)
        self.map_reg_var[reg.name] = reg
        self.byte_idx += reg.size
        print(f'{self.byte_idx=}')

    @abstractmethod
    def name(self) -> str:
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
        table = Table(title=f"skmap {self.name()} {self.head}")
        table.add_column("Addr", justify="right", style="cyan", no_wrap=True)
        table.add_column("W", justify="right", style="blue", no_wrap=True)
        table.add_column("Acc", justify="left", style="cyan", no_wrap=True)
        table.add_column("Ass", justify="left", no_wrap=True)
        table.add_column("Name", justify="left", style="cyan")
        table.add_column("Value", justify="right", style="green")
        table.add_column("Description", justify="left", style="blue")

        for reg in self.arr_reg_k:
            table.add_row(str(reg.addr), str(reg.width), str(reg.acc), str(reg.ass), reg.name, reg.value_str(), reg.desc)
        for reg in self.arr_reg_var:
            table.add_row(str(reg.addr), str(reg.width), str(reg.acc), str(reg.ass), reg.name, reg.value_str(), reg.desc)


        return table

    def reg_map_print(self) :
        table = self.reg_map_table()
        console.print(table)


class ModuleUnkowen(Module):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def name(self):
        return "Unkowen";

    def _init_reg_map_k(self):
        for ii in range(self.head.len_k):
            reg = RegK(self, f'UNKOWN_K_{ii}', SIZE_WORD*8, "Unkowen constant {ii}")
            self._add_reg_k(reg)


    def _init_reg_map_var(self):
        for ii in range(self.head.len_var):
            reg = Reg(self, f'UNKOWN_VAR_{ii}', SIZE_WORD*8, f"Unkowen variable {ii}", acc=Acc.na)
            self._add_reg_var(reg)


async def read_init_module_data(regio : Regio, addr : int):
    head_data = await regio.read(addr, SIZE_HEAD)
    module_head = Head(head_data)
    print(f"{module_head=}")
    module_size = module_head.module_size()
    module_data = bytearray(head_data + await regio.read(addr+SIZE_HEAD, module_size-SIZE_HEAD))
    print(f"{module_data=}")
    return regio, addr, module_head, module_data

async def make_Module(*args, **kwargs) -> Module:
    params = await read_init_module_data(*args, **kwargs)
    return ModuleUnkowen(*params)
