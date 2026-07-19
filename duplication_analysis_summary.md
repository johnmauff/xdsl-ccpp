# Code Duplication Analysis: NCAR/atmospheric_physics

**Repo analyzed:** local clone of `NCAR/atmospheric_physics` (companion to `ccpp-framework`), HEAD `b45efc1`, clean working tree.
**Scope:** Fortran source (`schemes/`, `phys_utils/`, `to_be_ccppized/`), CCPP metadata (`.meta`), and suite-definition files (SDF, `suites/*.xml`, `test/test_suites/*.xml`).

## Executive summary

Three layers were analyzed for duplication. They differ enormously in both proportion and root cause:

| Layer | Total | Duplicated | Percentage |
|---|---|---|---|
| Fortran source (`.F90`) | 45,399 lines | 651 lines | **1.4%** |
| CCPP metadata (`.meta`) | 23,862 lines | 607 lines (intra-`.meta` clones only) | **2.5%** |
| Suite definitions (SDF XML) | 619 scheme-call entries (1,364 total XML lines, 23 files) | 280 entries | **45.2%** |

But the more consequential finding isn't intra-`.meta` duplication — it's that **most of `.meta`'s content duplicates the adjacent Fortran source itself**, a different and much larger problem than any of the above (see §4).

Of three proposed interventions, ranked by code volume eliminable:

| Intervention | Layer targeted | Volume eliminable |
|---|---|---|
| Eliminate `.meta` as a hand-maintained shadow file (generate it from annotated Fortran) | Fortran ↔ metadata redundancy | **~14,300+ lines** |
| Python suite-composition DSL (replace XML SDF) | SDF | ~280 lines |
| `scheme_family` code generator (symbolic-tracing templating) | Fortran | ~320-360 lines |

---

## 1. Fortran-layer duplication

**Method:** type-2 clone detection — subroutine/function bodies compared after canonicalizing every identifier by order-of-first-appearance, so renamed-but-structurally-identical code is caught (e.g. `qv` vs `qc` vs `qr`).

**Result:** 27 clone families, 66 member subroutines, 651 duplicated lines out of 45,399 (1.4%).

Of these, 17 families (539 of the 651 lines) were individually verified by reading source, confirming genuine "same formula, different named quantity" duplication:

- `wet_to_dry_{water_vapor,cloud_liquid_water,cloud_ice,rain}` / `dry_to_wet_{...}` (`schemes/utilities/state_converters.F90`) — 8 subroutines, one multiply/divide by `pdel`/`pdeldry` each. **132 lines.**
- `apply_tendency_of_{eastward_wind,northward_wind,air_temperature}` (`schemes/utilities/physics_tendency_updaters.F90`) — identical 3-statement update pattern. **50 lines.**
- Saturation-vapor-pressure dispatch family (`to_be_ccppized/wv_sat_methods.F90`, `wv_saturation.F90`) — `qsat_{water,ice,trans}`, `svp_{water,ice}` dispatchers, and pure forwarding wrappers. **~221 lines.**
- MUSICA TUV-x profile/radiator builders — `create_{dry_air,O2,O3}_profile`, `create_{aerosol,cloud}_optics_radiator`. **73 lines.**
- Misc. small pairs: `set_{shallow,deep}_conv_fluxes_to_general` (11), `geopotential_height_wrt_sfc_{at_if_,}to_msl_run` (24), `gravity_wave_drag_ridge_{beta,gamma}_init` (23), `to_lower`/`to_upper` (21), `linear_1d_operators.F90` derivative/tridiag wrappers (22).

**One important negative result:** `GoffGratch_svp_water` vs. `GoffGratch_svp_ice` initially looked like the same family (same naming convention, similar "flavor") but turned out on inspection to be genuinely different empirical correlations — different number of terms, different reference constants (`tboil` vs. `h2otrip`), not a renamed copy. The clone scanner correctly did not flag these. This is the boundary of the technique: it collapses duplicated formulas, not merely similar-looking ones.

**Why it exists at all:** CCPP's argument binding is nominal (string-matched by `standard_name`), so a scheme can't be generic over a family of standard names — each physically distinct quantity needs its own named subroutine, even when the logic is identical.

