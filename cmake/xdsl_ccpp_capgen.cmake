# CMake wrapper for xdsl_ccpp's ccpp_xdsl tool (xdsl_ccpp.tools.ccpp_dsl).
#
# Modeled directly on capgen-v1's own cmake/ccpp_capgen.cmake (same
# keyword-argument shape: HOSTFILES/SCHEMEFILES/SUITES/HOST_NAME/
# OUTPUT_ROOT/VERBOSITY) so that a per-example CMakeLists.txt ported from
# capgen-v1's own end-to-end-tests needs only to swap the function name --
# everything else about the file's structure stays the same.
#
# HOST_NAME    - String name of host
# OUTPUT_ROOT  - String path to put generated caps (defaults to the build
#                tree, not the source tree -- unlike the Makefile-based
#                examples, which generate directly into their own source
#                directory; this keeps the CMake and Makefile build paths
#                from writing over each other while both exist side by side)
# VERBOSITY    - passed through as a single "--verbose N" flag (xdsl_ccpp's
#                own CLI takes one integer level, 0/1/2 -- unlike
#                capgen-v1's ccpp_capgen.cmake, which repeats "--verbose"
#                N times for its own CLI's different convention)
# HOSTFILES    - CMake list of host metadata filenames (no extension needed
#                by the caller; pass full relative/absolute paths as-is)
# SCHEMEFILES  - CMake list of scheme metadata files
# SUITES       - CMake list of suite xml files
#
# Sets CCPP_CAPS_LIST in the parent scope: the list of generated Fortran
# file paths, read back from --emit-datatable's own output. xdsl_ccpp's
# datatable.xml uses a different XML schema than capgen-v1's own
# datatable.xml (root element, and file paths as an attribute rather than
# element text) -- not compatible with capgen-v1's ccpp_datafile.py, so
# this parses it directly instead of trying to force schema compatibility
# with the other backend's tool.
function(xdsl_ccpp_capgen)
  set(oneValueArgs HOST_NAME OUTPUT_ROOT VERBOSITY)
  set(multiValueArgs HOSTFILES SCHEMEFILES SUITES)
  cmake_parse_arguments(arg "" "${oneValueArgs}" "${multiValueArgs}" ${ARGN})

  if(NOT DEFINED XDSL_CCPP_ROOT)
    message(FATAL_ERROR
      "xdsl_ccpp_capgen: XDSL_CCPP_ROOT must be set (the checkout's own "
      "repo root) before calling this function -- see examples/*/CMakeLists.txt.")
  endif()

  set(CCPP_XDSL_CMD "${Python3_EXECUTABLE}" -m xdsl_ccpp.tools.ccpp_dsl)

  if(DEFINED arg_HOSTFILES)
    list(JOIN arg_HOSTFILES "," HOSTFILES_SEPARATED)
    list(APPEND CCPP_XDSL_CMD "--host-files" "${HOSTFILES_SEPARATED}")
  endif()
  if(DEFINED arg_SCHEMEFILES)
    list(JOIN arg_SCHEMEFILES "," SCHEMEFILES_SEPARATED)
    list(APPEND CCPP_XDSL_CMD "--scheme-files" "${SCHEMEFILES_SEPARATED}")
  endif()
  if(DEFINED arg_SUITES)
    list(JOIN arg_SUITES "," SUITES_SEPARATED)
    list(APPEND CCPP_XDSL_CMD "--suites" "${SUITES_SEPARATED}")
  endif()
  if(DEFINED arg_HOST_NAME)
    list(APPEND CCPP_XDSL_CMD "--host-name" "${arg_HOST_NAME}")
  endif()

  set(OUTPUT_ROOT_DIR "${CMAKE_CURRENT_BINARY_DIR}/ccpp")
  if(DEFINED arg_OUTPUT_ROOT)
    set(OUTPUT_ROOT_DIR "${arg_OUTPUT_ROOT}")
  endif()
  file(MAKE_DIRECTORY "${OUTPUT_ROOT_DIR}")
  list(APPEND CCPP_XDSL_CMD "-o" "${OUTPUT_ROOT_DIR}")
  list(APPEND CCPP_XDSL_CMD "--tempdir" "${OUTPUT_ROOT_DIR}/tmp")

  if(DEFINED arg_VERBOSITY)
    list(APPEND CCPP_XDSL_CMD "--verbose" "${arg_VERBOSITY}")
  endif()

  set(DATATABLE_PATH "${OUTPUT_ROOT_DIR}/datatable.xml")
  list(APPEND CCPP_XDSL_CMD "--emit-datatable" "${DATATABLE_PATH}")

  message(STATUS "Running xdsl_ccpp's ccpp_xdsl from ${CMAKE_CURRENT_SOURCE_DIR}")

  # PYTHONPATH, not relying on a bare `ccpp_xdsl` console script or however
  # Python3_EXECUTABLE's own site-packages resolve xdsl_ccpp: an unrelated
  # xdsl-ccpp editable install elsewhere on the machine can otherwise
  # silently shadow this checkout's own code -- the identical precaution
  # every example's existing Makefile already takes.
  if(DEFINED ENV{PYTHONPATH} AND NOT "$ENV{PYTHONPATH}" STREQUAL "")
    set(_capgen_env "PYTHONPATH=${XDSL_CCPP_ROOT}:$ENV{PYTHONPATH}")
  else()
    set(_capgen_env "PYTHONPATH=${XDSL_CCPP_ROOT}")
  endif()

  # Separate stdout/stderr variables, not one shared variable for both:
  # keeping them distinct makes a failure's actual error output
  # unambiguous in the log, rather than an interleaved combined stream.
  execute_process(COMMAND ${CMAKE_COMMAND} -E env "${_capgen_env}" ${CCPP_XDSL_CMD}
                   WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
                   OUTPUT_VARIABLE CAPGEN_STDOUT
                   ERROR_VARIABLE CAPGEN_STDERR
                   RESULT_VARIABLE RES
                   COMMAND_ECHO STDOUT)
  message(STATUS "xdsl_ccpp ccpp_xdsl stdout:\n${CAPGEN_STDOUT}")
  message(STATUS "xdsl_ccpp ccpp_xdsl stderr:\n${CAPGEN_STDERR}")

  if(NOT RES EQUAL 0)
    message(FATAL_ERROR "xdsl_ccpp cap generation FAILED: result = ${RES}")
  endif()

  if(NOT EXISTS "${DATATABLE_PATH}")
    message(FATAL_ERROR "xdsl_ccpp_capgen: expected datatable at ${DATATABLE_PATH}, not found")
  endif()

  set(_parse_script "${CMAKE_CURRENT_FUNCTION_LIST_DIR}/parse_xdsl_ccpp_datatable.py")
  execute_process(
    COMMAND "${Python3_EXECUTABLE}" "${_parse_script}" "${DATATABLE_PATH}"
    OUTPUT_VARIABLE CCPP_CAPS
    RESULT_VARIABLE RES2
    OUTPUT_STRIP_TRAILING_WHITESPACE
  )
  if(NOT RES2 EQUAL 0)
    message(FATAL_ERROR "xdsl_ccpp_capgen: failed to read generated file list from ${DATATABLE_PATH}")
  endif()

  string(REPLACE "," ";" CCPP_CAPS_LIST "${CCPP_CAPS}")
  set(CCPP_CAPS_LIST "${CCPP_CAPS_LIST}" PARENT_SCOPE)
endfunction()
