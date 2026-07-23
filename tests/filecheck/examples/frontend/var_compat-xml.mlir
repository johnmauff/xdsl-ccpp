// Test the XML frontend IR for the var_compat example -- ported from NCAR
// ccpp-framework's feature/capgen-v1 branch, end-to-end-tests/var_compat.
// Exercises: nested <subcycle> parsing to three levels deep in one branch
// (a dynamic-count subcycle containing two nested loop="2" subcycles around
// effr_calc), plus a second sibling dynamic-count subcycle (effrs_calc) sharing
// the same standard_name (num_subcycles_for_effr) -- this is the primary
// frontend-level regression coverage for the nested-subcycle-support work.
// See examples/var_compat/README.md for what this example does and does not
// cover (top_at_one/kind-conversion fidelity and a dummy-argument-name
// collision are separate, already-tracked, out-of-scope issues).
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/var_compat/var_compatibility_suite.xml --scheme-files examples/var_compat/effr_pre.meta,examples/var_compat/effr_calc.meta,examples/var_compat/effr_post.meta,examples/var_compat/effrs_calc.meta,examples/var_compat/effr_diag.meta,examples/var_compat/rad_lw.meta,examples/var_compat/rad_sw.meta --host-files examples/var_compat/test_host_data.meta,examples/var_compat/test_host_mod.meta,examples/var_compat/test_host.meta | python3 -m filecheck %s

// Suite/group structure: the nested-subcycle shape under test.

