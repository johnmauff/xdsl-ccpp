// Test the XML frontend IR for the ddthost example.
// Exercises: DDT table type, host/module table types, and optional entry
// points (make_ddt_timestep_final but no make_ddt_finalize).
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/ddthost/scheme/ddt_suite.xml --scheme-files examples/ddthost/scheme/make_ddt.meta,examples/ddthost/scheme/environ_conditions.meta --host-files examples/ddthost/host_ftn/test_host_data.meta,examples/ddthost/host_ftn/test_host_mod.meta,examples/ddthost/scheme/host_ccpp_ddt.meta,examples/ddthost/host_ftn/test_host.meta | python3 -m filecheck %s

// Suite and group structure.

// CHECK:       builtin.module {
// CHECK-NEXT:    "ccpp.suite"() <{suite_name = "ddt_suite", version = "1.0"}> ({
// CHECK-NEXT:      "ccpp.group"() <{group_name = "data_prep"}> ({
// CHECK-NEXT:        "ccpp.scheme"() <{scheme_name = "make_ddt"}> : () -> ()
// CHECK-NEXT:        "ccpp.scheme"() <{scheme_name = "environ_conditions"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "vmr_type", type = #ccpp<table_type_kind ddt>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "vmr_type", type = #ccpp<table_type_kind ddt>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "nvmr", type = "integer", standard_name = "number_of_chemical_species", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "vmr_array", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,number_of_chemical_species", standard_name = "array_of_volume_mixing_ratios", kind = "kind_phys", units = "ppmv"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "make_ddt"} : () -> ()
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
// CHECK-NEXT:    }) {source_module = "make_ddt"} : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "environ_conditions", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "environ_conditions_run", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "psurf", type = "real", dimensions = #builtin.int<1>, dim_names = "horizontal_loop_extent", standard_name = "surface_air_pressure", kind = "kind_phys", intent = "in", units = "Pa", state_variable}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "environ_conditions_init", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "nbox", type = "integer", standard_name = "horizontal_dimension", intent = "in", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "o3", type = "real", dimensions = #builtin.int<1>, dim_names = "horizontal_dimension", standard_name = "ozone", kind = "kind_phys", intent = "out", units = "ppmv"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "hno3", type = "real", dimensions = #builtin.int<1>, dim_names = "horizontal_dimension", standard_name = "nitric_acid", kind = "kind_phys", intent = "out", units = "ppmv"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "ntimes", type = "integer", standard_name = "number_of_model_times", intent = "out", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "model_times", type = "integer", dimensions = #builtin.int<1>, dim_names = "number_of_model_times", standard_name = "model_times", intent = "out", units = "seconds", allocatable}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "environ_conditions_finalize", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "ntimes", type = "integer", standard_name = "number_of_model_times", intent = "in", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "model_times", type = "integer", dimensions = #builtin.int<1>, dim_names = "number_of_model_times", standard_name = "model_times", intent = "in", units = "seconds"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "environ_conditions"} : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "physics_state", type = #ccpp<table_type_kind ddt>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "physics_state", type = #ccpp<table_type_kind ddt>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "ps", type = "real", dimensions = #builtin.int<1>, dim_names = "horizontal_dimension", standard_name = "surface_air_pressure", kind = "kind_phys", units = "Pa", state_variable}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "u", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "eastward_wind", long_name = "Zonal wind", kind = "kind_phys", units = "m s-1", state_variable}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "v", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "northward_wind", long_name = "Meridional wind", kind = "kind_phys", units = "m s-1", state_variable}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "pmid", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "air_pressure", long_name = "Midpoint air pressure", kind = "kind_phys", units = "Pa", state_variable}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "q", type = "real", dimensions = #builtin.int<3>, dim_names = "horizontal_dimension,vertical_layer_dimension,number_of_tracers", standard_name = "constituent_mixing_ratio", kind = "kind_phys", units = "kg kg-1 moist or dry air depending on type", state_variable}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "q(:,:,index_of_water_vapor_specific_humidity)", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "water_vapor_specific_humidity", kind = "kind_phys", units = "kg kg-1", active = "(index_of_water_vapor_specific_humidity > 0)", state_variable}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "test_host_data"} : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "test_host_mod", type = #ccpp<table_type_kind module>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "test_host_mod", type = #ccpp<table_type_kind module>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "index_qv", type = "integer", standard_name = "index_of_water_vapor_specific_humidity", units = "index", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "ncols", type = "integer", standard_name = "horizontal_dimension", units = "count", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "pver", type = "integer", standard_name = "vertical_layer_dimension", units = "count", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "pverP", type = "integer", standard_name = "vertical_interface_dimension", units = "count", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "pcnst", type = "integer", standard_name = "number_of_tracers", units = "count", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "DiagDimStart", type = "integer", standard_name = "first_index_of_diag_fields", units = "count", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "temp_midpoints", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "potential_temperature", kind = "kind_phys", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "temp_interfaces", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_interface_dimension", standard_name = "potential_temperature_at_interface", kind = "kind_phys", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "diag1", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "diagnostic_stuff_type_1", long_name = "This is just a test field", kind = "kind_phys", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "diag2", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "diagnostic_stuff_type_2", long_name = "This is just a test field", kind = "kind_phys", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "dt", type = "real", standard_name = "time_step_for_physics", long_name = "time step", kind = "kind_phys", units = "s"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "temp_inc", type = "real", standard_name = "potential_temperature_increment", long_name = "Per time step potential temperature increment", kind = "kind_phys", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "phys_state", type = "physics_state", standard_name = "physics_state_derived_type", long_name = "Physics State DDT"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "num_model_times", type = "integer", standard_name = "number_of_model_times", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "model_times", type = "integer", dimensions = #builtin.int<1>, dim_names = "number_of_model_times", standard_name = "model_times", units = "seconds", allocatable}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "coeffs", type = "real", dimensions = #builtin.int<1>, dim_names = "horizontal_dimension", standard_name = "coefficients_for_interpolation", long_name = "coefficients for interpolation", kind = "kind_phys", units = "none"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "test_host_mod"} : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "ccpp_info_t", type = #ccpp<table_type_kind ddt>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "ccpp_info_t", type = #ccpp<table_type_kind ddt>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "col_start", type = "integer", standard_name = "horizontal_loop_begin", units = "count", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "col_end", type = "integer", standard_name = "horizontal_loop_end", units = "count", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "host_ccpp_ddt"} : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "suite_info", type = #ccpp<table_type_kind ddt>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "suite_info", type = #ccpp<table_type_kind ddt>}> ({
// CHECK-NEXT:      ^bb0:
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "test_host"} : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "test_host", type = #ccpp<table_type_kind host>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "test_host", type = #ccpp<table_type_kind host>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "ccpp", type = "ccpp_info_t", standard_name = "host_standard_ccpp_type"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "test_host"} : () -> ()
// CHECK-NEXT:  }
