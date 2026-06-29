"""Python suite definition for the gw_cam7_se test suite.

Python equivalent of suite_gw_cam7_se.xml from
atmospheric_physics/test/test_suites/.  This is the CAM7 gravity wave drag
suite configured for the Spectral-Element dycore:
  - moving mountain GWD enabled (SE dycore only)
  - deep convective GWD enabled
  - frontogenesis GWD enabled
  - ridge-beta GWD enabled (requires topo file)
  - shallow convective / orographic GWD disabled

Run to emit MLIR IR (from the xdsl-ccpp root):
    python3 examples/atmospheric_physics/test/test_suites/suite_gw_cam7_se_py.py

Full pipeline (MLIR → Fortran):
    python3 examples/atmospheric_physics/test/test_suites/suite_gw_cam7_se_py.py | \\
        python3 -m xdsl_ccpp.tools.ccpp_opt \\
        -p generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap,generate-kinds,strip-ccpp \\
        -t ftn
"""

from xdsl_ccpp.frontend.py_api import ccpp_scheme_from_meta, ccpp_suite, emit_ir

_AP   = "../atmospheric_physics/schemes"
_TEST = "../atmospheric_physics/test/test_schemes"
_TEND = f"{_AP}/utilities/physics_tendency_updaters.meta"
_ENER = f"{_AP}/conservation_adjust/check_energy"
_GWD  = f"{_AP}/gravity_wave_drag"
_DIAG = f"{_AP}/sima_diagnostics"

# ---------------------------------------------------------------------------
# Schemes
# ---------------------------------------------------------------------------

initialize_constituents          = ccpp_scheme_from_meta(f"{_TEST}/initialize_constituents.meta")

gravity_wave_drag_common         = ccpp_scheme_from_meta(f"{_GWD}/gw_common.meta")
check_energy_zero_fluxes         = ccpp_scheme_from_meta(f"{_ENER}/check_energy_zero_fluxes.meta")
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
gravity_wave_drag_common_diagnostics = ccpp_scheme_from_meta(
    f"{_DIAG}/gravity_wave_drag_common_diagnostics.meta")

apply_tendency_of_eastward_wind  = ccpp_scheme_from_meta(_TEND, name="apply_tendency_of_eastward_wind")
apply_tendency_of_northward_wind = ccpp_scheme_from_meta(_TEND, name="apply_tendency_of_northward_wind")
apply_constituent_tendencies     = ccpp_scheme_from_meta(_TEND, name="apply_constituent_tendencies")
apply_heating_rate               = ccpp_scheme_from_meta(_TEND, name="apply_heating_rate")
qneg                             = ccpp_scheme_from_meta(f"{_AP}/utilities/qneg.meta")
geopotential_temp                = ccpp_scheme_from_meta(f"{_AP}/utilities/geopotential_temp.meta")
update_dry_static_energy         = ccpp_scheme_from_meta(f"{_AP}/utilities/static_energy.meta")

# ---------------------------------------------------------------------------
# Suite
# ---------------------------------------------------------------------------


@ccpp_suite("gw_cam7_se", version="1.0")
class gw_cam7_se:
    physics_after_coupler = [
        initialize_constituents,
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
        gravity_wave_drag_common_diagnostics,
        apply_tendency_of_eastward_wind,
        apply_tendency_of_northward_wind,
        apply_constituent_tendencies,
        apply_heating_rate,
        qneg,
        geopotential_temp,
        update_dry_static_energy,
    ]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    emit_ir(gw_cam7_se)
