"""Python suite definition for the CAM7 physics suite.

Python equivalent of suite_cam7.xml from ESCOMP/atmospheric_physics.
CAM7 uses ZM deep convection, gravity wave drag (convective, frontogenesis,
ridge, moving-mountain), and the SIMA energy bookkeeping framework.

Run to emit MLIR IR (from the xdsl-ccpp root):
    python3 examples/atmospheric_physics/suite_cam7_py.py
"""

from xdsl_ccpp.frontend.py_api import ccpp_scheme_from_meta, ccpp_suite, emit_ir

_AP   = "../atmospheric_physics/schemes"
_TEND = f"{_AP}/utilities/physics_tendency_updaters.meta"
_CONV = f"{_AP}/utilities/state_converters.meta"
_ENER = f"{_AP}/conservation_adjust/check_energy"
_DIAG = f"{_AP}/sima_diagnostics"
_ZM   = f"{_AP}/zhang_mcfarlane"
_GWD  = f"{_AP}/gravity_wave_drag"

# ---------------------------------------------------------------------------
# Schemes
# ---------------------------------------------------------------------------

to_be_ccppized_temporary         = ccpp_scheme_from_meta(f"{_AP}/utilities/to_be_ccppized_temporary.meta")
set_cloud_fraction_top           = ccpp_scheme_from_meta(f"{_AP}/cloud_fraction/set_cloud_fraction_top.meta")
check_energy_gmean               = ccpp_scheme_from_meta(f"{_ENER}/check_energy_gmean/check_energy_gmean.meta")
check_energy_gmean_diagnostics   = ccpp_scheme_from_meta(f"{_DIAG}/check_energy_gmean_diagnostics.meta")
check_energy_zero_fluxes         = ccpp_scheme_from_meta(f"{_ENER}/check_energy_zero_fluxes.meta")
check_energy_fix                 = ccpp_scheme_from_meta(f"{_ENER}/check_energy_fix.meta")
apply_heating_rate               = ccpp_scheme_from_meta(_TEND, name="apply_heating_rate")
geopotential_temp                = ccpp_scheme_from_meta(f"{_AP}/utilities/geopotential_temp.meta")
check_energy_scaling             = ccpp_scheme_from_meta(f"{_ENER}/check_energy_scaling.meta")
check_energy_chng                = ccpp_scheme_from_meta(f"{_ENER}/check_energy_chng.meta")
check_energy_fix_diagnostics     = ccpp_scheme_from_meta(f"{_DIAG}/check_energy_fix_diagnostics.meta")
dadadj                           = ccpp_scheme_from_meta(f"{_AP}/dry_adiabatic_adjust/dadadj.meta")
apply_constituent_tendencies     = ccpp_scheme_from_meta(_TEND, name="apply_constituent_tendencies")
qneg                             = ccpp_scheme_from_meta(f"{_AP}/utilities/qneg.meta")
zm_conv_options                  = ccpp_scheme_from_meta(f"{_ZM}/zm_conv_options.meta")
zm_convr                         = ccpp_scheme_from_meta(f"{_ZM}/zm_convr.meta")
zm_convr_tendency_diagnostics    = ccpp_scheme_from_meta(f"{_DIAG}/zm_convr_tendency_diagnostics.meta")
save_ttend_from_convect_deep     = ccpp_scheme_from_meta(f"{_ZM}/save_ttend_from_convect_deep.meta")
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
sima_state_diagnostics           = ccpp_scheme_from_meta(f"{_DIAG}/sima_state_diagnostics.meta")
tropopause_find                  = ccpp_scheme_from_meta(f"{_AP}/tropopause_find/tropopause_find.meta")
tropopause_diagnostics           = ccpp_scheme_from_meta(f"{_DIAG}/tropopause_diagnostics.meta")
gravity_wave_drag_common         = ccpp_scheme_from_meta(f"{_GWD}/gw_common.meta")
gravity_wave_drag_prepare_profiles = ccpp_scheme_from_meta(f"{_GWD}/gravity_wave_drag_interstitials.meta")
gravity_wave_drag_top_taper      = ccpp_scheme_from_meta(f"{_GWD}/gravity_wave_drag_top_taper.meta")
gravity_wave_drag_moving_mountain = ccpp_scheme_from_meta(f"{_GWD}/gravity_wave_drag_moving_mountain.meta")
gravity_wave_drag_convection_deep = ccpp_scheme_from_meta(f"{_GWD}/gravity_wave_drag_convection.meta",
                                                          name="gravity_wave_drag_convection_deep")
