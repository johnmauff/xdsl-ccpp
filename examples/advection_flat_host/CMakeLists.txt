#------------------------------------------------------------------------------
#
# advection_flat_host: the same cloud advection example as examples/advection,
# but with a "flat" (non-DDT) host state -- individual arrays instead of a
# derived-type host state (see this directory's own README.md). No upstream
# capgen-v1 end-to-end-tests example exercises --directive, so this file is
# written from scratch, patterned directly on examples/advection's own
# CMakeLists.txt rather than a real upstream original.
#
# Shares the ARCH cache variable defined by examples/advection/CMakeLists.txt
# (both examples are GPU-capable via the same nvfortran/OpenACC recipe) --
# CMake CACHE variables are project-wide, so setting -DARCH=GPU once affects
# both examples' builds together (a single "build everything for GPU" toggle,
# not two independent ones).
#
#------------------------------------------------------------------------------
set(SCHEME_FILES "const_indices" "cld_liq" "apply_constituent_tendencies" "cld_ice")
set(HOST_FILES   "flat_host_data" "flat_host_mod")
set(SUITE_FILES  "cld_suite.xml")
set(HOST "flat_host")

set(CCPP_CAP_FILES "${CMAKE_CURRENT_BINARY_DIR}/ccpp")

list(TRANSFORM SCHEME_FILES APPEND ".F90"  OUTPUT_VARIABLE SCHEME_FORTRAN_FILES)
list(TRANSFORM SCHEME_FILES APPEND ".meta" OUTPUT_VARIABLE SCHEME_META_FILES)
list(TRANSFORM HOST_FILES   APPEND ".F90"  OUTPUT_VARIABLE FLAT_HOST_FORTRAN_FILES)
list(TRANSFORM HOST_FILES   APPEND ".meta" OUTPUT_VARIABLE FLAT_HOST_METADATA_FILES)

list(APPEND FLAT_HOST_METADATA_FILES "${HOST}.meta")

xdsl_ccpp_capgen(HOSTFILES ${FLAT_HOST_METADATA_FILES}
                 SCHEMEFILES ${SCHEME_META_FILES}
                 SUITES ${SUITE_FILES}
                 HOST_NAME ${HOST}
                 DIRECTIVE "acc"
                 OUTPUT_ROOT "${CCPP_CAP_FILES}")
# CCPP_CAPS_LIST is now set (by xdsl_ccpp_capgen, in this scope) to the
# generated Fortran files (ccpp_kinds.F90, flat_cld_suite_cap.F90,
# flat_host_ccpp_cap.F90).

if(XDSL_CCPP_HAVE_FORTRAN)
  if(ARCH STREQUAL "GPU" AND NOT CMAKE_Fortran_COMPILER_ID STREQUAL "NVHPC")
    message(FATAL_ERROR
      "examples/advection_flat_host: ARCH=GPU requires nvfortran for "
      "OpenACC (matching the existing Makefile's own requirement) -- e.g. "
      "`module load nvhpc` on Derecho, or pass "
      "-DCMAKE_Fortran_COMPILER=nvfortran explicitly; got "
      "CMAKE_Fortran_COMPILER_ID=${CMAKE_Fortran_COMPILER_ID}.")
  endif()

  # Create test host library. Unlike examples/advection, there's no orphan
  # dlc_liq.F90-style module here -- this directory's own file listing has
  # no such extra file, so none is added.
  add_library(ADVECTION_FLAT_HOST_TESTLIB OBJECT ${SCHEME_FORTRAN_FILES}
                                                  ${FLAT_HOST_FORTRAN_FILES}
                                                  ccpp_constituent_prop_mod.F90
                                                  ccpp_scheme_utils.F90
                                                  ${CCPP_CAPS_LIST})
  set_target_properties(ADVECTION_FLAT_HOST_TESTLIB PROPERTIES Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/mod)
  target_include_directories(ADVECTION_FLAT_HOST_TESTLIB PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/mod)
  target_link_libraries(ADVECTION_FLAT_HOST_TESTLIB PRIVATE test_utils)

  # Setup test executable with needed dependencies. test_utils' own module
  # include directory reaches this target automatically via its PUBLIC
  # target_include_directories (set where test_utils is defined, in the
  # root CMakeLists.txt) -- linking against it is enough, no need to name
  # that path again here. ${CMAKE_CURRENT_BINARY_DIR}/mod
  # (ADVECTION_FLAT_HOST_TESTLIB's own .mod output) is the one path this
  # target genuinely still needs to be told about directly.
  add_executable(advection_flat.exe test_flat_host_integration.F90 ${HOST}.F90)
  target_link_libraries(advection_flat.exe PRIVATE ADVECTION_FLAT_HOST_TESTLIB test_utils)
  target_include_directories(advection_flat.exe PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/mod)

  # GPU compile flags, scoped to just this example's own targets -- see
  # examples/advection/CMakeLists.txt for the full rationale (identical
  # here, just applied to this example's own target names).
  if(CMAKE_Fortran_COMPILER_ID STREQUAL "NVHPC")
    if(ARCH STREQUAL "GPU")
      target_compile_options(ADVECTION_FLAT_HOST_TESTLIB PRIVATE -mp=gpu -Minfo=accel)
      target_compile_options(advection_flat.exe PRIVATE -mp=gpu -Minfo=accel)
      target_compile_definitions(ADVECTION_FLAT_HOST_TESTLIB PRIVATE USE_GPU)
      target_compile_definitions(advection_flat.exe PRIVATE USE_GPU)
    else()
      target_compile_options(ADVECTION_FLAT_HOST_TESTLIB PRIVATE -noacc)
      target_compile_options(advection_flat.exe PRIVATE -noacc)
    endif()
  endif()

  # Add executable to be called with ctest
  add_test(NAME ctest_advection_flat_host_integration COMMAND advection_flat.exe)
endif()
