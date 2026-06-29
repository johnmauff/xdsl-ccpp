"""Python suite definition for the TJ2016 simplified physics suite.

Python equivalent of suite_tj2016.xml from ESCOMP/atmospheric_physics.

Run to emit MLIR IR (from the xdsl-ccpp root):
    python3 examples/atmospheric_physics/suite_tj2016_py.py
"""

from xdsl_ccpp.frontend.py_api import ccpp_scheme_from_meta, ccpp_suite, emit_ir

_AP = "../atmospheric_physics/schemes"
_TEND = f"{_AP}/utilities/physics_tendency_updaters.meta"
_ENER = f"{_AP}/conservation_adjust/check_energy"
_DIAG = f"{_AP}/sima_diagnostics"

# ---------------------------------------------------------------------------
# Schemes
# ---------------------------------------------------------------------------

tj2016_precip                    = ccpp_scheme_from_meta(f"{_AP}/tj2016/tj2016_precip.meta")
apply_heating_rate               = ccpp_scheme_from_meta(_TEND, name="apply_heating_rate")
qneg                             = ccpp_scheme_from_meta(f"{_AP}/utilities/qneg.meta")
check_energy_zero_fluxes         = ccpp_scheme_from_meta(f"{_ENER}/check_energy_zero_fluxes.meta")
check_energy_scaling             = ccpp_scheme_from_meta(f"{_ENER}/check_energy_scaling.meta")
check_energy_chng                = ccpp_scheme_from_meta(f"{_ENER}/check_energy_chng.meta")
sima_state_diagnostics           = ccpp_scheme_from_meta(f"{_DIAG}/sima_state_diagnostics.meta")
tj2016_sfc_pbl_hs                = ccpp_scheme_from_meta(f"{_AP}/tj2016/tj2016_sfc_pbl_hs.meta")
apply_tendency_of_eastward_wind  = ccpp_scheme_from_meta(_TEND, name="apply_tendency_of_eastward_wind")
apply_tendency_of_northward_wind = ccpp_scheme_from_meta(_TEND, name="apply_tendency_of_northward_wind")
thermo_water_update              = ccpp_scheme_from_meta(f"{_AP}/thermo_water_update/thermo_water_update.meta")
dycore_energy_consistency_adjust = ccpp_scheme_from_meta(f"{_ENER}/dycore_energy_consistency_adjust.meta")
apply_tendency_of_air_temperature = ccpp_scheme_from_meta(_TEND, name="apply_tendency_of_air_temperature")
sima_tend_diagnostics            = ccpp_scheme_from_meta(f"{_DIAG}/sima_tend_diagnostics.meta")

# ---------------------------------------------------------------------------
# Suite
# ---------------------------------------------------------------------------


@ccpp_suite("tj2016", version="1.0")
class tj2016:
    physics_before_coupler = [
        tj2016_precip,
        apply_heating_rate,
        qneg,
        check_energy_zero_fluxes,
        check_energy_scaling,
        check_energy_chng,
        sima_state_diagnostics,
    ]
    physics_after_coupler = [
        tj2016_sfc_pbl_hs,
        apply_heating_rate,
        apply_tendency_of_eastward_wind,
        apply_tendency_of_northward_wind,
        qneg,
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
    emit_ir(tj2016)
