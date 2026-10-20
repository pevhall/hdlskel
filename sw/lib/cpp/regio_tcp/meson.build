# Library: hdlskel_regio_tcp

hdlskel_regio_tcp_inc = include_directories('include')

hdlskel_regio_tcp_lib = library(
  'hdlskel_regio_tcp',
  [
    'src/regio_tcp.cpp',
    'src/regio_tcp_client.cpp',
    'src/regio_cli_utils.cpp',
    'include/hdlskel/regio/tcp/regio_tcp.hpp',
    'include/hdlskel/regio/tcp/regio_tcp_client.hpp',
    'include/hdlskel/regio/tcp/regio_cli_utils.hpp',
  ],
  include_directories: hdlskel_regio_tcp_inc,
  dependencies: [hdlskel_regio_dep, cli11_dep],
  install: false
)

hdlskel_regio_tcp_dep = declare_dependency(
  include_directories: [hdlskel_regio_tcp_inc, hdlskel_regio_inc],
  link_with: hdlskel_regio_tcp_lib
)
