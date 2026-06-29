"""Python suite definition for the CAM4 physics suite.

Python equivalent of suite_cam4.xml from ESCOMP/atmospheric_physics.
CAM4 uses ZM deep convection, Hack shallow convection, Rasch-Kristjansson
stratiform microphysics/macrophysics, RRTMGP radiation (with shortwave and
longwave diagnostic subcycles), Holtslag-Boville vertical diffusion, and
orographic gravity wave drag.

The RRTMGP shortwave and longwave diagnostic subcycles use the CCPP standard
name ``number_of_diagnostic_subcycles``, resolved at runtime by the host model.

Run to emit MLIR IR (from the xdsl-ccpp root):
    python3 examples/atmospheric_physics/suite_cam4_py.py
"""

from xdsl_ccpp.frontend.py_api import (
    ccpp_scheme_from_meta,
    forLoop,
    ccpp_suite,
    emit_ir,
)

_AP    = "../atmospheric_physics/schemes"
_TEND  = f"{_AP}/utilities/physics_tendency_updaters.meta"
_CONV  = f"{_AP}/utilities/state_converters.meta"
_ENER  = f"{_AP}/conservation_adjust/check_energy"
_DIAG  = f"{_AP}/sima_diagnostics"
_ZM    = f"{_AP}/zhang_mcfarlane"
_GWD   = f"{_AP}/gravity_wave_drag"
_HB    = f"{_AP}/holtslag_boville"
_VDIFF = f"{_AP}/vertical_diffusion"
_RK    = f"{_AP}/rasch_kristjansson"
_RRTM  = f"{_AP}/rrtmgp"

# ---------------------------------------------------------------------------
# Schemes
# ---------------------------------------------------------------------------

to_be_ccppized_temporary         = ccpp_scheme_from_meta(f"{_AP}/utilities/to_be_ccppized_temporary.meta")
prescribe_radiative_gas_concentrations = ccpp_scheme_from_meta(
    f"{_AP}/radiation_utils/prescribe_radiative_gas_concentrations.meta")
zm_conv_options                  = ccpp_scheme_from_meta(f"{_ZM}/zm_conv_options.meta")
check_energy_gmean               = ccpp_scheme_from_meta(f"{_ENER}/check_energy_gmean/check_energy_gmean.meta")
check_energy_gmean_diagnostics   = ccpp_scheme_from_meta(f"{_DIAG}/check_energy_gmean_diagnostics.meta")
check_energy_zero_fluxes         = ccpp_scheme_from_meta(f"{_ENER}/check_energy_zero_fluxes.meta")
check_energy_fix                 = ccpp_scheme_from_meta(f"{_ENER}/check_energy_fix.meta")
apply_heating_rate               = ccpp_scheme_from_meta(_TEND, name="apply_heating_rate")
geopotential_temp                = ccpp_scheme_from_meta(f"{_AP}/utilities/geopotential_temp.meta")
check_energy_scaling             = ccpp_scheme_from_meta(f"{_ENER}/check_energy_scaling.meta")
check_energy_chng                = ccpp_scheme_from_meta(f"{_ENER}/check_energy_chng.meta")
dadadj                           = ccpp_scheme_from_meta(f"{_AP}/dry_adiabatic_adjust/dadadj.meta")
apply_constituent_tendencies     = ccpp_scheme_from_meta(_TEND, name="apply_constituent_tendencies")
qneg                             = ccpp_scheme_from_meta(f"{_AP}/utilities/qneg.meta")
zm_convr                         = ccpp_scheme_from_meta(f"{_ZM}/zm_convr.meta")
zm_convr_tendency_diagnostics    = ccpp_scheme_from_meta(f"{_DIAG}/zm_convr_tendency_diagnostics.meta")
cloud_fraction_fice              = ccpp_scheme_from_meta(f"{_AP}/cloud_fraction/cloud_fraction_fice.meta")
set_deep_conv_fluxes_to_general  = ccpp_scheme_from_meta(f"{_ZM}/set_deep_conv_fluxes_to_general.meta")
zm_conv_evap                     = ccpp_scheme_from_meta(f"{_ZM}/zm_conv_evap.meta")
set_general_conv_fluxes_to_deep  = ccpp_scheme_from_meta(f"{_ZM}/set_general_conv_fluxes_to_deep.meta")
zm_evap_tendency_diagnostics     = ccpp_scheme_from_meta(f"{_DIAG}/zm_evap_tendency_diagnostics.meta")
zm_conv_momtran                  = ccpp_scheme_from_meta(f"{_ZM}/zm_conv_momtran.meta")
zm_momtran_tendency_diagnostics  = ccpp_scheme_from_meta(f"{_DIAG}/zm_momtran_tendency_diagnostics.meta")
apply_tendency_of_eastward_wind  = ccpp_scheme_from_meta(_TEND, name="apply_tendency_of_eastward_wind")
apply_tendency_of_northward_wind = ccpp_scheme_from_meta(_TEND, name="apply_tendency_of_northward_wind")
zm_conv_convtran                 = ccpp_scheme_from_meta(f"{_ZM}/zm_conv_convtran.meta")
zm_tendency_diagnostics          = ccpp_scheme_from_meta(f"{_DIAG}/zm_tendency_diagnostics.meta")
zm_diagnostics                   = ccpp_scheme_from_meta(f"{_DIAG}/zm_diagnostics.meta")
convect_shallow_diagnostics      = ccpp_scheme_from_meta(f"{_DIAG}/convect_shallow_diagnostics.meta",
                                                         name="convect_shallow_diagnostics")
