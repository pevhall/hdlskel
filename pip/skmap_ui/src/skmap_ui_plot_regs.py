#!/usr/bin/env python3
"""Plot skmap `var` registers against time with pyqtgraph.

Give one or more modules as a base address followed by the register names to
plot from that module, eg:

    skmap_ui_plot_regs.py 0x1000 temperature pressure 0x2000 status

A `RegVec` element is selected with square brackets, `vec_foo_bar[2]`. A
`RegVec` given without an index plots every element of the vector.

Each entry is read every `-t` seconds and appended to a rolling window of the
last `-l` samples, plotted as amplitude against time (seconds since start)
with one curve per entry (each in its own color) and a legend.

  * a `v_convert_rd` is applied: the plot shows the value of the module user,
    not the raw bits of the register
  * a `v_check` failing on a sample marks that sample with a red triangle
  * an `rc` register is cleared (a zero is written back) after it is read
  * a `rw`, `wt` or `k` register gives a warning (plotting them is usually
    not what you want: an `rw` / `wt` holds the value software wrote and a
    `k` is a constant, reported once at module creation)

The generated skmap module of the device has to be registered before the
modules can be made, import it with `-I` (a module name or the path of a
generated .py file), eg:

    python3 skmap_ui_plot_regs.py -p 39601 \\
        -I ../../../fw/tb/skmap/tb_py_skmap_module_recipe/recipe_test_bench_module.py \\
        0 temp regs_rw

Run with: python3 skmap_ui_plot_regs.py [options] <addr> <reg> ...

The axis ranges are fixed when the first samples arrive and are not
rescaled after every update (the time axis spans the whole -l window).

Third party applications can drive the plot themselves with the
`SkmapUiPlotReg` class: import the generated skmap modules, make the
modules and add registers (a scalar `Reg`, or `RegVec` elements) to the
plot, then call `run()`:

    import skmap
    from skmap_ui_plot_regs import SkmapUiPlotReg

    plot = SkmapUiPlotReg(period=0.5, length=200)
    plot.add_reg(module.temp)              # a scalar Reg
    plot.add_reg_vec_all(module.adc_vals)  # every element of a RegVec
    plot.add_reg_vec_idx(module.status, 2) # one element of a RegVec
    plot.run()                             # opens the window, blocks

This application lives in the skmap_ui project (the skmap package itself does
not depend on pyqtgraph). Requires pyqtgraph and a Qt binding (PyQt6 is the
`skmap-ui[plot]` dependency, PySide6 also works).
"""

import argparse
import asyncio
import importlib
import importlib.util
import logging
import re
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Optional, Union

import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, exec_

import regio.cli_utils
import skmap
from skmap.basic_types import Acc, ValueKind
from skmap.console import console
from skmap.module import make_module

logger = logging.getLogger('skmap_ui_plot_regs')

# reg_name or reg_name[idx]
REG_SPEC_RE = re.compile(r'^(?P<name>[A-Za-z_]\w*)(?:\[(?P<idx>\d+)\])?$')

# acc types that are plotted with a warning
ACC_WARN = {
    Acc.rw: 'is RW, it holds the value software wrote',
    Acc.wt: 'is WT, it holds the value software wrote (write trigger)',
    Acc.k:  'is K, a constant reported at module creation, the plot will be a flat line',
}

# ---------------------------------------------------------------------------
# command line


def positive_float(s : str) -> float:
    v = float(s)
    if v <= 0:
        raise argparse.ArgumentTypeError(f'must be positive, got {s}')
    return v


