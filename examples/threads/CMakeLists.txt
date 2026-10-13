#------------------------------------------------------------------------------
#
# threads: NEW test fixture (task11-omp-thread item 3) exercising
# thread_number/number_of_threads -- the per-thread analog of
# examples/instances' own instance_number/number_of_instances mechanism.
# NOT ported from real capgen-v1: confirmed during scoping that real
# capgen-v1's own end-to-end-tests/ has no fixture dimensioning a
# container DDT by number_of_threads (only unused control-table
# boilerplate declarations of the pair everywhere else); real capgen-v1's
# own coverage of this mechanism lives entirely at the unit-test level.
# See examples/threads/main.F90's own header comment for the direct
# structural precedent (examples/instances/main.F90) and what was
# simplified relative to it.
#
#------------------------------------------------------------------------------
set(SCHEME_FILES "thread_scheme")
# "test_host" (the control table) is metadata only -- its vars
# (lb/ub/errmsg/errflg/thread/nthreads) are plain arguments passed
# directly at each call site, never `use`-associated from a module, so
# there's no test_host.F90 to compile. Only "data" (which owns the real
# host state) needs a compiled Fortran counterpart -- same distinction
# examples/instances/CMakeLists.txt makes for its own identical
# test_host.meta shape.
set(HOST_FILES   "data")
set(SUITE_FILES  "suite_thread_suite.xml")
set(HOST         "test_host")

set(CCPP_CAP_FILES "${CMAKE_CURRENT_BINARY_DIR}/ccpp")

list(TRANSFORM SCHEME_FILES APPEND ".F90"  OUTPUT_VARIABLE SCHEME_FORTRAN_FILES)
list(TRANSFORM SCHEME_FILES APPEND ".meta" OUTPUT_VARIABLE SCHEME_META_FILES)
list(TRANSFORM HOST_FILES   APPEND ".F90"  OUTPUT_VARIABLE THREADS_HOST_FORTRAN_FILES)
list(TRANSFORM HOST_FILES   APPEND ".meta" OUTPUT_VARIABLE THREADS_HOST_METADATA_FILES)
list(APPEND THREADS_HOST_METADATA_FILES "${HOST}.meta")

xdsl_ccpp_capgen(HOSTFILES ${THREADS_HOST_METADATA_FILES}
                 SCHEMEFILES ${SCHEME_META_FILES}
                 SUITES ${SUITE_FILES}
                 HOST_NAME ${HOST}
                 OUTPUT_ROOT "${CCPP_CAP_FILES}")

if(XDSL_CCPP_HAVE_FORTRAN)
  add_library(THREADS_TESTLIB OBJECT ${SCHEME_FORTRAN_FILES}
                                      ${THREADS_HOST_FORTRAN_FILES}
                                      ${CCPP_CAPS_LIST})
  set_target_properties(THREADS_TESTLIB PROPERTIES Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/mod)
  target_include_directories(THREADS_TESTLIB PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/mod)

  add_executable(threads.exe main.F90)
  target_link_libraries(threads.exe PRIVATE THREADS_TESTLIB)
  target_include_directories(threads.exe PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/mod)

  add_test(NAME ctest_threads COMMAND threads.exe)
endif()
