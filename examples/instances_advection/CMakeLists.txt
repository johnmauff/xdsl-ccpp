#------------------------------------------------------------------------------
#
# instances_advection: ported from capgen-v1's own upstream
# end-to-end-tests/instances_advection (feature/capgen-v1 branch) -- combines
# the instance_number/number_of_instances multi-instance pattern (see
# examples/instances) with host + scheme-registered constituents (boiled down
# from advection). Brought in on request to have the real source available
# for a later decision -- NOT confirmed working; see the hard failure below.
#
# main.meta's upstream `type = control` table converted to test_host.meta
# (type = host), same as every other port in this backlog section, keeping
# `instance`/`ninstances`/`lb`/`ub`/`errmsg`/`errcode` as protected host
# scalars (note this example uses `errcode`, not `errflg`, matching upstream
# exactly).
#
# Cap generation HARD FAILS -- confirmed by actually running it, not
# predicted:
#
#   xdsl.utils.exceptions.VerifyException: Expected source and destination
#   to have the same shape.
#     "memref.copy"(%9, %errmsg) : (memref<i32>, memref<512xi8>) -> ()
#
# an xDSL IR verifier crash inside the constituent-registration cap code path
# (visible in the dumped IR around test_host_ccpp_register_constituents /
# is_scheme_constituent). This is the same *class* of failure as the "third,
# previously-untracked gap" already noted under the `constituents_dim`
# backlog entry in ccpp_cap_refactor_plan.md (also a memref.copy shape
# mismatch, also inside a constituent-registration path) -- worth comparing
# the two once someone investigates, they may share one root cause. Not
# diagnosed further here. xdsl_ccpp_capgen() below calls message(FATAL_ERROR)
# on this failure, so this directory is deliberately NOT add_subdirectory'd
# from the root CMakeLists.txt -- doing so would abort the whole project's
# configure step. main.F90 is left as upstream's own unadapted
# generic-dispatch + per-instance-constituent-API driver (there was no point
# rewriting it against a cap that doesn't generate).
#
#------------------------------------------------------------------------------
set(SCHEME_FILES "cld_liq" "apply_constituent_tendencies")
set(HOST_FILES   "data" "test_host")
set(SUITE_FILES  "cld_suite.xml")
set(HOST         "test_host")

set(CCPP_CAP_FILES "${CMAKE_CURRENT_BINARY_DIR}/ccpp")

list(TRANSFORM SCHEME_FILES APPEND ".F90"  OUTPUT_VARIABLE SCHEME_FORTRAN_FILES)
list(TRANSFORM SCHEME_FILES APPEND ".meta" OUTPUT_VARIABLE SCHEME_META_FILES)
list(TRANSFORM HOST_FILES   APPEND ".F90"  OUTPUT_VARIABLE INSTANCES_ADVECTION_HOST_FORTRAN_FILES)
list(TRANSFORM HOST_FILES   APPEND ".meta" OUTPUT_VARIABLE INSTANCES_ADVECTION_HOST_METADATA_FILES)

# Known-failing (see header comment above) -- calling this will
# message(FATAL_ERROR) with an xDSL IR verifier crash in the
# constituent-registration cap code path.
xdsl_ccpp_capgen(HOSTFILES ${INSTANCES_ADVECTION_HOST_METADATA_FILES}
                 SCHEMEFILES ${SCHEME_META_FILES}
                 SUITES ${SUITE_FILES}
                 HOST_NAME ${HOST}
                 OUTPUT_ROOT "${CCPP_CAP_FILES}")
