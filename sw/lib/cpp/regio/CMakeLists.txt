# ----------------------------------------------------------------------
# library: hdlskel_regio
# ----------------------------------------------------------------------
add_library(hdlskel_regio STATIC
    src/regio.cpp
    include/hdlskel/regio/regio.hpp
)

target_include_directories(hdlskel_regio PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}>            # <-- repository root
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>   # <-- original include dir
)

# Ensure C++20 for this target (required for <format>)
target_compile_features(hdlskel_regio PUBLIC cxx_std_20)

# Alias that mimics Meson’s declare_dependency
add_library(hdlskel_regio_dep ALIAS hdlskel_regio)
