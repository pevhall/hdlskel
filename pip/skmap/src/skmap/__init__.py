from skmap import code_generator_all_hpp
from . import regio
from . import head
from . import reg
from . import module
from . import basic_types
from . import external_mem
from . import reg_map_table
from . import code_generator_py
from . import code_generator_vhdl
from . import code_generator_cpp
from . import code_generator_all_hpp
from . import code_generator_version_hpp
from . import recipe_functions

Head   = head.Head
Regio  = regio.Regio
Module = module.Module

Acc            = basic_types.Acc
Ass            = basic_types.Ass
ValueKind      = basic_types.ValueKind
ValueType      = basic_types.ValueType

Reg       = reg.Reg
RegK      = reg.RegK
RegVec    = reg.RegVec
RegVecK   = reg.RegVecK
RegFlags  = reg.RegFlags
RegFlagsK = reg.RegFlagsK
RFlag     = reg.RFlag
RFlagK    = reg.RFlagK
ValueCheck = reg.ValueCheck
ValueConvert = reg.ValueConvert
VType = basic_types.VType

ExternalMem = external_mem.ExternalMem

make_module     = module.make_module
register_Module = module.register_Module
print_table_reg_list = reg_map_table.print_table_reg_list

generate_py_module   = code_generator_py.generate_py_module
generate_vhdl_module = code_generator_vhdl.generate_vhdl_module
generate_cpp_module  = code_generator_cpp.generate_cpp_module
generate_all_hpp     = code_generator_all_hpp.generate_all_hpp
generate_version_hpp = code_generator_version_hpp.generate_version_hpp
