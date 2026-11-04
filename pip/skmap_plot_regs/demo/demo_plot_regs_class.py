#!/usr/bin/env python3
"""The skmap_plot_regs plot driven through the SkmapPlotRegs class.

The plot of demo_skmap_plot_regs_sim_cli.sh, but built the way a third
party application builds it: import the generated skmap module, make
the module on a regio and hand the registers to plot to the
SkmapPlotRegs class instead of naming them on a command line:

    python3 demo_plot_regs_class.py -p 39601 \\
        -I recipe_test_bench_module.py --addr 0 temp regs_rw

The regio (a possible TCP connection) is bound to the asyncio loop it
is made on, so the module is made on a background io loop
(make_io_loop) and that loop is handed to SkmapPlotRegs, which then
samples on it (the GUI runs on the Qt thread).

This is only a few lines of application code around the class; the
same can be written into any python script that has the generated
skmap module and a regio at hand.
"""

import argparse
import asyncio

import regio.cli_utils
import skmap
from skmap.module import make_module

import skmap_plot_regs as plot_regs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog='demo_plot_regs_class',
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    regio.cli_utils.add_parser_args(parser)
    parser.add_argument('-I', '--import', dest='imports', action='append',
                        default=[], metavar='MODULE|FILE.py',
                        help='import a generated skmap module (repeatable)')
    parser.add_argument('-a', '--addr', type=lambda s: int(s, 0), default=0,
                        metavar='ADDR', help='module base address (default: 0)')
    parser.add_argument('-t', '--time', type=float, default=1.0, metavar='SEC',
                        help='period between samples in seconds (default: 1)')
    parser.add_argument('-l', '--length', type=int, default=100, metavar='N',
                        help='plot length, number of samples (default: 100)')
    parser.add_argument('regs', nargs='+',
                        help='registers to plot, eg: temp regs_rw vec_foo[2]')
    return parser.parse_args()


async def make_plot(args : argparse.Namespace,
                    loop : asyncio.AbstractEventLoop) -> plot_regs.SkmapPlotRegs:
    """Make the module on the io loop and add the requested registers."""
    rio = await regio.cli_utils.make_regio_from_args(args)
    module = await make_module(rio, args.addr)
    print(f'module {module.name()} at 0x{module.base_addr:x}')

    plot = plot_regs.SkmapPlotRegs(period=args.time, length=args.length, loop=loop)
    for spec in args.regs:
        name, idx = plot_regs.parse_reg_spec(spec)
        reg = plot_regs.find_reg(module, name)
        if isinstance(reg, skmap.RegVec):
            if idx is None:
                plot.add_reg_vec_all(reg)      # every element of the vector
            else:
                plot.add_reg_vec_idx(reg, idx)  # one element of the vector
        else:
            plot.add_reg(reg)                   # a scalar register
    return plot


def main():
    args = parse_args()
    for module_spec in args.imports:
        plot_regs.import_generated_module(module_spec)

    # the regio must be made on the same background loop the plot samples on
    loop = plot_regs.make_io_loop()
    plot = asyncio.run_coroutine_threadsafe(make_plot(args, loop), loop).result()
    raise SystemExit(plot.run())          # opens the window, blocks until closed


if __name__ == '__main__':
    main()
