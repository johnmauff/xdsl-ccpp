// Test that language = c++ in host meta files triggers chost cap generation
// without needing explicit_args=true on the generate-ccpp-cap pass.
//
// Uses host_cpp/ meta files (which carry language = c++) and omits
// explicit_args from the pass pipeline.  The output must be identical to
// the explicit_args=true path tested in kessler-chost-ftn.mlir.
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/kessler/scheme/kessler_suite.xml --scheme-files examples/kessler/scheme/kessler.meta,examples/kessler/scheme/kessler_update.meta --host-files examples/kessler/host_cpp/kessler_host_mod.meta,examples/kessler/host_cpp/kessler_host_sub.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p "generate-meta-cap,generate-meta-kinds,generate-arg-ownership,generate-suite-cap,generate-ccpp-cap{bind_c=true},generate-cpp-cap,generate-kinds,strip-ccpp" -t ftn | python3 -m filecheck %s

// Chost cap module is generated even without explicit_args=true.
// CHECK-LABEL: module Kessler_ccpp_chost_cap
// CHECK:         use iso_c_binding

// Run subroutine: col_start and col_end are present as explicit value args.
// CHECK-LABEL:   subroutine Kessler_chost_physics_run(
// CHECK:           integer(c_int), value, intent(in) :: col_start
// CHECK:           integer(c_int), value, intent(in) :: col_end
