// Test explicit_args mode of generate-ccpp-cap for the kessler example.
// Verifies that the generated chost cap module:
//   - uses iso_c_binding and delegates to the suite cap
//   - injects ncol and passes col_start/col_end through for the run subroutine
//   - emits bind(C) subroutines with correct Fortran types for every lifecycle
//   - passes col_start and col_end directly in suite cap calls
//   - converts Fortran character buffers to C strings via copy loops
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/kessler/scheme/kessler_suite.xml --scheme-files examples/kessler/scheme/kessler.meta,examples/kessler/scheme/kessler_update.meta --host-files examples/kessler/host_ftn/kessler_host_mod.meta,examples/kessler/host_ftn/kessler_host_sub.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p "generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap{bind_c=true explicit_args=true},generate-kinds,strip-ccpp" -t ftn | python3 -m filecheck %s

// Module header: uses iso_c_binding and imports only suite cap entry points.
// CHECK-LABEL: module Kessler_ccpp_chost_cap
// CHECK:         use ccpp_kinds, only: kind_phys
// CHECK:         use iso_c_binding
// CHECK:         use kessler_suite_cap, only: kessler_suite_suite_register
// CHECK:         use kessler_suite_cap, only: kessler_suite_suite_initialize
// CHECK:         use kessler_suite_cap, only: kessler_suite_suite_physics
// CHECK:         implicit none
// CHECK:         private

// Initialize: scalar physics constants passed by value with real() cast.
// CHECK-LABEL:   subroutine Kessler_chost_physics_initialize(lv, pref, rhoqr, gravit, errmsg, errflg) &
// CHECK:             bind(C, name='Kessler_chost_physics_initialize')
// CHECK:           real(c_double), value, intent(in) :: lv
// CHECK:           real(c_double), value, intent(in) :: gravit
// CHECK:           character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK:           integer(c_int),               intent(out) :: errflg
// CHECK:           character(len=512) :: errmsg_f
// CHECK:           call kessler_suite_suite_initialize(
// CHECK:               real(lv, kind_phys), real(pref, kind_phys), real(rhoqr, kind_phys),
// CHECK:               real(gravit, kind_phys), errmsg_f, errflg)

// Timestep initial: ncol and nz as value integers; 2-D arrays dimensioned (ncol, nz).
// CHECK-LABEL:   subroutine Kessler_chost_physics_timestep_initial(
// CHECK:             bind(C, name='Kessler_chost_physics_timestep_initial')
// CHECK:           integer(c_int), value, intent(in) :: ncol
// CHECK:           integer(c_int), value, intent(in) :: nz
// CHECK:           real(c_double), target, intent(in) :: temp(ncol, nz)
// CHECK:           real(c_double), target, intent(inout) :: temp_prev(ncol, nz)
// CHECK:           real(c_double), target, intent(inout) :: ttend_t(ncol, nz)
// CHECK:           character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK:           integer(c_int),               intent(out) :: errflg

// Run: ncol injected; col_start and col_end passed through as value ints.
// CHECK-LABEL:   subroutine Kessler_chost_physics_run(
// CHECK:             bind(C, name='Kessler_chost_physics_run')
// CHECK:           integer(c_int), value, intent(in) :: ncol
// CHECK:           integer(c_int), value, intent(in) :: nz
// CHECK:           integer(c_int), value, intent(in) :: col_start
// CHECK:           integer(c_int), value, intent(in) :: col_end
// CHECK:           real(c_double), value, intent(in) :: dt
// CHECK:           integer(c_int), value, intent(in) :: lyr_surf
// CHECK:           integer(c_int), value, intent(in) :: lyr_toa
// CHECK:           real(c_double), target, intent(in) :: cpair(ncol, nz)
// CHECK:           real(c_double), target, intent(in) :: exner(ncol, nz)
// CHECK:           real(c_double), target, intent(inout) :: theta(ncol, nz)
// CHECK:           real(c_double), target, intent(inout) :: precl(ncol)
// CHECK:           character(kind=c_char, len=1), intent(out) :: scheme_name(*)
// CHECK:           character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK:           integer(c_int),               intent(out) :: errflg
// CHECK:           character(len=64)  :: scheme_name_f
// CHECK:           character(len=512) :: errmsg_f

// Run call: col_start and col_end passed through; dt cast with real().
// CHECK:           call kessler_suite_suite_physics(
// CHECK:               col_start, col_end, nz, real(dt, kind_phys), lyr_surf, lyr_toa,
// CHECK:               scheme_name_f, errmsg_f, errflg)

// C-string copy loop for scheme_name appears before errmsg copy.
// CHECK:           do i = 1, len_trim(scheme_name_f)
// CHECK:             scheme_name(i) = scheme_name_f(i:i)
// CHECK:           end do
// CHECK:           scheme_name(len_trim(scheme_name_f)+1) = c_null_char
// CHECK:           do i = 1, len_trim(errmsg_f)
// CHECK:             errmsg(i) = errmsg_f(i:i)
// CHECK:           end do
// CHECK:           errmsg(len_trim(errmsg_f)+1) = c_null_char

// CHECK-LABEL: end module Kessler_ccpp_chost_cap
