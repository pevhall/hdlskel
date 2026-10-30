"""Tests for the recipe value options `v_type`, `v_check`, `v_convert_wr`
and `v_convert_rd`.

`v_check` is a boolean expression of the register value `v`, `v_convert_wr`
(value convert write side) converts a user value into the value stored in the
register and `v_convert_rd` (value convert read side) is its inverse, used by
every read. Each register gives at most one of the two conversion sides, the
other one is derived. They replaced the old `min` / `max` options.

Run with: python3 -m pytest pip/skmap/tests -q
"""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'pip' / 'skmap' / 'src'))

import skmap                                                     # noqa: E402
from skmap.basic_types import ValueKind, promote_to_sw_w         # noqa: E402
from skmap.reg import ValueCheck, ValueConvert                   # noqa: E402
from skmap.code_generator_parse_recipe import parse_recipe_file, parse_recipe_v_options   # noqa: E402
from skmap.code_generator_parse_resolvable import (               # noqa: E402
    parse_resolvable_v_check, parse_resolvable_v_convert_wr, parse_resolvable_v_convert_rd,
    resolvable_print_source, resolvable_to_int, NotInvertibleError,
)

RECIPE = ROOT / 'fw' / 'tb' / 'skmap' / 'tb_py_skmap_module_recipe' / 'recipe_test_bench_module.toml'

EVEN_U = ValueCheck(lambda v: (v % 2) == 0, '(v % 2) == 0')


