# Current Plan: `ccpp_cap.py` Refactor Backlog

Open items only. For the full narrative behind any item (why, how, what was
tried), see the `L<n>` pointer into `CHANGELOG.md` (line
numbers as of the split, 2026-09-29 — will drift as that file is edited; if
a number looks wrong, search for the quoted lead-in text instead, same
convention the archive's own Index already uses). Historical/completed
work — the full six-phase decomposition, Phase 7, every ✅ backlog item, and
the codebase complexity/duplication audit — lives only in the archive now.

**When an item resolves**, move it out of its open-items table/section into
a one-line "Resolved since last verification (`<date>`)" note (see the
examples throughout this file, e.g. `task70-arraysection`/`task71-validate-fir`):
what was done, in a single sentence, plus a `CHANGELOG.md L<n>` pointer.
Do **not** restate the problem, the fix mechanism, bug-by-bug detail, or
test-count verification in that note — all of that belongs in the
`CHANGELOG.md` entry only, which can be as thorough as needed. This file
is a scan of remaining/recently-closed work, not a changelog recap.

Every item below carries a stable ID (a short kebab-case slug in
backticks, e.g. `` `hle-vocab-retire` ``, not a plain integer — integers
were found to reshuffle depending on how the list gets presented/derived).
Where an item already had an established numeric identity elsewhere in the
repo/history (`Task #NN`, `TDB-NNN`), the slug incorporates it (e.g.
`task70-arraysection`). Use these IDs, not position in the list, when
referring to an item across sessions.

**`CPP_BACKLOG.md`** is a priority-ordered subset of this file, filtered
and reordered around the multi-language (C++) support goal specifically —
same stable IDs, kept manually in sync with this file. Check it when
deciding what C++/multi-language work to pick up next; keep both files in
sync when an item on it changes here.

Two corrections found while building this list, where the archive's own
Index table (last updated 2026-08-24) had gone stale relative to its own
later narrative entries:

- **Tier 3 of the complexity/duplication audit (tasks #56-#60,
  `suite_cap.py`/`run_dispatch.py` structural decomposition)** was still
  marked "backlog" in the Index, but all five tasks are in fact RESOLVED
  (archive L6276-L6462, dated 2026-08-19/20). Not carried forward here.
- **Task #65 (broader allocation-dependency model)** was marked a plain
  "📋 Backlog" item in the Index, but its own later re-scoping entry (archive
  L5326-L5350, "honest downgrade after checking each of the 4 items...
  against the current, post-#56/#57 code") found the epic doesn't hold up:
  2 of its 4 sub-items are small, no-design-needed test-coverage tasks; the
  other 2 are deferred indefinitely with no open action. Carried forward
  below in that narrower, corrected form.

## capgen-v1 end-to-end-test capability gaps

| ID | Item | Notes | Archive |
|---|---|---|---|
| `cmake-dep-manifest` | Metadata dependency-manifest automation for CMake (Tier 2 of dependency tracking — Tier 1 parse/IR-forward is done) | Size TBD, needs its own design pass; overlaps with the CMake-configure-time item below | L5465 |
| `hle-vocab-retire` | Retire the legacy `horizontal_loop_extent` vocabulary — actual code-path deletion | **Re-scoped 2026-09-29: deferred indefinitely, not a schedulable near-term task.** Examples migrated (2026-07-27) and `--legacy-mode` gate added (2026-08-13) already, but the 2026-07-27 premise that the legacy code path was "provably dead for every example" was found false by the 2026-08-24 investigation (real CAM-SIMA still declares `horizontal_loop_extent` directly, e.g. `temp_adjust.meta`/`temp_adjust_scalar.meta`) and reconfirmed by this session's own `/cam-sima-regression` run (`xdsl43g`) against real CAM-SIMA test cases. The code path must be retained for as long as `--legacy-mode` itself is supported — deletion is only safe once CAM-SIMA migrates off `horizontal_loop_extent` upstream, an external dependency this repo can't resolve on its own. `ccpp.py`'s `is_legacy_mode()` gate is still called; not scheduled for removal | L5679 |
| `task28-stage5-fanout` | Stage 5 of task #28: match capgen-v1's `''`/`'all'`-group fan-out call shape exactly | S-M, cosmetic, blocks nothing | L4820 |
| `task11-omp-thread` | Task #11 items 1/3: `number_of_openmp_threads` rename; `registered_dimensions.py`'s `thread_number` scalar-index mechanism | Scoped 2026-08-20, not started; item 3 is the real one (M-L, needs its own test fixture) | L4835 |

**Resolved since last verification (2026-09-29), removed from the list above**:
follow-up items spawned by `constituents_dim` (single-source migration for
`advection`, naming-convention audit) — `examples/advection/CMakeLists.txt`
now links `xdsl_ccpp/framework_src/` directly, and the naming audit landed
via Stage 5 (bare capgen-v1-style names), CHANGELOG.md L4727. `examples/ddthost`
falling behind `examples/capgen` — addressed by PR #104 (prerequisite + both
stages landed, plus two real bugs found and fixed during CI verification: an
uninitialized `cind` read shared with `examples/capgen`, and a missing
`ccpp_register` driver call), CI green, CHANGELOG.md L5616. `horizontal_loop_extent`'s
duplicate chunking code (`suite_cap.py`/`run_dispatch.py`) — unified into
`cap_shared.build_ncol_compute_ops` (Stage 1) and a single CapVar branch in
`_build_array_section_ops` (Stage 3, also fixing a real behavioral divergence
where the legacy branch ignored a failed extra-dimension resolution); full
`pytest` suite green (711 passed, 1 xfailed) and a `/cam-sima-regression`
run (test ID `xdsl43g`, gnu) confirmed 28/31 aux_sima cases pass, 1 known
pre-existing unrelated failure (`F2000_C7`/cam7 `MODEL_BUILD`, tracked
separately), CHANGELOG.md L5850.

## Other flagged issues

| ID | Item | Notes | Archive |
|---|---|---|---|
| `cmake-configure-regen` | CMake cap generation runs at configure time — every example regenerates on every CI job | Size TBD | L6059 |
| `type-control-gap` | `type = control` (capgen-v1) has no xdsl-ccpp equivalent | Modeling gap, currently inconsequential | L5974 |
| `suite-state-full-match` | Full capgen-v1 `ccpp_suite_state` match (integer-enum allocatable array + dedicated alloc/dealloc subroutines) | L; was deferred until after task #28 — task #28's Stages 1-4 are now done (archive L6148), so this is unblocked | L6148 |

**Resolved since last verification (2026-10-09), removed from the list
above**: `table-props-module-name` — `[ccpp-table-properties]`'s
`module_name` override now supported; also fixed two related latent
`suite_cap.py` bugs found along the way. CHANGELOG.md L10474.

**Resolved since last verification (2026-10-09), removed from the list
above**: `dsl-inprocess-api` — `ccppMain.run()` now takes an optional
`options_db` and returns a `CcppDslResult` (resolved vars, etc.) instead of
`None`; a Copilot review comment on PR #122 also caught a real
`options_db`-bypass normalization bug, fixed. CHANGELOG.md L10381.

**Resolved since last verification (2026-10-09), removed from the list
above**: `task70-arraysection` — `ArraySectionOp` consolidated into
`RankReducingSliceOp` and deleted; 3 real bugs found and fixed along the
way (not just a mechanical rename). CHANGELOG.md L10289.

**Resolved since last verification (2026-10-08), removed from the list
above**: `task71-validate-fir` — confirmed via direct code read that
`ccpp_validate_source.py --backend flang` is a strict superset of
`ccpp_validate_fir.py` (same `find_flang`/`run_flang`/`fir-to-meta`
extraction, same `compare_modules` comparison — the one apparent
difference, non-scheme `.meta` filtering, turned out to be cosmetic only,
since `compare_modules` itself already silently skips meta-only tables).
Deleted `ccpp_validate_fir.py`; updated `DEVELOPERS.md`'s tool table and
the `ctx_utils.py`/`flang_utils.py`/`ccpp_dsl.py` comments that named it
as one of the original duplication sites. CHANGELOG.md L10192.

**Resolved since last verification (2026-09-29), removed from the list above**:
"Move examples' build system from per-example Makefiles to CMake" — fully
done. Zero Makefiles remain under `examples/`; the repo-wide CMake
migration (root `CMakeLists.txt` + `cmake/xdsl_ccpp_capgen.cmake`,
documented in `README.md`'s "Repo-wide example build" section) replaced
them entirely. `errflg-guard-order` — fixed at the root cause in
`generateSchemeSubroutineCallOps` (`suite_cap.py`), a one-line reorder to
match true SSA def-use order; regenerated and diff-reviewed all 8 affected
`completed_ir` goldens (one more than originally flagged — `var_compat`
was added since), and found the same bug had also been causing a related
indentation glitch in the pretty-printer, fixed as a side effect. Full
suite green: 711 passed, 1 xfailed. CHANGELOG.md L5968.


**Resolved since last verification (2026-10-08), removed from the list
above**: `optionsdb-list-format` — `ccpp_dsl.py`'s and `ccpp_xml.py`'s
own independent `build_options_db_from_args` implementations each
unconditionally called `.split(",")` on `suites`/`scheme_files`/
`host_files`/`preproc_defs`, crashing (`AttributeError`) on a real Python
list instead of accepting it like capgen-v1 does. Confirmed the
downstream pipeline already fully supported native lists (proven by
`ccpp_prebuild.py`'s own direct `options_db` list assignment, bypassing
`build_options_db_from_args` entirely) — the gap was isolated to that one
function. Fixed via a new shared `coerce_list_option()`
(`xdsl_ccpp/util/options_db.py`), used at all 7 call sites: accepts a
comma-joined string (unchanged CLI contract) or a real list/tuple
(passed through). CHANGELOG.md L10241.

## From `capgen_v1_parity_backlog.md` (merged 2026-09-29)

Two workstreams: the `ResolvedVar`/`cam_autogen.py` integration
(Workstreams 1, Stages 0-9, all done) and a DDT-redefinition bug fix
(Workstream 2, resolved). Nearly everything in that doc turned out to
already be done or superseded by this session's own extensive
`/cam-sima-regression` testing — see CHANGELOG.md's merged section for the
full history. One small item survives as genuinely open:

- `constituent-ddt-stub-unify` — Consider whether `_generate_constituent_api`'s hardcoded DDT stub list
  should eventually be unified with the generic `ddt_source_module`
  mechanism rather than living as a second parallel path — today's fix
  makes the two paths coexist safely, it doesn't merge them. (CHANGELOG.md
  L8254)

**Resolved since last verification (2026-10-08), removed from the list
above**: `ddt-redef-filecheck` — added
`tests/filecheck/examples/end_to_end/ddt-redef-dedup-xml.mlir`, backed by
a new minimal fixture (`tests/filecheck/fixtures/ddt_redef/`) built
specifically to trigger both of `_generate_ccpp_cap_module`'s DDT-use-stub
paths for the same type (`ccpp_constituent_prop_ptr_t`) in one run —
confirmed no existing example reached this shape. Verified as a real
regression guard: fails with the original "Redefinition of symbol" error
when the `shared_seen_host_globals` dedup fix is locally reverted, passes
again once restored. CHANGELOG.md L10129.

**Resolved since last verification (2026-09-29), removed from the list above**:
`camsima-untested-confirm` — checked each of the four distinct "Untested" sub-claims
individually against real evidence rather than closing the group on general confidence. Three
confirmed covered: real production physics suites (`cam4`/`cam7` via real `/cam-sima-regression`
runs, most recently `xdsl43g`), subcycles in an actual CAM-SIMA context (`suite_cam7.xml`'s own
active subcycle blocks, successfully cap-generated), and GPU/`memory_space` directives in an
actual CAM-SIMA context (this session's se_cslam_gpu/kessler_mpas GPU fixes, against real CIME
`nvhpc` builds). One sub-claim, "nested" subcycles specifically, isn't a real gap — no CAM-SIMA
suite today nests one subcycle inside another (checked directly, max depth 1), so it can't be
confirmed or refuted either way. One genuinely narrower gap survives, not tracked as its own
numbered item (no urgency, no current use case): multi-suite builds in an actual CAM-SIMA
context remain untested — every real case's `CAM_CONFIG_OPTS` declares exactly one
`--physics-suites` name, even though both CAM-SIMA's CLI and xdsl_ccpp's generator support more.
CHANGELOG.md L8406.

## Someday-maybe: `NCAR/atmospheric_physics` duplication reduction (merged from `duplication_analysis_summary.md`, 2026-09-29)

Not scheduled, not started (unchanged status since first logged
2026-07-19) — real research, no current commitment to act on it. Full
analysis, worked examples, resolved technical risks, and an effort
staging table live in CHANGELOG.md (L8320 onward). Three proposals,
smallest to largest:

- `dup-scheme-family-gen` — **`scheme_family` code generator** (symbolic-tracing templating for
  formula-duplicate Fortran subroutines, e.g. `wet_to_dry_*`/
  `dry_to_wet_*`) — ~320-360 lines eliminable, <1% of the Fortran
  codebase. CHANGELOG.md L8365.
- `dup-suite-composition-dsl` — **Python suite-composition DSL** (replace hand-copied SDF XML blocks
  with composable Python, e.g. `dry_basis`/`theta_basis` combinators) —
  ~280 lines directly, bigger value in removing drift risk between
  `suite_cam4.xml`/`suite_cam7.xml` and their standalone-suite sources.
  CHANGELOG.md L8453.
- `dup-meta-shadow-elim` — **Eliminate `.meta` as a hand-maintained shadow file** — the big one:
  tag `standard_name`/`units` directly in Fortran source comments
  (`!ccpp [name] key=value`), generate `.meta` mechanically. ~14,300+
  lines' worth of hand-authored `.meta` content (45% mechanical mirror of
  the Fortran signature + 15% half-mechanical dimension info) would
  become a generated build artifact instead. CHANGELOG.md L8467
  (magnitude comparison) through L8577 (verdict: "small-to-moderate
  effort... a couple of focused weeks," with the two open technical risks
  — comment retrievability through fparser2, line length — already
  resolved with working techniques against the real corpus, not open
  questions).

