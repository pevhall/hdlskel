
# ----------------------------------------------------------------------
# executable: skmap
# ----------------------------------------------------------------------
add_executable(skmap
    main.cpp
)

# Link with every library/dependency listed in the Meson file
target_link_libraries(skmap PRIVATE
    hdlskel_skmap_autogen
    hdlskel_skmap
    hdlskel_regio_tcp
    hdlskel_regio
    CLI11::CLI11
    tabulate::tabulate
)

target_compile_features(skmap PUBLIC cxx_std_20)
