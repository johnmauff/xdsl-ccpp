// Test that the chost Fortran cap handles rank-3 real arrays.
// Verifies that a scheme with a (ncol, nz, nbands) array produces a correct
// assumed-size declaration — real(c_double), target, intent(inout) :: flux(ncol, nz, *)
// — and that the third-dimension integer (nbands) is passed by value as c_int.
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites tests/filecheck/examples/chost_r3/tiny_r3_suite.xml --scheme-files tests/filecheck/examples/chost_r3/tiny_r3_scheme.meta --host-files tests/filecheck/examples/chost_r3/tiny_r3_host_mod.meta,tests/filecheck/examples/chost_r3/tiny_r3_host_sub.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p "generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap{bind_c=true},generate-kinds,strip-ccpp" -t ftn | python3 -m filecheck %s

// CHECK-LABEL: module TinyR3_ccpp_chost_cap

// Run subroutine: ncol and nz as value ints; col_start and col_end passed through;
// nbands as value int; flux as rank-3 assumed-size real array, then errmsg and errflg.
// CHECK-LABEL:   subroutine TinyR3_chost_physics_run(
// CHECK:           integer(c_int), value, intent(in) :: ncol
// CHECK:           integer(c_int), value, intent(in) :: nz
// CHECK:           integer(c_int), value, intent(in) :: col_start
// CHECK:           integer(c_int), value, intent(in) :: col_end
// CHECK:           integer(c_int), value, intent(in) :: nbands
// CHECK:           real(c_double), target, intent(inout) :: flux(ncol, nz, *)
// CHECK:           character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK:           integer(c_int),               intent(out) :: errflg

// Suite cap call passes col_start and col_end through directly.
// CHECK:           call tiny_r3_suite_suite_physics(
// CHECK:               col_start, col_end, nz, nbands, flux,
