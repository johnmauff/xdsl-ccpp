#------------------------------------------------------------------------------
#
# nestedddt: a chost (C++ host) example exercising nested-DDT flattening --
# same structure as examples/tinyddt's own CMakeLists.txt, patterned
# directly on it (no upstream capgen-v1 end-to-end-tests example exercises
# chost generation either, so this is written from scratch, not ported from
# a real upstream original). No --host-name override needed -- the
# generated cap names (Nestedddt_ccpp_chost_cap.F90 etc.) are derived from
# the suite name, matching the existing Makefile's own CCPP_XDSL invocation
# (which also passes no --host-name).
#
#------------------------------------------------------------------------------
set(CCPP_CAP_FILES "${CMAKE_CURRENT_BINARY_DIR}/bindc")

xdsl_ccpp_capgen(HOSTFILES host_cpp/nestedddt_host_mod.meta host_cpp/nestedddt_host_sub.meta
                 SCHEMEFILES nestedddt.meta
                 SUITES nestedddt_suite.xml
                 OUTPUT_ROOT "${CCPP_CAP_FILES}")
# CCPP_CAPS_LIST is set but deliberately not used directly below: it also
# includes Nestedddt_ccpp_cap.F90, the plain (non-chost) cap xdsl_ccpp
# generates as a matter of course even in chost mode -- not needed here
# and not compiled by the existing Makefile either (same situation as
# examples/tinyddt's own CMakeLists.txt).

if(XDSL_CCPP_HAVE_CXX)
  # Compiles the generated C++ driver against the generated headers alone
  # -- confirms the chost header-generation output is at least valid C++
  # even without a Fortran compiler available to build the rest.
  add_library(nestedddt_cxx_driver_check OBJECT
    ${CMAKE_CURRENT_SOURCE_DIR}/host_cpp/driver_nestedddt_chost.cpp)
  target_include_directories(nestedddt_cxx_driver_check PRIVATE ${CCPP_CAP_FILES})
endif()

if(XDSL_CCPP_HAVE_FORTRAN AND XDSL_CCPP_HAVE_CXX)
  add_executable(nestedddt_cxx_host
    ${CCPP_CAP_FILES}/ccpp_kinds.F90
    ${CMAKE_CURRENT_SOURCE_DIR}/nestedddt.F90
    ${CCPP_CAP_FILES}/nestedddt_suite_cap.F90
    ${CCPP_CAP_FILES}/Nestedddt_ccpp_chost_cap.F90
    ${CMAKE_CURRENT_SOURCE_DIR}/host_cpp/driver_nestedddt_chost.cpp)
  set_target_properties(nestedddt_cxx_host PROPERTIES
    Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/mod
    # C++, not Fortran, as the linker -- see examples/tinyddt's own
    # CMakeLists.txt for the full rationale (identical here).
    LINKER_LANGUAGE CXX)
  target_include_directories(nestedddt_cxx_host PRIVATE
    ${CMAKE_CURRENT_BINARY_DIR}/mod
    ${CCPP_CAP_FILES})

  add_test(NAME ctest_nestedddt_cxx_host COMMAND nestedddt_cxx_host)
endif()
