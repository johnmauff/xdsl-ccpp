"""Python suite definition for the SIMA Kessler microphysics suite.

Python equivalent of suite_kessler.xml from ESCOMP/atmospheric_physics.
This is distinct from the standalone kessler example in examples/kessler/;
this suite wraps the same Kessler scheme in the full SIMA energy-conservation
and thermodynamics bookkeeping used by SIMA host models.

Run to emit MLIR IR (from the xdsl-ccpp root):
    python3 examples/atmospheric_physics/suite_kessler_py.py
"""

from xdsl_ccpp.frontend.py_api import ccpp_scheme_from_meta, ccpp_suite, emit_ir

_AP = "../atmospheric_physics/schemes"
_TEND = f"{_AP}/utilities/physics_tendency_updaters.meta"
_CONV = f"{_AP}/utilities/state_converters.meta"
_ENER = f"{_AP}/conservation_adjust/check_energy"
_DIAG = f"{_AP}/sima_diagnostics"

# ---------------------------------------------------------------------------
# Schemes
# ---------------------------------------------------------------------------

calc_exner                       = ccpp_scheme_from_meta(_CONV, name="calc_exner")
temp_to_potential_temp           = ccpp_scheme_from_meta(_CONV, name="temp_to_potential_temp")
calc_dry_air_ideal_gas_density   = ccpp_scheme_from_meta(_CONV, name="calc_dry_air_ideal_gas_density")
wet_to_dry_water_vapor           = ccpp_scheme_from_meta(_CONV, name="wet_to_dry_water_vapor")
wet_to_dry_cloud_liquid_water    = ccpp_scheme_from_meta(_CONV, name="wet_to_dry_cloud_liquid_water")
wet_to_dry_rain                  = ccpp_scheme_from_meta(_CONV, name="wet_to_dry_rain")
kessler                          = ccpp_scheme_from_meta(f"{_AP}/kessler/kessler.meta")
potential_temp_to_temp           = ccpp_scheme_from_meta(_CONV, name="potential_temp_to_temp")
dry_to_wet_water_vapor           = ccpp_scheme_from_meta(_CONV, name="dry_to_wet_water_vapor")
dry_to_wet_cloud_liquid_water    = ccpp_scheme_from_meta(_CONV, name="dry_to_wet_cloud_liquid_water")
dry_to_wet_rain                  = ccpp_scheme_from_meta(_CONV, name="dry_to_wet_rain")
kessler_update                   = ccpp_scheme_from_meta(f"{_AP}/kessler/kessler_update.meta")
qneg                             = ccpp_scheme_from_meta(f"{_AP}/utilities/qneg.meta")
geopotential_temp                = ccpp_scheme_from_meta(f"{_AP}/utilities/geopotential_temp.meta")
check_energy_zero_fluxes         = ccpp_scheme_from_meta(f"{_ENER}/check_energy_zero_fluxes.meta")
check_energy_scaling             = ccpp_scheme_from_meta(f"{_ENER}/check_energy_scaling.meta")
check_energy_chng                = ccpp_scheme_from_meta(f"{_ENER}/check_energy_chng.meta")
sima_state_diagnostics           = ccpp_scheme_from_meta(f"{_DIAG}/sima_state_diagnostics.meta")
kessler_diagnostics              = ccpp_scheme_from_meta(f"{_DIAG}/kessler_diagnostics.meta")
thermo_water_update              = ccpp_scheme_from_meta(f"{_AP}/thermo_water_update/thermo_water_update.meta")
dycore_energy_consistency_adjust = ccpp_scheme_from_meta(f"{_ENER}/dycore_energy_consistency_adjust.meta")
apply_tendency_of_air_temperature = ccpp_scheme_from_meta(_TEND, name="apply_tendency_of_air_temperature")
sima_tend_diagnostics            = ccpp_scheme_from_meta(f"{_DIAG}/sima_tend_diagnostics.meta")

# ---------------------------------------------------------------------------
# Suite
# ---------------------------------------------------------------------------


@ccpp_suite("kessler", version="1.0")
class kessler_suite:
    physics_before_coupler = [
        calc_exner,
        temp_to_potential_temp,
        calc_dry_air_ideal_gas_density,
        wet_to_dry_water_vapor,
        wet_to_dry_cloud_liquid_water,
        wet_to_dry_rain,
        kessler,
        potential_temp_to_temp,
        dry_to_wet_water_vapor,
        dry_to_wet_cloud_liquid_water,
        dry_to_wet_rain,
        kessler_update,
        qneg,
        geopotential_temp,
        check_energy_zero_fluxes,
        check_energy_scaling,
        check_energy_chng,
        sima_state_diagnostics,
        kessler_diagnostics,
    ]
    physics_after_coupler = [
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
    emit_ir(kessler_suite)
