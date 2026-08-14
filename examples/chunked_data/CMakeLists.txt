#------------------------------------------------------------------------------
#
# chunked_data: single-scheme example exercising capgen-v1's chunked/sliced
# horizontal-range dispatch -- the run phase is called once per chunk with a
# different lb/ub range each time. Ported from capgen-v1's own upstream
# end-to-end-tests/chunked_data/CMakeLists.txt (see
# https://github.com/NCAR/ccpp-framework, feature/capgen-v1 branch, for the
# original).
#
# main.meta's own upstream `type = control` table isn't a recognized
# xdsl-ccpp table type (only scheme/module/ddt/host) -- converted to
# `type = host` here (as test_host.meta) and trimmed to just the
# horizontal_loop_begin/end pair + errmsg/errflg, dropping suite_name/
# group_name/thread_num/nthreads/nphys_threads (capgen-v1's own generic
# multi-threaded dispatch convention, which xdsl-ccpp's generated caps don't
# support) -- same conversion examples/var_compat's test_host.meta already
# needed for the identical upstream pattern.
#
# main.F90's driver was rewritten to call xdsl-ccpp's own generated
# subroutine names (ccpp_register/ccpp_init/ccpp_physics_timestep_init/
# ccpp_physics_run/ccpp_physics_timestep_final/ccpp_final -- bare,
# capgen-v1-style names since the vocabulary-resolution redesign's Stage 5,
# ccpp_cap_refactor_plan.md) rather than capgen-v1's own generic
# ccpp_register/ccpp_init/ccpp_physics_init/etc dispatch convention, since
# xdsl-ccpp's lifecycle still has 6 phases where capgen-v1 has 8 (splitting
# "initialize"/"finalize" further) -- same rationale as
# examples/var_compat's test_host.F90.
#
#------------------------------------------------------------------------------

set(SCHEME_FILES "chunked_data_scheme")
# "test_host" (the control->host-converted table, see below) is metadata
# only -- its vars (lb/ub/errmsg/errflg) are plain arguments passed directly
# at each call site in main.F90, never `use`-associated from a module, so
# there's no test_host.F90 to compile (unlike examples/var_compat's own
# test_host.meta, whose vars ARE use-associated and so DOES have a paired
# test_host.F90). Only "data" (which owns the real chunked_data_instance
# derived-type object) needs a compiled Fortran counterpart.
set(HOST_FILES   "data")
set(SUITE_FILES  "suite_chunked_data_suite.xml")
set(HOST         "test_host")

set(CCPP_CAP_FILES "${CMAKE_CURRENT_BINARY_DIR}/ccpp")

list(TRANSFORM SCHEME_FILES APPEND ".F90"  OUTPUT_VARIABLE SCHEME_FORTRAN_FILES)
list(TRANSFORM SCHEME_FILES APPEND ".meta" OUTPUT_VARIABLE SCHEME_META_FILES)
list(TRANSFORM HOST_FILES   APPEND ".F90"  OUTPUT_VARIABLE CHUNKED_DATA_HOST_FORTRAN_FILES)
list(TRANSFORM HOST_FILES   APPEND ".meta" OUTPUT_VARIABLE CHUNKED_DATA_HOST_METADATA_FILES)
list(APPEND CHUNKED_DATA_HOST_METADATA_FILES "${HOST}.meta")

xdsl_ccpp_capgen(HOSTFILES ${CHUNKED_DATA_HOST_METADATA_FILES}
                 SCHEMEFILES ${SCHEME_META_FILES}
                 SUITES ${SUITE_FILES}
                 HOST_NAME ${HOST}
                 OUTPUT_ROOT "${CCPP_CAP_FILES}")
# CCPP_CAPS_LIST is now set (by xdsl_ccpp_capgen, in this scope) to the
# generated Fortran files (chunked_data_suite_cap.F90, test_host_ccpp_cap.F90
# -- no ccpp_kinds.F90 here, since this example has no kind_phys reals at all).

if(XDSL_CCPP_HAVE_FORTRAN)
  add_library(CHUNKED_DATA_TESTLIB OBJECT ${SCHEME_FORTRAN_FILES}
                                           ${CHUNKED_DATA_HOST_FORTRAN_FILES}
                                           ${CCPP_CAPS_LIST})
  set_target_properties(CHUNKED_DATA_TESTLIB PROPERTIES Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/mod)
  target_include_directories(CHUNKED_DATA_TESTLIB PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/mod)

  add_executable(chunked_data.exe main.F90)
  target_link_libraries(chunked_data.exe PRIVATE CHUNKED_DATA_TESTLIB)
  target_include_directories(chunked_data.exe PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/mod)

  add_test(NAME ctest_chunked_data COMMAND chunked_data.exe)
  set_tests_properties(ctest_chunked_data PROPERTIES PASS_REGULAR_EXPRESSION "TEST PASSED")
endif()
