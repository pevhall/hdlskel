from .basic_types import Acc, Ass, ValueKind, ValueType
from .reg import Reg, RegVec, RegK, RegVecK, RegFlags, RegFlagsK, RFlag
from .external_mem import ExternalMem
from typing import Union

from rich.table import Table
from rich.text import Text
from .console import console

def desc_cell(obj : Union[Reg, RFlag, ExternalMem]):
    """Description cell of the reg map.

    A register with a value conversion (`v_convert_wr` / `v_convert_rd` of the
    recipe) shows the conversion in front of its description, in the color of
    Ass.none: the value in the value column is the value of the module user,
    not the value stored in the register.
    """
    marker = obj.v_convert_marker() if isinstance(obj, Reg) else ''
    if not marker:
        return obj.desc
    return Text.assemble((marker, Ass.none.color), (obj.desc,))

class RegMapTable :

    def __init__(self, title : str):
        self._table = Table(title=title)
        self._table.add_column("Addr",        justify="right", style="cyan", no_wrap=True)
        self._table.add_column("T",           justify="right", style="blue", no_wrap=True)
        self._table.add_column("Acc",         justify="left",  style="blue", no_wrap=True)
        self._table.add_column("Name",        justify="left",  style="cyan")
        self._table.add_column("Value",       justify="right", style=Ass.none.color)
        self._table.add_column("Description", justify="left",  style="blue")

    def add_flag(self, f : RFlag):
        self._table.add_row('-', 'b',  f'{f.bit}',  f.name, f._value_rich_str(), desc_cell(f))

    def add_reg(self, reg : Reg, expand_flags : bool = False):
        assert reg.addr is not None
        self._table.add_row(hex(reg.addr), reg.value_type_str(),  str(reg.acc),  reg.name, reg.read_rich_str_cached(), desc_cell(reg))
        if expand_flags and isinstance(reg, RegFlags):
            for f in reg.flags:
                self.add_flag(f)

    def add_mem(self, mem : ExternalMem):
        type_str = f'{mem.value_type_str()}'
        self._table.add_row(hex(mem.base_addr), type_str, str(mem.acc), mem.name, f"(Mem size:{mem.size} B)", desc_cell(mem))

    def add_module(self, module):
        for reg in module.arr_reg_k:
            self.add_reg( reg, expand_flags=True)

        for reg in module.arr_reg_var:
            self.add_reg( reg, expand_flags=True)

        for mem in module.arr_external_mem:
            self.add_mem( mem )

    def print(self):
        console.print(self._table)

def print_table_reg_list(l : list[Union[RFlag, Reg]], title, prepend_regs = True):
    """ Print table of flags
    NOTE: expects flags to be in order
    """
    table = RegMapTable(title=title)
    reg_prev = None
    for v in l:
        # if isinstance(v, RFlag):
        if v.is_flag:
            reg = v.reg_flags
            if prepend_regs and reg is not reg_prev:
                table.add_reg( reg, expand_flags=False)
                reg_prev = reg
            table.add_flag( v)
        else:
            # assert isinstance(v, Reg)
            assert v.is_reg
            table.add_reg(v)
    table.print()
