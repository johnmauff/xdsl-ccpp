// Test that after generate-host-match, scheme args matched against a row_major
// host variable are annotated with model_var_array_layout = "row_major".
// Scalars and integers matched against the same host carry the annotation too
// (the match pass stamps it on all matched args regardless of rank).
// Block args (e.g. ncol / horizontal_loop_extent) that have no host match do
// not carry any layout annotation.
//
// RUN: python3 tests/filecheck/examples/array_layout_suite.py | python3 -m xdsl_ccpp.tools.ccpp_opt -p generate-meta-cap,generate-meta-kinds,generate-host-match | python3 -m filecheck %s

// ncol (horizontal_loop_extent) is a block arg with no host match — no annotation.
// CHECK: "ccpp.arg"() <{name = "ncol"
// CHECK-NOT: model_var_array_layout
// CHECK: "ccpp.arg"() <{name = "nz"

// nz (vertical_layer_dimension) is matched to the row_major host — annotated.
// CHECK-SAME: model_var_array_layout = "row_major"

// temp (1D array) is matched to the row_major host — annotated.
// CHECK: "ccpp.arg"() <{name = "temp"
// CHECK-SAME: model_var_array_layout = "row_major"

// theta (2D array) is matched to the row_major host — annotated.
// CHECK: "ccpp.arg"() <{name = "theta"
// CHECK-SAME: model_var_array_layout = "row_major"
