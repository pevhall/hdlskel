"""Tests for the functions generated for a `wt` (write trigger) register.

A `wt` register is *triggered* with `<reg>_write_trigger`, that is the write
the regio sees. `<reg>_write_cached` writes only the cache of the module, the
same function a `rw` register has. For a vector `wt` register the functions are
per lane (`<reg>_write_idx_cached`, `<reg>_write_trigger_idx`).

With a recipe `v_convert` the default functions take the value of the module
user and the `*_raw` functions the bits of the register, without a `v_convert`
there are no `*_raw` functions at all.

Run with: python3 -m pytest pip/skmap/tests -q
"""

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'pip' / 'skmap' / 'src'))

import skmap                                                     # noqa: E402
from skmap.basic_types import promote_to_sw_w                    # noqa: E402
from skmap.reg import ValueCheck, ValueConvert                   # noqa: E402

RECIPE = """
id = "TWt"
version = 1
name = "wt_test_module"
sw_module = "WtTestModule"
fw_module = "wt_test_module"
desc = "wt register test"
ipkg = []
k = []
var = [
  {name = "wt_s",   t = "u8",     acc = "wt", desc = "scalar wt"},
  {name = "wt_v",   t = "[4]u8",  acc = "wt", desc = "vector wt"},
  {name = "wt_cv",  t = "s16",    acc = "wt", desc = "wt with a v_convert", v_type = "f", v_convert = "{ v * 16 }", v_check = "{ (v >= -100) && (v <= 100) }"},
  {name = "wt_cvv", t = "[3]s16", acc = "wt", desc = "vector wt with a v_convert", v_convert = "{ v + 8 }", v_check = "{ (v >= -100) && (v <= 100) }"},
]
"""


def generate(tmp_path : Path) -> tuple[str, str]:
    """Generated python and c++ source of the recipe above."""
    recipe = tmp_path / 'wt_test_module.toml'
    recipe.write_text(RECIPE)
    py = tmp_path / 'wt_test_module.py'
    hpp = tmp_path / 'wt_test_module.hpp'
    cpp = tmp_path / 'wt_test_module.cpp'
    skmap.generate_py_module(recipe, py)
    skmap.generate_cpp_module(recipe, hpp, cpp)
    return py.read_text(), hpp.read_text()


class ModuleStub:
    """Enough of a skmap.Module for a standalone Reg.

    Every regio access raises, a function that works with it only touches the
    cache.
    """

    def __init__(self):
        self._byte_align = 1
        self._cache = bytearray(1024)
        self.base_addr = 0

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


def make_reg(acc : skmap.Acc, **kwargs) -> skmap.Reg:
    kind = kwargs.pop('kind', skmap.ValueKind.sint)
    width = kwargs.pop('w', 8)
    reg = skmap.Reg(ModuleStub(), name='wt',
                    value_type=skmap.ValueType(kind=kind, width=width),
                    acc=acc, desc='wt test reg', **kwargs)
    reg.addr = 0
    return reg


# ---------- generated python ----------

def test_py_wt_scalar(tmp_path):
    py, _ = generate(tmp_path)
    assert 'def wt_s_read_cached(self) -> int:' in py
    assert 'def wt_s_write_cached(self, value : int):' in py
    assert 'wt_s.write_uint_cached(value)' in py
    assert 'async def wt_s_write_trigger(self, value : int):' in py
    assert 'await self._var_wt_s.write_uint(value)' in py
    # no v_convert, so no raw functions
    assert 'wt_s_write_cached_raw' not in py
    assert 'wt_s_write_trigger_raw' not in py

def test_py_wt_vector(tmp_path):
    py, _ = generate(tmp_path)
    assert 'def wt_v_read_idx_cached(self, idx : int) -> int:' in py
    assert 'def wt_v_write_idx_cached(self, idx : int, val : int):' in py
    assert 'async def wt_v_write_trigger_idx(self, idx : int, val : int):' in py
    # every lane is a trigger on its own, there is no write of the whole vector
    assert 'def wt_v_write_cached(' not in py
    assert 'await self._var_wt_v.write_idx_uint(idx, val)' in py

def test_py_wt_with_v_convert(tmp_path):
    py, _ = generate(tmp_path)
    # the default functions are the domain of the module user (float), the
    # *_raw functions the bits of the register (int)
    assert 'def wt_cv_write_cached(self, value : float):' in py
    assert 'self._var_wt_cv.write_converted_cached(value)' in py
    assert 'async def wt_cv_write_trigger(self, value : float):' in py
    assert 'await self._var_wt_cv.write_converted(value)' in py
    assert 'def wt_cv_write_cached_raw(self, value : int):' in py
    assert 'self._var_wt_cv.write_sint_cached(value)' in py
    assert 'async def wt_cv_write_trigger_raw(self, value : int):' in py
    assert 'await self._var_wt_cv.write_sint(value)' in py

