#------------------------------------------------------------------------------
#
# capgen: two-suite DDT (Fortran derived-type) example with two drivers --
# a Fortran host (ftn_host, both ddt_suite and temp_suite, six schemes) and
# a C++ host-model/chost driver (cxx_host, its own capgen_chost_suite with
# three schemes: make_ddt, setup_coeffs, temp_calc_adjust). Same shape as
# examples/ddthost's own CMakeLists.txt (two separate cap-generation calls
# into two separate output directories, same rationale as that example's
# own comment on why -- see there for the full explanation), differing
# only in: no host_ccpp_ddt.meta DDT-table host file (this example has none
# at all), and the chost suite here uses three schemes rather than just
# one.
#
#------------------------------------------------------------------------------

# ── Plain generation (Fortran host, both suites) ──────────────────────────
set(PLAIN_CAP_DIR "${CMAKE_CURRENT_BINARY_DIR}/plain")
xdsl_ccpp_capgen(HOSTFILES host_ftn/test_host_data.meta host_ftn/test_host_mod.meta
                           host_ftn/test_host.meta
                 SCHEMEFILES scheme/make_ddt.meta scheme/environ_conditions.meta
                             scheme/setup_coeffs.meta scheme/temp_set.meta
                             scheme/temp_calc_adjust.meta scheme/temp_adjust.meta
                 SUITES scheme/ddt_suite.xml scheme/temp_suite.xml
                 HOST_NAME test_host
                 OUTPUT_ROOT "${PLAIN_CAP_DIR}")
set(PLAIN_KINDS       "${PLAIN_CAP_DIR}/ccpp_kinds.F90")
set(PLAIN_DDT_CAP     "${PLAIN_CAP_DIR}/ddt_suite_cap.F90")
set(PLAIN_TEMP_CAP    "${PLAIN_CAP_DIR}/temp_suite_cap.F90")
set(PLAIN_CCPP_CAP    "${PLAIN_CAP_DIR}/test_host_ccpp_cap.F90")

# ── Chost generation (C++ host, its own 3-scheme suite) ───────────────────
set(CHOST_CAP_DIR "${CMAKE_CURRENT_BINARY_DIR}/chost")
xdsl_ccpp_capgen(HOSTFILES host_cpp/capgen_host_mod.meta host_cpp/capgen_host_sub.meta
                 SCHEMEFILES scheme/make_ddt.meta scheme/setup_coeffs.meta
                             scheme/temp_calc_adjust.meta
                 SUITES scheme/capgen_chost_suite.xml
                 OUTPUT_ROOT "${CHOST_CAP_DIR}")
set(CHOST_KINDS      "${CHOST_CAP_DIR}/ccpp_kinds.F90")
set(CHOST_SUITE_CAP  "${CHOST_CAP_DIR}/capgen_chost_suite_cap.F90")
set(CHOST_CHOST_CAP  "${CHOST_CAP_DIR}/CapgenChost_ccpp_chost_cap.F90")
# CCPP_CAPS_LIST for this call also includes CapgenChost_ccpp_cap.F90 (the
# plain non-chost cap xdsl_ccpp generates as a matter of course even in
# chost mode) -- not needed here and not compiled by the existing Makefile
# either, same situation as examples/tinyddt's own CMakeLists.txt.

# ── Pure-C++ partial verification (no Fortran compiler needed) ───────────
if(XDSL_CCPP_HAVE_CXX)
  add_library(capgen_cxx_driver_check OBJECT
    ${CMAKE_CURRENT_SOURCE_DIR}/host_cpp/driver_capgen_chost.cpp)
  target_include_directories(capgen_cxx_driver_check PRIVATE ${CHOST_CAP_DIR})
endif()

# ── capgen_ftn_host.exe (Fortran only) ────────────────────────────────────
if(XDSL_CCPP_HAVE_FORTRAN)
  add_executable(capgen_ftn_host.exe
    ${PLAIN_KINDS}
    scheme/make_ddt.F90
    scheme/environ_conditions.F90
    scheme/setup_coeffs.F90
    scheme/temp_set.F90
    scheme/temp_calc_adjust.F90
    scheme/temp_adjust.F90
    host_ftn/test_host_data.F90
    host_ftn/test_host_mod.F90
    ${PLAIN_DDT_CAP}
    ${PLAIN_TEMP_CAP}
    ${PLAIN_CCPP_CAP}
    host_ftn/test_host.F90
    host_ftn/test_capgen_host_integration.F90)
  set_target_properties(capgen_ftn_host.exe PROPERTIES Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/mod_ftn)
  # host_ftn/test_utils.F90 here IS the canonical file the root
  # CMakeLists.txt's own shared `test_utils` target is built from
  # (examples/capgen/host_ftn/test_utils.F90) -- link against that target
  # directly rather than recompiling it as a second source in this list.
  target_link_libraries(capgen_ftn_host.exe PRIVATE test_utils)
  target_include_directories(capgen_ftn_host.exe PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/mod_ftn)

  add_test(NAME ctest_capgen_ftn_host COMMAND capgen_ftn_host.exe)
endif()

# ── capgen_cxx_host.exe (Fortran + C++) ───────────────────────────────────
if(XDSL_CCPP_HAVE_FORTRAN AND XDSL_CCPP_HAVE_CXX)
  add_executable(capgen_cxx_host.exe
    ${CHOST_KINDS}
    scheme/make_ddt.F90
    scheme/setup_coeffs.F90
    scheme/temp_calc_adjust.F90
    ${CHOST_SUITE_CAP}
    ${CHOST_CHOST_CAP}
    host_cpp/driver_capgen_chost.cpp)
  set_target_properties(capgen_cxx_host.exe PROPERTIES
    Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/mod_cxx
    # C++, not Fortran, as the linker -- see examples/tinyddt's own
    # CMakeLists.txt for the full rationale (identical here).
    LINKER_LANGUAGE CXX)
  target_include_directories(capgen_cxx_host.exe PRIVATE
    ${CMAKE_CURRENT_BINARY_DIR}/mod_cxx
    ${CHOST_CAP_DIR})

  add_test(NAME ctest_capgen_cxx_host COMMAND capgen_cxx_host.exe)
endif()
