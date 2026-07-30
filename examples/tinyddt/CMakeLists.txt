#------------------------------------------------------------------------------
#
# tinyddt: a chost (C++ host) example with no upstream capgen-v1 equivalent
# (BIND(C)/C++-host support is a native xdsl_ccpp feature, not something
# ported from capgen-v1's own end-to-end-tests -- confirmed directly:
# reference/ccpp-framework has no matching test anywhere). Written from
# scratch for this file, unlike nested_suite/var_compat's CMakeLists.txt,
# which are close ports of a real upstream original.
#
# The C++ host owns all arrays -- host_cpp/tinyddt_host_mod.meta and
# host_cpp/tinyddt_host_sub.meta are metadata-only, describing the host's
# C++-side interface for cap-generation, with no corresponding Fortran
# source file to compile (see the existing Makefile's own "tinyddt_host_mod
# is NOT used here" comment).
# Host language (C++, BIND(C) chost cap generation) is auto-detected by
# xdsl_ccpp itself from host_cpp/tinyddt_host_mod.meta's own "language = c++"
# declaration (ccpp_dsl.py's _host_lang_cpp) -- no --bind-c flag needed,
# matching the existing Makefile's own CCPP_XDSL invocation exactly.
#
#------------------------------------------------------------------------------
set(CCPP_CAP_FILES "${CMAKE_CURRENT_BINARY_DIR}/bindc")

xdsl_ccpp_capgen(HOSTFILES host_cpp/tinyddt_host_mod.meta host_cpp/tinyddt_host_sub.meta
                 SCHEMEFILES tinyddt.meta
                 SUITES tinyddt_suite.xml
                 OUTPUT_ROOT "${CCPP_CAP_FILES}")
# host_cpp/tinyddt_host_mod.meta and host_cpp/tinyddt_host_sub.meta, not a
# top-level file of the same name -- a stale, unused duplicate of each used
# to live directly under examples/tinyddt/, missing "language = c++" and so
# never triggering BIND(C) generation, and has since been removed.
# host_cpp/'s copies are the ones the existing Makefile's own
# $(HOST_CPP)/tinyddt_host_mod.meta correctly points at.
# CCPP_CAPS_LIST is set but deliberately not used directly below: it also
# includes Tinyddt_ccpp_cap.F90, the plain (non-chost) cap xdsl_ccpp
# generates as a matter of course even in chost mode -- not needed here
# and not compiled by the existing Makefile either. Only the three files
# actually referenced below (ccpp_kinds.F90, tinyddt_suite_cap.F90,
# Tinyddt_ccpp_chost_cap.F90 -- the BIND(C) cap the C++ driver actually
# calls into) are used.

if(XDSL_CCPP_HAVE_CXX)
  # Compiles the generated C++ driver against the generated headers alone
  # -- confirms the chost header-generation output is at least valid C++
  # even without a Fortran compiler available to build the rest (this
  # sandbox has g++ but no gfortran, so this is real, if partial,
  # verification -- more than the pure-Fortran examples get here).
  add_library(tinyddt_cxx_driver_check OBJECT
    ${CMAKE_CURRENT_SOURCE_DIR}/host_cpp/driver_tinyddt_chost.cpp)
  target_include_directories(tinyddt_cxx_driver_check PRIVATE ${CCPP_CAP_FILES})
endif()

if(XDSL_CCPP_HAVE_FORTRAN AND XDSL_CCPP_HAVE_CXX)
  add_executable(tinyddt_cxx_host
    ${CCPP_CAP_FILES}/ccpp_kinds.F90
    ${CMAKE_CURRENT_SOURCE_DIR}/tinyddt.F90
    ${CCPP_CAP_FILES}/tinyddt_suite_cap.F90
    ${CCPP_CAP_FILES}/Tinyddt_ccpp_chost_cap.F90
    ${CMAKE_CURRENT_SOURCE_DIR}/host_cpp/driver_tinyddt_chost.cpp)
  set_target_properties(tinyddt_cxx_host PROPERTIES
    Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/mod
    # C++, not Fortran, as the linker -- driver_tinyddt_chost.cpp's own
    # main() drives the program. This sidesteps what the existing
    # Makefile has to do manually to make gfortran-as-final-linker work
    # (-nofor-main/-Mnomain to suppress Fortran's own default main(), and
    # -lstdc++ for the C++ runtime): CMake's Fortran/C++ mixed-language
    # linking support already adds the Fortran runtime library implicitly
    # once Fortran object files feed a C++-linked target, so neither is
    # needed here. CMake's own Fortran module dependency scanner also
    # orders ccpp_kinds.F90 -> tinyddt.F90 -> tinyddt_suite_cap.F90 ->
    # Tinyddt_ccpp_chost_cap.F90 automatically from each file's own
    # use/module statements -- the list order above doesn't need to be
    # (and isn't) a manually-maintained dependency chain the way the
    # existing Makefile's own prerequisite chain is.
    LINKER_LANGUAGE CXX)
  target_include_directories(tinyddt_cxx_host PRIVATE
    ${CMAKE_CURRENT_BINARY_DIR}/mod
    ${CCPP_CAP_FILES})

  add_test(NAME ctest_tinyddt_cxx_host COMMAND tinyddt_cxx_host)
endif()
