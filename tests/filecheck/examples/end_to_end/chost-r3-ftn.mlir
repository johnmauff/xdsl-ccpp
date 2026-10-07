// Test that both the plain --bind-c module and the chost module handle
// rank-3 real arrays correctly -- each declares its own BIND(C) wrapper's
// flux array with EXPLICIT shape (+ target), not flat assumed-size (*),
// so it can legally be forwarded into the suite cap's own assumed-shape
// (:,:,:) dummy (chost-rank3-bindc: an assumed-size actual cannot be
// passed to an assumed-shape dummy, for any rank -- confirmed via
// gfortran). The two modules resolve the horizontal dimension
// differently, both correctly: the chost module's own independent
// ChostArgInfo machinery produces a literal "ncol" scalar directly;
// the plain --bind-c module has no such literal sibling in its own
// signature (only col_start/col_end), so it synthesizes
// "col_end - col_start + 1" instead (run_dispatch.py's resolve_dim_exprs
// -- general sibling lookup first, horizontal-extent synthesis only as
// a fallback).
//
// This file previously carried an XFAIL (rank-3 chost declaration style
// changed to explicit-shape flux(ncol, nz, nbands) in commit 2fe5473,
// without updating this golden or multilanguage_limitations.md §5; a
// suspected, then-unverified follow-on issue at the plain-bind_c layer,
// where flux was still flat assumed-size flux(*) forwarded into the
// suite cap's assumed-shape dummy). Both are now resolved and verified:
// the chost line below was simply stale (chost itself was already
// correct); the plain-bind_c issue was real, confirmed via gfortran
// (rank mismatch / "cannot be an assumed-size array" errors for every
// rank, not just rank > 2), and is fixed by this same change.
//
// --legacy-mode: the scheme's ncol arg and tiny_r3_host_sub's col_start/
// col_end deliberately exercise the legacy horizontal_loop_extent
// column-chunking convention (paired with a host module using
// horizontal_dimension), not incidental naming.
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --legacy-mode --suites tests/filecheck/examples/chost_r3/tiny_r3_suite.xml --scheme-files tests/filecheck/examples/chost_r3/tiny_r3_scheme.meta --host-files tests/filecheck/examples/chost_r3/tiny_r3_host_mod.meta,tests/filecheck/examples/chost_r3/tiny_r3_host_sub.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p "generate-meta-cap,generate-meta-kinds,generate-arg-ownership,generate-suite-cap,generate-ccpp-cap{bind_c=true},generate-cpp-cap,generate-kinds,strip-ccpp" -t ftn | python3 -m filecheck %s

// Plain --bind-c module: ccpp_physics_run forwards flux WHOLE (never
// sliced) into the suite cap's own entry point -- col_start/col_end/nz/
// nbands as value ints, flux as rank-3 EXPLICIT-shape real array
// (horizontal extent synthesized from col_start/col_end, since no bare
// "ncol" sibling exists in this module's own signature), then errmsg
// and errflg.
// CHECK-LABEL: module TinyR3_ccpp_cap

// CHECK-LABEL:   subroutine ccpp_physics_run(
// CHECK:           integer(c_int), value, intent(in) :: col_start
// CHECK:           integer(c_int), value, intent(in) :: col_end
// CHECK:           integer(c_int), value, intent(in) :: nz
// CHECK:           integer(c_int), value, intent(in) :: nbands
// CHECK:           real(c_double), target, intent(inout) :: flux(col_end - col_start + 1, nz, nbands)
// CHECK:           character(kind=c_char, len=1), intent(inout) :: errmsg(*)
// CHECK:           integer(c_int), intent(inout) :: errflg

// CHECK:           call tiny_r3_suite_physics(col_start, col_end, nz, nbands, flux, errmsg_f, errflg)

// CHECK-LABEL: module TinyR3_ccpp_chost_cap

// Run subroutine: ncol and nz as value ints; col_start and col_end passed through;
// nbands as value int; flux as rank-3 EXPLICIT-shape real array, then errmsg and errflg.
// CHECK-LABEL:   subroutine TinyR3_chost_physics_run(
// CHECK:           integer(c_int), value, intent(in) :: ncol
// CHECK:           integer(c_int), value, intent(in) :: nz
// CHECK:           integer(c_int), value, intent(in) :: nbands
// CHECK:           integer(c_int), value, intent(in) :: col_start
// CHECK:           integer(c_int), value, intent(in) :: col_end
// CHECK:           real(c_double), target, intent(inout) :: flux(ncol, nz, nbands)
// CHECK:           character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK:           integer(c_int),               intent(out) :: errflg

// Suite cap call passes col_start and col_end through directly.
// CHECK:           call tiny_r3_suite_physics(
// CHECK:               col_start, col_end, nz, nbands, flux,
