"""RRTMGP radiation as an exchangeable package (a composite scheme).

What this file is
-----------------
The RRTMGP radiation package as another modelling group would receive it.
It names RRTMGP's own CCPP schemes (by name only -- no file paths; the
metadata is supplied to the generator separately, as for an XML suite) and
arranges them into a few entry points.  Everything host-specific is left to
a host adapter (see cam_rrtmgp_adapter.py for CAM-SIMA's).

Slots and hooks
---------------
Every entry point is a Python function whose keyword parameters are of two
kinds, marked SLOT or HOOK below:

  SLOT -- a science component that has a sensible default inside the
          package (RRTMGP's own scheme) but that a host may swap for an
          alternative, e.g. a different cloud-optics parameterization or
          subcolumn-overlap generator.  Slots are keyword parameters WITH a
          default value.  Leaving them alone gives standard RRTMGP.

  HOOK  -- a point where the package needs something only the host can
          provide: host diagnostics/history output, where gas
          concentrations and solar input come from, the tropopause, the
          aerosol optics the host uses, the radiation-call counter.  Hooks
          are keyword parameters WITHOUT a default: Python refuses the call
          if the host forgets one.

Shortwave and longwave are separate entry points because they are called
at scientifically different frequencies (``iradsw``/``iradlw``); deciding
when each runs is host policy, so it lives in the adapter, not here.

How this reduces the complexity CCPP exposes
--------------------------------------------
In CCPP today a suite file is a flat list: atmospheric_physics'
suite_rrtmgp.xml spells out 40 scheme entries (38 distinct schemes) and 2
loops, and a host that wants RRTMGP must copy that list -- including
RRTMGP's internal glue (gas-optics preparation, aerosol band translation,
flux scatter, object allocation) and the CAM-specific pieces woven in
between.  Every one of those schemes, and every one of the 264 standard
names their 789 metadata arguments use, sits in one suite-wide namespace.

With this package:

- A host calls 4 entry points (``rrtmgp_prepare``, ``rrtmgp_shortwave``,
  ``rrtmgp_longwave``, ``rrtmgp_init_only``) instead of listing 40 schemes.
  The order of RRTMGP's internal steps is written once, here, by the people
  who own RRTMGP, instead of being re-typed into every host's suite file.
- What a host must understand is the package's call interface: 8 hooks to
  fill in and 7 optional slots -- not RRTMGP's internal data flow.
- Swapping a science component is one keyword argument
  (``rrtmgp_shortwave(..., overlap=my_overlap_scheme)``) rather than
  editing the right line(s) of a long flat list.
- The boundary between "RRTMGP" and "CAM" becomes explicit: everything in
  this file is exchangeable; everything CAM-specific is a hook filled in by
  the adapter.

Entry points belong to one package
----------------------------------
``rrtmgp = ccpp_package("rrtmgp")`` declares the package, and each entry
point is decorated ``@rrtmgp.entry_point``.  The generator's IR records every
call as one named ``ccpp.composite`` block tagged with the package, so the
package boundary survives while the suite is recorded.  Inside it, the host
code run through a hook is recorded as a nested block marked ``hook``: it is
the host's code, not RRTMGP's.

Private names
-------------
The package boundary is shared by all four entry points (e.g. the
k-distribution objects are made at init and used by both shortwave and
longwave).  A standard name only RRTMGP's own code touches, and RRTMGP
writes, is private to the package: the generator renames it
``rrtmgp__<name>`` and keeps it in the suite cap, out of the host's reach
(``ccpp_dsl --list-package-scope`` lists them; 51 with CAM-SIMA's host
metadata).  Names the host's code also touches -- the objects the adapter's
rrtmgp_pre/rrtmgp_post allocate and free, the fluxes the diagnostics hooks
read -- stay public.  The ``flatten-composites`` pass then inlines the
package before the remaining code generation.
"""

from xdsl_ccpp.frontend.py_api import ccpp_package, ccpp_scheme_ref, forLoop

rrtmgp = ccpp_package("rrtmgp")

