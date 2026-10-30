import copy
import hashlib
import string
try:
    import tomllib
except ModuleNotFoundError:
    import toml as tomllib #type: ignore
import argparse
from pathlib import Path
from enum import Enum, auto
from typing import Union, Optional
from dataclasses import dataclass

from .basic import ceil_div, ceil_log2 #promote_to_sw_w, ceil_multiple
from .basic_types import Acc, Ass, ValueKind, ValueType, SKMAP_ID_LEN, SKMAP_VER_MAJOR, SKMAP_VER_MINOR
from .head import SIZE_CHECKSUM
from .code_generator_parse_resolvable import (
    ResolvableT, make_resolvable_function, BultiInOperation, parse_resolvable, NameToKT,
    VType, value_kind_to_v_type, parse_resolvable_v_check,
    parse_resolvable_v_convert_wr, parse_resolvable_v_convert_rd,
    resolvable_to_int, resolvable_print_source,
)

dict_char_to_value_kind = {}
for vk in ValueKind:
    dict_char_to_value_kind[vk.char_str] = vk

def char_to_ValueKind(char : str) -> ValueKind:
    return dict_char_to_value_kind[char]

class FwInitMode(Enum):
    zero = auto()
    k = auto()
    k_int = auto()

    @property
    def not_zero(self) -> bool:
        return {
            FwInitMode.zero:      False,
            FwInitMode.k:         True,
            FwInitMode.k_int:     True,
        }[self]

    @property
    def is_k_int(self) -> bool:
        return {
            FwInitMode.zero:      False,
            FwInitMode.k:         False,
            FwInitMode.k_int:     True,
        }[self]

class RecipeIpkg:
    def __init__(self, d : dict, name_to_k : NameToKT):
        self.name : str = d['name']
        self.value = d['value']

        self.desc : Optional[str] = None
        if 'desc' in d:
            self.desc = d['desc']

        if 't' in d:
            self.t = parse_value_type_resolvable(d['t'], name_to_k)
        else:
            if isinstance(self.value, int):
                self.t = ValueType(kind=ValueKind.sint, width=32)
            elif isinstance(self.value, str):
                if self.value[0] == '{' and self.value[-1] == '}':
                    self.t = ValueType(kind=ValueKind.sint, width=32)
                    self.value = parse_unresolved_word(self.value, name_to_k=name_to_k)
                else:
                    self.t = ValueType(kind=ValueKind.char, width=8, vec_len=len(self.value))
            else:
                assert False, "Could not determine ipkg value type"


    def __repr__(self) -> str:
        return f'{self.name}'

class RecipeK:
    def __init__(self, d : dict, name_to_k : NameToKT):
        self.name : str = d['name']
        self.t = parse_value_type_resolvable(d['t'], name_to_k)
        self.acc = Acc.k
        self.desc : str = d['desc']
        flags, flags_width  = parse_recipe_flags(d, name_to_k=name_to_k)
        self.flags : Optional[list[RecipeFlag]] = flags
        # `v_check` is the value limit of the register (it replaces the old
        # `min` / `max` options), `v_convert_wr` / `v_convert_rd` map the user
        # value to the value stored in the register, see parse_recipe_v_options
        (self.v_type, self.v_check, self.v_check_str,
         self.v_convert_wr, self.v_convert_wr_str,
         self.v_convert_rd, self.v_convert_rd_str) = parse_recipe_v_options(d, name_to_k, self.t.kind, self.flags is not None)
        assert self.v_convert_wr is None and self.v_convert_rd is None, \
            f'v_convert_wr / v_convert_rd is not supported on constant registers ({self.name}), they convert values written to the module'
        if self.t.width is not None:
            if self.flags is not None:
                if isinstance(flags_width, int) and isinstance(self.t.width, int):
                    assert flags_width <= self.t.width
        else:
            assert self.flags is not None
            assert isinstance(self.t, ValueTypeUnresolved)
            self.t.width = flags_width

    @property
    def vec_len(self):
        return self.t.vec_len

    def __repr__(self) -> str:
        return f'{self.name}'

    @property
    def is_int(self):
        return self.t.kind.is_int

class ValueTypeUnresolved:
    def __init__(self, kind : ValueKind, width : ResolvableT, vec_len : Union[None, int, RecipeK]):
        self.kind    = kind
        self.width   = width
        self.vec_len = vec_len

    @property
    def elem_w(self) -> ResolvableT:
        return self.width

    @property
    def is_vec(self) -> bool:
        return self.vec_len is not None

    @property
    def is_bool(self) -> bool:
        return False

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

