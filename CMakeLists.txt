cmake_minimum_required(VERSION 3.20)
# LANGUAGES NONE, not Fortran: the cap-generation step below (shelling out
# to xdsl_ccpp) needs no compiler at all, and this lets configure succeed
# in a Python-only environment to at least verify generation -- Fortran is
# enabled conditionally further down, only if a compiler is actually found.
project(xdsl_ccpp_examples LANGUAGES NONE)

# Prototype CMake build for xdsl-ccpp's examples/ directory, patterned
# directly on capgen-v1's own upstream end-to-end-tests/*/CMakeLists.txt
# (see reference/ccpp-framework's test/*_test/CMakeLists.txt for the
# originals these were ported from). Coexists with each example's existing
# hand-written Makefile -- nothing here writes into any example's own
# source directory, and CI's compile-tests.yml still drives the Makefile
# path unchanged for every example except the one(s) opted into this build
# below.
#
# Only examples/nested_suite and examples/var_compat are wired in so far --
# this is an incremental migration, not yet covering every example.

enable_testing()

# find_program, not find_package(Python3): we only need *a* Python
# interpreter to shell out to as a subprocess, and find_package's own
# search heuristics can prefer a framework/registry Python (e.g. Xcode's
# bundled 3.9 on macOS) over whatever's actually on PATH -- which is very
# likely the *wrong* one here, since xdsl_ccpp's own dependencies are
# installed against whatever interpreter `pip install -e .` was actually
# run with (a pyenv/venv-managed one, in the common case), not any
# framework Python. Respecting PATH order (like a user typing `python3`
# themselves, or CI's own `python -m pip install -e .` step) is what's
# actually wanted. Override with -DPython3_EXECUTABLE=... if PATH doesn't
# resolve to the right one.
find_program(Python3_EXECUTABLE python3 REQUIRED)

# This checkout's own repo root -- xdsl_ccpp_capgen.cmake uses this to put
# it first on PYTHONPATH, so an unrelated xdsl-ccpp editable install
# elsewhere on the machine can't shadow this checkout's own code (the same
# precaution every example's existing Makefile already takes).
set(XDSL_CCPP_ROOT "${CMAKE_SOURCE_DIR}")

include(CheckLanguage)
check_language(Fortran)
if(CMAKE_Fortran_COMPILER)
  enable_language(Fortran)
  set(XDSL_CCPP_HAVE_FORTRAN TRUE)
  if(CMAKE_Fortran_COMPILER_ID STREQUAL "GNU")
    add_compile_options(-Wall -Wno-unused-dummy-argument -ffree-line-length-none -O2 -cpp)
  elseif(CMAKE_Fortran_COMPILER_ID MATCHES "Intel")
    add_compile_options(-O2 -fpp)
  elseif(CMAKE_Fortran_COMPILER_ID STREQUAL "NVHPC")
    add_compile_options(-Mfree -Mpreprocess -O2)
  endif()
else()
  set(XDSL_CCPP_HAVE_FORTRAN FALSE)
  message(WARNING
    "No Fortran compiler found -- configuring cap-generation targets only. "
    "Compile/test targets will be skipped. This is expected in a "
    "generation-only environment; a real build needs gfortran/ifx/nvfortran.")
endif()

include(${CMAKE_SOURCE_DIR}/cmake/xdsl_ccpp_capgen.cmake)

if(XDSL_CCPP_HAVE_FORTRAN)
  # Shared test-support module, referenced by every example's own test
  # driver -- same file the hand-written Makefiles already all point at
  # directly by relative path (examples/capgen/host_ftn/test_utils.F90).
  add_library(test_utils OBJECT ${CMAKE_SOURCE_DIR}/examples/capgen/host_ftn/test_utils.F90)
  set_target_properties(test_utils PROPERTIES Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/test_utils_mod)
  target_include_directories(test_utils PUBLIC ${CMAKE_CURRENT_BINARY_DIR}/test_utils_mod)
endif()

add_subdirectory(examples/nested_suite)
add_subdirectory(examples/var_compat)
