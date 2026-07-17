from pathlib import Path

import skmap
from hdldepends import analyse
from hdlworkflow import HdlWorkflow

gui        : bool = False
run_server : bool = False

script_dir = Path(__file__).resolve().parent

name = 'recipe_test_bench_module'
module_recipe = script_dir / f'{name}.toml'
if 1:
    skmap.generate_vhdl_module(module_recipe, script_dir/f'{name}.vhd')
    skmap.generate_py_module(module_recipe, script_dir/f'{name}.py')

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
    plusargs = [f"{run_server=}"],
    generics = [
           "BASE_ADDR=0" ,
           "RAMFACE_ADDR_W=8" ,
           "RAMFACE_DATA_W=32" ,
           "RO_LEN=3" ,
           "RO_VAL_W=12" ,
           "RW_LEN=3" ,
           "RW_VAL_W=12" ,
           "FLAGK1=false" ,
           "FLAGK2=true" ,
           "SKMAP_BYTE_ALIGN=4",
    ],
    libraries = 'hdlskel',
    cocotb=f'test_skmap_module_recipe',
    pythonpaths=[script_dir]
)   
sim.run()

