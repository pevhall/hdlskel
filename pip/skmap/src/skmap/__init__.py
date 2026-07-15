from . import regio
from . import head
from . import reg
from . import module
from . import basic_types
from . import reg_map_table
from . import code_generator_vhdl
from . import code_generator_py

Head   = head.Head
Regio  = regio.Regio
Module = module.Module

Acc            = basic_types.Acc
Ass            = basic_types.Ass
ValueKind      = basic_types.ValueKind
ValueType      = basic_types.ValueType
value_type_u8  = basic_types.value_type_u8
value_type_x32 = basic_types.value_type_x32

Reg       = reg.Reg
RegK      = reg.RegK
RegVec    = reg.RegVec
RegVecK   = reg.RegVecK
RegFlags  = reg.RegFlags
RegFlagsK = reg.RegFlagsK
RFlag     = reg.RFlag
RFlagK    = reg.RFlagK

make_module     = module.make_module
register_Module = module.register_Module
print_reg_map_table_flags = reg_map_table.print_table_flags

generate_py_module   = code_generator_py.generate_py_module
generate_vhdl_module = code_generator_vhdl.generate_vhdl_module