Targets a different repo (`NCAR/atmospheric_physics`), not this one, but
Section 5's own architecture review found most of the xdsl_ccpp-side
plumbing this would need (the `fparser2_to_meta.py`/`fir_to_meta.py`
extractors, `ArgumentOp`'s already-optional `standard_name`/`units`/
`memory_space` properties, `ccpp_generate_meta.py`'s stub generation)
already exists. `README.md`'s "Metadata Skeleton Generation" section
links here as a "Future direction" callout.

## chost (C++ host) known limitations — open items

Full detail, resolved-item history, and usage guidance stay in
`multilanguage_limitations.md` (kept standalone — it's live chost usage
reference, not backlog noise). These 3 items are its only open ones as
of 2026-10-07 (11 of its 14 numbered items are now resolved); pointer
entries here so they surface in a backlog sweep too. A 4th item
(`chost-real-width-fallback`), found and resolved the next day, was
tracked here only — never folded into `multilanguage_limitations.md`'s
own numbering, since it was closed before that was needed.

**`chost-rank3-bindc` — RESOLVED 2026-10-07**: the plain `--bind-c` path
(no chost layer) was non-functional for *every* array rank, not just
"rank > 2" as previously scoped here — confirmed via real gfortran
compilation. Fixed by declaring the BIND(C) wrapper's array arguments
with explicit shape + `target` instead of flat assumed-size, resolving
each dimension from a sibling scalar argument already in scope. See
`CHANGELOG.md`'s "`chost-rank3-bindc` resolution" (L9569) for full
detail, including a PR #112 Copilot review round (2 real findings, both
fixed) and real end-to-end gfortran compile verification.

