// Test the cpp_header target with the helloworld example.
// Verifies that BIND(C) function signatures are correctly translated to
// C++ declarations: character args → const char*/char*, intent(in) scalar
// integers → int (by value), intent(out/inout) scalars → int*, real arrays
// → double*.  Also checks that ccpp_kinds.h typedef aliases are emitted.
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/helloworld/hello_world_suite.xml --scheme-files examples/helloworld/hello_scheme.meta,examples/helloworld/temp_adjust.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p "generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap{bind_c=true},generate-cpp-cap,generate-kinds,strip-ccpp" -t cpp_header | python3 -m filecheck %s

// The cap header file marker and preamble.
// CHECK:      // FILE: HelloWorld_ccpp_cap.h
// CHECK:      #pragma once
// CHECK:      extern "C" {

// Register: suite_name is const char* (intent in), outputs are char*/int*.
// CHECK-LABEL: void HelloWorld_ccpp_physics_register(
// CHECK:          const char*      suite_name,
// CHECK-NEXT:     char*            errmsg,
// CHECK-NEXT:     int*             errflg

// Initialize: same character/integer pattern.
// CHECK-LABEL: void HelloWorld_ccpp_physics_initialize(
// CHECK:          const char*      suite_name,

// Run: intent(in) scalar integers are by-value (no pointer), strings use const/non-const char*.
// CHECK-LABEL: void HelloWorld_ccpp_physics_run(
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
