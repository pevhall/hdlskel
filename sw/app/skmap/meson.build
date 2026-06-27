# Executable: hdlskel_regio_tcp_op

# project('regio_tcp', 'cpp',
#   default_options: ['cpp_std=c++20']
# )

# Bring in regio_tcp (which itself brings in regio)
# hdlskel_regio_tcp_dep = dependency('hdlskel_regio_tcp', fallback: ['hdlskel_regio_tcp', 'hdlskel_regio_tcp_dep'])

executable(
  'skmap',
  'main.cpp',
  dependencies: [hdlskel_skmap_dep, hdlskel_regio_tcp_dep, hdlskel_regio_dep, cli11_dep, tabulate_dep],
  install: false
)