**`chost-identity-collision`/`chost-dim-collision` — RESOLVED 2026-10-07**:
`cpp_interop.py`'s `_chost_build_maps` resolved every chost argument's
identity (`local_to_std`) and dimension shape (`local_to_dim_names`) via
flat, global, unscoped scans across all schemes in the build — the same
collision bug class `chost-rank3-bindc`'s PR #112 review already fixed
once in `run_dispatch.py`. Fixed by scoping the scan to exactly the
schemes feeding one suite-cap function (new `_suite_fn_groups_for`/
`_chost_scan_scheme_phase_args`), keying a genuine collision by each
sibling's own `model_var_name` — precisely what `suite_cap.py`'s own
renaming already assigns it (new `_chost_resolve_scheme_arg_identities`).
Both items fixed in one implementation pass (identical new scoping
infrastructure needed for both), tracked as two separate entries by
deliberate choice. See `CHANGELOG.md`'s
"`chost-identity-collision`/`chost-dim-collision` resolution" (L9700)
for full detail.

- `chost-gpu-memory` — **GPU memory management** — the chost cap is a CPU BIND(C) wrapper; a
  C++ host driving GPU physics is entirely on its own for device-pointer
  placement across the boundary (Kokkos `CudaSpace` invisible to OpenACC,
  no automatic pointer sharing across a BIND(C) call for OpenMP target,
  etc.). Potential fix: an optional `--directive` mode emitting `!$acc
  host_data use_device(...)`/`!$omp target data use_device_ptr(...)` at
  the chost boundary. Medium-High effort. `multilanguage_limitations.md`
  §2. Related: the EAMxx bridge automation proposal's "Phase B — explicit
  device-pointer contract" below (`gpu_pointer_mode = deviceptr`) is a
  more concrete, narrower design for the same underlying gap — a fix
  there would directly resolve this item, not just a similar one.
