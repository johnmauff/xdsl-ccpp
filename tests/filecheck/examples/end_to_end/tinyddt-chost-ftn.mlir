// Test chost cap Fortran output for the tinyddt example with two DDT args.
// Verifies that both tiny_state_t and tiny_tend_t are each expanded into
// individual scalar/array BIND(C) args in the generated chost subroutine.
//
// Canonical arg ordering: ncol (is_ncol) → state_nz, tend_nz (is_nz) → others → errmsg → errflg
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/tinyddt/tinyddt_suite.xml --scheme-files examples/tinyddt/tinyddt.meta --host-files examples/tinyddt/host_cpp/tinyddt_host_mod.meta,examples/tinyddt/host_cpp/tinyddt_host_sub.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p "generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap{bind_c=true},generate-cpp-cap,generate-kinds,strip-ccpp" -t ftn | python3 -m filecheck %s

// Module header: uses both DDT types from tinyddt.
// CHECK-LABEL: module Tinyddt_ccpp_chost_cap
// CHECK:         use ccpp_kinds, only: kind_phys
// CHECK:         use iso_c_binding
// CHECK:         use tinyddt, only: tiny_state_t
// CHECK:         use tinyddt, only: tiny_tend_t
// CHECK:         use tinyddt_suite_cap, only: tinyddt_suite_suite_physics
// CHECK:         implicit none
// CHECK:         private

// Run: ncol injected; state_nz and tend_nz (both is_nz) before col_start/col_end.
// CHECK-LABEL:   subroutine Tinyddt_chost_physics_run(
// CHECK:             bind(C, name='Tinyddt_chost_physics_run')
// CHECK:           integer(c_int), value, intent(in) :: ncol
// CHECK:           integer(c_int), value, intent(in) :: state_nz
// CHECK:           integer(c_int), value, intent(in) :: tend_nz
// CHECK:           integer(c_int), value, intent(in) :: col_start
// CHECK:           integer(c_int), value, intent(in) :: col_end
// CHECK:           real(c_double), target, intent(inout) :: state_temp(ncol, state_nz)
// CHECK:           real(c_double), target, intent(inout) :: tend_dtemp(ncol, tend_nz)
// CHECK:           character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK:           integer(c_int),               intent(out) :: errflg

// Both DDT local var declarations.
// CHECK:           type(tiny_state_t) :: state_local
// CHECK:           type(tiny_tend_t) :: tend_local

// DDT reconstruction: state first, then tend.
// CHECK:           state_local%nz = state_nz
// CHECK:           allocate(state_local%temp(ncol, state_nz))
// CHECK:           state_local%temp = real(state_temp, kind_phys)
// CHECK:           tend_local%nz = tend_nz
// CHECK:           allocate(tend_local%dtemp(ncol, tend_nz))
// CHECK:           tend_local%dtemp = real(tend_dtemp, kind_phys)

// Suite cap call passes both reconstructed DDTs.
// CHECK:           call tinyddt_suite_suite_physics(
// CHECK:               col_start, col_end, state_local, tend_local,

// Writeback of inout members for both DDTs.
// CHECK:           state_temp = real(state_local%temp, c_double)
// CHECK:           deallocate(state_local%temp)
// CHECK:           tend_dtemp = real(tend_local%dtemp, c_double)
// CHECK:           deallocate(tend_local%dtemp)

// CHECK:         end subroutine Tinyddt_chost_physics_run
