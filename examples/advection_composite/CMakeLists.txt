# examples/advection_composite: examples/advection built from a Python
# composite suite (advection_composite_py.py, via PY_SUITE) instead of
# cld_suite.xml, with scheme metadata generated from the !$ccpp-tagged
# scheme sources (as in examples/advection_nometa). It generates the same
# caps as examples/advection, so the same host-integration test applies.

set(ARCH "CPU" CACHE STRING
    "examples/advection target architecture: CPU or GPU (OpenACC, requires nvfortran)")
set_property(CACHE ARCH PROPERTY STRINGS CPU GPU)

set(SCHEME_FILES "const_indices" "cld_liq" "apply_constituent_tendencies" "cld_ice" "cld_shadow")
set(HOST_FILES   "test_host_data" "test_host_mod")
set(HOST "test_host")

set(CCPP_CAP_FILES "${CMAKE_CURRENT_BINARY_DIR}/ccpp")

list(TRANSFORM SCHEME_FILES APPEND ".F90"  OUTPUT_VARIABLE SCHEME_FORTRAN_FILES)
list(TRANSFORM HOST_FILES   APPEND ".F90"  OUTPUT_VARIABLE ADVECTION_COMPOSITE_HOST_FORTRAN_FILES)
list(TRANSFORM HOST_FILES   APPEND ".meta" OUTPUT_VARIABLE ADVECTION_COMPOSITE_HOST_METADATA_FILES)
list(APPEND ADVECTION_COMPOSITE_HOST_METADATA_FILES "${HOST}.meta")

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
    "advection_composite: ccpp_generate_meta failed (result = ${_composite_gen_result}):\n"
    "${_composite_gen_stderr}")
endif()

xdsl_ccpp_capgen(HOSTFILES ${ADVECTION_COMPOSITE_HOST_METADATA_FILES}
                 SCHEMEFILES ${SCHEME_META_FILES}
                 PY_SUITE advection_composite_py.py
                 HOST_NAME ${HOST}
                 DIRECTIVE "acc"
                 OUTPUT_ROOT "${CCPP_CAP_FILES}")

if(XDSL_CCPP_HAVE_FORTRAN)
  if(ARCH STREQUAL "GPU" AND NOT CMAKE_Fortran_COMPILER_ID STREQUAL "NVHPC")
    message(FATAL_ERROR
      "examples/advection_composite: ARCH=GPU requires nvfortran for OpenACC "
      "(matching examples/advection's own requirement) -- e.g. "
      "`module load nvhpc` on Derecho, or pass "
      "-DCMAKE_Fortran_COMPILER=nvfortran explicitly; got "
      "CMAKE_Fortran_COMPILER_ID=${CMAKE_Fortran_COMPILER_ID}.")
  endif()

  add_library(ADVECTION_COMPOSITE_TESTLIB OBJECT ${SCHEME_FORTRAN_FILES}
                                        ${ADVECTION_COMPOSITE_HOST_FORTRAN_FILES}
                                        ${XDSL_CCPP_ROOT}/xdsl_ccpp/framework_src/ccpp_constituent_prop_mod.F90
                                        ${XDSL_CCPP_ROOT}/xdsl_ccpp/framework_src/ccpp_hashable.F90
                                        ${XDSL_CCPP_ROOT}/xdsl_ccpp/framework_src/ccpp_hash_table.F90
                                        ${XDSL_CCPP_ROOT}/xdsl_ccpp/framework_src/ccpp_scheme_utils.F90
                                        ${CCPP_CAPS_LIST})
  set_target_properties(ADVECTION_COMPOSITE_TESTLIB PROPERTIES Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/mod)
  target_include_directories(ADVECTION_COMPOSITE_TESTLIB PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/mod)
  target_link_libraries(ADVECTION_COMPOSITE_TESTLIB PRIVATE test_utils)

  add_executable(advection_composite.exe test_advection_host_integration.F90 ${HOST}.F90)
  target_link_libraries(advection_composite.exe PRIVATE ADVECTION_COMPOSITE_TESTLIB test_utils)
  target_include_directories(advection_composite.exe PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/mod)

  if(CMAKE_Fortran_COMPILER_ID STREQUAL "NVHPC")
    if(ARCH STREQUAL "GPU")
      target_compile_options(ADVECTION_COMPOSITE_TESTLIB PRIVATE -mp=gpu -Minfo=accel)
      target_compile_options(advection_composite.exe PRIVATE -mp=gpu -Minfo=accel)
      target_compile_definitions(ADVECTION_COMPOSITE_TESTLIB PRIVATE USE_GPU)
      target_compile_definitions(advection_composite.exe PRIVATE USE_GPU)
    else()
      target_compile_options(ADVECTION_COMPOSITE_TESTLIB PRIVATE -noacc)
      target_compile_options(advection_composite.exe PRIVATE -noacc)
    endif()
  endif()

  add_test(NAME ctest_advection_composite COMMAND advection_composite.exe)
endif()
