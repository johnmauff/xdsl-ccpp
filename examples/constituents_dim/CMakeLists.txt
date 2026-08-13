#------------------------------------------------------------------------------
#
# constituents_dim: ported from capgen-v1's own upstream
# end-to-end-tests/constituents_dim (feature/capgen-v1 branch) -- exercises a
# host-owned array dimensioned by the framework-injected constituent count
# (number_of_ccpp_constituents), a scheme (const_dim_producer) that takes
# that count directly as a scalar arg, and two SuiteOwned scratch vars
# (Case 2a/2b workspaces) plus a DDT-member tendency alias, all resolved
# without a host or module table ever declaring number_of_ccpp_constituents
# directly. See this directory's own README.md for capgen-v1's full
# description of what the test validates.
#
# Previously NOT add_subdirectory'd from the root CMakeLists.txt -- cap
# generation hard-failed on this example as ported. Fixed (2026-08-13),
# across four real xdsl_ccpp capability gaps found while porting this
# example, not vocabulary issues in this example's own .meta files (already
# clean v1 vocabulary, confirmed against real capgen-v1 upstream):
#
#   1. HostVariableMatchPass had no notion of a framework-injected scalar
#      standard_name with no host declaration at all
#      (number_of_ccpp_constituents) -- fixed via CCPP_FRAMEWORK_STD_NAMES /
#      FRAMEWORK_STD_NAME_TO_CAP_VAR (ccpp_conventions.py/cap_shared.py).
#   2. suite_cap.py's per-phase output-arg allocation tracked coverage by
#      literal local name ("errflg") instead of standard_name
#      (ccpp_error_code) -- a scheme naming its own arg "errcode" (as this
#      example's schemes do) got a second, spurious return value.
#   3. SuiteOwned scratch vars declared only in a scheme's own _run table
#      (never _init/_register) never got a LazyAllocOp at all.
#   4. A SuiteOwned var's allocation dimension declared only in a HOST-type
#      table (never a scheme's own arg or a MODULE-type table) had no
#      resolution path -- fixed by deriving it from an already in-scope
#      array's own shape (size()) instead, since HOST-type vars are
#      deliberately never use-associated anywhere in this codebase.
#
# main.F90 was rewritten to call xdsl_ccpp's own per-host-prefixed generated
# subroutine names (test_host_ccpp_physics_register/_initialize/
# _timestep_initial/_run/_timestep_final/_finalize,
# test_host_ccpp_register_constituents/_number_constituents/
# _initialize_constituents/_deallocate_dynamic_constituents) instead of
# capgen-v1's generic ccpp_register/ccpp_init/ccpp_physics_init/etc.
# dispatch convention -- same rationale as examples/var_compat/chunked_data's
# own test_host.F90/main.F90.
#
# ccpp_constituent_prop_mod.F90/ccpp_scheme_utils.F90 are NOT duplicated
# locally in this directory (unlike examples/advection's own copies, at
# least for now) -- this example links the single shared source in
# examples/shared/ instead (the ccpp_constituent_support target, built once
# at the root CMakeLists.txt level), added because this directory's own
# former local copy turned out to be missing diag_name, a real field/
# instantiate() argument register_consts.F90 (ported faithfully from real
# capgen-v1 upstream) genuinely needs. See examples/shared/
# ccpp_constituent_prop_mod.F90's own header comment for the full story and
# ccpp_cap_refactor_plan.md's backlog for the follow-up item tracking
# migration of every other still-duplicating example to this single source.
#
#------------------------------------------------------------------------------
set(SCHEME_FILES "register_consts" "const_dim_producer" "const_dim_consumer")
# "test_host" (the control->host-converted table) is metadata only -- its
# vars (col_start/col_end/errmsg/errcode) are plain arguments passed
# directly at each call site, never `use`-associated from a module, so
# there's no test_host.F90 to compile. Only "host_data" (which owns the
# real host state) needs a compiled Fortran counterpart -- same distinction
# examples/chunked_data/CMakeLists.txt makes for its own identical
# test_host.meta conversion.
set(HOST_FILES   "host_data")
set(SUITE_FILES  "constituents_dim_suite.xml")
set(HOST         "test_host")

set(CCPP_CAP_FILES "${CMAKE_CURRENT_BINARY_DIR}/ccpp")

list(TRANSFORM SCHEME_FILES APPEND ".F90"  OUTPUT_VARIABLE SCHEME_FORTRAN_FILES)
list(TRANSFORM SCHEME_FILES APPEND ".meta" OUTPUT_VARIABLE SCHEME_META_FILES)
list(TRANSFORM HOST_FILES   APPEND ".F90"  OUTPUT_VARIABLE CONSTITUENTS_DIM_HOST_FORTRAN_FILES)
list(TRANSFORM HOST_FILES   APPEND ".meta" OUTPUT_VARIABLE CONSTITUENTS_DIM_HOST_METADATA_FILES)
list(APPEND CONSTITUENTS_DIM_HOST_METADATA_FILES "${HOST}.meta")

xdsl_ccpp_capgen(HOSTFILES ${CONSTITUENTS_DIM_HOST_METADATA_FILES}
                 SCHEMEFILES ${SCHEME_META_FILES}
                 SUITES ${SUITE_FILES}
                 HOST_NAME ${HOST}
                 OUTPUT_ROOT "${CCPP_CAP_FILES}")
# CCPP_CAPS_LIST is now set (by xdsl_ccpp_capgen, in this scope) to the
# generated Fortran files (ccpp_kinds.F90, constituents_dim_suite_cap.F90,
# test_host_ccpp_cap.F90).

if(XDSL_CCPP_HAVE_FORTRAN)
  # Constituent-registration support (ccpp_constituent_prop_mod/
  # ccpp_scheme_utils) comes from the single shared source in
  # examples/shared/ (built once, at the root CMakeLists.txt level, as the
  # ccpp_constituent_support target) rather than a local per-example copy --
  # see examples/shared/ccpp_constituent_prop_mod.F90's own header comment.
  add_library(CONSTITUENTS_DIM_TESTLIB OBJECT ${SCHEME_FORTRAN_FILES}
                                               ${CONSTITUENTS_DIM_HOST_FORTRAN_FILES}
                                               ${CCPP_CAPS_LIST})
  set_target_properties(CONSTITUENTS_DIM_TESTLIB PROPERTIES Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/mod)
  target_include_directories(CONSTITUENTS_DIM_TESTLIB PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/mod)
  target_link_libraries(CONSTITUENTS_DIM_TESTLIB PRIVATE ccpp_constituent_support)

  add_executable(constituents_dim.exe main.F90)
  target_link_libraries(constituents_dim.exe PRIVATE CONSTITUENTS_DIM_TESTLIB ccpp_constituent_support)
  target_include_directories(constituents_dim.exe PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/mod)

  add_test(NAME ctest_constituents_dim COMMAND constituents_dim.exe)
  set_tests_properties(ctest_constituents_dim PROPERTIES PASS_REGULAR_EXPRESSION "PASS: constituents_dim")
endif()
