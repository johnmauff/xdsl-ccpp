#------------------------------------------------------------------------------
#
# instances_advection: ported from capgen-v1's own upstream
# end-to-end-tests/instances_advection (feature/capgen-v1 branch) -- combines
# the instance_number/number_of_instances multi-instance pattern (see
# examples/instances) with host + scheme-registered constituents (boiled
# down from advection).
#
# main.meta's upstream `type = control` table converted to test_host.meta
# (type = host), same as every other port in this backlog section, keeping
# `instance`/`ninstances`/`lb`/`ub`/`errmsg`/`errcode` as protected host
# scalars (note the .meta files use `errcode`, not `errflg`, matching
# upstream exactly -- the generated Fortran signatures still use `errflg`,
# the CCPP standard local name; main.F90's own header comment covers this).
#
# Cap generation used to hard fail here with an xDSL IR verifier crash
# (`memref.copy`, shape mismatch) inside the constituent-registration cap
# code -- confirmed fixed as an incidental side effect of the 5-stage
# multi-instance migration (ccpp_cap_refactor_plan.md's "instances/
# instances_advection" entry) once re-tested, not by anything targeted at
# it. What was still missing after that: the constituent-registration API
# itself (constituent_cap.py) had zero instance-awareness -- every
# constituent-API subroutine shared one flat set of module-level arrays,
# with no way to know which model instance a given call was for. Fixed
# (task #35, same backlog entry): a new per-instance bundle derived type
# (test_host_lc_instance_t) collects every constituent-API-owned array into
# one allocatable lc_instances(:) array, lazily allocated + sized by
# number_of_instances inside register_constituents (the one entry point the
# driver always calls first, with ninstances); every constituent-API
# subroutine gained an `instance` dummy argument indexing into it. Gated on
# the host declaring instance_number at all, so every OTHER
# constituent-using example (advection, constituents_dim, capgen, ddthost)
# is completely unaffected -- confirmed via the full existing test suite,
# 0 regressions.
#
#------------------------------------------------------------------------------
set(SCHEME_FILES "cld_liq" "apply_constituent_tendencies")
# "test_host" (the control->host-converted table) is metadata only -- its
# vars are plain arguments passed directly at each call site, never
# `use`-associated from a module, so there's no test_host.F90 to compile.
# Only "data" (which owns the real host state) needs a compiled Fortran
# counterpart -- same distinction examples/chunked_data/CMakeLists.txt and
# examples/instances/CMakeLists.txt make for their own identical
# test_host.meta conversion.
set(HOST_FILES   "data")
set(SUITE_FILES  "cld_suite.xml")
set(HOST         "test_host")

set(CCPP_CAP_FILES "${CMAKE_CURRENT_BINARY_DIR}/ccpp")

list(TRANSFORM SCHEME_FILES APPEND ".F90"  OUTPUT_VARIABLE SCHEME_FORTRAN_FILES)
list(TRANSFORM SCHEME_FILES APPEND ".meta" OUTPUT_VARIABLE SCHEME_META_FILES)
list(TRANSFORM HOST_FILES   APPEND ".F90"  OUTPUT_VARIABLE INSTANCES_ADVECTION_HOST_FORTRAN_FILES)
list(TRANSFORM HOST_FILES   APPEND ".meta" OUTPUT_VARIABLE INSTANCES_ADVECTION_HOST_METADATA_FILES)
list(APPEND INSTANCES_ADVECTION_HOST_METADATA_FILES "${HOST}.meta")

xdsl_ccpp_capgen(HOSTFILES ${INSTANCES_ADVECTION_HOST_METADATA_FILES}
                 SCHEMEFILES ${SCHEME_META_FILES}
                 SUITES ${SUITE_FILES}
                 HOST_NAME ${HOST}
                 OUTPUT_ROOT "${CCPP_CAP_FILES}")

if(XDSL_CCPP_HAVE_FORTRAN)
  # Needs the shared constituent-registration support stub (same reason
  # examples/advection's own TESTLIB does) -- cld_liq/apply_constituent_
  # tendencies both use ccpp_constituent_properties_t/ccpp_scheme_utils.
  add_library(INSTANCES_ADVECTION_TESTLIB OBJECT ${SCHEME_FORTRAN_FILES}
                                        ${INSTANCES_ADVECTION_HOST_FORTRAN_FILES}
                                        ${CMAKE_SOURCE_DIR}/examples/shared/ccpp_constituent_prop_mod.F90
                                        ${CMAKE_SOURCE_DIR}/examples/shared/ccpp_scheme_utils.F90
                                        ${CCPP_CAPS_LIST})
  set_target_properties(INSTANCES_ADVECTION_TESTLIB PROPERTIES Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/mod)
  target_include_directories(INSTANCES_ADVECTION_TESTLIB PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/mod)

  add_executable(instances_advection.exe main.F90)
  target_link_libraries(instances_advection.exe PRIVATE INSTANCES_ADVECTION_TESTLIB)
  target_include_directories(instances_advection.exe PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/mod)

  add_test(NAME ctest_instances_advection COMMAND instances_advection.exe)
endif()
