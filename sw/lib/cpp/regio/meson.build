# Library: regio

# project('hdlskel_regio', 'cpp',
#     default_options: ['cpp_std=c++20']
# )

hdlskel_regio_inc = include_directories('include')

hdlskel_regio_lib = library(
  'regio',
  [
    'src/regio.cpp',
    'include/hdlskel/regio/regio.hpp',
  ],
  include_directories: hdlskel_regio_inc,
  install: false
)

hdlskel_regio_dep = declare_dependency(
  include_directories: hdlskel_regio_inc,
  link_with: hdlskel_regio_lib
)
