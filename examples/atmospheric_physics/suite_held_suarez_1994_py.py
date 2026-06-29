"""Python suite definition for the Held-Suarez 1994 suite.

Python equivalent of suite_held_suarez_1994.xml from ESCOMP/atmospheric_physics.

Run to emit MLIR IR (from the xdsl-ccpp root):
    python3 examples/atmospheric_physics/suite_held_suarez_1994_py.py
"""

from xdsl_ccpp.frontend.py_api import ccpp_scheme_from_meta, ccpp_suite, emit_ir

_AP = "../atmospheric_physics/schemes"
_TEND = f"{_AP}/utilities/physics_tendency_updaters.meta"
_DIAG = f"{_AP}/sima_diagnostics"

# ---------------------------------------------------------------------------
# Schemes
# ---------------------------------------------------------------------------

held_suarez_1994              = ccpp_scheme_from_meta(f"{_AP}/held_suarez/held_suarez_1994.meta")
apply_tendency_of_eastward_wind  = ccpp_scheme_from_meta(_TEND, name="apply_tendency_of_eastward_wind")
apply_tendency_of_northward_wind = ccpp_scheme_from_meta(_TEND, name="apply_tendency_of_northward_wind")
apply_heating_rate            = ccpp_scheme_from_meta(_TEND, name="apply_heating_rate")
geopotential_temp             = ccpp_scheme_from_meta(f"{_AP}/utilities/geopotential_temp.meta")
sima_state_diagnostics        = ccpp_scheme_from_meta(f"{_DIAG}/sima_state_diagnostics.meta")
sima_tend_diagnostics         = ccpp_scheme_from_meta(f"{_DIAG}/sima_tend_diagnostics.meta")

# ---------------------------------------------------------------------------
# Suite
# ---------------------------------------------------------------------------


@ccpp_suite("held_suarez_1994", version="1.0")
class held_suarez_suite:
    physics_before_coupler = [
        held_suarez_1994,
        apply_tendency_of_eastward_wind,
        apply_tendency_of_northward_wind,
        apply_heating_rate,
        geopotential_temp,
        sima_state_diagnostics,
    ]
    physics_after_coupler = [
        sima_tend_diagnostics,
    ]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    emit_ir(held_suarez_suite)