hack_convect_shallow             = ccpp_scheme_from_meta(f"{_AP}/hack_shallow/hack_convect_shallow.meta")
convect_shallow_diagnostics_after_shallow_scheme = ccpp_scheme_from_meta(
    f"{_DIAG}/convect_shallow_diagnostics.meta",
    name="convect_shallow_diagnostics_after_shallow_scheme")
set_shallow_conv_fluxes_to_general = ccpp_scheme_from_meta(
    f"{_AP}/hack_shallow/set_shallow_conv_fluxes_to_general.meta")
set_general_conv_fluxes_to_shallow = ccpp_scheme_from_meta(
    f"{_AP}/hack_shallow/set_general_conv_fluxes_to_shallow.meta")
convect_shallow_diagnostics_after_convective_evaporation = ccpp_scheme_from_meta(
    f"{_DIAG}/convect_shallow_diagnostics.meta",
    name="convect_shallow_diagnostics_after_convective_evaporation")
convect_shallow_sum_to_deep      = ccpp_scheme_from_meta(f"{_AP}/hack_shallow/convect_shallow_sum_to_deep.meta")
convect_shallow_diagnostics_after_sum_to_deep = ccpp_scheme_from_meta(
    f"{_DIAG}/convect_shallow_diagnostics.meta",
    name="convect_shallow_diagnostics_after_sum_to_deep")
tropopause_find                  = ccpp_scheme_from_meta(f"{_AP}/tropopause_find/tropopause_find.meta")
rk_stratiform_diagnostics        = ccpp_scheme_from_meta(f"{_DIAG}/rk_stratiform_diagnostics.meta",
                                                         name="rk_stratiform_diagnostics")
rk_stratiform_check_qtlcwat      = ccpp_scheme_from_meta(f"{_RK}/rk_stratiform.meta",
                                                         name="rk_stratiform_check_qtlcwat")
cloud_particle_sedimentation     = ccpp_scheme_from_meta(f"{_RK}/cloud_particle_sedimentation.meta")
cloud_particle_sedimentation_diagnostics = ccpp_scheme_from_meta(
    f"{_DIAG}/cloud_particle_sedimentation_diagnostics.meta")
rk_stratiform_sedimentation      = ccpp_scheme_from_meta(f"{_RK}/rk_stratiform.meta",
                                                         name="rk_stratiform_sedimentation")
rk_stratiform_detrain_convective_condensate = ccpp_scheme_from_meta(
    f"{_RK}/rk_stratiform.meta", name="rk_stratiform_detrain_convective_condensate")
