#------------------------------------------------------------------------------
#
# constadv: a chost (C++ host) example exercising a rank-3 constituent
# array -- same pattern as examples/chararg's own CMakeLists.txt (explicit
# HOST_NAME "constadv_host_sub", matching the existing Makefile's own
# CCPP_XDSL invocation), plus one extra compiled source this example's own
# scheme needs: ccpp_constituent_prop_mod.F90 (a stub for the CCPP
# framework's constituent-properties module, defined at the top level of
# this directory, not host_cpp/ -- see the existing Makefile's own
# CXX_HOST_OBJS list, which compiles it before constadv.F90).
#
#------------------------------------------------------------------------------
set(CCPP_CAP_FILES "${CMAKE_CURRENT_BINARY_DIR}/bindc")

xdsl_ccpp_capgen(HOSTFILES host_cpp/constadv_host_mod.meta host_cpp/constadv_host_sub.meta
                 SCHEMEFILES constadv.meta
                 SUITES constadv_suite.xml
                 HOST_NAME constadv_host_sub
                 OUTPUT_ROOT "${CCPP_CAP_FILES}")
# CCPP_CAPS_LIST is set but deliberately not used directly below -- see
# examples/tinyddt's own CMakeLists.txt for why (it also includes the
# plain, non-chost cap, unused here).

if(XDSL_CCPP_HAVE_CXX)
  add_library(constadv_cxx_driver_check OBJECT
    ${CMAKE_CURRENT_SOURCE_DIR}/host_cpp/driver_constadv_chost.cpp)
  target_include_directories(constadv_cxx_driver_check PRIVATE ${CCPP_CAP_FILES})
endif()

if(XDSL_CCPP_HAVE_FORTRAN AND XDSL_CCPP_HAVE_CXX)
  add_executable(constadv_cxx_host
    ${CCPP_CAP_FILES}/ccpp_kinds.F90
    ${CMAKE_CURRENT_SOURCE_DIR}/ccpp_constituent_prop_mod.F90
    ${CMAKE_CURRENT_SOURCE_DIR}/constadv.F90
    ${CCPP_CAP_FILES}/constadv_suite_cap.F90
    ${CCPP_CAP_FILES}/constadv_host_sub_ccpp_chost_cap.F90
    ${CMAKE_CURRENT_SOURCE_DIR}/host_cpp/driver_constadv_chost.cpp)
  set_target_properties(constadv_cxx_host PROPERTIES
    Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/mod
    LINKER_LANGUAGE CXX)
  target_include_directories(constadv_cxx_host PRIVATE
    ${CMAKE_CURRENT_BINARY_DIR}/mod
    ${CCPP_CAP_FILES})

  add_test(NAME ctest_constadv_cxx_host COMMAND constadv_cxx_host)
endif()
