// End-to-end test: Fortran host calling one Fortran scheme and one C++ scheme,
// driven by .meta files (XML frontend) rather than the Python API.
// Verifies that "language = c++" in a [ccpp-table-properties] block is parsed,
// propagated through the IR, and produces a correct BIND(C) interface block in
// the generated suite cap — identical behaviour to language-cxx-interface-py.mlir.
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites tests/filecheck/examples/language_cxx/tiny_suite.xml --scheme-files tests/filecheck/examples/language_cxx/tiny_fortran_scheme.meta,tests/filecheck/examples/language_cxx/tiny_cxx_scheme.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap,generate-kinds,strip-ccpp -t ftn | python3 -m filecheck %s

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
