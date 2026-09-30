// Test the XML frontend IR for the instances_advection example.
// Exercises: the instance_number/number_of_instances multi-instance
// dispatch pattern combined with host + scheme-registered constituents
// (cld_liq.meta declares a dynamic ccpp_constituent_properties_t array) --
// the only example in this repo that drives constituent_cap.py's
// multi-instance path (the DerivedTypeDefOp/DdtComponentDeclOp per-instance
// bundle type, test_host_lc_instance_t). Added as part of tdb-002's Stage A
// completion (2026-09-30) to close a real coverage gap: none of the 4
// pre-existing constituent-API goldens (advection, ddthost, kw-override,
// var_compat) exercise the multi-instance branch at all.
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/instances_advection/cld_suite.xml --scheme-files examples/instances_advection/cld_liq.meta,examples/instances_advection/apply_constituent_tendencies.meta --host-files examples/instances_advection/data.meta,examples/instances_advection/test_host.meta | python3 -m filecheck %s

// CHECK:       builtin.module {
// CHECK-NEXT:    "ccpp.suite"() <{suite_name = "cld_suite", version = "1.0"}> ({
// CHECK-NEXT:      "ccpp.group"() <{group_name = "physics"}> ({
// CHECK-NEXT:        "ccpp.scheme"() <{scheme_name = "cld_liq"}> : () -> ()
// CHECK-NEXT:        "ccpp.scheme"() <{scheme_name = "apply_constituent_tendencies"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "cld_liq", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "cld_liq_register", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "dyn_const", type = "ccpp_constituent_properties_t", dimensions = #builtin.int<1>, dim_names = "", standard_name = "dynamic_constituents_for_cld_liq", intent = "out", allocatable}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errcode", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "cld_liq_run", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "ncol", type = "integer", standard_name = "horizontal_dimension", intent = "in", units = "count"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "timestep", type = "real", standard_name = "time_step_for_physics", long_name = "time step", kind = "kind_phys", intent = "in", units = "s"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "tcld", type = "real", standard_name = "minimum_temperature_for_cloud_liquid", kind = "kind_phys", intent = "in", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "temp", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_LAYER_dimension", standard_name = "temperature", kind = "kind_phys", intent = "inout", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "qv", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "water_vapor_specific_humidity", kind = "kind_phys", intent = "inout", units = "kg kg-1"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "ps", type = "real", dimensions = #builtin.int<1>, dim_names = "horizontal_dimension", standard_name = "surface_air_pressure", kind = "kind_phys", intent = "in", units = "hPa"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "cld_liq_array", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "cloud_liquid_dry_mixing_ratio", kind = "kind_phys", intent = "inout", units = "kg kg-1", diagnostic_name = "CLDLIQ", advected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "cld_liq_tend", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "tendency_of_cloud_liquid_dry_mixing_ratio", kind = "kind_phys", intent = "out", units = "kg kg-1 s-1", constituent}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errcode", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "cld_liq_init", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "tfreeze", type = "real", standard_name = "water_temperature_at_freezing", long_name = "Freezing temperature of water at sea level", kind = "kind_phys", intent = "in", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "tcld", type = "real", standard_name = "minimum_temperature_for_cloud_liquid", kind = "kind_phys", intent = "out", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errcode", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "cld_liq"} : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "apply_constituent_tendencies", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "apply_constituent_tendencies_run", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "const_tend", type = "real", dimensions = #builtin.int<3>, dim_names = "horizontal_dimension,vertical_layer_dimension,number_of_ccpp_constituents", standard_name = "ccpp_constituent_tendencies", long_name = "ccpp constituent tendencies", kind = "kind_phys", intent = "inout", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "const", type = "real", dimensions = #builtin.int<3>, dim_names = "horizontal_dimension,vertical_layer_dimension,number_of_ccpp_constituents", standard_name = "ccpp_constituents", long_name = "ccpp constituents", kind = "kind_phys", intent = "inout", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errcode", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "apply_constituent_tendencies"} : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "physics_state", type = #ccpp<table_type_kind ddt>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "physics_state", type = #ccpp<table_type_kind ddt>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "ps", type = "real", dimensions = #builtin.int<1>, dim_names = "horizontal_dimension", standard_name = "surface_air_pressure", kind = "kind_phys", units = "hPa"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "temp", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "temperature", kind = "kind_phys", units = "K"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "q", type = "real", dimensions = #builtin.int<3>, dim_names = "horizontal_dimension,vertical_layer_dimension,number_of_ccpp_constituents", standard_name = "state_constituent_mixing_ratio", kind = "kind_phys", units = "kg kg-1"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "q(:,:,index_of_water_vapor_specific_humidity)", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "water_vapor_specific_humidity", kind = "kind_phys", units = "kg kg-1"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "data"} : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "data", type = #ccpp<table_type_kind module>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "data", type = #ccpp<table_type_kind module>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "ncols", type = "integer", standard_name = "horizontal_dimension", long_name = "horizontal dimension", units = "count", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "pver", type = "integer", standard_name = "vertical_layer_dimension", long_name = "vertical layer dimension", units = "count", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "dt", type = "real", standard_name = "time_step_for_physics", long_name = "time step for physics", kind = "kind_phys", units = "s", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "tfreeze", type = "real", standard_name = "water_temperature_at_freezing", long_name = "freezing temperature of water at sea level", kind = "kind_phys", units = "K", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "index_qv", type = "integer", standard_name = "index_of_water_vapor_specific_humidity", long_name = "index of water vapor specific humidity in the constituent array", units = "index", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "phys_state", type = "physics_state", dimensions = #builtin.int<1>, dim_names = "number_of_instances", standard_name = "physics_state_derived_type", long_name = "per-instance physics state DDT", units = "none"}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "data"} : () -> ()
// CHECK-NEXT:    "ccpp.table_properties"() <{name = "test_host", type = #ccpp<table_type_kind host>}> ({
// CHECK-NEXT:      "ccpp.arg_table"() <{name = "test_host", type = #ccpp<table_type_kind host>}> ({
// CHECK-NEXT:        "ccpp.arg"() <{name = "lb", type = "integer", standard_name = "horizontal_loop_begin", long_name = "start of horizontal range for this phase", units = "index", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "ub", type = "integer", standard_name = "horizontal_loop_end", long_name = "end of horizontal range for this phase", units = "index", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", units = "none"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "errcode", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", units = "1"}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "instance", type = "integer", standard_name = "instance_number", long_name = "current model instance number", units = "index", protected}> : () -> ()
// CHECK-NEXT:        "ccpp.arg"() <{name = "ninstances", type = "integer", standard_name = "number_of_instances", long_name = "number of instances for multi-instance test", units = "count", protected}> : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:    }) {source_module = "test_host"} : () -> ()
// CHECK-NEXT:  }
