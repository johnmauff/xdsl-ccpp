// Test the Python frontend IR for the ddthost example.
// The Python API defines schemes and the vmr_type DDT via @ccpp_ddt +
// additional=[vmr_type].  Unlike the XML frontend there are no host tables.
//
// RUN: python3 examples/ddthost/ddthost_py.py | python3 -m filecheck %s

// Suite and group structure.

// CHECK:       builtin.module {
// CHECK-NEXT:    "ccpp.suite"() <{suite_name = "ddt_suite", version = "1.0"}> ({
// CHECK-NEXT:      "ccpp.group"() <{group_name = "data_prep"}> ({
// CHECK-NEXT:        "ccpp.scheme"() <{scheme_name = "make_ddt"}> : () -> ()
// CHECK-NEXT:        "ccpp.scheme"() <{scheme_name = "environ_conditions"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "make_ddt", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "make_ddt_run", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "cols", type = "integer", standard_name = "horizontal_loop_begin", intent = "in", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "cole", type = "integer", standard_name = "horizontal_loop_end", intent = "in", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "O3", type = "real", dimensions = #builtin.int<1>, dim_names = "horizontal_loop_extent", standard_name = "ozone", kind = "kind_phys", intent = "in", units = "ppmv"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "HNO3", type = "real", dimensions = #builtin.int<1>, dim_names = "horizontal_loop_extent", standard_name = "nitric_acid", kind = "kind_phys", intent = "in", units = "ppmv"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "vmr", type = "vmr_type", standard_name = "volume_mixing_ratio_ddt", intent = "inout"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "make_ddt_init", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "nbox", type = "integer", standard_name = "horizontal_dimension", intent = "in", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "ccpp_info", type = "ccpp_info_t", standard_name = "host_standard_ccpp_type", intent = "in"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "vmr", type = "vmr_type", standard_name = "volume_mixing_ratio_ddt", intent = "out"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "make_ddt_timestep_final", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "ncols", type = "integer", standard_name = "horizontal_dimension", intent = "in", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "vmr", type = "vmr_type", standard_name = "volume_mixing_ratio_ddt", intent = "in"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "environ_conditions", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "environ_conditions_run", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "psurf", type = "real", dimensions = #builtin.int<1>, dim_names = "horizontal_loop_extent", standard_name = "surface_air_pressure", kind = "kind_phys", intent = "in", units = "Pa"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "environ_conditions_init", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "nbox", type = "integer", standard_name = "horizontal_dimension", intent = "in", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "o3", type = "real", dimensions = #builtin.int<1>, dim_names = "horizontal_dimension", standard_name = "ozone", kind = "kind_phys", intent = "out", units = "ppmv"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "hno3", type = "real", dimensions = #builtin.int<1>, dim_names = "horizontal_dimension", standard_name = "nitric_acid", kind = "kind_phys", intent = "out", units = "ppmv"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "ntimes", type = "integer", standard_name = "number_of_model_times", intent = "out", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "model_times", type = "integer", dimensions = #builtin.int<1>, dim_names = "number_of_model_times", standard_name = "model_times", intent = "out", units = "seconds"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "environ_conditions_finalize", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "ntimes", type = "integer", standard_name = "number_of_model_times", intent = "in", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "model_times", type = "integer", dimensions = #builtin.int<1>, dim_names = "number_of_model_times", standard_name = "model_times", intent = "in", units = "seconds"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "vmr_type", type = #ccpp<table_type_kind ddt>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "vmr_type", type = #ccpp<table_type_kind ddt>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "nvmr", type = "integer", standard_name = "number_of_chemical_species", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "vmr_array", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,number_of_chemical_species", standard_name = "array_of_volume_mixing_ratios", kind = "kind_phys", units = "ppmv"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) : () -> ()
// CHECK-NEXT:  }
