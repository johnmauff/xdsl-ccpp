# Automating EAMxx Bridge Generation with xdsl-ccpp

This document is a forward-looking design proposal, not a record of work already done (see
`README.md` for that). It addresses: given both the CPU and GPU (OpenACC) Fortran versions of a
scheme like Kessler, how would `xdsl-ccpp` need to be used and extended to automatically generate
all of the code required to call it from EAMxx, including the EAMxx `AtmosphereProcess` C++
interface itself, not just the Fortran bridge/cap layer? Investigated 2026-07-29 by reading the
`xdsl-ccpp` generator source (`xdsl_ccpp/transforms/`) in addition to its docs. No code changes were
made; nothing here has been implemented.

---

## What already exists in xdsl-ccpp that's reusable

The generator has more GPU-directive infrastructure than its own docs (`multilanguage_limitations.md`)
let on. `xdsl_ccpp/transforms/gpu_data_pass.py` and `gpu_ccpp_cap_pass.py` read `memory_space`
metadata annotations and automatically insert `!$acc`/`!$omp target` data-movement directives
(`enter/exit data`, `update device/self`) at the correct lifecycle-phase boundaries, including
handling for cross-phase hoisting and per-scheme "diverged" variables. This is exactly the machinery
that produced the directives seen in `generated_bridge/Kessler_ccpp_cap.F90`.

However, this GPU-directive machinery is wired only into the plain `ccpp_cap.py` path -- the one
that expects a Fortran host module (`type = module`, e.g. the never-generated
`eamxx_kessler_host_mod`) -- and is **not** connected to `xdsl_ccpp/transforms/cpp_interop.py`'s
chost-cap path, which is what actually generates `Kessler_ccpp_chost_cap.F90`/`.h` and is what the
EAMxx C++ interface calls. That's the structural reason the chost cap has zero GPU-directive support
today.

`cpp_interop.py` itself (the chost-cap generator, pass name `generate-cpp-cap`) is a solid,
well-factored per-lifecycle emitter: it already does kind mapping (`kind_phys` -> `real(c_double)`/
`double`), DDT flattening, and automatic `ncol`/`nz` injection, all driven off the completed IR. A
new EAMxx-targeted printer should build on this same completed-IR state rather than re-deriving it
from the raw `.meta` files.

---

## Phase A -- Teach the metadata format about CPU/GPU scheme variants

This directly fixes bugs #2/#3 from `README.md` at the tool level instead of via a hand-patched meta
fork.

1. **Fix the upstream drift first.** Update
   `GPU_ports/atmospheric_physics/schemes/kessler/kessler_update.meta` so it actually matches its own
   `.F90` (add the missing `ncol`/`nz` entries on `kessler_update_timestep_init` and
   `kessler_update_timestep_final`, in the real subroutine's argument order, including the
   `errflg`-before-`errmsg` ordering on `timestep_final`). Do the same check for `kessler.meta`, even
   though `kessler_run`/`kessler_init` were confirmed identical between the CPU and GPU_ports trees.
2. **Add a variant tag to the metadata format.** Extend `[ccpp-table-properties]` with a new
   property, e.g. `variant = openacc`, parallel to the existing `array_layout` and `language`
   properties, so the CPU and GPU_ports `.meta` files for the same scheme can both be fed to the
   generator in one invocation without one overwriting the other.
3. **Extend `suite_cap.py`'s call emission.** The code that currently emits a single hardcoded
   `call kessler_update_timestep_init(...)` needs to detect when two variant tables for the same
   scheme+lifecycle have different argument lists, and emit a `#ifdef <directive-flag>` /
   `#else` branch automatically -- mechanizing the fix from the README's to-do list, generically,
   for any future scheme divergence, not just Kessler.

Effort: moderate. No new printer required. This alone would make `ccpp_xdsl` capable of generating a
correct, dual-variant chost cap for Kessler in one command, with no hand-editing of generated output.

---

## Phase B -- Make the chost cap's device-pointer contract explicit

Today, "the host always hands the cap an already-resident device pointer" is true only because EAMxx
happens to behave that way and the GPU_ports scheme happens to use `!$acc ... deviceptr(...)`
clauses internally -- nothing in the metadata says this is guaranteed. Proposed fix: add a host-meta
property (e.g. `gpu_pointer_mode = deviceptr`, sibling to the existing `array_layout`) that tells
`cpp_interop.py` to emit zero data-staging directives at the chost-cap boundary and simply pass
pointers through as-is.

