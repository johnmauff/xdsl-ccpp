#------------------------------------------------------------------------------
#
# threads_nometa: dup-meta-shadow-elim (BACKLOG.md) demonstration twin of
# examples/threads -- identical functionality and host/suite files, but
# thread_scheme.F90 carries standard_name/units/long_name/dim_names as
# !ccpp tags instead of a hand-maintained thread_scheme.meta. No .meta for
# the scheme is committed to this directory at all; it's generated here,
# into the build tree, from the tagged source.
#
# Verified directly (not assumed) that the regenerated .meta is
# semantically identical to examples/threads' own hand-authored
# thread_scheme.meta: compare_modules() between the two reports zero
# mismatches.
#
# Option 1 (current scope, see BACKLOG.md plan notes): .meta is generated
# once, at CONFIGURE time only, via execute_process(). This is required,
# not just simpler-for-now -- xdsl_ccpp_capgen()'s own --list-outputs
# prediction also runs at configure time and needs this .meta to already
# exist on disk at that point; a build-time-only generation step would
# leave nothing there for a clean first configure to find. Known
# limitation: editing thread_scheme.F90's tags requires re-running `cmake`
# (a reconfigure) to regenerate .meta -- `cmake --build` alone will not
# pick up the change. A later addition (Option 2) can layer a build-time
# add_custom_command() regeneration rule on top of this without changing
# anything here -- this configure-time step stays required either way.
#
#------------------------------------------------------------------------------
set(SCHEME_FILES "thread_scheme")
set(HOST_FILES   "data")
set(SUITE_FILES  "suite_thread_suite.xml")
set(HOST         "test_host")

set(CCPP_CAP_FILES "${CMAKE_CURRENT_BINARY_DIR}/ccpp")

list(TRANSFORM SCHEME_FILES APPEND ".F90"  OUTPUT_VARIABLE SCHEME_FORTRAN_FILES)
list(TRANSFORM HOST_FILES   APPEND ".F90"  OUTPUT_VARIABLE THREADS_HOST_FORTRAN_FILES)
list(TRANSFORM HOST_FILES   APPEND ".meta" OUTPUT_VARIABLE THREADS_HOST_METADATA_FILES)
list(APPEND THREADS_HOST_METADATA_FILES "${HOST}.meta")

# --- Generate thread_scheme.meta from its own tagged Fortran source, at
# configure time, into the build tree (never the source tree -- nothing
# here is meant to be committed). --root-dir is the source directory,
# where thread_scheme.F90 and any real USE-dependency it might have
# actually live; the generated .meta goes into CMAKE_CURRENT_BINARY_DIR.
if(DEFINED ENV{PYTHONPATH} AND NOT "$ENV{PYTHONPATH}" STREQUAL "")
  set(_nometa_env "PYTHONPATH=${XDSL_CCPP_ROOT}:$ENV{PYTHONPATH}")
else()
  set(_nometa_env "PYTHONPATH=${XDSL_CCPP_ROOT}")
endif()

set(SCHEME_META_FILES "${CMAKE_CURRENT_BINARY_DIR}/thread_scheme.meta")

message(STATUS "Generating ${SCHEME_META_FILES} from tagged source (threads_nometa)")
execute_process(
  COMMAND ${CMAKE_COMMAND} -E env "${_nometa_env}"
          "${Python3_EXECUTABLE}" -m xdsl_ccpp.tools.ccpp_generate_meta
          --output-dir "${CMAKE_CURRENT_BINARY_DIR}"
          --root-dir "${CMAKE_CURRENT_SOURCE_DIR}"
          "${CMAKE_CURRENT_SOURCE_DIR}/thread_scheme.F90"
  RESULT_VARIABLE _nometa_gen_result
  ERROR_VARIABLE _nometa_gen_stderr
)
if(NOT _nometa_gen_result EQUAL 0)
  message(FATAL_ERROR
    "threads_nometa: ccpp_generate_meta failed (result = ${_nometa_gen_result}):\n"
    "${_nometa_gen_stderr}")
endif()

xdsl_ccpp_capgen(HOSTFILES ${THREADS_HOST_METADATA_FILES}
                 SCHEMEFILES ${SCHEME_META_FILES}
                 SUITES ${SUITE_FILES}
                 HOST_NAME ${HOST}
                 OUTPUT_ROOT "${CCPP_CAP_FILES}")

if(XDSL_CCPP_HAVE_FORTRAN)
  add_library(THREADS_NOMETA_TESTLIB OBJECT ${SCHEME_FORTRAN_FILES}
                                             ${THREADS_HOST_FORTRAN_FILES}
                                             ${CCPP_CAPS_LIST})
  set_target_properties(THREADS_NOMETA_TESTLIB PROPERTIES Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/mod)
  target_include_directories(THREADS_NOMETA_TESTLIB PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/mod)

  add_executable(threads_nometa.exe main.F90)
  target_link_libraries(threads_nometa.exe PRIVATE THREADS_NOMETA_TESTLIB)
  target_include_directories(threads_nometa.exe PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/mod)

  add_test(NAME ctest_threads_nometa COMMAND threads_nometa.exe)
endif()
