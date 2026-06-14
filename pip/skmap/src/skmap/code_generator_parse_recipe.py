#!/usr/bin/env python3

# import sys
import copy
import hashlib
import string
import tomllib
import argparse
from pathlib import Path
from enum import Enum, auto
from typing import Union, Optional

from basic import ceil_div, ceil_log2 #promote_to_sw_w, ceil_multiple
from basic_types import Acc, Ass, ValueKind, ValueType, SKMAP_ID_LEN
from head import SIZE_CHECKSUM

dict_char_to_value_kind = {}
for vk in ValueKind:
    dict_char_to_value_kind[vk.char_str] = vk

def char_to_ValueKind(char : str) -> ValueKind:
    return dict_char_to_value_kind[char]

class RecipeK:
    def __init__(self, d : dict, name_to_k : dict[str, 'RecipeK']):
        self.name : str = d['name']
        self.t = parse_value_type_resolvable(d['t'])
        self.acc = Acc.k
        self.desc : str = d['desc']
        self.name_resolvable = self.name
        flags, flags_width  = parse_recipe_flags(d, name_to_k=name_to_k)
        self.flags : Optional[list[RecipeFlag]] = flags
        if self.t.width is not None:
            if self.flags is not None:
                if isinstance(flags_width, int) and isinstance(self.t.width, int):
                    assert flags_width <= self.t.width
        else:
            assert self.flags is not None
            assert isinstance(self.t, ValueTypeUnresolved)
            self.t.width = flags_width

    # def set_addr_offset_size(self, addr_offset : Union['ResolvableFunction', 'RecipeK', int], size : Union['ResolvableFunction', 'RecipeK', int]):
    #     self.addr_offset = addr_offset
    #     self.size = size

    def __repr__(self) -> str:
        return f'{self.name_resolvable}'

    @property
    def is_int(self):
        return self.t.kind.is_int

class ResolvableOp(Enum):
    add  = auto()
    mult = auto()

    def __str__(self) -> str:
        return {
            ResolvableOp.add : "+",
            ResolvableOp.mult: "*",
        }[self]

class ResolvableFunction():
    def __init__(self, lhs : Union['ResolvableFunction', RecipeK, int], op : ResolvableOp, rhs : Union['ResolvableFunction', RecipeK, int]):
        if isinstance(lhs, RecipeK):
            assert lhs.is_int
        if isinstance(rhs, RecipeK):
            assert rhs.is_int
        self.lhs = lhs
        self.op  = op
        self.rhs = rhs

    def __repr__(self) -> str:
        return f'({self.lhs} {self.op} {self.rhs})' #type: ignore

def make_resolvable_function(lhs : Union[ResolvableFunction, RecipeK, int], op : ResolvableOp, rhs : Union[ResolvableFunction, RecipeK, int]) -> Union[ResolvableFunction, int]:
    if isinstance(rhs, int):
        if isinstance(lhs, int):
            match op:
                case ResolvableOp.add : return lhs + rhs
                case ResolvableOp.mult: return lhs * rhs
        elif isinstance(lhs, ResolvableFunction):
            if isinstance(lhs.rhs, int) and op == ResolvableOp.add and lhs.op == ResolvableOp.add:
                lhs = copy.copy(lhs)
                assert isinstance(lhs.rhs, int)
                lhs.rhs += rhs
                return lhs
    return ResolvableFunction(lhs, op, rhs)

class ValueTypeUnresolved:
    def __init__(self, kind : ValueKind, width : Union[None, int, RecipeK, ResolvableFunction], vec_len : Union[None, int, RecipeK]):
        self.kind    = kind
        self.width   = width
        self.vec_len = vec_len

    @property
    def is_vec(self) -> bool:
        return self.vec_len is not None

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

    def castable_to_ValueType(self) -> bool:
        return isinstance(self.width, int) and self.vec_len is None or isinstance(self.vec_len, int)

    def to_ValueType(self) -> ValueType:
        assert isinstance(self.width, int)
        assert self.vec_len is None or isinstance(self.vec_len, int)
        return ValueType(kind=self.kind, width=self.width, vec_len=self.vec_len)

def make_value_type_resolvable(*args, **kwargs) -> Union[ValueType, ValueTypeUnresolved]:
    value_type = ValueTypeUnresolved(*args, **kwargs)
    if value_type.castable_to_ValueType():
        return value_type.to_ValueType()
    return value_type

def md5_update(m, val):
    if isinstance(val, int):
        b = ceil_log2(ceil_div(val+1,8)+1)
        m.update(val.to_bytes(b))
    else:
        m.update(str(val).encode())

def parse_unresolved(s : Union[str, int], ii : int, name_to_k : Optional[dict[str, RecipeK]] = None, strip_space=True) -> tuple[Union[int, RecipeK], int]:
    if isinstance(s, int):
        return s, ii
    if strip_space:
        while s[ii] == ' ':
            ii += 1
    if s[ii] == '{':
        assert name_to_k is not None
        ii += 1
        ii_start = ii
        while s[ii] != '}':
            assert s[ii] != '{'
            ii += 1
        token = s[ii_start:ii].strip()
        token = name_to_k[token]
        ii += 1
    else:
        ii_start = ii
        word_chars = string.ascii_letters + string.digits + "_"
        while ii < len(s) and s[ii] in word_chars:
            ii += 1
        token = s[ii_start:ii]
        token = int(token)
    if strip_space:
        while ii < len(s) and s[ii] == ' ':
            ii += 1
    return token, ii

