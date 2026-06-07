from enum import Enum, auto, IntEnum
from typing import Optional

SKMAP_VER_MAJOR = 0
SKMAP_VER_MINOR = 1
SKMAP_VER_PATCH = 0

SKMAP_VER_STR = f'v{SKMAP_VER_MAJOR}.{SKMAP_VER_MINOR}.{SKMAP_VER_PATCH}'
SKMAP_WORD_BYTES = 4
SKMAP_WORD_BITS =SKMAP_WORD_BYTES*8

SKMAP_ID_LEN = 8

class Acc(Enum):
    na = auto()
    k  = auto()
    ro = auto()
    rc = auto()
    rw = auto()
    wt = auto()

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

    def str(self) -> str:
        return self.name

    @property
    def color(self)->str:
        return {
            Ass.none:   "white",
            Ass.passed: "green",
            Ass.debug:  "turquoise4",
            Ass.info:   "cornflower_blue",
            Ass.warn:   "orange1",
            Ass.error:  "orange_red1",
            Ass.fatal:  "red3",
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

    def __repr__(self) -> str:
        s = f'{self.kind.char_str}{self.width}'
        if self.is_vec:
            s += f'[{self.vec_len}]'
        return s

value_type_u8  = ValueType(kind=ValueKind.uint, width=8)
value_type_x32 = ValueType(kind=ValueKind.bits, width=32)

