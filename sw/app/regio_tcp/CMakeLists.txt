
# ----------------------------------------------------------------------
# executable: hdlskel_regio_tcp_op
# ----------------------------------------------------------------------
add_executable(hdlskel_regio_tcp_op
    main.cpp
)

# Link with the libraries the Meson executable required
target_link_libraries(hdlskel_regio_tcp_op PRIVATE
    hdlskel_regio_tcp
    hdlskel_regio
    CLI11::CLI11
)

target_compile_features(hdlskel_regio_tcp_op PUBLIC cxx_std_20)