- `chost-column-major` — **Column-major array layout requirement** — a C++ caller must lay out
  arrays column-major (Fortran order) or get silently wrong physics
  results; no detection or row-major option exists. Potential fix:
  generate a row-major variant that transposes internally, or an
  `array_layout = row_major` host `.meta` option. Medium effort, more a
  documentation/footgun risk than a broken feature today.
  `multilanguage_limitations.md` §1.
- `chost-thread-safety` — **Thread safety — `ccpp_suite_state`** — concurrent C++ threads calling
  the chost cap race on the module-level suite-state variable. Safe today
  only because the one real C++ driver (kessler) is single-threaded.
  Low-Medium effort; multi-instance support (see above) is one viable
  fix path, now that its own reference to the removed `--num-instances`
  flag has been corrected. `multilanguage_limitations.md` §6.

**`chost-real-width-fallback` — RESOLVED 2026-10-08**: `cpp_interop.py`'s
`_real_width_from_iso` silently defaulted to 64-bit for any kind it
couldn't resolve via the ISO-name map — including an unresolved
bare-digit kind like `kind = 4` (single precision), since
`suite_kinds.py`'s own `MetaKind` pass deliberately never creates a
`ccpp.kind` entry for a bare-digit kind. Fixed by consulting the
Fortran-side `real_kind_width` (`ccpp_conventions.py`) before falling
back to 64 — note `real_kind_width` returns a byte count (4/8), not a
bit width, so the fix multiplies by 8. Confirmed this path is genuinely
reachable (not made moot by `lang-neutral-expr-ir` Stage 3c's own
Fortran-side `TypeConversions.convert` reclassification): a DDT member's
real width is inferred directly from the member's own raw metadata
`kind` string (`_chost_expand_ddt_arg`), independent of the suite-cap
block-arg MLIR type Stage 3c touches. 4 new unit tests in
`tests/unit/test_cpp_interop_kind_width.py`. See `CHANGELOG.md`'s
"`chost-real-width-fallback` resolution" (L9994) for full detail.

