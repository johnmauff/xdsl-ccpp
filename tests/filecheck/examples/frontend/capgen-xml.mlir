// Test the XML frontend output (raw MLIR IR) for the capgen example.
// Two suites (ddt_suite, temp_suite) with DDT arguments and optional entry points.
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/capgen/scheme/ddt_suite.xml,examples/capgen/scheme/temp_suite.xml --scheme-files examples/capgen/scheme/make_ddt.meta,examples/capgen/scheme/environ_conditions.meta,examples/capgen/scheme/setup_coeffs.meta,examples/capgen/scheme/temp_set.meta,examples/capgen/scheme/temp_calc_adjust.meta,examples/capgen/scheme/temp_adjust.meta --host-files examples/capgen/host_ftn/test_host_data.meta,examples/capgen/host_ftn/test_host_mod.meta,examples/capgen/host_ftn/test_host.meta | python3 -m filecheck %s

// CHECK:       builtin.module {
// CHECK-NEXT:    "ccpp.suite"() <{suite_name = "ddt_suite", version = "1.0"}> ({
// CHECK-NEXT:      "ccpp.group"() <{group_name = "data_prep"}> ({
// CHECK-NEXT:        "ccpp.scheme"() <{scheme_name = "make_ddt"}> : () -> ()
// CHECK-NEXT:        "ccpp.scheme"() <{scheme_name = "environ_conditions"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) : () -> ()
// CHECK-NEXT:    "ccpp.suite"() <{suite_name = "temp_suite", version = "1.0"}> ({
// CHECK-NEXT:      "ccpp.group"() <{group_name = "physics1"}> ({
// CHECK-NEXT:        "ccpp.scheme"() <{scheme_name = "setup_coeffs"}> : () -> ()
// CHECK-NEXT:        "ccpp.scheme"() <{scheme_name = "temp_set"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp.group"() <{group_name = "physics2"}> ({
// CHECK-NEXT:        "ccpp.scheme"() <{scheme_name = "temp_calc_adjust"}> : () -> ()
// CHECK-NEXT:        "ccpp.scheme"() <{scheme_name = "temp_adjust"}> : () -> ()
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
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "setup_coeffs", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "setup_coeffs_timestep_init", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "coeffs", type = "real", dimensions = #builtin.int<1>, dim_names = "horizontal_dimension", standard_name = "coefficients_for_interpolation", long_name = "coefficients for interpolation", kind = "kind_phys", intent = "inout", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "setup_coeffs"} : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "temp_set", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "temp_set_run", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "ncol", type = "integer", standard_name = "horizontal_loop_extent", intent = "in", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "lev", type = "integer", standard_name = "vertical_layer_dimension", intent = "in", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "timestep", type = "real", standard_name = "time_step_for_physics", long_name = "time step", kind = "kind_phys", intent = "in", units = "s"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "temp_level", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_loop_extent,vertical_interface_dimension", standard_name = "potential_temperature_at_interface", kind = "kind_phys", intent = "inout", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "temp_diag", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_loop_extent,6", standard_name = "temperature_at_diagnostic_levels", kind = "kind_phys", intent = "inout", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "temp", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_loop_extent,vertical_layer_dimension", standard_name = "potential_temperature", kind = "kind_phys", intent = "out", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "ps", type = "real", dimensions = #builtin.int<1>, dim_names = "horizontal_loop_extent", standard_name = "surface_air_pressure", kind = "kind_phys", intent = "in", units = "Pa", state_variable}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "to_promote", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_loop_extent,vertical_layer_dimension", standard_name = "promote_this_variable_to_suite", kind = "kind_phys", intent = "out", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "promote_pcnst", type = "real", dimensions = #builtin.int<1>, dim_names = "number_of_tracers", standard_name = "promote_this_variable_with_no_horizontal_dimension", kind = "kind_phys", intent = "out", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "slev_lbound", type = "integer", standard_name = "lower_bound_of_vertical_dimension_of_soil", intent = "in", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "soil_levs", type = "real", dimensions = #builtin.int<1>, dim_names = "upper_bound_of_vertical_dimension_of_soil", standard_name = "soil_levels", long_name = "soil levels", kind = "kind_phys", intent = "inout", units = "cm"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "var_array", type = "real", dimensions = #builtin.int<4>, dim_names = "horizontal_loop_extent,2,4,6", standard_name = "array_variable_for_testing", long_name = "array variable for testing", kind = "kind_phys", intent = "inout", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "temp_set_init", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "temp_inc_in", type = "real", standard_name = "potential_temperature_increment", long_name = "Per time step potential temperature increment", kind = "kind_phys", intent = "in", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "fudge", type = "real", standard_name = "random_fudge_factor", long_name = "Ignore this", kind = "kind_phys", intent = "in", units = "1", default_value = "1.0_kind_phys"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "temp_inc_set", type = "real", standard_name = "test_potential_temperature_increment", long_name = "Per time step potential temperature increment", kind = "kind_phys", intent = "out", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "temp_set_timestep_initialize", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "ncol", type = "integer", standard_name = "horizontal_dimension", intent = "in", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "temp_inc", type = "real", standard_name = "test_potential_temperature_increment", long_name = "Per time step potential temperature increment", kind = "kind_phys", intent = "in", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "temp_level", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_interface_dimension", standard_name = "potential_temperature_at_interface", kind = "kind_phys", intent = "inout", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "temp_set_finalize", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "temp_set"} : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "temp_calc_adjust", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "temp_calc_adjust_run", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "nbox", type = "integer", standard_name = "horizontal_loop_extent", intent = "in", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "timestep", type = "real", standard_name = "time_step_for_physics", long_name = "time step", kind = "kind_phys", intent = "in", units = "s"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "temp_level", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_loop_extent,vertical_interface_dimension", standard_name = "potential_temperature_at_interface", kind = "kind_phys", intent = "in", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "temp_calc", type = "real", dimensions = #builtin.int<1>, dim_names = "horizontal_loop_extent", standard_name = "potential_temperature_at_previous_timestep", kind = "kind_phys", intent = "out", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "temp_calc_adjust_init", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "temp_calc_adjust_finalize", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "temp_calc_adjust"} : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "temp_adjust", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "temp_adjust_register", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "config_var", type = "logical", standard_name = "configuration_variable", intent = "in", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "temp_adjust_run", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "foo", type = "integer", standard_name = "horizontal_loop_extent", intent = "in", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "timestep", type = "real", standard_name = "time_step_for_physics", long_name = "time step", kind = "kind_phys", intent = "in", units = "s"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "temp_prev", type = "real", dimensions = #builtin.int<1>, dim_names = "horizontal_loop_extent", standard_name = "potential_temperature_at_previous_timestep", kind = "kind_phys", intent = "in", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "temp_layer", type = "real", dimensions = #builtin.int<1>, dim_names = "horizontal_loop_extent", standard_name = "potential_temperature", kind = "kind_phys", intent = "inout", units = "K", diagnostic_name = "temperature"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "qv", type = "real", dimensions = #builtin.int<1>, dim_names = "horizontal_loop_extent", standard_name = "water_vapor_specific_humidity", kind = "kind_phys", intent = "inout", units = "kg kg-1", diagnostic_name_fixed = "Q", optional}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "ps", type = "real", dimensions = #builtin.int<1>, dim_names = "horizontal_loop_extent", standard_name = "surface_air_pressure", kind = "kind_phys", intent = "inout", units = "Pa", state_variable}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "to_promote", type = "real", dimensions = #builtin.int<1>, dim_names = "horizontal_loop_extent", standard_name = "promote_this_variable_to_suite", kind = "kind_phys", intent = "in", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "promote_pcnst", type = "real", dimensions = #builtin.int<1>, dim_names = "number_of_tracers", standard_name = "promote_this_variable_with_no_horizontal_dimension", kind = "kind_phys", intent = "in", units = "K"}> : () -> ()
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
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "physics_state", type = #ccpp<table_type_kind ddt>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "physics_state", type = #ccpp<table_type_kind ddt>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "ps", type = "real", dimensions = #builtin.int<1>, dim_names = "horizontal_dimension", standard_name = "surface_air_pressure", kind = "kind_phys", units = "Pa", state_variable}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "u", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "eastward_wind", long_name = "Zonal wind", kind = "kind_phys", units = "m s-1", state_variable}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "v", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "northward_wind", long_name = "Meridional wind", kind = "kind_phys", units = "m s-1", state_variable}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "pmid", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "air_pressure", long_name = "Midpoint air pressure", kind = "kind_phys", units = "Pa", state_variable}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "soil_levs", type = "real", dimensions = #builtin.int<1>, dim_names = "upper_bound_of_vertical_dimension_of_soil", standard_name = "soil_levels", long_name = "soil levels", kind = "kind_phys", units = "cm"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "q", type = "real", dimensions = #builtin.int<3>, dim_names = "horizontal_dimension,vertical_layer_dimension,number_of_tracers", standard_name = "constituent_mixing_ratio", kind = "kind_phys", units = "kg kg-1 moist or dry air depending on type", state_variable}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "q(:,:,index_of_water_vapor_specific_HUMidity)", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "water_vapor_specific_humidity", kind = "kind_phys", units = "kg kg-1", active = "(index_of_water_vapor_specific_humidity > 0)", state_variable}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "test_host_data"} : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "test_host_mod", type = #ccpp<table_type_kind module>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "test_host_mod", type = #ccpp<table_type_kind module>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "index_qv", type = "integer", standard_name = "index_of_water_vapor_specific_HUMidity", units = "index", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "config_var", type = "logical", standard_name = "configuration_variable", units = "none", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "ncols", type = "integer", standard_name = "horizontal_dimension", units = "count", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "pver", type = "integer", standard_name = "vertical_layer_dimension", units = "count", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "pverP", type = "integer", standard_name = "vertical_interface_dimension", units = "count", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "pcnst", type = "integer", standard_name = "number_of_tracers", units = "count", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "slevs", type = "integer", standard_name = "vertical_dimension_of_soil", units = "count", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "slev_lbound", type = "integer", standard_name = "lower_bound_of_vertical_dimension_of_soil", units = "count", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "slev_ubound", type = "integer", standard_name = "upper_bound_of_vertical_dimension_of_soil", units = "count", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "DiagDimStart", type = "integer", standard_name = "first_index_of_diag_fields", units = "count", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "temp_midpoints", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "potential_temperature", kind = "kind_phys", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "temp_interfaces", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_interface_dimension", standard_name = "potential_temperature_at_interface", kind = "kind_phys", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "temp_diag", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,6", standard_name = "temperature_at_diagnostic_levels", kind = "kind_phys", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "diag1", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "diagnostic_stuff_type_1", long_name = "This is just a test field", kind = "kind_phys", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "diag2", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "diagnostic_stuff_type_2", long_name = "This is just a test field", kind = "kind_phys", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "dt", type = "real", standard_name = "time_step_for_physics", long_name = "time step", kind = "kind_phys", units = "s"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "temp_inc", type = "real", standard_name = "potential_temperature_increment", long_name = "Per time step potential temperature increment", kind = "kind_phys", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "phys_state", type = "physics_state", standard_name = "physics_state_derived_type", long_name = "Physics State DDT"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "num_model_times", type = "integer", standard_name = "number_of_model_times", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "model_times", type = "integer", dimensions = #builtin.int<1>, dim_names = "number_of_model_times", standard_name = "model_times", units = "seconds", allocatable}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "coeffs", type = "real", dimensions = #builtin.int<1>, dim_names = "horizontal_dimension", standard_name = "coefficients_for_interpolation", long_name = "coefficients for interpolation", kind = "kind_phys", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "var_array", type = "real", dimensions = #builtin.int<4>, dim_names = "horizontal_dimension,2,4,6", standard_name = "array_variable_for_testing", long_name = "array variable for testing", kind = "kind_phys", units = "none"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "test_host_mod"} : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "suite_info", type = #ccpp<table_type_kind ddt>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "suite_info", type = #ccpp<table_type_kind ddt>}> ({
// CHECK-NEXT:      ^bb0:
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "test_host"} : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "test_host", type = #ccpp<table_type_kind host>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "test_host", type = #ccpp<table_type_kind host>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "col_start", type = "integer", standard_name = "horizontal_loop_begin", units = "count", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "col_end", type = "integer", standard_name = "horizontal_loop_end", units = "count", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "test_host"} : () -> ()
// CHECK-NEXT:  }
