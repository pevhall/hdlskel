project('hdlskel', 'cpp',
  default_options: ['cpp_std=c++20']
)

cli11_dep = dependency('CLI11')

cmake = import('cmake')
tabulate_sub = cmake.subproject('tabulate')
tabulate_dep = tabulate_sub.dependency('tabulate')

subdir('lib/cpp/regio')
subdir('lib/cpp/regio_tcp')
subdir('lib/cpp/skmap')
subdir('lib/cpp/skmap_autogen')
subdir('app/regio_tcp')
subdir('app/skmap')