def parse_unresolved_word(s : Union[str,int], name_to_k : Optional[dict[str, RecipeK]]) -> Union[RecipeK, int]:
    word, _ = parse_unresolved(s, ii=0, name_to_k=name_to_k)
    return word

def parse_value_type_resolvable(s : str, name_to_k : Optional[dict]=None) -> Union[ValueType, ValueTypeUnresolved]:
    value_kind_char = s[:1]
    value_kind = char_to_ValueKind(value_kind_char)
    ii = 1
    if ii == len(s):
        width = None
        vec_len = None
    else:
        width, ii = parse_unresolved(s, ii, name_to_k=name_to_k)
        if ii == len(s):
            vec_len = None
        else:
            assert s[ii] == '['
            ii+=1
            vec_len, ii = parse_unresolved(s, ii, name_to_k=name_to_k, strip_space=True)
            assert s[ii] == ']'
            ii += 1
            assert ii == len(s)
    return make_value_type_resolvable(kind=value_kind, width=width, vec_len=vec_len)

class RecipeFlag:
    def __init__(self, d, bit_default : Union[int, RecipeK, ResolvableFunction], name_to_k : dict[str, RecipeK]):
        self.name    : str = d['name']
        if 'ass' in d:
            self.ass = Ass[d['ass']]
        else:
            self.ass = Ass.none
        self.desc : str = d['desc']
        self.bit : Union[int, RecipeK, ResolvableFunction]

        if 'bit' in d:
            self.bit = parse_unresolved_word(d['bit'], name_to_k=name_to_k)
        else:
            self.bit = bit_default
        self.vec_len = None
        if 'vec_len' in d:
            self.vec_len = parse_unresolved_word(d['vec_len'], name_to_k=name_to_k)
        flags, flags_width  = parse_recipe_flags(d, name_to_k=name_to_k)
        self.flags = flags
        if flags is None:
            if self.vec_len is None:
                self.width_resolvable = 1
            else:
                self.width_resolvable = self.vec_len
        else:
            if self.vec_len is None:
                self.width_resolvable = flags_width
            else:
                self.width_resolvable = make_resolvable_function(self.vec_len, ResolvableOp.mult, flags_width)

    @property
    def is_vec(self) -> bool:
        return self.vec_len is not None

    # def width_resolvable(self) -> Union[int, RecipeK, ResolvableFunction]:
    #     if self.vec_len is None:
    #         if self.flags is None:
    #             return 1
    #         else:
    #             return self.flags.width_resolvable()


def parse_recipe_flags(d : dict, name_to_k : dict[str, RecipeK]) -> tuple[Optional[list[RecipeFlag]], Union[ResolvableFunction, RecipeK, int]]:
    flags = None
    width = 0
    if 'flags' in d:
        flags = []
        bit_default = 0
        for df in d['flags']:
            f = RecipeFlag(df, bit_default, name_to_k=name_to_k)
            flags.append(f)
            bit_default = f.bit
            if bit_default == 0:
                bit_default = f.width_resolvable
            else:
                bit_default = make_resolvable_function(bit_default, ResolvableOp.add, f.width_resolvable)
        width = bit_default
    return flags, width

class RecipeVar:
    def __init__(self, d : dict, name_to_k : dict[str, RecipeK]):
        self.name : str = d['name']
        self.t  = parse_value_type_resolvable(d['t'], name_to_k)
        self.acc = Acc[d['acc']]
        self.desc : str = d['desc']
        flags, flags_width  = parse_recipe_flags(d, name_to_k=name_to_k)
        self.flags : Optional[list[RecipeFlag]] = flags
        if self.t.width is not None:
            if self.flags is not None:
                if isinstance(flags_width, int) and isinstance(self.t.width, int):
                    assert flags_width <= self.t.width
        else:
            assert self.flags is not None
            assert isinstance(self.t, ValueTypeUnresolved)
            self.t.width = flags_width

RecipeReg = Union[RecipeK, RecipeVar]

class Recipe:
    def __init__(self, d : dict):
        self.name      : str = d['name']
        self.sw_module : str = d['sw_module']
        self.id        : str = d['id']
        assert len(self.id) <= SKMAP_ID_LEN
        self.version   : int = d['version']
        self.k = []
        self.name_to_k : dict[str, RecipeK]= {}

        for dkv in d['k']:
            kv = RecipeK(dkv, self.name_to_k)
            self.k.append(kv)
            self.name_to_k[kv.name] = kv

        self.var = []
        for dvv in d['var']:
            self.var.append(RecipeVar(dvv, self.name_to_k))
        self.checksum = self._checksum()

    def _checksum(self):
        m = hashlib.md5()
        m.update(self.id.encode())
        m.update(self.version.to_bytes(1))
        for vk in self.k:
            md5_update(m, vk.t.width)
        for vv in self.var:
            md5_update(m, vv.t.width)
        checksum = int.from_bytes(m.digest())
        return checksum & 0xFFFF

    def checksum_str(self) -> str:
        return f'{self.checksum:0{SIZE_CHECKSUM}X}'

def parse_recipe_file(file : Path) -> Recipe:
    with open(file, "rb") as toml_f:
        recipe_dict = tomllib.load(toml_f)
        # from pprint import pprint
        # pprint(recipe)
    return Recipe(recipe_dict)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Parse a skmap module recipe file and generate skmap module"
    )
    parser.add_argument(
        "file",
        type=Path,
        help="Path to skmap recipe file"
    )
    return parser.parse_args()

if __name__ == '__main__':

    args = parse_args()
    parse_recipe_file(args.file)

