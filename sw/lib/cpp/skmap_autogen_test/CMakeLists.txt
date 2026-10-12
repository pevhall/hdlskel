
# ----------------------------------------------------------------------
# library: hdlskel_skmap_autogen (autogen test helpers)
# ----------------------------------------------------------------------
add_library(hdlskel_skmap_autogen STATIC
    include/hdlskel/skmap/autogen_test/recipe_test_bench_module.hpp
    src/recipe_test_bench_module.cpp
    include/hdlskel/skmap/autogen_test/test_skmap_tree_module.hpp
    src/test_skmap_tree_module.cpp
)

# Public include directories needed by users of this library
target_include_directories(hdlskel_skmap_autogen PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}>
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/../skmap>
)

# Dependencies: skmap, regio and tabulate (just like the Meson file)
target_link_libraries(hdlskel_skmap_autogen
    PUBLIC
        hdlskel_skmap
        hdlskel_regio
        tabulate::tabulate
)

target_compile_features(hdlskel_skmap_autogen PUBLIC cxx_std_20)

# Alias for the Meson style dependency name
# add_library(hdlskel_skmap_autogen_dep ALIAS hdlskel_skmap_autogen)
