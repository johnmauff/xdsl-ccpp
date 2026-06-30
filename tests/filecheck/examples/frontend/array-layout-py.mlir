// Test that array_layout = row_major on a host table-properties block is
// parsed and emitted as an IR attribute on the TablePropertiesOp.
//
// RUN: python3 tests/filecheck/examples/array_layout_suite.py | python3 -m filecheck %s

// The scheme table has no array_layout attribute (Fortran default).
// CHECK:      "ccpp.table_properties"() <{name = "tiny_scheme", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NOT:  array_layout

// The host module table carries array_layout = "row_major".
// CHECK:      "ccpp.table_properties"() <{name = "tiny_host_mod", type = #ccpp<table_type_kind module>}> ({
// CHECK:      }) {array_layout = "row_major"} : () -> ()
