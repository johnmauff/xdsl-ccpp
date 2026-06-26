# cmake/xdsl_ccpp.cmake
#
# Provides xdsl_ccpp_generate() for integrating xdsl-ccpp CCPP cap generation
# into CMake-based host model builds.
#
# Minimum CMake version required by callers: 3.20
# (3.20 introduced reliable Fortran module dependency scanning)
#
# Usage:
#
#   include(path/to/cmake/xdsl_ccpp.cmake)
#
#   xdsl_ccpp_generate(
#       HOST_NAME   "MyHost"
#       OUTPUT_ROOT "${CMAKE_CURRENT_BINARY_DIR}/ccpp_caps"
#       TARGET_VAR  MY_CAPS
#       SUITES
#           "${CMAKE_CURRENT_SOURCE_DIR}/suite_a.xml"
#           "${CMAKE_CURRENT_SOURCE_DIR}/suite_b.xml"
#       SCHEMEFILES
#           "${CMAKE_CURRENT_SOURCE_DIR}/scheme_a.meta"
#           "${CMAKE_CURRENT_SOURCE_DIR}/scheme_b.meta"
#       HOSTFILES
#           "${CMAKE_CURRENT_SOURCE_DIR}/host_data.meta"
#   )
#
#   add_executable(my_host ${MY_SRCS} ${MY_CAPS})
#   target_include_directories(my_host PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/ccpp_caps")
#
# After the call, MY_CAPS contains the absolute paths of every .F90 file that
# was written into OUTPUT_ROOT.  Pass this list alongside your own source files
# to add_library() or add_executable().
#
# The generator runs at CMake configure time (via execute_process), mirroring
# the approach used by ccpp_capgen-ng.  Re-running cmake (or touching any
# .meta/.xml input file and calling cmake --build with --fresh-cmake) is
# required to pick up changes to the CCPP metadata.
#
# Requirements:
#   - ccpp_xdsl must be on PATH (pip install -e <path/to/xdsl-ccpp>)

cmake_minimum_required(VERSION 3.20)

function(xdsl_ccpp_generate)
    set(_oneValueArgs  HOST_NAME OUTPUT_ROOT TARGET_VAR)
    set(_multiValueArgs SUITES SCHEMEFILES HOSTFILES)
    cmake_parse_arguments(XDSL "" "${_oneValueArgs}" "${_multiValueArgs}" ${ARGN})

    # ── validate required arguments ───────────────────────────────────────────
    foreach(_req HOST_NAME OUTPUT_ROOT TARGET_VAR SUITES SCHEMEFILES)
        if(NOT XDSL_${_req})
            message(FATAL_ERROR "xdsl_ccpp_generate: ${_req} is required")
        endif()
    endforeach()

    # ── locate ccpp_xdsl entry point ──────────────────────────────────────────
    find_program(XDSL_CCPP_EXECUTABLE ccpp_xdsl
        HINTS ENV PATH
        DOC "ccpp_xdsl cap generator (from xdsl-ccpp)"
    )
    if(NOT XDSL_CCPP_EXECUTABLE)
        message(FATAL_ERROR
            "xdsl_ccpp_generate: could not find ccpp_xdsl on PATH.\n"
            "Install xdsl-ccpp with:  pip install -e <path/to/xdsl-ccpp>")
    endif()

    # ── build command ─────────────────────────────────────────────────────────
    # ccpp_xdsl expects comma-separated lists, not space-separated.
    list(JOIN XDSL_SUITES      "," _suites_str)
    list(JOIN XDSL_SCHEMEFILES "," _scheme_str)

    set(_cmd
        "${XDSL_CCPP_EXECUTABLE}"
        --suites       "${_suites_str}"
        --scheme-files "${_scheme_str}"
        --host-name    "${XDSL_HOST_NAME}"
        -o             "${XDSL_OUTPUT_ROOT}"
        --verbose      0
    )

    if(XDSL_HOSTFILES)
        list(JOIN XDSL_HOSTFILES "," _host_str)
        list(APPEND _cmd --host-files "${_host_str}")
    endif()

    # ── run at configure time ─────────────────────────────────────────────────
    file(MAKE_DIRECTORY "${XDSL_OUTPUT_ROOT}")
    message(STATUS "xdsl_ccpp_generate: generating CCPP caps for '${XDSL_HOST_NAME}'")

    execute_process(
        COMMAND         ${_cmd}
        RESULT_VARIABLE _exit_code
        OUTPUT_VARIABLE _stdout
        ERROR_VARIABLE  _stderr
    )

    if(NOT _exit_code EQUAL 0)
        message(FATAL_ERROR
            "xdsl_ccpp_generate failed (exit ${_exit_code}):\n${_stderr}\n${_stdout}")
    endif()

    # ── collect generated files ───────────────────────────────────────────────
    file(GLOB _caps "${XDSL_OUTPUT_ROOT}/*.F90")
    if(NOT _caps)
        message(WARNING
            "xdsl_ccpp_generate: no .F90 files found in ${XDSL_OUTPUT_ROOT} "
            "after running ccpp_xdsl — check the inputs.")
    endif()

    set(${XDSL_TARGET_VAR} "${_caps}" PARENT_SCOPE)
endfunction()
