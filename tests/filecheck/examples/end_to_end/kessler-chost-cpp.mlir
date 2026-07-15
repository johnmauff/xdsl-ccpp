// Test the cpp_header target for the chost cap with the kessler example.
// Verifies that chost BIND(C) subroutines are translated to C++ declarations
// with correct types: scalar integers and reals by value (int/double), intent(in)
// arrays as const double*, intent(inout/out) arrays as double*, character outputs
// as char*, and errflg as int*.  Also verifies the chost file marker is emitted
// and canonical arg ordering (ncol, nz, scalars, arrays, scheme_name, errmsg, errflg).
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/kessler/scheme/kessler_suite.xml --scheme-files examples/kessler/scheme/kessler.meta,examples/kessler/scheme/kessler_update.meta --host-files examples/kessler/host_cpp/kessler_host_mod.meta,examples/kessler/host_cpp/kessler_host_sub.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p "generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap{bind_c=true},generate-kinds,strip-ccpp" -t cpp_header | python3 -m filecheck %s

// Chost header file marker and preamble.
// CHECK:      // FILE: Kessler_ccpp_chost_cap.h
// CHECK:      #pragma once
// CHECK:      extern "C" {

// Initialize: scalar physics constants by value; errmsg/errflg as pointer outputs.
// CHECK-LABEL: void Kessler_chost_physics_initialize(
// CHECK:           double           lv,
// CHECK:           double           pref,
// CHECK:           double           rhoqr,
// CHECK:           double           gravit,
// CHECK-NEXT:      char*            errmsg,
// CHECK-NEXT:      int*             errflg

// Finalize: only errmsg and errflg.
// CHECK-LABEL: void Kessler_chost_physics_finalize(
// CHECK:           char*            errmsg,
// CHECK-NEXT:      int*             errflg

// Timestep initial: ncol and nz as int; intent(in) array is const double*;
// intent(inout) arrays are double*.
// CHECK-LABEL: void Kessler_chost_physics_timestep_initial(
// CHECK:           int              ncol,
// CHECK-NEXT:      int              nz,
// CHECK:           const double*    temp,
// CHECK:           double*          temp_prev,
// CHECK:           double*          ttend_t,
// CHECK:           char*            errmsg,
// CHECK-NEXT:      int*             errflg

// Timestep final: ncol, nz, then intent(in) arrays, then inout array.
// CHECK-LABEL: void Kessler_chost_physics_timestep_final(
// CHECK:           int              ncol,
// CHECK-NEXT:      int              nz,
// CHECK:           const double*    cpair,
// CHECK:           const double*    z,
// CHECK:           double*          st_energy,
// CHECK:           char*            errmsg,
// CHECK-NEXT:      int*             errflg

// Run: ncol and nz first; col_start and col_end passed through; scalars by value;
// intent(in) arrays as const double*; inout arrays as double*; scheme_name before errmsg before errflg.
// CHECK-LABEL: void Kessler_chost_physics_run(
// CHECK:           int              ncol,
// CHECK-NEXT:      int              nz,
// CHECK-NEXT:      int              col_start,
// CHECK-NEXT:      int              col_end,
// CHECK-NEXT:      double           dt,
// CHECK-NEXT:      int              lyr_surf,
// CHECK-NEXT:      int              lyr_toa,
// CHECK:           const double*    cpair,
// CHECK:           const double*    exner,
// CHECK:           double*          theta,
// CHECK:           double*          precl,
// CHECK:           char*            scheme_name,
// CHECK-NEXT:      char*            errmsg,
// CHECK-NEXT:      int*             errflg
