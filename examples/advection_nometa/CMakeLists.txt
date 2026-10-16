#------------------------------------------------------------------------------
#
# advection_nometa: dup-meta-shadow-elim (BACKLOG.md) demonstration twin of
# examples/advection -- identical functionality and host/suite files, but
# the 5 scheme .F90 files (const_indices, cld_liq, apply_constituent_tendencies,
# cld_ice, cld_shadow) carry standard_name/units/long_name/dim_names/advected/
# constituent/state_variable/default_value/protected as !$ccpp tags instead of
# hand-maintained .meta files. No .meta for any scheme is committed to this
# directory at all; all 5 are generated here, into the build tree, from the
# tagged sources, in a single ccpp_generate_meta invocation.
#
# dlc_liq.F90/.meta (a deliberate register-phase-violation negative-test
# fixture, not part of cld_suite) is out of scope for this demonstration --
# left untouched in examples/advection, not duplicated here.
#
# Verified directly (not assumed) that each regenerated .meta is semantically
# identical to examples/advection's own hand-authored .meta for that scheme:
# compare_modules() between the two reports zero mismatches for all 5.
#
# Option 1 (current scope, see BACKLOG.md plan notes): .meta is generated
# once, at CONFIGURE time only, via execute_process() -- same as
# examples/threads_nometa. Known limitation: editing a scheme .F90's tags
# requires re-running `cmake` (a reconfigure) to regenerate .meta --
# `cmake --build` alone will not pick up the change.
#
# ARCH/GPU: shares the ARCH cache variable defined by
# examples/advection/CMakeLists.txt (both examples are GPU-capable via the
# same nvfortran/OpenACC recipe, and cld_liq/cld_ice's memory_space=device
# here is mechanically derived from the same real !$acc present(...)
# clauses examples/advection's own scheme files carry) -- not redeclared
# here, matching examples/advection_flat_host's own precedent.
#
#------------------------------------------------------------------------------
set(SCHEME_FILES "const_indices" "cld_liq" "apply_constituent_tendencies" "cld_ice" "cld_shadow")
set(HOST_FILES   "test_host_data" "test_host_mod")
set(SUITE_FILES  "cld_suite.xml")
set(HOST "test_host")

set(CCPP_CAP_FILES "${CMAKE_CURRENT_BINARY_DIR}/ccpp")

list(TRANSFORM SCHEME_FILES APPEND ".F90"  OUTPUT_VARIABLE SCHEME_FORTRAN_FILES)
list(TRANSFORM HOST_FILES   APPEND ".F90"  OUTPUT_VARIABLE ADVECTION_NOMETA_HOST_FORTRAN_FILES)
list(TRANSFORM HOST_FILES   APPEND ".meta" OUTPUT_VARIABLE ADVECTION_NOMETA_HOST_METADATA_FILES)
list(APPEND ADVECTION_NOMETA_HOST_METADATA_FILES "${HOST}.meta")

# --- Generate all 5 schemes' .meta from their own tagged Fortran source, at
# configure time, into the build tree (never the source tree -- nothing here
# is meant to be committed). One ccpp_generate_meta invocation handles all 5
# files; --root-dir is this directory, where every real USE-dependency these
# scheme files might have actually lives.
if(DEFINED ENV{PYTHONPATH} AND NOT "$ENV{PYTHONPATH}" STREQUAL "")
  set(_nometa_env "PYTHONPATH=${XDSL_CCPP_ROOT}:$ENV{PYTHONPATH}")
else()
  set(_nometa_env "PYTHONPATH=${XDSL_CCPP_ROOT}")
endif()

list(TRANSFORM SCHEME_FILES APPEND ".meta" OUTPUT_VARIABLE _scheme_meta_names)
list(TRANSFORM _scheme_meta_names PREPEND "${CMAKE_CURRENT_BINARY_DIR}/" OUTPUT_VARIABLE SCHEME_META_FILES)

