#------------------------------------------------------------------------------
#
# constituents_dim: ported from capgen-v1's own upstream
# end-to-end-tests/constituents_dim (feature/capgen-v1 branch) -- exercises a
# host-owned array dimensioned by the framework-injected constituent count
# (number_of_ccpp_constituents) and a scheme (const_dim_producer) that takes
# that count directly as a scalar arg. See this directory's own README.md for
# capgen-v1's full description of what the test validates.
#
# NOT add_subdirectory'd from the root CMakeLists.txt -- xdsl_ccpp's own cap
# generation hard-fails on this example as ported, confirmed by actually
# running it (not just predicted by reading the source):
#
#   ValueError: Host model variable matching/compatibility failed:
#     Scheme 'const_dim_producer': argument 'n_const'
#     (standard_name='number_of_ccpp_constituents') has no matching host
#     model variable
#
# raised from HostVariableMatchPass._match_and_validate()
# (xdsl_ccpp/transforms/host_var_match_pass.py). xdsl_ccpp_capgen() below
# calls message(FATAL_ERROR) on any nonzero cap-generation exit code, so
# add_subdirectory'ing this directory from the root CMakeLists.txt would
# abort the ENTIRE project's cmake configure step, not just this example --
# left out of the root CMakeLists.txt's add_subdirectory list for that
# reason. See the "capgen-v1 end-to-end-tests capability gaps" backlog in
# ccpp_cap_refactor_plan.md for the full write-up.
#
# main.F90 is still upstream's own generic-dispatch driver, UNADAPTED to
# xdsl_ccpp's per-host-prefixed calling convention (unlike every other ported
# example) -- there was no point rewriting a driver for a cap that doesn't
# generate. Re-adapt it (see examples/chunked_data/main.F90 or
# examples/var_compat/test_host.F90 for the pattern) once the
# HostVariableMatchPass gap above is fixed.
#
#------------------------------------------------------------------------------
set(SCHEME_FILES "register_consts" "const_dim_producer" "const_dim_consumer")
set(HOST_FILES   "host_data" "test_host")
set(SUITE_FILES  "constituents_dim_suite.xml")
set(HOST         "test_host")

set(CCPP_CAP_FILES "${CMAKE_CURRENT_BINARY_DIR}/ccpp")

list(TRANSFORM SCHEME_FILES APPEND ".F90"  OUTPUT_VARIABLE SCHEME_FORTRAN_FILES)
list(TRANSFORM SCHEME_FILES APPEND ".meta" OUTPUT_VARIABLE SCHEME_META_FILES)
list(TRANSFORM HOST_FILES   APPEND ".F90"  OUTPUT_VARIABLE CONSTITUENTS_DIM_HOST_FORTRAN_FILES)
list(TRANSFORM HOST_FILES   APPEND ".meta" OUTPUT_VARIABLE CONSTITUENTS_DIM_HOST_METADATA_FILES)

# Known-failing (see header comment above) -- calling this will
# message(FATAL_ERROR) until HostVariableMatchPass gains support for
# framework-injected scalar dimensions like number_of_ccpp_constituents.
xdsl_ccpp_capgen(HOSTFILES ${CONSTITUENTS_DIM_HOST_METADATA_FILES}
                 SCHEMEFILES ${SCHEME_META_FILES}
                 SUITES ${SUITE_FILES}
                 HOST_NAME ${HOST}
                 OUTPUT_ROOT "${CCPP_CAP_FILES}")