This turns `multilanguage_limitations.md` section 2's current state -- "the generated code provides
no help with this, hope your scheme happens to use `deviceptr`" -- into a documented,
generator-checked contract. It also creates a place for the generator to flag a mismatch at
generation time (e.g. `memory_space = device` declared on an argument, but the scheme's own
directives don't use `deviceptr`), instead of only failing silently at runtime.

---

## Phase C -- A new "EAMxx AtmosphereProcess" printer

This is the actual "generate the whole C++ interface" ask. Nothing like it exists in xdsl-ccpp today
-- `multilanguage_plan.md` only ever generates a flat C header plus a thin C++ ergonomics wrapper
(`Kessler_chost.hpp`), never a framework-integrated host class. It would be a new backend module,
e.g. `xdsl_ccpp/backend/print_eamxx_process.py`, consuming the same completed IR that
`cpp_interop.py` already builds.

### Mechanical part (low risk -- the IR already has what's needed)

- `initialize_impl` / `run_impl` / `finalize_impl` bodies that call the generated
  `Kessler_chost_physics_*` entry points in the correct lifecycle order. This is a direct readout of
  the suite's lifecycle function list, which `cpp_interop.py` already computes internally.

### Requires genuinely new, EAMxx-specific metadata vocabulary

- `create_requests()`'s `add_field<Required/Updated/Computed>` / `add_tracer` calls need each host
  variable classified beyond what CCPP's `intent` already captures: is this a Field-Manager-registered
  field, a tracer, or purely local/derived data never seen by the host's field manager? What
  `FieldLayout` tags does it need (`COL`, `LEV`)? (`units` is already present in the metadata and
  needs no extension.)
- Buffer management (`requested_buffer_size_in_bytes` / `init_buffers`, `ATMBufferManager`) and the
  Kokkos transpose glue (`params_helpers` / `params_computed` structs, `h_*` vs `f_*` view selection)
  require the generator to understand EAMxx's buffer-manager and Kokkos-View APIs specifically. There
  is no existing analog anywhere in the tool for this. This is the highest-effort, most bespoke piece
  of the whole plan, and the first version would likely still need per-process hand-tuning (pack
  sizes, buffer counts) even once generated.

### Should stay hand-written -- permanently, not just for now

- **`add_invariant_check` / `add_postcondition_check` physical bounds** (e.g. `qv` clamped to
  `[1e-13, 0.2]`). This is an EAMxx QA convention with no CCPP equivalent. Encoding "what bounds are
  physically sane for this variable" into generic scheme metadata would be scope creep well beyond
  what a bridge-code generator should take on.
- **Energy-fixer boundary-flux zeroing** -- EAMxx-integration bookkeeping unrelated to Kessler
  itself.

The claim that originally sat here -- that all of the host-side physics derivation
(`PF::exner_function`, `calculate_theta_from_T`, `calculate_dz`, `calculate_z_int`/`calculate_z_mid`)
should stay permanently hand-written because it's "not part of Kessler's CCPP-described interface at
all" turned out to be wrong. See the next section.

---

## Revision (2026-07-29): the real suite XML changes the "hand-written" assessment

The assessment above was based only on the two-scheme suite (`kessler`, `kessler_update`) described
by `xdsl-cpp/examples/kessler/scheme/kessler_suite.xml`, the ad hoc suite definition used to generate
this bridge. The actual upstream suite definition,
`atmospheric_physics/suites/suite_kessler.xml`, lists 20 schemes across two groups:

```
physics_before_coupler:
  calc_exner, temp_to_potential_temp, calc_dry_air_ideal_gas_density,
  wet_to_dry_water_vapor, wet_to_dry_cloud_liquid_water, wet_to_dry_rain,
  kessler,
  potential_temp_to_temp, dry_to_wet_water_vapor, dry_to_wet_cloud_liquid_water, dry_to_wet_rain,
  kessler_update,
  qneg, geopotential_temp,
  check_energy_zero_fluxes, check_energy_scaling, check_energy_chng,
  sima_state_diagnostics, kessler_diagnostics
physics_after_coupler:
  thermo_water_update, check_energy_scaling, dycore_energy_consistency_adjust,
  apply_tendency_of_air_temperature, sima_tend_diagnostics
```

`eamxx_kessler_process_interface.cpp` already tracks this exact list via inline
`// <scheme>name</scheme>` comments -- whoever wrote the bridge was working through this real suite
XML scheme-by-scheme. Reading `schemes/utilities/state_converters.F90` (which implements
`calc_exner`, `temp_to_potential_temp`, `calc_dry_air_ideal_gas_density`, and all the wet/dry
conversion schemes) splits the old, single "physics derivation" bucket into three categories that
need different treatment, plus a fourth for `geopotential_temp` specifically.

### Category 1 -- Real CCPP schemes, formulas match, kept hand-fused purely for performance

`calc_exner_run` (`exner = (pmid/ref_pres)**(rair/cpair)`) and `temp_to_potential_temp_run`
(`theta = temp/exner`) are essentially the same math as `PF::exner_function`/
`PF::calculate_theta_from_T`, just expressed as standalone CCPP schemes instead of Kokkos device
functions. One real subtlety: `calc_exner_run` takes per-column, composition-dependent `rair`/`cpair`
as arguments, while EAMxx's `PF::exner_function(p_mid)` uses fixed dry-air constants internally -- so
the current hand-written preprocessing kernel and the real CCPP scheme are not even bit-identical
today; the CCPP version is arguably *more* thermodynamically self-consistent, since it reuses the
same composition-dependent `cpair`/`rair` fed into Kessler downstream. These genuinely could be
generated and called as separate bridge calls -- the reason not to is pure performance: doing so
would add two more Fortran round-trips (with column-major transposes each way) for cheap per-column
arithmetic that's currently fused into one Kokkos `parallel_for` alongside the rest of the
preprocessing. That is a legitimate engineering tradeoff, not a generator limitation, so the original
"not part of Kessler's CCPP interface at all" framing was wrong for this subset.

### Category 2 -- Nominally generatable; needs manual/metadata verification of matching conventions, not an assumption

`calc_dry_air_ideal_gas_density_run` computes `rho = pmiddry/(rair*temp)` using **dry** mid-level
pressure, not EAMxx's mass-weighted `rho = pseudo_density/(g*dz)` derivation -- a genuinely different
vertical-coordinate approach requiring a `pmiddry` quantity EAMxx does not currently compute.
`create_requests()` even has a commented-out line, `add_field<Required>("pseudo_density_dry", ...)`,
suggesting this was started and abandoned. Whether the CCPP scheme's ideal-gas density and EAMxx's
mass-weighted density agree closely enough to be interchangeable is a real open physics question, not
a code-generation question, and should not be assumed either way without checking.

The wet/dry mixing-ratio converters (`wet_to_dry_water_vapor`, `dry_to_wet_water_vapor`, etc.) looked
like a similar unaddressed gap at first glance, since the bridge has no comment justifying skipping
them (every other skipped scheme in Category 3 below has one). **This has since been confirmed not to
be a bug for Kessler specifically**: both `kessler_run` and `kessler_update`'s Fortran already declare
`qv`/`qc`/`qr` with standard name `water_vapor_mixing_ratio_wrt_dry_air` (etc.), and this matches what
EAMxx already provides for those fields, so no wet/dry conversion is needed in this particular case --
the standard names agree on both sides of the host/scheme boundary.

That agreement will not hold for every future scheme, though. CCPP's standard-name convention is
exactly the mechanism that should catch a mismatch (a scheme expecting
`water_vapor_mixing_ratio_wrt_dry_air` will simply fail to match a host variable declared
`_wrt_moist_air`, forcing either an explicit conversion scheme in the suite or a host-side fix) -- but
that protection only works if the host `.meta` file's standard name is *honestly* the basis the host
variable is actually on. A host author who mislabels a wet-basis field as dry-basis produces a
silent, high-confidence-looking match that is simply wrong, and no automated check catches a
mislabeling problem, since matching is defined as standard-name equality, not a semantic audit. So
the right practice going forward is: confirm the moisture basis (and any other convention a standard
name implies) by hand for each new field the first time it's wired up, and/or add this to a
host-to-scheme meta consistency check (see the suite-coverage idea below) rather than assuming
agreement by default.

### Category 3 -- Real schemes, structurally superseded by EAMxx's own centralized infrastructure

`qneg`, `check_energy_zero_fluxes`/`check_energy_scaling`/`check_energy_chng`,
`sima_state_diagnostics`/`kessler_diagnostics`/`sima_tend_diagnostics`, `thermo_water_update`,
`dycore_energy_consistency_adjust`, `apply_tendency_of_air_temperature` are all real, generatable CCPP
schemes, but each has a comment in `eamxx_kessler_process_interface.cpp` mapping it to an
EAMxx-generic mechanism instead: postcondition/invariant field checks substitute for `qneg`,
`output_fields.yml`-driven diagnostics substitute for the `sima_*`/`kessler_diagnostics` schemes, and
a single centralized energy-fixer `AtmosphereProcess` (wrapping the whole process list, not per-scheme)
substitutes for the `check_energy_*` family. Calling the generated versions of these *in addition to*
EAMxx's centralized equivalents would risk double-applying corrections -- e.g. two independent energy
adjustments on the same budget. This is a durable, architectural reason to exclude them, not a
metadata gap, and a smarter generator should never try to paper over it. Two of these
(`thermo_water_update`, and the `dycore_energy_consistency_adjust`/`apply_tendency_of_air_temperature`
pair) are marked with "I think" / "TODO ?" in the existing comments -- genuinely unresolved
uncertainty in the current bridge, independent of code generation.

### `geopotential_temp` -- a fourth, distinct case: linked but dead

`geopotential_temp` is in the suite, and its `.F90` is already linked into
`kessler/CMakeLists.txt`'s source list, but it is never actually called anywhere -- `z_mid` is instead
derived by a hand-written Kokkos team-parallel-scan (`calculate_z_int`/`calculate_z_mid`). Unlike
Category 3's entries, there is no comment establishing this as a deliberate, verified substitution --
it reads as linked dead code rather than a documented architectural decision.

### A cheaper, higher-value piece of tooling than the full `AtmosphereProcess` printer

Reading the real suite XML suggests a "suite-coverage checker": a small script that diffs the real
suite XML's `<scheme>` list against the `<scheme>` tracking comments already present in
`eamxx_kessler_process_interface.cpp`, and flags any suite entry with no corresponding comment at
all. That check alone would have flagged the wet/dry conversion question mechanically (it turned out
to be a non-issue for Kessler, but the bridge gave no evidence of having checked), and would catch the
same class of silent gap for every future scheme brought in this way. It requires no new xdsl-ccpp
printer and no new metadata vocabulary -- just a script comparing two lists of scheme names -- and
would be worth building well before Phase C.

---

## Revision (2026-08-25): what changed upstream since 2026-07-29

Reviewed `main` from `196c224` (this doc's commit) through `736b976` (~30 commits, 2026-08-13 to
2026-08-24). `suite_cap.py`, `cpp_interop.py`, `gpu_data_pass.py`, `gpu_ccpp_cap_pass.py` are all
still the right targets. Three things materially change the plan:

**Phase A0 (new, blocking): the lifecycle model changed from 6 phases to 8** (task #28, landed
2026-08-20). Real capgen-v1 splits "initialize" into suite-level `ccpp_init` (scheme-call-free) and
per-group `ccpp_physics_init` (owns the actual scheme `_init` calls), and "finalize" likewise. Not
hypothetical for Kessler: the `kessler-chost-ftn.mlir` golden test shows
`Kessler_chost_physics_initialize` now takes only `(errmsg, errflg)`, with the real init/final
scheme calls moved to new `Kessler_chost_physics_physics_initial`/`_physics_final` entry points.
**Regenerating the bridge today without updating `eamxx_kessler_process_interface.cpp` breaks the
build** (arity mismatch) and silently drops the init/final scheme calls if not rewired. Treat
"regenerate, fix `initialize_impl`/`finalize_impl`'s call sites, re-baseline `kessler-README.md`" as
a required Phase A0, ahead of everything else. This also sharpens Phase C's open question: EAMxx's
`initialize_impl`/`finalize_impl` almost certainly map to `ccpp_physics_init`/`_final`, not the
suite-scoped `ccpp_init`/`_final` -- someone still needs to decide who calls those. The
GPU-directive machinery already covers both new phases, so no extra work needed there.

**Phase A0 done (2026-08-25).** Regenerated against current `main` and updated
`eamxx_kessler_process_interface.cpp` (`generated_bridge/` and the `xdsl-ccpp-generated/bindc_eamxx_acc/`
reference copy in the E3SM_claude tree). Confirmed bug #1 no longer appears. One more signature
change turned up beyond the phase split: `Kessler_chost_physics_run` dropped `col_start`/`col_end`
entirely (the real Fortran never used them). Also found, only by reading the regenerated
`kessler_suite_cap.F90`'s body directly -- a real state-machine ordering requirement with no
comment anywhere documenting it: `physics_initial` must run *after* `initialize`, and
`physics_final` must run *before* `finalize`, or the generated `ccpp_suite_state` check silently
skips the real scheme calls (or fails its own check) instead of erroring obviously. `kessler-README.md`
is re-baselined with all of this; not yet compiled/tested against a real EAMxx build.

**The ordering bug is generic, not Kessler-specific.** The `ccpp_suite_state` check lives in
generated `*_suite_cap.F90` code, not anything Kessler wrote -- every future suite/process built
against this generator's 8-phase model will hit the identical `physics_initial`-after-`initialize`/
`physics_final`-before-`finalize` trap, with the identical absence of any generated comment warning
about it. Worth raising upstream as a generator fix, not just a documentation fix -- e.g. collapsing
`initialize`+`physics_initial` and `physics_final`+`finalize` into single entry points would remove
the footgun instead of requiring every future caller to independently discover it by reading
generated Fortran.

**Two other things are now stale, discovered but out of Phase A0's scope to fix:** the E3SM_claude
tree's own `kessler/README.md` (a separate file from this one, already diverged before today -- still
has the old, wrong "self-inflicted" Bug #1 diagnosis) and `xdsl-ccpp-generated/bindc_eamxx/` (the
non-`--directive acc` reference copy, not regenerated this pass).

