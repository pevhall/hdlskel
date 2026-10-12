cmake_minimum_required(VERSION 3.16)

project(hdlskel LANGUAGES CXX)

# --------------------------------------------------------------
# Global C++20 configuration (must appear **before** any sub directory)
# --------------------------------------------------------------
# Force C++20 for the whole build tree, overriding any C++11 defaults
# that the third party sub projects might set.
set(CMAKE_CXX_STANDARD 20 CACHE STRING "C++ language standard" FORCE)
set(CMAKE_CXX_STANDARD_REQUIRED ON CACHE BOOL "Require the requested C++ standard" FORCE)

# --------------------------------------------------------------
# External dependencies (bundled sub projects)
# --------------------------------------------------------------
# Calling `meson setup builddir` will create these here
add_subdirectory(subprojects/CLI11-2.6.2)       # provides CLI11::CLI11
add_subdirectory(subprojects/tabulate-2.2)     # provides tabulate::tabulate

# --------------------------------------------------------------
# Add our own libraries / applications
# --------------------------------------------------------------
add_subdirectory(lib/cpp/regio)
add_subdirectory(lib/cpp/regio_tcp)
add_subdirectory(lib/cpp/skmap)
add_subdirectory(lib/cpp/skmap_autogen_test)

add_subdirectory(app/regio_tcp)
add_subdirectory(app/skmap)