convective_cloud_cover           = ccpp_scheme_from_meta(f"{_AP}/cloud_fraction/convective_cloud_cover.meta")
convective_cloud_cover_diagnostics = ccpp_scheme_from_meta(f"{_DIAG}/convective_cloud_cover_diagnostics.meta")
compute_cloud_fraction           = ccpp_scheme_from_meta(f"{_AP}/cloud_fraction/compute_cloud_fraction.meta")
rk_stratiform_cloud_fraction_perturbation = ccpp_scheme_from_meta(
    f"{_RK}/rk_stratiform.meta", name="rk_stratiform_cloud_fraction_perturbation")
rk_stratiform_cloud_fraction_perturbation_diagnostics = ccpp_scheme_from_meta(
    f"{_DIAG}/rk_stratiform_diagnostics.meta",
    name="rk_stratiform_cloud_fraction_perturbation_diagnostics")
rk_stratiform_external_forcings  = ccpp_scheme_from_meta(f"{_RK}/rk_stratiform.meta",
                                                         name="rk_stratiform_external_forcings")
prognostic_cloud_water           = ccpp_scheme_from_meta(f"{_RK}/prognostic_cloud_water.meta")
rk_stratiform_condensate_repartioning = ccpp_scheme_from_meta(
    f"{_RK}/rk_stratiform.meta", name="rk_stratiform_condensate_repartioning")
rk_stratiform_condensate_repartioning_diagnostics = ccpp_scheme_from_meta(
    f"{_DIAG}/rk_stratiform_diagnostics.meta",
    name="rk_stratiform_condensate_repartioning_diagnostics")
rk_stratiform_prognostic_cloud_water_tendencies = ccpp_scheme_from_meta(
    f"{_RK}/rk_stratiform.meta", name="rk_stratiform_prognostic_cloud_water_tendencies")
rk_stratiform_prognostic_cloud_water_tendencies_diagnostics = ccpp_scheme_from_meta(
    f"{_DIAG}/rk_stratiform_diagnostics.meta",
    name="rk_stratiform_prognostic_cloud_water_tendencies_diagnostics")
compute_cloud_fraction_diagnostics = ccpp_scheme_from_meta(
    f"{_DIAG}/compute_cloud_fraction_diagnostics.meta")
rk_stratiform_cloud_optical_properties = ccpp_scheme_from_meta(
    f"{_RK}/rk_stratiform.meta", name="rk_stratiform_cloud_optical_properties")
rk_stratiform_cloud_optical_properties_diagnostics = ccpp_scheme_from_meta(
    f"{_DIAG}/rk_stratiform_diagnostics.meta",
    name="rk_stratiform_cloud_optical_properties_diagnostics")
rk_stratiform_save_qtlcwat       = ccpp_scheme_from_meta(f"{_RK}/rk_stratiform.meta",
                                                         name="rk_stratiform_save_qtlcwat")
sima_state_diagnostics           = ccpp_scheme_from_meta(f"{_DIAG}/sima_state_diagnostics.meta")
rrtmgp_pre                       = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_pre.meta")
rrtmgp_cloud_optics_setup        = ccpp_scheme_from_meta(f"{_RRTM}/utils/rrtmgp_cloud_optics_setup.meta")
rrtmgp_variables                 = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_variables.meta")
rrtmgp_inputs                    = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_inputs.meta")
rrtmgp_sw_cloud_optics           = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_sw_cloud_optics.meta")
rrtmgp_sw_mcica_subcol_gen       = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_sw_mcica_subcol_gen.meta")
rrtmgp_cloud_diagnostics         = ccpp_scheme_from_meta(f"{_DIAG}/rrtmgp_cloud_diagnostics.meta")
rrtmgp_constituents              = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_constituents.meta")
rrtmgp_sw_gas_optics_pre         = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_sw_gas_optics_pre.meta")
rrtmgp_sw_gas_optics             = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_sw_gas_optics.meta")
solar_irradiance_data            = ccpp_scheme_from_meta(f"{_AP}/radiation_utils/solar_irradiance_data.meta")
rrtmgp_sw_solar_var              = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_sw_solar_var.meta")
rrtmgp_sw_aerosols               = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_sw_aerosols.meta")
rrtmgp_sw_rte                    = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_sw_rte.meta")
rrtmgp_sw_calculate_fluxes       = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_sw_calculate_fluxes.meta")
rrtmgp_sw_calculate_heating_rate = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_sw_calculate_heating_rate.meta")
rrtmgp_sw_diagnostics            = ccpp_scheme_from_meta(f"{_DIAG}/rrtmgp_sw_diagnostics.meta")
rrtmgp_subcycle                  = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_subcycle.meta")
rrtmgp_lw_cloud_optics           = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_lw_cloud_optics.meta")
rrtmgp_lw_mcica_subcol_gen       = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_lw_mcica_subcol_gen.meta")
rrtmgp_lw_gas_optics_pre         = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_lw_gas_optics_pre.meta")
rrtmgp_lw_gas_optics             = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_lw_gas_optics.meta")
rrtmgp_lw_aerosols               = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_lw_aerosols.meta")
rrtmgp_lw_rte                    = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_lw_rte.meta")
rrtmgp_lw_calculate_fluxes       = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_lw_calculate_fluxes.meta")
rrtmgp_lw_calculate_heating_rate = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_lw_calculate_heating_rate.meta")
rrtmgp_lw_diagnostics            = ccpp_scheme_from_meta(f"{_DIAG}/rrtmgp_lw_diagnostics.meta")
rrtmgp_inputs_setup              = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_inputs_setup.meta")
rrtmgp_sw_solar_var_setup        = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_sw_solar_var_setup.meta")
rrtmgp_dry_static_energy_tendency = ccpp_scheme_from_meta(
    f"{_RRTM}/utils/rrtmgp_dry_static_energy_tendency.meta")
