import argparse
from pathlib import Path

import skmap
from hdldepends import analyse
from hdlworkflow import HdlWorkflow

def parse_args():
    parser = argparse.ArgumentParser(
        prog="Skmap Utility",
        description="Interact with skamp regio server or cached skmap files"
    )

    parser.add_argument(
        "-g", "--gui",
        action="store_true",
        help="Run GUI"
    )

    parser.add_argument(
        "-s", "--server",
        action="store_true",
        help="Run Regio Server"
    )
    return parser.parse_args()

args = parse_args()

script_dir = Path(__file__).resolve().parent

module_recipe = script_dir / 'test_skmap_tree_module.toml'
skmap.generate_vhdl_module(module_recipe, script_dir/'test_skmap_tree_module.vhd')
skmap.generate_py_module(module_recipe, script_dir/'test_skmap_tree_module.py')

top_entity = 'test_skmap_tree_top'
dep = analyse(config_files ='hdldepends.toml', top_entity=top_entity)
compile_order = dep.to_dict()['files']
# print(f'{compile_order=}')
# print(f'{script_dir=}')

run_server = args.server
sim = HdlWorkflow(
    eda_tool = "nvc",
    top = top_entity,
    path_to_working_directory = script_dir/'build',
    compile_order = compile_order,
    gui = args.gui,
    plusargs = [f"{run_server=}"],
    generics = [
        'RAMFACE_ADDR_W=30',
        'RAMFACE_DATA_W=32',
        'SKMAP_BYTE_ALIGN=1',
        'TREE_DEPTH=3',
        'TREE_WIDTH=2',
        # 'TREE_DEPTH=16',
        # 'TREE_WIDTH=15',
    ],
    libraries = 'hdlskel',
    cocotb=f'test_skmap_tree',
    pythonpaths=[script_dir]
)
sim.run()
