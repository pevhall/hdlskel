# Library: hdlskel_skmap

hdlskel_skmap_autogen_inc = include_directories('include')

hdlskel_skmap_autogen_lib = library(
  'hdlskel_skmap_autogen',
  [
    'include/hdlskel/skmap/autogen/recipe_test_bench_module.hpp',
    'src/recipe_test_bench_module.cpp'
  ],
  include_directories: [hdlskel_skmap_autogen_inc, hdlskel_skmap_inc],
  # dependencies: [hdlskel_regio_dep],
  dependencies: [hdlskel_skmap_dep, hdlskel_regio_dep, tabulate_dep],
  install: false
)


hdlskel_skmap_autogen_dep = declare_dependency(
  include_directories: [hdlskel_skmap_autogen_inc, hdlskel_skmap_inc, hdlskel_regio_inc],
  link_with: hdlskel_skmap_autogen_lib
)
