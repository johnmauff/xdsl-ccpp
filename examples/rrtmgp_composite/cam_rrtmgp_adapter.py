"""CAM-SIMA's host adapter for the RRTMGP package.

What this file is
-----------------
The CAM-specific half of radiation: the code that sits in front of and
behind the exchangeable RRTMGP package (rrtmgp_package.py).  It holds CAM
policy and science choices that do not belong inside RRTMGP:

- when shortwave and longwave run (``rrtmgp_pre``: radiation frequency);
- which CAM schemes fill the package's HOOKS (gas source, solar data,
  tropopause, aerosol optics, history diagnostics, radiation-call counter);
- carrying the radiative heating between radiation steps, net heating,
  coupler output, and freeing RRTMGP's objects (``rrtmgp_post``);
- CAM's time-split state update after radiation (apply heating, recompute
  geopotential).

How this reduces the complexity CCPP exposes
--------------------------------------------
Today these CAM pieces are interleaved line by line with RRTMGP's own
schemes in one flat suite file, so nothing marks which lines are "radiation"
and which are "CAM".  Here every CAM choice is in this one file, and every
hook binding is a named keyword argument -- ``diagnostics=rrtmgp_sw_diagnostics``
says what CAM plugs in and where.  Another model adopting RRTMGP writes its
own adapter like this one and leaves rrtmgp_package.py untouched.

A host may also override package SLOTS through ``cam_rrtmgp``; for example
``cam_rrtmgp(sw_slots={"overlap": other_sw_overlap})`` swaps the shortwave
overlap scheme without touching anything else.
"""

from xdsl_ccpp.frontend.py_api import ccpp_scheme_ref

from rrtmgp_package import rrtmgp_longwave, rrtmgp_prepare, rrtmgp_shortwave

# ---------------------------------------------------------------------------
# CAM schemes used before/after the package (adapter-owned steps).
# ---------------------------------------------------------------------------
rrtmgp_pre                        = ccpp_scheme_ref("rrtmgp_pre")
rrtmgp_dry_static_energy_tendency = ccpp_scheme_ref("rrtmgp_dry_static_energy_tendency")
calculate_net_heating             = ccpp_scheme_ref("calculate_net_heating")
rrtmgp_post                       = ccpp_scheme_ref("rrtmgp_post")
rrtmgp_diagnostics                = ccpp_scheme_ref("rrtmgp_diagnostics")
apply_heating_rate                = ccpp_scheme_ref("apply_heating_rate")
geopotential_temp                 = ccpp_scheme_ref("geopotential_temp")

# ---------------------------------------------------------------------------
# CAM schemes that fill the package's HOOKS.
# ---------------------------------------------------------------------------
tropopause_find          = ccpp_scheme_ref("tropopause_find")           # tropopause
rrtmgp_constituents      = ccpp_scheme_ref("rrtmgp_constituents")       # gas_source
solar_irradiance_data    = ccpp_scheme_ref("solar_irradiance_data")     # solar_source
aerosol_optics_zero_stub = ccpp_scheme_ref("aerosol_optics_zero_stub")  # aerosol_optics
rrtmgp_cloud_diagnostics = ccpp_scheme_ref("rrtmgp_cloud_diagnostics")  # cloud_diagnostics
rrtmgp_sw_diagnostics    = ccpp_scheme_ref("rrtmgp_sw_diagnostics")     # diagnostics (SW)
rrtmgp_lw_diagnostics    = ccpp_scheme_ref("rrtmgp_lw_diagnostics")     # diagnostics (LW)
rrtmgp_subcycle          = ccpp_scheme_ref("rrtmgp_subcycle")           # next_call

# HOOK value for n_calls: CAM's forcing-diagnostic radiation calls (one per
# gas set), a run-time count from CAM's namelist.
NDIAG = "number_of_diagnostic_subcycles"


def cam_rrtmgp(*,
               aerosol_optics=aerosol_optics_zero_stub,  # CAM's aerosol optics (CAM4: aerosol_optics)
               sw_slots=None,                            # optional SLOT overrides for shortwave
               lw_slots=None):                           # optional SLOT overrides for longwave
    """RRTMGP radiation as CAM-SIMA runs it."""
    rrtmgp_pre()                                  # CAM policy: when SW/LW run (dosw/dolw)
    rrtmgp_prepare(tropopause=tropopause_find)    # HOOK filled by CAM
    rrtmgp_shortwave(n_calls=NDIAG,                              # HOOK
                     next_call=rrtmgp_subcycle,                  # HOOK
                     gas_source=rrtmgp_constituents,             # HOOK
                     solar_source=solar_irradiance_data,         # HOOK
                     aerosol_optics=aerosol_optics,              # HOOK
                     cloud_diagnostics=rrtmgp_cloud_diagnostics, # HOOK
                     diagnostics=rrtmgp_sw_diagnostics,          # HOOK
                     **(sw_slots or {}))                         # SLOT overrides, if any
    rrtmgp_longwave(n_calls=NDIAG,                               # HOOK
                    next_call=rrtmgp_subcycle,                   # HOOK
                    gas_source=rrtmgp_constituents,              # HOOK
                    diagnostics=rrtmgp_lw_diagnostics,           # HOOK
                    **(lw_slots or {}))                          # SLOT overrides, if any
    rrtmgp_dry_static_energy_tendency()           # CAM: heating carried between radiation steps
    calculate_net_heating()                       # CAM: net radiative heating and fluxes
    rrtmgp_post()                                 # CAM: coupler output, free RRTMGP objects
    rrtmgp_diagnostics()                          # CAM: history output
    apply_heating_rate()                          # CAM: apply radiative heating to T (time-split update)
    geopotential_temp()
