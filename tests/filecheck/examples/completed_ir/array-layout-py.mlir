// Test that after generate-host-match, scheme args matched against a row_major
// host variable are annotated with model_var_array_layout = "row_major".
// Non-array args (scalars, integers) matched against the same host carry no
// such annotation because they are not affected by memory layout.
//
// RUN: python3 tests/filecheck/examples/array_layout_suite.py | python3 -m xdsl_ccpp.tools.ccpp_opt -p generate-meta-cap,generate-meta-kinds,generate-host-match | python3 -m filecheck %s

// The integer ncol arg is matched against horizontal_loop_extent — no layout annotation.
// CHECK: "ccpp.arg"() <{name = "ncol"
// CHECK-NOT: model_var_array_layout
// CHECK: "ccpp.arg"() <{name = "temp"

// The real array arg matched against a row_major host variable carries the annotation.
// CHECK-SAME: model_var_array_layout = "row_major"