ValueTypeT = Union[ValueType, ValueTypeUnresolved]
def make_value_type_resolvable(*args, **kwargs) -> ValueTypeT:
    value_type = ValueTypeUnresolved(*args, **kwargs)
    if value_type.castable_to_ValueType():
        return value_type.to_ValueType()
    return value_type

def checksum_hash_of(val) -> str:
    """Text of a recipe field for the module checksum.

    A recipe value can be written as a number or as an expression of other
    recipe constants (`bit = "{RO_LEN}"`), it is resolved here so two recipes
    that mean the same have the same checksum. Everything that can not be
    evaluated (the text of a `v_check`, an expression with a value parameter)
    is printed, with the recipe names resolved to their values.
    """
    if val is None:
        return 'none'
    if isinstance(val, bool):
        return str(int(val))
    if isinstance(val, int):
        return str(val)
    if isinstance(val, str):
        return val
    if isinstance(val, Enum):
        return str(val)
    try:
        return str(resolvable_to_int(val))
    except Exception:
        pass
    # a width or a bit can be a constant of the recipe (a value the module
    # reports at run time), it is hashed as the text with the recipe names
    # resolved, that is the name of the constant
    try:
        return str(resolvable_print_source(val))
    except Exception:
        return str(val)

def md5_update(m, val):
    if isinstance(val, int):
        b = ceil_log2(ceil_div(val+1,8)+1)
        m.update(val.to_bytes(b))
    else:
        m.update(str(val).encode())

def parse_unresolved(s : Union[str, int], ii : int, name_to_k : NameToKT, strip_space=True) -> tuple[ResolvableT, int]:
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
        token = parse_resolvable(token , name_to_k);
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

def parse_unresolved_word(s : Union[str,int], name_to_k : NameToKT) -> ResolvableT:
    word, _ = parse_unresolved(s, ii=0, name_to_k=name_to_k)
    return word

def parse_value_type_resolvable(s : str, name_to_k : NameToKT) -> Union[ValueType, ValueTypeUnresolved]:
    ii = 0
    vec_len = None

    if s[ii] == '[':
        ii += 1
        vec_len, ii = parse_unresolved(s, ii, name_to_k=name_to_k, strip_space=True)
        assert s[ii] == ']', "expected vector end"
        ii += 1
    else:
        vec_len = None

    value_kind_char = s[ii:ii+1]
    value_kind = char_to_ValueKind(value_kind_char)
    ii += 1
    if ii == len(s):
        width = None
    else:
        width, ii = parse_unresolved(s, ii, name_to_k=name_to_k)
    assert ii == len(s)
    return make_value_type_resolvable(kind=value_kind, width=width, vec_len=vec_len)

class RecipeFlag:
    def __init__(self, d, bit_default : ResolvableT, name_to_k : NameToKT):
        self.name    : str = d['name']
        if 'ass' in d:
            self.ass = Ass[d['ass']]
        else:
            self.ass = Ass.none
        self.desc : str = d['desc']
        self.bit : ResolvableT

        if 'bit' in d:
            self.bit = parse_resolvable(d['bit'], name_to_k=name_to_k)
        else:
            self.bit = bit_default
        self.vec_len = None
        if 'vec_len' in d:
            self.vec_len = parse_unresolved_word(d['vec_len'], name_to_k=name_to_k)
        # print(f'{self.name=} {self.vec_len=}')
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
                self.width_resolvable = make_resolvable_function(self.vec_len, BultiInOperation.mult, flags_width)

    @property
    def is_vec(self) -> bool:
        return self.vec_len is not None

    # def width_resolvable(self) -> Union[int, RecipeK, ResolvableFunction]:
    #     if self.vec_len is None:
    #         if self.flags is None:
    #             return 1
    #         else:
    #             return self.flags.width_resolvable()


def parse_recipe_flags(d : dict, name_to_k : NameToKT) -> tuple[Optional[list[RecipeFlag]], ResolvableT]:
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
                bit_default = make_resolvable_function(bit_default, BultiInOperation.add, f.width_resolvable)
        width = bit_default
    return flags, width

