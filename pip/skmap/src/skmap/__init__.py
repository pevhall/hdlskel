from . import head
from . import regio
from . import module
from . import basic_types

Head   = head.Head
Regio  = regio.Regio
Module = module.Module

Acc  = basic_types.Acc
Ass  = basic_types.Ass
ValueKind = basic_types.ValueKind
ValueType = basic_types.ValueType
value_type_u8 = basic_types.value_type_u8
value_type_x32 = basic_types.value_type_x32

Reg     = module.Reg
RegK    = module.RegK
RegVec  = module.RegVec
RegVecK = module.RegVecK
RegFlags= module.RegFlags
RegFlagsK = module.RegFlagsK
RFlag   = module.RFlag
RFlagK  = module.RFlagK

make_Module = module.make_Module
register_Module = module.register_Module
