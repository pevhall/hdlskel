import argparse
# import importlib
from typing import Optional

from regio.tcp import PORT_DEFAULT
from regio import RegioOptions
import regio.cli_utils 
from .basic_types import Ass
from .module import make_module
from . import print_table_flags
from pathlib import Path


# def import_py_files( files : list[Path] ):
#     for f in files:
#         importlib.import_module(str(f))

def auto_int(s : str) -> int:
    return int(s, 0)

def parse_args(parser : Optional[argparse.ArgumentParser] = None, return_parser : bool = False):
    if parser is None:
        parser = argparse.ArgumentParser(
            prog="Skmap Utility",
            description="Interact with skamp regio server or cached skmap files"
        )

    regio.cli_utils.add_parser_args(parser)

    parser.add_argument(
        "-a", "--addr",
        type=auto_int,
        default=0,
        help="Regio Address" # (defaults to 0)"
    )

    parser.add_argument(
        "-m", "--map",
        action="store_true",
        help="Print SKMap reg map"
    )

    parser.add_argument(
        "-t", "--tree",
        action="store_true",
        help="Traverse tree"
    )

    parser.add_argument(
        "-s", "--asserts",
        action="store_true",
        help="print asserts"
    )
    # parser.add_argument(
    #     "-l", "--asserts-level",
    #     type=lambda x: Ass[x],
    #     default=Ass.info
    #     help="Level of asserts that are printed"
    # )

    parser.add_argument(
        "-c", "--clear",
        action="store_true",
        help="Clear all `read clear` registers"
    )

    parser.add_argument(
        "-w", "--write",
        type=str,
        help="If specified, write to cache file"
    )

    # -v, -vv, -vvv
    parser.add_argument(
        "-v",
        action="count",
        default=0,
        help="Increase logging verbosity (repeat up to -vvv)"
    )
    if return_parser:
        return parser

    args =  parser.parse_args()
    args.asserts_level = Ass.debug
    return args

async def main(args):

    regio_inst = await regio.cli_utils.make_regio_from_args(args)
    module = await make_module(regio_inst, addr=args.addr)

    if args.tree:
        await module.make_tree()
        module.print_tree_cached()

    if args.map:
        module.print_reg_map_cached()

    if args.asserts:
        flags = []
        ass = module.check_assert_tree_cached(args.asserts_level, flags)
        print(f'{ass=}, {len(flags)=}')
        print_table_flags(flags, title='Asserts')

    if args.clear:
        if args.tree:
            await module.clear_reg_rc_tree()
        else:
            await module.clear_reg_rc()

    if args.write:
        module.write_cache_tree_to_file(args.write)