# ---------------------------------------------------------------------------
# Core schemes: fixed parts of RRTMGP, always used as-is.
# ---------------------------------------------------------------------------
variables          = ccpp_scheme_ref("rrtmgp_variables")
inputs             = ccpp_scheme_ref("rrtmgp_inputs")
inputs_setup       = ccpp_scheme_ref("rrtmgp_inputs_setup")
sw_solar_var_setup = ccpp_scheme_ref("rrtmgp_sw_solar_var_setup")
sw_gas_optics_pre  = ccpp_scheme_ref("rrtmgp_sw_gas_optics_pre")
sw_gas_optics      = ccpp_scheme_ref("rrtmgp_sw_gas_optics")
sw_solar_var       = ccpp_scheme_ref("rrtmgp_sw_solar_var")
sw_rte             = ccpp_scheme_ref("rrtmgp_sw_rte")
sw_fluxes          = ccpp_scheme_ref("rrtmgp_sw_calculate_fluxes")
sw_heating         = ccpp_scheme_ref("rrtmgp_sw_calculate_heating_rate")
lw_gas_optics_pre  = ccpp_scheme_ref("rrtmgp_lw_gas_optics_pre")
lw_gas_optics      = ccpp_scheme_ref("rrtmgp_lw_gas_optics")
lw_rte             = ccpp_scheme_ref("rrtmgp_lw_rte")
lw_fluxes          = ccpp_scheme_ref("rrtmgp_lw_calculate_fluxes")
lw_heating         = ccpp_scheme_ref("rrtmgp_lw_calculate_heating_rate")

# ---------------------------------------------------------------------------
# Slot defaults: RRTMGP's own implementations of the swappable components.
# ---------------------------------------------------------------------------
cloud_optics_setup = ccpp_scheme_ref("rrtmgp_cloud_optics_setup")   # cloud-optics tables
sw_cloud_optics    = ccpp_scheme_ref("rrtmgp_sw_cloud_optics")      # cloud optics (SW)
lw_cloud_optics    = ccpp_scheme_ref("rrtmgp_lw_cloud_optics")      # cloud optics (LW)
sw_mcica           = ccpp_scheme_ref("rrtmgp_sw_mcica_subcol_gen")  # overlap / McICA (SW)
lw_mcica           = ccpp_scheme_ref("rrtmgp_lw_mcica_subcol_gen")  # overlap / McICA (LW)
sw_aerosols        = ccpp_scheme_ref("rrtmgp_sw_aerosols")          # aerosol -> RRTMGP bands (SW)
lw_aerosols        = ccpp_scheme_ref("rrtmgp_lw_aerosols")          # aerosol -> RRTMGP bands (LW)


@rrtmgp.entry_point
def rrtmgp_prepare(*,
                   tropopause,                        # HOOK: host's tropopause diagnosis
                   optics_setup=cloud_optics_setup):  # SLOT: cloud-optics lookup tables
    """Set up cloud optics and build RRTMGP's grid and inputs."""
    optics_setup()
    tropopause()
    variables()
    inputs()


@rrtmgp.entry_point
def rrtmgp_shortwave(*,
                     n_calls,               # HOOK: how many radiation calls (host policy)
                     next_call,             # HOOK: advance the host's radiation-call counter
                     gas_source,            # HOOK: fill gas concentrations for this call
                     solar_source,          # HOOK: host's solar irradiance data
                     aerosol_optics,        # HOOK: host's aerosol optical properties
                     cloud_diagnostics,     # HOOK: host history output for cloud optics
                     diagnostics,           # HOOK: host history output for SW fluxes
                     clouds=sw_cloud_optics,   # SLOT: SW cloud optics
                     overlap=sw_mcica,         # SLOT: SW subcolumn overlap (McICA)
                     aerosols=sw_aerosols):    # SLOT: SW aerosol band translation
    """Shortwave radiation, repeated once per diagnostic call (gas set)."""
    clouds()
    overlap()
    cloud_diagnostics()
    aerosol_optics()
    with forLoop(n_calls):
        gas_source()
        sw_gas_optics_pre()
        sw_gas_optics()
        solar_source()
        sw_solar_var()
        aerosols()
        sw_rte()
        sw_fluxes()
        sw_heating()
        diagnostics()
        next_call()


@rrtmgp.entry_point
def rrtmgp_longwave(*,
                    n_calls,               # HOOK: how many radiation calls (host policy)
                    next_call,             # HOOK: advance the host's radiation-call counter
                    gas_source,            # HOOK: fill gas concentrations for this call
                    diagnostics,           # HOOK: host history output for LW fluxes
                    clouds=lw_cloud_optics,   # SLOT: LW cloud optics
                    overlap=lw_mcica,         # SLOT: LW subcolumn overlap (McICA)
                    aerosols=lw_aerosols):    # SLOT: LW aerosol band translation
    """Longwave radiation, repeated once per diagnostic call (gas set)."""
    clouds()
    overlap()
    with forLoop(n_calls):
        gas_source()
        lw_gas_optics_pre()
        lw_gas_optics()
        aerosols()
        lw_rte()
        lw_fluxes()
        lw_heating()
        diagnostics()
        next_call()


@rrtmgp.entry_point
def rrtmgp_init_only():
    """Schemes with only an init phase; inputs_setup must follow both gas optics."""
    inputs_setup()
    sw_solar_var_setup()
