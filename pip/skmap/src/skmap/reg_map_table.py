from .basic_types import Acc, Ass, ValueKind, ValueType
from .reg import Reg, RegVec, RegK, RegVecK, RegFlags, RegFlagsK, RFlag
from rich.table import Table
from .console import console

class RegMapTable :

    def __init__(self, title : str):
        self.table = Table(title=title)
        self.table.add_column("Addr",        justify="right", style="cyan", no_wrap=True)
        self.table.add_column("T",           justify="right", style="blue", no_wrap=True)
        self.table.add_column("Acc",         justify="left",  style="blue", no_wrap=True)
        self.table.add_column("Name",        justify="left",  style="cyan")
        self.table.add_column("Value",       justify="right", style=Ass.none.color)
        self.table.add_column("Description", justify="left",  style="blue")

    def add_flag(self, f : RFlag):
        self.table.add_row('-', 'b',  f'{f.bit}',  f.name, f._value_rich_str(), f.desc)

    def add_reg(self, reg : Reg, expand_flags : bool = False):
        self.table.add_row(str(reg.addr), reg.value_type_str(),  str(reg.acc),  reg.name, reg.read_rich_str_cached(), reg.desc)
        if expand_flags and isinstance(reg, RegFlags):
            for f in reg.flags:
                self.add_flag(f)

    def add_module(self, module):
        for reg in module.arr_reg_k:
            self.add_reg( reg, expand_flags=True)

        for reg in module.arr_reg_var:
            self.add_reg( reg, expand_flags=True)

    def print(self):
        console.print(self.table)

def print_table_flags(log_f : list[RFlag], title, prepend_regs = True):
    """ Print table of flags
    NOTE: expects flags to be in order
    """
    table = RegMapTable(title=title)
    reg_prev = None
    for f in log_f:
        reg = f.reg_flags
        if prepend_regs and reg is not reg_prev:
            table.add_reg( reg, expand_flags=False)
            reg_prev = reg
        table.add_flag( f)
    table.print()

