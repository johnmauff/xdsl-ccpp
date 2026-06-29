"""Python suite definition for the rrtmgp test suite.

Python equivalent of suite_rrtmgp.xml from
atmospheric_physics/test/test_suites/.  The suite runs RRTMGP shortwave and
longwave radiation, each with a diagnostic subcycle.  The iteration count is
the CCPP standard name ``number_of_diagnostic_subcycles``, resolved at runtime
by the host model (last iteration is the climate calculation).

Run to emit MLIR IR (from the xdsl-ccpp root):
    python3 examples/atmospheric_physics/suite_rrtmgp_py.py

Full pipeline (MLIR → Fortran):
    python3 examples/atmospheric_physics/suite_rrtmgp_py.py | \\
        python3 -m xdsl_ccpp.tools.ccpp_opt \\
        -p generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap,generate-kinds,strip-ccpp \\
        -t ftn
"""

from xdsl_ccpp.frontend.py_api import forLoop, ccpp_scheme_from_meta, ccpp_suite, emit_ir

_AP    = "../atmospheric_physics/schemes"
_TEST  = "../atmospheric_physics/test/test_schemes"
_TEND  = f"{_AP}/utilities/physics_tendency_updaters.meta"
_RRTM  = f"{_AP}/rrtmgp"
_DIAG  = f"{_AP}/sima_diagnostics"

# ---------------------------------------------------------------------------
# Schemes
# ---------------------------------------------------------------------------

initialize_constituents          = ccpp_scheme_from_meta(f"{_TEST}/initialize_constituents.meta")

# Setup / pre-processing
rrtmgp_pre                       = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_pre.meta")
rrtmgp_cloud_optics_setup        = ccpp_scheme_from_meta(f"{_RRTM}/utils/rrtmgp_cloud_optics_setup.meta")
tropopause_find                  = ccpp_scheme_from_meta(f"{_AP}/tropopause_find/tropopause_find.meta")
rrtmgp_variables                 = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_variables.meta")
rrtmgp_inputs                    = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_inputs.meta")

# Shortwave pre-subcycle
rrtmgp_sw_cloud_optics           = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_sw_cloud_optics.meta")
rrtmgp_sw_mcica_subcol_gen       = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_sw_mcica_subcol_gen.meta")
rrtmgp_cloud_diagnostics         = ccpp_scheme_from_meta(f"{_DIAG}/rrtmgp_cloud_diagnostics.meta")

# Shortwave and longwave subcycle schemes
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

# Longwave pre-subcycle
rrtmgp_lw_cloud_optics           = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_lw_cloud_optics.meta")
rrtmgp_lw_mcica_subcol_gen       = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_lw_mcica_subcol_gen.meta")

# Longwave subcycle schemes
rrtmgp_lw_gas_optics_pre         = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_lw_gas_optics_pre.meta")
rrtmgp_lw_gas_optics             = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_lw_gas_optics.meta")
rrtmgp_lw_aerosols               = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_lw_aerosols.meta")
rrtmgp_lw_rte                    = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_lw_rte.meta")
rrtmgp_lw_calculate_fluxes       = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_lw_calculate_fluxes.meta")
rrtmgp_lw_calculate_heating_rate = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_lw_calculate_heating_rate.meta")
rrtmgp_lw_diagnostics            = ccpp_scheme_from_meta(f"{_DIAG}/rrtmgp_lw_diagnostics.meta")

# Post-radiation and state updaters
rrtmgp_inputs_setup              = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_inputs_setup.meta")
rrtmgp_sw_solar_var_setup        = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_sw_solar_var_setup.meta")
rrtmgp_dry_static_energy_tendency = ccpp_scheme_from_meta(f"{_RRTM}/utils/rrtmgp_dry_static_energy_tendency.meta")
calculate_net_heating            = ccpp_scheme_from_meta(f"{_RRTM}/utils/calculate_net_heating.meta")
rrtmgp_post                      = ccpp_scheme_from_meta(f"{_RRTM}/rrtmgp_post.meta")
rrtmgp_diagnostics               = ccpp_scheme_from_meta(f"{_DIAG}/rrtmgp_diagnostics.meta")
apply_heating_rate               = ccpp_scheme_from_meta(_TEND, name="apply_heating_rate")
geopotential_temp                = ccpp_scheme_from_meta(f"{_AP}/utilities/geopotential_temp.meta")

# ---------------------------------------------------------------------------
# Suite
# ---------------------------------------------------------------------------


@ccpp_suite("rrtmgp", version="1.0")
class rrtmgp:
    physics_after_coupler = [
        initialize_constituents,
        rrtmgp_pre,
        rrtmgp_cloud_optics_setup,
        tropopause_find,
        rrtmgp_variables,
        rrtmgp_inputs,
        # Shortwave pre-subcycle
        rrtmgp_sw_cloud_optics,
        rrtmgp_sw_mcica_subcol_gen,
        rrtmgp_cloud_diagnostics,
        # Shortwave subcycle (last iteration is climate calculation)
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
        # Longwave pre-subcycle
        rrtmgp_lw_cloud_optics,
        rrtmgp_lw_mcica_subcol_gen,
        # Longwave subcycle (last iteration is climate calculation)
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
        # Post-radiation (must follow both gas optics schemes)
        rrtmgp_inputs_setup,
        rrtmgp_sw_solar_var_setup,
        rrtmgp_dry_static_energy_tendency,
        calculate_net_heating,
        rrtmgp_post,
        rrtmgp_diagnostics,
        # State updaters
        apply_heating_rate,
        geopotential_temp,
    ]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    emit_ir(rrtmgp)