**Estimated achievable savings:** splitting by whether CCPP forces a distinct named entry point per instance:
- CCPP-scheme-bound families (240 lines: wet/dry converters, tendency updaters, flux/geopotential/init pairs) — need to keep N named entry points, so only "thin wrapper + shared core" is possible → **~45-50% savings, ~110-120 lines.**
- Internal (non-CCPP) helper families (299 lines: SVP dispatch, MUSICA builders, `linear_1d_operators` wrappers) — no naming constraint, can collapse much further, some (the pure forwarding wrappers) almost entirely → **~70-80% savings, ~210-240 lines.**
- **Total: ~320-360 lines**, under 1% of the Fortran codebase.

**Mechanism proposed (not implemented):** symbolic tracing, the same technique behind SymPy's Fortran code-printer. A Python `formula=lambda q, pdel, pdeldry: q * (pdel / pdeldry)` is called once with placeholder objects that overload `+ - * /` to build an expression tree instead of computing a value; a printer walks the tree and emits Fortran array syntax. Works cleanly for every confirmed family above (all straight-line arithmetic, no branching); does not and should not apply to schemes with real control flow (`kessler`'s microphysics, `qneg`'s clipping, iterative solvers) — those aren't "one formula, renamed" duplicates in the first place.

---

## 2. SDF (suite XML)-layer duplication

**Method:** each suite's scheme-call sequence treated as an ordered token stream; greedy longest-match-first search for contiguous blocks (length ≥ 2) that recur identically across 2+ files.

**Result:** 24 repeated cross-file blocks, 280 of 619 total scheme-call entries (45.2%) sit inside a block duplicated verbatim elsewhere.

**Headline finding:** `suite_cam4.xml` and `suite_cam7.xml` are largely concatenations of the standalone single-process test suites:

| Monolithic-suite block | Duplicated verbatim in | Length |
|---|---|---|
| Rasch-Kristjansson stratiform cloud | `suite_rasch_kristjansson.xml` | 38 schemes |
| RRTMGP radiation | `suite_rrtmgp.xml` | 38 schemes |
| Holtslag-Boville vertical diffusion | `suite_vdiff_holtslag_boville.xml` | 31 schemes |
| Zhang-McFarlane convection | `suite_zhang_mcfarlane.xml` | 28 schemes |
| Shallow convection | `suite_convect_shallow_hack.xml` | 17 schemes |
| Gravity wave drag | `suite_gw_cam4.xml` | 16 schemes |

91% of `suite_cam4.xml` (183/201 entries) is reconstructible from these 6 other files — each maintained as a fully independent copy.

Second tier: the `wet_to_dry_*`/`kessler`/`dry_to_wet_*` bracket (14 schemes) is duplicated verbatim between `suite_kessler.xml` and `suite_kessler_test.xml`.

Third tier: small idiomatic 2-5 scheme pairs reused across otherwise-unrelated suites — `check_energy_scaling→check_energy_chng` (5 files), `sima_state_diagnostics→sima_tend_diagnostics` (5 files), `qneg→geopotential_temp` (4 files), `tropopause_find→tropopause_diagnostics` (3 files), and a full 5-scheme closing tail (`thermo_water_update→check_energy_scaling→dycore_energy_consistency_adjust→apply_tendency_of_air_temperature→sima_tend_diagnostics`) shared identically by `suite_cam7.xml`, `suite_kessler.xml`, and `suite_tj2016.xml`.

**Crossed-bracket structural finding:** within `suite_kessler.xml`, two conceptual "wrap" operations around the `kessler` scheme —
- a *theta basis* bracket: `temp_to_potential_temp` ... `potential_temp_to_temp`
- a *dry basis* bracket: `wet_to_dry_{water_vapor,cloud_liquid_water,rain}` ... `dry_to_wet_{...}`

— interleave in a way that is **not properly nested** (theta opens first but also closes first, a crossed interval). An automated bracket-pair scan across all 23 suite files found this pattern recurs in exactly one other place: `suite_convection_permitting.xml`, where three tracer conversions (water_vapor, cloud_liquid_water, cloud_ice) bracket a much larger 18-scheme MMM-physics block, opening and closing in matching *forward* order rather than LIFO — i.e. independent resources, not a stack discipline. Two other candidate bracket types (`check_energy_zero_fluxes`/`check_energy_chng`, `rrtmgp_pre`/`rrtmgp_post`) showed **zero** crossings anywhere in the corpus — those are always cleanly nestable.