## Fortran host → C++ scheme: no compiled end-to-end test

ID: `cxx-scheme-no-e2e-test`

From `multilanguage_plan.md` (kept standalone as design-background
reference; its main C++-host/Fortran-scheme plan, Phases 1-7, is fully
implemented). This is the *orthogonal* direction — a Fortran host calling
a C++ scheme implementation through a CCPP-generated suite cap. The cap
generator side is done and verified (`language = c++` on a scheme's
table-properties block correctly emits a `BIND(C)` interface block
instead of a plain `use` statement — confirmed via 3 FileCheck tests,
`tests/filecheck/examples/{frontend,completed_ir,end_to_end}/language*-py.mlir`).

**What's missing**: a real C++ scheme implementation with `extern "C"`
entry points to compile and link against, and a compiled end-to-end test
(Makefile/CTest) verifying ABI correctness and numerical results — only
static `.meta`/`.xml` FileCheck fixtures exist today
(`tests/filecheck/examples/language_cxx/`), confirmed still true
2026-09-29 (no such compiled test or example found anywhere in the
repo). Not scoped/estimated in the source doc.

## Someday-maybe: EAMxx bridge automation (merged from `EAMxx/EAMxx-bridge-automation.md`, 2026-09-29)

A design proposal (2026-07-29/08-06), not a record of work done — nothing
in it has been implemented, confirmed against current source (no
`variant` metadata tag, no `gpu_pointer_mode` property, no suite-coverage
checker script anywhere in `xdsl_ccpp/`). Full proposal lives in
CHANGELOG.md (L8588 onward). Addresses: given both CPU and GPU (OpenACC)
Fortran variants of a scheme, how would xdsl-ccpp generate a real C++
host's *entire* bridge, not just the Fortran cap layer — motivated by
`EAMxx/kessler-README.md`'s real downstream integration (a different
repo, kept here as reference, not tracked as this repo's own backlog).
Three phases, recommended in this order:

