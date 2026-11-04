"""Tests for the skmap_plot_regs application logic (no GUI).

Covers the command line target parsing (`<addr> <reg> ...`, `vec[idx]`), the
trace expansion of a `RegVec` given without an index, the `v_convert_rd` on
the plotted value, the `v_check` failure marking, the clear after read of
an `rc` register, and the `-I` import of a generated module file.

Run with: python3 -m pytest pip/skmap_plot_regs/tests -q
Requires pyqtgraph + a Qt binding (the application imports them at module
level), the plot window itself is not opened by these tests.
"""

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'pip' / 'skmap' / 'src'))
sys.path.insert(0, str(ROOT / 'pip' / 'regio' / 'src'))
sys.path.insert(0, str(ROOT / 'pip' / 'skmap_plot_regs' / 'src'))

import skmap                                                     # noqa: E402
from skmap.basic_types import ValueKind, ValueType, promote_to_sw_w  # noqa: E402
from skmap.reg import ValueCheck, ValueConvert                   # noqa: E402

import skmap_plot_regs as plot_regs                              # noqa: E402


class MemRegio:
    """Regio backed by one bytearray of device memory."""

    def __init__(self, size : int = 0x2000):
        self.mem = bytearray(size)

    async def read(self, addr : int, size : int) -> bytes:
        return bytes(self.mem[addr:addr + size])

    async def write(self, addr : int, data : bytes):
        self.mem[addr:addr + len(data)] = data