class ModuleStub:
    """Enough of a skmap.Module for a standalone Reg."""

    def __init__(self):
        self._byte_align = 1
        self._cache = bytearray(1024)
        self.base_addr = 0
        # the constant (k) registers, Reg.resolve_expr_names prints with these
        self.arr_reg_k = []

    def _byte_aligment_from_val_width(self, width):
        return max(self._byte_align, promote_to_sw_w(width) // 8)

    def read_cached(self, addr : int, size : int) -> bytes:
        return bytes(self._cache[addr:addr+size])

    def write_bytes_cached(self, addr : int, data : bytes):
        self._cache[addr:addr+len(data)] = data

    async def read_bytes(self, addr : int, size : int) -> bytes:
        raise RuntimeError('this test only uses the cached functions')

    async def write_bytes(self, addr : int, data : bytes):
        raise RuntimeError('this test only uses the cached functions')


def plain(s : str) -> str:
    """The value string without the rich markup."""
    return re.sub(r'\[/?[a-z_0-9]+\]', '', s)


def make_reg(**kwargs) -> skmap.Reg:
    reg = skmap.Reg(ModuleStub(), name=kwargs.pop('name', 'test'),
                    value_type=skmap.ValueType(kind=skmap.ValueKind.sint, width=kwargs.pop('width', 8)),
                    acc=kwargs.pop('acc', skmap.Acc.rw), desc='test reg', **kwargs)
    reg.addr = 0
    return reg


def make_reg_vec(**kwargs) -> skmap.RegVec:
    reg = skmap.RegVec(ModuleStub(), name=kwargs.pop('name', 'test'),
                       value_type=skmap.ValueType(kind=skmap.ValueKind.sint, width=kwargs.pop('width', 12),
                                                  vec_len=kwargs.pop('vec_len', 3)),
                       acc=kwargs.pop('acc', skmap.Acc.rw), desc='test reg', **kwargs)
    reg.addr = 0
    return reg


# ---------- ValueCheck / ValueConvert ----------

def test_value_check_str_and_call():
    c = ValueCheck(lambda v: v > 0, '(v > 0)')
    assert str(c) == '(v > 0)'
    assert c(1)
    assert not c(0)
    assert c.v_type == skmap.VType.s

def test_value_convert_round_trip():
    # Q4 style scale: 1.5 -> 24 -> 1.5
    c = ValueConvert(lambda v: v * 16, lambda v: v / 16, '(v * 16)', '(v / 16)', skmap.VType.f)
    assert c.to_raw(1.5) == 24
    assert c.from_raw(24) == 1.5
    assert str(c) == '(v * 16)'
    assert c.str_inv == '(v / 16)'


# ---------- v_check ----------

def test_check_write_passes():
    reg = make_reg(v_check=EVEN_U)
    reg.write_sint_cached(4)
    assert reg.read_sint_cached() == 4

def test_check_write_rejected():
    reg = make_reg(v_check=EVEN_U)
    reg.write_sint_cached(4)
    with pytest.raises(ValueError, match='check'):
        reg.write_sint_cached(3)
    # the old value is still cached
    assert reg.read_sint_cached() == 4

def raw_write(reg, value : int):
    """Put a value in the register without going through the v_check."""
    reg.write_bytes_cached(value.to_bytes(reg.size, byteorder='little', signed=True))


def test_check_read_asserts():
    reg = make_reg(v_check=EVEN_U)
    raw_write(reg, 3)
    assert reg.ass_check_cached() == skmap.Ass.error
    assert plain(reg.read_rich_str_cached()) == '(v % 2) == 0 3'

def test_check_read_asserts_configured_ass():
    reg = make_reg(ass=skmap.Ass.warn, v_check=EVEN_U)
    raw_write(reg, 3)
    assert reg.ass_check_cached() == skmap.Ass.warn

def test_check_read_passes():
    reg = make_reg(v_check=EVEN_U)
    reg.write_sint_cached(2)
    assert reg.ass_check_cached() == skmap.Ass.none

def test_check_only_has_limit():
    reg = make_reg(v_check=EVEN_U)
    assert reg.has_limit()
    assert not make_reg().has_limit()

def test_check_value_string_prints_resolved_text():
    reg = make_reg(v_check=EVEN_U)
    raw_write(reg, 3)
    assert plain(reg.read_rich_str_cached()) == '(v % 2) == 0 3'

def test_raw_write_checks_the_user_value():
    # without a v_convert the register value is the user value
    reg = make_reg(v_check=EVEN_U)
    with pytest.raises(ValueError):
        reg.write_sint_cached(3)


# ---------- v_convert_wr / v_convert_rd ----------

def test_convert_write_read_round_trip():
    conv = ValueConvert(lambda v: v * 2, lambda v: v / 2, '(v * 2)', '(v / 2)', skmap.VType.f)
    reg = make_reg(width=16, v_convert=conv)
    reg.write_converted_cached(1.5)
    assert reg.read_sint_cached() == 3            # raw value in the register
    assert reg.read_converted_cached() == 1.5     # user value
    assert reg.read_sint_cached() == 3

def test_convert_read_after_raw_write():
    conv = ValueConvert(lambda v: v * 2, lambda v: v / 2, '(v * 2)', '(v / 2)', skmap.VType.f)
    reg = make_reg(width=16, v_convert=conv)
    reg.write_sint_cached(5)
    assert reg.read_converted_cached() == 2.5

def test_convert_integer_offset_round_trip():
    # an integer v_type converts with an offset, it stays an int
    conv = ValueConvert(lambda v: v + 3, lambda v: v - 3, '(v + 3)', '(v - 3)', skmap.VType.s)
    reg = make_reg(width=16, v_convert=conv)
    reg.write_converted_cached(4)
    assert reg.read_sint_cached() == 7
    assert reg.read_converted_cached() == 4
    assert isinstance(reg.read_converted_cached(), int)

def test_convert_write_is_checked_with_the_user_value():
    conv = ValueConvert(lambda v: v * 2, lambda v: v / 2, '(v * 2)', '(v / 2)', skmap.VType.f)
    # only even user values pass
    reg = make_reg(width=16, v_check=ValueCheck(lambda v: (v % 2) == 0, '(v % 2) == 0', skmap.VType.f),
                   v_convert=conv)
    reg.write_converted_cached(4.0)
    with pytest.raises(ValueError):
        reg.write_converted_cached(3.5)   # raw 7 would be written, the user value 3.5 fails

def test_convert_write_outside_register_range():
    conv = ValueConvert(lambda v: v * 2, lambda v: v / 2, '(v * 2)', '(v / 2)', skmap.VType.f)
    reg = make_reg(width=8, v_convert=conv)
    with pytest.raises(ValueError, match='does not fit'):
        reg.write_converted_cached(1000.0)    # raw 2000 does not fit into s8

def test_convert_value_string_shows_user_value():
    conv = ValueConvert(lambda v: v * 2, lambda v: v / 2, '(v * 2)', '(v / 2)', skmap.VType.f)
    reg = make_reg(width=16, v_check=ValueCheck(lambda v: v <= 10, '(v <= 10)', skmap.VType.f), v_convert=conv)
    reg.write_converted_cached(3.0)
    # the check text, then the user value, not the raw 6
    assert plain(reg.read_rich_str_cached()) == '(v <= 10) 3.0'

def test_convert_read_asserts_when_check_fails():
    conv = ValueConvert(lambda v: v * 2, lambda v: v / 2, '(v * 2)', '(v / 2)', skmap.VType.f)
    reg = make_reg(width=16, v_check=ValueCheck(lambda v: v <= 10, '(v <= 10)', skmap.VType.f), v_convert=conv)
    reg.write_bytes_cached((40).to_bytes(2, byteorder='little', signed=True))  # bypasses the check
    assert reg.read_converted_cached() == 20
    assert reg.ass_check_cached() == skmap.Ass.error


# ---------- vectors ----------

def test_vec_list_write_checks_every_element():
    reg = make_reg_vec(v_check=EVEN_U)
    reg.write_list_sint_cached([2, 4, 6])
    assert reg.read_list_sint_cached() == [2, 4, 6]
    with pytest.raises(ValueError):
        reg.write_list_sint_cached([2, 4, 5])

def test_vec_indexed_write_checks_element():
    reg = make_reg_vec(v_check=EVEN_U)
    reg.write_idx_sint_cached(0, 2)
    with pytest.raises(ValueError):
        reg.write_idx_sint_cached(1, 3)

def test_vec_read_asserts_per_element():
    reg = make_reg_vec(v_check=EVEN_U)
    reg.write_list_sint_cached([2, 4, 6])
    assert reg.ass_check_cached() == skmap.Ass.none
    reg.write_idx_bytes_cached(2, (7).to_bytes(reg.elem_size, byteorder='little', signed=True))
    assert reg.ass_check_cached() == skmap.Ass.error

def test_vec_value_string_shows_check():
    reg = make_reg_vec(v_check=EVEN_U)
    reg.write_list_sint_cached([2, 4, 6])
    assert plain(reg.read_rich_str_cached()) == '(v % 2) == 0 [ 2, 4, 6 ]'

def test_vec_convert_list_round_trip():
    conv = ValueConvert(lambda v: v * 2, lambda v: v / 2, '(v * 2)', '(v / 2)', skmap.VType.f)
    reg = make_reg_vec(width=16, v_convert=conv)
    reg.write_converted_cached([1.5, 2.0, -0.5])
    assert reg.read_list_sint_cached() == [3, 4, -1]
    assert reg.read_converted_cached() == [1.5, 2.0, -0.5]
    assert reg.read_converted_idx_cached(1) == 2.0
    assert plain(reg.read_rich_str_cached()) == '[ 1.5, 2.0, -0.5 ]'

def test_vec_convert_indexed_write():
    conv = ValueConvert(lambda v: v * 2, lambda v: v / 2, '(v * 2)', '(v / 2)', skmap.VType.f)
    reg = make_reg_vec(width=16, v_convert=conv)
    reg.write_converted_idx_cached(2, 1.5)
    assert reg.read_list_sint_cached() == [0, 0, 3]
    with pytest.raises(ValueError):
        reg.write_converted_idx_cached(2, 1e6)

def test_vec_raw_write_checks_user_value():
    conv = ValueConvert(lambda v: v * 2, lambda v: v / 2, '(v * 2)', '(v / 2)', skmap.VType.f)
    reg = make_reg_vec(width=16, v_check=ValueCheck(lambda v: v <= 10, '(v <= 10)', skmap.VType.f),
                       v_convert=conv)
    reg.write_list_sint_cached([2, 4, 20])     # user value of 20 is 10, still ok
    with pytest.raises(ValueError):
        reg.write_list_sint_cached([2, 4, 22]) # user value of 22 is 11, fails the check


# ---------- recipe parsing ----------

def test_recipe_parses_v_options():
    recipe = parse_recipe_file(RECIPE)
    by_k = {kv.name: kv for kv in recipe.k}
    by_name = {var.name: var for var in recipe.var}

    rw_len = by_k['RW_LEN']
    assert str(resolvable_print_source(rw_len.v_check)) == '((v % 2) == 0)'
    assert rw_len.v_check_str == '((v % 2) == 0)'
    assert rw_len.v_type == skmap.VType.u   # uint register -> u by default
    assert rw_len.v_convert_wr is None
    assert rw_len.v_convert_rd is None

    regs_rw = by_name['regs_rw']
    assert regs_rw.v_type == skmap.VType.s
    assert 'v <= 100' in str(resolvable_print_source(regs_rw.v_check))
    with pytest.raises(ValueError):
        resolvable_to_int(regs_rw.v_check)   # it depends on v, it is not a constant

def test_recipe_v_convert_is_invertible():
    recipe = parse_recipe_file(RECIPE)
    by_name = {var.name: var for var in recipe.var}
    temp = by_name['temp']
    assert temp.v_type == skmap.VType.f
    # temp converts with the k register RO_VAL_W (a float Q scale), the k keeps
    # its name in the printed text (it has its value only at runtime, see
    # test_k_parameters_are_resolved_when_printed), the read side is its inverse
    assert str(resolvable_print_source(temp.v_convert_wr)) == '(v * RO_VAL_W)'
    assert str(resolvable_print_source(temp.v_convert_rd)) == '(v / RO_VAL_W)'

def test_recipe_old_options_are_gone():
    recipe = parse_recipe_file(RECIPE)
    for var in recipe.var:
        assert not hasattr(var, 'max')
        assert not hasattr(var, 'min')

def test_v_check_must_be_boolean():
    with pytest.raises(AssertionError):
        parse_resolvable_v_check('{ v + 1 }', {})

def test_v_check_must_use_v():
    with pytest.raises((AssertionError, KeyError)):
        parse_resolvable_v_check('{ RW_LEN == 0 }', {})

def test_v_convert_must_use_v():
    with pytest.raises((AssertionError, KeyError)):
        parse_resolvable_v_convert_wr('{ RW_LEN * 2 }', {})

def test_v_convert_that_loses_values_is_rejected():
    # an integer v can not be recovered from a scaled one
    with pytest.raises(NotInvertibleError):
        parse_resolvable_v_convert_wr('{ v * 2 }', {}, v_type=skmap.VType.s)
    # the same conversion written from the read side
    with pytest.raises(NotInvertibleError):
        parse_resolvable_v_convert_rd('{ v / 2 }', {}, v_type=skmap.VType.s)

def test_v_convert_non_affine_is_rejected():
    with pytest.raises(NotInvertibleError):
        parse_resolvable_v_convert_wr('{ v * v }', {}, v_type=skmap.VType.f)
    with pytest.raises(NotInvertibleError):
        parse_resolvable_v_convert_rd('{ v * v }', {}, v_type=skmap.VType.f)

# ---------- v_convert_wr and v_convert_rd are inverses ----------

def test_v_convert_rd_is_the_inverse_of_v_convert_wr():
    """The same conversion written from either side gives the same pair, both
    sides print with the parameters resolved to numbers, only `v` stays."""
    wr_a, wr_a_s, rd_a, rd_a_s = parse_resolvable_v_convert_wr('{ v * 16 }', {}, v_type=skmap.VType.f)
    wr_b, wr_b_s, rd_b, rd_b_s = parse_resolvable_v_convert_rd('{ v / 16 }', {}, v_type=skmap.VType.f)
    assert wr_a_s == wr_b_s == '(v * 16)'
    assert rd_a_s == rd_b_s == '(v / 16)'

def test_v_convert_rd_derives_the_write_side_exactly():
    """A Q4 scale written as a read conversion, the derived write side is the
    exact scale (no integer division by zero, no lost values)."""
    wr, wr_s, rd, rd_s = parse_resolvable_v_convert_rd('{ v / 16 }', {}, v_type=skmap.VType.f)
    assert wr_s == '(v * 16)'
    assert rd_s == '(v / 16)'
    # an offset stays exact through the rational inversion
    wr, wr_s, rd, rd_s = parse_resolvable_v_convert_rd('{ (v + 2) / 4 }', {}, v_type=skmap.VType.f)
    assert wr_s == '((v * 4) - 2)'
    assert rd_s == '((v + 2) / 4)'

def make_recipe(tmp_path : Path, var : str, ipkg : str = '', k : str = '') -> 'skmap.code_generator_parse_recipe.Recipe':
    from skmap.code_generator_parse_recipe import parse_recipe_file
    text = f'''
id = "TVConv"
version = 1
name = "v_convert_test"
sw_module = "VConvertTest"
fw_module = "v_convert_test"
ipkg = [ {ipkg} ]
k = [ {{name = "RW_LEN", t = "u8", desc = "len"}} {k} ]
var = [
  {{name = "temp", t = "s16", acc = "rw", desc = "temp"{var}}},
]
'''
    p = tmp_path / 'recipe.toml'
    p.write_text(text)
    return parse_recipe_file(p)

def test_recipe_v_convert_rd_option(tmp_path):
    """A recipe with v_convert_rd generates the same conversion as the one
    with v_convert_wr, the write side is derived."""
    recipe_wr = make_recipe(tmp_path, var=', v_type="f", v_convert_wr="{ v * 16 }"')
    recipe_rd = make_recipe(tmp_path, var=', v_type="f", v_convert_rd="{ v / 16 }"')
    wr = recipe_wr.var[0]
    rd = recipe_rd.var[0]
    assert str(resolvable_print_source(wr.v_convert_wr)) == '(v * 16)'
    assert str(resolvable_print_source(rd.v_convert_wr)) == '(v * 16)'
    assert str(resolvable_print_source(wr.v_convert_rd)) == '(v / 16)'
    assert str(resolvable_print_source(rd.v_convert_rd)) == '(v / 16)'
    # the same conversion is the same module, written from either side
    assert recipe_wr.checksum_str() == recipe_rd.checksum_str()

def test_recipe_v_convert_wr_and_rd_together_are_rejected(tmp_path):
    """A register never has both sides, they are inverses of each other."""
    with pytest.raises(AssertionError, match='inverses of each other'):
        make_recipe(tmp_path, var=', v_type="f", v_convert_wr="{ v * 16 }", v_convert_rd="{ v / 16 }"')

def test_recipe_old_v_convert_option_is_rejected(tmp_path):
    """The old `v_convert` names the new options in the error."""
    with pytest.raises(AssertionError, match='v_convert_wr'):
        make_recipe(tmp_path, var=', v_type="f", v_convert="{ v * 16 }"')

def test_v_options_use_ipkg_and_k_parameters(tmp_path):
    """`v_check`, `v_convert_wr` and `v_convert_rd` can use the `ipkg` values
    and the `k` registers of the recipe as parameters of the expression."""
    # an ipkg value resolves to its number at recipe parse time, a k register
    # has its value only at runtime so it keeps its name in the text (it is
    # read through the module in the generated code and resolved when
    # printed, see test_k_parameters_are_resolved_when_printed)
    recipe = make_recipe(tmp_path,
                         ipkg = '{name = "SCALE", value = 8 },',
                         var  = (', v_check="{ (v >= (-1*SCALE)) && (v <= 100) && ((v % RW_LEN) == 0) }"'
                                 ', v_convert_wr="{ v + SCALE }"'))
    reg = recipe.var[0]
    assert reg.v_check_str == '(((v >= (-1 * 8)) && (v <= 100)) && ((v % RW_LEN) == 0))'
    assert reg.v_convert_wr_str == '(v + 8)'
    assert reg.v_convert_rd_str == '(v - 8)'

    recipe = make_recipe(tmp_path,
                         ipkg = '{name = "SCALE", value = 8 },',
                         var  = ', v_type="f", v_convert_rd="{ v / SCALE }"')
    reg = recipe.var[0]
    assert reg.v_convert_wr_str == '(v * 8)'
    assert reg.v_convert_rd_str == '(v / 8)'

def test_v_options_print_resolved_numbers(tmp_path):
    """The printed text of the three options resolves the recipe `ipkg` names
    to their number, only the value parameter `v` can not be simplified (a
    `k` register is resolved when printed, see
    test_k_parameters_are_resolved_when_printed)."""
    recipe = make_recipe(tmp_path,
                         ipkg = '{name = "SCALE", value = 8 },',
                         var  = (', v_type="f", v_check="{ v <= SCALE }"'
                                 ', v_convert_wr="{ v * SCALE + SCALE }"'))
    reg = recipe.var[0]
    assert 'SCALE' not in reg.v_check_str and 'v' in reg.v_check_str
    assert reg.v_check_str == '(v <= 8)'
    assert reg.v_convert_wr_str == '((v * 8) + 8)'
    assert reg.v_convert_rd_str == '((v - 8) / 8)'

def test_k_parameters_are_resolved_when_printed():
    """A `k` register has its value only at runtime, its name stays in the
    text of `v_check` / `v_convert_wr` / `v_convert_rd` and the runtime
    resolves it from the module cache when printing, only `v` stays."""
    module = ModuleStub()
    reg_k = skmap.RegK(module, name='RW_LEN',
                       value_type=skmap.ValueType(kind=ValueKind.uint, width=8),
                       desc='k reg')
    reg_k.addr = 16
    module.write_bytes_cached(16, bytes([3]))       # the firmware reported 3
    module.arr_reg_k = [reg_k]
    reg = skmap.Reg(module, name='test', value_type=skmap.ValueType(kind=ValueKind.sint, width=8),
                    acc=skmap.Acc.rw, desc='test reg',
                    v_check=ValueCheck(lambda v: (v % 3) == 0, '((v % RW_LEN) == 0)'),
                    v_convert=ValueConvert(lambda v: v * 4, lambda v: v / 4,
                                           '(v * RW_LEN)', '(v / RW_LEN)'))
    reg.addr = 0
    # the k name resolves to the value of the module, `v` stays
    assert reg.resolve_expr_names('((v % RW_LEN) == 0)') == '((v % 3) == 0)'
    # only whole words, RW_LEN is the suffix of MEM_RW_LEN and stays
    assert reg.resolve_expr_names('MEM_RW_LEN') == 'MEM_RW_LEN'
    assert reg.resolve_expr_names('(v + OTHER)') == '(v + OTHER)'
    # the `= ... ` marker of the reg map
    assert reg.v_convert_marker() == '={ v * 3 } '
    # the check printed with the value in the reg map
    assert '(v % 3) == 0' in plain(reg._v_check_bound_str(''))
    # and the error messages
    with pytest.raises(ValueError) as e:
        reg.check_value_limit(1)
    assert '((v % 3) == 0)' in str(e.value)

# ---------- unique names ----------

def write_named_recipe(tmp_path : Path, ipkg : str, k : str, var : str, mem : str = '') -> Path:
    from skmap.code_generator_parse_recipe import parse_recipe_file
    text = f'''
id = "TName"
version = 1
name = "name_test_module"
sw_module = "NameTestModule"
fw_module = "name_test_module"
ipkg = [ {ipkg} ]
k = [ {k} ]
var = [ {var} ]
mem = [ {mem} ]
'''
    p = tmp_path / 'recipe.toml'
    p.write_text(text)
    return parse_recipe_file(p)

def mem_of(name : str) -> str:
    return (f'{{name = "{name}", t = "[8]u8", acc = "rw", desc = "m", '
            f'fw_depth = 8, fw_width = 8, fw_latency = 1}}')

def test_duplicate_names_are_rejected(tmp_path):
    """Every ipkg, k, var and mem name of a recipe has to be unique."""
    ipkg = '{name = "DUP", value = 2 }, {name = "DUP", value = 3 }'
    with pytest.raises(ValueError, match='duplicate name'):
        write_named_recipe(tmp_path, ipkg = ipkg, k = '', var = '')
    with pytest.raises(ValueError, match='duplicate name'):
        write_named_recipe(tmp_path, ipkg = '{name = "DUP", value = 2 },',
                           k = '{name = "DUP", t = "u8", desc = "x"}', var = '')
    with pytest.raises(ValueError, match='duplicate name'):
        write_named_recipe(tmp_path, ipkg = '',
                           k = '{name = "DUP", t = "u8", desc = "x"}, {name = "DUP", t = "u8", desc = "y"}',
                           var = '')
    with pytest.raises(ValueError, match='duplicate name'):
        write_named_recipe(tmp_path, ipkg = '',
                           k = '{name = "DUP", t = "u8", desc = "x"}',
                           var = '{name = "DUP", t = "u8", acc = "rw", desc = "v"}')
    with pytest.raises(ValueError, match='duplicate name'):
        write_named_recipe(tmp_path, ipkg = '', k = '',
                           var = ('{name = "DUP", t = "u8", acc = "rw", desc = "v"}, '
                                  '{name = "DUP", t = "u8", acc = "ro", desc = "w"}'))
    with pytest.raises(ValueError, match='duplicate name'):
        write_named_recipe(tmp_path, ipkg = '{name = "DUP", value = 2 },', k = '',
                           var = '{name = "DUP", t = "u8", acc = "rw", desc = "v"}')
    # a mem name is unique against the other mems and every other name
    with pytest.raises(ValueError, match='duplicate name'):
        write_named_recipe(tmp_path, ipkg = '', k = '', var = '',
                           mem = f'{mem_of("DUP")}, {mem_of("DUP")}')
    with pytest.raises(ValueError, match='duplicate name'):
        write_named_recipe(tmp_path, ipkg = '', k = '',
                           var = '{name = "DUP", t = "u8", acc = "rw", desc = "v"}',
                           mem = mem_of('DUP'))
    # unique names across all four kinds are fine
    write_named_recipe(tmp_path, ipkg = '{name = "I", value = 2 },',
                       k = '{name = "K", t = "u8", desc = "x"}',
                       var = '{name = "V", t = "u8", acc = "rw", desc = "v"}',
                       mem = mem_of('M'))


# ---------- generated module ----------

def test_generated_module_has_raw_and_converted_functions():
    """The generated module converts in the default functions, *_raw bypasses it."""
    src = (RECIPE.parent / 'recipe_test_bench_module.py').read_text()

    # temp has a v_convert: the default functions are float, the raw ones int
    assert 'def temp_read_cached(self) -> float:' in src
    assert 'async def temp_read(self) -> float:' in src
    assert 'def temp_write_cached(self, value : float):' in src
    assert 'async def temp_write(self, value : float):' in src
    assert 'def temp_read_cached_raw(self) -> int:' in src
    assert 'async def temp_read_raw(self) -> int:' in src
    assert 'def temp_write_cached_raw(self, value : int):' in src
    assert 'async def temp_write_raw(self, value : int):' in src
    assert 'return self._var_temp.read_converted_cached()' in src
    assert 'return self._var_temp.read_sint_cached()' in src

    # the min / max properties are gone
    assert '_max(self)' not in src
    assert '_min(self)' not in src

    # registers without a v_convert keep their old functions
    assert 'def regs_rw_read_cached(self) -> list[int]:' in src
    assert 'def regs_rw_read_cached_raw(self)' not in src
    assert 'def regs_rw_write_idx_cached(self, idx : int, val : int):' in src

    # the check text is printed with resolved values
    assert "'((v % 2) == 0)'" in src
    assert 'v_check=skmap.ValueCheck(' in src
    assert 'v_convert=skmap.ValueConvert(' in src


# ---------- v_convert marker of the reg map ----------

def test_v_convert_marker_text():
    """The reg map prints the conversion in front of the description."""
    conv = ValueConvert(lambda v: v * 16, lambda v: v / 16, '(v * 16)', '(v / 16)', skmap.VType.f)
    assert make_reg(v_convert=conv).v_convert_marker() == '={ v * 16 } '
    # a reg without a v_convert has no marker, it changes nothing else
    assert make_reg().v_convert_marker() == ''
    assert make_reg(v_check=EVEN_U).v_convert_marker() == ''
    # a check is not a conversion: it stays in the value column
    assert make_reg(v_check=EVEN_U).read_rich_str_cached().startswith('[green](v % 2) == 0')
    # braces (the way a recipe writes it) are normalised to the same text
    braced = ValueConvert(lambda v: v * 2, lambda v: v / 2, '{ v * 2 }', '{ v / 2 }')
    assert make_reg(v_convert=braced).v_convert_marker() == '={ v * 2 } '

def test_desc_cell_of_reg_map_table():
    """The description cell of the reg map holds the marker in the color of
    Ass.none followed by the description of the register."""
    from rich.text import Text
    from skmap.reg_map_table import desc_cell
    conv = ValueConvert(lambda v: v * 16, lambda v: v / 16, '(v * 16)', '(v / 16)', skmap.VType.f)
    reg = make_reg(v_convert=conv)
    reg.desc = 'scaled'
    cell = desc_cell(reg)
    assert isinstance(cell, Text)
    assert cell.plain == '={ v * 16 } scaled'
    assert cell.spans[0].style == skmap.Ass.none.color
    # only the marker is colored, the description keeps the color of the column
    assert len(cell.spans) == 1
    assert (cell.spans[0].start, cell.spans[0].end) == (0, len('={ v * 16 } '))
    # a register without a v_convert keeps the plain description
    assert desc_cell(make_reg()) == make_reg().desc

# ---------- removed options ----------

def test_removed_options_are_rejected(tmp_path):
    """min / max / check are gone, an old recipe fails with a helpful error."""
    for removed, value in (('min', 2), ('max', 100), ('check', '{ v > 2 }')):
        d = {'name': 'X', 't': 'u8', 'acc': 'rw', 'desc': 'x', removed: value}
        with pytest.raises(AssertionError, match=removed):
            parse_recipe_v_options(d, {}, ValueKind.uint, False)

def test_removed_options_help_says_v_check():
    d = {'name': 'X', 't': 'u8', 'acc': 'rw', 'desc': 'x', 'max': 100}
    with pytest.raises(AssertionError) as e:
        parse_recipe_v_options(d, {}, ValueKind.uint, False)
    assert 'v_check' in str(e.value)

def test_float_v_convert_rounds_the_raw_value():
    """The value of the register is an int, a fractional float user value
    rounds it (half away from zero, same as c++)."""
    reg = make_reg(v_type=skmap.VType.f,
                   v_check=skmap.ValueCheck(lambda v: -1000 <= v <= 1000, 'v in [-1000, 1000]', skmap.VType.f),
                   v_convert=skmap.ValueConvert(lambda v: v * 16, lambda v: v / 16,
                                                '(v * 16)', '(v / 16)', skmap.VType.f))
    reg.write_converted_cached(1.55)     # raw 24.8 -> 25
    assert reg.read_sint_cached() == 25
    assert reg.read_converted_cached() == 25 / 16
    reg.write_converted_cached(-1.5/16)  # raw -1.5 -> -2
    assert reg.read_sint_cached() == -2