calculate_net_heating            = ccpp_scheme_from_meta(f"{_RRTM}/utils/calculate_net_heating.meta")
rrtmgp_post                      = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_post.meta")
rrtmgp_diagnostics               = ccpp_scheme_from_meta(f"{_DIAG}/rrtmgp_diagnostics.meta")
tropopause_diagnostics           = ccpp_scheme_from_meta(f"{_DIAG}/tropopause_diagnostics.meta")
calc_dry_air_ideal_gas_density   = ccpp_scheme_from_meta(_CONV, name="calc_dry_air_ideal_gas_density")
set_surface_coupling_vars        = ccpp_scheme_from_meta(f"{_AP}/utilities/set_surface_coupling_vars.meta")
holtslag_boville_diff_options    = ccpp_scheme_from_meta(f"{_HB}/holtslag_boville_diff_options.meta")
vertical_diffusion_options       = ccpp_scheme_from_meta(f"{_VDIFF}/vertical_diffusion_options.meta")
zero_upper_boundary_condition    = ccpp_scheme_from_meta(f"{_VDIFF}/diffusion_stubs.meta",
                                                         name="zero_upper_boundary_condition")
hb_diff_set_vertical_diffusion_top = ccpp_scheme_from_meta(
    f"{_HB}/holtslag_boville_diff_interstitials.meta",
    name="hb_diff_set_vertical_diffusion_top")
tms_beljaars_zero_stub           = ccpp_scheme_from_meta(f"{_VDIFF}/diffusion_stubs.meta",
                                                         name="tms_beljaars_zero_stub")
hb_diff_set_total_surface_stress = ccpp_scheme_from_meta(
    f"{_HB}/holtslag_boville_diff_interstitials.meta",
    name="hb_diff_set_total_surface_stress")
hb_diff_prepare_vertical_diffusion_inputs = ccpp_scheme_from_meta(
    f"{_HB}/holtslag_boville_diff_interstitials.meta",
    name="hb_diff_prepare_vertical_diffusion_inputs")
holtslag_boville_diff            = ccpp_scheme_from_meta(f"{_HB}/holtslag_boville_diff.meta",
                                                         name="holtslag_boville_diff")
hb_pbl_independent_coefficients  = ccpp_scheme_from_meta(f"{_HB}/holtslag_boville_diff.meta",
                                                         name="hb_pbl_independent_coefficients")
hb_pbl_dependent_coefficients    = ccpp_scheme_from_meta(f"{_HB}/holtslag_boville_diff.meta",
                                                         name="hb_pbl_dependent_coefficients")
hb_diff_exchange_coefficients    = ccpp_scheme_from_meta(f"{_HB}/holtslag_boville_diff.meta",
                                                         name="hb_diff_exchange_coefficients")
