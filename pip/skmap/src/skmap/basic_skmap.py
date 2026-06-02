from enum import Enum, auto, IntEnum
from typing import Optional

from basic import promote_to_sw_w, ceil_multiple

SKMAP_VER_MAJOR = 0
SKMAP_VER_MINOR = 1
SKMAP_VER_PATCH = 0

SKMAP_VER_STR = f'v{SKMAP_VER_MAJOR}.{SKMAP_VER_MINOR}.{SKMAP_VER_PATCH}'
SKMAP_WORD_BYTES = 4
SKMAP_WORD_BITS =SKMAP_WORD_BYTES*8

SKMAP_ID_LEN = 8

def align_addr_width(addr : int, width : int):
    sw_width = promote_to_sw_w(width)
    sw_width_bytes = sw_width//8
    align = min(SKMAP_WORD_BYTES, sw_width//8)
    addr = ceil_multiple(addr, align)
    return addr, sw_width_bytes


class Acc(Enum):
    na = auto()
    k  = auto()
    ro = auto()
    rc = auto()
    rw = auto()
    ws = auto()

    def __str__(self):
        return self.name

    @property
    def sw_writable(self) -> Optional[bool]:
        return {
            Acc.na: None,
            Acc.k:  False,
            Acc.ro: False,
            Acc.rc: False,
            Acc.rw: True,
            Acc.ws: True,
        }[self]

class Ass(IntEnum):
    none    = -1
    passed  = 0
    debug   = 1
    info    = 2
    warn    = 3
    error   = 4
    failure = 5

    def __str__(self) -> str:
        if self.name == 'none':
            return '-'
        return self.name

    def str(self) -> str:
        return self.name

    @property
    def color(self) -> str:
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

    @property
    def is_int(self) -> bool:
        return self == ValueKind.uint or self == ValueKind.sint

class ValueType:
    def __init__(self, kind : ValueKind, width : int, vec_len : Optional[int]=None):
        assert(width >= 0)
        self.kind = kind
        self.width = width
        self.vec_len = vec_len

    @property
    def is_vec(self) -> bool:
        return self.vec_len is not None

    @property
    def sw_size(self):
        return promote_to_sw_w(self.width)//8

    @property
    def supports_int32(self) -> bool:
        if not isinstance(self.width, int):
            return False
        if not self.vec_len is None:
            return False
        if self.kind == ValueKind.sint:
            return self.width <= 32
        if self.kind == ValueKind.uint:
            return self.width <= 31
        return False

    def __repr__(self) -> str:
        s = f'{self.kind.char_str}{self.width}'
        if self.is_vec:
            s += f'[{self.vec_len}]'
        return s

value_type_u8  = ValueType(kind=ValueKind.uint, width=8)
value_type_x32 = ValueType(kind=ValueKind.bits, width=32)

