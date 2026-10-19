# examples/helloworld_composite: examples/helloworld built from a Python
# composite suite (helloworld_composite_py.py, via PY_SUITE) instead of
# hello_world_suite.xml, with scheme metadata generated from the
# !$ccpp-tagged scheme sources. It generates the same caps as
# examples/helloworld, so the same host program and check apply.

set(SCHEME_FILES "hello_scheme" "temp_adjust")
set(CCPP_CAP_FILES "${CMAKE_CURRENT_BINARY_DIR}/ccpp")

list(TRANSFORM SCHEME_FILES APPEND ".F90" OUTPUT_VARIABLE SCHEME_FORTRAN_FILES)

# Scheme .meta generated from the tagged sources, at configure time, into
# the build tree (same mechanism as examples/advection_nometa).
if(DEFINED ENV{PYTHONPATH} AND NOT "$ENV{PYTHONPATH}" STREQUAL "")
  set(_composite_env "PYTHONPATH=${XDSL_CCPP_ROOT}:$ENV{PYTHONPATH}")
else()
  set(_composite_env "PYTHONPATH=${XDSL_CCPP_ROOT}")
endif()
list(TRANSFORM SCHEME_FILES APPEND ".meta" OUTPUT_VARIABLE _scheme_meta_names)
list(TRANSFORM _scheme_meta_names PREPEND "${CMAKE_CURRENT_BINARY_DIR}/" OUTPUT_VARIABLE SCHEME_META_FILES)
execute_process(
  COMMAND ${CMAKE_COMMAND} -E env "${_composite_env}"
          "${Python3_EXECUTABLE}" -m xdsl_ccpp.tools.ccpp_generate_meta
          --output-dir "${CMAKE_CURRENT_BINARY_DIR}"
          --root-dir "${CMAKE_CURRENT_SOURCE_DIR}"
          ${SCHEME_FORTRAN_FILES}
  WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
  RESULT_VARIABLE _composite_gen_result
  ERROR_VARIABLE _composite_gen_stderr
)
if(NOT _composite_gen_result EQUAL 0)
  message(FATAL_ERROR
    "helloworld_composite: ccpp_generate_meta failed (result = ${_composite_gen_result}):\n"
    "${_composite_gen_stderr}")
endif()

xdsl_ccpp_capgen(HOSTFILES hello_world_host.meta hello_world_mod.meta
                 SCHEMEFILES ${SCHEME_META_FILES}
                 PY_SUITE helloworld_composite_py.py
                 KIND_MAP "kind_dyn:REAL32"
                 OUTPUT_ROOT "${CCPP_CAP_FILES}")

if(XDSL_CCPP_HAVE_FORTRAN)
  add_executable(helloworld_composite.exe
    ${CCPP_CAP_FILES}/ccpp_kinds.F90
    hello_world_mod.F90
    hello_scheme.F90
    temp_adjust.F90
    ${CCPP_CAP_FILES}/hello_world_suite_cap.F90
    ${CCPP_CAP_FILES}/HelloWorld_ccpp_cap.F90
    hello_world_host.F90)
  set_target_properties(helloworld_composite.exe PROPERTIES Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/mod)
  target_include_directories(helloworld_composite.exe PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/mod)
  add_test(NAME ctest_helloworld_composite COMMAND helloworld_composite.exe)
  set_tests_properties(ctest_helloworld_composite PROPERTIES
    PASS_REGULAR_EXPRESSION "Answers are correct!")
endif()
