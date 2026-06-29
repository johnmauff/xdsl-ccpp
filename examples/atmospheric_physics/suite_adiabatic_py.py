"""Python suite definition for the SIMA adiabatic suite.

This is the Python equivalent of suite_adiabatic.xml from ESCOMP/atmospheric_physics.
All scheme metadata is loaded from the original .meta files; only the suite
orchestration is written here.

Run to emit MLIR IR (from the xdsl-ccpp root):
    python3 examples/atmospheric_physics/suite_adiabatic_py.py

Full pipeline (MLIR → Fortran):
    python3 examples/atmospheric_physics/suite_adiabatic_py.py | \\
        python3 -m xdsl_ccpp.tools.ccpp_opt \\
        -p generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap,generate-kinds,strip-ccpp \\
        -t ftn
"""

from xdsl_ccpp.frontend.py_api import ccpp_scheme_from_meta, ccpp_suite, emit_ir

_AP = "../atmospheric_physics/schemes"
_TEND = f"{_AP}/utilities/physics_tendency_updaters.meta"
_ENER = f"{_AP}/conservation_adjust/check_energy"
_DIAG = f"{_AP}/sima_diagnostics"

# ---------------------------------------------------------------------------
# Schemes
# ---------------------------------------------------------------------------

check_energy_gmean        = ccpp_scheme_from_meta(f"{_ENER}/check_energy_gmean/check_energy_gmean.meta")
check_energy_gmean_diagnostics = ccpp_scheme_from_meta(f"{_DIAG}/check_energy_gmean_diagnostics.meta")
check_energy_zero_fluxes  = ccpp_scheme_from_meta(f"{_ENER}/check_energy_zero_fluxes.meta")
check_energy_fix          = ccpp_scheme_from_meta(f"{_ENER}/check_energy_fix.meta")
apply_heating_rate        = ccpp_scheme_from_meta(_TEND, name="apply_heating_rate")
geopotential_temp         = ccpp_scheme_from_meta(f"{_AP}/utilities/geopotential_temp.meta")
check_energy_scaling      = ccpp_scheme_from_meta(f"{_ENER}/check_energy_scaling.meta")
check_energy_chng         = ccpp_scheme_from_meta(f"{_ENER}/check_energy_chng.meta")
check_energy_fix_diagnostics = ccpp_scheme_from_meta(f"{_DIAG}/check_energy_fix_diagnostics.meta")
check_energy_save_teout   = ccpp_scheme_from_meta(f"{_ENER}/check_energy_save_teout.meta")
sima_state_diagnostics    = ccpp_scheme_from_meta(f"{_DIAG}/sima_state_diagnostics.meta")
sima_tend_diagnostics     = ccpp_scheme_from_meta(f"{_DIAG}/sima_tend_diagnostics.meta")

# ---------------------------------------------------------------------------
# Suite
# ---------------------------------------------------------------------------


@ccpp_suite("adiabatic", version="1.0")
class adiabatic:
    physics_before_coupler = [
        check_energy_gmean,
        check_energy_gmean_diagnostics,
        check_energy_zero_fluxes,
        check_energy_fix,
        apply_heating_rate,
        geopotential_temp,
        check_energy_scaling,
        check_energy_chng,
        check_energy_fix_diagnostics,
        check_energy_save_teout,
        sima_state_diagnostics,
    ]
    physics_after_coupler = [
        sima_tend_diagnostics,
    ]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    emit_ir(adiabatic)