def positive_int(s : str) -> int:
    v = int(s)
    if v <= 0:
        raise argparse.ArgumentTypeError(f'must be positive, got {s}')
    return v


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog='skmap_ui_plot_regs',
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='example: skmap_ui_plot_regs.py -t 0.5 -l 200 0x1000 temp '
               'adc_vals[3] 0x2000 err_cnt')
    regio.cli_utils.add_parser_args(parser)
    parser.add_argument(
        '-t', '--time',
        type=positive_float,
        default=1.0,
        metavar='SEC',
        help='period between samples in seconds (default: 1)')
    parser.add_argument(
        '-l', '--length',
        type=positive_int,
        default=100,
        metavar='N',
        help='plot length, number of samples to plot (default: 100)')
    parser.add_argument(
        '-I', '--import',
        dest='imports',
        action='append',
        default=[],
        metavar='MODULE|FILE.py',
        help='import a python module, so a generated skmap module registers '
             'with the module factory, a module name or the path of a '
             'generated .py file (repeatable)')
    parser.add_argument(
        '-v',
        dest='verbose',
        action='count',
        default=0,
        help='Increase logging verbosity (repeat up to -vv)')
    parser.add_argument(
        'targets',
        nargs='+',
        help='module base address followed by the registers to plot from it, '
             'eg: 0x1000 reg_foo vec_bar[2] 0x2000 reg_baz')
    args = parser.parse_args()
    return args

# ---------------------------------------------------------------------------
# module import


def import_generated_module(spec : str):
    """Import a generated skmap module, so it registers with the factory.

    `spec` is a python module name (`pkg.recipe_test_bench_module`) or the
    path of a generated .py file, which is loaded from the file.
    """
    path = Path(spec)
    if spec.endswith('.py') or path.is_file():
        if not path.is_file():
            raise SystemExit(f'-I: skmap module file not found: {spec}')
        name = path.stem
        module_spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(module_spec)
        sys.modules[name] = module              # keep a later import consistent
        module_spec.loader.exec_module(module)
        logger.info('imported skmap module %s from %s', name, path)
    else:
        importlib.import_module(spec)
        logger.info('imported skmap module %s', spec)

# ---------------------------------------------------------------------------
# target / register spec parsing


def try_addr(token : str) -> Optional[int]:
    """The token as a module base address, None when it is not a number."""
    try:
        return int(token, 0)
    except ValueError:
        return None


def parse_targets(tokens : list[str]) -> list[tuple[int, list[str]]]:
    """Split the tokens into (base address, register names) groups.

    Every group starts with a module base address, followed by the names of
    the registers to plot from that module.
    """
    groups : list[tuple[int, list[str]]] = []
    for token in tokens:
        addr = try_addr(token)
        if addr is not None:
            groups.append((addr, []))
        elif not groups:
            raise SystemExit(f'register "{token}" given before a module base address')
        else:
            groups[-1][1].append(token)
    for addr, specs in groups:
        if not specs:
            raise SystemExit(f'no registers given for the module at 0x{addr:x}')
    return groups


def parse_reg_spec(token : str) -> tuple[str, Optional[int]]:
    """`name` or `name[idx]` of one command line register spec."""
    m = REG_SPEC_RE.match(token)
    if m is None:
        raise SystemExit(f'invalid register spec "{token}", expected name or name[idx]')
    idx = m['idx']
    return m['name'], None if idx is None else int(idx)

# ---------------------------------------------------------------------------
# traces (one plotted curve)


class Trace:
    """One plotted entry: a register, or one element of a `RegVec`."""

    def __init__(self, module : skmap.Module, reg : skmap.Reg, idx : Optional[int]):
        self.module   = module
        self.reg      = reg
        self.idx      = idx                       # None for a scalar register
        self.label    = (f'{module.name()} @0x{module.base_addr:x} / {reg.name}'
                         + ('' if idx is None else f'[{idx}]'))
        self.curve    = None                      # set by the plot
        self.scatter  = None                      # set by the plot
        self.xs       : deque = deque()
        self.ys       : deque = deque()
        self.bad_xs   : deque = deque()           # samples failing the v_check
        self.bad_ys   : deque = deque()
        self.read_error = False

    async def sample(self) -> tuple[Union[int, float, bool], bool]:
        """Read the entry once, return (value, v_check passed).

        The value is the value of the module user (the `v_convert_rd` of the
        register is applied), an `rc` register is cleared after the read.
        """
        if self.idx is None:
            value = await self.reg.read_converted()
        else:
            value = await self.reg.read_converted_idx(self.idx)
        if self.reg.acc == Acc.rc:
            await self.clear_rc()
        check_ok = True if self.reg.v_check is None else bool(self.reg.v_check(value))
        return value, check_ok

    async def clear_rc(self):
        """Clear an `rc` register after reading it (write zero)."""
        if self.idx is None:
            await self.reg.write_bytes(bytes(self.reg.size))
        else:
            await self.reg.write_idx_bytes(self.idx, bytes(self.reg.elem_size))

    def add_sample(self, t : float, value : Union[int, float, bool], check_ok : bool, length : int):
        """Append one sample, keeping at most `length` samples per curve."""
        while len(self.xs) >= length:
            self.xs.popleft()
            self.ys.popleft()
        self.xs.append(t)
        self.ys.append(float(value))
        if not check_ok:
            self.bad_xs.append(t)
            self.bad_ys.append(float(value))
        # drop the v_check markers that scrolled out of the window
        while self.bad_xs and self.bad_xs[0] < self.xs[0]:
            self.bad_xs.popleft()
            self.bad_ys.popleft()


