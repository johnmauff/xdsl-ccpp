#------------------------------------------------------------------------------
#
# instances: ported from capgen-v1's own upstream end-to-end-tests/instances
# (feature/capgen-v1 branch) -- exercises capgen-v1's own explicit
# instance_number/number_of_instances multi-instance dispatch pattern, an
# architecturally different model from xdsl-ccpp's existing ccpp_t-handle
# mechanism (see the "instances/instances_advection" backlog entry in
# ccpp_cap_refactor_plan.md for the full comparison). Brought in on request
# to have the real source available for a later decision, NOT because the
# mechanism is confirmed to work end-to-end yet -- see the caveat below.
#
# main.meta's upstream `type = control` table isn't a recognized xdsl-ccpp
# table type -- folded into test_host.meta (type = host), dropping
# suite_name/group_name/thread_num/nthreads/nphys_threads (unsupported
# generic-dispatch args, same conversion every other port in this backlog
# section needed), but this time KEEPING `instance`/`ninstances` as ordinary
# protected host scalars (standard_name instance_number/number_of_instances)
# -- unlike suite_name/group_name/etc, these two are exactly the mechanism
# under test, not dispatch plumbing to discard.
#
# Cap generation SUCCEEDS with this conversion -- but inspecting the
# generated output shows the actual per-instance DDT-array mechanism is NOT
# implemented: `instance_data` (the host's own `instance_type` array,
# dimensioned by number_of_instances) never appears anywhere in the
# generated Fortran at all. `data_array`/`data_array2`/`data_array_opt`
# (DDT members of `instance_type`) get resolved as ordinary top-level
# caller-supplied ("Block") arguments instead of being indexed through
# `instance_data(instance)%...` -- `instance` itself is accepted and
# forwarded to the scheme calls correctly, but nothing in the generated
# code ever uses it to select which instance's own storage to touch. A
# driver could still manually pass `instance_data(ins)%data_array(:,2)`
# etc. at each call (similar to how examples/chunked_data's driver manually
# slices by [lb,ub]) to recover real per-instance separation by hand -- but
# that's a workaround, not the automatic per-instance dispatch capgen-v1
# itself provides, and building it means taking a position on the open
# architecture question this backlog entry raises. main.F90 is left as
# upstream's own unadapted generic-dispatch driver for now, pending that
# decision -- not add_subdirectory'd from the root CMakeLists.txt.
#
#------------------------------------------------------------------------------
set(SCHEME_FILES "unit_conv_scheme_1" "unit_conv_scheme_2")
# "test_host" (the control->host-converted table) is metadata only -- its
# vars (lb/ub/errmsg/errflg/instance/ninstances) are plain arguments passed
# directly at each call site, never `use`-associated from a module, so
# there's no test_host.F90 to compile. Only "data" (which owns the real
# host state) needs a compiled Fortran counterpart -- same distinction
# examples/chunked_data/CMakeLists.txt makes for its own identical
# test_host.meta conversion.
set(HOST_FILES   "data")
set(SUITE_FILES  "suite_unit_conv_suite.xml")
set(HOST         "test_host")

set(CCPP_CAP_FILES "${CMAKE_CURRENT_BINARY_DIR}/ccpp")

list(TRANSFORM SCHEME_FILES APPEND ".F90"  OUTPUT_VARIABLE SCHEME_FORTRAN_FILES)
list(TRANSFORM SCHEME_FILES APPEND ".meta" OUTPUT_VARIABLE SCHEME_META_FILES)
list(TRANSFORM HOST_FILES   APPEND ".F90"  OUTPUT_VARIABLE INSTANCES_HOST_FORTRAN_FILES)
list(TRANSFORM HOST_FILES   APPEND ".meta" OUTPUT_VARIABLE INSTANCES_HOST_METADATA_FILES)
list(APPEND INSTANCES_HOST_METADATA_FILES "${HOST}.meta")

xdsl_ccpp_capgen(HOSTFILES ${INSTANCES_HOST_METADATA_FILES}
                 SCHEMEFILES ${SCHEME_META_FILES}
                 SUITES ${SUITE_FILES}
                 HOST_NAME ${HOST}
                 OUTPUT_ROOT "${CCPP_CAP_FILES}")