gravity_wave_drag_frontogenesis  = ccpp_scheme_from_meta(f"{_GWD}/gravity_wave_drag_frontogenesis.meta")
gravity_wave_drag_ridge          = ccpp_scheme_from_meta(f"{_GWD}/gravity_wave_drag_ridge.meta",
                                                         name="gravity_wave_drag_ridge")
gravity_wave_drag_ridge_beta     = ccpp_scheme_from_meta(f"{_GWD}/gravity_wave_drag_ridge.meta",
                                                         name="gravity_wave_drag_ridge_beta")
convert_dry_constituent_tendencies_to_dry_air_basis = ccpp_scheme_from_meta(
    f"{_AP}/utilities/convert_dry_constituent_tendencies_to_dry_air_basis.meta")
update_dry_static_energy         = ccpp_scheme_from_meta(f"{_AP}/utilities/static_energy.meta",
                                                         name="update_dry_static_energy")
check_energy_save_teout          = ccpp_scheme_from_meta(f"{_ENER}/check_energy_save_teout.meta")
thermo_water_update              = ccpp_scheme_from_meta(f"{_AP}/thermo_water_update/thermo_water_update.meta")
dycore_energy_consistency_adjust = ccpp_scheme_from_meta(f"{_ENER}/dycore_energy_consistency_adjust.meta")
apply_tendency_of_air_temperature = ccpp_scheme_from_meta(_TEND, name="apply_tendency_of_air_temperature")
sima_tend_diagnostics            = ccpp_scheme_from_meta(f"{_DIAG}/sima_tend_diagnostics.meta")

# ---------------------------------------------------------------------------
# Suite
# Schemes appear in the same order as suite_cam7.xml, including repetitions.
# ---------------------------------------------------------------------------


@ccpp_suite("cam7", version="1.0")
class cam7:
    physics_before_coupler = [
        to_be_ccppized_temporary,
        set_cloud_fraction_top,
        check_energy_gmean,
        check_energy_gmean_diagnostics,
        check_energy_zero_fluxes,
        check_energy_fix,
        apply_heating_rate,
        geopotential_temp,
        check_energy_scaling,
        check_energy_chng,
        check_energy_fix_diagnostics,
        # Dry adiabatic adjustment
        dadadj,
        apply_constituent_tendencies,
        apply_heating_rate,
        qneg,
        geopotential_temp,
        # Zhang-McFarlane deep convection
        zm_conv_options,
        zm_convr,
        zm_convr_tendency_diagnostics,
        save_ttend_from_convect_deep,
        apply_heating_rate,
        apply_constituent_tendencies,
        qneg,
        geopotential_temp,
        cloud_fraction_fice,
        set_deep_conv_fluxes_to_general,
        zm_conv_evap,
        set_general_conv_fluxes_to_deep,
        zm_evap_tendency_diagnostics,
        save_ttend_from_convect_deep,
        apply_heating_rate,
        apply_constituent_tendencies,
        qneg,
        geopotential_temp,
        cloud_fraction_fice,
        zm_conv_momtran,
        zm_momtran_tendency_diagnostics,
        save_ttend_from_convect_deep,
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
    ]
    physics_after_coupler = [
        sima_state_diagnostics,
        tropopause_find,
        tropopause_diagnostics,
        # Gravity wave drag
        gravity_wave_drag_common,
        check_energy_zero_fluxes,
        gravity_wave_drag_prepare_profiles,
        gravity_wave_drag_top_taper,
        gravity_wave_drag_moving_mountain,
        gravity_wave_drag_convection_deep,
        gravity_wave_drag_frontogenesis,
        gravity_wave_drag_ridge,
        gravity_wave_drag_ridge_beta,
        convert_dry_constituent_tendencies_to_dry_air_basis,
        apply_tendency_of_eastward_wind,
        apply_tendency_of_northward_wind,
        apply_constituent_tendencies,
        apply_heating_rate,
        qneg,
        geopotential_temp,
        update_dry_static_energy,
        check_energy_save_teout,
        thermo_water_update,
        check_energy_scaling,
        dycore_energy_consistency_adjust,
        apply_tendency_of_air_temperature,
        sima_tend_diagnostics,
    ]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    emit_ir(cam7)
