# Composite schemes: packages with slots and hooks

Backlog ID: `composite-scheme` (see `BACKLOG.md`). Status: proposal, not
started (logged 2026-10-19). Stage 1 is sized S-M (4-7 days); Stage 2 is
sized L (15-25 days, flatten-only lowering) to XL (25-50 days, with a real
package cap and CAM-SIMA integration).

This document is standalone design background in the same spirit as
`multilanguage_plan.md`: motivation, vocabulary, a worked example, and the
staged plan. The backlog carries only the sized items and a pointer here.

---

## 1. Motivation

### 1.1 The RRTMGP block of `suite_cam4.xml`

The radiation section of `atmospheric_physics`' `suites/suite_cam4.xml`
(about L245-301) has **40 scheme entries**; the whole suite has 222. Only 11
of the 40 do radiative transfer. Classified by role:

| Role | Entries | Code lines | `.meta` args |
|---|---|---|---|
| Radiative-transfer science (gas/cloud optics, McICA, solar variability, RTE, heating rates) | 11 | 1,895 | 219 |
| Glue: layout translation, object lifetime, control, setup, between-step carry-over | 19 (17 distinct) | 1,683 | 323 |
| Diagnostics (`sima_diagnostics/*`) | 5 | 691 | 135 |
| Neighbours (`aerosol_optics`, `tropopause_find`, `solar_irradiance_data`) and state update (`apply_heating_rate`, `geopotential_temp`) | 5 | — | — |

The glue is roughly the same amount of code as the science and carries
about 50% more interface. Glue also appears inside the science schemes
(day-column gathers and `ktopcam`/`ktoprad` offsets in McICA and cloud
optics), so the true share is higher.

### 1.2 Why the glue becomes schemes

Three independent causes:

1. **Data-passing granularity.** The only data path the framework sees is
   standard-named scheme arguments. Every computation between two library
   calls must therefore be a scheme, and every intermediate value needs a
   standard name and a `.meta` entry in each producer and consumer. Examples:
   gathering sunlit columns (`idxday`), the extra layer above the model top,
   reordering RRTMG→RRTMGP bands, MMR→VMR conversion, and allocating and
   freeing RRTMGP objects.
2. **No run-time control in the SDF.**
   - There is no loop index, so a scheme (`rrtmgp_subcycle`) keeps its own
     counter, and it appears twice.
   - There is no scope that controls a variable's lifetime, so
     `rrtmgp_pre`/`rrtmgp_post` exist to allocate and free objects.
   - capgen's suite-level `<init>` allows only one scheme, so init-only
     `*_setup` schemes sit in the run list just to get their `_init` called.
3. **CAM-SIMA conventions, which no language changes.** Diagnostics live in
   separate schemes, and a time-split state update (apply the tendency,
   recompute geopotential) follows each process.

Schemes also share data outside that path: run-phase schemes `use`
module tables filled by init-only setup schemes (`rrtmgp_cloud_optics_setup`,
`rrtmgp_sw_solar_var_setup`). Those dependencies are invisible to the
generator. It cannot order them, check them, or make them GPU-resident.

### 1.3 The exchange-unit argument

CCPP's original goal was exchanging physics between modelling groups. The
40-scheme decomposition does not serve that goal. Its internal interfaces
are not physical concepts that other groups could adopt piecemeal: RRTMGP
wrapper objects, `ktoprad`, `idxday`, `iteration_number_for_radiation_subcycle`.
Much of the glue is also CAM-specific (visible/near-IR albedo mapping, the
extra top layer at 1.01 Pa, coupler flux splits). The unit worth exchanging
is the **parameterization**: a package with a small public interface, whose
internals are still composed of schemes, and which exposes the
sub-components groups actually differ on as swappable slots.

---

## 2. Vocabulary

- **Generated cap**: the mechanical adapter between host and scheme code.
  It matches variables by standard name, converts units and kinds, slices
  arrays and moves GPU data. It is already produced by xdsl_ccpp.
- **Package (composite scheme)**: the exchangeable unit. From outside it
  looks like one scheme with a public interface. Inside, it is a mini-suite
  with private intermediate (interstitial) variables.
- **Slot**: a swappable science component inside a package (cloud optics,
  McICA/overlap, aerosol-optics translation). The package supplies a
  default, and the host may override it.
- **Hook**: host code the package calls at a defined point (diagnostics,
  gas-concentration source, solar input, tropopause, loop advance). It has
  no default, and the host must supply it.
- **Host adapter**: hand-written, host-owned code in front of and behind the
  package. It holds host *policy and science*: when radiation runs, carrying
  heating between radiation steps, coupler output, diagnostics. Each feature
  the generator gains moves more mechanical work into the generated cap; the
  remainder stays here.

---

## 3. Worked example (Stage 1 syntax)

