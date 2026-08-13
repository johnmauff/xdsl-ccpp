#------------------------------------------------------------------------------
#
# opt_arg: ported from capgen-v1's own upstream end-to-end-tests/opt_arg
# (feature/capgen-v1 branch) -- exercises the `active = <flag>` optional-
# argument mechanism (opt_var/opt_var_2 only meaningful when the host's
# flag_for_opt_arg is true) and a kind_phys override via KIND_MAP.
#
# main.meta's upstream `type = control` table isn't a recognized xdsl-ccpp
# table type (only scheme/module/ddt/host) -- folded into test_host.meta
# (type = host), dropping suite_name/group_name/thread_num/nthreads/
# nphys_threads (unsupported generic-dispatch args), matching
# examples/var_compat's own test_host.meta port exactly.
#
# The driver was rewritten from upstream's own generic ccpp_register/
# ccpp_init/ccpp_physics_init/... calling convention (module test_host_ccpp_cap
# in capgen-v1's own framework) to xdsl-ccpp's per-host-prefixed generated
# subroutine names (test_host_ccpp_physics_register/_initialize/
# _timestep_initial/_run/_timestep_final/_finalize), matching
# examples/var_compat/test_host.F90's own calling convention.
#
#------------------------------------------------------------------------------
set(SCHEME_FILES "opt_arg_scheme")
# "test_host" (the control->host-converted table) is metadata only -- its
# vars (lb/ub/errmsg/errflg) are plain arguments passed directly at each
# call site, never `use`-associated from a module, so there's no
# test_host.F90 to compile. Only "data" (which owns the real host state)
# needs a compiled Fortran counterpart -- same distinction
# examples/chunked_data/CMakeLists.txt makes for its own identical
# test_host.meta conversion.
set(HOST_FILES   "data")
set(SUITE_FILES  "suite_opt_arg_suite.xml")
set(HOST         "test_host")

set(CCPP_CAP_FILES "${CMAKE_CURRENT_BINARY_DIR}/ccpp")

list(TRANSFORM SCHEME_FILES APPEND ".F90"  OUTPUT_VARIABLE SCHEME_FORTRAN_FILES)
list(TRANSFORM SCHEME_FILES APPEND ".meta" OUTPUT_VARIABLE SCHEME_META_FILES)
list(TRANSFORM HOST_FILES   APPEND ".F90"  OUTPUT_VARIABLE OPT_ARG_HOST_FORTRAN_FILES)
list(TRANSFORM HOST_FILES   APPEND ".meta" OUTPUT_VARIABLE OPT_ARG_HOST_METADATA_FILES)
list(APPEND OPT_ARG_HOST_METADATA_FILES "${HOST}.meta")

xdsl_ccpp_capgen(HOSTFILES ${OPT_ARG_HOST_METADATA_FILES}
                 SCHEMEFILES ${SCHEME_META_FILES}
                 SUITES ${SUITE_FILES}
                 HOST_NAME ${HOST}
                 KIND_MAP "kind_phys:REAL32"
                 OUTPUT_ROOT "${CCPP_CAP_FILES}")

if(XDSL_CCPP_HAVE_FORTRAN)
  add_library(OPT_ARG_TESTLIB OBJECT ${SCHEME_FORTRAN_FILES}
                                      ${OPT_ARG_HOST_FORTRAN_FILES}
                                      ${CCPP_CAPS_LIST})
  set_target_properties(OPT_ARG_TESTLIB PROPERTIES Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/mod)
  target_include_directories(OPT_ARG_TESTLIB PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/mod)

  add_executable(opt_arg_host_integration test_opt_arg_host_integration.F90)
  target_link_libraries(opt_arg_host_integration PRIVATE OPT_ARG_TESTLIB)
  target_include_directories(opt_arg_host_integration PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/mod)

  # Both bugs originally found in this port are now fixed (see
  # ccpp_cap_refactor_plan.md's "opt_arg's dead active property" entry):
  # `active = flag_for_opt_arg` now correctly gates opt_var/opt_var_2's
  # allocation/marshaling/call behind an ActiveCheckOp, and
  # test_host_ccpp_physics_timestep_initial/_timestep_final now receive
  # nx/std_arg/opt_arg/opt_arg_2 as real dummy arguments (passed through
  # from this driver) instead of disconnected local placeholders. A CI
  # compile then caught a real gfortran type mismatch this laptop's lack
  # of a Fortran compiler couldn't: `flag_for_opt_arg` is itself threaded
  # as a genuine dummy argument on test_host_ccpp_physics_timestep_initial/
  # _timestep_final/_run (the active-expression HOST-type-propagation fix,
  # see ccpp_cap_refactor_plan.md's CI-confirmed follow-on entry), and this
  # driver's own positional calls hadn't been updated to pass it -- fixed
  # in test_opt_arg_host_integration.F90. Confirmed by direct inspection of
  # the generated Fortran signatures; not yet compile/run-verified on this
  # laptop (no Fortran compiler available) -- CI is the first real
  # compile+run check.
  add_test(NAME ctest_opt_arg_host_integration COMMAND opt_arg_host_integration)
endif()
