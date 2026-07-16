// Test chost cap Fortran output for the tinyddt example with DDT flattening.
// Verifies that a scheme argument of derived type tiny_state_t is expanded into
// individual scalar/array BIND(C) args in the generated chost subroutine:
//   - state_nz  : integer(c_int), value, intent(in)   — the nz member
//   - state_temp: real(c_double), target, intent(inout) :: state_temp(ncol, state_nz)
//                 — the temp member dimensioned by ncol (injected) and state_nz
//
// The chost wrapper reconstructs the tiny_state_t local variable from the flat
// args, calls the suite cap, then writes back inout members.
//
// Canonical arg ordering: ncol (is_ncol) → state_nz (is_nz) → others → errmsg → errflg
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/tinyddt/tinyddt_suite.xml --scheme-files examples/tinyddt/tinyddt.meta --host-files examples/tinyddt/host_cpp/tinyddt_host_mod.meta,examples/tinyddt/host_cpp/tinyddt_host_sub.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p "generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap{bind_c=true},generate-kinds,strip-ccpp" -t ftn | python3 -m filecheck %s

// Module header: uses iso_c_binding, tiny_state_t, and imports suite cap entry point.
// CHECK-LABEL: module Tinyddt_ccpp_chost_cap
// CHECK:         use ccpp_kinds, only: kind_phys
// CHECK:         use iso_c_binding
// CHECK:         use tinyddt, only: tiny_state_t
// CHECK:         use tinyddt_suite_cap, only: tinyddt_suite_suite_physics
// CHECK:         implicit none
// CHECK:         private

// Run: ncol injected; state_nz (is_nz) before col_start/col_end; DDT expanded.
// CHECK-LABEL:   subroutine Tinyddt_chost_physics_run(
// CHECK:             bind(C, name='Tinyddt_chost_physics_run')
// CHECK:           integer(c_int), value, intent(in) :: ncol
// CHECK:           integer(c_int), value, intent(in) :: state_nz
// CHECK:           integer(c_int), value, intent(in) :: col_start
// CHECK:           integer(c_int), value, intent(in) :: col_end
// CHECK:           real(c_double), target, intent(inout) :: state_temp(ncol, state_nz)
// CHECK:           character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK:           integer(c_int),               intent(out) :: errflg

// DDT local var declaration.
// CHECK:           type(tiny_state_t) :: state_local

// DDT reconstruction from flat args.
// CHECK:           state_local%nz = state_nz
// CHECK:           allocate(state_local%temp(ncol, state_nz))
// CHECK:           state_local%temp = real(state_temp, kind_phys)

// Suite cap call passes the reconstructed DDT.
// CHECK:           call tinyddt_suite_suite_physics(
// CHECK:               col_start, col_end, state_local,

// Writeback of inout DDT members after the call.
// CHECK:           state_temp = real(state_local%temp, c_double)
// CHECK:           deallocate(state_local%temp)

// CHECK:         end subroutine Tinyddt_chost_physics_run