def parse_recipe_v_options(d : dict, name_to_k : NameToKT, value_kind, is_flag : bool) -> tuple[VType, Optional[ResolvableT], Optional[str], Optional[ResolvableT], Optional[str], Optional[ResolvableT], Optional[str]]:
    """Parse the optional `v_type`, `v_check`, `v_convert_wr` and
    `v_convert_rd` recipe options.

    Returns (v_type, v_check, v_check_str, v_convert_wr, v_convert_wr_str,
    v_convert_rd, v_convert_rd_str):

      * `v_type`        type of the value parameter `v`, 'u', 's' or 'f'
                        (float, a float_t in c++), defaults to the type of the
                        register
      * `v_check`       boolean expression of `v`, the value limits, replacing
                        the old `min` / `max` options, eg v_check="{ v <= 100 }".
                        A value that fails it is an assert on a read and is
                        rejected on a write.
      * `v_convert_wr`  int expression of `v` converting a user value into the
                        raw register value (write side), eg
                        v_convert_wr="{ v * 8 }". The read side is its inverse,
                        derived here and returned as `v_convert_rd`.
      * `v_convert_rd`  the inverse form, it converts the raw register value
                        into the user value (read side), eg
                        v_convert_rd="{ v / 8 }". The write side is derived as
                        its inverse and returned as `v_convert_wr`.

    `v_convert_wr` and `v_convert_rd` are inverses of each other, a register
    can have at most one of them, the other side is always derived (both
    directions are returned in both cases).

    All three expressions can use the constants of the recipe as parameters,
    the `ipkg` values and the `k` registers, next to the value `v`.

    The `_str` texts have the parameters resolved to numbers: the `ipkg`
    values resolve here, a `k` register has its value only at runtime (it is
    reported by the firmware) so it keeps its name in the text and the
    runtime resolves it when the expression is printed (see
    Reg.resolve_expr_names in the python and c++ libraries). The value
    parameter `v` is never simplified.
    """
    for opt in ('v_type', 'v_check', 'v_convert_wr', 'v_convert_rd'):
        assert not is_flag or opt not in d, \
            f'{opt} is not supported on flag registers ({d["name"]})'
    # min / max of the register value and the first version of the value check
    # are removed, an old recipe has to say so instead of being ignored
    for removed in ('min', 'max', 'check'):
        assert removed not in d, \
            (f'{removed} is not a recipe option anymore ({d["name"]}), '
             f'write the same limit as a v_check of the value v, '
             f'eg. min = 2, max = 100 becomes v_check="{{ (v >= 2) && (v <= 100) }}"')
    assert 'v_convert' not in d, \
        (f'v_convert is not a recipe option anymore ({d["name"]}), it is split into '
         f'its two sides: v_convert_wr (value_convert_write_side) converts the user '
         f'value into the register value, v_convert_rd (value_convert_read_side) is '
         f'its inverse and converts the register value into the user value')
    assert not ('v_convert_wr' in d and 'v_convert_rd' in d), \
        (f'{d["name"]}: v_convert_wr and v_convert_rd are inverses of each other, '
         f'give at most one of them and the other side is derived')
    v_type = VType.from_str(d['v_type']) if 'v_type' in d else value_kind_to_v_type(value_kind)
    if 'v_check' in d:
        v_check, v_check_str = parse_resolvable_v_check(d['v_check'], name_to_k, v_type)
    else:
        v_check, v_check_str = None, None
    if 'v_convert_wr' in d or 'v_convert_rd' in d:
        given = 'v_convert_wr' if 'v_convert_wr' in d else 'v_convert_rd'
        assert v_check is not None or v_type.is_float, \
            f'{given} of {d["name"]} needs a v_check or a float v_type'
        if 'v_convert_wr' in d:
            v_convert_wr, v_convert_wr_str, v_convert_rd, v_convert_rd_str = \
                parse_resolvable_v_convert_wr(d['v_convert_wr'], name_to_k, v_type)
        else:
            v_convert_wr, v_convert_wr_str, v_convert_rd, v_convert_rd_str = \
                parse_resolvable_v_convert_rd(d['v_convert_rd'], name_to_k, v_type)
    else:
        assert v_type.is_float is False, \
            f'{d["name"]}: a float register (v_type="f") needs a v_convert_wr or a v_convert_rd to map it to the register value'
        v_convert_wr = v_convert_wr_str = v_convert_rd = v_convert_rd_str = None
    return v_type, v_check, v_check_str, v_convert_wr, v_convert_wr_str, v_convert_rd, v_convert_rd_str