// CHECK:       builtin.module {
// CHECK-NEXT:   "ccpp.suite"() <{suite_name = "var_compatibility_suite", version = "1.0"}> ({
// CHECK-NEXT:     "ccpp.group"() <{group_name = "radiation"}> ({
// CHECK-NEXT:       "ccpp.subcycle"() <{loop_count = "num_subcycles_for_effr", is_literal = false}> ({
// CHECK-NEXT:         "ccpp.scheme"() <{scheme_name = "effr_pre"}> : () -> ()
// CHECK-NEXT:         "ccpp.subcycle"() <{loop_count = "2", is_literal = true}> ({
// CHECK-NEXT:           "ccpp.subcycle"() <{loop_count = "2", is_literal = true}> ({
// CHECK-NEXT:             "ccpp.scheme"() <{scheme_name = "effr_calc"}> : () -> ()
// CHECK-NEXT:           }) : () -> ()
// CHECK-NEXT:         }) : () -> ()
// CHECK-NEXT:         "ccpp.scheme"() <{scheme_name = "effr_post"}> : () -> ()
// CHECK-NEXT:       }) : () -> ()
// CHECK-NEXT:       "ccpp.subcycle"() <{loop_count = "num_subcycles_for_effr", is_literal = false}> ({
// CHECK-NEXT:         "ccpp.scheme"() <{scheme_name = "effrs_calc"}> : () -> ()
// CHECK-NEXT:       }) : () -> ()
// CHECK-NEXT:       "ccpp.scheme"() <{scheme_name = "effr_diag"}> : () -> ()
// CHECK-NEXT:       "ccpp.scheme"() <{scheme_name = "rad_lw"}> : () -> ()
// CHECK-NEXT:       "ccpp.scheme"() <{scheme_name = "rad_sw"}> : () -> ()
// CHECK-NEXT:     }) : () -> ()
// CHECK-NEXT:   }) : () -> ()
// CHECK-NEXT:   "ccpp.table_properties"() <{name = "effr_pre", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:     "ccpp.arg_table"() <{name = "effr_pre_init", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:       "ccpp.arg"() <{name = "scheme_order", type = "integer", standard_name = "scheme_order_in_suite", long_name = "scheme order in suite definition file", intent = "inout", units = "None"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:     }) : () -> ()
// CHECK-NEXT:     "ccpp.arg_table"() <{name = "effr_pre_run", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:       "ccpp.arg"() <{name = "effrr_inout", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "effective_radius_of_stratiform_cloud_rain_particle", long_name = "effective radius of cloud rain particle in micrometer", kind = "kind_phys", intent = "inout", units = "m"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "scalar_var", type = "real", standard_name = "scalar_variable_for_testing_a", long_name = "unused scalar variable A", kind = "kind_phys", intent = "in", units = "m"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:     }) : () -> ()
// CHECK-NEXT:   }) {source_module = "effr_pre"} : () -> ()
// CHECK-NEXT:   "ccpp.table_properties"() <{name = "effr_calc", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:     "ccpp.arg_table"() <{name = "effr_calc_init", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:       "ccpp.arg"() <{name = "scheme_order", type = "integer", standard_name = "scheme_order_in_suite", long_name = "scheme order in suite definition file", intent = "inout", units = "None"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:     }) : () -> ()
// CHECK-NEXT:     "ccpp.arg_table"() <{name = "effr_calc_run", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:       "ccpp.arg"() <{name = "ncol", type = "integer", standard_name = "horizontal_dimension", intent = "in", units = "count"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "nlev", type = "integer", standard_name = "vertical_layer_dimension", intent = "in", units = "count"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "effrr_in", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "effective_radius_of_stratiform_cloud_rain_particle", long_name = "effective radius of cloud rain particle in micrometer", kind = "kind_phys", intent = "in", units = "um"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "effrg_in", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "effective_radius_of_stratiform_cloud_graupel", long_name = "effective radius of cloud graupel in micrometer", kind = "kind_phys", intent = "in", units = "um", optional}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "ncg_in", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "cloud_graupel_number_concentration", long_name = "number concentration of cloud graupel", kind = "kind_phys", intent = "in", units = "kg-1", optional}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "nci_out", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "cloud_ice_number_concentration", long_name = "number concentration of cloud ice", kind = "kind_phys", intent = "out", units = "kg-1", optional}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "effrl_inout", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "effective_radius_of_stratiform_cloud_liquid_water_particle", long_name = "effective radius of cloud liquid water particle in micrometer", kind = "kind_phys", intent = "inout", units = "um"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "effri_out", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "effective_radius_of_stratiform_cloud_ice_particle", long_name = "effective radius of cloud ice water particle in micrometer", kind = "kind_phys", intent = "out", units = "um", optional}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "effrs_inout", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "effective_radius_of_stratiform_cloud_snow_particle", long_name = "effective radius of cloud snow particle in micrometer", kind = "8", intent = "inout", units = "um"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "ncl_out", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "cloud_liquid_number_concentration", long_name = "number concentration of cloud liquid", kind = "kind_phys", intent = "out", units = "kg-1", optional}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "has_graupel", type = "logical", standard_name = "flag_indicating_cloud_microphysics_has_graupel", long_name = "flag indicating that the cloud microphysics produces graupel", intent = "in", units = "flag"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "scalar_var", type = "real", standard_name = "scalar_variable_for_testing", long_name = "scalar variable for testing", kind = "kind_phys", intent = "inout", units = "km"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "tke_inout", type = "real", standard_name = "turbulent_kinetic_energy", long_name = "turbulent_kinetic_energy", kind = "kind_phys", intent = "inout", units = "m2 s-2"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "tke2_inout", type = "real", standard_name = "turbulent_kinetic_energy2", long_name = "turbulent_kinetic_energy2", kind = "kind_phys", intent = "inout", units = "m+2 s-2"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:     }) : () -> ()
// CHECK-NEXT:   }) {source_module = "effr_calc"} : () -> ()
// CHECK-NEXT:   "ccpp.table_properties"() <{name = "effr_post", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:     "ccpp.arg_table"() <{name = "effr_post_init", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:       "ccpp.arg"() <{name = "scheme_order", type = "integer", standard_name = "scheme_order_in_suite", long_name = "scheme order in suite definition file", intent = "inout", units = "None"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:     }) : () -> ()
// CHECK-NEXT:     "ccpp.arg_table"() <{name = "effr_post_run", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:       "ccpp.arg"() <{name = "effrr_inout", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "effective_radius_of_stratiform_cloud_rain_particle", long_name = "effective radius of cloud rain particle in micrometer", kind = "kind_phys", intent = "inout", units = "m"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "scalar_var", type = "real", standard_name = "scalar_variable_for_testing_b", long_name = "unused scalar variable B", kind = "kind_phys", intent = "in", units = "m"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:     }) : () -> ()
// CHECK-NEXT:   }) {source_module = "effr_post"} : () -> ()
// CHECK-NEXT:   "ccpp.table_properties"() <{name = "effrs_calc", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:     "ccpp.arg_table"() <{name = "effrs_calc_run", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:       "ccpp.arg"() <{name = "effrs_inout", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "effective_radius_of_stratiform_cloud_snow_particle", kind = "kind_phys", intent = "inout", units = "m"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:     }) : () -> ()
// CHECK-NEXT:   }) {source_module = "effrs_calc"} : () -> ()
// CHECK-NEXT:   "ccpp.table_properties"() <{name = "effr_diag", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:     "ccpp.arg_table"() <{name = "effr_diag_init", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:       "ccpp.arg"() <{name = "scheme_order", type = "integer", standard_name = "scheme_order_in_suite", long_name = "scheme order in suite definition file", intent = "inout", units = "None"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:     }) : () -> ()
// CHECK-NEXT:     "ccpp.arg_table"() <{name = "effr_diag_run", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:       "ccpp.arg"() <{name = "effrr_in", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "effective_radius_of_stratiform_cloud_rain_particle", long_name = "effective radius of cloud rain particle in micrometer", kind = "kind_phys", intent = "in", units = "um"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "scalar_var", type = "integer", standard_name = "scalar_variable_for_testing_c", long_name = "unused scalar variable C", intent = "in", units = "m"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:     }) : () -> ()
// CHECK-NEXT:   }) {source_module = "effr_diag"} : () -> ()
// CHECK-NEXT:   "ccpp.table_properties"() <{name = "rad_lw", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:     "ccpp.arg_table"() <{name = "rad_lw_run", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:       "ccpp.arg"() <{name = "ncol", type = "integer", standard_name = "horizontal_dimension", intent = "in", units = "count"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "fluxLW", type = "ty_rad_lw", dimensions = #builtin.int<1>, dim_names = "horizontal_dimension", standard_name = "longwave_radiation_fluxes", long_name = "longwave radiation fluxes", intent = "inout", units = "W m-2"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:     }) : () -> ()
// CHECK-NEXT:   }) {source_module = "rad_lw"} : () -> ()
// CHECK-NEXT:   "ccpp.table_properties"() <{name = "rad_sw", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:     "ccpp.arg_table"() <{name = "rad_sw_run", type = #ccpp<table_type_kind scheme>}> ({
// CHECK-NEXT:       "ccpp.arg"() <{name = "ncol", type = "integer", standard_name = "horizontal_dimension", intent = "in", units = "count"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "sfc_up_sw", type = "real", dimensions = #builtin.int<1>, dim_names = "horizontal_dimension", standard_name = "surface_upwelling_shortwave_radiation_flux", kind = "kind_phys", intent = "inout", units = "W m2"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "sfc_down_sw", type = "real", dimensions = #builtin.int<1>, dim_names = "horizontal_dimension", standard_name = "surface_downwelling_shortwave_radiation_flux", kind = "kind_phys", intent = "inout", units = "W m2"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", intent = "out", units = "none"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", intent = "out", units = "1"}> : () -> ()
// CHECK-NEXT:     }) : () -> ()
// CHECK-NEXT:   }) {source_module = "rad_sw"} : () -> ()
// CHECK-NEXT:   "ccpp.table_properties"() <{name = "physics_state", type = #ccpp<table_type_kind ddt>}> ({
// CHECK-NEXT:     "ccpp.arg_table"() <{name = "physics_state", type = #ccpp<table_type_kind ddt>}> ({
// CHECK-NEXT:       "ccpp.arg"() <{name = "effrr", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "effective_radius_of_stratiform_cloud_rain_particle", long_name = "effective radius of cloud rain particle in meter", kind = "kind_phys", units = "m"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "effrl", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "effective_radius_of_stratiform_cloud_liquid_water_particle", long_name = "effective radius of cloud liquid water particle in meter", kind = "kind_phys", units = "m"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "effri", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "effective_radius_of_stratiform_cloud_ice_particle", long_name = "effective radius of cloud ice water particle in meter", kind = "kind_phys", units = "m", active = "(flag_indicating_cloud_microphysics_has_ice)"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "effrg", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "effective_radius_of_stratiform_cloud_graupel", long_name = "effective radius of cloud graupel in meter", kind = "kind_phys", units = "m", active = "(flag_indicating_cloud_microphysics_has_graupel)"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "ncg", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "cloud_graupel_number_concentration", long_name = "number concentration of cloud graupel", kind = "kind_phys", units = "kg-1", active = "(flag_indicating_cloud_microphysics_has_graupel)"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "nci", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "cloud_ice_number_concentration", long_name = "number concentration of cloud ice", kind = "kind_phys", units = "kg-1", active = "(flag_indicating_cloud_microphysics_has_ice)"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "scalar_var", type = "real", standard_name = "scalar_variable_for_testing", long_name = "unused scalar variable", kind = "kind_phys", units = "m"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "tke", type = "real", standard_name = "turbulent_kinetic_energy", long_name = "turbulent_kinetic_energy", kind = "kind_phys", units = "J kg-1"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "tke2", type = "real", standard_name = "turbulent_kinetic_energy2", long_name = "turbulent_kinetic_energy2", kind = "kind_phys", units = "m2 s-2"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "fluxSW", type = "ty_rad_sw", standard_name = "shortwave_radiation_fluxes", long_name = "shortwave radiation fluxes", units = "W m-2"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "fluxLW", type = "ty_rad_lw", dimensions = #builtin.int<1>, dim_names = "horizontal_dimension", standard_name = "longwave_radiation_fluxes", long_name = "longwave radiation fluxes", units = "W m-2"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "scalar_varA", type = "real", standard_name = "scalar_variable_for_testing_a", long_name = "unused scalar variable A", kind = "kind_phys", units = "m"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "scalar_varB", type = "real", standard_name = "scalar_variable_for_testing_b", long_name = "unused scalar variable B", kind = "kind_phys", units = "m"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "scalar_varC", type = "integer", standard_name = "scalar_variable_for_testing_c", long_name = "unused scalar variable C", units = "m"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "scheme_order", type = "integer", standard_name = "scheme_order_in_suite", long_name = "scheme order in suite definition file", units = "None"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "num_subcycles", type = "integer", standard_name = "num_subcycles_for_effr", long_name = "Number of times to subcycle the effr calculation", units = "None"}> : () -> ()
// CHECK-NEXT:     }) : () -> ()
// CHECK-NEXT:   }) {source_module = "test_host_data"} : () -> ()
// CHECK-NEXT:   "ccpp.table_properties"() <{name = "test_host_mod", type = #ccpp<table_type_kind host>}> ({
// CHECK-NEXT:     "ccpp.arg_table"() <{name = "test_host_mod", type = #ccpp<table_type_kind host>}> ({
// CHECK-NEXT:       "ccpp.arg"() <{name = "ncols", type = "integer", standard_name = "horizontal_dimension", units = "count", protected}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "pver", type = "integer", standard_name = "vertical_layer_dimension", units = "count", protected}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "phys_state", type = "physics_state", standard_name = "physics_state_derived_type", long_name = "Physics State DDT"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "effrs", type = "real", dimensions = #builtin.int<2>, dim_names = "horizontal_dimension,vertical_layer_dimension", standard_name = "effective_radius_of_stratiform_cloud_snow_particle", long_name = "effective radius of cloud snow particle in meter", kind = "kind_phys", units = "m"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "has_ice", type = "logical", standard_name = "flag_indicating_cloud_microphysics_has_ice", long_name = "flag indicating that the cloud microphysics produces ice", units = "flag"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "has_graupel", type = "logical", standard_name = "flag_indicating_cloud_microphysics_has_graupel", long_name = "flag indicating that the cloud microphysics produces graupel", units = "flag"}> : () -> ()
// CHECK-NEXT:     }) : () -> ()
// CHECK-NEXT:   }) {source_module = "test_host_mod"} : () -> ()
// CHECK-NEXT:   "ccpp.table_properties"() <{name = "suite_info", type = #ccpp<table_type_kind ddt>}> ({
// CHECK-NEXT:     "ccpp.arg_table"() <{name = "suite_info", type = #ccpp<table_type_kind ddt>}> ({
// CHECK-NEXT:     ^bb0:
// CHECK-NEXT:     }) : () -> ()
// CHECK-NEXT:   }) {source_module = "test_host"} : () -> ()
// CHECK-NEXT:   "ccpp.table_properties"() <{name = "test_host", type = #ccpp<table_type_kind host>}> ({
// CHECK-NEXT:     "ccpp.arg_table"() <{name = "test_host", type = #ccpp<table_type_kind host>}> ({
// CHECK-NEXT:       "ccpp.arg"() <{name = "col_start", type = "integer", standard_name = "horizontal_loop_begin", units = "count", protected}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "col_end", type = "integer", standard_name = "horizontal_loop_end", units = "count", protected}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "errmsg", type = "character", standard_name = "ccpp_error_message", long_name = "Error message for error handling in CCPP", kind = "len=512", units = "none"}> : () -> ()
// CHECK-NEXT:       "ccpp.arg"() <{name = "errflg", type = "integer", standard_name = "ccpp_error_code", long_name = "Error flag for error handling in CCPP", units = "1"}> : () -> ()
// CHECK-NEXT:     }) : () -> ()
// CHECK-NEXT:   }) {source_module = "test_host"} : () -> ()
// CHECK-NEXT: }
