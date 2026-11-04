"""skmap_plot_regs — plot skmap ``var`` registers against time (pyqtgraph).

One curve per register (or ``RegVec`` element), each in its own color, with a
legend. Two ways to use it:

- the command line application (:func:`main`, console script
  ``skmap-plot-regs``, ``python3 -m skmap_plot_regs``), which takes the
  module base addresses and the register names to plot from them,
- from your own application, with the :class:`SkmapPlotRegs` class: import
  the generated skmap modules, make the modules and add registers to the
  plot, then call ``run()``.

Run the command line application against a regio TCP server::

    skmap-plot-regs -p 39601 -I recipe_test_bench_module.py 0 temp regs_rw

Or from your own application::

    import skmap
    from skmap_plot_regs import SkmapPlotRegs

    plot = SkmapPlotRegs(period=0.5, length=200)
    plot.add_reg(module.temp)              # a scalar Reg
    plot.add_reg_vec_all(module.adc_vals)  # every element of a RegVec
    plot.add_reg_vec_idx(module.status, 2) # one element of a RegVec
    plot.run()                             # opens the window, blocks

The same sampling behaviour is used both ways: a ``v_convert_rd`` is applied
(the value of the module user is plotted, not the raw register bits), a
``v_check`` failing on a sample marks it with a red triangle and an ``rc``
register is cleared after it is read.

The implementation is in :mod:`skmap_plot_regs.app`; this project is separate
from ``skmap`` so the skmap package itself does not depend on pyqtgraph.
"""

__version__ = "0.1.0"

from skmap_plot_regs.app import (
    LENGTH_MAX,
    LENGTH_MIN,
    PERIOD_MAX,
    PERIOD_MIN,
    SkmapPlotRegs,
    Trace,
    clamp_length,
    clamp_period,
    find_reg,
    import_generated_module,
    main,
    make_io_loop,
    make_traces,
    parse_reg_spec,
    parse_targets,
    trim_trace,
)

__all__ = [
    "SkmapPlotRegs",
    "Trace",
    "PERIOD_MIN",
    "PERIOD_MAX",
    "LENGTH_MIN",
    "LENGTH_MAX",
    "clamp_length",
    "clamp_period",
    "find_reg",
    "import_generated_module",
    "main",
    "make_io_loop",
    "make_traces",
    "parse_reg_spec",
    "parse_targets",
    "trim_trace",
    "__version__",
]
