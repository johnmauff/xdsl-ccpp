#------------------------------------------------------------------------------
#
# instances: ported from capgen-v1's own upstream end-to-end-tests/instances
# (feature/capgen-v1 branch) -- exercises real capgen-v1's own explicit
# instance_number/number_of_instances multi-instance dispatch pattern: a
# HOST-owned array of DDT (`instance_data`, one entry per model instance),
# indexed at each call by an ordinary instance_number-standard-name scalar
# arg. xdsl-ccpp previously had a second, structurally different mechanism
# of its own (`ccpp_handle`/`num_instances`, an opaque handle type) for the
# same general idea; that was removed (Stage 1 of the "instances/
# instances_advection" backlog entry in ccpp_cap_refactor_plan.md) in favor
# of matching real capgen-v1's model directly (Stages 2-4, same entry) --
# this example now builds and runs against that real mechanism.
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
# main.F90's driver was adapted from real capgen-v1's own upstream driver to
# match xdsl-ccpp's actual generated calling convention -- see main.F90's
# own header comment for exactly what changed and why (in short: xdsl-ccpp's
# lifecycle still has 6 phases where capgen-v1 has 8, splitting
# "initialize"/"finalize" further into separate per-group physics_init/
# physics_final calls that don't exist here yet -- ccpp_cap_refactor_plan.md's
# "Full 6-phase to 8-phase lifecycle match" backlog entry, still open; same
# rationale as examples/opt_arg's and examples/chunked_data's own drivers).
# The loop-over-instances structure itself -- the actual mechanism under
# test -- is unchanged from upstream.
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

if(XDSL_CCPP_HAVE_FORTRAN)
  add_library(INSTANCES_TESTLIB OBJECT ${SCHEME_FORTRAN_FILES}
                                        ${INSTANCES_HOST_FORTRAN_FILES}
                                        ${CCPP_CAPS_LIST})
  set_target_properties(INSTANCES_TESTLIB PROPERTIES Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/mod)
  target_include_directories(INSTANCES_TESTLIB PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/mod)

  add_executable(instances.exe main.F90)
  target_link_libraries(instances.exe PRIVATE INSTANCES_TESTLIB)
  target_include_directories(instances.exe PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/mod)

  add_test(NAME ctest_instances COMMAND instances.exe)
endif()
