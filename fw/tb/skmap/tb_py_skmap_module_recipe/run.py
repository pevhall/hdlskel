from pathlib import Path

import skmap
import argparse
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
run_server = args.server
gui        = args.gui


script_dir = Path(__file__).resolve().parent

name = 'recipe_test_bench_module'
module_recipe = script_dir / f'{name}.toml'

if 1:
    skmap.generate_vhdl_module(module_recipe, script_dir/f'{name}.vhd')
    skmap.generate_py_module(module_recipe, script_dir/f'{name}.py')
if 0:
    import sys
    sys.exit()

top_entity = name
dep = analyse(config_files ='hdldepends.toml', top_entity=top_entity) #doesn't work
compile_order = dep.to_dict()['files']
# print(f'{compile_order=}')
# print(f'{script_dir=}')

sim = HdlWorkflow(
    eda_tool = "nvc",
    top = top_entity,
    path_to_working_directory = script_dir/'build',
    compile_order = compile_order,
    gui = gui,
    wave = 'surfer',
    plusargs = [f"{run_server=}"],
    generics = [
           "BASE_ADDR=0" ,
           "RAMFACE_ADDR_W=12" ,
           "RAMFACE_DATA_W=32" ,
           "RO_LEN=3" ,
           "RO_VAL_W=12" ,
           "RW_LEN=3" ,
           "RW_VAL_W=12" ,
           "MEM_RW_VAL_W=32",
           "MEM_RW_LEN=32",
           "MEM_RW_LATENCY=1",
           "MEM_RO_WIDTH=32",
           "MEM_RO_ADDR_W=3",
           "MEM_RO_LATENCY=1",
           "FLAGK1=false" ,
           "FLAGK2=true" ,
           "SKMAP_BYTE_ALIGN=4",
           "REGS_WT_INIT=15",
    ],
    libraries = 'hdlskel',
    cocotb=f'test_skmap_module_recipe',
    pythonpaths=[script_dir]
)
sim.run()

