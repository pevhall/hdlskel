from pathlib import Path

import skmap
from hdldepends import analyse
from hdlworkflow import HdlWorkflow


script_dir = Path(__file__).resolve().parent

module_recipe = script_dir / 'test_skmap_tree_module.toml'
skmap.generate_vhdl_module(module_recipe, script_dir/'test_skmap_tree_module.vhd')
skmap.generate_py_module(module_recipe, script_dir/'test_skmap_tree_module.py')

top_entity = 'test_skmap_tree_top'
dep = analyse(config_files ='hdldepends.toml', top_entity=top_entity) #doesn't work
compile_order = dep.to_dict()['files']
# print(f'{compile_order=}')
# print(f'{script_dir=}')

sim = HdlWorkflow(
    eda_tool = "nvc",
    top = top_entity,
    path_to_working_directory = script_dir/'build',
    compile_order = compile_order,
    generics = [
        'RAMFACE_ADDR_W=30',
        'RAMFACE_DATA_W=32',
        'SKMAP_BYTE_ALIGN=1',
        'TREE_DEPTH=6',
        'TREE_WIDTH=5',
    ],
    libraries = 'hdlskel',
    cocotb=f'test_skmap_tree',
    pythonpaths=[script_dir]
)   
sim.run()
