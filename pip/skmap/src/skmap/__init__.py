from . import regio
from . import head
from . import reg
from . import module
from . import basic_types

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

make_Module     = module.make_Module
register_Module = module.register_Module