**Correctness check:** verified (by reading each scheme's declared `intent`/`standard_name` arguments) that the theta and dry-basis conversions around `kessler` touch completely disjoint variable sets, so their relative ordering has no effect on the computed result — reordering to a properly-nested form is safe, just not byte-identical to the original hand-written file. Worth noting: CCPP performs no dependency-based reordering of its own; it executes the SDF list exactly as given, so this safety was never verified by the framework in the first place, only implicitly by whoever wrote the file.

**Proposed alternative — a Python suite-composition DSL:**
```python
with suite.group("physics_before_coupler") as g:
    g.add("calc_exner")
    with theta_basis(g):
        g.add("calc_dry_air_ideal_gas_density")
        with dry_basis(g, TRACERS):
            g.add("kessler")
    g.add("kessler_update")
    ...
```
`dry_basis`/`theta_basis` are combinators that auto-insert the conversion bracket around a block, parameterized by a tracer list — collapsing the copy-pasted XML bracket into one reusable call. (Full worked example saved as `suite_kessler_example.py` in this directory.)

**Which pieces are actually reusable, checked against real data:**
- `theta_basis` — narrowly reusable: a true open+close pair exists only in `suite_kessler.xml`/`suite_kessler_test.xml` (the same suite, forked for testing). `suite_convection_permitting.xml` calls `temp_to_potential_temp` once with no matching close, so it isn't really using this bracket at all.
- `dry_basis` — genuinely reusable with a parameter: two distinct tracer lists across two suite families (`[water_vapor, cloud_liquid_water, rain]` for kessler; `[water_vapor, cloud_liquid_water, cloud_ice]` for convection_permitting).
- Bigger payoff than either: `energy_budget` (8 files, zero crossings, safe to factor out), `rrtmgp_radiation` (2 files), and named per-process pipeline functions for the 6 cam4/cam7 blocks above — these account for most of the 45% SDF duplication.

**Estimated savings:** ~280 lines directly, but the more important benefit is eliminating the *risk* that `cam4`'s embedded copy of, e.g., the Rasch-Kristjansson pipeline drifts from the standalone test suite's copy — a correctness/maintenance risk that raw line count understates.

---

## 3. CCPP metadata (`.meta`)-layer duplication

Not initially in scope — added after being asked directly whether `.meta` files had been checked (they hadn't).

**Method:** same clone-detection approach adapted to `.meta`'s INI-like block structure (`[ccpp-table-properties]`, `[ccpp-arg-table]`, per-variable `[ varname ]` sections).

**First pass (exact match): only 237 of 23,862 lines (1.0%)** — surprisingly low, and traced to a real bug-and-finding combination: `wet_to_dry_water_vapor.meta`'s `qv` variable is missing a `long_name` field that the sibling `qc`/`qi`/`qr` blocks all have. That's a genuine small inconsistency in the repo, and it also broke exact-match comparison (one incidental optional-field difference made otherwise-identical blocks look "different").

**After normalizing away that purely-documentary field: 607 duplicated lines (2.5%)** — and the families that appear track almost exactly onto the CCPP-scheme-bound Fortran families (`wet_to_dry_*`/`dry_to_wet_*` alone account for 370 of the 607 lines), plus two `.meta`-only matches (`rrtmgp_{lw,sw}_calculate_heating_rate`, `convect_shallow_diagnostics`/`rk_stratiform_diagnostics`).

---

## 4. The bigger question: how much of `.meta` duplicates the Fortran itself?

This turned out to matter more than intra-`.meta` duplication. Field-by-field classification across all ~3,596 variable-argument blocks in the corpus:

| Category | Fields | Lines | % of `.meta` |
|---|---|---|---|
| Fully derivable from Fortran | variable-name header, `type`, `intent` | 10,788 | 45.2% |
| Mixed | `dimensions` (rank derivable; which standard-named quantity each axis represents is not) | 3,596 | 15.1% |
| Must be human-supplied, load-bearing | `standard_name`, `units` | 7,192 | 30.1% |
| Optional, human-added, sparse | `long_name` (present in only ~7.7% of blocks), `advected`, `persistence` | 302 | 1.3% |
| Structural boilerplate | table headers, separators, blank lines | 1,984 | 8.3% |

So **roughly 45% of every `.meta` file is a mechanical mirror of the Fortran signature** (type, intent, argument name), **~15% is half-mechanical** (dimension count, but not meaning), and **~30% (`standard_name`/`units`) is genuinely irreducible information that cannot be derived from Fortran at all** — this is the actual reason `.meta` exists, since CCPP's cross-scheme wiring depends entirely on `standard_name` matching. This matches the repo's own tooling instructions (`scheme_diagnostics_template.F90`): run `ccpp_fortran_to_metadata.py` to get the skeleton, then "complete the metadata (fill out standard names, units, dimensions)" by hand.

### Proposed intervention: put `standard_name`/`units` in the Fortran source itself

Rather than accepting `.meta` as a permanently separate, hand-synchronized file, embed the non-derivable fields directly at the declaration site via a structured comment:

```fortran
real(kind_phys), intent(in) :: qv(:,:)  !! standard_name=water_vapor_mixing_ratio_wrt_moist_air_and_condensed_water units=kg kg-1
```

This is not a foreign idea for this codebase — it already does the equivalent twice: the `!> \section arg_table_X_run` Doxygen-style markers, and the pervasive `!$acc parallel loop collapse(2)` OpenACC directives throughout `kessler.F90`, `kessler_update.F90`, `wv_sat_methods.F90`. Both are "semantic information a bare type signature can't express, embedded in a structured comment co-located with the code it describes." `standard_name`/`units` would be a third instance of the same house style.

**Practically achievable without changing CCPP itself:** `capgen` only ever consumes `.meta` as a file, indifferent to its provenance. A local pre-build step (extending the already-referenced `ccpp_fortran_to_metadata.py`) could parse the annotated Fortran and mechanically emit `.meta` in full — turning it from hand-maintained source into a generated build artifact that can never drift from the declarations it describes, eliminating exactly the class of bug found in §3 (the missing `qv` `long_name`) by construction.

**Caveats:** a few things aren't naturally per-argument-line (table-level scheme name, cross-references to other schemes' declared dimension standard-names) and need a modest annotation-scheme extension beyond one tag per line; and this fixes the *two-sources-of-truth* problem, not the *N-named-entry-points-per-family* problem from §1 — the two ideas compose (a `scheme_family` generator could emit annotated Fortran per tracer, and this extraction step turns that into `.meta` "for free," with zero un-derivable residue left).

### Magnitude comparison

| Intervention | Lines eliminable | What kind of win |
|---|---|---|
| `scheme_family` generator (§1) | ~320-360 | Deduplicating copies of a formula *within* Fortran |
| Python SDF DSL (§2) | ~280 | Deduplicating copies of a scheme sequence *within* XML |
| Eliminate `.meta` as hand-maintained shadow file (§4) | **~14,300+** (the derivable+mixed 60.3% of 23,862 lines that would no longer need separate authorship, review, or sync) | Eliminating an entire *second representation* of information that already exists elsewhere |

The third is not just larger, it's a different category of fix — the first two remove redundant copies of the same kind of artifact; the third removes the need for an entire redundant artifact format to exist as hand-written source at all. It is also the one requiring the most new tooling investment (an annotation parser and a pre-`capgen` generation step), versus the other two, which are purely local Python authoring-layer changes with no build-pipeline impact.

---

## 5. Effort assessment: eliminating the `.meta` shadow file

This section evaluates how hard the §4 proposal (embed `standard_name`/`units` in the Fortran source and generate `.meta` mechanically) would actually be to build, grounded in a review of the real source of [`johnmauff/xdsl-ccpp`](https://github.com/johnmauff/xdsl-ccpp) — an experimental MLIR/xDSL-based alternative to `ccpp_capgen` under active development — rather than assessed in the abstract.

**Most of the required architecture already exists:**

- **Two independent "derive from Fortran" extractors are already implemented** — `fparser2_to_meta.py` (pure-Python parse) and `fir_to_meta.py` (via Flang/HLFIR compilation) — and both docstrings independently state the exact same gap this analysis derived from `atmospheric_physics` data: *"Information NOT available from Fortran source text: `standard_name`/`long_name`, `units`, kind name."* This is convergent validation of the §4 field-derivability split from a completely independent source.
- **`ccpp_generate_meta.py` already generates stub `.meta` skeletons** from either extractor, filling unresolvable fields with placeholders (`std_name_001`, `enter_units`) — matching the existing `ccpp_fortran_to_metadata.py` workflow, i.e. "generate skeleton, then hand-edit," not yet closing the loop.
- **The IR already has zero-cost room for the missing fields.** `ArgumentOp` in `xdsl_ccpp/dialects/ccpp.py` already declares `standard_name`, `units`, `long_name`, `dim_names` as first-class optional properties, currently populated from the XML/`.meta` frontend or the Python `py_api` inline-authoring mode. The `.meta`-text writer (`meta_from_module`) already prints these generically from whatever's on the op. **Adding a third way to populate the same properties — from a parsed Fortran comment — requires no dialect change and no writer change**, only a change to the extraction step.
- **A Python suite-authoring frontend already exists** (`xdsl_ccpp.frontend.py_api`, `@ccpp_suite`/`@ccpp_scheme`/`forLoop`), independently arriving at the same "suites should be composable Python, not XML" idea proposed in §2 — though without a `dry_basis`/`theta_basis`-style auto-bracketing combinator yet.

**The hard technical fork:** annotation-based generation can only ever work through the `fparser2` path, never the Flang/FIR path. Once Flang compiles source to FIR/HLFIR, comments are gone — `fir_to_meta.py` reads compiler IR that never retained them. So this only ever extends `fparser2_to_meta.py`; the compiler-validated route stays `.meta`-consuming, not `.meta`-producing, for this purpose.

### Resolved: how `fparser2` actually handles the annotation

Tested directly against the installed `fparser2` library rather than assessed from documentation. **Comments are fully stripped from the parse tree** — confirmed empirically: parsing a subroutine with `!! standard_name=... units=...` comments (trailing or standalone) through `f03.Program(reader)`, the exact API `fparser2_to_meta.py` already uses, produces zero `Comment` nodes anywhere near the declarations.

However, every parsed `Type_Declaration_Stmt` carries `.item.span` (the exact 1-indexed source line range the statement occupies) and `.item.line` (the statement text with the comment already removed). That's enough for a reliable recovery path: split the original source into lines once, index into the statement's line span, and regex for `!` onward on that raw line. Demonstrated end-to-end on a real 149-character standard name:

```
Parsed OK: REAL, INTENT(IN) :: qv_tend(:, :)
item.span: (4, 4)
item.line (comment stripped by fparser2): real, intent(in) :: qv_tend(:,:)
Recovered comment via raw-line cross-reference:
  !! standard_name=tendency_of_water_vapor_mixing_ratio_wrt_moist_air_and_condensed_water_from_cloud_condensation_minus_precipitation_evaporation_due_to_deep_convection units=kg kg-1 s-1
Recovered standard_name matches original: True
```

fparser2 parsed the 222-character source line with zero errors — no truncation, no failure. **This resolves the earlier "one real unknown" and downgrades it from a medium-risk spike to a small, well-defined implementation task** with a working technique already demonstrated. No `fparser2` patching or lower-level tokenizer access is needed.

### Resolved: the line-length concern, checked against the real corpus

Pulled the actual `standard_name` length distribution across all 3,596 variable blocks in `atmospheric_physics`:

| Threshold | Count exceeding | % |
|---|---|---|
| > 60 chars | 1,363 | 37.9% |
| > 80 chars | 590 | 16.4% |
| > 100 chars | 224 | 6.2% |
| > 132 chars (traditional Fortran free-form limit) | 27 | 0.8% |

Median is 53 characters, max is 167. `units` values are short and negligible (median 15, max 31 chars). So the risk is real but narrow — under 1% of variables would push a trailing-comment line past 132 characters from the standard name alone.

More importantly: **this isn't a new problem the proposal introduces.** The current `.meta` file already contains an unwrapped ~186-character line for that same worst-case name, sitting in the repo today without remark, because plain-text `.meta` was never subject to any line-length convention. What's new is only that Fortran source is traditionally held to a stricter one — so the proposal relocates an existing "some names are long" reality rather than creating it.

### Refined design: name-tagged annotation block, not trailing-per-line comments

The original sketch (a `!!` comment trailing each declaration) has a real weakness: matching by line adjacency is fragile to reordering — if declarations get rearranged and a comment doesn't move with its declaration, the association silently breaks. A better design tags each annotation with the variable's local name explicitly and matches by name instead of position:

```fortran
subroutine wet_to_dry_water_vapor_run(ncol, nz, pdel, pdeldry, qv, qv_dry, errmsg, errflg)
  !ccpp [qv] standard_name=water_vapor_mixing_ratio_wrt_moist_air_and_condensed_water units=kg kg-1
  !ccpp [qv_dry] standard_name=water_vapor_mixing_ratio_wrt_dry_air units=kg kg-1
  integer, intent(in) :: ncol
  ...
```

This is deliberately close to `.meta`'s existing `[ qv ]` bracket-header syntax, just prefixed with a comment marker and relocated into the `.F90` file — minimal new grammar to design or teach. Advantages over the trailing-per-line version:

- **Immune to reordering.** Matching is "does this tag's bracketed name match a real dummy argument," not "is this comment adjacent to the right line" — declarations can be reordered freely with no risk of silent misattribution.
- **Groups cleanly into one block**, close to today's `.meta` right after the `subroutine` header, rather than being scattered one-per-declaration-line — better readability, and it further defuses the line-length concern since the block's lines never sit next to or compete with code.
- **Simpler to implement, not harder.** Matching only needs to be *subroutine*-scoped, not *line*-scoped: use `fparser2`'s `Subroutine_Subprogram` span to find all `!ccpp [name]` tags anywhere within that range, then join by name. This is coarser-grained than the line-span technique already demonstrated above, so it composes directly with it while requiring less bookkeeping.
- **Enables a hard validation check that doesn't exist today**: the extraction tool can error if a `!ccpp [name]` tag doesn't match any actual dummy argument, or if an argument has no matching tag — a build-time consistency guarantee current `.meta` never had. Today, Fortran and `.meta` can silently drift (as found with `qv`'s missing `long_name` in §3) with nothing catching it.
- **One small thing reintroduced, worth being explicit about:** the local name is now spelled twice — once in the declaration, once in the tag's bracket — so it can itself go stale if a variable is renamed without updating its tag. This is a much narrower risk than today's, where five fields (type, intent, dimensions, standard_name, units) can each independently drift; here only the name-as-join-key can drift, and the hard-error check above turns that into a build failure rather than a silent gap.

### Bonus finding: `memory_space` is likely derivable too — from existing GPU directives, not a new annotation

`xdsl-ccpp`'s `ArgumentOp` also carries a `memory_space` property (`"host"`/`"device"`/`"unified"`), added to drive GPU data-movement directive generation. Unlike `standard_name`/`units`, this is a *mechanical/data-placement* property, not a *physical-meaning* one — much closer in kind to `intent`, which is already fully derivable. That makes it a fundamentally better candidate for derivation, and this codebase already shows the right kind of evidence.

`schemes/kessler/kessler_update.F90` has a currently-disabled macro:
```fortran
!#define DEVICEPTR(...) deviceptr(__VA_ARGS__)
#define DEVICEPTR(...)
```
whose clear intent, once enabled, is to expand into an OpenACC clause naming exactly which arguments the kernel expects as device pointers — e.g. `!$acc parallel loop collapse(2) deviceptr(theta, exner, temp_prev, ttend_t)`. That's a per-variable, machine-parseable assertion of device residency sitting in the compute directive itself.

Tested whether this is recoverable using the same subroutine-span cross-referencing technique already demonstrated for `!ccpp` tags (fparser2 strips `!$acc` sentinel comments too, confirmed empirically — same as any other comment). Scanning `kessler_update_run`'s line span for `!$acc ... deviceptr(...)` and matching names recovered exactly the right set with no new annotation grammar at all:
```
subroutine kessler_update_run: span=(3, 23)
  device-resident (deviceptr) vars found: {'theta', 'ttend_t', 'temp_prev', 'exner'}
```

**Where this goes architecturally:** not into the `!ccpp [name] key=value` block alongside `standard_name`/`units` — it would be a separate, fourth extraction pass (parallel to the type/intent/rank extractor and the `!ccpp`-tag extractor) that scans for `!$acc`/`!$omp` directives within a subroutine's span and feeds the result into the same, already-existing `ArgumentOp.memory_space` property. Same target, same merge point, different source.

**Caveats:** (1) this only gives a signal for variables a scheme's directives *already* name explicitly — an unported subroutine gives nothing, and would need to fall back to an explicit `!ccpp` tag or a project-wide default; (2) absence of a clause doesn't reliably mean "host," since some OpenACC/OpenMP code relies on an outer `!$acc data` region or compiler defaults rather than per-call clauses, so the signal is only as strong as the scheme's own discipline about writing explicit clauses; (3) the dialect already separates this from `model_var_memory_space` ("memory space declared by the host model") — only the scheme-side `memory_space` is derivable from the scheme's own Fortran; the host-side fact would still need to come from the host's own metadata.

**Staged effort:**

| Phase | Work | Size |
|---|---|---|
| 0. Design | Finalize the `!ccpp [name] key=value ...` grammar; decide how table-level scheme name and cross-scheme dimension standard-names (not local to one line) get expressed | Small — days |
| 1. Extend `fparser2_to_meta.py` | Use `Subroutine_Subprogram` span to collect `!ccpp` tags per subroutine, join by bracketed name against the already-extracted declaration dict, merge into the same `attrs` structure that already feeds `type`/`intent`/`rank`; wire `ccpp_generate_meta.py` to use real values instead of stubs when present, and hard-error on unmatched tags/arguments | Moderate — well-isolated, no IR changes needed, and the core recovery technique is already demonstrated working |
| 2. Add a `memory_space` extraction pass | Scan each subroutine's span for `!$acc`/`!$omp` device/data clauses (`deviceptr`, `present`, `copyin`/`copyout`), populate `ArgumentOp.memory_space` directly — independent of the `!ccpp` tag mechanism, reusing the same span-based recovery technique | Small — narrow, well-isolated, technique already demonstrated working |
| 3. Migrate `atmospheric_physics` | Backfill ~3,596 existing variable declarations across ~126 `.meta` files as `!ccpp` blocks — a scripted job, not re-authoring, since the `standard_name`/`units` values already exist in the checked-in `.meta` today; a one-time tool matches each `.meta` block to its Fortran subroutine by name, inserts the tagged block, then round-trips through the new generator to diff against the original for verification | Moderate, mostly automated, human review only on mismatches (like the `qv`/`long_name` gap found in §3) |
| 4. CI wiring | Regenerate `.meta` as a build step; check it matches the committed copy (standard generated-artifact CI pattern) | Small |

**A framing point that lowers perceived risk:** this doesn't require the repo to stop *committing* `.meta`, and it doesn't require any change to production `ccpp-framework`/`capgen` at all — a generated `.meta` file is still a completely valid `.meta` file. What changes is that humans stop *hand-editing* it; annotated Fortran becomes the source of truth, and `.meta` becomes a build artifact that also happens to be checked in for the benefit of tools that only know how to read `.meta`. That makes this adoptable incrementally, without coordinating a change to the production toolchain.

**Overall verdict:** given how much of the surrounding plumbing (IR schema, `.meta` writer, module-grouping convention, entry-point-suffix filtering) already exists and already generalizes cleanly to this, and given that the two open risks (comment retrievability, line length) are now both resolved with working techniques and real corpus data rather than open questions, this looks like a small-to-moderate effort — on the order of a couple of focused weeks for the tooling change plus the one-time migration script — with no remaining architecturally risky unknowns. The irreducible 30% (`standard_name`/`units` content itself) was never going to get easier to *author*; what this buys is making it impossible for that content to *drift* from the Fortran it describes, and with the name-tagged design, making any remaining drift a loud build failure rather than a silent gap — which was the actual problem this analysis was chasing, not the authoring effort itself. `memory_space` turning out to be plausibly derivable from existing (if currently dormant) GPU directives is a bonus: it suggests the "genuinely irreducible" fraction of `.meta` may be smaller than the §4 field-derivability table implies once fields like this are examined individually rather than assumed to all be equally human-only.

---

## Files produced during this analysis

- `suite_kessler_example.py` — worked Python SDF DSL sketch for `suite_kessler.xml`, corrected for the `kessler`/`kessler_update` adjacency and crossed-bracket issues discussed in §2.
- Clone-detection scripts (Fortran, SDF-block, `.meta`) were run from scratch space and are not preserved in this directory, but all reported numbers are reproducible from the methods described above.
