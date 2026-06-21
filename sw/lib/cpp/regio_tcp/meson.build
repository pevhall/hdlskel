# Library: hdlskel_regio_tcp

# project('hdlskel_regio_tcp', 'cpp',
#     default_options: ['cpp_std=c++20']
# )

hdlskel_regio_tcp_inc = include_directories('include')

# hdlskel_regio_dep = dependency('hdlskel_regio', fallback: ['hdlskel_regio', 'hdlskel_regio_dep'])

hdlskel_regio_tcp_lib = library(
  'hdlskel_regio_tcp',
  [
    'src/regio_tcp.cpp',
    'src/regio_tcp_client.cpp',
    'include/hdlskel/regio/tcp/regio_tcp.hpp',
    'include/hdlskel/regio/tcp/regio_tcp_client.hpp',
  ],
  include_directories: hdlskel_regio_tcp_inc,
  # dependencies: [hdlskel_regio_dep],
  dependencies: [hdlskel_regio_dep],
  install: false
)

hdlskel_regio_tcp_dep = declare_dependency(
  include_directories: [hdlskel_regio_tcp_inc, hdlskel_regio_inc],
  link_with: hdlskel_regio_tcp_lib
)
