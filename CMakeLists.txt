cmake_minimum_required(VERSION 3.20)
# LANGUAGES NONE, not Fortran: the cap-generation step below (shelling out
# to xdsl_ccpp) needs no compiler at all, and this lets configure succeed
# in a Python-only environment to at least verify generation -- Fortran is
# enabled conditionally further down, only if a compiler is actually found.
project(xdsl_ccpp_examples LANGUAGES NONE)

# CMake build for xdsl-ccpp's examples/ directory, patterned directly on
# capgen-v1's own upstream end-to-end-tests/*/CMakeLists.txt (see
# https://github.com/NCAR/ccpp-framework's own test/*_test/CMakeLists.txt
# for the originals nested_suite/var_compat were ported from) where a real
# upstream original exists; the chost-only examples (tinyddt, kessler's
# chost/bind-c drivers, nestedddt, chararg, constadv, constprop, ddthost/
# capgen's chost drivers, helloworld) have no upstream analog and were
# written from scratch, each example's own CMakeLists.txt says so directly.
#
# This is now the SOLE build system for every compilable example --
# per-example hand-written Makefiles (and the Makefile-driven
# compile-tests.yml CI workflow) have been removed; this repo-wide CMake
# build superseded them once every example that has anything to compile was
# ported over. examples/atmospheric_physics is the only example directory
# with no CMakeLists.txt, because it has nothing to compile at all (scheme-
# only Python suite definitions, exercised by pytest directly, not a
# Makefile/executable in the first place).
#
# Wired in: examples/nested_suite, examples/var_compat, examples/tinyddt,
# examples/advection, examples/advection_flat_host, examples/kessler,
# examples/nestedddt, examples/chararg, examples/constadv,
# examples/constprop, examples/ddthost, examples/capgen,
# examples/helloworld, examples/chunked_data, examples/constituents_dim
# (as of 2026-08-13, after fixing four real xdsl_ccpp capability gaps its cap
# generation hit -- see examples/constituents_dim/CMakeLists.txt's own header
# comment for the specific gaps and fixes), and examples/opt_arg (as of
# 2026-08-13, after fixing the two confirmed bugs described in its own
# CMakeLists.txt -- the dead `active` property and the timestep-phase
# lifecycle-signature gap, both in ccpp_cap_refactor_plan.md's own "opt_arg's
# dead active property" backlog entry), and examples/suite_allocate (as of
# 2026-08-17, after fixing the host-output-var discard bug described in
# ccpp_cap_refactor_plan.md's own "suite_allocate" backlog entry -- checksum
# was being discarded into a throwaway local instead of written back to the
# host).
#
# examples/instances (as of 2026-08-18, after implementing real capgen-v1's
# own multi-instance model -- see ccpp_cap_refactor_plan.md's "instances/
# instances_advection" backlog entry, Stages 1-5), and examples/
# instances_advection (as of 2026-08-18, task #35 of the same backlog
# entry -- the constituent-registration API gained the same kind of
# per-instance awareness the suite lifecycle already had) are now wired in
# below.

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
  # Wrapped in a COMPILE_LANGUAGE:Fortran generator expression, not passed
  # bare: add_compile_options() applies directory-wide to every enabled
  # language, and these flags are Fortran-compiler-specific (e.g.
  # -ffree-line-length-none/-Wno-unused-dummy-argument mean nothing to a C++
  # compiler and can break compiling the chost examples' C++ sources once
  # CXX is also enabled below).
  #
  # Each generator expression is quoted -- without quotes, CMake's own
  # unquoted-argument list splitting treats every ';' inside as a separate
  # argument boundary, tearing the genex apart before it's ever evaluated
  # (confirmed: this broke -cpp into a bare, unclosed "-cpp>" token that got
  # passed to gfortran literally, which rejected it as an unrecognized
  # flag). Quoting keeps the whole "$<...:a;b;c>" string intact as one
  # argument, which add_compile_options()/generator expressions then expand
  # into separate flags correctly at build time.
  if(CMAKE_Fortran_COMPILER_ID STREQUAL "GNU")
    add_compile_options("$<$<COMPILE_LANGUAGE:Fortran>:-Wall;-Wno-unused-dummy-argument;-ffree-line-length-none;-O2;-cpp>")
  elseif(CMAKE_Fortran_COMPILER_ID MATCHES "Intel")
    add_compile_options("$<$<COMPILE_LANGUAGE:Fortran>:-O2;-fpp>")
  elseif(CMAKE_Fortran_COMPILER_ID STREQUAL "NVHPC")
    add_compile_options("$<$<COMPILE_LANGUAGE:Fortran>:-Mfree;-Mpreprocess;-O2>")
  endif()