def test_py_wt_vector_with_v_convert(tmp_path):
    py, _ = generate(tmp_path)
    assert 'def wt_cvv_write_idx_cached(self, idx : int, val : int):' in py
    assert 'self._var_wt_cvv.write_converted_idx_cached(idx, val)' in py
    assert 'async def wt_cvv_write_trigger_idx(self, idx : int, val : int):' in py
    assert 'await self._var_wt_cvv.write_converted_idx(idx, val)' in py
    assert 'def wt_cvv_write_idx_cached_raw(self, idx : int, val : int):' in py
    assert 'async def wt_cvv_write_trigger_idx_raw(self, idx : int, val : int):' in py


# ---------- generated c++ ----------

def test_cpp_wt(tmp_path):
    _, hpp = generate(tmp_path)
    assert 'void wt_s_write_cached( uint_t value ) { m_var_wt_s->write_uint_cached(value); }' in hpp
    assert 'void wt_s_write_trigger( uint_t value ) { m_var_wt_s->write_uint(value); }' in hpp
    assert 'wt_s_write_cached_raw' not in hpp
    # vector: per lane, no write of the whole vector
    assert 'void wt_v_write_idx_cached(addr_t idx, uint_t val) { m_var_wt_v->write_idx_uint_cached(idx, val); }' in hpp
    assert 'void wt_v_write_trigger_idx(addr_t idx, uint_t val) { m_var_wt_v->write_idx_uint(idx, val); }' in hpp
    assert 'void wt_v_write_cached(' not in hpp

def test_cpp_wt_with_v_convert(tmp_path):
    _, hpp = generate(tmp_path)
    assert 'void wt_cv_write_cached( float_t value ) { m_var_wt_cv->write_converted_cached(value); }' in hpp
    assert 'void wt_cv_write_trigger( float_t value ) { m_var_wt_cv->write_converted(value); }' in hpp
    assert 'void wt_cv_write_cached_raw( sint_t value ) { m_var_wt_cv->write_sint_cached(value); }' in hpp
    assert 'void wt_cv_write_trigger_raw( sint_t value ) { m_var_wt_cv->write_sint(value); }' in hpp

def test_cpp_wt_vector_with_v_convert(tmp_path):
    _, hpp = generate(tmp_path)
    assert 'void wt_cvv_write_idx_cached(addr_t idx, sint_t val) { m_var_wt_cvv->write_idx_converted_cached(idx, val); }' in hpp
    assert 'void wt_cvv_write_trigger_idx(addr_t idx, sint_t val) { m_var_wt_cvv->write_idx_converted(idx, val); }' in hpp
    assert 'void wt_cvv_write_idx_cached_raw(addr_t idx, sint_t val) { m_var_wt_cvv->write_idx_sint_cached(idx, val); }' in hpp


# ---------- runtime behavior of a wt register ----------

def test_wt_write_cached_only_touches_the_cache():
    reg = make_reg(skmap.Acc.wt)
    reg.write_sint_cached(5)
    assert reg.read_sint_cached() == 5
    # the trigger write is the one that reaches the regio (the stub raises)
    with pytest.raises(RuntimeError):
        asyncio.run(reg.write_sint(7))

def test_wt_write_cached_converted():
    reg = make_reg(skmap.Acc.wt, w = 16,
                   v_type = skmap.VType.f,
                   v_check = ValueCheck(lambda v: -100 <= v <= 100,
                                        '((v >= -100) && (v <= 100))', skmap.VType.f),
                   v_convert = ValueConvert(lambda v: v * 16, lambda v: v / 16,
                                            '(v * 16)', '(v / 16)', skmap.VType.f))
    reg.write_converted_cached(1.5)
    assert reg.read_sint_cached() == 24
    assert reg.read_converted_cached() == 1.5
    with pytest.raises(ValueError, match='check'):
        reg.write_converted_cached(1000.0)
    # a raw write checks the user value the bits stand for (1601 / 16 > 100)
    with pytest.raises(ValueError, match='check'):
        reg.write_sint_cached(1601)
    reg.write_sint_cached(1600)
    assert reg.read_converted_cached() == 100.0