vertical_diffusion_sponge_layer  = ccpp_scheme_from_meta(f"{_VDIFF}/vertical_diffusion_sponge_layer.meta")
holtslag_boville_diff_diagnostics = ccpp_scheme_from_meta(
    f"{_DIAG}/holtslag_boville_diff_diagnostics.meta")
vertical_diffusion_not_use_rairv = ccpp_scheme_from_meta(f"{_VDIFF}/diffusion_stubs.meta",
                                                         name="vertical_diffusion_not_use_rairv")
vertical_diffusion_set_temperature_at_toa_default = ccpp_scheme_from_meta(
    f"{_VDIFF}/diffusion_solver.meta",
    name="vertical_diffusion_set_temperature_at_toa_default")
vertical_diffusion_interpolate_to_interfaces = ccpp_scheme_from_meta(
    f"{_VDIFF}/diffusion_solver.meta",
    name="vertical_diffusion_interpolate_to_interfaces")
implicit_surface_stress_add_drag_coefficient = ccpp_scheme_from_meta(
    f"{_VDIFF}/diffusion_solver.meta",
    name="implicit_surface_stress_add_drag_coefficient")
vertical_diffusion_wind_damping_rate = ccpp_scheme_from_meta(
    f"{_VDIFF}/diffusion_solver.meta",
    name="vertical_diffusion_wind_damping_rate")
vertical_diffusion_diffuse_horizontal_momentum = ccpp_scheme_from_meta(
    f"{_VDIFF}/diffusion_solver.meta",
    name="vertical_diffusion_diffuse_horizontal_momentum")
vertical_diffusion_set_dry_static_energy_at_toa_zero = ccpp_scheme_from_meta(
    f"{_VDIFF}/diffusion_solver.meta",
    name="vertical_diffusion_set_dry_static_energy_at_toa_zero")
vertical_diffusion_diffuse_dry_static_energy = ccpp_scheme_from_meta(
    f"{_VDIFF}/diffusion_solver.meta",
    name="vertical_diffusion_diffuse_dry_static_energy")
vertical_diffusion_diffuse_tracers = ccpp_scheme_from_meta(
    f"{_VDIFF}/diffusion_solver.meta",
    name="vertical_diffusion_diffuse_tracers")
vertical_diffusion_tendencies    = ccpp_scheme_from_meta(f"{_VDIFF}/diffusion_solver.meta",
                                                         name="vertical_diffusion_tendencies")
vertical_diffusion_tendencies_diagnostics = ccpp_scheme_from_meta(
    f"{_DIAG}/diffusion_solver_diagnostics.meta")
gravity_wave_drag_common         = ccpp_scheme_from_meta(f"{_GWD}/gw_common.meta")
gravity_wave_drag_prepare_profiles = ccpp_scheme_from_meta(f"{_GWD}/gravity_wave_drag_interstitials.meta")
gravity_wave_drag_top_taper      = ccpp_scheme_from_meta(f"{_GWD}/gravity_wave_drag_top_taper.meta")
gravity_wave_drag_orographic     = ccpp_scheme_from_meta(f"{_GWD}/gravity_wave_drag_orographic.meta")
convert_dry_constituent_tendencies_to_dry_air_basis = ccpp_scheme_from_meta(
    f"{_AP}/utilities/convert_dry_constituent_tendencies_to_dry_air_basis.meta")
gravity_wave_drag_common_diagnostics = ccpp_scheme_from_meta(
    f"{_DIAG}/gravity_wave_drag_common_diagnostics.meta")
update_dry_static_energy         = ccpp_scheme_from_meta(f"{_AP}/utilities/static_energy.meta",
                                                         name="update_dry_static_energy")
check_energy_save_teout          = ccpp_scheme_from_meta(f"{_ENER}/check_energy_save_teout.meta")
dycore_energy_consistency_adjust = ccpp_scheme_from_meta(f"{_ENER}/dycore_energy_consistency_adjust.meta")
apply_tendency_of_air_temperature = ccpp_scheme_from_meta(_TEND, name="apply_tendency_of_air_temperature")
sima_tend_diagnostics            = ccpp_scheme_from_meta(f"{_DIAG}/sima_tend_diagnostics.meta")

