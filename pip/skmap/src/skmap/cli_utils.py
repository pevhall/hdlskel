import argparse
import logging
# import importlib
from typing import Optional

from regio.tcp import PORT_DEFAULT
from regio import RegioOptions
import regio.cli_utils

from skmap.basic import to_rich_str 
from .basic_types import Ass
from .module import make_module
from . import print_table_reg_list
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
    parser.add_argument(
        "-x", "--allow-unknowen",
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
        dest='verbose',
        action="count",
        default=0,
        help="Increase logging verbosity (repeat up to -vv)"
    )
    if return_parser:
        return parser

    args =  parser.parse_args()
    args.asserts_level = Ass.debug
    return args

async def make_module_from_args(args, read_tree = True, allow_unknowen = False, read_external_mem_cache = False):
    rio = await regio.cli_utils.make_regio_from_args(args)
    addr = 0
    if hasattr(args, 'addr'):
        addr = args.addr
    module = await make_module(rio, addr=addr, allow_unknowen=allow_unknowen)
    if read_tree:
        await module.read_all_tree(skip_self=True, read_external_mem_cache=read_external_mem_cache)
    return module

async def main(args):

    module = await make_module_from_args(args, args.tree, allow_unknowen=args.allow_unknowen)

    if (args.verbose == 0):
        level = logging.WARNING
    elif (args.verbose == 1):
        level = logging.INFO
    else:
        level = logging.DEBUG
    logging.basicConfig(level=level)

    if args.tree:
        await module.make_tree()
        module.print_tree_cached()

    if args.map:
        module.print_reg_map_cached()

    if args.asserts:
        list_reg = []
        if args.tree:
            ass = module.check_assert_tree_cached(args.asserts_level, list_reg)
        else:
            ass = module.check_assert_cached(args.asserts_level, list_reg)
        print_table_reg_list(list_reg, title=f'Asserts (max {to_rich_str(ass.to_str(), ass.color)})')

    if args.clear:
        if args.tree:
            print('Clearing all RC regs in tree')
            await module.clear_reg_rc_tree()
        else:
            print('Clearing all RC regs in module')
            await module.clear_reg_rc()

    if args.write:
        module.write_cache_tree_to_file(args.write)

