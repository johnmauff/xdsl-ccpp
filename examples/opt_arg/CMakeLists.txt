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
# The driver calls the generated subroutines directly (module test_host_ccpp_cap,
# matching examples/var_compat/test_host.F90's own calling convention). Since the
# vocabulary-resolution redesign's Stage 5 (ccpp_cap_refactor_plan.md), these are
# bare, capgen-v1-style names (ccpp_register/ccpp_init/ccpp_physics_timestep_init/
# ccpp_physics_run/ccpp_physics_timestep_final/ccpp_final) rather than
# host-prefixed ones -- xdsl-ccpp's own 6-phase lifecycle structure is unchanged,
# only the naming; see the redesign's own backlog entry for the still-open
# 6-phase vs. capgen-v1's 8-phase question.
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
  # ccpp_physics_timestep_init/_timestep_final now receive
  # nx/std_arg/opt_arg/opt_arg_2 as real dummy arguments (passed through
  # from this driver) instead of disconnected local placeholders.
  # `flag_for_opt_arg` itself is no longer threaded as a dummy argument at
  # all -- the vocabulary-resolution redesign's Stage 2a (same doc)
  # resolves it via use-association instead, matching real capgen-v1's own
  # approach, so this driver only needs to `use`-associate and set it, not
  # pass it through any call. CI-verified green (compile+run) -- this
  # laptop has no Fortran compiler to check locally.
  add_test(NAME ctest_opt_arg_host_integration COMMAND opt_arg_host_integration)
endif()