**No environment on this system had `xdsl` installed** before this regeneration -- not the base
Python, not any of the user's existing conda environments (several import `xdsl_ccpp` successfully
but not its own `xdsl` dependency, suggesting a stale/partial install somewhere). Needed a fresh venv
(`pip install -e .`) to get a working `ccpp_xdsl` command at all -- anyone else regenerating this
bridge will hit the same gap, and it's worth a documented setup step somewhere more discoverable than
this doc (`xdsl-ccpp`'s own top-level README). Relatedly: everything above was verified by hand
(argument counts/types checked one call site at a time against the regenerated header), not by
compiling -- a cheap compile-only smoke test for the Kessler bridge would catch this exact class of
drift automatically on future regenerations, and is a similarly cheap, high-value addition as the
still-unbuilt suite-coverage checker.

**Bug #1 (`kessler_suite_suite_*` double naming) is fixed upstream** (#93/`00bbffb`) -- it was a
real generator bug (an unconditional `_suite` infix), not the self-inflicted naming issue
originally diagnosed. Doesn't change Phase A's scope (which only ever targeted bugs #2/#3); the doc
and `kessler-README.md` should just stop implying bug #1 is open.

**Phase A items 2/3 (`variant`, `#ifdef` emission) and Phase B (`gpu_pointer_mode`) are still fully
unimplemented**, and the extension point is unchanged: `ccpp_xml.py`'s `CCPPTableProperties.setAttr`
still only accepts `name`/`type`/`dependencies`/`dependencies_path`/`source_path`/`array_layout`/
`language` -- worth doing together, since they'd extend the same allow-list and the same
historically-drifting `ccpp_xml.py`/`py_api.py` forwarding path. The emission side is easier than it
looked in July: `suite_cap.py` already has a working precedent for gating two argument-list variants
of one call (`PresentCheckOp`/`ActiveCheckOp`), and `print_ftn.py` already prints `#ifdef`/`#endif`
at column 0 for the GPU-directive ops -- a new op for this is a recombination of both, not new
territory.

**Still true:** the suite-coverage checker (diff a real suite XML's `<scheme>` list against
`eamxx_kessler_process_interface.cpp`'s tracking comments) is still unbuilt, still cheap, still
worth doing early. Every commit in this window was a CAM-SIMA capgen-v1-parity push, not EAMxx
work -- but it's shared generator infrastructure that helps the EAMxx path as a side effect (the
naming/lifecycle fixes above), which is exactly why regenerating and re-baselining (Phase A0) before
investing further in Phase A's `#ifdef` work is the right order now.

---

## Phase D -- A shared EAMxx C++ device-function layer

Investigated 2026-08-25, prompted by: could a new EAMxx process just write `pk = compute_exner(p_mid)`
instead of regenerating the `params_helpers`/`params_computed`/transpose/`ATMBufferManager` apparatus
Phase C's Category 1 already flagged as its highest-effort piece, for schemes simple enough that a
Fortran round-trip isn't mandatory?

**Two live EAMxx precedents already exist.** `PhysicsFunctions` (`PF::exner_function`,
`calculate_theta_from_T`, `calculate_dz`) is this pattern in miniature -- pure, pointwise
`KOKKOS_INLINE_FUNCTION`s, no Fortran call, no transpose, no buffer manager.
`calculate_z_int`/`calculate_z_mid` extend the same idea to a team-parallel column scan. More
strikingly, `physics/tms` (and `cld_fraction`) show a *whole scheme* done this way: no
`params_helpers`, no buffer manager, no `BIND(C)` -- just `TMSFunctions::compute_tms(ncols, nlevs,
<views>...)` called once in `run_impl`. This is the minority pattern in EAMxx today (Kessler/ZM's
Fortran-bridge pattern is still the majority), but it's real and working, not something to invent.

**Hard constraint: xdsl-ccpp has no representation of scheme bodies, only signatures.** Neither
frontend (`fir_to_meta.py`, `fparser2_to_meta.py`) ever builds an IR for a scheme's executable
statements -- both only extract declaration-level metadata. Auto-transpiling Fortran math into a
`KOKKOS_INLINE_FUNCTION` would need a new Fortran-executable-statement parser/IR/printer from
scratch -- an order of magnitude bigger than anything else in this plan, and out of scope. What
*is* achievable is automating the layer above the math: generating the **declaration** (name, typed
args, units) and validating it against the CCPP metadata, while a human writes the body once --
exactly as already happened for `PF::exner_function`/`TMSFunctions::compute_tms`.

### D.1 -- Consolidate the view/type vocabulary

Cheap, no generator involvement. `eamxx_types.hpp`/`physics_constants.hpp` already centralize
`Real`/`KokkosTypes`/named constants; what's *not* centralized is the `Pack`/`view_2d`/`fview_*`
aliasing every process (`kessler_functions.hpp`, `zm_functions.hpp`, ...) re-declares locally from
the same underlying `ekat` types. Pull that into one shared header (`eamxx_ccpp_view_types.hpp`)
before generating anything -- pure refactor, de-risks everything below.

### D.2 -- Per-scheme portability triage

Classify each scheme's `_run` (and relevant `_init`/`_timestep_*`) subroutine as:
- **Pointwise/elemental** -- scalar-in/out per (col,lev), no cross-level dependency. Direct
  `PF`-style candidate.
- **Column-scan** -- needs a team + a running dependency up/down the column (`calculate_z_int`-style).
- **Structurally superseded** -- an EAMxx-generic mechanism already substitutes for it (Category 3) --
  only assumed where an existing EAMxx interface actually confirms it (Kessler's bridge comments), or
  for schemes generalizing cleanly from those (shared utilities/diagnostics used by every suite).
- **Genuinely needs the Fortran bridge** -- stateful in a way that doesn't reduce to the above.

### D.2 results (2026-08-25): every scheme in `atmospheric_physics`

Read every `_run`/`_init`/`_timestep_*`/`_register` subroutine across `schemes/` (21 packages,
~36,000 lines, ~190 CCPP entry points), cross-checked against the repo's 6 production suites
(`kessler`, `cam4`, `cam7`, `adiabatic`, `tj2016`, `held_suarez_1994`, `musica`). Excluded:
`phys_utils/`, `to_be_ccppized/` (plain Fortran helper libraries, essentially no `arg_table_` entries
of their own), and `test/`'s CI-only schemes/suites.

Four structural situations came up that the four buckets don't cleanly capture:

1. **Gather/scatter over an active-column subset** (`zm_convr_run`/`zm_conv_convtran_run`/
   `zm_conv_momtran_run`): compact convectively-active columns via an index list (`ideep`,
   `il1g:il2g`) before operating, then scatter back. No Kokkos-native analog exists in this plan --
   a fifth pattern, not a column-scan variant.
2. **Thin wrappers around an external, already-non-Fortran library** (RRTMGP, MUSICA): their `_run`
   entry points contain almost no physics math of their own -- confirmed via `use mo_rte_lw`/
   `mo_gas_optics_rrtmgp` imports (RRTMGP) and opaque `micm_t`/`tuvx` solver-object calls (MUSICA).
   Real RTE+RRTMGP already has an independently-maintained native C++ port used in production climate
   models (well-established, not independently re-verified here). Hand-porting Fortran math is very
   likely the wrong move for both packages -- the better path is investigating a direct bridge to
   whatever native C++ RTE+RRTMGP/MICM/TUV-x implementation already exists, a separate track from
   Phase D.
3. **Self-contained inline implicit solves are portable; externally-delegated ones aren't**, even for
   the same math. `tj2016_sfc_pbl_hs_run` does its own two-pass inline Thomas-algorithm PBL solve
   (portable, column-scan). `vertical_diffusion`'s diffusion schemes and `gravity_wave_drag`'s
   `gw_ediff`/`gw_diff_tend` solve the same class of implicit system by calling out to
   `to_be_ccppized`'s `fin_vol_solve`/`TriDiagDecomp` -- genuinely needs Fortran, since the numerics
   live in a separate, not-yet-CCPP-ized module.
4. **Some schemes/packages aren't referenced by any of the repo's 6 suites.** `rayleigh_friction` and
   `mmm/` (two of whose schemes additionally `use` Fortran modules confirmed absent from the entire
   repo -- MPAS compatibility shims, not something a CAM-SIMA/EAMxx bridge would ever generate
   against). Included below for full-repo completeness, flagged as currently inert.

A methodological note: "structurally superseded" is only asserted where an existing EAMxx interface
confirms it (Kessler's own tracking comments), or for the same shared schemes generalizing to every
other suite that also calls them (`qneg`, `check_energy_*`, `geopotential_temp`, `sima_*`/
`kessler_diagnostics`, plus the "unconfirmed"-hedged `thermo_water_update`/
`dycore_energy_consistency_adjust`/`apply_tendency_of_air_temperature` group) -- not assumed for any
other package.

**Suites column key:** `K`=kessler, `C4`=cam4, `C7`=cam7, `A`=adiabatic, `TJ`=tj2016, `HS`=held_suarez_1994, `M`=musica.

**`utilities`** (K, C4, C7, A, TJ, HS) -- generic, shared by nearly every suite.

| Scheme/function | Bucket | Evidence |
|---|---|---|
| `calc_exner_run`, `temp_to_potential_temp_run`, `potential_temp_to_temp_run`, `calc_dry_air_ideal_gas_density_run` | Pointwise | per-level array math, no recurrence. `calc_exner`/`temp_to_potential_temp` already have hand-written EAMxx analogs (`PF::exner_function`/`calculate_theta_from_T`) -- port means re-derive-and-verify, not copy-paste, since `calc_exner_run` takes composition-dependent `rair`/`cpair` while `PF::exner_function` uses fixed constants. `calc_dry_air_ideal_gas_density`'s dry-pressure-based `rho` vs. EAMxx's mass-weighted `rho` is an open physics question independent of portability. |
| `wet_to_dry_water_vapor_run`, `wet_to_dry_cloud_liquid_water_run`, `wet_to_dry_cloud_ice_run`, `wet_to_dry_rain_run`, `dry_to_wet_water_vapor_run`, `dry_to_wet_cloud_liquid_water_run`, `dry_to_wet_cloud_ice_run`, `dry_to_wet_rain_run` | Pointwise | `q_dry(:,k)=q(:,k)*pdel(:,k)/pdeldry(:,k)` or inverse. Not needed for Kessler (its `qv`/`qc`/`qr` are already dry-basis on both host and scheme sides), but trivially portable for a future suite that needs them. |
| `convert_dry_constituent_tendencies_to_dry_air_basis_run` | Pointwise | per-point `tend_q *= pdel/pdeldry` |
| `apply_tendency_of_eastward_wind_run`, `apply_tendency_of_northward_wind_run`, `apply_heating_rate_run`, `apply_tendency_of_air_temperature_run`, `apply_constituent_tendencies_run` | Pointwise | `state += tend*dt`, per level, then zero the tendency; `apply_tendency_of_air_temperature_run` also "likely superseded (unconfirmed -- TODO? in Kessler's bridge)" by the energy fixer |
| `geopotential_temp_run` | Column-scan, but **confirmed structurally superseded** | Cumulative height integral up the column (`zi(k)=zi(k-1)+...`) -- same shape as `PF::calculate_z_int`/`calculate_z_mid`, which is in fact EAMxx's own substitute for it (bridge comment: "-> done above when calculating z_mid"). **Corrects an earlier finding in this doc**, which had called this "linked dead code" with no justifying comment -- direct re-inspection shows the comment exists. Kept in the table (rather than dropped like `qneg`) because its math shape is the clearest evidence in the whole suite that column-scan schemes really are Phase-D-portable. |
| `qneg_run` (+`_init`/`_timestep_final`/`_final`) | Structurally superseded | confirmed -- substituted by EAMxx's postcondition/invariant checks. Its own global violation-stats/MPI-reduce logging (`qneg_print_summary`) has no EAMxx equivalent, but it's optional debug output, not physics -- doesn't block dropping the scheme. |

**`conservation_adjust`** (K, C4, C7, A, TJ) -- generic energy/water bookkeeping.

| Scheme/function | Bucket | Evidence |
|---|---|---|
| `check_energy_zero_fluxes_run`, `check_energy_chng_run`(+`_timestep_init`) | Structurally superseded | confirmed "taken care of by HOMME"; `check_energy_chng` additionally non-portable on its own merits (`use cam_thermo, only: get_hydrostatic_energy`; own comment: "non-portable due to dependencies on cam_thermo") |
| `check_energy_scaling_run` | Superseded (1st use, confirmed) / unconfirmed (2nd use) | `scaling_dycore=cpairv/cp_or_cv_dycore` -- trivially pointwise either way, same code both uses |
| `check_energy_fix_run`, `check_energy_save_teout_run` | Pointwise | scalar broadcast / per-column copy |
| `dycore_energy_consistency_adjust_run` | Likely superseded, unconfirmed ("TODO ?" in Kessler's bridge) | `tend_dTdt_local=(scaling_dycore-1)*tend_dTdt` -- pointwise if not superseded |
| `check_energy_gmean_run` | Genuinely needs Fortran | own comment: "non-portable due to dependency" on `gmean_mod`; calls `gmean()`, an MPI-parallel global mean |
| `dme_adjust_run` | Column-scan | `pint(:,k+1)=pint(:,k)+pdel(:,k)` -- genuine level-to-level recurrence, plus a pointwise per-constituent mass adjustment; early-returns if not moist-dycore |

**`dry_adiabatic_adjust`** (C4, C7): `dadadj_run` -- **genuinely needs Fortran** (adaptive iterative
convergence solver, doubling-retry `zeps`, same family as `kessler_run`'s own subcycling).

**`rayleigh_friction`** (unused by any suite here): `rayleigh_friction_run` -- **pointwise**
(`dudt(:,k)=c1*u(:,k)` etc.; `otau` moves from module state to an explicit argument, same caveat as
Kessler's `gravit`).

**`held_suarez`** (HS): `held_suarez_1994_run` -- **pointwise** (per-level `ds`/`du`/`dv` from a
fixed coefficient profile and per-column trig terms, no recurrence).

**`cloud_fraction`** (C4: all 4; C7: 2 of 4).

| Scheme/function | Bucket | Evidence |
|---|---|---|
| `cloud_fraction_fice_run`, `set_cloud_fraction_top_init`, `convective_cloud_cover_run`(+`_init`) | Pointwise | piecewise map / scalar copy / per-(i,k) formula from inputs at k, k+1 (not own prior output) |
| `compute_cloud_fraction_run`(+`_init`/`_timestep_init`) | Genuinely needs Fortran | calls `to_be_ccppized`'s `qsat`/`svp_ice_vect`; argmin-style scan for "most stable lapse rate below 750mb," not a simple recurrence |

**`hack_shallow`** (C4 only).

| Scheme/function | Bucket | Evidence |
|---|---|---|
| `set_general_conv_fluxes_to_shallow_run`, `set_shallow_conv_fluxes_to_general_run`, `convect_shallow_sum_to_deep_run` | Pointwise | pure array copy / per-level sum + per-column scalar index merge |
| `hack_convect_shallow_run`(+`_init`) | Genuinely needs Fortran | full shallow-convection plume model, calls `to_be_ccppized`'s `qsat`, restructured-from-`goto` control flow, explicit convergence tolerance |

**`tj2016`** (TJ).

| Scheme/function | Bucket | Evidence |
|---|---|---|
| `tj2016_precip_run` | Pointwise | closed-form per-(i,k) condensation, no subcycling -- **the single cleanest Phase D candidate found in this entire survey** |
| `tj2016_sfc_pbl_hs_run` | Column-scan | self-contained two-pass inline Thomas-algorithm implicit PBL diffusion solve (finding #3 above) |

**`mmm`** (unused by any suite here; two schemes wrap Fortran modules confirmed absent from the
whole repo -- finding #4).

| Scheme/function | Bucket | Evidence |
|---|---|---|
| `mmm_physics_compat_run`, `mmm_physics_accumulate_tendencies_*`, `mmm_physics_persist_states_*`, `compute_characteristic_grid_length_scale_init`, `geopotential_height_wrt_sfc_at_if_to_msl_run`(+`_to_msl_run`) | Pointwise | elementwise tendency accumulation/reset/copy, per level |
| `bl_gwdo_compat_run`(+`_init`/`_pre_run`), `cu_ntiedtke_compat_run`(+`_init`) | Genuinely needs Fortran, and moot | wraps `bl_gwdo`/`cu_ntiedtke` modules not present anywhere in this repo |

**`holtslag_boville`** (C4, C7) -- PBL scheme.

| Scheme/function | Bucket | Evidence |
|---|---|---|
| `hb_diff_exchange_coefficients_run`, `hb_diff_free_atm_exchange_coefficients_run`, `hb_diff_set_total_surface_stress_run`, `hb_diff_prepare_vertical_diffusion_inputs_run`(+`_free_atm_`/`_timestep_final`), `hb_pbl_independent_coefficients_run` | Pointwise | per-(i,k) from same-level/fixed-table inputs; one two-level *input* stencil (not a scan -- doesn't depend on this scheme's own prior output) |
| `hb_pbl_dependent_coefficients_run` | Column-scan | top-down PBL-top search with a per-column "found" latch -- same scan-with-latch family as `tropopause_find` below |

**`vertical_diffusion`** (C4, C7).

| Scheme/function | Bucket | Evidence |
|---|---|---|
| ~14 setup/bookkeeping schemes (TOA defaults, interface interpolation, sponge-layer damping, `diffusion_stubs.F90`'s temporary TMS/Beljaars stand-ins) | Pointwise | per-column/level arithmetic or two-level input stencils, no true recurrence |
| `vertical_diffusion_diffuse_horizontal_momentum_run`, `_diffuse_dry_static_energy_run`, `_diffuse_tracers_run` | Genuinely needs Fortran | each calls `to_be_ccppized`'s `fin_vol_solve`/`fin_vol_lu_decomp` -- an implicit tridiagonal solve coupling the whole column (finding #3) |

**`tropopause_find`** (C4, C7): `tropopause_find_run` -- **column-scan** (dispatches to ~6 internal
algorithms -- WMO, climate, hybrid-Stobie, cold-point, chemical -- each a per-column level-by-level
search with a running "found" latch and fallback chain).

**`rasch_kristjansson`** (C4 only) -- stratiform cloud microphysics.

| Scheme/function | Bucket | Evidence |
|---|---|---|
| `rk_stratiform_check_qtlcwat_run`, `_sedimentation_run`, `_detrain_convective_condensate_run`, `_external_forcings_run`, `_condensate_repartioning_run`, `_prognostic_cloud_water_tendencies_run`, `_save_qtlcwat_run` | Pointwise | per-(i,k) combination of already-computed rate terms, no recurrence |
| `cloud_particle_sedimentation_run` (+`getflx`/`cfint2`/`cfdotmc`) | Column-scan | cumulative top-down flux integral plus a per-column interval-search/cubic interpolation -- more sophisticated than `PF::calculate_z_int`, same team-per-column shape |
| `prognostic_cloud_water_run` (+`findmcnew`/`relhum_min_adj`) | Genuinely needs Fortran | bounded 2-pass iteration, nested column-scan, calls `wv_saturation`'s `findsp_vc` (iterative Newton solver) |
| `rk_stratiform_cloud_fraction_perturbation_run`, `_cloud_optical_properties_run` | Delegates elsewhere | thin wrappers around `compute_cloud_fraction_run` and `to_be_ccppized/cloud_optical_properties.F90`'s `cldefr` respectively |

**`zhang_mcfarlane`** (C4, C7) -- deep convection.

| Scheme/function | Bucket | Evidence |
|---|---|---|
| `save_ttend_from_convect_deep_timestep_init`(+`_run`), `set_deep_conv_fluxes_to_general_run`, `set_general_conv_fluxes_to_deep_run` | Pointwise | zero-fill/accumulate/copy, per level |
| `zm_convr_run` (+helpers), `zm_conv_convtran_run`, `zm_conv_momtran_run` | Genuinely needs Fortran + gather/scatter (finding #1) | `ideep`/`il1g:il2g` column-subset compaction before a buoyant-parcel/dilute-plume/closure solve or implicit-flux transport on the gathered subset |
| `zm_conv_evap_run` | Column-scan, pending | top-down Sundqvist-type accumulation, no gather/scatter -- but calls `wv_saturation`'s `qsat`, so the verdict depends on that module's own portability |

**`gravity_wave_drag`** (C4, C7) -- almost entirely non-portable; one shared engine.

| Scheme/function | Bucket | Evidence |
|---|---|---|
| `gravity_wave_drag_prepare_profiles_run` | Pointwise | fixed 2-point neighbor stencil, not a growing recurrence |
| `gravity_wave_drag_top_taper_init` | Column-scan | explicit backward recursion, init-only (fixed reference grid, no `_run`) |
| `gw_drag_prof` + every driver scheme (`_orographic_run`, `_ridge_beta_run`, `_ridge_gamma_run`, `_frontogenesis_run`(+`_inertial`), `_convection_deep_run`(+`_shallow`), `_moving_mountain_run`) | Genuinely needs Fortran | `gw_drag_prof`'s own docstring: "scan up from the wave source... scan down the stress profile" -- a two-pass scan per wave mode plus an implicit tridiagonal solve (`gw_ediff`/`gw_diff_tend`); every driver computes its own wave-source spectrum then calls it directly |

**`rrtmgp` + `radiation_utils`** (C4, C7) -- **special case (finding #2)**; do not apply standard
Phase D porting to this package.

| Category | Count | Examples |
|---|---|---|
| Pointwise pre/post-processing glue | ~8 | `rrtmgp_lw_calculate_heating_rate_run`, `calculate_net_heating_run`, `rrtmgp_dry_static_energy_tendency_run`, `rrtmgp_*_gas_optics_pre_run` |
| Administrative only, no radiative math | ~7 | `rrtmgp_subcycle_*`, `rrtmgp_variables_*` |
| Thin wrapper calling the external RTE+RRTMGP library | ~8 | `rrtmgp_lw_rte_run`/`_sw_rte_run` (call `rte_lw`/`rte_sw`), `rrtmgp_lw_gas_optics_run`/`_sw_gas_optics_run` |
| DDT-lifecycle/table-loading/RNG glue | ~11 | `rrtmgp_pre_run`, `rrtmgp_post_run`, `rrtmgp_*_gas_optics_init` (netCDF loads), `rrtmgp_*_mcica_subcol_gen_run` (stateful RNG), `rrtmgp_*_cloud_optics_run` |

**`musica`** (M, standalone suite) -- **special case (finding #2)**: `musica_ccpp_register`/`_init`/
`_run`/`_final` are genuinely-needs-Fortran but with **no Fortran math to actually port**
-- `musica_ccpp_run`'s body is just `tuvx_run(...)` then `micm_run(...)`, both delegating to opaque
solver objects (MICM's Rosenbrock/backward-Euler stiff-ODE solver; a TUV-x photolysis object) from
separately-built C/C++ libraries.

**`sima_diagnostics`** (every suite) -- verified uniform across all 26 real schemes (`*_diagnostics`
for check_energy, cloud/convection/diffusion/GWD/PBL/ZM/tropopause, plus `sima_state`/`sima_tend`/
`kessler_diagnostics`): all **structurally superseded**, pure `history_add_field`/`history_out_field`
calls with at most a trivial unit conversion first, never real physics. No exceptions.
`scheme_diagnostics_template.F90` is a copy-paste template, not a real scheme -- excluded.

#### Rollup

| Package | Pointwise | Column-scan | Structurally superseded | Genuinely needs Fortran | Special case |
|---|---|---|---|---|---|
| utilities | 13 | 0 | 1 (`geopotential_temp`) + `qneg` | 0 | -- |
| conservation_adjust | 2 | 1 | 3-4 (1-2 unconfirmed) | 1 (MPI) | -- |
| dry_adiabatic_adjust | 0 | 0 | 0 | 1 | -- |
| rayleigh_friction | 1 | 0 | 0 | 0 | unused by any suite |
| held_suarez | 1 | 0 | 0 | 0 | -- |
| cloud_fraction | 3 | 0 | 0 | 1 | -- |
| hack_shallow | 3 | 0 | 0 | 1 | -- |
| tj2016 | 1 | 1 | 0 | 0 | -- |
| mmm | 6 | 0 | 0 | 2 | unused; 2 wrap missing modules |
| holtslag_boville | 6 | 1 | 0 | 0 | -- |
| vertical_diffusion | ~14 | 0 | 0 | 3 | -- |
| tropopause_find | 0 | 1 | 0 | 0 | -- |
| rasch_kristjansson | 7 | 1 | 0 | 1 | 2 delegate elsewhere |
| zhang_mcfarlane | 3 | 0-1 | 0 | 3 | gather/scatter |
| gravity_wave_drag | 1 | 1 (init-only) | 0 | 8 | shared non-portable engine |
| rrtmgp | ~8 | 0 | 0 | 0 | ~26 external-library/administrative |
| musica | 0 | 0 | 0 | 4 | no Fortran math to port at all |
| sima_diagnostics | 0 | 0 | 25 | 0 | -- |

**What this changes about the plan:** roughly half of all ~190 schemes are trivially pointwise
bookkeeping/glue -- Kessler's own suite (23 schemes: ~13 pointwise, 1 superseded column-scan, 3
permanently non-portable regardless of supersession, only `kessler_run` itself a true "stays on the
Fortran bridge" case) is a representative sample. But the scientifically interesting packages
(`gravity_wave_drag`, `zhang_mcfarlane`, most of `rasch_kristjansson`/`vertical_diffusion`'s real
solvers) are dominated by genuinely-needs-Fortran, often for reasons Kessler never exhibited
(implicit solves delegated to a shared non-CCPP-ized library, or ZM's column gather/scatter). RRTMGP
and MUSICA fall outside the Phase D framing entirely -- their real numerics live in external
libraries this repo never owned in Fortran; the actionable next step there is investigating a direct
bridge to native C++ ports, not hand-porting. `tj2016_precip_run` is the best unclaimed Phase D pilot
in the repo -- simpler than any Kessler piece, real physics, zero subtlety.

### D.3 -- New emission mode: declaration-only, Kokkos-aware C++ headers

`cpp_interop.py`'s metadata-to-typed-parameter-list pipeline (`_chost_build_maps`,
`_chost_fn_contexts`, kind mapping, `ncol`/`nz` injection) is cleanly separable from "print an
`extern "C"` call chain" -- it produces `(name, type, intent)` tuples a different printer could
consume just as well; `print_cpp_header.py` confirms the IR side has zero Kokkos awareness today. A
new emission mode (`generate-cpp-device-decls`) would consume the same completed IR and print
`KOKKOS_INLINE_FUNCTION static <ret> <name>(<Pack-or-Real args>);` using D.1's shared view-type
header, gated by a new `cpp_native = pointwise | column_scan` metadata property (same shape as
Phase A's `variant`/Phase B's `gpu_pointer_mode`). A new printer roughly `print_cpp_header.py`'s
size, not new infrastructure.

The declaration is a **contract, not an implementation**: if a scheme's metadata changes on
regeneration, the declaration changes with it, and a stale hand-written body simply fails to
compile -- a free compile-time check that the hand-ported C++ kept up with the Fortran interface.

### D.4 -- The body is still a one-time human port, checked against the Fortran it replaces

A person writes the `KOKKOS_INLINE_FUNCTION` body once, exactly as already happened for
`PF::exner_function`/`TMSFunctions::compute_tms` -- not eliminated by D.3. "Port" means re-derive and
verify, not copy-paste, for schemes with a pre-existing hand-written analog (Category 1's finding).
Since the Fortran chost-cap path still exists and still runs the real scheme, it's a ready-made
oracle during migration: a small regression harness calling both the Fortran entry point and the new
native function on the same random inputs, before retiring the Fortran call site.

### D.5 -- Call-site integration is a bare line, never a generated loop

**Hard requirement (2026-08-25):** the generated `AtmosphereProcess` must never itself contain a
`Kokkos::parallel_for`/index loop. So every D.4 function is **whole-array** --
`TMSFunctions::compute_tms`'s shape (`compute_tms(ncols, nlevs, <views>...)`, one bare-line call,
caller manages no loop), never `PF::exner_function`'s per-point form. Since the function owns its own
internal loop (or team-scan, for a column-scan candidate), the call site is always one flat
statement regardless of how bespoke the surrounding `run_impl` is -- there's no per-point indexing
convention to match, because there's no per-point call at the call site at all. This is still
hand-wired, not auto-inserted (no shared "the" preprocessing loop exists across processes to splice
into), but it's a **one-line substitution using a generator-checked, always-current signature**
instead of the full `params_helpers`/transpose/`ATMBufferManager` apparatus.

### Drafted artifacts (2026-08-25)

All draft/exploratory, none wired into the real `xdsl_ccpp` package or an EAMxx build:

| File | Purpose |
|---|---|
| `draft_xdsl_ccpp_backend/print_cpp_device_decls.py` | D.3's printer -- emits whole-array, declaration-only signatures for `cpp_native`-tagged schemes. Documents (without making) 4 real-repo edit points, including a genuine pre-existing gap found while writing it: `transforms/util/ccpp_descriptors.py`'s allow-list is missing `array_layout` entirely. |
| `draft_xdsl_ccpp_backend/cpp_native_candidates.meta` | Proposed `cpp_native` property for every pointwise/column-scan scheme above (~55 schemes, 15 packages), confidence-tagged. Documents a real limitation: `vertical_diffusion_diffuse_horizontal_momentum`/`_diffuse_tracers` have lifecycle phases that disagree on portability, which per-scheme granularity can't express -- both excluded rather than mistagged. |
| `draft_eamxx_files/eamxx_ccpp_view_types.hpp`, `utilities_ccpp_native.hpp`, `conservation_adjust_ccpp_native.hpp`, `kessler_ccpp_native.hpp` | D.4 device-function headers. The latter three split shared-utility vs. package-specific scope, since most of what Kessler's suite needs beyond `kessler_update` is generic and reused by `cam4`/`cam7`/`adiabatic`/`tj2016` too. `utilities_ccpp_native.hpp`'s `compute_geopotential_temp` has a real body (extracted verbatim from `eamxx_kessler_process_interface.cpp` lines 276-288's `PF::calculate_z_int`/`calculate_z_mid` team-scan), unlike every other function here -- included for reuse even though it's confirmed superseded and no *generated* call site will ever invoke it. |
| `draft_eamxx_files/eamxx_xdsl_process_interface.{hpp,cpp}` | D.5's process-interface skeleton, showing the bare-line whole-array call convention. |
| `draft_eamxx_files/D4_D5_outline.md` | Structural outline (file names + confidence-tagged best-effort signatures) for the remaining 12 packages, where argument lists weren't verified against full source. Documents a cross-package pattern: several CCPP schemes reduce to the same device function (e.g. one `convert_wet_to_dry_mixing_ratio` replaces 4 near-identical schemes) -- a real D.3 generator would need to recognize and consolidate these, or accept over-generation and consolidate by hand afterward. |

---

## Recommended order

**Phase A0 -- done (2026-08-25)**, unblocking everything below (regenerated against current `main`,
fixed `initialize_impl`/`finalize_impl`/`run_impl`'s call sites, re-baselined `kessler-README.md`);
not yet compiled against a real EAMxx build, and a compile-only smoke test for the Kessler bridge is
now a similarly cheap, high-value addition as the suite-coverage checker below, given Phase A0 found
drift that manual signature review would have needed to catch by hand every single time. **Next,
together:** Phase A + Phase B (same allow-list, same extension point), D.1 + D.2 (view-type
consolidation and the per-scheme triage -- cheap, no generator changes, D.2 literally extends the
suite-coverage checker), and the suite-coverage checker itself.
**Then D.3** (the declaration-only printer), comparable in size/risk to Phase A's `#ifdef` work.
**D.4/D.5 run continuously** per-scheme from as soon as D.2 has a candidate, independent of Phase
B/C's schedules -- recurring human effort, not one-time generator work.

Phase C (the full `AtmosphereProcess` printer) is the largest ask, an order of magnitude more effort
than anything else here, and even fully built would still leave hand-written code behind: the
QA-check bounds and energy-fixer bookkeeping permanently, and (for whatever Phase D doesn't end up
covering) the Category 1 preprocessing kernels by deliberate performance choice. Phase D is a
*complement* to Phase C, not a replacement -- it shrinks Phase C's costliest piece (buffer
management/transpose glue) for schemes simple enough to qualify, while Phase C's own remaining scope
(field/tracer classification, lifecycle wiring) is unaffected. "Automatically generate all of the
code" is realistically achievable for the bridge/cap layer and the lifecycle-orchestration skeleton,
but not for the entire file.
