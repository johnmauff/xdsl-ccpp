// Test the XML frontend IR for the threads example (task11-omp-thread
// item 3): the thread_number/number_of_threads scalar-index dimension
// pair, the per-thread analog of instances/instances_advection's own
// instance_number/number_of_instances multi-instance dispatch pattern.
// NOT a capgen-v1 port -- see examples/threads/README.md.

// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/threads/suite_thread_suite.xml --scheme-files examples/threads/thread_scheme.meta --host-files examples/threads/data.meta,examples/threads/test_host.meta | python3 -m filecheck %s

// CHECK:       builtin.module {
// CHECK-NEXT:    "ccpp.suite"() <{suite_name = "thread_suite", version = "2.0"}> ({
// CHECK-NEXT:      "ccpp.group"() <{group_name = "thread_group"}> ({
// CHECK-NEXT:        "ccpp.scheme"() <{scheme_name = "thread_scheme"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "thread_scheme", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "thread_scheme_run", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "error message for error handling in CCPP", kind = "len=*", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "error code for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "thread", type = "integer", standard_name = "thread_number", long_name = "thread number for testing multi-thread support", intent = "in", units = "index"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "data_array", type = "real", dimensions = #builtin.int<1>, dim_names = "horizontal_dimension", standard_name = "data_array", long_name = "per-thread data array", kind = "kind_phys", intent = "inout", units = "m"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "thread_scheme"} : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "thread_type", type = #ccpp<table_type_kind ddt>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "thread_type", type = #ccpp<table_type_kind ddt>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "data_array", type = "real", dimensions = #builtin.int<1>, dim_names = "horizontal_dimension", standard_name = "data_array", long_name = "per-thread data array", kind = "kind_phys", units = "m"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "data"} : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "data", type = #ccpp<table_type_kind host>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "data", type = #ccpp<table_type_kind host>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "ncols", type = "integer", standard_name = "horizontal_dimension", long_name = "horizontal dimension", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "thread_data", type = "thread_type", dimensions = #builtin.int<1>, dim_names = "number_of_threads", standard_name = "thread_data", long_name = "per-thread data for multi-thread test", units = "ddt"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "data"} : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "test_host", type = #ccpp<table_type_kind control>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "test_host", type = #ccpp<table_type_kind control>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "lb", type = "integer", standard_name = "horizontal_loop_begin", long_name = "start of horizontal range for this phase", units = "index", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "ub", type = "integer", standard_name = "horizontal_loop_end", long_name = "end of horizontal range for this phase", units = "index", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "test_host"} : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "test_host_thread", type = #ccpp<table_type_kind host>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "test_host_thread", type = #ccpp<table_type_kind host>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "thread", type = "integer", standard_name = "thread_number", long_name = "current OpenMP thread number", units = "index", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "nthreads", type = "integer", standard_name = "number_of_threads", long_name = "number of threads for multi-thread test", units = "count", protected}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "test_host"} : () -> ()
// CHECK-NEXT:  }