else()
  set(XDSL_CCPP_HAVE_FORTRAN FALSE)
  message(WARNING
    "No Fortran compiler found -- configuring cap-generation targets only. "
    "Compile/test targets will be skipped. This is expected in a "
    "generation-only environment; a real build needs gfortran/ifx/nvfortran.")
endif()

# Needed by the chost/C++-host examples (e.g. examples/tinyddt) -- their
# driver is genuine C++, not Fortran calling into BIND(C) from the C side.
check_language(CXX)
if(CMAKE_CXX_COMPILER)
  enable_language(CXX)
  set(XDSL_CCPP_HAVE_CXX TRUE)
  # Pinned explicitly, not left to the compiler's own default dialect:
  # xdsl_ccpp's generated chost headers and the hand-written C++ drivers
  # that use them rely on C++11 features (constexpr, default member
  # initializers, aggregate-style return-statement initialization).
  # Confirmed this actually matters, not just theoretical -- some default
  # compiler configurations (e.g. this sandbox's clang++) pick a
  # pre-C++11 dialect unless told otherwise, which fails to compile
  # examples/tinyddt's driver with "unknown type name 'constexpr'". Global
  # CMAKE_CXX_STANDARD, not a per-target property, so every current and
  # future chost example gets this without needing to remember it again.
  set(CMAKE_CXX_STANDARD 11)
  set(CMAKE_CXX_STANDARD_REQUIRED ON)
else()
  set(XDSL_CCPP_HAVE_CXX FALSE)
  message(WARNING
    "No C++ compiler found -- chost example compile/test targets that need "
    "one will be skipped.")
endif()

# Needed by examples/kessler, the first example with plain C sources (its
# shared/*.c RNG/init-data helpers) -- no other example ported so far needs
# a C compiler at all.
check_language(C)
if(CMAKE_C_COMPILER)
  enable_language(C)
  set(XDSL_CCPP_HAVE_C TRUE)
else()
  set(XDSL_CCPP_HAVE_C FALSE)
  message(WARNING
    "No C compiler found -- example compile/test targets that need one "
    "will be skipped.")
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

# examples/shared/ccpp_constituent_prop_mod.F90 / ccpp_scheme_utils.F90 (see
# that file's own header comment) are the single source for this
# constituent-registration support stub, but are NOT built as a shared
# library here the way test_utils is -- unlike test_utils, they `use
# ccpp_kinds`, which is itself a per-example *generated* file (part of each
# example's own xdsl_ccpp_capgen() output, in that example's own build
# directory, not a single static file this root scope could depend on
# before any example subdirectory has even run its own cap generation).
# Confirmed the hard way: building them as their own root-level target
# fails with "Cannot open module file 'ccpp_kinds.mod'" since no example's
# ccpp_kinds.F90 exists yet at that point. Each example that needs them
# instead compiles these same two source files directly into its own
# TESTLIB, alongside that example's own ${CCPP_CAPS_LIST} (which includes
# its own ccpp_kinds.F90) -- CMake's own Fortran dependency scanner already
# orders compilation correctly within one target, exactly as it already
# does today for ${SCHEME_FORTRAN_FILES} against the same target's own
# ccpp_kinds.F90.

add_subdirectory(examples/nested_suite)
add_subdirectory(examples/var_compat)
add_subdirectory(examples/tinyddt)
add_subdirectory(examples/advection)
add_subdirectory(examples/advection_flat_host)
add_subdirectory(examples/kessler)
add_subdirectory(examples/nestedddt)
add_subdirectory(examples/chararg)
add_subdirectory(examples/constadv)
add_subdirectory(examples/constprop)
add_subdirectory(examples/ddthost)
add_subdirectory(examples/capgen)
add_subdirectory(examples/helloworld)
add_subdirectory(examples/chunked_data)
add_subdirectory(examples/constituents_dim)
add_subdirectory(examples/opt_arg)
add_subdirectory(examples/suite_allocate)
add_subdirectory(examples/instances)
add_subdirectory(examples/instances_advection)
