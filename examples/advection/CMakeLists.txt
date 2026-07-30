#------------------------------------------------------------------------------
#
# advection: a cloud advection example with four schemes, one of which
# (apply_constituent_tendencies) is invoked twice in the suite. Also GPU-
# capable via generated OpenACC directives ("--directive acc") -- no
# upstream capgen-v1 end-to-end-tests example exercises --directive, so
# this file is written from scratch, like examples/tinyddt's, rather than
# ported from a real upstream original.
#
# Cap generation always passes --directive acc, regardless of target
# architecture: the generated Fortran source's "!$acc" comments are inert
# on a plain Fortran compile (no special flag needed to make a compiler
# ignore an unrecognized directive comment) and only take effect once the
# right GPU compile flags are added below -- so the SAME generated caps
# serve both the CPU and GPU builds, exactly like the existing Makefile's
# own `make caps` (which always passes --directive acc too, independent of
# ARCH=CPU|GPU).
#
# ARCH mirrors the existing Makefile's own ARCH=CPU|GPU variable exactly
# (same name, same two values). It's a CMake CACHE variable, so it's
# project-wide, not scoped to just this example -- examples/advection_flat_host
# (also GPU-capable) intentionally reuses this same variable rather than
# defining its own, so -DARCH=GPU builds both for GPU together as a single
# switch instead of needing one flag per example.
# GPU currently requires nvfortran for OpenACC, matching that Makefile's own
# hard requirement -- see this repo's top-level README for the full GPU
# configure/build recipe (module load, cache variables, etc).
#
#------------------------------------------------------------------------------
set(ARCH "CPU" CACHE STRING
    "examples/advection target architecture: CPU or GPU (OpenACC, requires nvfortran)")
set_property(CACHE ARCH PROPERTY STRINGS CPU GPU)

set(SCHEME_FILES "const_indices" "cld_liq" "apply_constituent_tendencies" "cld_ice")
set(HOST_FILES   "test_host_data" "test_host_mod")
set(SUITE_FILES  "cld_suite.xml")
set(HOST "test_host")

set(CCPP_CAP_FILES "${CMAKE_CURRENT_BINARY_DIR}/ccpp")

list(TRANSFORM SCHEME_FILES APPEND ".F90"  OUTPUT_VARIABLE SCHEME_FORTRAN_FILES)
list(TRANSFORM SCHEME_FILES APPEND ".meta" OUTPUT_VARIABLE SCHEME_META_FILES)
list(TRANSFORM HOST_FILES   APPEND ".F90"  OUTPUT_VARIABLE ADVECTION_HOST_FORTRAN_FILES)
list(TRANSFORM HOST_FILES   APPEND ".meta" OUTPUT_VARIABLE ADVECTION_HOST_METADATA_FILES)

list(APPEND ADVECTION_HOST_METADATA_FILES "${HOST}.meta")

xdsl_ccpp_capgen(HOSTFILES ${ADVECTION_HOST_METADATA_FILES}
                 SCHEMEFILES ${SCHEME_META_FILES}
                 SUITES ${SUITE_FILES}
                 HOST_NAME ${HOST}
                 DIRECTIVE "acc"
                 OUTPUT_ROOT "${CCPP_CAP_FILES}")
# CCPP_CAPS_LIST is now set (by xdsl_ccpp_capgen, in this scope) to the
# generated Fortran files (ccpp_kinds.F90, cld_suite_cap.F90,
# test_host_ccpp_cap.F90).

if(XDSL_CCPP_HAVE_FORTRAN)
  if(ARCH STREQUAL "GPU" AND NOT CMAKE_Fortran_COMPILER_ID STREQUAL "NVHPC")
    message(FATAL_ERROR
      "examples/advection: ARCH=GPU requires nvfortran for OpenACC "
      "(matching the existing Makefile's own requirement) -- e.g. "
      "`module load nvhpc` on Derecho, or pass "
      "-DCMAKE_Fortran_COMPILER=nvfortran explicitly; got "
      "CMAKE_Fortran_COMPILER_ID=${CMAKE_Fortran_COMPILER_ID}.")
  endif()

  # Create test host library. dlc_liq.F90 has no corresponding .meta (it's
  # not part of the suite -- see its own file header comment: "Test
  # parameterization with a runtime constituents properties object outside
  # of the register phase") but the existing Makefile compiles it into the
  # same library unconditionally, so this does too, for parity.
  add_library(ADVECTION_TESTLIB OBJECT ${SCHEME_FORTRAN_FILES}
                                        ${ADVECTION_HOST_FORTRAN_FILES}
                                        ccpp_constituent_prop_mod.F90
                                        ccpp_scheme_utils.F90
                                        dlc_liq.F90
                                        ${CCPP_CAPS_LIST})
  set_target_properties(ADVECTION_TESTLIB PROPERTIES Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/mod)
  target_include_directories(ADVECTION_TESTLIB PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/mod)
  target_link_libraries(ADVECTION_TESTLIB PRIVATE test_utils)

  # Setup test executable with needed dependencies. test_utils' own module
  # include directory reaches this target automatically via its PUBLIC
  # target_include_directories (set where test_utils is defined, in the
  # root CMakeLists.txt) -- linking against it is enough, no need to name
  # that path again here. ${CMAKE_CURRENT_BINARY_DIR}/mod (ADVECTION_TESTLIB's
  # own .mod output) is the one path this target genuinely still needs to
  # be told about directly.
  add_executable(advection.exe test_advection_host_integration.F90 ${HOST}.F90)
  target_link_libraries(advection.exe PRIVATE ADVECTION_TESTLIB test_utils)
  target_include_directories(advection.exe PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/mod)

  # GPU compile flags, scoped to just this example's own targets (not the
  # root CMakeLists.txt's directory-wide add_compile_options, which stays
  # architecture-agnostic) -- mirrors the existing Makefile's own nvfortran
  # FC_GPU/FC_CPU flag pair. Only the NVHPC branch is reachable given the
  # FATAL_ERROR guard above (ifx/gnu GPU support is a possible future
  # extension the Makefile leaves unreachable too, via its own
  # ARCH=GPU-requires-nvfortran check).
  if(CMAKE_Fortran_COMPILER_ID STREQUAL "NVHPC")
    if(ARCH STREQUAL "GPU")
      target_compile_options(ADVECTION_TESTLIB PRIVATE -mp=gpu -Minfo=accel)
      target_compile_options(advection.exe PRIVATE -mp=gpu -Minfo=accel)
      target_compile_definitions(ADVECTION_TESTLIB PRIVATE USE_GPU)
      target_compile_definitions(advection.exe PRIVATE USE_GPU)
    else()
      # -noacc: nvfortran recognizes "!$acc" directives by default, so a
      # plain CPU build needs this to explicitly ignore them (unlike
      # gfortran/ifx, which never process OpenACC and so need no
      # equivalent flag) -- matching the existing Makefile's own nvfortran
      # FC_CPU flags exactly.
      target_compile_options(ADVECTION_TESTLIB PRIVATE -noacc)
      target_compile_options(advection.exe PRIVATE -noacc)
    endif()
  endif()

  # Add executable to be called with ctest
  add_test(NAME ctest_advection_host_integration COMMAND advection.exe)
endif()
