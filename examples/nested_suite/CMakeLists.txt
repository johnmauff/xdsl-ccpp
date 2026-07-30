#------------------------------------------------------------------------------
#
# Patterned directly on capgen-v1's own upstream
# end-to-end-tests/nested_suite/CMakeLists.txt (see this project's
# reference/ccpp-framework checkout's test/nested_suite_test/CMakeLists.txt
# for the original this was ported from) -- the only intentional
# differences are the xdsl_ccpp_capgen() function name (this repo's own
# cap-generation tool, not capgen-v1's) and two extra entries this port
# needs that the upstream file doesn't (suite_lifecycle, for the
# suite-level init/final hooks feature; ccpp_constituent_prop_mod/
# ccpp_scheme_utils stub modules, needed by every xdsl_ccpp-generated cap
# regardless of whether the example declares constituents -- see the
# existing Makefile's own comment on this).
#
#------------------------------------------------------------------------------
set(SCHEME_FILES "effr_calc" "effrs_calc" "effr_diag" "effr_pre" "effr_post" "rad_lw" "rad_sw" "suite_lifecycle")
set(HOST_FILES   "module_rad_ddt" "test_host_data" "test_host_mod")
set(SUITE_FILES  "main_suite.xml")
# HOST is the name of the executable we will build.
# We assume there are files ${HOST}.meta and ${HOST}.F90 in CMAKE_CURRENT_SOURCE_DIR
set(HOST "test_host")

# Only the top-level suite file is passed via SUITE_FILES -- radiation2_suite.xml/
# radiation3_suite.xml/radiation3_subsuite.xml/radiation4_suite.xml are pulled in
# dynamically via main_suite.xml's own <nested_suite file=.../> references
# (resolved relative to this directory), not listed here directly, matching
# the existing Makefile's own CAPS_SUITES/CAPS_PREREQS split.

# By default, generated caps go in the build tree, not this source directory
# (see xdsl_ccpp_capgen.cmake's own OUTPUT_ROOT default) -- deliberately
# different from the existing Makefile's `caps` target, which writes into
# this directory directly, so the two build systems can coexist without
# overwriting each other's output while both exist.
set(CCPP_CAP_FILES "${CMAKE_CURRENT_BINARY_DIR}/ccpp")

# Create lists for Fortran and meta data files from file names
list(TRANSFORM SCHEME_FILES APPEND ".F90"  OUTPUT_VARIABLE SCHEME_FORTRAN_FILES)
list(TRANSFORM SCHEME_FILES APPEND ".meta" OUTPUT_VARIABLE SCHEME_META_FILES)
list(TRANSFORM HOST_FILES   APPEND ".F90"  OUTPUT_VARIABLE NESTED_SUITE_HOST_FORTRAN_FILES)
list(TRANSFORM HOST_FILES   APPEND ".meta" OUTPUT_VARIABLE NESTED_SUITE_HOST_METADATA_FILES)

list(APPEND NESTED_SUITE_HOST_METADATA_FILES "${HOST}.meta")

# Run xdsl_ccpp's own cap generator (analogous to capgen-v1's ccpp_capgen()
# call in the upstream original this file is ported from)
xdsl_ccpp_capgen(HOSTFILES ${NESTED_SUITE_HOST_METADATA_FILES}
                 SCHEMEFILES ${SCHEME_META_FILES}
                 SUITES ${SUITE_FILES}
                 HOST_NAME ${HOST}
                 OUTPUT_ROOT "${CCPP_CAP_FILES}")
# CCPP_CAPS_LIST is now set (by xdsl_ccpp_capgen, in this scope) to the
# generated Fortran files (ccpp_kinds.F90, main_suite_cap.F90,
# test_host_ccpp_cap.F90).

if(XDSL_CCPP_HAVE_FORTRAN)
  # Create test host library
  add_library(NESTED_SUITE_TESTLIB OBJECT ${SCHEME_FORTRAN_FILES}
                                           ${NESTED_SUITE_HOST_FORTRAN_FILES}
                                           ccpp_constituent_prop_mod.F90
                                           ccpp_scheme_utils.F90
                                           ${CCPP_CAPS_LIST})
  set_target_properties(NESTED_SUITE_TESTLIB PROPERTIES Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/mod)
  target_include_directories(NESTED_SUITE_TESTLIB PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/mod)
  target_link_libraries(NESTED_SUITE_TESTLIB PRIVATE test_utils)

  # Setup test executable with needed dependencies. test_utils' own module
  # include directory reaches this target automatically via its PUBLIC
  # target_include_directories (set where test_utils is defined, in the
  # root CMakeLists.txt) -- linking against it is enough, no need to name
  # that path again here. ${CMAKE_CURRENT_BINARY_DIR}/mod (NESTED_SUITE_TESTLIB's
  # own .mod output) is the one path this target genuinely still needs to
  # be told about directly.
  add_executable(nested_suite_host_integration test_nested_suite_integration.F90 ${HOST}.F90)
  target_link_libraries(nested_suite_host_integration PRIVATE NESTED_SUITE_TESTLIB test_utils)
  target_include_directories(nested_suite_host_integration PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/mod)

  # Add executable to be called with ctest
  add_test(NAME ctest_nested_suite_host_integration COMMAND nested_suite_host_integration)
endif()