class RecipeVar:

    def __init__(self, d : dict, name_to_k : NameToKT):
        self.name : str = d['name']
        self.t  = parse_value_type_resolvable(d['t'], name_to_k)
        self.acc = Acc[d['acc']]
        self.desc : str = d['desc']
        self.ass = Ass.none
        if 'ass' in d:
            self.ass = Ass[d['ass']]
        self.fw_init = FwInitMode.zero
        if 'fw_init' in d:
            self.fw_init = FwInitMode[d['fw_init']]
        flags, flags_width  = parse_recipe_flags(d, name_to_k=name_to_k)
        self.flags : Optional[list[RecipeFlag]] = flags
        # `v_check` is the value limit of the register (it replaces the old
        # `min` / `max` options), `v_convert_wr` / `v_convert_rd` map the user
        # value to the value stored in the register, see parse_recipe_v_options
        (self.v_type, self.v_check, self.v_check_str,
         self.v_convert_wr, self.v_convert_wr_str,
         self.v_convert_rd, self.v_convert_rd_str) = parse_recipe_v_options(d, name_to_k, self.t.kind, self.flags is not None)

        if self.t.width is not None:
            if self.flags is not None:
                if isinstance(flags_width, int) and isinstance(self.t.width, int):
                    assert flags_width <= self.t.width
        else:
            assert self.flags is not None
            assert isinstance(self.t, ValueTypeUnresolved)
            self.t.width = flags_width

    @property
    def vec_len(self):
        return self.t.vec_len

class RecipeMem:
    def __init__(self, d : dict, name_to_k : NameToKT):
        self.name : str = d['name']
        self.t  = parse_value_type_resolvable(d['t'], name_to_k)
        self.acc = Acc[d['acc']]
        self.desc : str = d['desc']
        self.fw_depth = parse_unresolved_word(d['fw_depth'], name_to_k=name_to_k)
        self.fw_width = parse_unresolved_word(d['fw_width'], name_to_k=name_to_k)
        self.fw_latency = parse_unresolved_word(d['fw_latency'], name_to_k=name_to_k)

RecipeReg = Union[RecipeK, RecipeVar]


@dataclass
class FwOpts:
    ports_use_basic_types : bool = False
    hdlskel_vhdl_lib : str = 'hdlskel'
    size_reserved : str = 'SKMAP_SIZE_RESERVED_DEFAULT'
    size_reserved_base_regs : str = 'SKMAP_SIZE_RESERVED_DEFAULT'

