# ----------------------------------------------------------------------
# C++ unit tests (mirrors sw/test/meson.build)
#
#   ctest --test-dir <build dir>
# ----------------------------------------------------------------------

# Recipe `check` option (ValueCheck), runs against a cached regio file
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
