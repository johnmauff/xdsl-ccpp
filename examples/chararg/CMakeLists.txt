#------------------------------------------------------------------------------
#
# chararg: a chost (C++ host) example exercising a character(len=N) scalar
# argument -- same pattern as examples/tinyddt's own CMakeLists.txt, with
# one difference: HOST_NAME must be passed explicitly ("chararg_host_sub"),
# matching the existing Makefile's own CCPP_XDSL invocation exactly --
# without it, the generated cap names would derive from the suite name
# instead ("Chararg_ccpp_chost_cap.F90" etc.), not matching what the
# Makefile's own CHOST_F90/CHOST_HDR/CHOST_HPP variables expect
# ("chararg_host_sub_ccpp_chost_cap.F90" etc.).
#
#------------------------------------------------------------------------------
set(CCPP_CAP_FILES "${CMAKE_CURRENT_BINARY_DIR}/bindc")

xdsl_ccpp_capgen(HOSTFILES host_cpp/chararg_host_mod.meta host_cpp/chararg_host_sub.meta
                 SCHEMEFILES chararg.meta
                 SUITES chararg_suite.xml
                 HOST_NAME chararg_host_sub
                 OUTPUT_ROOT "${CCPP_CAP_FILES}")
# CCPP_CAPS_LIST is set but deliberately not used directly below -- see
# examples/tinyddt's own CMakeLists.txt for why (it also includes the
# plain, non-chost cap, unused here).

if(XDSL_CCPP_HAVE_CXX)
  add_library(chararg_cxx_driver_check OBJECT
    ${CMAKE_CURRENT_SOURCE_DIR}/host_cpp/driver_chararg_chost.cpp)
  target_include_directories(chararg_cxx_driver_check PRIVATE ${CCPP_CAP_FILES})
endif()

if(XDSL_CCPP_HAVE_FORTRAN AND XDSL_CCPP_HAVE_CXX)
  add_executable(chararg_cxx_host
    ${CCPP_CAP_FILES}/ccpp_kinds.F90
    ${CMAKE_CURRENT_SOURCE_DIR}/chararg.F90
    ${CCPP_CAP_FILES}/chararg_suite_cap.F90
    ${CCPP_CAP_FILES}/chararg_host_sub_ccpp_chost_cap.F90
    ${CMAKE_CURRENT_SOURCE_DIR}/host_cpp/driver_chararg_chost.cpp)
  set_target_properties(chararg_cxx_host PROPERTIES
    Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/mod
    LINKER_LANGUAGE CXX)
  target_include_directories(chararg_cxx_host PRIVATE
    ${CMAKE_CURRENT_BINARY_DIR}/mod
    ${CCPP_CAP_FILES})

  add_test(NAME ctest_chararg_cxx_host COMMAND chararg_cxx_host)
endif()