class PlotModuleStub:
    """Enough of a skmap.Module for standalone Regs backed by a Regio.

    Mirrors the cache handling of skmap.Module: reads refresh the cache,
    writes go to the cache and to the regio.
    """

    def __init__(self, regio : MemRegio, base_addr : int = 0x100):
        self._regio     = regio
        self._base_addr = base_addr
        self._byte_align = 1
        self._cache     = bytearray(0x2000)
        self._arr_reg_k   = []
        self._arr_reg_var = []

    @classmethod
    def name(cls) -> str:
        return 'PlotStub'

    @property
    def base_addr(self) -> int:
        return self._base_addr

    @property
    def arr_reg_k(self):
        return self._arr_reg_k

    @property
    def arr_reg_var(self):
        return self._arr_reg_var

    def _byte_aligment_from_val_width(self, width : int) -> int:
        return max(self._byte_align, promote_to_sw_w(width) // 8)

    def read_cached(self, addr : int, size : int) -> bytes:
        a = addr - self._base_addr
        return bytes(self._cache[a:a + size])

    def write_bytes_cached(self, addr : int, data : bytes):
        a = addr - self._base_addr
        self._cache[a:a + len(data)] = data

    async def read_bytes(self, addr : int, size : int) -> bytes:
        b = await self._regio.read(addr, size)
        self.write_bytes_cached(addr, b)
        return b

    async def write_bytes(self, addr : int, data : bytes):
        self.write_bytes_cached(addr, data)
        await self._regio.write(addr, bytes(data))


def make_reg(module, name, kind, width, acc, addr, **kwargs) -> skmap.Reg:
    reg = skmap.Reg(module, name=name, value_type=ValueType(kind=kind, width=width),
                    acc=acc, desc=name, **kwargs)
    reg.addr = addr
    module._arr_reg_var.append(reg)
    return reg


# ---------------------------------------------------------------------------
# command line parsing


def test_parse_targets_grouping():
    groups = plot_regs.parse_targets(
        ['0x1000', 'temp', 'vec_foo_bar[2]', '0x2000', 'status'])
    assert groups == [(0x1000, ['temp', 'vec_foo_bar[2]']), (0x2000, ['status'])]


def test_parse_targets_reg_before_addr():
    with pytest.raises(SystemExit):
        plot_regs.parse_targets(['temp', '0x1000'])


def test_parse_targets_module_without_regs():
    with pytest.raises(SystemExit):
        plot_regs.parse_targets(['0x1000', 'temp', '0x2000'])


def test_parse_reg_spec():
    assert plot_regs.parse_reg_spec('reg_foo') == ('reg_foo', None)
    assert plot_regs.parse_reg_spec('vec_foo_bar[2]') == ('vec_foo_bar', 2)
    with pytest.raises(SystemExit):
        plot_regs.parse_reg_spec('not a reg')


def test_import_generated_module_from_file(tmp_path):
    """-I with a path to a generated .py file registers it with the factory."""
    recipe = tmp_path / 'plot_import_test_module.toml'
    recipe.write_text('id = "TPlt"\nversion = 1\nname = "plot_import_test_module"\n'
                      'sw_module = "PlotImportTestModule"\nfw_module = "plot_import_test_module"\n'
                      'desc = "-I file import test"\nipkg = []\nk = []\nvar = []\n')
    py_file = tmp_path / 'plot_import_test_module.py'
    skmap.generate_py_module(recipe, py_file)
    plot_regs.import_generated_module(str(py_file))
    assert 'TPlt' in skmap.module.factory.lookup
    assert 1 in skmap.module.factory.lookup['TPlt']


def test_import_generated_module_missing_file():
    with pytest.raises(SystemExit):
        plot_regs.import_generated_module('does/not/exist_module.py')


# ---------------------------------------------------------------------------
# trace construction


def setup_module_stub():
    return PlotModuleStub(MemRegio())


def test_make_traces_vec_without_idx_expands():
    module = setup_module_stub()
    reg = skmap.RegVec(module, name='vec_foo_bar', acc=skmap.Acc.ro, desc='v',
                       value_type=ValueType(kind=ValueKind.uint, width=8, vec_len=4))
    reg.addr = 0x100
    module._arr_reg_var.append(reg)
    traces = plot_regs.make_traces(module, 'vec_foo_bar')
    assert [t.idx for t in traces] == [0, 1, 2, 3]
    assert all('vec_foo_bar[' in t.label and 'PlotStub @0x100' in t.label for t in traces)


def test_make_traces_vec_with_idx():
    module = setup_module_stub()
    reg = skmap.RegVec(module, name='vec_foo_bar', acc=skmap.Acc.ro, desc='v',
                       value_type=ValueType(kind=ValueKind.uint, width=8, vec_len=4))
    reg.addr = 0x100
    module._arr_reg_var.append(reg)
    traces = plot_regs.make_traces(module, 'vec_foo_bar[2]')
    assert len(traces) == 1 and traces[0].idx == 2


def test_make_traces_vec_idx_out_of_range():
    module = setup_module_stub()
    reg = skmap.RegVec(module, name='vec', acc=skmap.Acc.ro, desc='v',
                       value_type=ValueType(kind=ValueKind.uint, width=8, vec_len=2))
    reg.addr = 0x100
    module._arr_reg_var.append(reg)
    with pytest.raises(SystemExit):
        plot_regs.make_traces(module, 'vec[2]')


def test_make_traces_idx_on_scalar_rejected():
    module = setup_module_stub()
    make_reg(module, 'scalar', ValueKind.uint, 32, skmap.Acc.ro, 0x100)
    with pytest.raises(SystemExit):
        plot_regs.make_traces(module, 'scalar[0]')


def test_make_traces_char_rejected():
    module = setup_module_stub()
    make_reg(module, 'txt', ValueKind.char, 8, skmap.Acc.ro, 0x100)
    with pytest.raises(SystemExit):
        plot_regs.make_traces(module, 'txt')


def test_make_traces_unknown_reg_lists_available():
    module = setup_module_stub()
    make_reg(module, 'known_reg', ValueKind.uint, 32, skmap.Acc.ro, 0x100)
    with pytest.raises(SystemExit, match='known_reg'):
        plot_regs.make_traces(module, 'unknown_reg')


# ---------------------------------------------------------------------------
# sampling


def test_sample_scalar():
    module = setup_module_stub()
    reg = make_reg(module, 'cnt', ValueKind.uint, 32, skmap.Acc.ro, 0x100)
    module._regio.mem[0x100:0x104] = (1234).to_bytes(4, 'little')
    trace = plot_regs.Trace(module, reg, None)
    value, ok = asyncio.run(trace.sample())
    assert value == 1234
    assert ok                                     # no v_check -> passes


def test_sample_uses_v_convert_rd():
    module = setup_module_stub()
    conv = ValueConvert(lambda v: v * 16, lambda v: v / 16, '{ v * 16 }', '{ v / 16 }')
    reg = make_reg(module, 'temp', ValueKind.sint, 16, skmap.Acc.ro, 0x100,
                   v_convert=conv)
    module._regio.mem[0x100:0x104] = (-32).to_bytes(4, 'little', signed=True)
    trace = plot_regs.Trace(module, reg, None)
    value, _ = asyncio.run(trace.sample())
    assert value == -2                            # the user value, not the raw -32


def test_sample_rc_cleared_after_read():
    module = setup_module_stub()
    reg = make_reg(module, 'err', ValueKind.uint, 32, skmap.Acc.rc, 0x100)
    module._regio.mem[0x100:0x104] = (0xAB).to_bytes(4, 'little')
    trace = plot_regs.Trace(module, reg, None)
    value, _ = asyncio.run(trace.sample())
    assert value == 0xAB
    assert module._regio.mem[0x100:0x104] == bytes(4)     # cleared on the device
    # a second read of the (now clear) register gives 0
    value, _ = asyncio.run(trace.sample())
    assert value == 0


def test_sample_rc_vec_idx_cleared_after_read():
    module = setup_module_stub()
    reg = skmap.RegVec(module, name='errs', acc=skmap.Acc.rc, desc='v',
                       value_type=ValueType(kind=ValueKind.uint, width=8, vec_len=4))
    reg.addr = 0x100
    module._arr_reg_var.append(reg)
    for ii in range(4):
        module._regio.mem[0x100 + ii * reg.elem_offset] = 0x10 + ii
    trace = plot_regs.Trace(module, reg, 2)
    value, _ = asyncio.run(trace.sample())
    assert value == 0x12
    assert module._regio.mem[0x100:0x104] == bytes([0x10, 0x11, 0, 0x13])


def test_sample_v_check_marks_failure():
    module = setup_module_stub()
    check = ValueCheck(lambda v: (v % 2) == 0, '(v % 2) == 0')
    reg = make_reg(module, 'even', ValueKind.uint, 32, skmap.Acc.ro, 0x100,
                   v_check=check)
    trace = plot_regs.Trace(module, reg, None)
    module._regio.mem[0x100:0x104] = (2).to_bytes(4, 'little')
    assert asyncio.run(trace.sample()) == (2, True)
    module._regio.mem[0x100:0x104] = (3).to_bytes(4, 'little')
    assert asyncio.run(trace.sample()) == (3, False)


def test_sample_vec_idx():
    module = setup_module_stub()
    reg = skmap.RegVec(module, name='adc', acc=skmap.Acc.ro, desc='v',
                       value_type=ValueType(kind=ValueKind.sint, width=16, vec_len=4))
    reg.addr = 0x100
    module._arr_reg_var.append(reg)
    for ii, v in enumerate([-1, 2, -3, 4]):
        module._regio.mem[0x100 + ii * reg.elem_offset:
                          0x100 + ii * reg.elem_offset + 2] = v.to_bytes(2, 'little', signed=True)
    trace = plot_regs.Trace(module, reg, 2)
    value, _ = asyncio.run(trace.sample())
    assert value == -3


def test_sample_k_uses_cache():
    module = setup_module_stub()
    reg = skmap.RegK(module, name='ver', value_type=ValueType(kind=ValueKind.uint, width=32),
                     desc='k')
    reg.addr = 0x100
    module._arr_reg_k.append(reg)
    module.write_bytes_cached(0x100, (7).to_bytes(4, 'little'))
    trace = plot_regs.Trace(module, reg, None)
    value, _ = asyncio.run(trace.sample())
    assert value == 7


# ---------------------------------------------------------------------------
# plot window handling


def test_trim_trace():
    module = setup_module_stub()
    reg = make_reg(module, 'r', ValueKind.uint, 32, skmap.Acc.ro, 0x100)
    reg.v_check = ValueCheck(lambda v: v > 10, 'v > 10')
    trace = plot_regs.Trace(module, reg, None)
    for ii in range(10):
        trace.add_sample(float(ii), ii, ii > 10, length=10)
    assert list(trace.bad_xs) == list(range(10))   # all of them failed, v > 10
    for ii in range(10, 20):
        trace.add_sample(float(ii), ii, ii > 10, length=10)
    assert list(trace.xs) == list(range(10, 20))
    assert list(trace.bad_xs) == [10.0]        # only ii == 10 fails (check_ok = ii > 10)
    # shorten to 3 points, the oldest samples and their markers go
    plot_regs.trim_trace(trace, 3)
    assert list(trace.xs) == [17, 18, 19]
    assert list(trace.ys) == [17, 18, 19]
    assert list(trace.bad_xs) == []            # the marker at 10 scrolled out
    # a failing marker that scrolls out with the trim is dropped too
    trace2 = plot_regs.Trace(module, reg, None)
    trace2.add_sample(0.0, 1, False, length=10)
    trace2.add_sample(1.0, 2, True, length=10)
    plot_regs.trim_trace(trace2, 1)
    assert list(trace2.xs) == [1.0]
    assert list(trace2.bad_xs) == []


def test_add_sample_keeps_plot_length():
    module = setup_module_stub()
    reg = make_reg(module, 'r', ValueKind.uint, 32, skmap.Acc.ro, 0x100)
    trace = plot_regs.Trace(module, reg, None)
    check = ValueCheck(lambda v: v > 10, 'v > 10')
    reg.v_check = check
    for ii in range(20):
        trace.add_sample(float(ii), ii, ii > 10, length=5)
    assert list(trace.xs) == [15, 16, 17, 18, 19]
    assert list(trace.ys) == [15, 16, 17, 18, 19]
    # the failing sample at t=0..10 scrolled out of the window
    assert list(trace.bad_xs) == []
    trace.add_sample(30.0, 1, False, length=5)
    assert list(trace.bad_xs) == [30.0]


# ---------------------------------------------------------------------------
# SkmapPlotRegs (third party entry point)


def make_vec(module, name, vec_len):
    reg = skmap.RegVec(module, name=name, acc=skmap.Acc.ro, desc='v',
                       value_type=ValueType(kind=ValueKind.uint, width=8, vec_len=vec_len))
    reg.addr = 0x200
    module._arr_reg_var.append(reg)
    return reg


def test_plot_reg_add_reg_scalar():
    module = setup_module_stub()
    reg = make_reg(module, 'temp', ValueKind.uint, 32, skmap.Acc.ro, 0x100)
    plot = plot_regs.SkmapPlotRegs()
    plot.add_reg(reg)
    assert [t.idx for t in plot.traces] == [None]
    assert plot.traces[0].reg is reg


def test_plot_reg_add_reg_rejects_vec():
    module = setup_module_stub()
    vec = make_vec(module, 'adc', 4)
    plot = plot_regs.SkmapPlotRegs()
    with pytest.raises(TypeError):
        plot.add_reg(vec)
    assert plot.traces == []


def test_plot_reg_add_reg_vec_all():
    module = setup_module_stub()
    vec = make_vec(module, 'adc', 4)
    plot = plot_regs.SkmapPlotRegs()
    plot.add_reg_vec_all(vec)
    assert [t.idx for t in plot.traces] == [0, 1, 2, 3]
    assert all(t.reg is vec for t in plot.traces)


def test_plot_reg_add_reg_vec_idx():
    module = setup_module_stub()
    vec = make_vec(module, 'adc', 4)
    plot = plot_regs.SkmapPlotRegs()
    plot.add_reg_vec_idx(vec, 2)
    assert [t.idx for t in plot.traces] == [2]


def test_plot_reg_add_reg_vec_idx_out_of_range():
    """A bad index is a programming error of the caller: TypeError."""
    module = setup_module_stub()
    vec = make_vec(module, 'adc', 2)
    plot = plot_regs.SkmapPlotRegs()
    with pytest.raises(TypeError):
        plot.add_reg_vec_idx(vec, 2)
    with pytest.raises(TypeError):
        plot.add_reg_vec_idx(vec, -1)
    assert plot.traces == []


def test_plot_reg_run_without_regs_exits():
    with pytest.raises(SystemExit):
        plot_regs.SkmapPlotRegs().run()


# ---------------------------------------------------------------------------
# the plot settings: the update rate and the number of points


def test_clamp_period():
    assert plot_regs.clamp_period(1.0) == 1.0
    assert plot_regs.clamp_period(0.0) == plot_regs.PERIOD_MIN
    assert plot_regs.clamp_period(0.001) == plot_regs.PERIOD_MIN
    assert plot_regs.clamp_period(1e9) == plot_regs.PERIOD_MAX


def test_clamp_length():
    assert plot_regs.clamp_length(100) == 100
    assert plot_regs.clamp_length(0) == plot_regs.LENGTH_MIN
    assert plot_regs.clamp_length(-5) == plot_regs.LENGTH_MIN
    assert plot_regs.clamp_length(10_000_000) == plot_regs.LENGTH_MAX


def test_plot_reg_clamps_its_settings():
    """The constructor holds the values that are used, not what was asked."""
    plot = plot_regs.SkmapPlotRegs(period=0.0001, length=0)
    assert plot.period == plot_regs.PERIOD_MIN
    assert plot.length == plot_regs.LENGTH_MIN
    plot = plot_regs.SkmapPlotRegs(period=1e6, length=10_000_000)
    assert plot.period == plot_regs.PERIOD_MAX
    assert plot.length == plot_regs.LENGTH_MAX


def test_package_exports_its_public_api():
    """skmap_plot_regs is a package (src/skmap_plot_regs/, as the other pip
    projects), the public API is reachable on the package."""
    import skmap_plot_regs
    assert skmap_plot_regs.SkmapPlotRegs is plot_regs.SkmapPlotRegs
    assert skmap_plot_regs.main is plot_regs.main
    assert skmap_plot_regs.__version__
    for name in skmap_plot_regs.__all__:
        assert hasattr(skmap_plot_regs, name), name

