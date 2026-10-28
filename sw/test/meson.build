# ----------------------------------------------------------------------
# C++ tests (also runnable directly from the build directory, see the header of
# each source)
#
# Run all of them with:  meson test -C build
# ----------------------------------------------------------------------

# Recipe `v_check` / `v_convert` options (ValueCheck / ValueConvert), runs
# against a cached regio file (a captured image of the recipe test bench)
test('skmap_check', executable(
  'test_skmap_check',
  'test_skmap_check.cpp',
  dependencies: [hdlskel_skmap_autogen_dep, hdlskel_skmap_dep, hdlskel_regio_dep],
  install: false
  ),
  # the image path is relative to the build directory, which meson uses as cwd
  args : ['../../test/data/test_recipe.skmap'],
)

# Hermetic regression of the apps against the same captured regio images
# (regio cache file, module tree, unknown modules, clearing, python output
# parity). The script finds the repo root itself, no simulation is needed.
test('skmap_file', find_program('test_skmap_file.sh'),
  depends : [skmap_app, regio_op_app],
)
