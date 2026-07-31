#------------------------------------------------------------------------------
#
# helloworld: minimal two-scheme introductory example (hello_scheme,
# temp_adjust). Single Fortran-only driver -- hello_world_host.F90 contains
# both a verification module and the program entry point in one file, no
# separate TESTLIB needed (only one executable, nothing else shares its
# compiled objects). No ARCH/GPU distinction and no upstream capgen-v1
# equivalent by name (see this repo's own README for confirmation: no
# "helloworld" test exists in capgen-v1's own end-to-end-tests; it's
# xdsl_ccpp's own bespoke introductory example), so this is written from
# scratch rather than ported from a real original.
#
# --kind-map kind_dyn:REAL32 supplements the built-in kind table to
# demonstrate cap-generation's kind-mismatch/kind-cast handling (the host's
# own kind_phys vs. hello_scheme's declared kind_dyn for the same
# standard_name) -- matches the existing Makefile's own CCPP_XDSL
# invocation exactly.
#
#------------------------------------------------------------------------------
set(CCPP_CAP_FILES "${CMAKE_CURRENT_BINARY_DIR}/ccpp")

xdsl_ccpp_capgen(HOSTFILES hello_world_host.meta hello_world_mod.meta
                 SCHEMEFILES hello_scheme.meta temp_adjust.meta
                 SUITES hello_world_suite.xml
                 KIND_MAP "kind_dyn:REAL32"
                 OUTPUT_ROOT "${CCPP_CAP_FILES}")
# CCPP_CAPS_LIST is now set (by xdsl_ccpp_capgen, in this scope) to the
# generated Fortran files (ccpp_kinds.F90, hello_world_suite_cap.F90,
# HelloWorld_ccpp_cap.F90).

if(XDSL_CCPP_HAVE_FORTRAN)
  add_executable(helloworld.exe
    ${CCPP_CAP_FILES}/ccpp_kinds.F90
    hello_world_mod.F90
    hello_scheme.F90
    temp_adjust.F90
    ${CCPP_CAP_FILES}/hello_world_suite_cap.F90
    ${CCPP_CAP_FILES}/HelloWorld_ccpp_cap.F90
    hello_world_host.F90)
  set_target_properties(helloworld.exe PROPERTIES Fortran_MODULE_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/mod)
  target_include_directories(helloworld.exe PRIVATE ${CMAKE_CURRENT_BINARY_DIR}/mod)

  add_test(NAME ctest_helloworld COMMAND helloworld.exe)
  # hello_world_host.F90's own compare_temp() check (see that file, around
  # line 74) never sets a nonzero exit code on a wrong-answer result -- it
  # only ever `stop`s on an actual CCPP framework error (errflg /= 0), which
  # is a completely separate failure mode. The ONLY way to detect a wrong-
  # answer result is the printed text itself ("Answers are correct!" vs.
  # "Answers are not correct!"), exactly what the existing Makefile's own
  # `check` target does via `grep -q "Answers are correct"`. Without this
  # property, ctest's default exit-code-only pass criterion would report
  # PASS unconditionally, regardless of whether the physics answers were
  # actually right -- confirmed directly: this genuinely happened here
  # while temp_midpoints briefly used mismatched units, well after this
  # test had already started reporting PASS.
  set_tests_properties(ctest_helloworld PROPERTIES
    PASS_REGULAR_EXPRESSION "Answers are correct!")
endif()
