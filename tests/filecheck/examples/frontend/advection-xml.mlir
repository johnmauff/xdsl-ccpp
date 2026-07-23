// Test the XML frontend IR for the advection example.
// Exercises: four distinct schemes, apply_constituent_tendencies appearing
// twice in the suite group (duplicate scheme entries in the XML), host and
// module table types, and 3-D array arguments.
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/advection/cld_suite.xml --scheme-files examples/advection/const_indices.meta,examples/advection/cld_liq.meta,examples/advection/cld_ice.meta,examples/advection/apply_constituent_tendencies.meta --host-files examples/advection/test_host_data.meta,examples/advection/test_host.meta,examples/advection/test_host_mod.meta | python3 -m filecheck %s

// Suite and group: apply_constituent_tendencies appears twice as specified in
// the XML — deduplication only happens later in the optimizer pass.

// CHECK:       builtin.module {
// CHECK-NEXT:    "ccpp.suite"() <{suite_name = "cld_suite", version = "1.0"}> ({
// CHECK-NEXT:      "ccpp.group"() <{group_name = "physics"}> ({
// CHECK-NEXT:        "ccpp.scheme"() <{scheme_name = "const_indices"}> : () -> ()
// CHECK-NEXT:        "ccpp.scheme"() <{scheme_name = "cld_liq"}> : () -> ()
// CHECK-NEXT:        "ccpp.scheme"() <{scheme_name = "apply_constituent_tendencies"}> : () -> ()
// CHECK-NEXT:        "ccpp.scheme"() <{scheme_name = "cld_ice"}> : () -> ()
// CHECK-NEXT:        "ccpp.scheme"() <{scheme_name = "apply_constituent_tendencies"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "const_indices", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "const_indices_run", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "const_std_name", type = "character", standard_name = "test_banana_name", kind = "len=*", intent = "in", units = "1", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "num_consts", type = "integer", standard_name = "banana_array_dim", long_name = "Size of test_banana_name_array", intent = "in", units = "1"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "test_stdname_array", type = "character", dimensions = #builtin.int<1>, dim_names = "banana_array_dim", standard_name = "test_banana_name_array", kind = "len=*", intent = "in", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "const_index", type = "integer", standard_name = "test_banana_constituent_index", long_name = "Constituent index", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "const_inds", type = "integer", dimensions = #builtin.int<1>, dim_names = "banana_array_dim", standard_name = "test_banana_constituent_indices", long_name = "Array of constituent indices", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "const_indices_init", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "const_std_name", type = "character", standard_name = "test_banana_name", kind = "len=*", intent = "in", units = "1", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "num_consts", type = "integer", standard_name = "banana_array_dim", long_name = "Size of test_banana_name_array", intent = "in", units = "1"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "test_stdname_array", type = "character", dimensions = #builtin.int<1>, dim_names = "banana_array_dim", standard_name = "test_banana_name_array", kind = "len=*", intent = "in", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "const_index", type = "integer", standard_name = "test_banana_constituent_index", long_name = "Constituent index", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "const_inds", type = "integer", dimensions = #builtin.int<1>, dim_names = "banana_array_dim", standard_name = "test_banana_constituent_indices", long_name = "Array of constituent indices", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "const_indices"} : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "cld_liq", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "cld_liq_register", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "dyn_const", type = "ccpp_constituent_properties_t", dimensions = #builtin.int<1>, dim_names = "", standard_name = "dynamic_constituents_for_cld_liq", intent = "out", allocatable}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "cld_liq_run", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "ncol", type = "integer", standard_name = "horizontal_loop_extent", intent = "in", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "timestep", type = "real", standard_name = "time_step_for_physics", long_name = "time step", kind = "kind_phys", intent = "in", units = "s"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "tcld", type = "real", standard_name = "minimum_temperature_for_cloud_liquid", kind = "kind_phys", intent = "in", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "temp", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_loop_extent,vertical_LAYER_dimension", standard_name = "temperature", kind = "kind_phys", intent = "inout", units = "K", memory_space = "device"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "qv", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_loop_extent,vertical_layer_dimension", standard_name = "water_vapor_specific_humidity", kind = "kind_phys", intent = "inout", units = "kg kg-1", memory_space = "device"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "ps", type = "real", dimensions = #builtin.int<1>, dim_names = "horizontal_loop_extent", standard_name = "surface_air_pressure", kind = "kind_phys", intent = "in", units = "hPa", state_variable}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "cld_liq_tend", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_loop_extent,vertical_layer_dimension", standard_name = "tendency_of_cloud_liquid_dry_mixing_ratio", kind = "kind_phys", intent = "inout", units = "kg kg-1 s-1", memory_space = "device", constituent}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "cld_liq_init", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "tfreeze", type = "real", standard_name = "water_temperature_at_freezing", long_name = "Freezing temperature of water at sea level", kind = "kind_phys", intent = "in", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "cld_liq_array", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "cloud_liquid_dry_mixing_ratio", kind = "kind_phys", intent = "out", units = "kg kg-1", memory_space = "device", advected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "tcld", type = "real", standard_name = "minimum_temperature_for_cloud_liquid", kind = "kind_phys", intent = "out", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "cld_liq"} : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "cld_ice", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "cld_ice_register", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "dyn_const_ice", type = "ccpp_constituent_properties_t", dimensions = #builtin.int<1>, dim_names = "", standard_name = "dynamic_constituents_for_cld_ice", intent = "out", units = "none", allocatable}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errcode", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "cld_ice_run", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "ncol", type = "integer", standard_name = "horizontal_loop_extent", intent = "in", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "timestep", type = "real", standard_name = "time_step_for_physics", long_name = "time step", kind = "kind_phys", intent = "in", units = "s"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "temp", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_loop_extent,vertical_layer_dimension", standard_name = "temperature", kind = "kind_phys", intent = "inout", units = "K", memory_space = "device"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "qv", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_loop_extent,vertical_layer_dimension", standard_name = "water_vapor_specific_humidity", kind = "kind_phys", intent = "inout", units = "kg kg-1", memory_space = "device"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "ps", type = "real", dimensions = #builtin.int<1>, dim_names = "horizontal_loop_extent", standard_name = "surface_air_pressure", kind = "kind_phys", intent = "in", units = "Pa", state_variable}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "cld_ice_array", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_loop_extent,vertical_layer_dimension", standard_name = "cloud_ice_dry_mixing_ratio", kind = "kind_phys", intent = "inout", units = "kg kg-1", default_value = "0.0_kind_phys", advected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "cld_ice_init", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "tfreeze", type = "real", standard_name = "water_temperature_at_freezing", long_name = "Freezing temperature of water at sea level", kind = "kind_phys", intent = "in", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "cld_ice_array", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "cloud_ice_dry_mixing_ratio", kind = "kind_phys", intent = "inout", units = "kg kg-1", memory_space = "device", default_value = "0.0_kind_phys", advected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "cld_ice_final", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "cld_ice"} : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "apply_constituent_tendencies", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "apply_constituent_tendencies_run", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "const_tend", type = "real", dimensions = #builtin.int<3>, dim_names = "horizontal_loop_extent,vertical_layer_dimension,number_of_ccpp_constituents", standard_name = "ccpp_constituent_tendencies", long_name = "ccpp constituent tendencies", kind = "kind_phys", intent = "inout", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "const", type = "real", dimensions = #builtin.int<3>, dim_names = "horizontal_loop_extent,vertical_layer_dimension,number_of_ccpp_constituents", standard_name = "ccpp_constituents", long_name = "ccpp constituents", kind = "kind_phys", intent = "inout", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errcode", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "apply_constituent_tendencies"} : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "physics_state", type = #ccpp<table_type_kind ddt>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "physics_state", type = #ccpp<table_type_kind ddt>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "ps", type = "real", dimensions = #builtin.int<1>, dim_names = "horizontal_dimension", standard_name = "surface_air_pressure", kind = "kind_phys", units = "Pa", state_variable}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "Temp", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "temperature", kind = "kind_phys", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "q", type = "real", dimensions = #builtin.int<3>, dim_names = "horizontal_dimension,vertical_layer_dimension,number_of_tracers", standard_name = "constituent_mixing_ratio", kind = "kind_phys", units = "kg kg-1 moist or dry air depending on type", state_variable}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "q(:,:,index_of_water_vapor_specific_humidity)", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "water_vapor_specific_humidity", kind = "kind_phys", units = "kg kg-1", state_variable}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "test_host_data"} : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "test_host_data", type = #ccpp<table_type_kind module>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "test_host_data", type = #ccpp<table_type_kind module>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "num_consts", type = "integer", standard_name = "banana_array_dim", long_name = "Size of test_banana_name_array", units = "1"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "std_name_array", type = "character", dimensions = #builtin.int<1>, dim_names = "banana_array_dim", standard_name = "test_banana_name_array", kind = "len=32", units = "count", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "const_std_name", type = "character", standard_name = "test_banana_name", kind = "len=32", units = "1", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "const_inds", type = "integer", dimensions = #builtin.int<1>, dim_names = "banana_array_dim", standard_name = "test_banana_constituent_indices", long_name = "Array of constituent indices", units = "1", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "const_index", type = "integer", standard_name = "test_banana_constituent_index", long_name = "Constituent index", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "test_host_data"} : () -> ()
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
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "test_host_mod", type = #ccpp<table_type_kind module>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "test_host_mod", type = #ccpp<table_type_kind module>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "ncols", type = "integer", standard_name = "horizontal_dimension", units = "count", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "pver", type = "integer", standard_name = "vertical_layer_dimension", units = "count", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "pverP", type = "integer", standard_name = "vertical_interface_dimension", units = "count", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "ncnst", type = "integer", standard_name = "number_of_tracers", units = "count", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "index_qv", type = "integer", standard_name = "index_of_water_vapor_specific_humidity", units = "index", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "dt", type = "real", standard_name = "time_step_for_physics", long_name = "time step", kind = "kind_phys", units = "s"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "tfreeze", type = "real", standard_name = "water_temperature_at_freezing", long_name = "Freezing temperature of water at sea level", kind = "kind_phys", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "phys_state", type = "physics_state", standard_name = "physics_state_derived_type", long_name = "Physics State DDT"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "num_model_times", type = "integer", standard_name = "number_of_model_times", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "model_times", type = "integer", dimensions = #builtin.int<1>, dim_names = "number_of_model_times", standard_name = "model_times", units = "seconds", allocatable}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "test_host_mod"} : () -> ()
// CHECK-NEXT:  }
