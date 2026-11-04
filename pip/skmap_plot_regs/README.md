# skmap-plot-regs

Plot skmap `var` registers against time with pyqtgraph: one curve per
register (or `RegVec` element), each in its own color, with a legend.
It is the `skmap_plot_regs` package (`src/skmap_plot_regs/`, the layout of
the other `pip/` projects: `app.py` is the implementation, `__main__.py`
allows `python3 -m skmap_plot_regs`) and can be used two ways: as a
command line application or, from a third party python application,
through the `SkmapPlotRegs` class.

Sampling behaviour (both uses):

  * a `v_convert_rd` is applied: the plot shows the value of the module
    user, not the raw bits of the register
  * a `v_check` failing on a sample marks that sample with a red triangle
  * an `rc` register is cleared (a zero is written back) after it is read
  * a `rw`, `wt` or `k` register gives a warning (plotting them is usually
    not what you want)
  * the axis ranges are fixed when the first samples arrive, they are not
    rescaled after every update
  * while the plot runs, the option row above it changes the two plot
    settings live: **Update rate (sample period)** — the period between
    samples in seconds — and **Points** — the number of samples kept
    per curve (shortening it drops the oldest samples immediately, and
    the time axis keeps spanning `points x period`). Both are clamped to
    the range the option row allows: `0.01 .. 3600` seconds and
    `1 .. 1000000` points, `-t` / `-l` and the `SkmapPlotRegs`
    constructor are clamped to it as well (a clamped value is logged)

## Install

```bash
# siblings first (they live in this repo's pip/ dir)
pip install ../regio ../skmap
pip install -e .[dev]              # or: pip install pip/skmap_plot_regs
```

## Command line

Give one or more modules as a base address followed by the register
names to plot from that module; a `RegVec` element is selected with
square brackets (`vec_foo_bar[2]`), a `RegVec` without an index plots
every element:

```bash
python3 -m skmap_plot_regs -p 39601 -I <generated_module>.py \
    0 temp regs_rw            # <addr> <reg> [reg vec[idx] ...], repeatable

# example: -t 0.5 (sample every 0.5 s), -l 200 (keep 200 samples)
python3 -m skmap_plot_regs -t 0.5 -l 200 -p 39601 -I module.py 0 temp
```

or, when installed, `skmap-plot-regs [options] <addr> <reg> ...`.

## Use from your own application (`SkmapPlotRegs`)

Import the generated skmap modules you want to access, make the
modules and add registers to the plot:

```python
import skmap
from skmap_plot_regs import SkmapPlotRegs

plot = SkmapPlotRegs(period=0.5, length=200)   # sample period / window
plot.add_reg(module.temp)              # a scalar Reg
plot.add_reg_vec_all(module.adc_vals)  # every element of a RegVec
plot.add_reg_vec_idx(module.status, 2) # one element of a RegVec
plot.run()                             # opens the window, blocks
```

A regio lives on the asyncio loop it was made on; when the modules
were made over a TCP regio on a background loop, pass that loop to the
constructor (`SkmapPlotRegs(loop=loop)`, see `make_io_loop`) so the
plot samples on it.

## Demos (`demo/`)

Both scripts start the cocotb recipe testbench
(`fw/tb/skmap/tb_py_skmap_module_recipe`, build it once first), a
headless `regio_ui` proxy (`pip/regio/src/regio_proxy_headless.py`,
the simulation's regio server takes only one client), the plot of
`temp` and every lane of `regs_rw`, and the `skmap_ui` TUI in the
foreground: edit a value in the TUI and watch the plot curve move.

```bash
cd demo
bash demo_skmap_plot_regs_sim_cli.sh      # plot via the command line app
bash demo_skmap_plot_regs_sim_class.sh    # same plot via SkmapPlotRegs
```

`demo_plot_regs_class.py` is the small third party style application
the class demo runs: it shows the few lines of code needed to build
the plot through `SkmapPlotRegs` (`add_reg`, `add_reg_vec_all`,
`add_reg_vec_idx` and `run`).

Both scripts first require `SIM_PORT` and `PROXY_PORT` to be free: a
leftover simulation or proxy (for instance of the previous run) would
answer instead of the ones the demo starts, and the plot and the TUI
would talk to another design.

## Tests

```bash
python3 -m pytest pip/skmap_plot_regs/tests -q
```
