# Library: hdlskel_skmap

hdlskel_skmap_inc = include_directories('include')

hdlskel_skmap_lib = library(
  'hdlskel_skmap',
  [
    './src/basic_types.cpp'
  , './src/head.cpp'
  , './src/reg.cpp'
  , './src/module.cpp'
  , './include/hdlskel/skmap/basic_types.hpp'
  , './include/hdlskel/skmap/head.hpp'
  , './include/hdlskel/skmap/reg.hpp'
  , './include/hdlskel/skmap/module.hpp'
  ],
  include_directories: hdlskel_skmap_inc,
  # dependencies: [hdlskel_regio_dep],
  dependencies: [hdlskel_regio_dep, tabulate_dep],
  install: false
)


hdlskel_skmap_dep = declare_dependency(
  include_directories: [hdlskel_skmap_inc, hdlskel_regio_inc],
  link_with: hdlskel_skmap_lib
)
