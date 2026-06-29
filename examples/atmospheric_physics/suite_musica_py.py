"""Python suite definition for the MUSICA chemistry suite.

Python equivalent of suite_musica.xml from ESCOMP/atmospheric_physics.

Run to emit MLIR IR (from the xdsl-ccpp root):
    python3 examples/atmospheric_physics/suite_musica_py.py
"""

from xdsl_ccpp.frontend.py_api import ccpp_scheme_from_meta, ccpp_suite, emit_ir

_AP = "../atmospheric_physics/schemes"
_CONV = f"{_AP}/utilities/state_converters.meta"
_DIAG = f"{_AP}/sima_diagnostics"

# ---------------------------------------------------------------------------
# Schemes
# ---------------------------------------------------------------------------

calc_dry_air_ideal_gas_density = ccpp_scheme_from_meta(_CONV, name="calc_dry_air_ideal_gas_density")
musica_ccpp                    = ccpp_scheme_from_meta(f"{_AP}/musica/musica_ccpp.meta")
sima_state_diagnostics         = ccpp_scheme_from_meta(f"{_DIAG}/sima_state_diagnostics.meta")

# ---------------------------------------------------------------------------
# Suite
# ---------------------------------------------------------------------------


@ccpp_suite("musica", version="1.0")
class musica:
    physics_after_coupler = [
        calc_dry_air_ideal_gas_density,
        musica_ccpp,
        sima_state_diagnostics,
    ]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    emit_ir(musica)
