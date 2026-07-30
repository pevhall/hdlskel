from hdldepends import analyse, output
from hdlworkflow import HdlWorkflow
from pathlib import Path

gui        : bool = True
script_dir = Path(__file__).resolve().parent

name = 'tb_skmap_module_basic'
top_entity = name
top_file = script_dir / f'{name}.vhd'
dep = analyse(config_files ='hdldepends.toml', top_file=top_file) #doesn't work
dep.print_compile_order()
compile_order = dep.to_dict()['files']
if 0:
    with open('compile_order.txt', 'w') as f:
        for c in compile_order:
            f.write(c['path']+'\n')


if 1:
    sim = HdlWorkflow(
        eda_tool = "nvc",
        stop_time = (1000, 'ns'),
        top = top_entity,
        path_to_working_directory = script_dir/'build',
        compile_order = compile_order,
        gui = gui,
        libraries = 'hdlskel',
    )
    sim.run()
