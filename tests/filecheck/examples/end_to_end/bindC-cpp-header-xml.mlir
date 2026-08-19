// Test the cpp_header target with the helloworld example.
// Verifies that BIND(C) function signatures are correctly translated to
// C++ declarations: character args → const char*/char*, intent(in) scalar
// integers → int (by value), intent(out/inout) scalars → int*, real arrays
// → double*.  Also checks that ccpp_kinds.h typedef aliases are emitted.
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/helloworld/hello_world_suite.xml --scheme-files examples/helloworld/hello_scheme.meta,examples/helloworld/temp_adjust.meta --host-files examples/helloworld/hello_world_host.meta,examples/helloworld/hello_world_mod.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p "generate-meta-cap,generate-meta-kinds,generate-host-match,generate-arg-ownership,generate-suite-cap,generate-ccpp-cap{bind_c=true},generate-cpp-cap,generate-kinds,strip-ccpp" -t cpp_header | python3 -m filecheck %s

// The cap header file marker and preamble.
// CHECK:      // FILE: HelloWorld_ccpp_cap.h
// CHECK:      #pragma once
// CHECK:      extern "C" {

// Register: suite_name is const char* (intent in), outputs are char*/int*.
// Character params carry a comment documenting the caller-allocated buffer
// size contract -- xdsl-ccpp's own C++ interop layer is not part of the
// (Fortran-only) CCPP spec, so this generated comment is the sole
// documentation of that contract (Copilot review, PR #80).
// CHECK-LABEL: void ccpp_register(
// CHECK:          const char*      suite_name,  /* null-terminated string, any length */
// CHECK-NEXT:     char*            errmsg,  /* caller must allocate >= 513 bytes (512 + null terminator) */
// CHECK-NEXT:     int*             errflg

// Initialize: same character/integer pattern.
// CHECK-LABEL: void ccpp_init(
// CHECK:          const char*      suite_name,

// Run: intent(in) scalar integers are by-value (no pointer), strings use const/non-const char*.
// CHECK-LABEL: void ccpp_physics_run(
// CHECK:          const char*      suite_name,
// CHECK-NEXT:     const char*      suite_part,
// CHECK-NEXT:     int              col_start,
// CHECK-NEXT:     int              col_end,
// CHECK:          char*            errmsg,
// CHECK-NEXT:     int*             errflg

// Utility subroutines are NOT BIND(C) → not emitted in the header.
// CHECK-NOT: ccpp_physics_suite_list

// The kinds header file.
// CHECK:      // FILE: ccpp_kinds.h
// CHECK:      #pragma once
// CHECK:      typedef double    kind_phys_t;