message(STATUS "Generating ${SCHEME_META_FILES} from tagged source (advection_nometa)")
execute_process(
  COMMAND ${CMAKE_COMMAND} -E env "${_nometa_env}"
          "${Python3_EXECUTABLE}" -m xdsl_ccpp.tools.ccpp_generate_meta
          --output-dir "${CMAKE_CURRENT_BINARY_DIR}"
          --root-dir "${CMAKE_CURRENT_SOURCE_DIR}"
          ${SCHEME_FORTRAN_FILES}
  WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
  RESULT_VARIABLE _nometa_gen_result
  ERROR_VARIABLE _nometa_gen_stderr
)
if(NOT _nometa_gen_result EQUAL 0)
  message(FATAL_ERROR
    "advection_nometa: ccpp_generate_meta failed (result = ${_nometa_gen_result}):\n"
    "${_nometa_gen_stderr}")
endif()

xdsl_ccpp_capgen(HOSTFILES ${ADVECTION_NOMETA_HOST_METADATA_FILES}
                 SCHEMEFILES ${SCHEME_META_FILES}
                 SUITES ${SUITE_FILES}
                 HOST_NAME ${HOST}
                 DIRECTIVE "acc"
                 OUTPUT_ROOT "${CCPP_CAP_FILES}")

if(XDSL_CCPP_HAVE_FORTRAN)
  if(ARCH STREQUAL "GPU" AND NOT CMAKE_Fortran_COMPILER_ID STREQUAL "NVHPC")
    message(FATAL_ERROR
      "examples/advection_nometa: ARCH=GPU requires nvfortran for OpenACC "
      "(matching examples/advection's own requirement) -- e.g. "
      "`module load nvhpc` on Derecho, or pass "
      "-DCMAKE_Fortran_COMPILER=nvfortran explicitly; got "
      "CMAKE_Fortran_COMPILER_ID=${CMAKE_Fortran_COMPILER_ID}.")
  endif()

  add_library(ADVECTION_NOMETA_TESTLIB OBJECT ${SCHEME_FORTRAN_FILES}
                                        ${ADVECTION_NOMETA_HOST_FORTRAN_FILES}
                                        ${XDSL_CCPP_ROOT}/xdsl_ccpp/framework_src/ccpp_constituent_prop_mod.F90
                                        ${XDSL_CCPP_ROOT}/xdsl_ccpp/framework_src/ccpp_hashable.F90
                                        ${XDSL_CCPP_ROOT}/xdsl_ccpp/framework_src/ccpp_hash_table.F90
                                        ${XDSL_CCPP_ROOT}/xdsl_ccpp/framework_src/ccpp_scheme_utils.F90
                                        ${CCPP_CAPS_LIST})
  set_target_properties(ADVECTION_NOMETA_TESTLIB PROPERTIES Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/mod)
  target_include_directories(ADVECTION_NOMETA_TESTLIB PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/mod)
  target_link_libraries(ADVECTION_NOMETA_TESTLIB PRIVATE test_utils)

  add_executable(advection_nometa.exe test_advection_host_integration.F90 ${HOST}.F90)
  target_link_libraries(advection_nometa.exe PRIVATE ADVECTION_NOMETA_TESTLIB test_utils)
  target_include_directories(advection_nometa.exe PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/mod)

  if(CMAKE_Fortran_COMPILER_ID STREQUAL "NVHPC")
    if(ARCH STREQUAL "GPU")
      target_compile_options(ADVECTION_NOMETA_TESTLIB PRIVATE -mp=gpu -Minfo=accel)
      target_compile_options(advection_nometa.exe PRIVATE -mp=gpu -Minfo=accel)
      target_compile_definitions(ADVECTION_NOMETA_TESTLIB PRIVATE USE_GPU)
      target_compile_definitions(advection_nometa.exe PRIVATE USE_GPU)
    else()
      target_compile_options(ADVECTION_NOMETA_TESTLIB PRIVATE -noacc)
      target_compile_options(advection_nometa.exe PRIVATE -noacc)
    endif()
  endif()

  add_test(NAME ctest_advection_nometa COMMAND advection_nometa.exe)
endif()
