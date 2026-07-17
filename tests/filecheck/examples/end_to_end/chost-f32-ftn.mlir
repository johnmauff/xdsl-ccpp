// Test that chost Fortran cap emits real(c_float) when kind_phys maps to REAL32.
// Verifies the precision fix: the chost cap must respect the actual float width
// rather than always emitting real(c_double).
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/kessler/scheme/kessler_suite.xml --scheme-files examples/kessler/scheme/kessler.meta,examples/kessler/scheme/kessler_update.meta --host-files examples/kessler/host_cpp/kessler_host_mod.meta,examples/kessler/host_cpp/kessler_host_sub.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p "generate-meta-cap,generate-meta-kinds{extra_kind=kind_phys extra_iso=REAL32},generate-suite-cap,generate-ccpp-cap{bind_c=true},generate-cpp-cap,generate-kinds,strip-ccpp" -t ftn | python3 -m filecheck %s

// Chost cap module starts here — anchor all subsequent checks within it.
// CHECK-LABEL: module Kessler_ccpp_chost_cap

// Scalar real args (rank 0) in initialize use real(c_float), not c_double.
// CHECK-LABEL:   subroutine Kessler_chost_physics_initialize(lv, pref, rhoqr, gravit, errmsg, errflg) &
// CHECK:           real(c_float), value, intent(in) :: lv
// CHECK:           real(c_float), value, intent(in) :: gravit

// 2-D array args in timestep_initial use real(c_float).
// CHECK-LABEL:   subroutine Kessler_chost_physics_timestep_initial(
// CHECK:           real(c_float), target, intent(in) :: temp(ncol, nz)
// CHECK:           real(c_float), target, intent(inout) :: temp_prev(ncol, nz)

// Run: scalar dt and 2-D arrays all use real(c_float).
// CHECK-LABEL:   subroutine Kessler_chost_physics_run(
// CHECK:           real(c_float), value, intent(in) :: dt
// CHECK:           real(c_float), target, intent(in) :: cpair(ncol, nz)
// CHECK:           real(c_float), target, intent(inout) :: theta(ncol, nz)
// CHECK:           real(c_float), target, intent(inout) :: precl(ncol)

// ccpp_kinds uses REAL32 — verifies the kind map was applied end-to-end.
// CHECK-LABEL: module ccpp_kinds
// CHECK:         use ISO_FORTRAN_ENV, only: kind_phys => REAL32
