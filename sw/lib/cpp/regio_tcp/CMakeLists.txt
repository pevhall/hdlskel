
# ----------------------------------------------------------------------
# library: hdlskel_regio_tcp (depends on regio)
# ----------------------------------------------------------------------
add_library(hdlskel_regio_tcp STATIC
    src/regio_tcp.cpp
    src/regio_tcp_client.cpp
    src/regio_cli_utils.cpp
    include/hdlskel/regio/tcp/regio_tcp.hpp
    include/hdlskel/regio/tcp/regio_tcp_client.hpp
    include/hdlskel/regio/tcp/regio_cli_utils.hpp
)

target_include_directories(hdlskel_regio_tcp PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}>
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
)

target_compile_features(hdlskel_regio_tcp PUBLIC cxx_std_20)

# Link against the core regio library
target_link_libraries(hdlskel_regio_tcp PUBLIC hdlskel_regio CLI11::CLI11)

# Alias for consistency with Meson’s declared dependency
add_library(hdlskel_regio_tcp_dep ALIAS hdlskel_regio_tcp)
