cmake_minimum_required(VERSION 3.16)

project(hdlskel LANGUAGES CXX)

# C++ unit tests (sw/test), see ctest
enable_testing()

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

# The tabulate wrap directory name carries its version, so pick up whatever
# version meson fetched instead of hardcoding one.
file(GLOB tabulate_subdirs RELATIVE ${CMAKE_CURRENT_SOURCE_DIR}/subprojects
     ${CMAKE_CURRENT_SOURCE_DIR}/subprojects/tabulate-*)
list(LENGTH tabulate_subdirs num_tabulate_subdirs)
if(num_tabulate_subdirs EQUAL 0)
    message(FATAL_ERROR
        "subprojects/tabulate-* not found. Run `meson setup <builddir>` in sw/ first "
        "to download the wraps.")
endif()
list(SORT tabulate_subdirs ORDER DESCENDING)
list(GET tabulate_subdirs 0 tabulate_subdir)
add_subdirectory(subprojects/${tabulate_subdir})   # provides tabulate::tabulate

# --------------------------------------------------------------
# Add our own libraries / applications
# --------------------------------------------------------------
add_subdirectory(lib/cpp/regio)
add_subdirectory(lib/cpp/regio_tcp)
add_subdirectory(lib/cpp/skmap)
add_subdirectory(lib/cpp/skmap_autogen_test)

add_subdirectory(app/regio_op)
add_subdirectory(app/skmap)
add_subdirectory(test)