def find_reg(module : skmap.Module, name : str) -> skmap.Reg:
    for reg in (*module.arr_reg_var, *module.arr_reg_k):
        if reg.name == name:
            return reg
    available = ', '.join(sorted(reg.name for reg in (*module.arr_reg_var, *module.arr_reg_k)))
    raise SystemExit(f'no register "{name}" in module "{module.name()}" at '
                     f'0x{module.base_addr:x}, available: {available}')


def checked_traces(module : skmap.Module, reg : skmap.Reg,
                   idxs : list[Optional[int]]) -> list[Trace]:
    """One trace per entry of `idxs` (None = the whole scalar register).

    Rejects char registers, warns about the acc types of `ACC_WARN` and
    reports the v_check / v_convert handling of the register.
    """
    if reg.value_type.kind == ValueKind.char:
        raise SystemExit(f'register "{reg.name}" of module "{module.name()}" holds chars, '
                          'it cannot be plotted')

    traces = []
    for trace_idx in idxs:
        trace = Trace(module, reg, trace_idx)
        if reg.acc in ACC_WARN:
            console.print(f'[yellow]warning: {trace.label} {ACC_WARN[reg.acc]}[/]')
        if reg.v_check is not None:
            logger.info('%s has a v_check, failing samples are marked in red', trace.label)
        if reg.has_v_convert:
            logger.info('%s is plotted with its v_convert_rd conversion', trace.label)
        traces.append(trace)
    return traces


def make_traces(module : skmap.Module, token : str) -> list[Trace]:
    """The traces of one command line register spec.

    A `RegVec` without an index gives one trace for every element.
    """
    name, idx = parse_reg_spec(token)
    reg = find_reg(module, name)

    if isinstance(reg, skmap.RegVec):
        vec_len = reg.value_type.vec_len
        if idx is None:
            idxs : list[Optional[int]] = list(range(vec_len))
        elif idx >= vec_len:
            raise SystemExit(f'index {idx} out of range for the {vec_len} element '
                             f'vector "{name}" of module "{module.name()}"')
        else:
            idxs = [idx]
    else:
        if idx is not None:
            raise SystemExit(f'"{token}": an index is only allowed on a vector register')
        idxs = [None]

    return checked_traces(module, reg, idxs)


async def build_traces(args : argparse.Namespace) -> list[Trace]:
    """Connect to the regio, make the modules and the traces of every spec."""
    rio = await regio.cli_utils.make_regio_from_args(args)
    traces : list[Trace] = []
    modules : dict[int, skmap.Module] = {}
    for addr, specs in parse_targets(args.targets):
        if addr not in modules:
            modules[addr] = await make_module(rio, addr)
            logger.info('module %s at 0x%x', modules[addr].name(), addr)
        for spec in specs:
            traces.extend(make_traces(modules[addr], spec))
    if not traces:
        raise SystemExit('nothing to plot')
    return traces

# ---------------------------------------------------------------------------
# plot


