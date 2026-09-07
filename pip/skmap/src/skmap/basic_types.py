from enum import Enum, auto, IntEnum
from typing import Optional
from .basic import promote_to_sw_w

SKMAP_VER_MAJOR = 1
SKMAP_VER_MINOR = 1
SKMAP_VER_PATCH = 0

SKMAP_VER_STR = f'v{SKMAP_VER_MAJOR}.{SKMAP_VER_MINOR}.{SKMAP_VER_PATCH}'
SKMAP_WORD_BYTES = 4
SKMAP_WORD_BITS =SKMAP_WORD_BYTES*8

SKMAP_ID_LEN = 8

class Acc(Enum):
    na = 0
    k  = 1
    ro = 2
    rc = 3
    rw = 4
    wt = 5

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
            Acc.wt: True,
        }[self]

class Ass(IntEnum):
    none    = -1
    passed  = 0
    debug   = 1
    info    = 2
    warn    = 3
    error   = 4
    fatal = 5

    def __str__(self):
        if self.name == 'none':
            return '-'
        return self.name

    def to_str(self) -> str:
        return self.name

    @property
    def color(self) -> str:
        return {
            Ass.none:   "default",
            Ass.passed: "green",
            Ass.debug:  "turquoise4",
            Ass.info:   "cornflower_blue",
            Ass.warn:   "orange1",
            Ass.error:  "orange_red1", #"red3",
            Ass.fatal:  "red3", # "magenta3"
        }[self]
        # rich colors

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

    def str(self):
        return {
            ValueKind.bits: "bits",
            ValueKind.uint: "uint",
            ValueKind.sint: "sint",
            ValueKind.char: "char",
            ValueKind.flag: "flag",
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
    def is_bool(self) -> bool:
        return self.kind == ValueKind.flag and self.width == 1

    @property
    def elem_size(self) -> int:
        return promote_to_sw_w(self.width)>>3

    @property
    def total_size(self) -> int:
        s = self.elem_size
        if self.vec_len is not None:
            s *= self.vec_len 
        return s

    def __repr__(self) -> str:
        s = ''
        if self.is_vec:
            s += f'[{self.vec_len}]'
        s += f'{self.kind.char_str}{self.width}'
        return s

value_type_u8  = ValueType(kind=ValueKind.uint, width=8)
value_type_x32 = ValueType(kind=ValueKind.bits, width=32)

