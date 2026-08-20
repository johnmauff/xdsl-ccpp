// Test the cpp_header target with the kessler example.
// Verifies that BIND(C) function signatures are correctly translated to
// C++ declarations: character args → const char*/char*, intent(in) scalar
// integers and reals → by-value (int/double), real arrays → double* with
// column-major comments.  Also checks that ccpp_kinds.h typedef alias is
// emitted.  Utility subroutines (ccpp_physics_suite_list) must NOT appear
// in the header since they are not BIND(C).
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/kessler/scheme/kessler_suite.xml --scheme-files examples/kessler/scheme/kessler.meta,examples/kessler/scheme/kessler_update.meta --host-files examples/kessler/host_ftn/kessler_host_mod.meta,examples/kessler/host_ftn/kessler_host_sub.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p "generate-meta-cap,generate-meta-kinds,generate-host-match,generate-arg-ownership,generate-suite-cap,generate-ccpp-cap{bind_c=true},generate-cpp-cap,generate-kinds,strip-ccpp" -t cpp_header | python3 -m filecheck %s

// The cap header file marker and preamble.
// CHECK:      // FILE: Kessler_ccpp_cap.h
// CHECK:      #pragma once
// CHECK:      extern "C" {

// Register: suite_name is const char* (intent in), outputs are char*/int*.
// CHECK-LABEL: void ccpp_register(
// CHECK:          const char*      suite_name,
// CHECK-NEXT:     char*            errmsg,
// CHECK-NEXT:     int*             errflg

// Initialize: same character/integer pattern.
// CHECK-LABEL: void ccpp_init(
// CHECK:          const char*      suite_name,

// Finalize.
// CHECK-LABEL: void ccpp_final(
// CHECK:          const char*      suite_name,

// Run: with the horizontal_dimension convention, all per-call physics args
// (nz, dt, cpair, theta, precl, ...) are host-resolved internally via the
// host module rather than threaded through the framework-level dispatch
// entry point, so the signature collapses to just the standard 6 args.
// CHECK-LABEL: void ccpp_physics_run(
// CHECK:          const char*      suite_name,
// CHECK-NEXT:     const char*      suite_part,
// CHECK-NEXT:     int              col_start,
// CHECK-NEXT:     int              col_end,
// CHECK-NEXT:     char*            errmsg,
// CHECK-NEXT:     int*             errflg

// Timestep initial: now group-scoped (task #28), emitted AFTER ccpp_physics_run
// in generation order -- same physics signature ccpp_physics_run has.
// CHECK-LABEL: void ccpp_physics_timestep_init(
// CHECK:          const char*      suite_name,
// CHECK-NEXT:     const char*      suite_part,
// CHECK-NEXT:     int              col_start,
// CHECK-NEXT:     int              col_end,
// CHECK-NEXT:     char*            errmsg,
// CHECK-NEXT:     int*             errflg

// Timestep final: now group-scoped (task #28 Stage 2), emitted AFTER
// ccpp_physics_timestep_init in generation order -- same physics signature
// ccpp_physics_run/ccpp_physics_timestep_init already have.
// CHECK-LABEL: void ccpp_physics_timestep_final(
// CHECK:          const char*      suite_name,
// CHECK-NEXT:     const char*      suite_part,
// CHECK-NEXT:     int              col_start,
// CHECK-NEXT:     int              col_end,
// CHECK-NEXT:     char*            errmsg,
// CHECK-NEXT:     int*             errflg

// Utility subroutines are NOT BIND(C) → not emitted in the header.
// CHECK-NOT: ccpp_physics_suite_list

// The kinds header file.
// CHECK:      // FILE: ccpp_kinds.h
// CHECK:      #pragma once
// CHECK:      typedef double    kind_phys_t;