class Recipe:
    def __init__(self, d : dict):
        self.name      : str = d['name']
        self.sw_module : str = d['sw_module']
        self.fw_module : str = d['fw_module']
        self.id        : str = d['id']
        assert len(self.id) <= SKMAP_ID_LEN
        self.version   : int = d['version']
        self.ipkg : list[RecipeIpkg] = []
        self.k    : list[RecipeK]    = []
        self.var  : list[RecipeVar]  = []
        self.name_to_k : NameToKT = {}
        # every name of the recipe (ipkg, k, var and mem), they have to be
        # unique, see _check_unique_name
        self._names : set[str] = set()

        # if 'with_external_mem' in d:
        #     self.with_external_mem = d['with_external_mem']
        # else:
        #     self.with_external_mem = False
        #
        # if 'with_vec_external_mem' in d:
        #     self.with_vec_external_mem = d['with_vec_external_mem']
        # else:
        #     self.with_vec_external_mem = False


        self.fw_opts = FwOpts()

        if 'fw_opts' in d:
            d_fw_opts = d['fw_opts']
            if 'ports_use_basic_types' in d_fw_opts:
                self.fw_opts.ports_use_basic_types = d_fw_opts['ports_use_basic_types']
            if 'hdlskel_vhdl_lib' in d_fw_opts:
                self.fw_opts.hdlskel_vhdl_lib = d_fw_opts['hdlskel_vhdl_lib']
            if 'size_reserved_base_regs' in d_fw_opts:
                self.fw_opts.size_reserved_base_regs = d_fw_opts['size_reserved_base_regs']
            if 'size_reserved' in d_fw_opts:
                self.fw_opts.size_reserved = d_fw_opts['size_reserved']
            else:
                self.fw_opts.size_reserved = self.fw_opts.size_reserved_base_regs


        if 'ipkg' in d:
            for dnv in d['ipkg']:
                ipkgv = RecipeIpkg(dnv, self.name_to_k)
                self._check_unique_name(ipkgv.name, 'ipkg')
                self.ipkg.append(ipkgv)
                self.name_to_k[ipkgv.name] = ipkgv

        for dkv in d['k']:
            kv = RecipeK(dkv, self.name_to_k)
            self._check_unique_name(kv.name, 'k')
            self.k.append(kv)
            self.name_to_k[kv.name] = kv

        for dvv in d['var']:
            varv = RecipeVar(dvv, self.name_to_k)
            self._check_unique_name(varv.name, 'var')
            self.var.append(varv)

        self.mem = []
        if 'mem' in d:
            for memv in d['mem']:
                memv_parsed = RecipeMem(memv, self.name_to_k)
                self._check_unique_name(memv_parsed.name, 'mem')
                self.mem.append(memv_parsed)

        self._checksum = self._caculate_checksum()

    def _check_unique_name(self, name : str, kind : str):
        """Every name of the recipe (ipkg, k, var and mem) has to be unique, a
        duplicate is an error and not a silent overwrite."""
        if name in self._names:
            raise ValueError(f'recipe has a duplicate name {name!r} (in {kind}), '
                             f'the ipkg, k, var and mem names have to be unique')
        self._names.add(name)

    def _checksum_update_reg(self, m, r):
        """Update the checksum with one register (a `k` or a `var` entry)."""
        md5_update(m, r.name)
        md5_update(m, r.acc)
        md5_update(m, r.t.kind)
        md5_update(m, checksum_hash_of(r.t.width))
        # The vector length is part of the layout of the module (how many
        # elements a register has), the assert level, the value type (v_type),
        # the value check (v_check) and the value conversions (v_convert_wr /
        # v_convert_rd) are baked into the generated code of the firmware and
        # the software, so a module and the code that parses it have to agree
        # on all of them.
        md5_update(m, checksum_hash_of(r.t.vec_len))
        md5_update(m, checksum_hash_of(getattr(r, 'ass', Ass.none)))
        md5_update(m, checksum_hash_of(r.v_type))
        md5_update(m, checksum_hash_of(r.v_check_str))
        # v_convert_wr and v_convert_rd are inverses of each other, one of
        # them is always derived from the other, hashing one of the two sides
        # hashes the conversion pair (a recipe that gives the read side gets
        # the same checksum as the one that writes the same conversion as the
        # write side)
        md5_update(m, checksum_hash_of(r.v_convert_wr_str))
        # the flags of a flag register (a flag is only visible through its
        # register, its bit, length and assert belong to the module)
        if r.flags is None:
            md5_update(m, checksum_hash_of(None))
        else:
            md5_update(m, checksum_hash_of(len(r.flags)))
            for f in r.flags:
                md5_update(m, checksum_hash_of(f.name))
                md5_update(m, checksum_hash_of(f.bit))
                md5_update(m, checksum_hash_of(f.vec_len))
                md5_update(m, checksum_hash_of(f.ass))

    def _caculate_checksum(self):
        """Checksum of the recipe, embedded in the generated py / cpp / vhdl
        and in the module head, so a module image and the code that parses it
        can be checked against each other (ModuleFactory.make_module refuses a
        checksum mismatch).

        Hashed: the skmap version, the module id and version, the names of the
        ipkg / `k` constants (and the type of their value), and for every
        register the name, the access type, the value kind, width and vector
        length, the assert level, the value options (`v_type`, `v_check`,
        `v_convert_wr` / `v_convert_rd`) and the flags.

        Not hashed: the *value* of the ipkg / `k` constants (a constant value
        is a parameter of the design, changing it usually changes the layout
        through the widths that use it, and every name that is used is hashed),
        the descriptions and the `fw_init` mode.

        Extending this list is a breaking change: the checksum is checked
        against the images the firmware produces and against cached regio
        files, so every generated file and every cached image has to be
        regenerated together (see `test/data/*.skmap`).
        """
        m = hashlib.md5()
        m.update(SKMAP_VER_MAJOR.to_bytes(1))
        # m.update(SKMAP_VER_MINOR.to_bytes(1))
        m.update(self.id.encode())
        m.update(self.version.to_bytes(1))
        for r in self.ipkg:
            md5_update(m, r.name)
            md5_update(m, type(r.value))
        for r in self.k:
            self._checksum_update_reg(m, r)
        for r in self.var:
            self._checksum_update_reg(m, r)

        checksum = int.from_bytes(m.digest())
        return checksum & 0xFFFF

    def checksum_str(self) -> str:
        return f'{self._checksum:0{SIZE_CHECKSUM}X}'

    def checksum(self) -> int:
        return self._checksum

def parse_recipe_file(file : Path) -> Recipe:
    with open(file, "rb") as toml_f:
        recipe_dict = tomllib.load(toml_f) #type:ignore
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

