#------------------------------------------------------------------------------
#
# ddthost: two-suite DDT (Fortran derived-type) example with two drivers --
# a Fortran host (ftn_host, both ddt_suite and temp_suite, six schemes) and
# a C++ host-model/chost driver (cxx_host, make_ddt only, exercising DDT
# flattening) -- similar in spirit to examples/kessler's multi-driver
# structure, but simpler: no numerical cross-driver comparison (each
# driver's own exit code is all that's checked, matching the existing
# Makefile's own `check` target) and no GPU/OpenACC support at all (no
# ARCH=GPU in the existing Makefile).
#
# Two separate cap-generation calls into two separate output directories,
# same rationale as examples/kessler's own plain/chost split: the two
# calls' outputs would otherwise collide in a single shared directory
# (harmless for the existing Makefile, which doesn't ask CMake to track
# custom-command outputs precisely, but not safe to rely on here).
#
# host_ccpp_ddt.meta (scheme/, type=ddt -- the ccpp_info_t DDT definition,
# not a host or scheme table) is passed as a HOSTFILE to both generation
# calls, matching the existing Makefile's own CAPS_HOSTS/CAPS_CHOST_HOSTS
# exactly.
#
#------------------------------------------------------------------------------

# ── Plain generation (Fortran host, both suites) ──────────────────────────
set(PLAIN_CAP_DIR "${CMAKE_CURRENT_BINARY_DIR}/plain")
xdsl_ccpp_capgen(HOSTFILES scheme/host_ccpp_ddt.meta host_ftn/test_host_data.meta
                           host_ftn/test_host_mod.meta host_ftn/test_host.meta
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

# ── Chost generation (C++ host, make_ddt only) ────────────────────────────
set(CHOST_CAP_DIR "${CMAKE_CURRENT_BINARY_DIR}/chost")
xdsl_ccpp_capgen(HOSTFILES host_cpp/ddthost_host_mod.meta host_cpp/ddthost_host_sub.meta
                           scheme/host_ccpp_ddt.meta
                 SCHEMEFILES scheme/make_ddt.meta
                 SUITES scheme/ddthost_suite.xml
                 OUTPUT_ROOT "${CHOST_CAP_DIR}")
set(CHOST_KINDS      "${CHOST_CAP_DIR}/ccpp_kinds.F90")
set(CHOST_SUITE_CAP  "${CHOST_CAP_DIR}/ddthost_suite_cap.F90")
set(CHOST_CHOST_CAP  "${CHOST_CAP_DIR}/Ddthost_ccpp_chost_cap.F90")
# CCPP_CAPS_LIST for this call also includes Ddthost_ccpp_cap.F90 (the
# plain non-chost cap xdsl_ccpp generates as a matter of course even in
# chost mode) -- not needed here and not compiled by the existing Makefile
# either, same situation as examples/tinyddt's own CMakeLists.txt.

# ── Pure-C++ partial verification (no Fortran compiler needed) ───────────
if(XDSL_CCPP_HAVE_CXX)
  add_library(ddthost_cxx_driver_check OBJECT
    ${CMAKE_CURRENT_SOURCE_DIR}/host_cpp/driver_ddthost_chost.cpp)
  target_include_directories(ddthost_cxx_driver_check PRIVATE ${CHOST_CAP_DIR})
endif()

# ── ddthost_ftn_host.exe (Fortran only) ───────────────────────────────────
if(XDSL_CCPP_HAVE_FORTRAN)
  add_executable(ddthost_ftn_host.exe
    ${PLAIN_KINDS}
    scheme/host_ccpp_ddt.F90
    host_ftn/test_host_data.F90
    host_ftn/test_host_mod.F90
    scheme/make_ddt.F90
    scheme/environ_conditions.F90
    scheme/setup_coeffs.F90
    scheme/temp_set.F90
    scheme/temp_calc_adjust.F90
    scheme/temp_adjust.F90
    ${PLAIN_DDT_CAP}
    ${PLAIN_TEMP_CAP}
    ${PLAIN_CCPP_CAP}
    host_ftn/test_host.F90
    host_ftn/test_ddt_host_integration.F90)
  set_target_properties(ddthost_ftn_host.exe PROPERTIES Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/mod_ftn)
  # test_utils.F90 here is byte-identical to examples/capgen/host_ftn/
  # test_utils.F90 (confirmed directly) -- link against the root
  # CMakeLists.txt's own shared `test_utils` target rather than recompiling
  # a second, separate copy of the same source.
  target_link_libraries(ddthost_ftn_host.exe PRIVATE test_utils)
  target_include_directories(ddthost_ftn_host.exe PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/mod_ftn)

  add_test(NAME ctest_ddthost_ftn_host COMMAND ddthost_ftn_host.exe)
endif()

# ── ddthost_cxx_host.exe (Fortran + C++) ──────────────────────────────────
if(XDSL_CCPP_HAVE_FORTRAN AND XDSL_CCPP_HAVE_CXX)
  add_executable(ddthost_cxx_host.exe
    ${CHOST_KINDS}
    scheme/host_ccpp_ddt.F90
    scheme/make_ddt.F90
    ${CHOST_SUITE_CAP}
    ${CHOST_CHOST_CAP}
    host_cpp/driver_ddthost_chost.cpp)
  set_target_properties(ddthost_cxx_host.exe PROPERTIES
    Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/mod_cxx
    # C++, not Fortran, as the linker -- see examples/tinyddt's own
    # CMakeLists.txt for the full rationale (identical here).
    LINKER_LANGUAGE CXX)
  target_include_directories(ddthost_cxx_host.exe PRIVATE
    ${CMAKE_CURRENT_BINARY_DIR}/mod_cxx
    ${CHOST_CAP_DIR})

  add_test(NAME ctest_ddthost_cxx_host COMMAND ddthost_cxx_host.exe)
endif()
