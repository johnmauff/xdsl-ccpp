// Test the cpp_header target with the kessler example.
// Verifies that BIND(C) function signatures are correctly translated to
// C++ declarations: character args → const char*/char*, intent(in) scalar
// integers and reals → by-value (int/double), real arrays → double* with
// column-major comments.  Also checks that ccpp_kinds.h typedef alias is
// emitted.  Utility subroutines (ccpp_physics_suite_list) must NOT appear
// in the header since they are not BIND(C).
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/kessler/kessler_suite.xml --scheme-files examples/kessler/kessler.meta,examples/kessler/kessler_update.meta --host-files examples/kessler/kessler_host_mod.meta,examples/kessler/kessler_host_sub.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p "generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap{bind_c=true},generate-kinds,strip-ccpp" -t cpp_header | python3 -m filecheck %s

// The cap header file marker and preamble.
// CHECK:      // FILE: Kessler_ccpp_cap.h
// CHECK:      #pragma once
// CHECK:      extern "C" {

// Register: suite_name is const char* (intent in), outputs are char*/int*.
// CHECK-LABEL: void Kessler_ccpp_physics_register(
// CHECK:          const char*      suite_name,
// CHECK-NEXT:     char*            errmsg,
// CHECK-NEXT:     int*             errflg

// Initialize: same character/integer pattern.
// CHECK-LABEL: void Kessler_ccpp_physics_initialize(
// CHECK:          const char*      suite_name,

// Finalize.
// CHECK-LABEL: void Kessler_ccpp_physics_finalize(
// CHECK:          const char*      suite_name,

// Timestep initial/final.
// CHECK-LABEL: void Kessler_ccpp_physics_timestep_initial(
// CHECK-LABEL: void Kessler_ccpp_physics_timestep_final(

// Run: scalar intent(in) args are by-value; real arrays are double* with
// column-major comments; strings use const char*/char*.
// CHECK-LABEL: void Kessler_ccpp_physics_run(
// CHECK:          const char*      suite_name,
// CHECK-NEXT:     const char*      suite_part,
// CHECK-NEXT:     int              col_start,
// CHECK-NEXT:     int              col_end,
// CHECK-NEXT:     int              nz,
// CHECK-NEXT:     double           dt,
// CHECK:          double*          cpair,
// CHECK:          double*          theta,
// CHECK:          double*          precl,
// CHECK:          char*            errmsg,
// CHECK-NEXT:     int*             errflg

// Utility subroutines are NOT BIND(C) → not emitted in the header.
// CHECK-NOT: ccpp_physics_suite_list

// The kinds header file.
// CHECK:      // FILE: ccpp_kinds.h
// CHECK:      #pragma once
// CHECK:      typedef double    kind_phys_t;
