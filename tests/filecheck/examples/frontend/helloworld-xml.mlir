// Test the XML frontend IR for the helloworld example.
// Verifies the ccpp.suite/group/scheme structure and that hello_scheme and
// temp_adjust are both parsed with the correct arg tables and argument kinds.
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/helloworld/hello_world_suite.xml --scheme-files examples/helloworld/hello_scheme.meta,examples/helloworld/temp_adjust.meta | python3 -m filecheck %s

// Suite and group structure.

// CHECK:       builtin.module {
// CHECK-NEXT:    "ccpp.suite"() <{suite_name = "hello_world_suite", version = "1.0"}> ({
// CHECK-NEXT:      "ccpp.group"() <{group_name = "physics"}> ({
// CHECK-NEXT:        "ccpp.scheme"() <{scheme_name = "hello_scheme"}> : () -> ()
// CHECK-NEXT:        "ccpp.scheme"() <{scheme_name = "temp_adjust"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "hello_scheme", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "hello_scheme_run", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "ncol", type = "integer", standard_name = "horizontal_loop_extent", intent = "in", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "lev", type = "integer", standard_name = "vertical_layer_dimension", intent = "in", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "ilev", type = "integer", standard_name = "vertical_interface_dimension", intent = "in", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "timestep", type = "real", standard_name = "time_step_for_physics", long_name = "time step", kind = "kind_phys", intent = "in", units = "s"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "temp_level", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_loop_extent,vertical_interface_dimension", standard_name = "potential_temperature_at_interface", kind = "kind_dyn", intent = "inout", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "temp_layer", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_loop_extent,vertical_layer_dimension", standard_name = "potential_temperature", kind = "kind_phys", intent = "out", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "hello_scheme_init", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "hello_scheme_finalize", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "hello_scheme"} : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "temp_adjust", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "temp_adjust_run", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "nbox", type = "integer", standard_name = "horizontal_loop_extent", intent = "in", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "lev", type = "integer", standard_name = "vertical_layer_dimension", intent = "in", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "temp_layer", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_loop_extent,vertical_layer_dimension", standard_name = "potential_temperature", kind = "kind_phys", intent = "inout", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "timestep", type = "real", standard_name = "time_step_for_physics", long_name = "time step", kind = "kind_phys", intent = "in", units = "s"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "temp_adjust_init", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "temp_adjust_finalize", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "temp_adjust"} : () -> ()
// CHECK-NEXT:  }
