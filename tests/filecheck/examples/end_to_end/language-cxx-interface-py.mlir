// End-to-end test: Fortran host calling one Fortran scheme and one C++ scheme.
// Verifies that the suite cap:
//   - uses iso_c_binding (triggered by C++ scheme presence)
//   - imports the Fortran scheme via a normal USE statement
//   - does NOT emit a USE for the C++ scheme module
//   - emits a BIND(C) interface block for the C++ scheme
//   - declares C-interoperable types inside the interface block
//   - calls both schemes inside the physics subroutine
//
// RUN: python3 tests/filecheck/examples/language_suite.py | python3 -m xdsl_ccpp.tools.ccpp_opt -p generate-meta-cap,generate-meta-kinds,generate-arg-ownership,generate-suite-cap,generate-ccpp-cap,generate-cpp-cap,generate-kinds,strip-ccpp -t ftn | python3 -m filecheck %s

// Suite cap module header: iso_c_binding from C++ scheme; Fortran scheme imported normally.
// CHECK-LABEL: module tiny_suite_cap
// CHECK:         use ccpp_kinds
// CHECK:         use iso_c_binding
// CHECK:         use tiny_fortran_scheme, only: tiny_fortran_scheme_run
// CHECK-NOT:     use tiny_cxx_scheme

// BIND(C) interface block for the C++ scheme.
// CHECK:       interface
// CHECK:         subroutine tiny_cxx_scheme_run(ncol, temp, errmsg, errflg) &
// CHECK:             BIND(C, name='tiny_cxx_scheme_run')
// CHECK:             use iso_c_binding
// CHECK:           integer(c_int), value, intent(in) :: ncol
// CHECK:           real(c_double), intent(inout) :: temp(*)
// CHECK:           character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK:           integer(c_int), intent(out) :: errflg
// CHECK:         end subroutine tiny_cxx_scheme_run
// CHECK:       end interface

// Physics subroutine calls both schemes.
// CHECK-LABEL:   subroutine tiny_suite_suite_physics(
// CHECK:           call tiny_fortran_scheme_run(
// CHECK:           call tiny_cxx_scheme_run(
