# ----------------------------------------------------------------------
# executable: regio_op (C++ mirror of pip/regio/src/regio_op.py)
# ----------------------------------------------------------------------
add_executable(regio_op
    main.cpp
)

# Link with the libraries the Meson executable required
target_link_libraries(regio_op PRIVATE
    hdlskel_regio_tcp
    hdlskel_regio
    CLI11::CLI11
)

target_compile_features(regio_op PUBLIC cxx_std_20)
