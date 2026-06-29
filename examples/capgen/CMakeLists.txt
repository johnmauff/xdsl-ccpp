cmake_minimum_required(VERSION 3.20)
project(xdsl_ccpp_capgen_example Fortran)

# ── Generate CCPP caps at configure time ──────────────────────────────────────
include("${CMAKE_CURRENT_SOURCE_DIR}/../../cmake/xdsl_ccpp.cmake")

xdsl_ccpp_generate(
    HOST_NAME   "test_host"
    OUTPUT_ROOT "${CMAKE_CURRENT_BINARY_DIR}/caps"
    TARGET_VAR  XDSL_CAPS
    SUITES
        "${CMAKE_CURRENT_SOURCE_DIR}/ddt_suite.xml"
        "${CMAKE_CURRENT_SOURCE_DIR}/temp_suite.xml"
    SCHEMEFILES
        "${CMAKE_CURRENT_SOURCE_DIR}/make_ddt.meta"
        "${CMAKE_CURRENT_SOURCE_DIR}/environ_conditions.meta"
        "${CMAKE_CURRENT_SOURCE_DIR}/setup_coeffs.meta"
        "${CMAKE_CURRENT_SOURCE_DIR}/temp_set.meta"
        "${CMAKE_CURRENT_SOURCE_DIR}/temp_calc_adjust.meta"
        "${CMAKE_CURRENT_SOURCE_DIR}/temp_adjust.meta"
    HOSTFILES
        "${CMAKE_CURRENT_SOURCE_DIR}/test_host_data.meta"
        "${CMAKE_CURRENT_SOURCE_DIR}/test_host_mod.meta"
        "${CMAKE_CURRENT_SOURCE_DIR}/test_host.meta"
)

# ── Pre-existing Fortran sources (scheme implementations + test driver) ────────
set(CAPGEN_SRCS
    "${CMAKE_CURRENT_SOURCE_DIR}/test_utils.F90"
    "${CMAKE_CURRENT_SOURCE_DIR}/test_host_data.F90"
    "${CMAKE_CURRENT_SOURCE_DIR}/test_host_mod.F90"
    "${CMAKE_CURRENT_SOURCE_DIR}/make_ddt.F90"
    "${CMAKE_CURRENT_SOURCE_DIR}/environ_conditions.F90"
    "${CMAKE_CURRENT_SOURCE_DIR}/setup_coeffs.F90"
    "${CMAKE_CURRENT_SOURCE_DIR}/temp_set.F90"
    "${CMAKE_CURRENT_SOURCE_DIR}/temp_calc_adjust.F90"
    "${CMAKE_CURRENT_SOURCE_DIR}/temp_adjust.F90"
    "${CMAKE_CURRENT_SOURCE_DIR}/test_host.F90"
    "${CMAKE_CURRENT_SOURCE_DIR}/test_capgen_host_integration.F90"
)

# ── Build and test ─────────────────────────────────────────────────────────────
add_executable(test_capgen ${CAPGEN_SRCS} ${XDSL_CAPS})

# Both the source dir (pre-existing .mod producers) and the caps dir (generated
# .mod producers) must be on the module search path.
target_include_directories(test_capgen PRIVATE
    "${CMAKE_CURRENT_BINARY_DIR}"
    "${CMAKE_CURRENT_BINARY_DIR}/caps"
)

target_compile_options(test_capgen PRIVATE
    -ffree-line-length-none
    -Wno-unused-dummy-argument
)

enable_testing()
add_test(NAME capgen_integration COMMAND test_capgen)
