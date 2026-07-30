#------------------------------------------------------------------------------
#
# constprop: a chost (C++ host) example exercising constituent DDT array
# support -- same pattern as examples/constadv's own CMakeLists.txt
# (explicit HOST_NAME "constprop_host_sub", matching the existing
# Makefile's own CCPP_XDSL invocation, plus the same extra compiled source:
# ccpp_constituent_prop_mod.F90, a stub for the CCPP framework's
# constituent-properties module, at the top level of this directory, not
# host_cpp/ -- see the existing Makefile's own CXX_HOST_OBJS list, which
# compiles it before constprop.F90).
#
#------------------------------------------------------------------------------
set(CCPP_CAP_FILES "${CMAKE_CURRENT_BINARY_DIR}/bindc")

xdsl_ccpp_capgen(HOSTFILES host_cpp/constprop_host_mod.meta host_cpp/constprop_host_sub.meta
                 SCHEMEFILES constprop.meta
                 SUITES constprop_suite.xml
                 HOST_NAME constprop_host_sub
                 OUTPUT_ROOT "${CCPP_CAP_FILES}")
# CCPP_CAPS_LIST is set but deliberately not used directly below -- see
# examples/tinyddt's own CMakeLists.txt for why (it also includes the
# plain, non-chost cap, unused here).

if(XDSL_CCPP_HAVE_CXX)
  add_library(constprop_cxx_driver_check OBJECT
    ${CMAKE_CURRENT_SOURCE_DIR}/host_cpp/driver_constprop_chost.cpp)
  target_include_directories(constprop_cxx_driver_check PRIVATE ${CCPP_CAP_FILES})
endif()

if(XDSL_CCPP_HAVE_FORTRAN AND XDSL_CCPP_HAVE_CXX)
  add_executable(constprop_cxx_host
    ${CCPP_CAP_FILES}/ccpp_kinds.F90
    ${CMAKE_CURRENT_SOURCE_DIR}/ccpp_constituent_prop_mod.F90
    ${CMAKE_CURRENT_SOURCE_DIR}/constprop.F90
    ${CCPP_CAP_FILES}/constprop_suite_cap.F90
    ${CCPP_CAP_FILES}/constprop_host_sub_ccpp_chost_cap.F90
    ${CMAKE_CURRENT_SOURCE_DIR}/host_cpp/driver_constprop_chost.cpp)
  set_target_properties(constprop_cxx_host PROPERTIES
    Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/mod
    LINKER_LANGUAGE CXX)
  target_include_directories(constprop_cxx_host PRIVATE
    ${CMAKE_CURRENT_BINARY_DIR}/mod
    ${CCPP_CAP_FILES})

  add_test(NAME ctest_constprop_cxx_host COMMAND constprop_cxx_host)
endif()
