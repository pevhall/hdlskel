# ----------------------------------------------------------------------
# C++ unit tests (mirrors sw/test/meson.build)
#
#   ctest --test-dir <build dir>
# ----------------------------------------------------------------------

# Recipe `v_check` / `v_convert` options (ValueCheck / ValueConvert),
# runs against a cached regio file (a captured image of the recipe test bench)
add_executable(test_skmap_check
    test_skmap_check.cpp
)

target_link_libraries(test_skmap_check PRIVATE
    hdlskel_skmap_autogen
    hdlskel_skmap
    hdlskel_regio
)

target_compile_features(test_skmap_check PUBLIC cxx_std_20)

add_test(
    NAME skmap_check
    COMMAND test_skmap_check ${CMAKE_CURRENT_SOURCE_DIR}/../../test/data/test_recipe.skmap
)

# Hermetic regression of the apps against the captured regio images (the same
# test meson registers as 'skmap_file'). The script finds the repo itself, it
# only needs to be told where this build put its binaries.
add_test(
    NAME skmap_file
    COMMAND ${CMAKE_CURRENT_SOURCE_DIR}/test_skmap_file.sh
)
set_tests_properties(skmap_file PROPERTIES
    ENVIRONMENT "HDSKEL_BUILD_DIR=${CMAKE_BINARY_DIR}"
)
