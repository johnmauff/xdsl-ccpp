// Test the cpp_header target for the tinyddt chost cap with two DDT args.
// Verifies that both DDTs are expanded to C-compatible types:
//   - state_nz, tend_nz as int (integer nz members)
//   - state_temp, tend_dtemp as double* (real array members, intent(inout))
//
// Canonical arg ordering: ncol (is_ncol) → state_nz, tend_nz (is_nz) → others → errmsg → errflg
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/tinyddt/tinyddt_suite.xml --scheme-files examples/tinyddt/tinyddt.meta --host-files examples/tinyddt/host_cpp/tinyddt_host_mod.meta,examples/tinyddt/host_cpp/tinyddt_host_sub.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p "generate-meta-cap,generate-meta-kinds,generate-arg-ownership,generate-suite-cap,generate-ccpp-cap{bind_c=true},generate-cpp-cap,generate-kinds,strip-ccpp" -t cpp_header | python3 -m filecheck %s

// Chost header file marker and preamble.
// CHECK:      // FILE: Tinyddt_ccpp_chost_cap.h
// CHECK:      #pragma once
// CHECK:      extern "C" {

// Register/Initialize/Finalize: only errmsg and errflg.
// CHECK-LABEL: void Tinyddt_chost_physics_register(
// CHECK:            char*            errmsg,
// CHECK-NEXT:       int*             errflg

// CHECK-LABEL: void Tinyddt_chost_physics_initialize(
// CHECK:            char*            errmsg,
// CHECK-NEXT:       int*             errflg

// CHECK-LABEL: void Tinyddt_chost_physics_finalize(
// CHECK:            char*            errmsg,
// CHECK-NEXT:       int*             errflg

// Run: ncol; state_nz and tend_nz (is_nz before others); col_start/col_end;
//      state_temp; tend_dtemp; errmsg; errflg.
// CHECK-LABEL: void Tinyddt_chost_physics_run(
// CHECK:            int              ncol,
// CHECK:            int              state_nz,
// CHECK:            int              tend_nz,
// CHECK:            int              col_start,
// CHECK:            int              col_end,
// CHECK:            double*          state_temp,
// CHECK:            double*          tend_dtemp,
// CHECK:            char*            errmsg,
// CHECK-NEXT:       int*             errflg