- `eamxx-phaseA-variant-tag` — **Phase A — metadata `variant` tag** (moderate effort): teach the
  `.meta` format that a scheme has CPU and GPU (OpenACC) variants with
  different argument lists, so `suite_cap.py` can emit an `#ifdef`
  branch automatically instead of requiring a hand-patched meta per
  build config. CHANGELOG.md L8624.
- `eamxx-phaseB-deviceptr` — **Phase B — explicit device-pointer contract** (small): a
  `gpu_pointer_mode = deviceptr` host-meta property so `cpp_interop.py`
  knows to pass GPU pointers straight through with zero data-staging
  directives, instead of silently assuming the scheme's own directives
  happen to do the right thing. CHANGELOG.md L8650. Related: this is a
  concrete design for the "chost (C++ host) known limitations" section's
  "GPU memory management" item above — implementing this would directly
  close that gap.
- `eamxx-phaseC-printer` — **Phase C — a new "EAMxx AtmosphereProcess" printer** (large, an order
  of magnitude more effort than A+B): generate the whole C++
  `AtmosphereProcess` class, not just the BIND(C) layer. Needs genuinely
  new EAMxx-specific metadata vocabulary (Field-Manager registration,
  `FieldLayout` tags, buffer-manager/Kokkos-View integration) with no
  existing analog in the tool. Some pieces (QA-check bounds,
  energy-fixer bookkeeping) should stay permanently hand-written even if
  built. CHANGELOG.md L8667.

`eamxx-suite-coverage-checker` — A cheaper, high-value piece of tooling identified independent of the
three phases: a "suite-coverage checker" script diffing a real suite
XML's scheme list against a hand-written bridge's own tracking comments,
flagging any scheme with no corresponding comment — needs no generator
changes at all, would have mechanically caught a real silent gap found
during this analysis. CHANGELOG.md's merged section, "A cheaper,
higher-value piece of tooling."