# ---------------------------------------------------------------------------
# Suite
# Schemes appear in the same order as suite_cam4.xml, including repetitions.
# ---------------------------------------------------------------------------


@ccpp_suite("cam4", version="1.0")
class cam4:
    physics_before_coupler = [
        to_be_ccppized_temporary,
        prescribe_radiative_gas_concentrations,
        zm_conv_options,
        check_energy_gmean,
        check_energy_gmean_diagnostics,
        check_energy_zero_fluxes,
        check_energy_fix,
        apply_heating_rate,
        geopotential_temp,
        check_energy_scaling,
        check_energy_chng,
        # Dry adiabatic adjustment
        dadadj,
        apply_constituent_tendencies,
        apply_heating_rate,
        qneg,
        geopotential_temp,
        # Zhang-McFarlane deep convection
        check_energy_zero_fluxes,
        zm_convr,
        zm_convr_tendency_diagnostics,
        apply_heating_rate,
        apply_constituent_tendencies,
        qneg,
        geopotential_temp,
        cloud_fraction_fice,
        set_deep_conv_fluxes_to_general,
        zm_conv_evap,
        set_general_conv_fluxes_to_deep,
        zm_evap_tendency_diagnostics,
        apply_heating_rate,
        apply_constituent_tendencies,
        qneg,
        geopotential_temp,
        cloud_fraction_fice,
        zm_conv_momtran,
        zm_momtran_tendency_diagnostics,
        apply_heating_rate,
        apply_tendency_of_eastward_wind,
        apply_tendency_of_northward_wind,
        geopotential_temp,
        zm_conv_convtran,
        zm_tendency_diagnostics,
        apply_constituent_tendencies,
        qneg,
        geopotential_temp,
        zm_diagnostics,
        check_energy_scaling,
        check_energy_chng,
        # Hack shallow convection
        convect_shallow_diagnostics,
        check_energy_zero_fluxes,
        hack_convect_shallow,
        convect_shallow_diagnostics_after_shallow_scheme,
        apply_heating_rate,
        apply_constituent_tendencies,
        qneg,
        geopotential_temp,
        cloud_fraction_fice,
        set_shallow_conv_fluxes_to_general,
        zm_conv_evap,
        set_general_conv_fluxes_to_shallow,
        convect_shallow_diagnostics_after_convective_evaporation,
        apply_heating_rate,
        apply_constituent_tendencies,
        qneg,
        geopotential_temp,
        convect_shallow_sum_to_deep,
        convect_shallow_diagnostics_after_sum_to_deep,
        check_energy_scaling,
        check_energy_chng,
        # Rasch-Kristjansson stratiform microphysics
        tropopause_find,
        rk_stratiform_diagnostics,
        rk_stratiform_check_qtlcwat,
        cloud_particle_sedimentation,
        cloud_particle_sedimentation_diagnostics,
        apply_constituent_tendencies,
        apply_heating_rate,
        qneg,
        geopotential_temp,
        rk_stratiform_sedimentation,
        rk_stratiform_detrain_convective_condensate,
        apply_constituent_tendencies,
        qneg,
        geopotential_temp,
        convective_cloud_cover,
        convective_cloud_cover_diagnostics,
        compute_cloud_fraction,
        rk_stratiform_cloud_fraction_perturbation,
        rk_stratiform_cloud_fraction_perturbation_diagnostics,
        rk_stratiform_external_forcings,
        cloud_fraction_fice,
        prognostic_cloud_water,
        rk_stratiform_condensate_repartioning,
        rk_stratiform_condensate_repartioning_diagnostics,
        apply_constituent_tendencies,
        qneg,
        geopotential_temp,
        rk_stratiform_prognostic_cloud_water_tendencies,
        rk_stratiform_prognostic_cloud_water_tendencies_diagnostics,
        apply_constituent_tendencies,
        apply_heating_rate,
        qneg,
        geopotential_temp,
        compute_cloud_fraction,
        compute_cloud_fraction_diagnostics,
        rk_stratiform_cloud_optical_properties,
        rk_stratiform_cloud_optical_properties_diagnostics,
        rk_stratiform_save_qtlcwat,
        sima_state_diagnostics,
        # RRTMGP radiation
        rrtmgp_pre,
        rrtmgp_cloud_optics_setup,
        tropopause_find,
        rrtmgp_variables,
        rrtmgp_inputs,
        rrtmgp_sw_cloud_optics,
        rrtmgp_sw_mcica_subcol_gen,
        rrtmgp_cloud_diagnostics,
        # SW diagnostic subcycle
        forLoop("number_of_diagnostic_subcycles", [
            rrtmgp_constituents,
            rrtmgp_sw_gas_optics_pre,
            rrtmgp_sw_gas_optics,
            solar_irradiance_data,
            rrtmgp_sw_solar_var,
            rrtmgp_sw_aerosols,
            rrtmgp_sw_rte,
            rrtmgp_sw_calculate_fluxes,
            rrtmgp_sw_calculate_heating_rate,
            rrtmgp_sw_diagnostics,
            rrtmgp_subcycle,
        ]),
        rrtmgp_lw_cloud_optics,
        rrtmgp_lw_mcica_subcol_gen,
        # LW diagnostic subcycle
        forLoop("number_of_diagnostic_subcycles", [
            rrtmgp_constituents,
            rrtmgp_lw_gas_optics_pre,
            rrtmgp_lw_gas_optics,
            rrtmgp_lw_aerosols,
            rrtmgp_lw_rte,
            rrtmgp_lw_calculate_fluxes,
            rrtmgp_lw_calculate_heating_rate,
            rrtmgp_lw_diagnostics,
            rrtmgp_subcycle,
        ]),
        rrtmgp_inputs_setup,
        rrtmgp_sw_solar_var_setup,
        rrtmgp_dry_static_energy_tendency,
        calculate_net_heating,
        rrtmgp_post,
        rrtmgp_diagnostics,
        apply_heating_rate,
        geopotential_temp,
        tropopause_find,
        tropopause_diagnostics,
        calc_dry_air_ideal_gas_density,
        set_surface_coupling_vars,
    ]
    physics_after_coupler = [
        # Holtslag-Boville vertical diffusion
        holtslag_boville_diff_options,
        vertical_diffusion_options,
        zero_upper_boundary_condition,
        hb_diff_set_vertical_diffusion_top,
        tms_beljaars_zero_stub,
        hb_diff_set_total_surface_stress,
        hb_diff_prepare_vertical_diffusion_inputs,
        holtslag_boville_diff,
        hb_pbl_independent_coefficients,
        hb_pbl_dependent_coefficients,
        hb_diff_exchange_coefficients,
        vertical_diffusion_sponge_layer,
        holtslag_boville_diff_diagnostics,
        vertical_diffusion_not_use_rairv,
        vertical_diffusion_set_temperature_at_toa_default,
        vertical_diffusion_interpolate_to_interfaces,
        implicit_surface_stress_add_drag_coefficient,
        vertical_diffusion_wind_damping_rate,
        vertical_diffusion_diffuse_horizontal_momentum,
        vertical_diffusion_set_dry_static_energy_at_toa_zero,
        vertical_diffusion_diffuse_dry_static_energy,
        vertical_diffusion_diffuse_tracers,
        vertical_diffusion_tendencies,
        vertical_diffusion_tendencies_diagnostics,
        apply_tendency_of_northward_wind,
        apply_tendency_of_eastward_wind,
        apply_constituent_tendencies,
        apply_heating_rate,
        qneg,
        geopotential_temp,
        update_dry_static_energy,
        # Orographic gravity wave drag
        gravity_wave_drag_common,
        check_energy_zero_fluxes,
        gravity_wave_drag_prepare_profiles,
        gravity_wave_drag_top_taper,
        gravity_wave_drag_orographic,
        convert_dry_constituent_tendencies_to_dry_air_basis,
        gravity_wave_drag_common_diagnostics,
        apply_tendency_of_eastward_wind,
        apply_tendency_of_northward_wind,
        apply_constituent_tendencies,
        apply_heating_rate,
        qneg,
        geopotential_temp,
        update_dry_static_energy,
        check_energy_scaling,
        check_energy_chng,
        check_energy_save_teout,
        check_energy_scaling,
        dycore_energy_consistency_adjust,
        apply_tendency_of_air_temperature,
        sima_tend_diagnostics,
    ]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    emit_ir(cam4)