**Implemented** in `examples/rrtmgp_composite/` (composite-scheme PR 3):
`rrtmgp_package.py`, `cam_rrtmgp_adapter.py` and
`suite_rrtmgp_composite_py.py`, commented to mark every SLOT and HOOK. They
use path-free `ccpp_scheme_ref` references and generate input identical to
atmospheric_physics' flat `suite_rrtmgp.xml`, checked in CI against a
metadata-only snapshot (`examples/rrtmgp_composite/meta/`). Compared with the
sketch below, the implementation adds an `rrtmgp_prepare` entry point, an
`aerosol_optics` hook (filled by `aerosol_optics_zero_stub` in that test
suite; CAM4's `aerosol_optics` in a full suite) and `initialize_constituents`
in the suite; the sketch is kept as design background.

The three files below flatten to exactly the scheme order of
`examples/atmospheric_physics/suite_rrtmgp_py.py`. SW and LW are **separate
package entry points**. They run at scientifically different frequencies
(`iradsw` and `iradlw` give independent `dosw`/`dolw` in `rrtmgp_pre`), so
when each runs is host policy, not something to hide inside the package.

### 3.1 `rrtmgp_package.py` (owned by atmospheric_physics)

```python
"""RRTMGP radiation package -- the exchangeable unit."""
from xdsl_ccpp.frontend.py_api import ccpp_scheme_from_meta, forLoop

_R = "../atmospheric_physics/schemes/rrtmgp"
def _s(name, sub=""):
    return ccpp_scheme_from_meta(f"{_R}/{sub}{name}.meta")

# --- core: fixed parts of the package ---------------------------------
variables          = _s("rrtmgp_variables")
inputs             = _s("rrtmgp_inputs")
inputs_setup       = _s("rrtmgp_inputs_setup")
sw_solar_var_setup = _s("rrtmgp_sw_solar_var_setup")
sw_gas_optics_pre  = _s("rrtmgp_sw_gas_optics_pre")
sw_gas_optics      = _s("rrtmgp_sw_gas_optics")
sw_solar_var       = _s("rrtmgp_sw_solar_var")
sw_rte             = _s("rrtmgp_sw_rte")
sw_fluxes          = _s("rrtmgp_sw_calculate_fluxes")
sw_heating         = _s("rrtmgp_sw_calculate_heating_rate")
lw_gas_optics_pre  = _s("rrtmgp_lw_gas_optics_pre")
lw_gas_optics      = _s("rrtmgp_lw_gas_optics")
lw_rte             = _s("rrtmgp_lw_rte")
lw_fluxes          = _s("rrtmgp_lw_calculate_fluxes")
lw_heating         = _s("rrtmgp_lw_calculate_heating_rate")

# --- default implementations for the slots ----------------------------
cloud_optics_setup = _s("rrtmgp_cloud_optics_setup", "utils/")
sw_cloud_optics    = _s("rrtmgp_sw_cloud_optics")
lw_cloud_optics    = _s("rrtmgp_lw_cloud_optics")
sw_mcica           = _s("rrtmgp_sw_mcica_subcol_gen")
lw_mcica           = _s("rrtmgp_lw_mcica_subcol_gen")
sw_aerosols        = _s("rrtmgp_sw_aerosols")
lw_aerosols        = _s("rrtmgp_lw_aerosols")


def rrtmgp_prepare(*, tropopause, optics_setup=cloud_optics_setup):
    optics_setup()               # slot
    tropopause()                 # hook
    variables()
    inputs()


def rrtmgp_shortwave(*, n_calls, next_call, gas_source, solar_source,
                     cloud_diagnostics, diagnostics,
                     clouds=sw_cloud_optics, overlap=sw_mcica,
                     aerosols=sw_aerosols):
    clouds()                     # slot
    overlap()                    # slot
    cloud_diagnostics()          # hook
    with forLoop(n_calls):       # diagnostic calls (gas sets)
        gas_source()             # hook
        sw_gas_optics_pre()
        sw_gas_optics()
        solar_source()           # hook
        sw_solar_var()
        aerosols()               # slot
        sw_rte()
        sw_fluxes()
        sw_heating()
        diagnostics()            # hook
        next_call()              # hook


def rrtmgp_longwave(*, n_calls, next_call, gas_source, diagnostics,
                    clouds=lw_cloud_optics, overlap=lw_mcica,
                    aerosols=lw_aerosols):
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


def rrtmgp_init_only():
    # Init-phase-only schemes. Kept at their current SDF position so the
    # Stage 1 output stays byte-identical; Stage 2 moves them to package init.
    inputs_setup()
    sw_solar_var_setup()
```

### 3.2 `cam_radiation_adapter.py` (owned by CAM-SIMA)

```python
"""CAM-SIMA host adapter for RRTMGP: policy, coupler and diagnostics."""
from rrtmgp_package import (rrtmgp_prepare, rrtmgp_shortwave,
                            rrtmgp_longwave, rrtmgp_init_only)
from cam_schemes import (rrtmgp_pre, rrtmgp_constituents, solar_irradiance_data,
                         tropopause_find, rrtmgp_cloud_diagnostics,
                         rrtmgp_sw_diagnostics, rrtmgp_lw_diagnostics,
                         rrtmgp_subcycle, rrtmgp_dry_static_energy_tendency,
                         calculate_net_heating, rrtmgp_post, rrtmgp_diagnostics,
                         apply_heating_rate, geopotential_temp)

NDIAG = "number_of_diagnostic_subcycles"   # CAM's forcing-diagnostic calls

def cam_rrtmgp(*, sw_slots=None, lw_slots=None):
    rrtmgp_pre()                           # SW/LW frequency policy (dosw/dolw)
    rrtmgp_prepare(tropopause=tropopause_find)
    rrtmgp_shortwave(n_calls=NDIAG, next_call=rrtmgp_subcycle,
                     gas_source=rrtmgp_constituents,
                     solar_source=solar_irradiance_data,
                     cloud_diagnostics=rrtmgp_cloud_diagnostics,
                     diagnostics=rrtmgp_sw_diagnostics, **(sw_slots or {}))
    rrtmgp_longwave(n_calls=NDIAG, next_call=rrtmgp_subcycle,
                    gas_source=rrtmgp_constituents,
                    diagnostics=rrtmgp_lw_diagnostics, **(lw_slots or {}))
    rrtmgp_init_only()
    rrtmgp_dry_static_energy_tendency()    # qrs carry-over between radiation steps
    calculate_net_heating()
    rrtmgp_post()
    rrtmgp_diagnostics()
    apply_heating_rate()                   # CAM time-split update: apply radiative heating to T
    geopotential_temp()
```

### 3.3 Suite file

```python
@ccpp_suite("rrtmgp", version="1.0")
class rrtmgp:
    def physics_after_coupler():
        initialize_constituents()
        cam_rrtmgp()

@ccpp_suite("rrtmgp_alt_overlap", version="1.0")    # swapping one slot
class rrtmgp_alt_overlap:
    def physics_after_coupler():
        initialize_constituents()
        cam_rrtmgp(sw_slots={"overlap": exp_random_sw},
                   lw_slots={"overlap": exp_random_lw})
```

In Stage 1, frequency gating still happens inside each scheme
(`if (.not. dosw) return`). Separate entry points make it possible to gate
whole SW/LW calls in the adapter once a run-time conditional construct exists
(Stage 2, item 2i).

---

## 4. Findings from writing the example

1. **Hooks are needed as well as slots.** Eight hooks exist only because
   host work is currently interleaved inside the radiation sequence:
   diagnostics inside the loops, the per-iteration constituent copy, the
   solar data read, `tropopause_find`, and the loop counter. The hook list
   is the package's call-level public interface, alongside its data-level
   interface.
2. **Four schemes mix package and host concerns**: `rrtmgp_pre`,
   `rrtmgp_post`, `rrtmgp_inputs` and `*_calculate_fluxes` (detail in §7).
   Notably, `shortwave_net_radiative_flux` is produced by the scatter in
   `rrtmgp_sw_calculate_fluxes` (which also does CAM coupler work) and
   consumed by the package's own `rrtmgp_sw_calculate_heating_rate`.
3. **The SW and LW loops stay separate.** From the metadata, they share only
   the loop counter and the constituent copy, so they *could* be fused. They
   are kept separate deliberately: SW and LW run at scientifically different
   frequencies, and separate entry points let the host own that policy.
4. **A latent column-block bug exists in the RRTMGP schemes.**
   `rrtmgp_sw_gas_optics`, `rrtmgp_sw_rte` and `rrtmgp_lw_gas_optics` compute
   `iCol = (iter_num-1)*rrtmgp_phys_blksz + 1`. `iter_num` is bound to
   `iteration_number_for_radiation_subcycle` (the diagnostic-call index),
   while `rrtmgp_phys_blksz` is all columns. On diagnostic call 2 the column
   range is empty. The bug is latent today because `ndiags` defaults to 1
   and only `rad_climate` exists. The generated cap confirms the binding
   (`rrtmgp_sw_gas_optics_run(..., iter_num=diag_cur, ncol=nday, ...)`).
5. **Stage 1 shrinks the authoring, not the run-time calls.** About 115
   lines of structured Python replace a flat 60-entry list. Generated
   Fortran is identical; the gains are structure, reuse and swappable slots.

---

## 5. Stage 1 — Python composition frontend (S-M, ~4-7 days)

Frontend only, flattening at IR-generation time. No changes to the
generator's transformation passes; generated Fortran is unchanged.

| Step | Work | File(s) |
|---|---|---|
| 1a | **Recording context.** `SchemeDescriptor.__call__(**overrides)` appends to the active recorder, reusing `_run_groups`' `_add`/override semantics. Calling outside a recorder raises a clear error. Enables ordinary Python functions (packages, adapters) that call schemes. | `xdsl_ccpp/frontend/py_api.py` (`_run_groups`, ~L408-494) |
| 1b | **Group functions.** In `ccpp_suite`, non-private plain functions other than `run` become groups named after the function. List-attribute groups and `run()` keep working. | `py_api.py` (`ccpp_suite`, ~L497-560) |
| 1c | **`with forLoop("std_name"):`** context-manager form that records a `SubcycleDescriptor`; lowering reuses `_group_item_to_op` unchanged. Keeps the existing `range("std_name")` error. | `py_api.py` |
| 1d | **Slots and hooks**: keyword defaults and required keyword-only arguments. Pure Python, no framework code. Documented in the `py_api` module docstring. | `py_api.py` docstring |
| 1e | **Example**: §3's three files. | `examples/atmospheric_physics/suite_rrtmgp_composite_py.py` (+ package and adapter modules) |
| 1f | **Tests**: calling a descriptor outside a recorder errors; group functions; nested helper composition; `with forLoop`; a slot override changes the recorded scheme. Self-contained on helloworld/kessler metas. | `tests/unit/test_py_api_composition.py` |

**Exit criterion:** the composite example's IR (and generated Fortran) is
byte-identical to `suite_rrtmgp_py.py`'s; existing Python examples are
unchanged. The atmospheric_physics example needs the sibling
`atmospheric_physics` checkout, as the existing `suite_*_py.py` examples
already do.

**Relation to `dup-suite-composition-dsl`:** Stage 1 supplies that item's
mechanism. `dry_basis`/`theta_basis` become ordinary `with`-combinators, so
the residual work there should shrink once Stage 1 lands.

---

## 6. Stage 2 — encapsulation (L to XL)

Turns the flattened composition into real packages: private names, a declared
interface, and optionally a separately generated package cap.

| Step | Work | Size |
|---|---|---|
| 2a | **IR**: a `ccpp.composite` op (region of schemes, subcycles and nested composites, plus slot/hook bindings) in `xdsl_ccpp/dialects/ccpp.py`. `@ccpp_composite` in `py_api` records into it instead of flattening. | S |
| 2b | **Public interface**: either a declared table (`type = composite`) or inferred (internal inputs not produced internally, plus declared exports). A validation pass checks that every internal argument resolves to the interface or a private variable. With source-derived metadata (`dup-meta-shadow-elim`/`direct-fortran-ingest`), inference avoids yet another hand-maintained shadow file. The interface also includes a **package-level init** sequence: init-only schemes (RRTMGP's `rrtmgp_inputs_setup`, which must follow both gas-optics inits, and `rrtmgp_sw_solar_var_setup`) are declared there instead of being placed in a run sequence only to order their `_init` calls -- removing the Stage 1 workaround `rrtmgp_init_only()`. | M |
| 2c | **Scoped name resolution**, package → suite → host, through `host_var_match_pass.py`, `generate-arg-ownership` (a new private ownership kind), interstitial promotion in `suite_cap.py`, `run_dispatch.py`, and constituents. | M-L |
| 2d | **Hook scoping rule**: hooks resolve in host scope plus the composite's exported interface only. | S-M |
| 2e | **Lowering A — flatten with name mangling** into the existing suite-cap path. Output equals Stage 1's apart from private names. | S-M |
| 2f | **Lowering B — per-composite package cap**: its own phase entry points, package-owned persistent state (k-distribution, lookup tables, today's module-variable side channels), instances via the existing `ccpp_t` support. **Open decision:** hooks inside a separately generated cap need procedure arguments, or must be eliminated by the upstream scheme splits (§7). | L |
| 2g | **GPU residency across the boundary** (`gpu_ccpp_cap_pass.py`, `gpu_data_pass.py`). Package-private data could stay device-resident for the package's lifetime. Highest-risk area, given the history of multi-group residency bugs. | M |
| 2h | **CAM-SIMA integration**: `--py` support in `cime_config/cam_autogen.py`; private ownership excluded from `resolved_vars.json` and `src/data/resolved_var_xdsl_ccpp.py` (which already drops `suite_owned`); FPHYStest rrtmgp. | M |
| 2i | **Run-time conditional construct** (e.g. `with when("do_shortwave_radiation"):`), so the adapter can gate whole SW/LW entry points and schemes drop their `if (.not. dosw) return` boilerplate. | S |

**Totals:** 2a-2e + 2i give real encapsulation with unchanged generated
Fortran, about **L (15-25 days)**. Adding 2f-2h gives an exchangeable
compiled package integrated in CAM-SIMA, about **XL (25-50 days)**.

**Not sizable:** agreeing a public radiation interface across modelling
groups (standard names, units, required vs host-specific outputs). This is
governance, like the fixture-storage decision in `scheme-io-capture`.

---

## 7. Upstream prerequisites (atmospheric_physics, not xdsl tooling)

These change atmospheric_physics schemes, so they go upstream as ESCOMP PRs,
separately from xdsl-ccpp work. Stage 1 does not need them (hooks absorb the
interleaving). They make Stage 2's boundary clean and reduce the hook count.

**Rule for every split:** anything that needs RRTMGP internals (band layout,
the k-distribution temperature range, the RRTMGP objects) goes into the
package; anything that is host policy or a host data format goes into the
host adapter; ambiguous items become interface decisions.

| Scheme | Package part | Host-adapter part |
|---|---|---|
| `rrtmgp_pre` (worked out in §11.6) | Allocating the flux objects (move next to the optics-object allocation in `rrtmgp_inputs`) | `radiation_do` for SW/LW, `dosw_heat`/`dolw_heat`, `nextsw_cday` for the coupler |
| `rrtmgp_post` | Freeing all optics, source and flux objects | `qrs`/`qrl` carry-over (`*pdel`), `netsw` and `flwds` to the coupler |
| `rrtmgp_inputs` | Radiation grid and extra top layer, T clamp to the k-distribution range, day gather, object init, albedo band mapping (the interface takes visible/near-IR albedos) | t_sfc from LW-up, emissivity, which cloud fraction radiation sees (snow/graupel) |
| `*_calculate_fluxes` | Scatter back to the model grid (consumed by the package's heating-rate schemes) | `fsns/fsnt/flns/flnt`; the coupler `soll/sols/solld/solsd` |

Better still, the package should export visible/near-IR direct and diffuse
surface fluxes computed from its own band boundaries. That removes the
hard-coded band indices (1-9, half of 10, 11-14) from host code.

In flat form, splitting raises the scheme count slightly (4 → about 8), but
hooks drop and the boundary becomes clean.

**Sequencing:**
1. `iter_num` fix (XS): drop `iter_num`/`rrtmgp_phys_blksz` from
   `rrtmgp_sw_gas_optics`, `rrtmgp_sw_rte` and `rrtmgp_lw_gas_optics`.
   CAM-SIMA does not block columns; this is a leftover from the UFS original.
2. The scheme splits (S-M), coordinated with the Stage 2 interface design.

Verify each step with FPHYStest rrtmgp and QPC4 bit-for-bit.

**Not pursued:** fusing the SW and LW diagnostic loops. It is legal by the
metadata, but SW and LW run at different frequencies, and keeping separate
entry points lets the host own that policy (decision 2026-10-19).

---

## 8. Relation to existing backlog items

- `dup-suite-composition-dsl` — Stage 1 supplies its composition mechanism.
- `dup-meta-shadow-elim` / `direct-fortran-ingest` — metadata derived from
  `!$ccpp`-tagged Fortran is produced ahead of generation, so it is
  frontend-agnostic: Python suites load generated `.meta` through
  `ccpp_scheme_from_meta` unchanged (only exercised with XML suites so far).
  The RRTMGP sources are not tagged yet (corpus Stage 2 not started). A small
  `ccpp_scheme_from_source()` helper in `py_api` would be a slice of
  `direct-fortran-ingest`. Stage 2's inferred interface (2b) builds on the
  same idea.
- `suite-state-full-match` and the `ccpp_t` multi-instance support — relevant
  to package-owned persistent state in 2f.

---

## 9. Suite-wide impact: CAM4 (analysis 2026-10-19)

`suite_cam4.xml` has 222 `<scheme>` entries and 147 distinct schemes. Four
of the schemes are commented out: `dme_adjust`, `thermo_water_update`,
`turbulent_mountain_stress_add_drag_coefficient` and
`beljaars_add_wind_damping_rate`. The **active** suite therefore has **218
entries and 143 distinct schemes**.

### 9.1 Three different counts

Composition barely changes the number of Fortran schemes. What it changes is
how many are *public*: visible at the top level, written out by suite
authors, and sharing one global namespace.

| Count | Today | With packages |
|---|---|---|
| Top-level entries in the CAM4 suite | 218 | ~15-20 |
| Public building blocks (composed or exchanged) | 143 | ~12-15 packages + 1 shared update combinator |
| Distinct Fortran schemes | 143 | ~135 (Stage 1/2 language features); ~120-125 (plus suite-wide glue reduction); ~100 (plus declarative diagnostics) |

### 9.2 Top-level suite sketch

```python
@ccpp_suite("cam4")
class cam4:
    def physics_before_coupler():
        cam_prescribed_inputs()        # ozone, aerosols, volcanic, seasalt rebin, gases  (~8)
        global_energy_fixer()          # gmean, fix, diagnostics                       (~4)
        dry_adiabatic_adjustment()     # dadadj                                        (1)
        zm_deep_convection()           # convr, evap, momtran, convtran, diags          (~14)
        hack_shallow_convection()      # hack, evap, sum-to-deep, diags                 (~10)
        rk_stratiform()                # sedimentation ... optical properties           (~23)
        cam_rrtmgp(aerosol_optics=prescribed_aerosol_optics)                          # (~40)
        cam_surface_export()           # tropopause, state diags, coupling vars         (~5)

    def physics_after_coupler():
        vertical_diffusion(pbl=holtslag_boville)                                       # (~27)
        gravity_wave_drag(sources=[orographic])                                        # (~7)
        energy_closure()               # save_teout, dycore consistency, tend diags     (~5)
```

Parenthesised numbers are the distinct schemes each package absorbs. The cam5
and cam7 suites contain the same ZM, RRTMGP, gravity-wave and
vertical-diffusion blocks. Shared packages remove the drift risk that
`dup-suite-composition-dsl` was concerned about.

### 9.3 The largest reduction: the process-update combinator

**76 of the 218 active entries (35%)** are process-update bookkeeping, made
up of just 11 distinct schemes:
- `apply_heating_rate`, `apply_constituent_tendencies`,
  `apply_tendency_of_{eastward,northward}_wind` and
  `apply_tendency_of_air_temperature`;
- `qneg`, `geopotential_temp` and `update_dry_static_energy`;
- the `check_energy_zero_fluxes`/`check_energy_scaling`/`check_energy_chng`
  bracket around each process.

This is CAM's former `physics_update`, unrolled 12-15 times in the suite. One
reusable Stage 1 combinator covers it:

```python
with energy_checked():
    zm_convr()
    apply_updates(heat=True, q=True)      # -> apply_*, qneg, geopotential_temp
```

### 9.4 What actually removes Fortran schemes

Composition alone moves schemes inside packages; deletions come from
language features:

| Feature | Schemes removed |
|---|---|
| Call-site argument binding: bind a scheme argument to a different standard name (extends today's constant-only kwarg overrides) | 4 renaming interstitials: `set_deep_conv_fluxes_to_general`, `set_general_conv_fluxes_to_deep`, `set_shallow_conv_fluxes_to_general`, `set_general_conv_fluxes_to_shallow` (exist only so `zm_conv_evap` can serve deep and shallow convection) |
| Slots with empty defaults | 2 stubs: `tms_beljaars_zero_stub`, `zero_upper_boundary_condition` |
| Package-level init | 0 deleted; the 4 `*_options` init-only schemes (`zm_conv_options`, `cloud_fraction_options`, `holtslag_boville_diff_options`, `vertical_diffusion_options`) leave the run lists |
| Loop index, scoped lifetime, layout transforms (RRTMGP-style glue reduction) | ~5-8 in RRTMGP; vertical diffusion has a similar pre/post-interstitial pattern (~8), not yet measured |
| Declarative diagnostics: history output driven by metadata (separate feature, outside Stage 1/2) | most of the 30 `*_diagnostics` schemes |

Call-site argument binding is not yet itemised in §6. It fits naturally next
to 2c (scoped resolution), or as a small Stage 1 extension, since overrides
already exist for constants.

### 9.5 Standard-name impact

**Method:**
1. Parse the `.meta` files of all 143 active schemes, collecting standard
   names across all phases.
2. Classify each name using the `resolved_vars.json` of a real CAM4 build
   (`SMS_D_Ln9.mpasa120_mpasa120.QPC4...cam4.xdsl45g`, 2026-09-30).
3. Assign each scheme to a §9.2 package by its position in the suite.

A name is **package-private** if every scheme that uses it is in a single
package.

**The 708 standard names used by active CAM4 schemes today:**

| Kind | Count | Affected by packages? |
|---|---|---|
| Host-provided (registry, host `.meta`) | 345 | No — they remain the host interface |
| Interstitial (scheme-to-scheme, suite-owned) | 337 | **Yes** |
| Framework (`ccpp_error_*`, horizontal/vertical dimensions, constituent arrays) | 23 | No |
| Constituents | 3 | No |

**How many interstitials become package-private:**

| Step | Private to one package |
|---|---|
| Packages as in §9.2, with the RRTMGP adapter and package counted separately | 227 |
| Counting the RRTMGP adapter + package as one radiation unit | 277 |
| A tropopause package: of `tropopause_find`'s 25 outputs only ~5 are read elsewhere (`prescribed_volcanic_aerosol`, `prognostic_cloud_water`, RRTMGP diagnostics); the rest feed only `tropopause_diagnostics` | +~20 |
| Names recomputed in each package (`cloud_fraction_fice` outputs, `tendency_of_{eastward,northward}_wind`) | +4 |
| Call-site argument binding, which removes the ZM/Hack "general convection" renaming (§9.4) | +~9 |
| **Total** | **~310 of 337 (~92%)** |

About 25-30 interstitials remain genuinely public (cross-package):
- energy-budget bookkeeping shared by every process (10: cumulative
  boundary fluxes, start-of-timestep T/z, imbalance counts);
- precipitation passed to surface export (9);
- the main tropopause outputs (~5);
- the deep-convection top and launch indices used by Hack (2);
- `relative_humidity` (stratiform → radiation) and `scheme_name`.

**Net result:** the global standard-name namespace shrinks from 708 to about
400 (345 host + 23 framework + 3 constituents + ~30 public interstitials).
About 310 names (~44% of all names) leave the global namespace.

**Notes:**
- **The RRTMGP adapter/package split is the noisiest part.** 50 names cross
  it today. Most are RRTMGP objects, flags and band indices that cross only
  because of the four mixed schemes (§7). The upstream splits make them
  private to one side.
- **"Leave the global namespace" is not the same as "deleted".** Inside a
  package these values may keep standard names for documentation or use
  local names. Glue reduction would delete some outright (e.g. the
  `*_object_for_rrtmgp` names).
- **Possible further reduction among host names.** 234 of the 345 are used
  by only one package. Some are likely registry variables that exist mainly
  to hold a scheme's own state between timesteps. With Stage 2's package-cap
  lowering (2f) they could become package-owned and leave the registry. Not
  yet quantified; it needs a pass over `registry.xml`.
- **Caveats.** The numbers depend on the §9.2 package boundaries and on a
  2026-09-30 build; the current atmospheric_physics submodule may differ
  slightly.

### 9.6 Framing

The core problem is not that CAM4 has 143 Fortran units. It is that all 143
are public, share one global namespace, and are written out flat in every
suite that uses them. With packages:
- **suite authors write** ~15-20 entries instead of 218;
- **other groups exchange** about a dozen packages with slots;
- **the Fortran units** become package internals.

Stage 1 delivers the first point, with identical generated Fortran. Stage 2's
encapsulation makes the second point real, by taking each package's standard
names out of the global namespace.

---

## 10. PR breakdown

Group sub-steps into PRs that are independently useful, reviewable in one
sitting, and leave `main` green. That avoids both one PR per sub-step and
one PR per stage (Stage 2 is 15-50 days). The precedent is
`dup-meta-shadow-elim` (4 PRs for 7 phases, #136-#140) and
`scheme-io-capture` (3 PRs, #141-#143).

**Rules for PR boundaries:**
1. **No existing output changes.** Every PR leaves generated Fortran
   byte-identical for all existing XML and Python examples. This is the
   regression bar that makes each PR safe to merge.
2. **End a PR before each design decision.** Merge, look at the result, then
   decide with real code in hand.
3. **High-risk areas get their own PR** — GPU residency especially, since it
   needs real nvhpc verification.

### Stage 1 — 2 PRs

| PR | Contents | Why it is separate |
|---|---|---|
| 1 | 1a recording context, 1b group functions, 1c `with forLoop`, 1d docs, 1f unit tests | Pure `py_api` mechanics; backward-compatible; tested in isolation |
| 2 | 1e RRTMGP composite example, plus the IR byte-identity check against `suite_rrtmgp_py.py` | Depends on the atmospheric_physics checkout; reviewed as a design showcase (package boundaries); may iterate |

Checkpoint after PR 2: reassess the design before starting Stage 2.
(Held 2026-10-19, after Stage 1 took 3 PRs; see §11, which supersedes the
Stage 2 rows below.)

### Stage 2 — about 6-7 PRs

| PR | Contents | Notes |
|---|---|---|
| 3 | 2a composite op + 2e flatten lowering | Output identical to Stage 1: a pure refactor into new IR |
| 4 | 2c scoped resolution + 2d hook scoping rule + name mangling | The core and the largest; split host-match scoping from interstitial/promotion scoping if the diff grows |
| 5 | 2b public interface (declared or inferred) + validation | Coordinate with the upstream scheme splits (§7) |
| 6 | 2i run-time conditional | Independent; can land at any time, even alongside Stage 1 |
| 7 | 2g GPU residency across the composite boundary | Isolated because of the risk; requires a real GPU run |
| 8 | 2f package cap; possibly 2 PRs (the cap itself, then persistent state and instances) | Merge PR 4 first, so the "hooks inside a package cap" decision is made with scoping in place |
| — | 2h CAM-SIMA integration | Lands in the CAM-SIMA repo, not xdsl-ccpp |

### Upstream atmospheric_physics (separate repo, own schedule)

- **`iter_num` fix:** tiny, independent, a real latent bug — can be sent now
  rather than waiting for this plan.
- **The four scheme splits (§7):** later, coordinated with Stage 2's
  interface work (PR 5).

**Total:** about 2 PRs for Stage 1 and 6-8 for Stage 2. Each is comparable in
size to recent PRs (#136-#146), and each has a clear "nothing existing
changed" check.

---

## 11. Stage 1 retrospective and Stage 2 reassessment (2026-10-19)

The checkpoint planned in §10, held after Stage 1 merged (PRs #148, #149 and
the RRTMGP example PR). Where this section and §6/§10 differ, this section
wins.

### 11.1 What Stage 1 delivered and taught

**Delivered:**
- Python composition: callable schemes, group functions, `with forLoop`,
  slots and hooks.
- Path-free `ccpp_scheme_ref` references and `export_suite`.
- CMake `PY_SUITE` support.
- Three composite examples: helloworld and advection (compiled, run in CI)
  and RRTMGP (checked at the generator's input against atmospheric_physics'
  `suite_rrtmgp.xml`).

**Lessons that shape Stage 2:**
1. **Real packages need a real host to validate.** The RRTMGP example can
   only be checked up to the generator's input: full cap generation needs
   CAM-SIMA's host metadata. Stage 2 changes generated code, so it needs a
   compiled, numerically checked vehicle.
2. **There is a concrete case for scoped names.** RRTMGP's SW and LW
   gas-optics schemes both use the local name `kdist` for different standard
   names. Host matching hides this inside CAM-SIMA; without a host, it blocks
   suite-cap generation. Package scoping (2c/2e) should resolve it.
3. **Hooks decide the package-cap question.** RRTMGP needs 8 hooks.
   - Under flatten lowering (2e) they are trivial.
   - In a separately generated package cap (2f) they become callbacks into
     host code -- the hardest open design question.
4. **Stage 2's gains are structural, not textual.** It barely changes what
   suite authors write. It delivers private names, an enforced interface and
   an exchangeable unit. The visible complexity in the Python files (hook
   count, interleaved CAM calls) comes down through other work: a
   scheme-visible loop index, call-site argument binding, the upstream scheme
   splits (§7), and the process-update combinator.
5. **Nothing consumes Python suites in production yet.** CAM-SIMA still builds
   from XML. Until it can build from a Python suite, every Stage 2 benefit is
   confined to this repository's examples.

### 11.2 Decisions

- **Primary test vehicle: CAM-SIMA's RRTMGP FPHYStest**
  (`SMS_Ln2.ne3pg3_ne3pg3_mg37.FPHYStest`, testmod
  `cam/outfrq_rrtmgp_derecho`).
  - It runs exactly the suite `examples/rrtmgp_composite` reproduces:
    `--dyn none --physics-suites rrtmgp` selects atmospheric_physics'
    `test/test_suites/suite_rrtmgp.xml`.
  - It is a strict numerical check: it starts from a CAM snapshot and compares
    the result against the "after" snapshot (`ncdata_check`,
    `ncdata_check_err = .true.`, `min_difference = 1e-15`), with
    `irad_always = 3` forcing radiation on every tested step and all SW/LW
    flux and heating diagnostics written.
  - It is cheap: null dycore, `ne3pg3`, 2 steps.
  - Its GPU twin, `cam/outfrq_rrtmgp_derecho_gpu`, is the vehicle for GPU
    residency (2g).
- **No synthetic test framework.** Building a compiled synthetic package
  example would be substantial work of uncertain value next to an existing,
  strict, real-physics test.
- **CAM-SIMA integration moves first** (old step 2h becomes step S2-0),
  using Stage 1's flattening, before any encapsulation code.
- **Core scope: 2a-2e + 2i** (encapsulation with flatten lowering; generated
  Fortran equivalent up to private-name renaming).
- **Deferred until there is a concrete need:**
  - 2f, the separately generated package cap (needed only to ship a compiled
    package to another group; blocked on the hook-callback design);
  - 2g, GPU residency across the boundary.

### 11.3 Revised sequence and acceptance criteria

Each step is its own PR, gated on the FPHYStest. Repositories differ: S2-0 is
CAM-SIMA (`cime_config/cam_autogen.py` and a testmod); S2-1..S2-4 are
xdsl-ccpp.

| Step | Work | Repo | Acceptance | Size |
|---|---|---|---|---|
| S2-0 | **CAM-SIMA builds from a Python suite** (old 2h, using Stage 1 flattening). `cam_autogen.py`: find a Python suite for a `--physics-suites` name when `CCPP_GENERATOR=xdsl_ccpp`; get its scheme list from the Python frontend instead of parsing XML (`_find_schemes_in_sdf`); pass `--py`. New testmod `cam/outfrq_rrtmgp_composite_derecho`, identical to `outfrq_rrtmgp_derecho` but supplying the composite suite, package and adapter (via the testmod's `SourceMods/src.cam/` if CIME supports that for testmods -- confirm first). | CAM-SIMA | Composite case passes `ncdata_check`; its generated caps in `bld/atm/obj/ccpp` are identical to the XML case's. | M |
| S2-1 | **2a + 2e without renaming:** `ccpp.composite` op; `@ccpp_composite` records into it; flatten lowering into the existing suite-cap path. | xdsl-ccpp | FPHYStest passes; caps identical to S2-0's. | S-M |
| S2-2 | **2c + 2d + renaming:** scoped resolution package → suite → host, hook scoping rule, private names renamed in the flattened output. | xdsl-ccpp | FPHYStest passes, including `ncdata_check` against the CAM snapshot (the golden reference). Generated code may differ from S2-1's only through scoping: private standard names renamed `<package>__<name>` (datatable, `resolved_vars.json`) and leaving the host-visible suite-variable lists. Two private names sharing a local name (RRTMGP's `kdist`) no longer collide without host metadata (unit test). | M-L |
| S2-3 | **2b:** public interface (declared or inferred, see 11.4) with validation, and package-level init, removing `rrtmgp_init_only()`. | xdsl-ccpp | FPHYStest passes, including `ncdata_check` against the CAM snapshot; interface violations are reported by the new validation. | M |
| S2-4 | **Deferred (2026-10-20); see "S2-4 decision" below.** **2i:** run-time conditional (`with when("do_shortwave_radiation"):`) so the adapter gates whole SW/LW entry points. | xdsl-ccpp | FPHYStest passes, including `ncdata_check` against the CAM snapshot. Removing the schemes' own `if (.not. dosw) return` checks is upstream follow-on work, not part of this step. | S |

Core total: about L (15-25 days) for xdsl-ccpp, plus S2-0 in CAM-SIMA.

**S2-2 as built.**
- **The package is the scope.** `rrtmgp = ccpp_package("rrtmgp")` with
  `@rrtmgp.entry_point`. It is not per composite, because RRTMGP's internal
  state (e.g. `kdist`) is made at init and used by both the SW and LW entry
  points.
- **Hooks are host code.** Parameters without defaults are hooks: what they
  run is recorded as a nested composite marked `hook` and belongs to the
  host's scope.
- **Private rule.** A name is private to P if all three hold:
  - it is not host-supplied, framework-managed or a constituent;
  - only P's own code touches it (entry points and slot implementations,
    not hooks);
  - P writes it.
- **Pass.** `scope-packages`, run before `flatten-composites`, renames each
  private name to `<package>__<name>` and marks it suite-owned.
- **Report.** `ccpp_dsl --list-package-scope` reports the result. With
  CAM-SIMA's host metadata: 51 of RRTMGP's 181 names are private, 47 are
  shared with host code, and 80 are host-declared.
  - The shared names are mostly the §7 boundary problem: objects
    `rrtmgp_pre`/`rrtmgp_post` allocate or free, and fluxes the diagnostics
    hooks read.
  - All 51 private names were already suite-owned in CAM. Regenerated with
    and without scoping, the RRTMGP suite cap is byte-identical; only private
    `lw_Ds` leaves `cam_ccpp_cap.F90`'s host-visible output lists.
- **Host-less example.** In `examples/rrtmgp_composite`, scoping removes the
  `kdist` collision. Full cap generation still needs host metadata: 12
  public names share local names (`hrate`, `qrs`, `qrl`, the flux objects,
  ...), which is the host's business, not the package's.

**S2-3 as built.**
- **Interface: inferred, with shared state checked (11.4 settled).** The
  names a package shares with host code are classified by who writes them:
  outputs, inputs, and shared state (both write).
  - Shared state must be declared in `ccpp_package(..., shared_state=[...])`.
    An undeclared one stops generation; a declared one that no longer is
    shared state gives a warning, so the list only shrinks.
  - RRTMGP, with CAM-SIMA's host metadata: 13 outputs, 21 inputs, 13 shared
    state. The shared state is the 11 objects `rrtmgp_pre`/`rrtmgp_post`
    allocate and free, plus the SW/LW heating rates, which CAM's
    `rrtmgp_dry_static_energy_tendency` also writes.
  - The §7 splits would remove the 11 objects. The heating rates need an
    interface (naming) decision upstream.
- **Package-level init, limited to init-only schemes.** `@rrtmgp.init`
  lists them. The generator places them after the package's last entry-point
  call, which keeps the init order. `scope-packages` rejects a scheme with a
  run phase there. The adapter no longer calls `rrtmgp_init_only()`.
  - Other package init phases keep their positions, interleaved with host
    inits as before.
- **Generated code.** CAM-SIMA's generated code is identical to S2-2's.

**S2-4 decision: deferred.**
- **The analysis.** Gating the SW/LW entry points with `when()` leaves
  physics state unchanged, but it changes history output on non-radiation
  steps. Inside the entry points, the cloud, SW and LW diagnostics run every
  step today (`write_diag` defaults to `.true.`), and would stop writing.
  - On those steps they currently write stale cloud optical depths, and
    fluxes from objects `rrtmgp_pre` re-allocates but never fills.
  - The heating-rate, gas-source, call-counter and aerosol-stub schemes are
    unaffected; `solar_irradiance_data` has no run phase.
- **The value.** S2-4 adds clarity, not encapsulation; the schemes already
  return early on `dosw`/`dolw`. That isn't worth a visible output change
  that is a CAM physics decision.
- **Caveat for any later attempt.** The `aerosol_optics` hook in the SW entry
  point also produces LW aerosol absorption. With a real aerosol scheme and
  different SW/LW frequencies, gating SW would leave LW using stale aerosol
  optics.
- **Known issue.** The diagnostics behaviour is CAM-SIMA issue #482 (open):
  on non-radiation steps the diagnostics should show the last radiation
  step's values, as CAM does. #426/#527 already did this for the net fluxes.
  So gating would move CAM-SIMA away from the intended behaviour. The fix is
  the CAM-SIMA developers': keep the quantities in the registry. It needs no
  generator work.

Division of work is as for Stage 1: changes are prepared in the
repositories; building, submitting and judging the CAM-SIMA test runs stays
with the project owner.

### 11.4 Open decisions, settled at the start of the step that needs them

- **S2-0:** the file convention for a Python suite in CAM-SIMA (e.g.
  `suite_<name>.py`) and where package and adapter modules live: the
  testmod's SourceMods for testing, atmospheric_physics and CAM-SIMA for
  production.
- **S2-3:** declared versus inferred public interface. Inferred fits the
  project's "no hand-maintained shadow files" direction.
- **Later:** whether and when to take on 2f (package cap) and 2g (GPU
  residency, validated on `outfrq_rrtmgp_derecho_gpu`).

### 11.5 Known limits of the test vehicle

- **One package.** The RRTMGP FPHYStest exercises a single package. Scoping
  between packages (2c across, e.g., radiation and convection) needs a
  multi-package suite: QPC4/CAM4, or a composite version of another FPHYStest
  suite, as a later step.
- **Single-step checks.** FPHYStest is a null-dycore, snapshot-in/snapshot-out
  check of one or two steps. It validates physics data flow, not long-run
  behaviour.

### 11.6 The `rrtmgp_pre`/`rrtmgp_post` split, worked out (2026-10-20)

A CAM-SIMA/atmospheric_physics change, not xdsl-ccpp work. It is recorded
here because it removes most of the shared state S2-3 declares.

**Today, per step:**

| Objects | Allocated by | Filled by | Read by | Freed by |
|---|---|---|---|---|
| 4 flux objects (SW/LW, all-sky and clear-sky) | CAM `rrtmgp_pre` | RRTMGP `*_rte` | CAM diagnostics hooks; CAM `rrtmgp_post` (`flwds`) | CAM `rrtmgp_post` |
| 7 optics/source objects | RRTMGP `rrtmgp_inputs`, `*_mcica_subcol_gen` | RRTMGP | RRTMGP | CAM `rrtmgp_post` |

The objects are allocated and freed every step. That must stay: the SW
objects are sized by the sunlit-column count (`nday`), which changes every
step.

**The split.**
- **CAM keeps** (in the adapter):
  - in `rrtmgp_pre`: `dosw`/`dolw` (`iradsw`/`iradlw`/`irad_always`),
    `dosw_heat`/`dolw_heat`, `nextsw_cday`;
  - in `rrtmgp_post`: `qrs`/`qrl` carry-over (times `pdel`), `netsw = fsns`,
    and `flwds` read from the LW flux object (a read of a package output).
- **RRTMGP gets:**
  - the flux-object allocation, in `rrtmgp_inputs_run`, where the other
    objects are allocated with the same sizes; it gains `spectralflux` as an
    ordinary input;
  - the freeing of all 11 objects.

**When to free.** The objects must outlive CAM's last read of them (the
diagnostics hooks and `flwds`). Two options:
- **(a) Free-before-allocate (preferred).** At the start of each step,
  RRTMGP frees the previous step's objects, then allocates new ones; a final
  phase frees the last set. The host gets no new call.
  - This relies on suite-internal variables persisting between steps. They
    do with xdsl-ccpp, as suite-cap module variables; to be confirmed for
    capgen-v1.
- **(b) A `rrtmgp_cleanup()` entry point** that the adapter calls after its
  last read. Simpler, but it adds an obligation on the host.

**Result.**
- **Shared state: 13 names down to 2.** The 7 optics and source objects
  become private; the 4 flux objects become ordinary outputs. Only the SW/LW
  heating rates remain, which need a separate naming decision.
- **No policy crosses the boundary.** Moving all of `rrtmgp_pre`/
  `rrtmgp_post` into the package instead was tried with `--list-package-scope`:
  shared state also drops to 2, but the package then touches 7 more CAM host
  variables (radiation frequencies, coupler fields, the heating carry-over),
  and `dosw`/`dolw` become private to it, taking the frequency decision away
  from the host.
- **No numerical change.** `ncdata_check` passes against the unchanged
  snapshot and history is unchanged. The split does not fix CAM-SIMA #482;
  persisting objects across steps cannot either, because of `nday`.

**Work.**
- Move code between `rrtmgp_pre.F90`, `rrtmgp_post.F90` and
  `rrtmgp_inputs.F90`, and update their `.meta` arguments and intents.
- `suite_rrtmgp.xml` and the composite change only if a scheme is added:
  none for (a), one for (b).
- Validate with the RRTMGP FPHYStest pair, plus `--list-package-scope`
  showing 2 shared-state names.
- Size: S-M, low risk.

---

## 12. Design: 2f (per-package cap) and 2g (GPU residency) (2026-10-20)

Today packages are lowered by flattening (§11.3). 2f instead generates one
Fortran module per package; 2g keeps GPU data placement correct across that
module boundary. GPU residency is a hard requirement.

### 12.1 Goals

| Goal | Decision |
|---|---|
| (a) compiler-enforced privacy | yes |
| (d) smaller, readable suite caps | yes |
| (e) a natural home for package-owned (device) state; simpler generator logic | yes |
| (b) a separately compiled, exchangeable package | not a goal; don't preclude it |
| (c) per-instance package state | deferred: state is shared, and a package in a multi-instance host is an error |

### 12.2 Decisions

1. **Hooks are lowered by segmentation, not callbacks.**
   - Each entry point is cut at its hook calls. Each maximal run of package
     calls becomes one package-cap routine (a *segment*).
   - Control flow that contains a hook (e.g. RRTMGP's diagnostic loop) stays in
     the suite cap, which calls segment, hook, segment.
   - A loop that holds only package code stays inside its segment.
2. **Every phase is segmented by the same rule:** register, init,
   timestep_init, run, timestep_final, final.
   - Segments follow the suite cap's call order exactly: a scheme is called
     only in the phases it has, and loops repeat only the run phase. Order and
     results are therefore unchanged.
3. **State.**
   - Package-private names become private module variables of the package cap,
     allocated on first use and deallocated in the package's final segment.
   - Declared shared state stays in the suite cap and is passed to segments.
4. **Instances:** a package in a multi-instance host (one declaring both
   `instance_number` and `number_of_instances`) is rejected.
5. **2g: package-cap routines never move data.**
   - Interface arguments pass straight through, with no directives. Data
     regions stay where `gpu_ccpp_cap_pass.py`/`gpu_data_pass.py` put them
     today.
   - Private device state gets `enter data create` at first allocation and
     `exit data delete` in the package's final segment.
   - Hook calls stay in the suite cap, unchanged.
6. **Implementation.**
   - A segment is a small group in its own module, generated by the existing
     group-generation code in `suite_cap.py`.
   - The lowering is opt-in (`--package-caps`) until the GPU gate passes.

### 12.3 Test vehicles

- **Synthetic generator tests** (CI, no GPU).
- **The RRTMGP CPU pair** for segmentation and package state on a large
  package.
- **The kessler FPHYStest on GPU** (`cam/outfrq_kessler_derecho_gpu`) as the
  end-to-end 2g gate.
  - The package: `calc_exner`, `temp_to_potential_temp`,
    `calc_dry_air_ideal_gas_density`, `kessler`, `potential_temp_to_temp`,
    `kessler_update`.
  - The wet↔dry conversions are hooks, giving about 3 run segments, with
    device-resident private `theta`/`exner`/`rho` crossing segments and host
    code between them.

### 12.4 Staging

1. **2f-1: segmentation analysis, no code change (done 2026-10-20).**
   - `transforms/package_segments.py`; the segments appear in
     `ccpp_dsl --list-package-scope`.
   - The multi-instance check runs in `scope-packages`.
   - RRTMGP: SW and LW each have 2 run segments (cloud optics + McICA; then
     gas optics through heating rate, inside the diagnostic loop). Init has 5
     package routines interleaved with host inits.
2. **2f-2: package caps on CPU,** gated on the synthetic tests and the RRTMGP
   CPU pair.
   - **Mechanism (refined 2026-10-21).** No synthetic suite in the IR: about
     90 places iterate over suites.
     - `lower-packages` (`transforms/lower_packages.py`) gives each segment a
       synthetic scheme whose metadata is the segment's interface. The
       interface is its schemes' arguments in that phase, minus private
       names, merged by standard name: `in` if never written, `out` if first
       written, otherwise `inout`. Disagreeing units, kind or dimensions are
       an error.
     - The suite then calls these synthetic schemes. The segment's calls move
       into `ccpp.package_cap`/`ccpp.segment` ops, so inner schemes are never
       host-matched.
     - The package cap module will be generated from those ops by the
       existing group-generation code.
   - **Consumers inside the pipeline must look into `ccpp.package_cap`:**
     constituents (correctness) and resolved-vars, scheme I/O capture and
     variable tracking (completeness). CAM-SIMA's compiled-source list and the
     datatable come from the frontend IR, so they are unaffected.
   - **Stage 1 (IR lowering) done.** RRTMGP lowers to 11 segments (5 run, 6
     init/timestep-init) with CAM's metadata and no interface conflicts.
   - **Stage 2 (Fortran) done: `ccpp_dsl --package-caps`.**
     `suitecap/package_cap.py` generates `<package>_package_cap.F90`: one
     routine `<segment>_<phase>` per segment, built by the group-generation
     code in physics mode (`register` excepted) without suite-state checks.
     - Segments taking the loop extent take `col_start`/`col_end` like group
       functions do; the synthetic scheme declares the same.
     - `--list-outputs` predicts the new file.
     - Without `--package-caps`, generated code is byte-identical (24
       CAM-SIMA configurations).
   - **CAM-SIMA RRTMGP generates with package caps.**
     - All 56 scheme calls have the same keywords.
     - Suite-owned arrays that the flattened cap slices at each call are now
       sliced once, at the segment call (23 arguments).
     - One genuine difference: some private arrays (`lw_Ds`, the
       `*_icld_vistau` arrays) are sliced `(col_start:col_end, ...)`
       flattened but passed whole in the package cap. The slicing rule needs
       every dimension available in the current function, and segments lack
       some (e.g. the g-point count). Identical when one call covers all
       columns, as in CAM-SIMA (`col_start = 1`, `col_end = columns_on_task`).
   - **FPHYStest fixes (s25a-s25d):**
     - the package cap owns only `<pkg>__*` names; shared ones are dummy
       arguments (`SuiteVariableModel.keep_only`);
     - an unmatched `len=*` character dummy stays assumed-length
       (`block_args._block_arg_type`), not `len=512`;
     - synthetic segment schemes record their schemes (`segment_schemes`), so
       `ccpp_physics_suite_schemes` lists RRTMGP's schemes and CAM reads
       their namelists;
     - in a package cap, allocations wait for the scheme that first writes
       their dimension, even when that dimension is a dummy argument.
   - **Open:**
     - routine names repeat the phase for non-run segments
       (`rrtmgp_prepare_init_1_init`);
     - package-only loops with a non-literal count are rejected;
     - constituents inside packages, resolved-vars and capture tooling;
     - private arrays passed whole rather than sliced (above): wrong rows
       for a host that runs physics in column chunks;
     - GPU (2g).
3. **2g: package caps on GPU,** gated on the synthetic GPU tests and a kessler
   composite, CPU and GPU, compared with the XML kessler cases.
   - **2g-1, package state lifecycle (done 2026-10-22).** `lower-packages`
     adds two state schemes per package, bracketing its entry-point calls:
     `<pkg>_state_create` (an `_init` phase only) and `<pkg>_state_delete`
     (a `_finalize` phase only), with only the error arguments and no
     package scheme in `segment_schemes`. The package cap generates
     `<pkg>_state_create_init` like the suite cap's `_initialize` -- the
     allocation sweep, no scheme calls -- so private arrays whose sizes are
     known at init are allocated there (device-resident ones also
     `enter data create`), and `<pkg>_state_delete_finalize` gets
     `exit data delete` for every device-resident private array
     (`_inject_suite_owned_gpu_exit`). Run segments no longer allocate
     these; arrays sized by per-step values (e.g. `nday`) keep the 2f-2
     run-time reallocation. Without this, private arrays were allocated on
     the run path, sized by the chunk, and never deleted from the device.
   - **2g-2, host uses of device data inside the package cap (done
     2026-10-22).** Two gaps, both now synced in the package cap with the
     suite cap's convention (the device copy is current between host runs:
     `update self` before each run of host uses, `update device` after):
     - private state used on the device by some schemes and on the host by
       others (`_inject_suite_owned_gpu_update`, as in the suite cap). The
       convention holds at every routine boundary, so it covers host uses in
       a later segment than the device write;
     - a shared argument a segment uses on both sides. Its synthetic scheme
       declared the first use's memory space, so a host use after a device
       one went unsynced. `interface_args` now declares it device-resident
       when any use is, the suite cap hands it over device-resident, and
       `_inject_segment_interface_gpu_update` syncs the host uses.
     The rule "package caps never move data" is refined: they never
     allocate, copy in or copy out shared data, but they do sync it between
     host and device. Calls inside a package-only loop are not synced (as
     for suite-owned variables in the suite cap). OpenACC only.
   - **2g-3, the kessler gate (passed 2026-10-23).** Kessler is a package
     in atmospheric_physics' `suites-py/parameterizations/kessler_package.py`
     (calc_exner through kessler_update; the wet/dry conversions are hooks
     filled by CAM's adapter, `kessler.py`), run by the Python test suite
     `test/test_suites-py/suite_kessler_test.py`. Private: theta, exner, rho,
     relhum; three run segments. Gate: `/cam-sima-test <id> kessler
     [gpu] pkgcap` against the XML `kessler_test` cases -- CPU s27b (gnu,
     exact `ncdata_check`) and GPU s29a (nvhpc/OpenACC, 1e-8 against CPU
     snapshots) both PASS, with the package's syncs and device lifetime as
     in the reference. Fixed on the way:
     - an advected array the suite cap owns (Kessler's dry water species,
       written by a hook) was neither a segment argument nor package state
       (s27a build failure); in a package cap only its private names are
       cap-owned (`phase_functions._classify_args`);
     - init segments repeated the state-create routine's allocations; they
       no longer do (`package_cap._drop_allocations_in`).
     Remaining differences from the reference, behaviour-neutral: argument
     order of the generated phase routines (BACKLOG
     `canonical-error-arg-order`) and the `scheme_list` order (BACKLOG
     `package-scheme-list-order`).
   - **Open (2g):** routine names repeat the phase for non-run segments
     (`kessler_microphysics_init_1_init`); shortening them needs a change to
     segment naming, since dropping the phase makes run and init segments
     share a scheme name.

4. **The default switch,** decided later.

The separate track, `xdsl-upgrade` and then `gpu-conversion-residency` (see
BACKLOG.md), does not block 2f.
