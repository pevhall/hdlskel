
# ----------------------------------------------------------------------
# library: hdlskel_skmap (uses regio & tabulate)
# ----------------------------------------------------------------------
add_library(hdlskel_skmap STATIC
    src/basic_types.cpp
    src/head.cpp
    src/reg.cpp
    src/module.cpp
    src/external_mem.cpp
    include/hdlskel/skmap/basic_types.hpp
    include/hdlskel/skmap/head.hpp
    include/hdlskel/skmap/reg.hpp
    include/hdlskel/skmap/module.hpp
    include/hdlskel/skmap/external_mem.hpp
    include/hdlskel/skmap/recipe_functions.hpp
    include/hdlskel/skmap/version.hpp
)

target_include_directories(hdlskel_skmap PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}>
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)

target_compile_features(hdlskel_skmap PUBLIC cxx_std_20)

# Link with regio library and tabulate (external)
target_link_libraries(hdlskel_skmap PUBLIC
    hdlskel_regio
   tabulate::tabulate
)

# Alias that matches the Meson dependency name
add_library(hdlskel_skmap_dep ALIAS hdlskel_skmap)