class PlotApp(QtCore.QObject):
    """The pyqtgraph window and the sampler.

    The regio access is async, Qt is not: the reads run on a dedicated asyncio
    loop on a background thread and the samples are handed to the GUI thread
    through a signal (a queued connection, emitting it from the io thread is
    safe). A tick is skipped while the previous sample is still running.
    """

    samples_ready = QtCore.pyqtSignal(list)   # list of (trace idx, value, check ok, error)

    def __init__(self, traces : list[Trace], period : float, length : int,
                 loop : asyncio.AbstractEventLoop):
        super().__init__()
        self.traces  = traces
        self.period  = period
        self.length  = length
        self.t0      = time.monotonic()
        self._ranges_fixed = False        # the axis ranges are set once
        # the io loop the regio was created on, run everything on it
        self.loop = loop

        self._inflight = False
        self.samples_ready.connect(self.on_samples)

        self._make_plot()

        self.timer = QtCore.QTimer()
        self.timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(max(1, round(period * 1000)))

    # -- plot construction --------------------------------------------------
    def _make_plot(self):
        self.plot = pg.PlotWidget(title='skmap registers, a red ▲ marks a v_check failure')
        self.plot.showGrid(x=True, y=True)
        self.plot.setLabel('left', 'Value')
        self.plot.setLabel('bottom', 'Time', units='s')
        self.plot.addLegend(offset=(10, 10))
        # one hue per trace, so every signal gets its own color (the colors
        # stay fixed for the life of the plot, only the data scrolls)
        hues = max(len(self.traces), 3)
        for idx, trace in enumerate(self.traces):
            trace.curve = self.plot.plot([], [], name=trace.label,
                                         pen=pg.mkPen(pg.intColor(idx, hues=hues), width=2))
            # failing samples of this trace, always red on a black outline so
            # they stand out on any curve color, not added to the legend
            # (ScatterPlotItem without a name)
            trace.scatter = pg.ScatterPlotItem(symbol='t', size=10,
                                               brush=pg.mkBrush(220, 0, 0),
                                               pen=pg.mkPen('k', width=1))
            self.plot.addItem(trace.scatter)

    # -- sampling -------------------------------------------------------------
    def tick(self):
        """QTimer callback on the GUI thread, start one sample of every trace."""
        if self._inflight:
            logger.debug('previous sample still running, skipping this tick')
            return
        self._inflight = True
        asyncio.run_coroutine_threadsafe(self._sample_all(), self.loop)

    async def _sample_all(self):
        """Read every entry once on the io thread, then report to the GUI."""
        results = []
        for idx, trace in enumerate(self.traces):
            try:
                value, check_ok = await trace.sample()
                results.append((idx, value, check_ok, None))
            except Exception as e:                                # noqa: BLE001
                results.append((idx, 0.0, True, e))
        self.samples_ready.emit(results)

    def on_samples(self, results : list):
        """Signal handler on the GUI thread, update the curves."""
        self._inflight = False
        t = time.monotonic() - self.t0
        for idx, value, check_ok, error in results:
            trace = self.traces[idx]
            if error is not None:
                if not trace.read_error:
                    trace.read_error = True
                    logger.warning('reading %s failed: %r', trace.label, error)
                continue
            if trace.read_error:
                trace.read_error = False
                logger.info('reading %s works again', trace.label)
            trace.add_sample(t, value, check_ok, self.length)
            trace.curve.setData(trace.xs, trace.ys)
            trace.scatter.setData(trace.bad_xs, trace.bad_ys)
        # the ranges are set once, when the first samples arrive, they are
        # not rescaled after every update
        if not self._ranges_fixed:
            self._set_fixed_ranges()

    def _set_fixed_ranges(self):
        """Fix the axis ranges once, no rescaling afterwards.

        The time axis spans the whole `-l` sample window from t=0, the
        value axis the range of the samples seen so far. Waiting for the
        first plotted sample also disables pyqtgraph's auto range before
        any curve moves.
        """
        ys = [y for trace in self.traces for y in trace.ys]
        if not ys:
            return                          # wait for the first sample
        span = (self.length - 1) * self.period
        self.plot.setXRange(0, span * 1.04 + self.period, padding=0)
        lo, hi = min(ys), max(ys)
        if lo == hi:
            lo, hi = lo - 1, hi + 1
        self.plot.setYRange(lo, hi, padding=0.1)
        self._ranges_fixed = True

    def close(self):
        self.timer.stop()
        self.loop.call_soon_threadsafe(self.loop.stop)


# ---------------------------------------------------------------------------
# third party entry point


class SkmapUiPlotReg:
    """Register plot driven from a third party python application.

    The application imports the generated skmap modules it wants to
    access, makes the modules on any regio and hands the registers to
    plot to this class, then calls `run()` to open the window (which
    blocks until it is closed):

        import skmap
        from skmap_ui_plot_regs import SkmapUiPlotReg

        plot = SkmapUiPlotReg(period=0.5, length=200)
        plot.add_reg(module.temp)              # a scalar Reg
        plot.add_reg_vec_all(module.adc_vals)  # every element of a RegVec
        plot.add_reg_vec_idx(module.status, 2) # one element of a RegVec
        plot.run()

    The same sampling as the command line application is used: the
    `v_convert_rd` is applied, a failing `v_check` marks the sample in
    red and an `rc` register is cleared after it is read.
    """

    def __init__(self, period : float = 1.0, length : int = 100):
        self.traces : list[Trace] = []
        self.period = period              # sample period in seconds
        self.length = length              # number of samples per curve

    def add_reg(self, reg : skmap.Reg):
        """Add one scalar register (use the add_reg_vec_* for a RegVec)."""
        if isinstance(reg, skmap.RegVec):
            raise TypeError(f'"{reg.name}" is a RegVec, add it with '
                            'add_reg_vec_all() or add_reg_vec_idx()')
        self.traces.extend(checked_traces(reg.module, reg, [None]))

    def add_reg_vec_all(self, reg_vec : skmap.RegVec):
        """Add every element of a `RegVec`, one curve per element."""
        self.traces.extend(checked_traces(reg_vec.module, reg_vec,
                                          list(range(reg_vec.value_type.vec_len))))

    def add_reg_vec_idx(self, reg_vec : skmap.RegVec, idx : int):
        """Add one element of a `RegVec` by its index."""
        vec_len = reg_vec.value_type.vec_len
        if not 0 <= idx < vec_len:
            raise SystemExit(f'index {idx} out of range for the {vec_len} element '
                             f'vector "{reg_vec.name}" of module '
                             f'"{reg_vec.module.name()}"')
        self.traces.extend(checked_traces(reg_vec.module, reg_vec, [idx]))

    def run(self):
        """Open the plot window and block until it is closed (exit code)."""
        if not self.traces:
            raise SystemExit('SkmapUiPlotReg: no registers added, nothing to plot')
        return run_plot_app(self.traces, self.period, self.length, make_io_loop())

# ---------------------------------------------------------------------------
# application entry


def make_io_loop() -> asyncio.AbstractEventLoop:
    """A background asyncio loop for the regio access (the io loop).

    The regio (a possible TCP connection) is bound to the loop it is
    made on, so create it on the same background loop the plot samples
    on, the GUI runs on the Qt thread.
    """
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True,
                     name='skmap-plot-io').start()
    return loop


def run_plot_app(traces : list[Trace], period : float, length : int,
                 loop : asyncio.AbstractEventLoop) -> int:
    """Open the plot window for `traces`, block until it is closed."""
    pg.mkQApp('skmap_ui_plot_regs')
    pg.setConfigOption('antialias', True)
    gui = PlotApp(traces, period, length, loop)
    gui.plot.show()
    gui.tick()                          # the first sample, then the timer
    QtCore.QCoreApplication.instance().aboutToQuit.connect(gui.close)
    return exec_()


def main():
    args = parse_args()
    level = logging.WARNING
    if args.verbose == 1:
        level = logging.INFO
    elif args.verbose >= 2:
        level = logging.DEBUG
    logging.basicConfig(level=level)
    for module_spec in args.imports:
        import_generated_module(module_spec)

    loop = make_io_loop()
    traces = asyncio.run_coroutine_threadsafe(build_traces(args), loop).result()
    sys.exit(run_plot_app(traces, args.time, args.length, loop))


if __name__ == '__main__':
    main()
