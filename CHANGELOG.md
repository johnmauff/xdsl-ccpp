# Refactor Archive: Decomposing `ccpp_cap.py` in xdsl-ccpp

**Historical record.** For the current, open backlog items only, see
`BACKLOG.md`. Everything below (including the Index) reflects the full
narrative and is kept for reference; items marked ✅/🔄 here may since have
moved -- `BACKLOG.md` is the up-to-date source for open items, this file
is not.

**Target (as of the plan's start, 2026-07-17):** `xdsl_ccpp/transforms/ccpp_cap.py`
(4,749 lines), the `CCPPCAP` pass (`generate-ccpp-cap`) in
[johnmauff/xdsl-ccpp](https://github.com/johnmauff/xdsl-ccpp). **Current size (2026-07-19,
after Phases 1-5): 853 lines** — an 82% reduction, all of it moved into
`cpp_interop.py`/`lifecycle_cap.py`/`constituent_cap.py`/`run_dispatch.py`/`suite_cap.py`/
`cap_shared.py` rather than deleted; see "Current state" below for where it all landed.

**Context (as of the plan's start):** `CCPPCAP` bundled at least five distinct concerns into
one `ModulePass`: a C++/BIND(C) backend, run-dispatch argument resolution, lifecycle-function
generation, constituent-API generation, and suite-variable/final-module assembly. The
project's own sibling passes at the time — `generate_kinds.py` (66 lines, unchanged since) and
`gpu_ccpp_cap_pass.py` (339 lines at the time; now 405 after this session's lifecycle-coverage
work) — showed that small, focused passes were the established pattern here; `CCPPCAP` just
hadn't been split the same way yet.

The repo had a single contributor and a thin test net (0.25:1 test:core ratio at the time),
with some existing tests already broken. That shaped the plan below: order phases by risk
(lowest first), keep every phase behavior-preserving until the last one, and lean on the
existing golden-file (FileCheck) tests as the de facto reviewer at each step. **None of that
motivating state is current anymore** — see "Current state" immediately below for where things
actually stand; the paragraph above is kept as-is as the original rationale, not a live
description.

---

## Index (added 2026-08-13)

Lightweight status lookup so updating this doc doesn't require re-reading 3,600+ lines of
narrative first. Each row's `L<n>` is the line number of that item's own bullet/heading in this
file (as of 2026-08-13 — will drift as the doc grows; if a line number looks wrong, search for
the bolded lead-in text quoted in "Item" instead). The narrative sections themselves remain the
source of truth for *why* and *how* — this table only tracks *what* and *whether it's done*.

**The six-phase `ccpp_cap.py` decomposition + Phase 7:**

| Item | Status | Location |
|---|---|---|
| Phase 0 — Stabilize the safety net | ✅ Done | L1307 |
| Phase 1 — Extract the C++/BIND(C) backend (`chost`) | ✅ Done | L1374 |
| Phase 2 — Extract lifecycle and constituent-API generation | ✅ Done | L1439 |
| Phase 3 — The run-dispatch cluster | ✅ Done (3a + 3b, all stages) | L1522 |
| Phase 4 — Consolidate with `suite_cap.py`'s argument classification | ✅ Done (narrow extraction) | L1762 |
| Phase 5 — Slim `ccpp_cap.py` down to its real remaining job | ✅ Done | L1905 |
| Phase 6 — Decide pass-status for the new pieces | ✅ Decided (no code change) | L1965 |
| Phase 7 — Full IR unification | ✅ Done (Stages 1-4) | L2004 |

**Backlog — capgen-v1 end-to-end-tests capability gaps:**

| Item | Status | Location |
|---|---|---|
| `var_compat` (vertical flip, kind/unit conversion, cross-scheme divergence, wrapper copy-back) | ✅ Done | L2290 |
| `nested_suite` | ✅ Done (PR #47, merged) | L2998 |
| `constituents_dim` | ✅ Done (PR #67, merged, CI green, 2026-08-13) | L3068 |
| Follow-ups spawned by `constituents_dim`: single-source migration for `advection`; naming-convention audit | 📋 Backlog | L3224 |
| `suite_allocate` | ✅ Done (2026-08-17) | L3242 |
| `chunked_data` | ✅ Done (ported, wired into root build) | L3276 |
| `instances`/`instances_advection` | ✅ Both done (2026-08-18): `instances` via the multi-instance `ccpp_suite_state` narrow fix; `instances_advection` via task #35's constituent-API instance-awareness fix (its own originally-tracked cap-gen crash was already gone by the time it was re-investigated) | L3296 |
| `instance_number`/`number_of_instances` paired-contract bug (Copilot review, PR #77) + 2 self-found companion bugs of the same class in `suite_cap.py` | ✅ Done (2026-08-18) | L4226 |
| `opt_arg`'s dead `active` property | ✅ Done (2026-08-13) | L3350 |
| Unconditional unit-conversion buffer allocate for optional args (found while fixing the above) | ✅ Done (2026-08-17) | L3505 |
| Metadata `kind_spec` support (capgen/ddthost port completeness) | ✅ Done (2026-08-17) | L3966 |
| Interstitial-variable register-phase mechanism | ✅ Done (2026-08-17) — non-chained case restored/tested; chained case tracked separately | L4038 |
| `temp_adjust`/`temp_calc_adjust`/`temp_set` rank/dimensionality re-sync to real upstream | ✅ Done (2026-08-17) | L4098 |
| Chained-interstitial allocation-ordering bug (`_build_framework_refs`) — task #30 | ✅ Done (2026-08-19) | L4085 |
| Broader allocation-dependency model (cross-phase unification, DDT/non-real interstitial coverage) — task #65 | 📋 Backlog (size TBD, deliberately deferred until #30 lands) | L5015 |
| Metadata `dependencies`/`dependencies_path`/`source_path` tracking (Tier 1: parse + IR-forward, no build-system consumer) | ✅ Done (2026-08-17) | L4176 |
| Metadata dependency-manifest automation for CMake (Tier 2 of the above, overlaps with CMake configure-time item below) | 📋 Backlog (size TBD, needs its own design pass) | L4176 |
| `examples/ddthost`'s own copies of `temp_set`/`temp_adjust`/`temp_calc_adjust` have fallen behind `examples/capgen`'s (missing `kind_spec`, `interstitial_var`, rank re-sync, `temp_adjust_register`) | 📋 Backlog, detailed scoping done (2026-08-24) — upgraded S-M to M: real cross-file coupling (`temp_calc_adjust`+`temp_adjust` share a standard_name, must land together), `temp_set` has 4 undocumented new vars needing host-side additions, staged as 1 tiny prerequisite + 2 stages. Not started; not a CAM-SIMA blocker, not small cleanup | L5551 |
| `advection`'s error-path bonus (negative test for constituent-props-outside-register) | ✅ Done (2026-08-18) — real silent-miswiring bug found and fixed, not just a missing check | L3377 |
| Retire the legacy `horizontal_loop_extent` vocabulary | ✅ Examples migrated (2026-07-27); ✅ `--legacy-mode` gate added, default now rejects (2026-08-13); 📋 actual code-path deletion still open | L3383 |
| Consolidating `horizontal_loop_extent`'s duplicate chunking code (`suite_cap.py`/`run_dispatch.py`) | 🔍 Investigated (2026-08-24) — 2 of 4 files already unified, nothing to fix; the other 2 are real, --legacy-mode-only code still used by real CAM-SIMA fixtures (confirmed against CAM-SIMA-fresh), not dead code. Deliberately deferred until a CAM-SIMA-backed fixture exists in this repo to test a consolidation against; stale code comment fixed in the meantime | L5698 |
| Vocabulary-resolution redesign (match capgen-v1's use-association model) | ✅ Stages 1-5 done (2026-08-13); 6-8-phase lifecycle match logged separately | L3589 |
| Full 6-phase to 8-phase lifecycle match with capgen-v1 — task #28 | ✅ Stages 1-4 done (2026-08-20), CI green; Stage 5 spun off as its own item below | L4759 |
| Stage 5 of task #28: match capgen-v1's `''`/`'all'`-group fan-out call shape exactly | 📋 Backlog (S-M, cosmetic, blocks nothing) | L4759 |
| Task #11: 3 remaining legacy/compat vocabulary gaps (`number_of_openmp_threads` rename, `--gfs-dim-aliases` vertical-axis shim, `registered_dimensions.py`'s `thread_number` scalar-index mechanism) | Item 2 (`--gfs-dim-aliases`) ✅ Done (2026-08-24, task #68); items 1/3 still 🔍 Scoped, not started — coupled to each other, item 3 the real one (M-L, needs its own test fixture) | L4818 |

**Backlog — other flagged issues:**

| Item | Status | Location |
|---|---|---|
| `generateSchemeSubroutineCallOps`'s errflg-guard SSA def-use order | 📋 Backlog (S, cosmetic) | L3436 |
| Move examples' build system from per-example Makefiles to CMake | 📋 Backlog (size TBD) | L3467 |
| CMake cap generation runs at configure time -- every example regenerates on every CI job | 📋 Backlog (size TBD) | L3652 |
| `.meta` bracket-spacing parser bug (`[ name ]` vs `[name]`) | ✅ Fixed | L3493 |
| Three more whitespace-parsing bugs (same class, found by audit) | ✅ Fixed | L3540 |
| `[ccpp-table-properties]`'s `module_name` override unsupported | 📋 Backlog (S) | L3566 |
| `type = control` (capgen-v1) has no xdsl-ccpp equivalent | 📋 Backlog (modeling gap, currently inconsequential) | L3585 |
| Suite signature generation ignored host's own unique local name (collision) | ✅ Fixed (2026-07-23) | L3620 |
| Full capgen-v1 `ccpp_suite_state` match (integer-enum allocatable array + dedicated alloc/dealloc subroutines) | 📋 Backlog (L, deliberately deferred until after task #28) | L5135 |
| ~~Scheme-level dynamic constituent registration output discarded~~ (corrected: not a bug) + the real multi-instance regression this investigation found in the same code path | ✅ Corrected + fixed (2026-08-18) | L5360 |
| Codebase-wide complexity/duplication audit (tasks #37-#62) | 🔄 Tier 1+2 executing (2026-08-18); Tier 3 backlog; Tier 4: tasks #61/#62 ✅ both fully Done (2026-08-24, #62 incl. PR #91 Copilot follow-up), tasks #70/#71 split out and still backlog | L5539 |
| Task #72: SuiteOwned dimension var from prior phase missing from allocation (`pint_day` not allocated in rrtmgp cap) | ✅ Fixed (2026-09-09): `_resolve_alloc_dim_var_refs` fallback to `data_ops` | L6752 |
| Task #70: consolidate `ArraySectionOp` into `RankReducingSliceOp` | 📋 Backlog (M, real refactor touching 5 files' core dispatch logic) — split from task #61 | L6544 |
| Task #71: decide fate of `ccpp_validate_fir.py` vs `ccpp_validate_source.py --backend flang` | 📋 Backlog (S-M, needs a diff + decision, not a same-sitting deletion) — split from task #61 | L6544 |
| Task #66: double-`"_suite"` naming convention (e.g. `kessler_suite_suite_register`) — needed for CAM-SIMA link compatibility | ✅ Done (2026-08-24): Stage 1 (centralize infix) + Stage 2 (actual rename, `SUITE_FN_INFIX=""`) both landed on `double-suite-naming-stage1`; Stage 2 found and fixed a real bug (`cpp_interop.py`'s own independent, un-centralized `"_suite_"` copy) via real regen before touching goldens | L6621 |

---

## Current state (2026-07-19)

Numbers below are freshly measured from the actual repo, not carried forward from any earlier
entry in this log:

- **`ccpp_cap.py`: 853 lines** (was 4,749 at the plan's start — Phases 1-5 below account for
  the reduction).
- **Full test suite: 378 unit tests passed + 44 FileCheck passed, 1 xfailed** (305 unit tests
  before this session's `test_gpu_data_hoisting.py` addition, 357 after Option 2, 359 after
  item 1(a)'s update-clause hoisting extension, 361 after the second Copilot-review fix to
  `_resolve_lifetime`'s whole-sim rule, 366 after the OMP `map(...)` paren-bug fix
  (`test_omp_directives.py`), 368 after the OMP hoisting IR ops' op-level printer tests, 374
  after wiring OMP hoisting itself into `GPUCcppCapPass` (`test_omp_hoisting.py`'s initial
  Group A/B/E), 378 after extending `test_omp_hoisting.py` with Group C/D/F; the one accepted
  xfail exception is the rank-3 chost/`--bind-c` question — still open, see the entries below on
  that). Green throughout every phase since Phase 0; **the "some existing tests already broken"
  state from the plan's start no longer applies and hasn't since Phase 0.**
- **Test:core ratio: ~5,426 test lines / ~18,566 `xdsl_ccpp/` source lines (~0.29:1) before this
  session's GPU data-hoisting tests**, up from 0.25:1 at the plan's start — 21 files under
  `tests/unit/` (25 after this session: `test_gpu_data_hoisting.py`, `test_omp_directives.py`,
  `test_omp_hoisting.py` added). Treat this as an approximate, not a precisely reproduced
  recomputation of whatever methodology produced the original 0.25:1 figure.
- **`gpu_ccpp_cap_pass.py`: 788 lines** (775 before OMP hoisting was wired in; 740 after item
  1(a)'s update-clause hoisting extension; 660 after Option 2's cross-function OpenACC
  data-hoisting rewrite below; 405 before Option 2; 339 before the lifecycle-phase-coverage
  extension that preceded it) and **`gpu_data_pass.py`: 257 lines** (untouched by item 1(a) or
  the OMP hoisting wiring — see "Current state" above on why the two passes' host-less-
  scratch-array and host-matched-variable paths never overlap) — both outside the original
  6-phase plan's scope (that plan targeted `ccpp_cap.py` specifically) but touched heavily in
  this same session; see the GPU/OpenACC entries further down. New
  `tests/unit/test_gpu_data_hoisting.py`: 845 lines, 12 tests (8 after Option 2, +2 for item
  1(a)'s `TestUpdateClauseHoisting`, +2 for `TestFinalizeAlongsidePerTimestepHoisting`).
- Everything above reflects this session's cumulative work, not just today: the 6-phase
  `ccpp_cap.py` decomposition, Phase 7's design work, the subcycle/duplication-sweep fixes, the
  GPU lifecycle-coverage extension and its Copilot-review fixes, the cross-function OpenACC
  data-hoisting feature ("Option 2") and its own Copilot-review fixes, extending that hoisting to
  the update-clause path (item 1(a)), the documentation-limitations audit and cleanup, and the
  `duplication_analysis_summary.md` backlog addition are all already reflected in these totals.

---

## 📍 Session status (updated 2026-07-19)

**Done and merged to upstream `main`:** Phases 0, 1, 2, 3a, all of Phase 3b (Stages 1-4, PRs
#9-#12), and Phase 4 (PR #13, including a post-merge Copilot review fix — a second occurrence
of a subcycle-flattening bug found via a full repo sweep, which turned out to be dead code and
was deleted rather than patched). See each phase's own "outcome" section below for full details
(what moved, bugs found, verification performed).

**Done and committed locally, not yet merged to `main`:** Phase 5 (commit `5eb3f0a` on
`phase5-slim-down-docs`) — pure documentation phase, as anticipated: `ccpp_cap.py`'s structure
already matched the target shape by the time this phase started (Phases 1-4 did the actual
slimming). Checked every pipeline-position docstring across `xdsl_ccpp/transforms/` against the
real pass ordering in `ccpp_dsl.py`'s `_build_pipeline` — all but one were already accurate;
fixed the one gap (`gpu_ccpp_cap_pass.py` didn't mention `generate-cpp-cap` now also running
before it). The real target was `DEVELOPERS.md`, which had drifted significantly: never
mentioned `generate-cpp-cap` (a real Phase-1 pass) anywhere, referenced a `ccpp_cap_dialect.py`
file that doesn't exist (it's `ccpp.py`), never mentioned
`lifecycle_cap.py`/`constituent_cap.py`/`run_dispatch.py` or `cap_shared.py` at all. All fixed —
full details under the Phase 5 section below. Full suite: 302 passed, 1 xfailed (unchanged —
docs + one docstring edit only).

**Done, not yet committed:** Phase 6 — decided (no code change): `run_dispatch.py`,
`lifecycle_cap.py`, and `constituent_cap.py` all stay plain internal modules, not registered
passes; `cpp_interop.py` remains the only one of the newly-extracted pieces promoted to a full
pass (already done in Phase 1). Full rationale — the real dividing line turned out to be
architectural shape (does the module scan an already-complete downstream artifact, like
`cpp_interop.py`, or contribute mid-construction to a module still being assembled, like all
three of these) rather than size, as originally guessed — is under the Phase 6 section below.
Also fixed a line in `DEVELOPERS.md` (added during Phase 5, on the same uncommitted branch) that
called this "an open decision, not yet made" — no longer accurate. On local branch
`phase5-slim-down-docs`, uncommitted upstream as of this writing.

**This closes out the original 6-phase refactor plan.** All six phases are now done.

**Tracked separately, not scheduled:** Phase 7 — full IR unification, added 2026-07-19 as its
own staged sub-plan (4 stages, in the Phase 3b mold) after reconsidering an earlier claim that
it wasn't decomposable — see the Phase 7 section below for the full plan, and Phase 4 above for
the motivating investigation. No obligation to start this soon; also the prerequisite for
revisiting the Phase 6 pass-status decision.

**Also proposed, not yet implemented** (discussed after the Phase 3a review round, before
starting 3b):
- ~~A regression test asserting the "no suite matched" error message text is identical across
  `run_dispatch.py`'s and `lifecycle_cap.py`'s independent implementations~~ **✅ done
  (2026-07-19), and done as the actual design fix rather than just a test.** Extracted the
  identical 4-op sequence (`WriteErrMsgOp` + errflg-set + store + yield) all three call sites
  built independently — `run_dispatch.py`'s `_build_run_chain_preamble` and
  `_generate_suite_part_list_fn`, plus `lifecycle_cap.py`'s one call site — into a single
  `_build_no_suite_matched_false_ops(errmsg_dest, trim_suite_name_res, errflg_dest)` in
  `cap_shared.py`, following the exact `_is_framework_managed` precedent from Phase 4. This
  closes the drift risk structurally: with one implementation, a future fix landing on "some
  copies but not others" (the Phase 3a bug class this item was originally about) is no longer
  possible, not just easier to catch after the fact. Added 4 new unit tests in
  `test_cap_shared.py` covering the op sequence shape, the exact message text
  ("No suite named "/" found", confirming the Phase 3a leading-space fix is preserved), and
  that it targets the given errmsg/errflg operands. Verified byte-identical across all 4
  target/example combinations. Full suite: 306 passed (302 + 4 new), 1 xfailed.
  `ruff --select F401` clean.
- Nested (2+ level) `<subcycle>` coverage — confirmed via repo-wide grep that **zero** example
  or test XML files anywhere in the repo have more than one `<subcycle>` tag. Untested at both
  the frontend-parsing layer and, more relevantly, the run-dispatch layer.
  **Update (2026-07-18): the single-level case in `ccpp_cap.py` is now fixed.** Flagged while
  investigating Phase 4 (`_build_cap_var_map`'s `_grp_schemes = [_s.attributes["name"] for _s
  in _grp_cv]` didn't flatten through `XMLSubcycle` the way `suite_cap.py`'s `getSchemeNames`
  does), then confirmed real by a Copilot review comment on the Phase 4 PR — repo-wide grep
  found **zero** example XML files with any `<subcycle>` tag at all, so this was a real,
  currently-latent bug (present since before Phase 4, preserved verbatim by the
  behavior-preserving extraction, not introduced by it) rather than a live failure. Fixed by
  flattening through `_iter_schemes`, the same helper already used at every other call site in
  `ccpp_cap.py`. Verified the fix actually catches the bug: temporarily reverted it and
  confirmed the new regression test (`TestBuildCapVarMapFlattensSubcycles` in
  `test_ccpp_cap.py`) fails with exactly the predicted `KeyError: 'name'`, then restored it.
  **What's still open:** nested (2+ level) `<subcycle>` coverage specifically, and whether
  `run_dispatch.py`'s own layer has an analogous gap — this item stays on the backlog for that.
  **Update (2026-07-19): confirmed, by reading the code (not just absence of examples), that
  nested subcycles are a silent-data-loss bug, not just an untested feature.** Verified at
  three independent layers:
  1. Frontend XML parser (`ccpp_xml.py`'s `XMLSubcycle.__init__`) only checks
     `child.tag == "scheme"` for a subcycle's children — no branch for
     `child.tag == "subcycle"` — so a `<subcycle>` nested inside another `<subcycle>` in the
     source XML, and every scheme inside it, is silently dropped at parse time. No error, no
     warning.
  2. The IR type itself (`ccpp.py`'s `SubcycleOp`) is structurally permissive — its `body`
     region has no constraint forbidding a nested `SubcycleOp` — so this is a frontend/
     reconstruction limitation, not an IR design constraint.
  3. IR-to-descriptor reconstruction (`ccpp_descriptors.py`'s
     `BuildSchemeDescription.traverse_group_op`) only checks `isa(child_op, ccpp.SchemeOp)`
     inside a subcycle's body — a nested `SubcycleOp`, even if one somehow reached the IR by
     another route, would be silently skipped here too.

  So if anyone ever wrote a nested `<subcycle>` expecting it to work, the schemes inside it
  would vanish from the generated suite with no error anywhere in the pipeline. **Decided
  (2026-07-19, per project owner): track as something to address**, not just a coverage gap —
  either reject nested subcycles with a clear error at frontend-parse time, or actually support
  them end-to-end (frontend parser → IR → `BuildSchemeDescription` → every consumer of
  `_iter_schemes`/`getSchemeNames`/`getCallSequence`/`suite_variable_model.py`'s own duck-typed
  loop). **Resolved same day** — see the "✅ Resolved" update below: checked whether nesting is
  a real capgen-ng feature first, found no evidence it is, and implemented the reject-clearly
  option rather than the support-end-to-end one.
  **Follow-up (same day): a second occurrence of the identical bug was found, and turned out to
  be dead code.** Asked directly ("do you see this pattern anywhere else?") after the Copilot
  fix, prompting a full repo-wide sweep of all 17 `.attributes["name"]` access sites. Found one
  more: `_generate_ccpp_cap_module`'s own `scheme_names_lc = [s.attributes["name"] for g in
  suite_desc for s in g]` (feeding a `_get_suite_lifecycle_ret_info` call whose `ret_info` was
  then iterated by a loop with two `continue` guards and no other body) — confirmed via grep
  that neither `scheme_names_lc` nor that `ret_info` were read anywhere else in the method. The
  comment inside the dead loop explained why: "DDT interstitials... are now declared at suite
  cap module scope... the top-level cap no longer needs to track... via cap_var_map" — leftover
  scaffolding from a prior refactor whose consuming code was removed but whose input-computing
  code wasn't. Deleted the whole block (including its now-unused `errmsg_type_tmp`/
  `errflg_type_tmp` locals) rather than patching it with `_iter_schemes`, per project owner
  instruction. Verified byte-identical across all 4 target/example combinations (expected,
  since the block was provably inert) and `ruff --select F401`/`--select F841` both clean.
  Every other `.attributes["name"]` site in the repo was individually checked and confirmed
  already subcycle-safe.
  **✅ Resolved (2026-07-19): Option A (reject, don't support) implemented, after checking
  whether nested subcycles are a real capgen-ng feature first.** Found no `briefing.md` or
  XML schema/DTD in this repo to check the upstream spec directly, but two strong pieces of
  internal evidence: (1) `examples/atmospheric_physics/suite_cam4_py.py` — a real, production
  CAM4 physics suite from ESCOMP/atmospheric_physics — has exactly two `forLoop(...)` blocks
  ("SW diagnostic subcycle" / "LW diagnostic subcycle"), both flat, both siblings, never
  nested (matching the README's "cam4/cam5: 2 subcycles" note — a count of sibling blocks,
  not nesting depth); (2) the Python DSL's own `forLoop(count, schemes: list[SchemeDescriptor])`
  is typed to accept only schemes, not another `forLoop()` result, so nesting was never a
  designed capability of this tool's own suite-authoring API either. Project owner had
  believed nesting was supported; this investigation didn't confirm that, and the decision was
  made to implement Option A now, capturing the need to revisit if a real case for nesting
  ever surfaces. Rejected explicitly, not silently, at **three** entry points (one more than
  originally scoped — the Python DSL bypasses the XML parser entirely):
  1. `ccpp_xml.py`'s `XMLSubcycle.__init__` — raises `ValueError` on a nested `<subcycle>` tag
     in raw suite XML.
  2. `py_api.py`'s `_group_item_to_op` — raises `ValueError` on a nested `forLoop()` result
     (previously would have hit a confusing `AttributeError: 'SubcycleDescriptor' object has
     no attribute 'name'` a few lines later instead).
  3. `ccpp_descriptors.py`'s `BuildSchemeDescription.traverse_group_op` — defense in depth,
     in case a nested `SubcycleOp` reaches the IR by any other route.
  4 new unit tests in `test_subcycle.py` (nested-XML rejection, the IR-reconstruction
  defense-in-depth check, nested-forLoop rejection, and a non-nested-forLoop sanity check).
  Verified byte-identical output for `kessler`, `advection`, and `helloworld`'s Python-DSL
  variant (exercising `py_api.py`'s non-subcycle path) — the real forLoop-using examples
  (`suite_cam4_py.py`/`suite_rrtmgp_py.py`) require a sibling `atmospheric_physics` checkout
  not available in this sandbox, so the direct unit tests on `_group_item_to_op` are the most
  thorough verification available here for that specific path. Full suite: 329 passed
  (325 + 4), 1 xfailed. `ruff --select F401` clean except pre-existing, unrelated findings in
  `py_api.py` (confirmed via `git stash` comparison, same discipline as every prior fix).
- ~~`ccpp_t` (multi-instance) combined with constituents~~ **✅ done (2026-07-19).** Added
  `TestCcppTWithConstituents` to `test_ccpp_t_threading.py`: a scheme declaring both a regular
  host-matched real var (needs ccpp_t) and the framework constituent arrays `ccpp_constituents`/
  `ccpp_constituent_tendencies` (matching `examples/advection/apply_constituent_tendencies.meta`'s
  pattern), run through the full `SuiteCAP` + `CCPPCAP` pipeline. Confirms ccpp_t threading
  still works with constituents present (`intent(inout)` block arg, per-instance
  `ccpp_suite_state(ccpp_data%ccpp_instance)` guard), and that the constituent args resolve to
  cap-owned module vars (`lc_constituent_array`/`lc_const_tend`) rather than leaking through as
  extra block args — at the correct layer: the suite cap's own `_suite_physics` signature
  legitimately still has them as dummy args (that classification doesn't exclude them), it's the
  top-level `_ccpp_physics_run` dispatcher, where `cap_var_map` is actually consumed, that must
  not expose them. First test caught exactly this layer confusion (checked the wrong function,
  failed, fixed to check `_ccpp_physics_run` instead of `_suite_physics`) — a useful reminder
  that "which layer resolves this" is easy to get wrong even after living in this exact code for
  most of a session. 3 new tests. Full suite: 332 passed (329 + 3), 1 xfailed.
  `ruff --select F401` clean except pre-existing, unrelated findings (confirmed via `git stash`).
- ~~Subcycle-flattening logic is duplicated ~4 ways, with no shared canonical utility~~
  **✅ done (2026-07-19), with one deliberate exception found during implementation.** Moved
  `_iter_schemes` from `ccpp_cap.py` into `cap_shared.py` and switched `suite_cap.py`'s
  `getSchemeNames` to use it too — the two genuinely-duplicated implementations. Left
  `suite_variable_model.py`'s copy separate on purpose: that module's own docstring commits to
  "No xDSL/MLIR imports — pure Python analysis," and it duck-types the subcycle check
  (`"loop_count" in child.attributes`) specifically to avoid importing `XMLSubcycle` (which
  transitively pulls in xDSL via `ccpp_descriptors.py`). Importing the shared, isinstance-based
  `_iter_schemes` from `cap_shared.py` (which itself now imports `xdsl.dialects` for the
  no-suite-matched helper above) would have broken that boundary — so what looked like 3-4
  candidates for unification going in was actually 2 duplicates + 1 correctly-separate
  implementation, once the reason for the difference was understood rather than assumed to be
  an oversight. Documented the reasoning in both `cap_shared._iter_schemes`'s docstring and a
  comment at `suite_variable_model.py`'s call site, so it isn't "fixed" again without
  re-reading why. `getCallSequence` (which deliberately *preserves* subcycle boundaries rather
  than flattening them) was correctly out of scope — a different transformation, not a
  duplicate. Added 4 new unit tests for `_iter_schemes` in `test_cap_shared.py`. Verified
  byte-identical across all 4 target/example combinations. Full suite: 310 passed (306 + 4
  new), 1 xfailed. `ruff --select F401` clean except the same pre-existing, unrelated `i32`
  finding in `suite_cap.py` noted in Phase 4.
- **Full IR unification — now its own tracked sub-plan: Phase 7 (2026-07-19).** The one *big*
  architectural change still on the table (as opposed to the narrow-extraction-sized items
  above): a single classification decided once, upfront, as durable IR, consumed by
  `suite_cap.py`, `ccpp_cap.py`, and `run_dispatch.py` instead of three sequential,
  independently-computed heuristics. Also the prerequisite for revisiting the Phase 6
  pass-status decision for `run_dispatch.py`/`lifecycle_cap.py`/`constituent_cap.py`. Motivating
  investigation is under Phase 4; the actual 4-stage execution plan is under Phase 7 — earlier
  assumed not decomposable into Phase-3b-style stages, revised on reconsideration.
- **Still-open correctness question, unrelated to this refactor's own scope (Phase 0,
  re-investigated 2026-07-19 during a documentation-limitations sweep — more precisely
  characterized, still unresolved).** The original framing here was imprecise: regenerating
  the `tiny_r3` fixture confirmed the **chost** layer is actually fine — it emits
  explicit-shape `flux(ncol, nz, nbands)` (per commit `2fe5473`), correctly matching the
  suite cap's assumed-shape `(:, :, :)` dummy. The real open question is the **plain
  `--bind-c` path** (no `language = c++`): `TinyR3_ccpp_cap.F90` declares `flux` as flat
  assumed-size (`real(c_double), intent(inout) :: flux(*)`) and forwards it directly as the
  actual argument into the suite cap's assumed-shape `flux(:, :, :)` dummy — a rank mismatch
  (1 vs 3) that should be a compile-time error under standard Fortran rules for assumed-shape
  dummies (they require a genuine matching-rank array with a descriptor; assumed-size actuals
  only participate in sequence association when the callee's own dummy is itself explicit-shape
  or assumed-size, never assumed-shape). **Still not verified against an actual compiler** —
  none available in this environment either time this has been investigated. Documented
  precisely in `multilanguage_limitations.md` §5 (split into "chost path: resolved" / "plain
  `--bind-c` path: likely broken, unverified") and flagged in `README.md`'s `--bind-c` section
  — see those two for the exact declarations and full writeup. See Phase 0 above for the
  original flag.
- **Full duplication sweep, 2026-07-19 (after the subcycle-flattening fix above):** asked
  directly whether more of this failure shape exists in the cap-generation cluster. Found and
  ranked three candidates, plus several investigated-and-ruled-out false positives (worth
  keeping the negative results, since they show the same "looks similar, isn't" pattern already
  seen with the cap-ownership investigation and `suite_variable_model.py`'s deliberate
  exception):
  - ~~DDT USE-association stub emission duplicated in `ccpp_cap.py` and `suite_cap.py`'s
    `_build_ddt_use_stubs`~~ **✅ done (2026-07-19).** Byte-identical logic (same
    `primitive_types` set, same `llvm.LLVMArrayType.from_size_and_type(0, i8)` construction),
    scanning different scopes (all of `meta_data` vs. one suite's `scheme_entries`). Extracted
    `_collect_ddt_use_stubs(arg_tables_iterable, ddt_source_module, seen=None)` into
    `cap_shared.py`; each caller now passes its own flattened generator over the arg tables it
    needs to scan. Verified byte-identical across 5 examples, including `ddthost` (chosen
    specifically to exercise the DDT-stub path directly).
  - ~~Cap-var type rank computation duplicated in `ccpp_cap.py`'s `_build_cap_var_map` and
    `run_dispatch.py`'s `_build_run_dispatch_chain`~~ **✅ done (2026-07-19).** Exact duplicate
    of `len(list(t.shape.data)) if hasattr(t, "shape") else 0`, used in two adjacent stages of
    the same cap-var pipeline (allocating the scratch var vs. referencing it at a call site).
    Extracted `_rank_of(mlir_type) -> int` into `cap_shared.py`.
  - ~~"Signature mismatch" arg-count assertion duplicated in `lifecycle_cap.py` (~line 279-286)
    and `run_dispatch.py` (~line 1072-1080)~~ **✅ done (2026-07-19).** Same check-and-raise
    shape (`if len(call_args) != len(callee_input_types): raise ValueError(...)`) at two
    different call-construction sites, with already-diverged wording (`run_dispatch.py`'s copy
    had an extra "Generated args:" debug line `lifecycle_cap.py`'s lacked). Extracted
    `_assert_call_arg_count_matches_signature(suite_callee, call_args, callee_input_names,
    callee_input_types)` into `cap_shared.py`; both callers now get the richer message
    (confirmed via repo-wide grep that no test checks this exact string, so enriching
    `lifecycle_cap.py`'s copy carried zero risk). 4 new unit tests. Verified byte-identical
    across 3 representative examples (kessler, advection, helloworld+ccpp_t) — expected, since
    this path only fires on a bug, never during normal generation.
  - **Investigated and ruled out** (kept for the record, not just the positive findings):
    `suite_cap.py`'s "Invalid initial CCPP state" `WriteErrMsgOp` (different failure condition,
    appears once, not a duplicate); two rank-computation call sites within `suite_cap.py` itself
    (`actual_rank`/`scheme_rank`, in-file not cross-file, and a different fallback semantics —
    falls back to `scheme_rank`, not `0` — so not the same pattern as the cap-var rank fix
    above); `lifecycle_cap.py`'s unconditional `shape = list(arg_type.shape.data)` (already
    inside a known-memref branch, not the same guarded-fallback utility);
    `_collect_public_suite_functions`/`collect_ddt_source_modules` (already properly shared);
    `_resolve_ddt_access_path` (unique to `run_dispatch.py`); `constituent_cap.py`'s arg-table
    scan loop (different purpose, coincidental resemblance only).
  - New unit tests: 15 added to `test_cap_shared.py` across the three fixes (7 for
    `_collect_ddt_use_stubs`, 4 for `_rank_of`, 4 for `_assert_call_arg_count_matches_signature`).
    All three of the confirmed findings (#1, #2, #3) are now fixed — nothing left open from
    this sweep except the investigated-and-ruled-out false positives above. Full suite: 321
    passed (306 + 15 new), 1 xfailed. `ruff --select F401` clean except the same pre-existing,
    unrelated `i32` finding in `suite_cap.py` noted in Phase 4.
- ~~`DEVELOPERS.md`'s pass reference table is missing `lower-ccpp-utils` and `fir-to-meta`~~
  **✅ done (2026-07-19).** Both were registered, real passes (`ccpp_opt.py`) that predated this
  refactor and were deliberately scoped out of Phase 5 as unrelated cleanup — picked up now as
  its own small, independent item. Added both to the pass reference table with a note that
  neither is part of the main `ccpp_xdsl` pipeline: `fir-to-meta` is a standalone alternative
  frontend (Flang FIR → CCPP metadata, used by `fir2meta.py`/`ccpp_validate_fir.py`/
  `ccpp_validate_source.py`, not `_build_pipeline`), and `lower-ccpp-utils` lowers remaining
  `ccpp_utils` ops to plain `arith`/`memref`/`llvm` for consumers needing fully-lowered MLIR
  rather than printed Fortran. Docs-only change; full suite unaffected.
- **GPU/OpenACC data-movement follow-up, unrelated to this refactor's own scope (flagged
  2026-07-19).** Surfaced while extending `gpu_ccpp_cap_pass.py`/`gpu_data_pass.py`
  (`generate-gpu-ccpp-cap`/`generate-gpu-data`) to cover all lifecycle phases, not just `_run`
  (local commit, on the `kessler-gpu-acc-fixes` branch — see that branch's commits for the
  DEVICEPTR→present fix, the nvfortran `-noacc`/`ACC_OFF_C` Makefile fix, the lifecycle-coverage
  extension to both GPU passes, and three bugs the new test coverage caught: `_get_device_args`
  hardcoding `<scheme>_run` instead of the actual callee's table, the `__opt`/`__alloc` name-hint
  suffix not being stripped before the suite_cap-level arg lookup, and `KeywordCallOp` not being
  recognized alongside `func.CallOp`). Confirmed via the regenerated `examples/kessler` caps that
  none of `cpair`/`rair`/`rho`/`z`/`exner`/`theta`/`qv`/`qc`/`qr`/`temp_prev`/`ttend_t`/`phis`/
  `st_energy` persist on device across calls — every lifecycle phase
  (`timestep_initial`/`run`/`timestep_final`) opens and closes its own structured
  `!$acc data copyin/copy/copyout ... end data` region, because `kessler_host_mod.meta` never
  declares `memory_space = device` (so every var lands on the `scheme=device + model=host` clause
  path, never `present`). Not a bug — a real transition-period concern for a host model that will
  have a long-lived mix of GPU-resident and not-yet-ported schemes. Two follow-on pieces were
  identified; **"Option 2" is now done, the update-clause item is not implemented, not
  scheduled**:
  - **"Option 2" — cross-function OpenACC data hoisting: done (2026-07-19).** Generalized beyond
    the original fixed-anchor sketch above per the project owner's request: rather than
    hardcoding `timestep_initial`/`timestep_final` as the entry/exit points, `GPUCcppCapPass` now
    computes the actual earliest/latest lifecycle phase each host variable is used in, per suite,
    and hoists `copyin`/`copy`/`copyout` variables to a single unstructured `!$acc enter
    data`/`exit data` pair spanning that real range (with `present()` at any phase strictly in
    between), instead of re-transferring on every call. `present`-clause and `update`-clause
    variables are deliberately excluded — see the follow-on item just below for the latter.
    Covers whole-simulation scope (`register`/`initialize`/`finalize`, entry anchor genuinely
    computed rather than assumed to be `initialize`; exit always forced to `finalize` via a
    synthesized `HostVarRefOp` when the variable has no natural reference there) and per-suite
    scoping (a variable's classification in one suite is unaffected by an unrelated suite's usage
    of a same-named host variable in a multi-suite module, confirmed real via
    `examples/capgen`'s two-suite `CAPS_SUITES` pattern). v1 scope: OpenACC only — the
    `directive="omp"` backend keeps its pre-existing per-call `OmpTargetDataBeginOp`/
    `OmpTargetDataEndOp` path unchanged (known gap, not silently mishandled; see the OMP item
    below).
    - New `AccEnterDataOp`/`AccExitDataOp` ops in the `ccpp_utils` dialect plus printer support
      (`print_ftn.py`), a shared `cap_shared.split_scheme_table_name` helper (scheme arg-table
      name → phase, replacing `gpu_data_pass.py`'s narrower `_get_scheme_name`), and a full
      rewrite of `GPUCcppCapPass` around a `VarLifetime` per-suite/per-host-variable record and a
      two-pass discovery-then-insertion `apply()`. New `tests/unit/test_gpu_data_hoisting.py` (8
      tests: per-timestep hoisting across two schemes, whole-simulation scope including the
      register-only entry-anchor edge case, multi-suite scoping, the present-clause exclusion,
      and an update-clause regression guard). Full suite green throughout (357 unit + 44
      FileCheck, 1 xfailed unchanged), `ruff check` clean.
    - **Copilot review fixes (2026-07-19):** the initial insertion logic anchored every tier
      (`AccEnterDataOp`/`AccExitDataOp`, the structured `AccDataBeginOp`/`AccDataEndOp` region,
      and the update-clause ops) directly at `InsertPoint.before/after(suite_call)`. Since a later
      insertion at that same point always lands closer to `suite_call` than an earlier one,
      whichever tier's code ran last ended up interleaved *inside* the structured region instead
      of outside it — confirmed concretely in regenerated `examples/kessler` output (`!$acc enter
      data copyin(cpair, z)` was landing *after* `!$acc data copy(...)` instead of before it, and
      `exit data` before `end data` instead of after). Fixed by capturing the inserted
      `AccDataBeginOp`/`AccDataEndOp` in local `data_begin_op`/`data_end_op` variables and
      anchoring the enter/exit-data insertions to those ops directly (falling back to
      `suite_call` when no structured region was emitted for that call site), making the nesting
      deterministic regardless of insertion order. Re-verified against `examples/kessler`: correct
      nesting confirmed, full suite still green.
    - **Milestone (2026-07-19): confirmed on the project owner's HPC system (nvhpc/nvfortran)**,
      both before and after the Copilot-review ordering fix — passed CI and manual HPC
      verification.
    - **Second Copilot review finding (2026-07-19), on item 1(a)'s PR: docstring/implementation
      mismatch in `_resolve_lifetime`'s whole-sim rule.** The class docstring said "if any of
      {register, initialize, finalize} reference the variable, it gets whole-simulation scope,"
      but `_resolve_lifetime` only ever accepted `register`/`initialize` as an entry anchor —
      finalize-only one-time-phase usage returned `hoisted=False` unconditionally. The narrow
      case (a variable used *only* at `finalize`, nowhere else at all) is correctly non-hoistable
      (entry would equal exit — nothing to span, same reasoning as the already-documented
      per-timestep degenerate case) and just needed the docstring corrected. But digging further
      surfaced a real, broader gap the narrow framing didn't capture: `_resolve_lifetime` returned
      `hoisted=False` for *any* variable touching `finalize` at all, even one with a genuine
      per-timestep span alongside it (e.g. used at `timestep_initial` + `run` + `finalize`) —
      losing all hoisting benefit for the per-timestep portion too, not just failing to hoist the
      lone `finalize` touch. Decided with the project owner to fix the implementation, not just
      the docstring: `_resolve_lifetime` now falls through to per-timestep hoisting when
      `finalize` is the *only* one-time-phase usage, leaving `finalize` as an independent touch
      outside the hoisted range. This makes `_role_at`'s `"unused"` role reachable for the first
      time (previously commented "not reachable in practice," accurately, before this fix) —
      `_wrap_scheme_call` now folds `"unused"` into the same handling as `"legacy"`, so that
      independent `finalize` touch still gets a correct full per-call transfer, just outside the
      hoisted span. Verified for both the copyin/copy/copyout path and the update path (which
      shares the same `_resolve_lifetime`/`_role_at` machinery) via two new tests in
      `TestFinalizeAlongsidePerTimestepHoisting`. Full suite green (361 unit + 44 FileCheck, 1
      xfailed unchanged), `ruff check` clean.
    - **Third Copilot review comment (2026-07-19), on the same PR: already resolved by the fix
      above.** Flagged the `if not candidates:` branch's comment ("no ... per-timestep usage") as
      claiming a stronger invariant than the code enforced (`not candidates` only means no
      register/initialize usage — per-timestep usage, e.g. `run` + `finalize`, was still
      possible). Checked against the current file: this exact comment was already reworded by the
      fix immediately above (which turned that branch into a fallthrough rather than an
      unconditional return, and rewrote its comment to say "no register/initialize usage"
      precisely, calling out the per-timestep fallthrough explicitly). Confirmed via a repo-wide
      grep that the old phrasing no longer exists anywhere in the file — Copilot's review was
      against the pre-fix commit; no further change needed.
  - **Making the `scheme=host + model=device` (update self/update device) clause path robust —
    (a) done (2026-07-19), (b)/(c) still not implemented, not scheduled.**
    - **(a): hoisting extended to "update" variables — done.** Turned out different from the
      original sketch above (which guessed unconditional whole-simulation anchoring using the
      new enter/exit-data ops): after discussing the design trade-offs with the project owner,
      built as a direct extension of Option 2's existing machinery instead. `_analyze_one_suite`
      now tracks `phases_used` for update-clause variables exactly like copyin/copy/copyout and
      resolves them through the same `_resolve_lifetime` (whole-sim vs per-timestep, genuine
      earliest/latest phase, not a hardcoded anchor); `_role_at`/`_wrap_scheme_call` fire a single
      `AccUpdateSelfOp` at the computed entry phase and a single `AccUpdateDeviceOp` at the exit
      phase instead of a pair at every touching call site, with nothing at all (no directive, no
      assertion) at any phase strictly in between. Deliberately reuses the existing
      `AccUpdateSelfOp`/`AccUpdateDeviceOp` ops, not the new `AccEnterDataOp`/`AccExitDataOp` —
      CCPP doesn't own an update-clause variable's device allocation (the host model does), so it
      should only ever synchronize it, never allocate/deallocate it. **Explicit, accepted risk,
      not silently assumed:** unlike copyin/copy/copyout (pure CCPP-owned scratch device memory,
      invisible to anything outside this framework), hoisting an update variable assumes nothing
      outside this suite's own dispatch — in particular, no GPU-resident code the host model runs
      independently of CCPP (e.g. its own dynamics core) — touches that variable's device copy
      between the suite's calls. CCPP has no way to verify this itself; documented prominently in
      `GPUCcppCapPass`'s class docstring rather than deferred. Currently untested in practice: no
      example in this repo declares a host variable `memory_space = device`, so this path (like
      the update-clause path generally) has zero real exercise beyond its own unit tests —
      `tests/unit/test_gpu_data_hoisting.py`'s new `TestUpdateClauseHoisting` (2 tests: a
      three-phase span confirming sync-once-each-way with nothing at the passthrough phase, and
      an initialize+run-only span confirming the synthesized-reference path forces the device
      sync to `finalize`). Full suite green (359 unit + 44 FileCheck, 1 xfailed unchanged),
      `ruff check` clean.
    - **(c): done (2026-07-21).** Re-scoped after tracing the actual architecture in detail (see
      the follow-on plan below): (c) turned out to be fully solvable today, with no dependency on
      (b). `_analyze_one_suite` now tracks, per host var, which scheme(s) contributed to each of
      the three top-level clause categories (present/update/copy-family) via a new `contributors`
      dict, and a new `_check_no_clause_conflicts` raises a `ValueError` naming the suite, the host
      var, and every conflicting scheme+category, called right before the (unchanged)
      `lifetimes` dict is built. Root cause confirmed precisely, and it's narrower than first
      described: the prior "silent last-write-wins" wasn't actually order-dependent on the
      unordered `scheme_names` set iteration — `present_vars.add(...)`/`update_vars.add(...)` are
      independent sets that both legitimately end up containing a conflicting host var regardless
      of scheme-processing order; the real overwrite was the three lifetimes-construction loops'
      *fixed* code order (present, then update, then copy-family always wins), silent and
      undetected either way. Validated two ways: a new synthetic fixture,
      `TestGPUCcppCapClauseConflict` in `test_gpu_directives.py` (two schemes, one wanting
      `present`, the other `update`, for the same host var in the same suite — asserts the
      `ValueError` fires with both scheme names in the message); and regenerating
      `examples/advection_flat_host`'s caps with `--directive acc` directly, confirming the pass
      now raises for `qv` naming `cld_liq` (present) vs `cld_ice` (update) instead of silently
      emitting the incoherent code the README previously described. README updated to match the
      new loud-error behavior. Full suite green (345 unit + 1 pre-existing unrelated
      environmental failure, 44 FileCheck + 1 xfailed — both unchanged from the pre-fix baseline),
      `ruff check` clean on both touched files.
    - **(b): done (2026-07-21), as a refined hybrid rather than either strawman extreme
      first considered.** Two candidate designs were rejected before landing on this one:
      "always per-call" (simpler, one code path, but throws away real efficiency — repeated
      `update self`/`update device` syncs for consecutive same-classified calls, and losing
      cross-phase hoisting even for vars that don't need to lose it) and "keep detecting and
      erroring on divergence" (today's (c) state, never actually fixes anything). The chosen
      design: `cap_shared.find_diverged_suite_vars(scheme_names, meta_data)` (the same
      contributor-tracking (c) built, narrowed and shared) computes, per suite, which host vars
      genuinely diverge between present and update across contributing schemes — proven that
      divergence can *only* ever be present-vs-update (both require `model_var_memory_space
      ==device`), never involving the copy-family (`model=host`), since that host-declared
      attribute is invariant per var regardless of which scheme references it.
      `GPUCcppCapPass._analyze_one_suite` excludes diverged vars from `present_vars`/
      `update_vars` entirely (no `VarLifetime`, so `_wrap_scheme_call` does nothing for them) —
      **zero behavior change for the common, non-diverging case**, all of item (a)'s cross-phase
      hoisting work stays fully exercised and untouched. `GPUDataPass` (which already operates
      inside the `<suite>_suite_cap` module at exactly the right per-call granularity, via
      `_find_call_in_if`, previously only for host-less `CapScratch` args) is extended
      (`_get_diverged_args`/`_process_diverged_host_vars`) to classify each individual scheme
      call's own need for a diverged var (a pure per-arg computation, no accumulation) and route
      it: `present` touches are emitted individually per call (free to repeat, and coalescing
      them risked producing improperly-nested/criss-crossing `!$acc data` regions across
      *different* diverged vars); `update` touches are coalesced into maximal runs of consecutive
      same-classified calls — correctly *breaking* a run at any interleaved present-classified
      touch for the same var (an unstructured sync spanning across a present call would leave
      that present call observing a stale device copy — a real correctness bug that a naive
      "first update touch to last update touch" span would have introduced; caught during
      implementation, not assumed away). No new IR ops needed — reuses
      `AccDataBeginOp(present=...)`/`AccDataEndOp`/`AccUpdateSelfOp`/`AccUpdateDeviceOp` (and OMP
      equivalents) exactly as `GPUCcppCapPass` already used them for the single-classification
      case.
      - **A real implementation bug found and fixed before landing:** `suite_cap.py` unifies
        same-`standard_name` args from *different* schemes into a single shared function
        parameter, named after whichever scheme's own local arg name was encountered first
        (confirmed empirically, not assumed) — so a later-contributing scheme's own local name
        (e.g. `qv_b`) is *never* itself a block-arg key; only the "winning" name (`qv_a`) is.
        First implementation silently dropped every touch using a losing local name. Fixed by
        resolving one canonical SSA reference per diverged host var (try every local name any
        contributing call used until one resolves), rather than trying to reproduce
        `suite_cap.py`'s own dedup-naming logic.
      - **DDT-member side benefit, validated not just asserted:** since this all operates on
        suite_cap's already-resolved plain block arguments (DDT resolution already happened
        upstream, building the call *into* this suite's dispatch function), it works correctly
        for DDT-member host vars too — unlike `GPUCcppCapPass`'s `HostVarRefOp`-based lookup
        (gap #5 below), which can't see them at all. Confirmed with a dedicated new DDT-member
        unit fixture (`TestGPUDivergedClauseRoutingDDTMember`), not just claimed from the
        architecture.
      - Validated against the real reproduction vehicle: regenerating
        `examples/advection_flat_host` with `--directive acc` now compiles cleanly (no
        `ValueError`) — `cld_liq_run`'s call wrapped in `present(qv)`, `cld_ice_run`'s in
        `update self(qv)`/`update device(qv)`, `temp` (non-diverging) unaffected on the
        unchanged whole-suite `copy(...)` path. README updated accordingly.
      - **Deliberately excluded from this scope:** the multi-group `_ccpp_physics_run`
        discovery gap (next item below) — it's a separate, orthogonal bug in the *outer*
        dispatch's call-site enumeration, affecting every var kind `GPUCcppCapPass` still
        handles (unified present/update and all copy-family vars), not specific to divergence
        routing. Bundling it in would have blurred this change's review surface; it remains its
        own tracked follow-up, unchanged below.
      - Full suite green (349 passed unit tests, 44 FileCheck + 1 xfailed — same single
        pre-existing unrelated environmental failure as every prior phase), `ruff check` clean
        on every touched file.
  - **A fourth, previously-unnamed sub-item found while scoping (b), now Phase 7 is done
    (2026-07-20): the multi-group `_ccpp_physics_run` discovery gap.** `GPUCcppCapPass`'s
    `_find_inner_suite_part_if` does a flat scan of the outer suite branch's block and returns on
    the *first* `scf.IfOp` it finds whose true-region contains a `_suite_physics*` call. Traced
    `run_dispatch.py`'s actual construction of the suite-part dispatch chain: when a suite has
    more than one XML `<group>`, each group's dispatch `IfOp` is nested in the *false-region* of
    the next, so only the last-processed group's `IfOp` is a direct sibling in the block being
    scanned — every other group's call site is silently never instrumented for cross-function
    hoisting. Confirmed currently unexercised (not just theoretical): `examples/capgen` and
    `examples/ddthost`'s `temp_suite.xml` are the only two-group suites in the repo, and neither
    declares any `memory_space` metadata, so `GPUCcppCapPass.apply()` exits before ever reaching
    this code path.
    - **Investigated whether this is a small standalone fix — it is not.** Naively walking the
      whole nested if/else chain and calling `_wrap_scheme_call` once per discovered group would
      not just add coverage, it would introduce two new bugs, because `_wrap_scheme_call`'s
      role/reference lookup scans the *shared* outer block for `HostVarRefOp`s — and that block
      is genuinely shared across every group (`run_dispatch.py` accumulates
      `suite_host_refs`/`suite_array_secs` from *all* groups into one list, placed once in the
      common ancestor block specifically so it dominates every nested group branch, per SSA
      scoping rules). The lookup has no concept of "does *this specific group's* call actually use
      this var" — only "does a ref for this var exist anywhere in the suite, at this phase."
      Confirmed via `run_dispatch.py`'s `ccpp_physics_suite_part_list` machinery that each group
      is invoked as a genuinely separate, host-driver-issued call per timestep (not one combined
      call), which makes both failure modes real rather than hypothetical: (1) *misattribution* —
      a var used only by group1's scheme could get a directive inserted around group2's call too;
      (2) *duplicate reference-counted directives* — a var whose hoisted entry/exit phase is
      `"run"` and genuinely used by multiple groups would get `AccEnterDataOp`/`AccExitDataOp`
      fired once per group's separate invocation per timestep, an unbalanced enter:exit ratio
      under OpenACC/OMP's reference-counted semantics — a real device-memory bug, not just
      redundant work. A correct fix needs per-*group* variable usage tracking (not just
      per-phase) and directive insertion driven by each group's own call operands, not a blind
      scan of the shared block — genuinely the same class of work as (b)'s redesign, not a
      separable small patch.
    - **Decision (2026-07-20, explicit user choice): defer entirely to (b).** A narrower
      "detect multi-group suites and skip run-phase hoisting for them" guard was offered as a
      smaller, safe interim option and declined in favor of folding this into (b)'s eventual
      redesign. No code changed as a result of this investigation.
  - **Sequencing finding: (b)/(c) should wait for Phase 7 (full IR unification, below), not be
    attempted before it — Phase 7 is now done (2026-07-20), so this is no longer a live blocker.**
    Phase 7's whole point was making "which bucket does this scheme arg fall into" a single
    durable-IR decision instead of the three independently-computed heuristics scattered across
    `suite_cap.py`/`ccpp_cap.py`/`run_dispatch.py` (and its own text already flagged
    `lifecycle_cap.py` as blocked on it). Per-scheme-call GPU clause routing needs an analogous
    per-argument, computed-once classification; building it before Phase 7 would have meant a
    fourth ad hoc heuristic Phase 7 would then have to reconcile or replace. Note this connection
    is looser than it first sounds: `ownership_kind` doesn't decide *which* GPU clause an arg
    needs (that's still a fresh, separate memory_space-based question) — the real overlap is that
    GPU-clause-relevant args are exactly the `ownership_kind == HostMatched` subset (both gate on
    the same underlying `model_var_name` presence), so (b) could read that instead of
    re-deriving the same check, but still has to build its own new per-scheme-call classification
    from scratch, following Phase 7's pattern rather than reusing its actual enum. Option 2 and
    the enter/exit-data lifecycle piece of (a) never had this dependency and proceeded
    independently, as already recorded above.
  - **Two new backlog items found while scoping (b)/the advection example (2026-07-20), neither
    scheduled:**
    - **Silent no-op: `memory_space` declared on a non-`HostMatched` arg does nothing, with zero
      feedback.** Metadata parsing has no schema validation — `CCPPArgument`/`ArgumentOp` just
      store whatever properties are set. Both `GPUDataPass` and `GPUCcppCapPass` gate their whole
      analysis on `arg.hasAttr("model_var_name")` before ever consulting `memory_space`, so a
      scheme author declaring `memory_space = device` on a `CapScratch`-classified arg (e.g.
      `apply_constituent_tendencies`'s `const_tend`/`const`, which resolve via
      `FRAMEWORK_STD_NAME_TO_CAP_VAR` to cap-owned module variables, never matched against host
      metadata at all) gets no error, no warning, nothing — exactly the silent-misconfiguration
      pattern this session has repeatedly hunted down elsewhere (Stage 3's 38-file pipeline gap,
      the Copilot-flagged `ownership_kind` fallback). Small, independent fix: a validation
      check (in `HostVariableMatchPass` or a small new pass) that raises/warns whenever an arg
      declares `memory_space` but isn't `HostMatched`.
    - **Missing capability, not a bug: `CapScratch` args have no GPU-residency story at all.**
      Actually making `memory_space=device` do something useful for e.g.
      `apply_constituent_tendencies` would mean teaching `cap_var_map`'s scratch-array allocation
      path (`lc_constituent_array`, `lc_const_tend`, etc. — cap-module-scope arrays, potentially
      large, dimensioned by ncol×pver×ntracers) about `!$acc enter data create(...)`/OMP
      equivalents — a genuinely new capability, not a routing fix, and a plausible real want for
      CCPP-GPU users given how large constituent-tendency arrays typically are. Separate, larger
      backlog item from (b)/(c), which are scoped to `HostMatched` args only.
    - **A third, distinct missing capability, found 2026-07-21 while reviewing the project
      owner's manual OpenACC edits to `examples/advection`: `SuiteOwned` args have no
      GPU-residency story either, and it's a genuinely separate gap from `CapScratch` above, not
      the same one under a different name.** Concretely hit this reviewing `cld_ice.meta`'s
      `cld_ice_array` (`advected = .true.`, so `SuiteOwned` per `classify_arg_ownership`) marked
      `memory_space = device` — inert today, for a different reason than the `CapScratch` case.
      `SuiteOwned` variables are allocated and owned by `suite_cap.py`/`suite_variable_model.py`
      at the *suite* level (inside the generated `<suite>_suite_cap` module) — a structurally
      different allocation path from `CapScratch`'s `cap_var_map` in `ccpp_cap.py` (the top-level
      `ccpp_cap` dispatcher module). They share a conceptual shape — both are framework-owned
      scratch memory the host never sees — but building `CapScratch` residency would not, by
      itself, do anything for `SuiteOwned` variables; the actual code that would need to change
      (`suite_cap.py`/`suite_variable_model.py`'s own allocation-and-storage logic, not
      `ccpp_cap.py`'s) is different.
      - **Done (2026-07-22), triggered by a real GPU runtime failure**, not just the earlier
        static observation above: running `examples/advection_flat_host`'s GPU-compiled code on
        real HPC hardware produced `FATAL ERROR: data in PRESENT clause was not found on device:
        name=cld_liq_array(:,:)` — `cld_liq_init`'s own hand-written
        `!$acc parallel loop ... present(cld_liq_array)` asserting residency nothing established.
        `SuiteVarEntry` (`suite_variable_model.py`) gained a `needs_device_residency: bool` field,
        computed from `memory_space=device` on *any* occurrence of the var across every scheme/
        phase table (an OR, not a first-writer-only read — `_process_table`'s "Case 4: already in
        suite data" branch previously discarded every later occurrence's attributes entirely,
        confirmed real via `cld_ice_array` appearing in both `cld_ice_init` and `cld_ice_run`).
        No present-vs-update-style divergence check needed here, unlike `HostMatched` — a
        `SuiteOwned` var's residency need is a simple boolean, never conflicting across schemes.
        `LazyAllocOp` (`ccpp_utils.py`) gained a `needs_device_residency` property, and its own
        printer (not a separately-inserted op) now emits `!$acc enter data create(x)` *inside* the
        same `if (.not. allocated(x))` guard the allocate itself uses — deliberately not a
        separate `AccEnterDataOp` insertion, since these vars can be allocated from either of two
        lifecycle functions (`_suite_register`/`_suite_initialize`, whichever runs first); a
        separately-inserted enter-data op after each of the two `LazyAllocOp` occurrences would
        double-fire regardless of which one's allocate actually ran, double-incrementing the
        OpenACC reference count. `_suite_finalize` (confirmed to have zero competing ops and to
        run exactly once) gets a matching `AccExitDataOp`/`exit data delete` — but only for vars
        whose enter-data-create is confirmed, by scanning the actual generated IR, to have really
        fired: a `SuiteOwned` var's allocation dimensions aren't always resolvable outside
        physics_mode (found via `examples/helloworld`'s own `temp_layer`, which declares
        `memory_space=device` but uses `horizontal_loop_extent` as its dimension — never
        resolvable in `_register`/`_init`, so `_build_framework_refs` never emits a `LazyAllocOp`
        for it there at all). The first implementation keyed the exit side purely off
        `suite_model`'s static classification and produced exactly this bug — an unmatched
        `exit data delete` with no corresponding enter, caught via `examples/helloworld`'s
        existing FileCheck goldens (legitimately regenerated once for `temp_layer`'s new residency
        treatment, then regenerated back to byte-identical once the fix was in, since the fix
        correctly excludes it). ACC only; OMP deferred as its own later follow-on, matching this
        project's established practice (`SuiteCAP` has no `directive` field today, and adding one
        for this alone isn't justified). New unit tests in
        `tests/unit/test_suite_owned_residency.py` cover: enter-data inside the alloc guard,
        matching exit-data in `_suite_finalize`, a non-resident regression guard, and the
        second-table-occurrence OR fix. `examples/advection_flat_host/cld_liq.meta`'s
        `cld_liq_array` and `cld_ice.meta`'s `cld_ice_array` both gained the
        `memory_space = device` declaration needed to actually activate this (the code alone
        doesn't retroactively fix the reported error without it) — regenerating with
        `--directive acc` now shows the correct `enter data create`/`exit data delete` pair for
        both, with `temp` (the unrelated, non-diverging `HostMatched` var) unaffected. Full suite
        green (353 unit + 44 FileCheck + 1 xfailed, same 1 pre-existing unrelated environmental
        failure), `ruff check` clean (same 13 pre-existing baseline findings, confirmed unchanged
        via `git stash`). Not yet verified on real GPU hardware — that remains with the project
        owner to confirm the reported error is actually resolved.
    - **`HostMatched` present/update residency: done (2026-07-22), a third residency capability
      alongside `SuiteOwned` and (still-unbuilt) `CapScratch`, prompted by the very next expected
      GPU runtime failure once `SuiteOwned` residency was fixed** —
      `FATAL ERROR: data in PRESENT clause was not found on device: name=qv(:,:)` on real HPC
      hardware, for `examples/advection_flat_host`'s `qv` (`HostMatched`, diverging between
      `cld_liq_run`'s `present` and `cld_ice_run`'s `update` — backlog item (b)'s routing was
      already correct; nothing had ever established `qv`'s residency in the first place, since
      `present()`/`update self`/`update device` are pure assertions/syncs that never allocate
      anything, by this pass's own long-standing design). The project owner asked directly whether
      hand-writing `!$acc enter data create(qv)` (mirroring `cld_ice.F90`'s `tcld`) was really the
      right long-term answer, given users have no way to discover they need to — the answer: no,
      xdsl_ccpp can and should establish this automatically, driven by the same `memory_space =
      device` metadata already inert here, the same shape of fix as `SuiteOwned` residency. Does
      **not** weaken the "host model manages present-clause residency independently" principle:
      OpenACC's `enter data`/`exit data` are reference-counted, so CCPP establishing residency
      alongside a real host model's own independent management is safe (an extra, balanced
      increment/decrement), making this a strict improvement with no downside when something else
      already manages it.
      - **Built as a new, deliberately separate analysis/emission path in `gpu_ccpp_cap_pass.py`**
        (`_analyze_one_suite_residency`/`_analyze_suite_residency_lifetimes`/
        `_wrap_residency_directives`), not integrated into the existing `present_vars`/
        `update_vars`/`_wrap_scheme_call` machinery — lower risk than modifying that already-
        intricate, working code, at the cost of a var needing both residency and a present()/update
        assertion getting two adjacent directives at a call site instead of one merged one (a real
        but minor, explicitly-flagged verbosity/redundancy tradeoff, not a correctness one).
        Entirely self-contained within `GPUCcppCapPass` — no changes to `gpu_data_pass.py`, no new
        IR ops (`AccEnterDataOp`/`AccExitDataOp`/`AccDataBeginOp`/`AccDataEndOp` and OMP equivalents
        all already existed). Residency doesn't care about present-vs-update divergence at all
        (unlike clause routing) — it's a simple "does anything declare `model_var_memory_space ==
        device`" union across every scheme, computed independently of
        `cap_shared.find_diverged_suite_vars`.
      - **Key correctness insight, found by tracing two consecutive timesteps, not assumed:**
        `_resolve_lifetime`'s existing "degenerate" (single-phase) case returns `hoisted=False`,
        which for copy-family vars does *not* mean "do nothing" — `_wrap_scheme_call`'s "legacy"
        role still wraps a plain per-call structured `copy()` region around every invocation (this
        is `temp`'s own existing, unchanged treatment, since it's also single-phase). Naively
        treating `hoisted=False` as "skip residency" (matching present's *current* clause behavior)
        would have silently reproduced the exact bug being fixed for `qv`, which is used only at
        `_run`. The correct model: a degenerate residency var also gets a plain per-call `copy()`
        region, every invocation — redundant (each timestep's fresh copyin re-uploads whatever the
        previous timestep's own exit-copyout, or `qv`'s own existing `update device` call, already
        wrote back to host) but never stale or wrong. A multi-phase var gets real hoisting instead
        (entry/exit anchors, no per-call re-transfer) — both cases reuse `_resolve_lifetime`/
        `_role_at` completely unchanged, since neither actually depends on the `kind` string beyond
        what the caller does with it.
      - Regenerating `examples/advection_flat_host` with `--directive acc` confirms the concrete
        fix: `qv`'s new `!$acc data copy(qv(col_start:col_end, 1:pver))` region nests correctly
        around `temp`'s existing, unchanged one, both wrapping the whole group dispatch call — by
        the time `cld_liq_run`'s `present(qv)` executes, `qv` is genuinely on the device.
      - **Several existing tests asserted the old, incorrect-in-hindsight behavior** ("present-
        clause vars never get enter/exit-data," "finalize/register are always untouched," "diverged
        vars get zero `!$acc` at the ccpp_cap level") and were updated to assert the new, correct
        behavior precisely rather than loosened carelessly — e.g. `test_gpu_directives.py`'s
        `TestGPUDivergedClauseRouting` now separately asserts *no clause routing* at the ccpp_cap
        level (still true, still `GPUDataPass`'s job) *and* a residency `copy()` region there (new,
        correct). New dedicated coverage in `tests/unit/test_gpu_residency.py` (single-phase
        present/update vars, multi-phase hoisted var, copy-family regression — confirms
        `model_var_memory_space != device` vars are completely untouched by this new mechanism).
      - ACC coverage added; OMP directive path implemented but currently untested/deferred as a separate
        follow-on, matching this project's established practice. Inherits the already-known, separately-tracked multi-group `_ccpp_physics_run`
        discovery limitation (reuses the same call-site discovery `_wrap_scheme_call` already used)
        — not fixed here, same explicit deferral as backlog item (b).
      - Full suite green (360 unit + 44 FileCheck + 1 xfailed, same 1 pre-existing unrelated
        environmental failure), `ruff check` clean. Not yet verified on real GPU hardware.
      - **Note:** this also means item (a)'s "currently untested in practice: no example in this
        repo declares a host variable memory_space=device" (above) is no longer accurate — `qv` in
        `examples/advection_flat_host` now genuinely exercises the update-clause hoisting path too,
        via this new residency mechanism working alongside it.
    - **A fourth, related gap found the same day: module-private scheme state (not a
      ccpp-arg-table entry at all) has no GPU-residency story, and can't, without first making
      it CCPP-visible somehow.** Surfaced concretely by `cld_ice.F90`'s own `tcld` — a
      `real(kind_phys), private` module variable (not a dummy argument, not in any `.meta` file),
      set on the host in `cld_ice_init` and read inside `cld_ice_run`'s `!$acc parallel` region.
      xdsl-ccpp's cap-generation pipeline only ever knows about what's declared in `.meta` files
      — a variable that's genuinely private to the scheme's own module is invisible to it by
      construction, so there is no way for xdsl-ccpp to emit `!$acc declare create(...)`/
      `update device(...)` for it automatically, *regardless* of `HostMatched`/`CapScratch`/
      `SuiteOwned` residency support: none of those apply to something that was never an
      arg-table entry in the first place. Two genuinely different paths exist, and they're
      mutually exclusive:
      1. **Chosen for now (2026-07-21): keep it module-private, hand-write the OpenACC
         directives in the scheme's own source** — `!$acc declare create(tcld)` at module scope,
         `!$acc update device(tcld)` right after computing it in `cld_ice_init`. Self-contained,
         no xdsl-ccpp changes, works today; the tradeoff is it's manual, not something xdsl-ccpp
         manages or could ever validate.
      2. **Not chosen — would require real, unscoped work:** make the variable CCPP-visible by
         turning it into a real arg-table entry (as `cld_liq`'s equivalent `tcld` already is) and
         marking it `memory_space=device`, which would only actually do something once the
         `SuiteOwned` residency capability above is built to consume that annotation at
         `suite_cap.py`'s suite-level allocation site. This was the path first tried for
         `cld_ice`'s `tcld` before backing it out in favor of option 1 — reverting it changed the
         scheme's own call signature, which the project owner didn't want as a side effect of a
         GPU-residency fix.
      Worth deciding later, once `SuiteOwned` residency is actually scoped: should xdsl-ccpp gain
      some way to flag "this module has private state read inside an `!$acc` region with no
      corresponding arg-table entry" at all — genuinely hard, since it would require parsing
      scheme `.F90` source (which xdsl-ccpp never does today, treating schemes as opaque behind
      their declared metadata interface), not just reading `.meta` files.
    - **A fifth gap, found 2026-07-21 while trying to build a real (b)/(c) test case in
      `advection`, and more fundamental than any of the above: `GPUCcppCapPass` has *zero*
      support for `HostMatched` args that are DDT members.** `temp`/`qv`/`ps` in `advection` all
      resolve to `phys_state%Temp`/`phys_state%q(:,:,index_of_water_vapor_specific_humidity)`/
      `phys_state%ps` — real DDT members, not plain module scalars/arrays. Confirmed directly by
      running `GPUCcppCapPass` on `advection`'s generated cap and inspecting the actual IR: a DDT
      member's host reference is a `HostVarRefOp("phys_state", ...)` (the DDT *instance*) plus a
      separate member-access mechanism — never a `HostVarRefOp` named `"Temp"` or
      `"q(:,:,...)"` directly. `_wrap_scheme_call`'s reference-scanning loop only ever looks for
      a `HostVarRefOp` whose `var_name` matches the lifetime dict's key exactly, so a DDT member
      is silently invisible to it — not misclassified, never found at all. Verified the
      *classification* itself is fine (`_analyze_suite_var_lifetimes` correctly computes
      `kind="copy"`/`"update"` for these), it's purely the directive-insertion side that never
      fires — so neither `cld_liq` nor `cld_ice` ever got *any* `!$acc` treatment for `temp`/`qv`
      in the example, agreement or conflict, the whole time this was being built. This closes an
      "open question" flagged much earlier in this same GPU backlog ("no example anywhere in
      this repo exercises a DDT member's device residency... is currently an open question") —
      it's now confirmed broken, not just unverified. Independent of `(b)`/`(c)`: this is about
      *reference resolution* for directive insertion, not per-scheme-call classification
      granularity — fixing one doesn't require or unblock the other. Not scheduled, not scoped
      in detail yet (would need `_wrap_scheme_call`/`_resolve_array_refs`/`_synthesize_ref` to
      recognize a DDT-instance-plus-member-access reference shape, presumably mirroring however
      `host_var_match_pass.py`/`suite_cap.py` already represent DDT member access elsewhere).
    - **Fifth gap: implemented (2026-07-22).** Prompted by a direct question — since
      `advection_flat_host` was built flat specifically to avoid this, was the DDT problem still
      open? Confirmed empirically first (not from this note alone): running `examples/advection`
      through the *actual* full production pipeline (its own two FileCheck fixtures happen to omit
      `generate-host-match` from their `RUN` line, an unrelated pre-existing quirk, which is why an
      earlier session's inspection looked like `temp`/`qv` were `CapScratch`, not `HostMatched` —
      with `generate-host-match` included, they correctly resolve `HostMatched`, DDT and all) showed
      `GPUCcppCapPass` established **zero** `!$acc` treatment for `phys_state%Temp`/`phys_state%q`
      — not just missing present/update residency as originally scoped above, but missing even the
      ordinary `copy()` region an equivalent plain host var already got. Root cause, traced in both
      directions: `host_var_match_pass.py` annotates a DDT-member scheme arg with `model_var_name`
      = the bare member name (e.g. `"Temp"`) and `model_module_name` = the DDT *type table's* name
      (e.g. `"physics_state"`, not the Fortran instance variable); `run_dispatch.py` separately
      resolves that type name to the real instance (`"phys_state"`, via `_resolve_ddt_access_path`
      + `ddt_instance_map`/`ddt_parent_map`, plus `_resolve_member_subscripts` for array-section
      members) when building the actual `HostVarRefOp(var_name="phys_state", member_name="Temp")`.
      Every place in `gpu_ccpp_cap_pass.py` that scanned for a matching `HostVarRefOp`
      (`_wrap_scheme_call`, `_resolve_array_refs`, `_wrap_residency_directives`,
      `_collect_donor_host_var_refs`/`_synthesize_ref`) compared against `op.var_name.data` alone
      (`"phys_state"`) — never equal to the lifetime dict's key (`"Temp"`). Classification was
      computed correctly; directive insertion silently found nothing to attach to.
      - Fixed by extracting `_resolve_ddt_access_path`/`_resolve_member_subscripts` from
        `run_dispatch.py` into `cap_shared.py` (pure functions, zero coupling to
        `run_dispatch.py`'s own internals — a clean relocation, not a duplication;
        `run_dispatch.py` now imports them back), adding `_build_ddt_resolution_maps` and
        `_resolve_host_var_key` there too, and using `_resolve_host_var_key`'s resolved
        `"instance%member"` identity (matching a new `_ref_key` helper on the IR-scanning side) as
        the dict key everywhere in `gpu_ccpp_cap_pass.py` instead of the bare `model_var_name` —
        for a plain host var this is a no-op (same bare name), so every existing non-DDT test is
        unaffected by construction.
      - Deliberately did **not** touch `find_diverged_suite_vars` (`cap_shared.py`) — it's purely
        metadata-driven, shared with `GPUDataPass` (which already handles DDT members correctly,
        working on already-resolved `suite_cap`-level block arguments rather than scanning
        `HostVarRefOp`s), and changing its key convention would have broken that working path. The
        existing diverged-DDT-member regression test
        (`test_gpu_directives.py::TestGPUDivergedClauseRoutingDDTMember`) still passes unchanged,
        confirming this.
      - New coverage: `tests/unit/test_ddt_member_residency.py` — present, copy-family, multi-phase
        hoisting, and residency-establishment cases for a DDT-member host var, each verified to
        fail without the fix (temporarily reverted, confirmed all four fail) and pass with it.
      - Regenerating `examples/advection` with the real full pipeline (`generate-host-match`
        included) confirms `phys_state%Temp`/`phys_state%q(...)` now get a real
        `!$acc data copy(...)` region — the concrete backlog scenario, resolved. Deliberately did
        not modify `examples/advection`'s own two FileCheck fixtures (they omit
        `generate-host-match` on purpose/by long-standing accident — out of scope here) or its
        metadata (shared example, other tests depend on its current form) — verification here is
        read-only regeneration + grep, not a new permanent fixture.
      - Full suite green (`pytest tests/unit -q`/`tests/filecheck -q`, same one pre-existing
        environmental failure as every prior phase; 412 unit passed, up from 408 by exactly the 4
        new tests), `ruff check` clean (same 16 pre-existing, unrelated findings in
        `run_dispatch.py` as before this change — zero new findings).
    - **Future test vehicle for the above, once it's actually built (2026-07-21, not scheduled,
      not part of (b)/(c)) — a third `advection` variant with `apply_constituent_tendencies`
      GPU-enabled.** Discussed with the project owner: `CapScratch` residency is a real
      efficiency (arguably correctness) requirement, not just a nice-to-have, the moment a
      GPU-resident scheme's output has to flow through cap-owned scratch memory to reach another
      scheme — and `advection` already has a live preview of exactly this shape: `cld_liq`'s/
      `cld_ice`'s own `cld_liq_tend`/`cld_ice_tend` args (each `CapScratch` themselves, confirmed
      via `classify_arg_ownership` — no host match, not in `FRAMEWORK_STD_NAME_TO_CAP_VAR`, falls
      through to the generic scratch case) feed into the combined `lc_const_tend`/
      `lc_constituent_array` that `apply_constituent_tendencies` consumes directly. For this to be
      a *meaningful* test once the capability exists — not just "does allocation-time `enter data
      create(...)` work in isolation" — it needs `memory_space=device` on **both ends**: the
      producer (`cld_liq_tend`/`cld_ice_tend`) and the consumer (`apply_constituent_tendencies`'s
      `const`/`const_tend`), so it actually exercises data written by a GPU-resident producer
      correctly reaching a GPU-resident consumer through cap-owned scratch memory. Deliberately
      not the same `advection` variant as the (b)/(c) validation plan below (which explicitly
      leaves the constituent-tendency plumbing untouched, since the mechanism doesn't exist yet) —
      a separate variant, for a separate, later capability.
    - **`CapScratch` residency: implemented (2026-07-22).** The third and last residency gap,
      closing this whole GPU-residency backlog thread (`SuiteOwned`'s `LazyAllocOp` and
      `HostMatched`'s `_analyze_one_suite_residency`/`_wrap_residency_directives` were already
      done). Triggered by the exact reported runtime error this backlog anticipated: `FATAL ERROR:
      data in PRESENT clause was not found on device: name=cld_liq_tend(:,:)`. Key finding: unlike
      `SuiteOwned`'s `LazyAllocOp` (a real IRDL op that could carry a `needs_device_residency`
      property), `constituent_cap.py`'s `_generate_constituent_api` builds the entire constituent
      registration/query API as raw Fortran **text** in a single `ConstituentApiOp` (plain
      `StringAttr` body) — there's no IR-level mechanism to attach a residency property to, so the
      fix is string-templated directly into that generation code.
      - `ccpp_cap.py`'s `_build_cap_var_map` gained OR-across-occurrences residency tracking (same
        fix shape as `suite_variable_model.py`'s Case 4): the generic-scratch path
        (`scratch_var_list`, now a 5-tuple with a `needs_device_residency` flag) and the direct
        framework-mapped path (`const`/`const_tend` → `lc_constituent_array`/`lc_const_tend`, now
        tracked via a new `framework_var_residency` dict) both OR every occurrence's own
        `memory_space=device` into the shared entry, rather than "first occurrence wins."
        Constituent-tendency scratch vars (e.g. `cld_liq_tend` → `lc_cld_liq_tend`) are Fortran
        pointer slices into `lc_const_tend`, not separately allocated — their residency request
        rolls up into `lc_const_tend`'s, not a separate entry.
      - Enter side: `constituent_cap.py`'s `_generate_constituent_api` emits
        `#ifdef USE_GPU` / `!$acc enter data copyin(...)` / `#endif` directly after each array's
        `allocate(...)` in `ic_lines`, for `lc_constituent_array`, `lc_const_tend`, and any generic
        (non-constituent-pointer) scratch array whose residency flag is set.
      - Exit side: a new `_inject_capscratch_gpu_exit` in `ccpp_cap.py`, mirroring
        `suite_cap.py`'s `_inject_suite_owned_gpu_exit` exactly (same `HostVarRefOp`+
        `AccExitDataOp(delete=...)` pattern, inserted before the target function's
        `func.ReturnOp`) but **unconditional**, not per-suite-gated — these arrays are
        cap-module-global, not suite-scoped, so the insertion targets the combined cap's own
        `_ccpp_physics_finalize` directly rather than each suite's `_suite_finalize`.
      - Companion metadata: `memory_space = device` added to `examples/advection_flat_host`'s
        `cld_liq.meta`'s `cld_liq_tend` (the producer; no `cld_ice`-equivalent tendency arg exists
        in this example, so nothing to add there) and `apply_constituent_tendencies.meta`'s
        `const`/`const_tend` (the consumer) — activating the mechanism for the reported scenario.
      - Regenerating `advection_flat_host` confirms `lc_constituent_array`/`lc_const_tend` now get
        `!$acc enter data create(...)` in `flat_host_ccpp_initialize_constituents` and
        `!$acc exit data delete(...)` in `flat_host_ccpp_physics_finalize`.
      - Side effect, not a regression: `examples/advection`'s existing FileCheck fixtures changed
        too — `temp`/`qv` in that example already carry `memory_space=device` (for the unrelated,
        still-unfixed HostMatched-DDT-member gap noted above) and, in `advection` specifically,
        fall through to `CapScratch` (no host match resolves for them there), so they now
        correctly get `lc_temp`/`lc_qv` enter/exit-data treatment they were silently missing
        before. Fixtures updated to match.
      - New coverage: `tests/unit/test_capscratch_residency.py` — constituent-tendency scratch var
        residency (enter/exit for `lc_const_tend`), the direct framework-mapped path activating
        `lc_constituent_array` independently of `lc_const_tend`, a non-resident regression guard,
        and the OR-across-occurrences fix itself (two different groups feeding the same
        constituent-tendency standard_name, only the second declaring `memory_space=device`,
        still activates residency for the shared array — the exact case the old
        first-occurrence-wins gate would have silently dropped).
      - Full suite green throughout (unit + FileCheck, same one pre-existing environmental
        failure as every prior phase), `ruff check` clean on touched files. Not verified: actual
        GPU hardware behavior — this sandbox has no compiler/accelerator access; the user
        confirms on their HPC system.
      - **Post-merge fix #1 (2026-07-22): real CI build failure, not just a local-test gap.**
        `constituent_cap.py`'s raw-text `ConstituentApiOp` body prints every line through the
        same indentation-prefixing path as ordinary Fortran statements
        (`print_ftn.py`'s `case CCPPConstituentApiOp():` just called `self.print(line)` for
        each line unconditionally) — so the new `#ifdef USE_GPU`/`#endif` lines picked up the
        module-body indent along with everything else, landing as `  #ifdef USE_GPU` in the
        generated `.F90`. gfortran's `-cpp` rejects an indented `#` as invalid Fortran source
        rather than recognizing it as a directive (`Error: Invalid character in name`) — this
        broke the real `examples/advection_flat_host` build in CI (`make check`) even though the
        local FileCheck suite passed, since FileCheck's whitespace matching is lenient and never
        would have caught it. Fixed in `print_ftn.py`: lines starting with `#` inside
        `CCPPConstituentApiOp`'s body are now printed with `use_prefix=False` (stripped of
        leading whitespace first), matching the pattern every other `#ifdef`-emitting op
        (`CCPPAccEnterDataOp`/`CCPPAccExitDataOp`/`CCPPLazyAllocOp`) already used. Confirmed by
        regenerating `flat_host_ccpp_cap.F90` directly and checking column position; user
        confirmed the real CI build (which does invoke gfortran, unlike anything in this
        sandbox) now succeeds.
      - **Post-merge fix #2 (2026-07-22): Copilot review on PR #38 — `create` vs `copyin`.**
        Flagged at all three CapScratch enter-data sites in `constituent_cap.py`
        (`lc_constituent_array`, `lc_const_tend`, and the generic per-scratch-var case):
        `!$acc enter data create(...)` allocates uninitialized device memory — it does **not**
        copy the host-initialized values from the default-value loop (`lc_constituent_array`) or
        the `= 0.0_kind_phys` fills (`lc_const_tend`, generic scratch vars) that immediately
        precede each directive. Any device kernel reading these arrays before writing them would
        see garbage, not the initialized host state. A real, confirmed bug — `copyin` (already
        the established pattern for `HostMatched` residency's own enter-data, see
        `gpu_ccpp_cap_pass.py`) copies host to device instead of leaving it uninitialized, and is
        the correct fix for all three sites since each is genuinely preceded by host
        initialization. Fixed by changing all three `create(...)` calls to `copyin(...)`; updated
        `tests/unit/test_capscratch_residency.py`'s assertions and both `examples/advection`
        FileCheck fixtures (`lc_temp`/`lc_qv`, which hit the same generic-scratch-var code path)
        to match. Full suite re-verified green; `ruff check` clean (no new findings beyond the
        pre-existing, unrelated F541 baseline already present throughout this file).
  - **Plan for validating (b)/(c) against a real example, not just synthetic fixtures
    (2026-07-20, not yet implemented) — modify `examples/advection/` directly, single group,
    no new example directory.** Originally proposed splitting `cld_suite.xml`'s one "physics"
    group into two, specifically so `cld_liq`/`cld_ice` would land in *different* groups and
    exercise the multi-group `_ccpp_physics_run` discovery bug above at the same time. Rejected
    (2026-07-20): changes the form of the existing, shared advection example (5 other test files
    depend on it) for a benefit the actual data-movement scoping work doesn't need — an intra-group
    transition between two schemes that genuinely disagree about a host var's residency needs
    only two *different schemes* with divergent `memory_space` settings, not two *groups*.
    `cld_liq`/`cld_ice` already sit in the same single group today, so this is achievable as
    metadata-only additions to the existing example, no restructuring, no new directory:
    - `temp` (real DDT member, `phys_state%Temp`, referenced by both `cld_liq_run` and
      `cld_ice_run`): `memory_space=device` on both — the DDT-residency validation (never
      exercised by any real example today) plus the compatible-union case (two schemes agree).
    - `qv` (`phys_state%q(:,:,index_of_water_vapor_specific_humidity)`, also referenced by both):
      host side (`test_host_data.meta`) gets `memory_space=device`; `cld_liq_run`'s `qv` stays
      unset (→ `update`); `cld_ice_run`'s `qv` gets `memory_space=device` (→ `present`) — a
      genuine, deliberate `present`-vs-`update` conflict between two schemes in the *same group*,
      the exact scenario (c) needs a conflict-raise for. Deliberately not `ps` — it already has
      its own dedicated unit-mismatch test in `test_ccpp_track_variables.py` not worth entangling.
    - `tfreeze` (already host-matched in both `_init` tables against `test_host_mod`'s `tfreeze`):
      `memory_space=device` on `cld_liq_init`'s arg only, for whole-sim-scope entry. Exit needs a
      **new**, correctly-named `cld_liq_finalize` table with a `tfreeze` arg
      (`memory_space=device`) — `cld_liq` has no finalize table today, and `cld_ice_final` hits
      a real, separate bug (`lifecycle_cap.py`'s `_lc_postfix_aliases` has no bare
      `_finalize`↔`_final` alias, so `cld_ice_final` is silently never recognized at all) —
      deliberately sidestepping that bug rather than depending on it being fixed first.
    - Confirmed low blast radius: none of advection's 3 existing FileCheck goldens invoke any
      GPU pass, so `memory_space` itself won't appear in the `completed_ir`/`end_to_end` outputs
      (both run past `strip-ccpp`, which drops scheme metadata) — only `frontend`'s raw parse
      dump would show it directly. The new `cld_liq_finalize` table does add a new dispatch
      entry point, so all 3 goldens still need regenerating, but this is a small, local,
      mechanical regeneration — nothing like the group-split version's ripple.
      `test_ccpp_track_variables.py`'s `TestAdvectionIntegration` (the `ps` unit-mismatch test)
      is unaffected — confirmed its assertions never touch `qv`, `temp`, or `tfreeze`.
    - **The multi-group `_ccpp_physics_run` discovery bug still needs its own validation**, but
      now clearly separately from this — a small synthetic fixture (mirroring
      `test_gpu_data_hoisting.py`'s existing `TestMultiSuiteScoping` pattern, just multi-*group*
      instead of multi-*suite*) is enough; it doesn't need a real example or advection at all.
  - **OMP backend equivalent ("item #2"): done (2026-07-20).** `directive="omp"` now gets the
    same cross-function hoisting Option 2 built for ACC — `OmpTargetEnterDataOp`/
    `OmpTargetExitDataOp` and `OmpTargetUpdateFromOp`/`OmpTargetUpdateToOp` fire once at the
    computed entry/exit phase instead of the old per-call `OmpTargetDataBeginOp`/
    `OmpTargetDataEndOp` structured-region path on every touching call (which remains, unchanged,
    for degenerate/single-phase variables — same as ACC's legacy path).
    - **Prerequisite bug, found while scoping (2026-07-19), fixed (2026-07-20): existing OMP
      `map(...)` clauses rendered malformed.** `print_ftn.py`'s `CCPPOmpTargetDataBeginOp` case
      arm called `_emit_omp_directive`/`_emit_acc_directive` with clause names like
      `"map(tofrom:"` and `"map(alloc:"`, but that shared helper *also* appended its own `"("`
      before the first variable (the mechanism that makes ACC's bare clause names like
      `"copyin"` turn into `copyin(var)`). Combining the two produced a doubled, unbalanced
      paren — confirmed by actually generating OMP output through the pipeline before the fix:
      `!$omp target data map(alloc:(always_present)` and `!$omp target data
      map(tofrom:(three_phase)`, both missing a closing paren, invalid Fortran. Affected both
      `map(tofrom:...)` and `map(alloc:...)` uniformly, on both `GPUDataPass._process_physics_fn`'s
      and `GPUCcppCapPass._wrap_scheme_call`'s existing structured-region emission. `target
      update from(...)`/`to(...)` (the update-clause path) was unaffected — those clause names
      don't have their own `map(...)` wrapper, so they fit the old single-paren assumption
      correctly.
      - **Fix:** `_emit_acc_directive`'s clause tuples now optionally accept a third element,
        `opener` (default `"("`, preserving every existing 2-tuple call site unchanged). Passing
        `opener=""` lets a clause_name be the complete literal prefix (e.g. `"map(tofrom:"`)
        with nothing extra appended — used by the `target data` case arm's two clauses. No
        change needed to `GPUDataPass`/`GPUCcppCapPass` themselves; this was purely a printer-level
        fix, both existing call sites (`GPUDataPass`'s suite_cap-level region and
        `GPUCcppCapPass`'s ccpp_cap-level region) render correctly through the one shared helper.
      - **New test coverage, the first real OMP directive-output tests in the repo:**
        `tests/unit/test_omp_directives.py` (5 tests) — reuses `test_gpu_directives.py`'s existing
        present/copyin/host-less-scratch fixtures with `directive="omp"` instead of `"acc"`
        (confirms the fix across `map(alloc:...)`, `map(tofrom:...)`, and the suite_cap-level
        host-less path), plus a small dedicated fixture confirming `target update
        from(...)`/`to(...)` still renders correctly (regression guard on the tuple-unpacking
        change, though that path was never actually broken). Verified the new tests actually
        catch the regression: reverted the fix locally and confirmed the 3 map-clause tests fail
        without it, then restored the fix. Full suite green (366 unit + 44 FileCheck, 1 xfailed
        unchanged), `ruff check` clean (same 3 pre-existing baseline issues in `print_ftn.py`,
        unchanged from before this fix).
    - **New IR ops: done (2026-07-20).** `OmpTargetEnterDataOp` (`map(to:...)`/`map(alloc:...)`,
      mirroring `AccEnterDataOp`'s copyin/create split) and `OmpTargetExitDataOp`
      (`map(from:...)`/`map(release:...)` — OMP's `release` is the ref-counted-decrement analog
      of ACC's `delete`, not OMP 5.0's stronger `delete` mapping-type, which forces removal
      regardless of reference count) added to `ccpp_utils.py` and registered in the `CCPPUtils`
      dialect. The update-clause hoist path needs **no new ops** — `OmpTargetUpdateFromOp`/
      `OmpTargetUpdateToOp` already exist and are the direct equivalents of
      `AccUpdateSelfOp`/`AccUpdateDeviceOp` used for that path. Printer support added too (case
      arms in `print_ftn.py`, using the `opener=""` mechanism from the paren-bug fix above — both
      new directives render with balanced parens by construction, not by luck). At this point in
      the work these ops weren't wired into any pass yet — `GPUCcppCapPass`/`GPUDataPass` didn't
      construct them, verified only via direct construction (`OmpTargetEnterDataOp(to=[],
      alloc=[])` etc.) and two op-level printer tests in `TestOmpTargetEnterExitDataPrinter`
      (`test_omp_directives.py`) confirming correct, balanced output through the actual `case`
      dispatch. **That gap is closed by the very next sub-bullet below** (the `_role_at` gate
      removal + `_wrap_scheme_call` branches) — both ops are now constructed by
      `GPUCcppCapPass`'s hoisting for `directive="omp"` and exercised end-to-end in
      `test_omp_hoisting.py`; nothing here is still pending. Full suite green at this snapshot
      (368 unit + 44 FileCheck, 1 xfailed unchanged), `ruff check` clean.
    - **The actual unlock was a single removed gate, not new analysis, confirmed correct.**
      `_role_at` (and a second copy of the same gate in `_wrap_scheme_call`'s forced-anchor loop)
      hard-coded `self.directive != "acc"` → always `"legacy"`. Both removed — the underlying
      `VarLifetime`/per-suite analysis was already fully directive-agnostic, so no new analysis
      was needed, only the gate itself.
    - **Passthrough needed no new code, confirmed.** ACC's passthrough already worked by feeding
      the variable into the *existing* structured-region block in `_wrap_scheme_call` (the one
      that builds `AccDataBeginOp`'s `present=` bucket), which already branched on
      `self.directive` and already used `OmpTargetDataBeginOp(alloc=...)` for the OMP case.
      Removing the `_role_at` gate was sufficient — no changes needed to that block at all.
    - **`_wrap_scheme_call` insertion blocks: `self.directive` branches added** for the two new
      enter/exit-data blocks and the two update-hoist blocks, mirroring the branch the structured-
      region block already had. OMP's `map(to:...)`/`map(alloc:...)` map onto ACC's
      `copyin`/`create`; `map(from:...)`/`map(release:...)` onto `copyout`/`delete`;
      `OmpTargetUpdateFromOp`/`OmpTargetUpdateToOp` onto `AccUpdateSelfOp`/`AccUpdateDeviceOp`
      (same "before call = self/from, after call = device/to" mapping the pre-existing legacy
      per-call update path already used). Class docstring and `directive` field comment updated
      to drop the now-inaccurate "ACC backend only"/"ACC-only for now" wording.
    - **Verified end-to-end against `test_gpu_data_hoisting.py`'s Group A fixture** (manual dump)
      before writing tests: `three_phase` correctly enters at `timestep_initial`
      (`map(to:three_phase)`), folds into the passthrough `map(alloc:...)` bucket at `run`, exits
      at `timestep_final` (`map(from:three_phase)`); `cross_var` enters at `run`
      (`map(to:cross_var)`) and exits via `map(release:cross_var)` at `timestep_final` (`copyin`
      kind → release, no data movement back needed) — same shapes as the ACC behavior, just with
      OMP ops/clause text.
    - **New test coverage, now all six groups: `tests/unit/test_omp_hoisting.py` (10 tests).**
      Initially added Group A (per-timestep hoisting across two schemes, three-phase passthrough,
      degenerate single-phase stays legacy), Group B (whole-sim scope via synthesized ref,
      register-only entry anchor), and Group E (update-clause hoisting with nothing at the
      passthrough phase) — 6 tests, judged sufficient at the time since the underlying lifetime
      analysis is directive-agnostic. Extended (2026-07-20) with the remaining three: **Group C**
      (multi-suite scoping — suite A's run-only usage stays degenerate despite suite B's
      unrelated `_init`-phase usage of the same variable name, asserted via
      `map(tofrom:shared_var...)` and no target enter/exit data), **Group D** (a single-phase,
      degenerate update-clause variable stays on the legacy per-call `target update
      from(...)`/`to(...)` path, no target enter/exit data), and **Group F** (finalize
      independent of a per-timestep-hoisted span — both the copyin/copy/copyout and update-clause
      sub-cases). All ten reuse `test_gpu_data_hoisting.py`'s exact fixtures (including its
      `_make_context`/`_build_multi_suite_module` helpers for Group C's two-suite module) with
      `directive="omp"` — genuinely new coverage for the OMP backend, not a copy-paste of
      already-tested ACC behavior. Full suite green (378 unit + 44 FileCheck, 1 xfailed
      unchanged), `ruff check` clean. **The OMP hoisting test matrix is now symmetric with ACC's
      — every one of `test_gpu_data_hoisting.py`'s six groups has an OMP counterpart.**
  - **Use `examples/advection` to exercise subtler OpenACC cases against a real example, not just
    synthetic fixtures: scoped (2026-07-19), not implemented, not scheduled — pick up another
    day.** Prompted by the project owner asking whether `advection` (the constituent/DDT example
    — `const_indices`, `cld_liq`, `cld_ice`, `apply_constituent_tendencies`, `physics_state` DDT)
    could stress-test hoisting beyond what `examples/kessler` already covers. Investigated
    directly rather than guessing:
    - **Real gaps `kessler` genuinely can't cover, confirmed by grepping both examples' `.meta`
      files:** (1) `kessler.meta`/`kessler_update.meta` have no `_register` table at all (only
      `_init`/`_timestep_init`/`_run`/`_timestep_final`) — meaning the whole-simulation-scope
      hoisting path (register/initialize entry, forced exit at finalize) has **never been
      validated against a real example**, only synthetic fixtures in
      `test_gpu_data_hoisting.py`. `cld_ice.meta`/`cld_liq.meta` do have real `_register` tables.
      (2) No example anywhere in this repo exercises a DDT member's device residency — whether
      `HostVariableMatchPass` even resolves `model_var_name`/`model_var_memory_space` correctly
      for a DDT member (`advection` has one: `physics_state`) is currently an open question.
    - **`apply_constituent_tendencies` appearing twice in one group turned out NOT to stress
      `GPUCcppCapPass`'s hoisting at all**, contrary to the initial guess that repeated scheme
      calls would be an interesting case for it. Traced through `_wrap_scheme_call`'s discovery:
      it only ever sees one call site per lifecycle phase (the suite's combined `_suite_physics`
      call) — the repeated scheme call happens one level deeper, inside `suite_cap.py`'s own
      generated function body, which only `GPUDataPass` instruments (and already unions device
      vars across both occurrences into one combined region, correctly). Good for stress-testing
      `GPUDataPass`'s host-less-scratch dedup path specifically, not Option 2/1(a)'s hoisting.
    - **Not usable as-is.** Confirmed via `grep -rn memory_space examples/advection/` — zero
      hits, on both scheme and host side, and the Makefile has no ACC/GPU target at all. Using it
      for this purpose means deliberately adding `memory_space = device` to a couple of
      variables: one in `cld_ice_register`/`cld_liq_register` plus a matching host declaration
      (for the whole-sim-scope case), and one on a DDT member (for the DDT-residency case) — not
      just running the existing example through the pipeline.
    - **Separate, unrelated bug found while checking this: `cld_ice.meta`'s finalize table is
      named `cld_ice_final`, not `cld_ice_finalize`.** `lifecycle_cap.py`'s `_lc_postfix_aliases`
      only maps `_timestep_initialize`/`_timestep_finalize` to their `_timestep_init`/
      `_timestep_final` aliases — there's no equivalent bare `_finalize`/`_final` alias pair, so
      `cld_ice_final` is never picked up by the core lifecycle dispatch at all today. Currently
      silent/inert rather than actively broken (the table's only content is boilerplate
      `errmsg`/`errflg`, no real args), but a real gap worth fixing regardless — and specifically
      blocks using `cld_ice` for the whole-sim-scope test above until fixed (or that test uses
      `cld_liq` / a properly-named new finalize table instead).
    - **Recommended next steps, in order:** (1) fix the `_final`/`_finalize` alias gap in
      `lifecycle_cap.py` (small, independent, unblocks using `cld_ice` for anything finalize-
      related); (2) add a real whole-sim-scope hoisting example (register/initialize → finalize)
      using `cld_ice`/`cld_liq`, the first real (non-synthetic) validation of that path; (3) add a
      DDT-member device-residency case and confirm `HostVariableMatchPass` handles it correctly
      before assuming `GPUCcppCapPass`'s hoisting does too.
  - **Milestone (2026-07-19): confirmed on the project owner's HPC system (nvhpc/nvfortran).**
    `examples/kessler` now builds *and executes* under `ARCH=GPU`, producing bit-for-bit
    identical output to the CPU build. First real GPU pass/fail confirmation for this codebase.
  - **Not yet checked via CI (flagged 2026-07-19) — tracked as a future item, not scheduled.**
    Both existing workflows (`.github/workflows/tests.yml`, `.github/workflows/compile-tests.yml`)
    run only on GitHub-hosted `ubuntu-latest` runners with `gfortran`/`ARCH=CPU` (the default) —
    zero coverage of `FC=nvfortran`, `ARCH=GPU`, or the bit-for-bit GPU/CPU check the project
    owner just ran by hand. Real execution coverage needs a GPU-attached runner (self-hosted
    against the HPC system, or a cloud GPU instance) — infrastructure/access/cost the project
    owner needs to set up, not something achievable on the hosted pool. **Decision (2026-07-19):
    hold off on any CI changes until the project owner has consulted colleagues with existing
    GPU-CI setups for guidance**, rather than build something ad hoc first. A lower-effort
    fallback remains on the table for later if wanted sooner: a compile-only smoke test (install
    NVIDIA HPC SDK Community Edition on the hosted runner, build-check the `ARCH=GPU` path with an
    explicit `-gpu=ccXY` target since no device is present to auto-detect) — would have caught the
    `-noacc`/`ACC_OFF_C` Makefile regression above, but can't execute the binary or verify
    bit-for-bit correctness.
  - **`kessler-gpu-acc-fixes` branch: closed out (2026-07-19).** Copilot's automated PR review
    found 2 issues, both real, both fixed same day: (1) `GPUDataPass._get_scheme_name` didn't
    recognize the `_timestep_initialize`/`_timestep_finalize` naming convention (the canonical
    scheme-level postfix per `ccpp_cap.py`'s `lifecycle_specs` — see e.g.
    `examples/capgen/scheme/temp_set.meta`'s `temp_set_timestep_initialize`); only the
    `_timestep_init`/`_timestep_final` alias (kessler_update's convention) was recognized, so
    calls using the canonical spelling were silently skipped — no data region, no error. Fixed by
    adding both suffixes with correct precedence ordering (`_timestep_finalize` must be checked
    before `_finalize`, same shadowing hazard as the earlier `_timestep_init`/`_init` fix).
    (2) The blanket `DEVICEPTR→present` sed replacement in `kessler.F90` had left **9** directives
    (not just the 1 Copilot flagged) with two separate `present(...)` clauses on the same
    directive — invalid per OpenACC, since the original code paired `DEVICEPTR(...)` for caller
    args with an already-separate `present(...)` for locally `enter data`-managed scratch arrays;
    replacing the macro made both clauses the same type. Found the rest with a script that
    reassembles logical (continuation-joined) `!$acc` directives and checks for more than one
    `present(` per directive; merged each pair into one combined clause. Added a 9-case
    parametrized regression test for (1) and a programmatic duplicate-clause check for (2). Full
    suite green throughout (305 unit + 44 FileCheck, 1 xfailed unchanged), `ruff check` clean,
    regenerated kessler end-to-end to confirm.
- **Documentation-limitations audit and cleanup, 2026-07-19 (unrelated to this refactor's own
  scope, but logged here since it's the same running session).** Project owner asked for a
  full sweep of every doc (`README.md`, `DEVELOPERS.md`, `multilanguage_limitations.md`,
  `multilanguage_plan.md`, `multi_instance_plan.md`, this file, every `examples/*/README.md`)
  plus code docstrings/comments across `xdsl_ccpp/` for documented limitations, to sort real
  from stale together. Full findings list delivered directly to the project owner (not
  duplicated here); items acted on so far:
  - **`README.md`:** the "Known limitations" chost summary (fixed double precision/no DDT
    support/rank > 2 arrays) was stale — all three are marked Resolved in
    `multilanguage_limitations.md` itself; replaced with the three items that doc's own
    priority table still lists live (column-major layout, chost GPU memory management, thread
    safety). The "GPU execution not yet tested" footnote was stale given the GPU milestone
    above; updated to record the confirmed CPU/GPU bit-for-bit match. Added a callout in the
    plain `--bind-c` section flagging the rank ≥ 3 array issue below. Removed `--num-instances
    N` from the `ccpp_xdsl` options table — confirmed via `ccpp_xdsl --help` and reading
    `ccpp_dsl.py`'s own arg parser that this flag does not exist on that driver at all; added a
    short note pointing to `multi_instance_plan.md` instead.
  - **`multilanguage_limitations.md`:** §4's heading still said "Remaining Gaps" though all
    three sub-items were already marked Resolved — fixed. §5 ("Rank > 2 Arrays — Resolved") was
    the substantial fix — see the rank-3 entry above for the full technical detail; changed to
    "Partially Resolved" (chost path confirmed fine with a corrected code example; plain
    `--bind-c` path flagged as likely broken, unverified) and the Priority Summary table's row 5
    updated to match.
  - **`multi_instance_plan.md`:** the original audit pass flagged a "contradiction" between this
    doc (claims `--num-instances` works "on `ccpp_xdsl`") and a `# TODO: expose via
    --num-instances CLI argument` comment in `ccpp_conventions.py`, guessing the TODO was stale.
    Verifying directly showed the opposite: `--num-instances` is real, but only on the
    low-level `xdsl_ccpp.frontend.ccpp_xml` frontend module (confirmed via `ccpp_xdsl --help`
    and `ccpp_dsl.py`'s arg parser having no such flag) — the plan doc's wording was the
    inaccurate one, and the TODO comment is correct as written. Rewrote the doc's "Instance cap"
    bullet to state precisely which tool the flag lives on. **Worth remembering: don't trust an
    audit's first-pass guess about which of two contradicting docs is stale without checking the
    actual code directly** — the fork that did the original sweep guessed correctly about the
    existence of a contradiction but reasoned backwards about which side of it was true.
  - Not yet revisited: `multilanguage_plan.md`, `DEVELOPERS.md`, the example READMEs (audit found
    nothing stale in the latter two), and two of the three smaller code-level TODOs the audit
    surfaced (`suite_cap.py:381`'s single-optional-arg-name-per-group limitation,
    `ccpp_dsl.py`'s `--kind-map` first-entry-only limitation — both confirmed genuinely live, not
    stale, so no action needed there).
  - **Correction on the third: the `cpp_interop.py` DDT `ValueError` was not actually dead code.**
    The original audit guessed it was stale leftover from before DDT flattening shipped;
    investigating directly (before touching it) found a dedicated test file
    (`tests/unit/test_chost_ddt_error.py`, 8 tests) that exercises it in isolation, and
    `_chost_arg_info` is deliberately `meta_data`-agnostic by design — it's a low-level guard
    against a DDT ever reaching it directly, not the flattening path itself (that's one layer up,
    in `_chost_fn_contexts`, gated on whether `meta_data` was provided). What was actually stale
    was narrower: the error message's closing pointer to `multilanguage_limitations.md` "for
    options," which no longer matches that doc's §4 (now fully Resolved). Fixed just that
    sentence; left the raise, its "not supported" framing, and the test file untouched. **Second
    reminder in the same session not to trust an audit's dead-code/staleness guess without
    verifying against the actual call graph and test suite first** — see the `multi_instance_plan.md`
    reminder above for the first.
- **Ideas from `duplication_analysis_summary.md` added to the backlog (2026-07-19).** Project
  owner ran a code-duplication analysis of the companion `NCAR/atmospheric_physics` repo (Fortran
  source, `.meta`, and suite-XML layers) and asked for a link from existing docs — done (a
  pointer from `README.md`'s "Metadata Skeleton Generation" section, see that file). Logging the
  substance here too, since two of the three proposed interventions are `xdsl_ccpp` tooling work,
  not `atmospheric_physics`-side changes, and belong in this project's own backlog:
  - **By far the largest finding, not yet started:** eliminate `.meta` as a hand-maintained shadow
    file. ~45% of every `.meta` block (type/intent/argument name) is mechanically derivable from
    the Fortran signature already; `standard_name`/`units` (~30%) is the only genuinely
    irreducible content. Proposed fix: tag `standard_name`/`units` directly in Fortran via a
    name-keyed comment block (`!ccpp [qv] standard_name=... units=...`, immune to declaration
    reordering unlike a trailing-per-line comment), and extend `fparser2_to_meta.py` /
    `ccpp_generate_meta.py` to consume it — generating `.meta` mechanically instead of leaving
    `standard_name`/`units` as hand-filled stubs. Confirmed practical against this repo
    specifically, not just in the abstract: `ArgumentOp` (`xdsl_ccpp/dialects/ccpp.py`) already
    carries `standard_name`/`units`/`long_name`/`dim_names` as optional properties with a working
    generic `.meta` writer (`meta_from_module`), so this only needs a third way to populate
    already-existing IR fields — no dialect or writer change. Two open risks the analysis
    resolved with working code rather than leaving as open questions: (1) `fparser2` strips
    comments from the parse tree, but `Type_Declaration_Stmt.item.span` gives the exact source
    line range, letting the raw comment be recovered by cross-referencing back into the original
    source text — demonstrated end-to-end on a real 149-character standard name; (2) checked the
    real `standard_name` length distribution across `atmospheric_physics`'s 3,596 variable
    blocks — under 1% would push a line past the traditional 132-column Fortran limit, and the
    current `.meta` already has an unwrapped ~186-character line for that same worst case, so
    this isn't a new problem, just a relocated one. **Only ever extends `fparser2_to_meta.py`,
    never `fir_to_meta.py`** — once Flang compiles to FIR/HLFIR the comments are already gone, so
    the compiler-validated route stays `.meta`-consuming, not `.meta`-producing, for this purpose.
    Staged effort plan (design → extend `fparser2_to_meta.py` → migrate `atmospheric_physics` →
    CI wiring) already sketched in the source document, sized as "a couple of focused weeks," not
    a major rearchitecture.
  - **Bonus finding, smaller and independent of the above:** `ArgumentOp.memory_space` (the
    property `generate-gpu-ccpp-cap`/`generate-gpu-data` read to decide `present`/`copyin`/etc.)
    may also be derivable — not from a new annotation, but from **existing, currently-disabled**
    OpenACC `deviceptr(...)` clauses already sitting in `kessler_update.F90` behind
    `#define DEVICEPTR(...)` (empty). Demonstrated recovering the exact device-resident variable
    set from `kessler_update_run`'s existing directives with the same span-based technique used
    for the `standard_name`/`units` proposal. Would be a separate, fourth extraction pass (parallel
    to the type/intent extractor and the new `!ccpp`-tag extractor), feeding the same existing
    `memory_space` property — same target, different source, no IR change. Caveated: only gives a
    signal for variables a scheme's directives *already* name explicitly; says nothing about
    `model_var_memory_space` (the host-side declaration), which is a separate concern.
  - **Not part of this project's backlog** (logged in the source document, not here, since they're
    `atmospheric_physics`-side or purely `atmospheric_physics`-authoring-layer changes with no
    `xdsl_ccpp` tooling implication): the `scheme_family` symbolic-tracing code generator for
    Fortran-layer formula duplication (~320-360 lines), and the Python suite-composition DSL
    (`theta_basis`/`dry_basis` combinators) for SDF XML duplication (~280 lines) — though the
    latter echoes `xdsl_ccpp.frontend.py_api`'s existing `@ccpp_suite`/`forLoop` design
    independently, which is worth knowing about if that DSL is ever extended with
    auto-bracketing combinators.
  - **Not scheduled, not started** — logged per this doc's usual practice for considered-but-not-
    committed-to future work (same treatment as Phase 7 and the GPU data-movement follow-up
    above). See `duplication_analysis_summary.md` for the full analysis, worked examples, and
    effort staging table; not duplicated here.

**Housekeeping — done, same day:** local `main` was briefly stale (showed only through Phase 2
(#7) — no fetch credentials in this sandbox, not a real gap upstream) but the project owner
pulled fresh before ending the session. Confirmed: `main` is now at `2839fed` ("Phase 3a
restructuring (#8)"), both post-merge review fixes are present (`lifecycle_cap.py`/
`run_dispatch.py` "No suite named" text, and the `dim_std_name.lower()` fix), and the full
suite is green on `main` — 227/227 unit, 44 passed + 1 xfailed FileCheck. **Next session can
branch for Stage 1 immediately, no re-sync needed.**

**Established working pattern this project has used successfully across every phase so far**
(carry forward into 3b):
- One branch per phase/stage, branched fresh off `main`, prepared locally and left
  uncommitted for the project owner to review and commit/push themselves (no push credentials
  in this sandbox).
- Before moving any function: systematically grep every candidate name against the *whole*
  file for cross-boundary call sites — don't trust proximity or naming convention. Caught real
  gaps in both Phase 2 (`_get_suite_lifecycle_ret_info`) and Phase 3a
  (`_derive_camel_case_name`/`_build_suite_variables_fn` sitting inside the naive line range).
- Verify every extraction line boundary with `cat -n` before cutting, not just `grep`/`sed -n`
  alone — Phase 2's off-by-two mistake (caught immediately by the test suite) came from
  skipping this.
- After every move: `ruff check --select F401` proactively (don't wait for review) to catch
  imports the move made stale. Full (non-`F401`) `ruff check` is worth a look too, but treat
  pre-existing findings (e.g. `F841`) as separate cleanup, not something to bundle into a
  structural-move PR.
- Verify **byte-identical** output directly via `git stash` / regenerate / diff — not just
  "FileCheck passes" — for at least 2-3 representative examples chosen to cover the phase's
  specific territory (e.g. Phase 3a used `kessler`, `constprop`, and `helloworld`+`ccpp_t` to
  cover chost/general, constituents, and multi-instance respectively).
- Real content bugs found via review (buffer overflow, missing space in error text, missing
  lowercase normalization) get fixed in their own commit/PR, separate from structural-move
  PRs, so the "verified byte-identical" property of a move PR is never diluted by a real
  behavior change riding along with it.

---

## Phase 0 — Stabilize the safety net ✅ done

Before restructuring anything, get the existing test suite to a known-green baseline —
otherwise there's no way to tell whether a later change introduced a regression or just
exposed a pre-existing one.

- [x] Fix the stale example paths (`examples/capgen/*.xml` moved to `examples/capgen/scheme/*.xml`,
  and host metas to `examples/capgen/host_ftn/`, without updating `tests/` or `gen_capgen`).
  Fixed in `tests/unit/test_build_integration.py`, `tests/unit/test_ccpp_track_variables.py`,
  `tests/unit/test_optional_args.py`, the three `tests/filecheck/examples/*/capgen-xml.mlir`
  `RUN:` lines, and `gen_capgen`. Result: unit tests went from 196 passed/1 failed/11 errors to
  **208 passed**; FileCheck went from 41 passed/4 failed to **44 passed**.
- [x] Investigated the rank-3 array FileCheck failure
  (`tests/filecheck/examples/end_to_end/chost-r3-ftn.mlir` vs. the "Resolved" claim in
  `multilanguage_limitations.md` §5). Root cause: the most recent commit (`2fe5473`,
  "Hopefully fixes the simple test case") deliberately changed the chost rank≥3 array
  declaration from assumed-size (`flux(ncol, nz, *)`) to explicit-shape
  (`flux(ncol, nz, nbands)`) when the third dimension is known, with its own rationale
  ("so the array can be passed to assumed-shape `(:,:,:)` suite cap dummies") — but the
  golden test and `multilanguage_limitations.md` §5 were never updated to match. There's also
  a possible follow-on issue one layer up: `TinyR3_ccpp_cap.F90` still declares `flux` as flat
  assumed-size (`flux(*)`) and forwards it into the suite cap's assumed-shape `(:,:,:)` dummy,
  which looks like the same class of problem — unverified, no Fortran compiler available in
  this environment to compile-check either layer.
  **Decision (per project owner, 2026-07-17):** this is ongoing work — leave the test failing
  and the docs as-is for now rather than guess-fixing a Fortran interop correctness question.
  Not blocking Phase 1.
- [x] Confirmed test suite state before Phase 1: **208/208 unit tests pass**,
  **44/45 FileCheck tests pass** (1 accepted, documented exception above).

Committed as `78aa115` ("Phase 0 of the restructure involves cleaning up some tests.") on
branch `phase0-stabilize-tests`, pushed and submitted as a PR by the project owner
(2026-07-17). Phase 1 has not been started.

### Round 2: PR review feedback (2026-07-17)

A reviewer on the Phase 0 PR pointed out that the original path fix only covered
`tests/` and `gen_capgen` — several other in-repo invocations still referenced the old,
now-nonexistent top-level paths and would fail post-restructure. Fixed (documentation and
scripts updated directly; no compatibility symlinks added, per project owner preference):

- `examples/capgen/README.md` — the `ccpp_xdsl` command block and the Files table.
- `README.md` (top-level) — the "Integrated use" `ccpp_xdsl` command block.
- `examples/capgen/scheme/capgen_py.py` — both the docstring examples **and** the actual
  executable `ccpp_ddt_from_meta`/`ccpp_scheme_from_meta`/`ccpp_host_from_meta` calls. This
  one mattered most: the script itself now lives under `scheme/` and was passing dead paths
  to those loaders, so it would have raised `FileNotFoundError` at import time, not just
  produced stale documentation. Verified by actually running it post-fix (`exit 0`, valid IR
  emitted).
- `xdsl_ccpp/frontend/py_api.py:708-709` — docstring example for `ccpp_ddt_from_meta`.
- `xdsl_ccpp/tools/ccpp_validate_fir.py:13` — one more instance found by a repo-wide sweep,
  not in the original review comment but the same class of staleness.

Verified via a repo-wide grep for `examples/capgen/<file>` outside `scheme/`/`host_ftn/`/
`host_cpp/` — zero remaining hits. Full suite re-confirmed green (208/208 unit; 44 passed +
1 accepted rank-3 exception in FileCheck). Uncommitted as of this writing, on
`phase0-stabilize-tests`, ready for the project owner to commit/push as a follow-up to the
existing PR.

## Process note: one PR per phase

Per project owner direction, each phase of this plan gets its own PR against
`johnmauff/xdsl-ccpp`, reviewed and merged independently before the next phase starts.
This session doesn't hold push credentials for the repo, so the pattern is: changes are
prepared and committed locally, then the project owner pushes the branch and opens the PR
from their own authenticated environment.

## Phase 1 — Extract the C++/BIND(C) backend (`chost`) ✅ done

Lowest-risk, highest-confidence cut. The `_chost_*` helpers (lines ~153–891) are already free
functions with no `self` and no shared mutable state with the rest of the pass.

- [x] Moved 17 free functions (`_emit_subr_header`, `_emit_call`, and 15 `_chost_*`/`_ddt_*`/
  `_lc_of`/`_suite_fns_for` helpers) plus `_generate_chost_cap_module`, `_build_chost_ftn_text`,
  `_build_chost_cpp_text`, `_build_chost_wrapper_text` into a new
  `xdsl_ccpp/transforms/cpp_interop.py`, wrapped in a new `CPPInteropCap(ModulePass)`.
- [x] Registered as `generate-cpp-cap` in `ccpp_opt.py`; wired into `ccpp_dsl.py`'s
  `_build_pipeline()` unconditionally right after `generate-ccpp-cap` (not gated by `--bind-c`
  at the CLI level — the original code always ran its internal IR-content check regardless of
  CLI flags, so the new pass replicates that by always running and no-op'ing internally unless
  a host/module table declares `language = "c++"`, exactly matching prior behavior).
- [x] Handled the two architectural seams flagged before starting:
  - **`cap_mod` handoff** — the new pass re-locates the just-generated `<HostName>_ccpp_cap`
    module by scanning `op.body.block.ops` for a `ModuleOp` whose `sym_name` ends in
    `_ccpp_cap`, since passes can no longer share a direct Python object reference.
  - **`public_fns` scope** — the new pass excludes the just-found `cap_mod` from its
    `_collect_public_suite_functions` scan, reproducing the exact set the original code saw
    (computed before `cap_mod` existed in the block).
- [x] Found and fixed a real modeling error during the move: `_resolve_ddt_access_path` was
  initially moved wholesale (it looked chost-exclusive by proximity), but a systematic
  cross-boundary check of all 19 moved names found one call site outside both moved ranges
  (original line 1469, in the run-dispatch cluster). Kept it in `ccpp_cap.py` alongside `_bare`
  and `_collect_public_suite_functions` (also promoted from a method to a module-level
  function, imported by both files) rather than duplicating it.
- [x] Found and fixed a second issue post-move: 34 `tests/filecheck/*.mlir` golden tests invoke
  `ccpp_opt` directly with their own **hardcoded** pass-list string in the `// RUN:` line,
  completely bypassing `ccpp_dsl.py`'s `_build_pipeline()`. Every one needed
  `generate-cpp-cap` inserted after `generate-ccpp-cap` by hand (scripted, not manual).
- [x] **Verified byte-identical output directly**, not just via FileCheck's partial pattern
  matching: diffed the complete raw output (both the `ftn` and `cpp_header` targets) for the
  most complex chost example (`kessler`) between the pre-Phase-1 code and the refactored code
  — `diff` exit code 0, zero output, both targets.
- [x] Full suite green: 208/208 unit tests, 44 passed + 1 xfailed FileCheck (same 1 accepted
  rank-3 exception from Phase 0 — untouched).
- **Result:** `ccpp_cap.py` 4,749 → 3,248 lines (−1,501); new `cpp_interop.py` is 1,617 lines.
  Combined total 4,865 vs. the original 4,749 (+116, from the new pass's docstring/glue code
  for the `apply()` seams above) — roughly flat overall, as predicted, with the real win being
  the C++/BIND(C) backend now independently testable and toggleable rather than permanently
  entangled with core Fortran cap generation.

Merged into `main` as PR #5 ("Extracting chost from the Fortran pass").

### Post-merge: buffer-overflow bug found by review (2026-07-17)

A reviewer on the Phase 1 PR found a real, pre-existing correctness bug in the moved code
(confirmed identical in the original pre-Phase-1 `ccpp_cap.py`, so not introduced by the
move): the generated C++ chost wrapper allocates `scheme_name`/`errmsg` buffers sized
exactly `CCPP_SCHEME_NAME_LEN`/`CCPP_ERRMSG_LEN`, but the generated Fortran writes a null
terminator at `len_trim(...)+1` — an out-of-bounds write when the string fully fills the
buffer. Fixed in `cpp_interop.py` (bumped both sizes by 1, matching a `+1` convention
already used correctly elsewhere in the same file) plus two golden-test updates. A follow-up
review comment then found the fix hadn't reached a **checked-in generated artifact**
(`examples/ddthost/bindc/`, the only committed generator-output directory in the repo,
`errmsg[512]` still present) — removed those 8 stale files and added `bindc/` to
`.gitignore` so this class of staleness can't recur, since no other example commits its
generated output either. Merged as PR #6.

**Process takeaway, applied below:** before moving any function, systematically grep every
candidate name against the *whole* file for cross-boundary call sites — don't trust
proximity or naming convention. Doing this for Phase 2 before writing any code (below)
caught two real gaps the same way `_resolve_ddt_access_path` surprised us in Phase 1.

## Phase 2 — Extract lifecycle and constituent-API generation

Narrower interfaces than Phase 3's cluster — each mostly consumes `suite_descriptions`/
`meta_data` and produces one self-contained piece of the output module. **Unlike Phase 1's
chost cluster, this one is not contiguous**: `_generate_run_fn`/`_generate_suite_part_list_fn`
(Phase 3's run-dispatch territory) sit physically between the lifecycle and constituent-API
functions in `ccpp_cap.py` — expect multiple non-adjacent cuts, not one clean block.

Current line numbers (post-Phase-1 `ccpp_cap.py`, 3,248 lines):

- `_get_suite_lifecycle_return_types` — 1662–1666. **Appears to be dead code**: zero call
  sites anywhere in the codebase or tests. Decide remove-vs-migrate rather than assuming it
  needs a new home.
- `_get_suite_lifecycle_ret_info` — 1667–1720. **Do not move this one.** Its call sites
  are not lifecycle-exclusive: `_build_run_dispatch_chain` (line ~1462, Phase 3's
  not-yet-extracted run-dispatch cluster) also calls it, alongside `_generate_lifecycle_fn`'s
  own caller (`_generate_ccpp_cap_module`). Keep it in `ccpp_cap.py` as a shared helper —
  same treatment as `_bare` in Phase 1 — until Phase 3 extracts run-dispatch too, at which
  point it may make more sense as a genuinely neutral shared utility both modules import.
- `_collect_constituent_info` — 1721–1772. Its only call site is inside
  `_generate_ccpp_cap_module` (final assembly, staying in `ccpp_cap.py` per Phase 5), not
  inside `_generate_constituent_api`. Still fine to move into `constituent_cap.py` — just
  means `ccpp_cap.py` imports it back — but don't assume it travels with
  `_generate_constituent_api` by proximity; it doesn't share a caller with it.
- `_generate_lifecycle_fn` — 1773–2139 (367 lines). Confirmed lifecycle-exclusive: only
  called from `_generate_ccpp_cap_module`.
- `_generate_constituent_api` — 2378–2733 (356 lines). Confirmed constituent-API-exclusive:
  only called from `_generate_ccpp_cap_module`.

Two things that bit Phase 1 and are **confirmed not to apply here**: no test file directly
imports any of these five names (unlike Phase 1's `test_chost_ddt_expand.py`/
`test_chost_ddt_error.py`), and since Phase 2 keeps these as plain importable modules rather
than registering a new pass, the 34-file hardcoded-pipeline-string fixup Phase 1 needed
shouldn't recur.

- Move `_generate_lifecycle_fn` (367 lines) into `lifecycle_cap.py`.
- Move `_generate_constituent_api` (356 lines) + `_collect_constituent_info` into
  `constituent_cap.py`.
- Keep these as plain importable modules/functions for now rather than full registered
  passes — defer that decision to Phase 6.
- Validate against the full golden suite again.

### Phase 2 outcome ✅ done

Removed `_get_suite_lifecycle_return_types` entirely (confirmed dead code, per project owner
decision). Moved `_generate_lifecycle_fn` into `lifecycle_cap.py` and
`_generate_constituent_api`/`_collect_constituent_info` into `constituent_cap.py`, exactly as
corrected above. Kept `_get_suite_lifecycle_ret_info` and `_build_host_var_map` in
`ccpp_cap.py` as shared helpers, per the plan.

**A third architectural issue surfaced during implementation, beyond the two found while
planning:** since Phase 2 calls the new modules' functions *directly* from
`_generate_ccpp_cap_module` (unlike Phase 1's `cpp_interop.py`, which is invoked as a
separate pipeline pass, never imported by `ccpp_cap.py`), `ccpp_cap.py` needs to import from
`lifecycle_cap.py`/`constituent_cap.py` — but those two also need `_bare`/
`_build_host_var_map`/`_CCPP_CONSTITUENT_MOD` back from `ccpp_cap.py`. A genuine import
cycle, not just an ordering inconvenience. Fixed by creating a new neutral leaf module,
`xdsl_ccpp/transforms/util/cap_shared.py`, holding `_bare`, `_build_host_var_map`,
`_get_suite_lifecycle_ret_info`, `_CCPP_CONSTITUENT_MOD`, and `_CONSTITUENT_DDT_NAME` — all
four cap-generation files (`ccpp_cap.py`, `cpp_interop.py`, `lifecycle_cap.py`,
`constituent_cap.py`) import from it, and it imports from none of them. Verified by importing
all four modules independently in isolation (each as the first import in a fresh process) —
all succeed regardless of order.

**A mechanical mistake also surfaced and was fixed via the test suite, exactly as the
process is supposed to work:** an off-by-two line-counting error when removing `_bare`'s
old definition left two dangling body lines behind, causing an immediate `NameError` on
every test that exercises `_generate_ccpp_cap_module`. Caught by the first unit-test run
after the move, fixed directly, re-verified.

Verified byte-identical (not just FileCheck-passing) by diffing complete raw output for two
representative examples — `kessler` (lifecycle-heavy) and `constprop` (constituent-API-heavy,
confirmed 65 occurrences of "constituent" in its generated output) — between the pre-Phase-2
code and the refactored code: `diff` exit code 0, zero output, both examples. Full suite:
208/208 unit tests, 44 passed + 1 xfailed FileCheck (same accepted rank-3 exception,
untouched).

**Result:** `ccpp_cap.py` 3,248 → 2,382 lines (−866). New files: `lifecycle_cap.py` (405),
`constituent_cap.py` (426), `cap_shared.py` (110). Combined total 3,323 vs. the pre-Phase-2
3,248 (+75, new-file header/import boilerplate) — flat overall, as expected.

Done on local branch `phase2-extract-lifecycle-constituent`, uncommitted as of this writing.

## Phase 3 — The run-dispatch cluster (highest risk — do this last, in two steps)

The ~1,500-line heart of the pass: `_build_run_metadata_maps` → `_build_per_suite_run_info`
→ `_build_run_block_signature` → `_build_run_chain_preamble` → `_build_run_dispatch_chain`
(520 lines alone) → `_assemble_run_fn`. Every generated suite touches this code, so it carries
the widest blast radius of anything in the file.

**3a — Mechanical move (behavior-preserving):**
Cut-paste the cluster into `run_dispatch.py` with no logic changes. This alone gets it out of
the monolith and, for the first time, makes it something that can be unit-tested in isolation
rather than only exercised indirectly through full end-to-end FileCheck comparisons.

**3b — Promote to real IR (the actual architectural fix, and genuinely riskier):**
Turn `_RunMetadataMaps`/`_RunBlockSignature`/`_RunChainPreamble` from transient dataclasses
into real ops in the `ccpp` dialect, so argument resolution produces durable, inspectable IR
instead of Python state built and discarded within one method call. `_assemble_run_fn` then
becomes a thin printer over that IR — mirroring the frontend/backend split already used
elsewhere in the project. This is what actually delivers "resolution bugs and printing bugs
are separately testable," not just a smaller file.

Only start 3b once 3a has been stable for a while, and ideally with a second reviewer — it's
a behavioral refactor of the most load-bearing code in the pass, not a pure move.

**Open question, decide before naming any op (raised 2026-07-17):** of the three dataclasses,
only `_RunBlockSignature`/`_RunChainPreamble` hold live IR references (Blocks, ops already
inserted). `_RunMetadataMaps` is pure lookup tables built from `meta_data` — no IR content —
and "promote it to an op" may not be the right move architecturally (ops represent program
structure, not internal analysis caches). The more valuable IR-ification target is likely the
**per-argument resolution result** `_build_per_suite_run_info` computes per scheme call
(host var / DDT member / cap-owned var / block arg, plus any needed transform) — the actual
`ResolvedArg`-equivalent for this project. Narrow or re-scope 3b accordingly before Stage 1.

### Phase 3b: staged breakdown ✅ done (agreed 2026-07-17, all 4 stages completed 2026-07-18)

Same incremental discipline as every phase so far — introduce the new representation
alongside the old, verify equivalence, migrate one consumer at a time, remove the old path
last (the "parallel change" pattern). Each stage is its own small, independently-mergeable
PR; if something breaks, the stage boundary tells you where to look.

- **Stage 1 — Define, don't wire. ✅ done (2026-07-18)** Scope resolved: the target is the
  four-way tag already living as ad hoc tuples in `_build_per_suite_run_info`'s
  `physics_arg_sources` list (`("host", var, mod)` / `("ddt_member", var, mod, path)` /
  `("cap_var", std_name)` / `("block",)`) — not `_RunMetadataMaps` literally. Added to
  `xdsl_ccpp/dialects/ccpp.py`:
  - `ArgSourceKind` (`StrEnum`: Host/DdtMember/CapVar/Block) + `ArgSourceKindAttr`
    (`EnumAttribute` wrapper), following the exact `TableTypeKind`/`TableTypeKindAttr`
    convention already established in this dialect.
  - `ResolvedArgOp` (`ccpp.resolved_arg`): `arg_name` + `source_kind` (required), plus
    `var_name`/`module_name`/`member_path`/`std_name` (all optional, kind-dependent). Custom
    `verify_()` enforces the required/forbidden field combination per kind, following the
    `StrCmpOp` custom-verify precedent in `ccpp_utils.py`.
  - Both registered on the `CCPP` dialect (ops and attrs lists).
  - Note: `HostVarRefOp` already handles the actual SSA-value construction for Host/DdtMember
    (it already accepts a `member_name` param) — `ResolvedArgOp` doesn't replace that, it
    makes the *resolution decision* durable one level up from where value construction
    already happens. That split is exactly what Stage 3 migrates.
  - 15 new unit tests in `tests/unit/test_resolved_arg_op.py` (dialect registration, one
    positive construct+verify case per source_kind, 8 negative verify cases covering every
    required/forbidden-field violation). All passed on first write (after fixing one
    self-inflicted test-script mistake before committing anything: `StrEnum.auto()` squashes
    `DdtMember` → `"ddtmember"`/`CapVar` → `"capvar"`, no underscore — same behavior the
    existing `TableTypeKind.DDT` → `"ddt"` already has, not a new inconsistency).
  - Verified zero impact on the generator, as intended: 242 passed (227 + 15 new) unit tests,
    FileCheck unchanged at 44 passed + 1 xfailed (identical counts to pre-Stage-1 baseline —
    nothing in `run_dispatch.py` was touched, so this was guaranteed by construction, not
    just observed).
  - Done on local branch `phase3b-stage1-resolved-arg-op`, uncommitted as of this writing.
- **Stage 2 — Dual-build, don't switch consumers. ✅ done (2026-07-18)** Added
  `_resolved_arg_op_from_source(arg_name, src)` to `run_dispatch.py`: converts one
  `physics_arg_sources` tuple into its `ResolvedArgOp` equivalent. `_build_per_suite_run_info`
  now builds `resolved_arg_ops` (one op per callee input arg, in the same order as
  `physics_arg_sources`) right after the classification loop, and stores it as a new key in
  the `per_suite` dict — nothing downstream reads it yet, so this is guaranteed zero-impact by
  construction, not just by observation.
  - Added a direct unit test for `_build_per_suite_run_info` (previously untested at this
    level — see the "also proposed" list above) in `tests/unit/test_run_dispatch.py`: a
    hand-built `meta_data`/`_RunMetadataMaps` fixture producing exactly one arg of each of the
    four source kinds (host, one-level-nested ddt_member, cap_var, block), asserting both that
    `physics_arg_sources` classifies each correctly and that `resolved_arg_ops`' fields mirror
    each tuple's payload field-for-field. All passed on first write.
  - Verified byte-identical generator output before/after, using the same three representative
    examples as Phase 3a's own verification (`kessler`, `advection` for constituents,
    `helloworld`+`hello_world_host_ccpp_t.meta` for multi-instance) — `diff` exit code 0, zero
    output, all three.
  - Full suite: 289 passed (288 + 1 new) unit, 44 passed + 1 xfailed FileCheck — identical
    FileCheck counts to pre-Stage-2, as expected since no consumer was touched.
  - Merged as PR #10. **Post-merge Copilot review round (3 comments, all fixed):**
    (1) `_resolved_arg_op_from_source`'s `else` branch silently mapped *any* unrecognized
    `physics_arg_sources` kind to `ArgSourceKind.Block` — now the `"block"` tag is handled
    explicitly and anything else raises `ValueError`. (2) The `resolved_arg_ops` list
    comprehension used `zip(callee_input_names, physics_arg_sources)`, which would silently
    truncate if the two ever diverged in length — extracted into a new
    `_build_resolved_arg_ops` helper with an explicit length check, independently unit-tested
    with contrived mismatched-length inputs. (3) The `"block"` branch itself never unpacked
    `src`, so a malformed `("block", ...)` tuple with extra fields would silently drop them,
    unlike the other three kinds (which fail on unpack) — now unpacks `(_,) = src` too. A
    fourth, self-found issue in the same theme: an empty tuple hit `IndexError` instead of the
    same clear `ValueError` as every other malformed input — fixed with an explicit
    empty-tuple guard. All four covered by new regression tests in `test_run_dispatch.py`.
- **Stage 3 — Migrate one consumer at a time. ✅ done (2026-07-18)** Turned out to be a
  single-consumer migration: a repo-wide grep confirmed `_build_run_dispatch_chain` is the
  *only* function outside `_build_per_suite_run_info` itself that reads `physics_arg_sources`
  (`_build_run_block_signature`/`_build_run_chain_preamble` never touch it). Migrated all 5
  internal read sites — HostVarRefOps, ArraySectionOps, RowMajorConvertOps, call-arg building,
  and the cap-var inout-echo mirror-back — from `physics_arg_sources[i]` tuple unpacking to
  `resolved_arg_ops[i]` (`ResolvedArgOp`) field access (`.source_kind.data`, `.var_name.data`,
  `.module_name.data`, `.member_path.data`, `.std_name.data`), then removed the now-dead
  `physics_arg_sources = info["physics_arg_sources"]` local read at the top of the loop.
  `_build_per_suite_run_info` itself is untouched — still builds and returns both forms.
  Verified byte-identical raw output for `kessler` (both `ftn` and `cpp_header` targets,
  extending Phase 1's dual-target discipline), `advection` (constituents), and
  `helloworld`+`ccpp_t` (multi-instance) — `diff` exit code 0, zero output, all four
  target/example combinations. Full suite: 296 passed, 1 xfailed — unchanged from
  pre-Stage-3, as expected for a read-site swap with no behavior change.
  `ruff --select F401` clean. Because this was the only consumer, Stage 3 is fully done, not
  partial. Done on local branch `phase3b-stage3-migrate-run-dispatch-chain`, uncommitted
  upstream as of this writing.
- **Stage 4 — Remove the old path. ✅ done (2026-07-18)** Rather than deleting a separate
  tuple-building block and keeping the Stage 2 tuple→op conversion helpers, went one step
  further: the classification loop now constructs `ResolvedArgOp` directly at each of its 5
  append sites (`arg_name` is already in scope there from the enclosing `for` loop), so there
  was never a tuple to delete a *conversion* from — `_resolved_arg_op_from_source` and
  `_build_resolved_arg_ops` (Stage 2's bridge functions) became dead code and were removed
  entirely, along with their unit tests. The two remaining internal consumers inside
  `_build_per_suite_run_info` — the `non_host_args` list comprehension and the host-global-stub
  collection loop — now read `resolved_arg_ops` directly instead of the tuple form.
  - This also fully *closes* (rather than just guards against) Copilot's Stage-2 length-mismatch
    concern: since `resolved_arg_ops` is built in the same loop, same index, as
    `callee_input_names`, there is no longer a second list that could diverge from it at all.
  - Updated two now-stale docstrings describing the tuple form: `ResolvedArgOp`'s own docstring
    in `ccpp.py`, and `test_resolved_arg_op.py`'s module docstring (both previously said
    "not yet wired into the generator" / described the ad hoc tuple format).
  - Rewrote `test_run_dispatch.py`'s `TestBuildPerSuiteRunInfoResolvedArgOps` test to assert
    `resolved_arg_ops`' fields directly (kind + var_name/module_name/member_path/std_name per
    arg) instead of comparing against the now-gone tuple.
  - Verified byte-identical raw output across all 4 target/example combinations used
    throughout Phase 3b: `kessler` (`ftn` and `cpp_header` targets), `advection`
    (constituents), `helloworld`+`ccpp_t` (multi-instance) — `diff` exit code 0, zero output,
    all four.
  - Full suite: 289 passed, 1 xfailed (down from 296 — 7 tests removed for the deleted bridge
    functions, 1 rewritten in place; FileCheck counts unchanged). `ruff --select F401` clean.
  - Net -107 lines across the 4 changed files (`run_dispatch.py`, `ccpp.py`,
    `test_run_dispatch.py`, `test_resolved_arg_op.py`) — the first real (not just relocated)
    line-count reduction in Phase 3b, since Stage 4 is where the dual-representation scaffolding
    from Stage 2 actually gets torn down.
  - Done on local branch `phase3b-stage4-remove-old-path`, uncommitted upstream as of this
    writing. **Phase 3b is now fully complete.**

### Phase 3a outcome ✅ done

**A real boundary correction surfaced immediately, before writing any code:** the naive
"140 to 1857" line range (dataclasses through the last run-dispatch function) turned out to
be non-contiguous. `_derive_camel_case_name` and `_build_suite_variables_fn` — both meant to
stay in `ccpp_cap.py` per Phase 5 — sit physically between the 3 `_Run*` dataclasses (140–179)
and the actual run-dispatch functions (456–1856). Caught via an unexpected `ModulePass: 1`
hit while checking import usage against the naive range, which shouldn't have appeared if the
range were truly just the run-dispatch cluster — traced it back and found the gap. Corrected
range: 77–106 (`_resolve_ddt_access_path`, previously a shared helper, but confirmed its only
non-recursive caller was inside this cluster, so it moved wholesale rather than staying
shared) + 139–179 (the 3 dataclasses) + 456–1856 (the 9 run-dispatch functions, confirmed
`_generate_run_fn`/`_generate_suite_part_list_fn` are the entry points
`_generate_ccpp_cap_module` calls, exactly mirroring Phase 2's pattern).

Moved all of the above into a new `xdsl_ccpp/transforms/run_dispatch.py` (1,531 lines),
called directly from `ccpp_cap.py`'s `_generate_ccpp_cap_module` via
`_generate_run_fn`/`_generate_suite_part_list_fn` — same plain-importable-module pattern as
`lifecycle_cap.py`/`constituent_cap.py`, deferring pass-status to Phase 6. No new circular
import: `_bare`/`_build_host_var_map`/`_get_suite_lifecycle_ret_info` already lived in
`cap_shared.py` from Phase 2's fix, so `run_dispatch.py` imports them from there directly.

Learning from Phase 2's off-by-two mistake, verified every segment boundary with `cat -n`
before extracting this time — result: **208/208 unit tests passed on the first try**, no
`NameError` debugging round needed.

Proactively ran `ruff check --select F401` (not just waiting for review) and found 19 unused
imports — 17 in `ccpp_cap.py` (leftovers from code that moved out) and 2 in `run_dispatch.py`
(false positives from usage-checking against comments/type-hint strings, same class of
mistake as the `ModuleVarOp` Copilot caught in Phase 2). Fixed all 19 with `ruff --fix`. Also
ran the full (non-`F401`) ruff check out of caution and found 148 more findings, nearly all
`F841` (unused local variables) — confirmed these are pre-existing lint debt in the moved
code itself (consistent with the 273 repo-wide pre-existing violations found back during CI
setup), not something the move introduced. Left untouched — fixing them would conflate
unrelated cleanup with a change whose whole value is being verified byte-identical; flagged
for the project owner rather than silently bundled in.

Verified byte-identical (not just FileCheck-passing) using three representative examples this
time, deliberately chosen to cover this cluster's specific territory: `kessler` (chost/general),
`constprop` (constituent dispatch), and `helloworld` with `hello_world_host_ccpp_t.meta`
(multi-instance/`ccpp_t` threading path, run through `generate-host-match` too) — all three
`diff` exit code 0 against pre-Phase-3a output.

**Result:** `ccpp_cap.py` 2,372 → 888 lines (−1,484). New `run_dispatch.py`: 1,531 lines.
Combined total 2,419 vs. the pre-Phase-3a 2,372 (+47) — flat, as expected for a mechanical
move. Full suite: 208/208 unit, 44 passed + 1 xfailed FileCheck.

Committed on branch `phase3a-extract-run-dispatch` and merged to upstream `main` by the
project owner (2026-07-17).

### Post-merge: two more review-round fixes (2026-07-17)

Both found via a Copilot review pass on the Phase 3a PR — same pattern as Phase 1's
buffer-overflow finding: real, pre-existing correctness bugs surfaced by review, fixed
separately from the structural move itself.

1. **Duplicate "no suite matched" error text diverged across two implementations.** The
   project owner applied a Copilot-suggested one-line fix (missing space: `"found"` →
   `" found"`) to `run_dispatch.py`'s two occurrences of this fallback error message. That
   broke 15 golden FileCheck tests (8 checking generated Fortran text, 7 checking raw MLIR —
   `tests/filecheck/examples/end_to_end/*.mlir` and `.../completed_ir/*.mlir`), which were
   fixed to expect the corrected text. But re-running the full suite fresh (not trusting an
   earlier, apparently-stale "1 failed" reading) showed all 15 *still* failing — traced to a
   **third, independent copy** of the exact same error-message-building code in
   `lifecycle_cap.py:124` (the init/finalize/timestep lifecycle dispatcher's own "no suite
   matched" path), which the original fix missed entirely. Fixed to match. A 4th occurrence
   in `ccpp_cap.py:364` (a different subroutine, `ccpp_physics_suite_variables`) was already
   correct and unrelated. Full suite green after: 227 passed (208 + 19 new `run_dispatch.py`
   unit tests), 44 passed + 1 xfailed FileCheck.
2. **Case-sensitivity bug in array-sectioning dimension lookup**, `run_dispatch.py` lines
   930-934: `host_var_map` is always keyed by lowercased `standard_name` (see
   `_build_host_var_map`'s docstring/implementation), and the loop already lowercases
   `dim_names_list[0]` before comparing it — but used `dim_names_list[1:]` directly,
   unlowercased, as a dict key. Confirmed via code inspection, then empirically: found a real
   example with a mixed-case dimension name (`examples/advection/cld_liq.meta`'s
   `vertical_LAYER_dimension`) and diffed generated output before/after the fix — zero diff,
   meaning this specific occurrence doesn't currently exercise the buggy branch (likely gated
   by some other row-major/array-section-eligibility condition), but the fix carries zero
   regression risk on any current example while closing a real latent bug for whichever
   combination *does* reach it. One-line fix: `.lower()` the loop variable to match.

Also added **19 new direct unit tests** for `run_dispatch.py`'s three "pure" functions (no
xDSL IR/Block fixtures needed) in `tests/unit/test_run_dispatch.py`:
`_resolve_ddt_access_path` (direct/nested/two-level/unreachable/circular-depth-guard/
multiple-candidates), `_resolve_member_subscripts` (colons/integers/standard_name
resolution/case-insensitivity/unresolved-passthrough), and `_build_run_metadata_maps`
(host_var_map/host_block_std_names/constituent_std_names/ddt_type_names/ddt_instance_map/
ddt_parent_map, including a genuine nested-DDT case). All 19 passed on first write. The
remaining, IR-heavy functions in this module still rely on the existing end-to-end examples
for coverage — see the "Also proposed, not yet implemented" list in the session-status block
up top for what's still missing there.

## Phase 4 — Consolidate with `suite_cap.py`'s argument classification (flagged 2026-07-17)

**The one place in this whole plan where a real line-count reduction looks plausible, not
just relocation.** `suite_cap.py`'s `_ArgClassification`/`_classify_args` (file is 1,770 lines
total) and the run-dispatch cluster's own argument-resolution logic (~1,480 lines, moving in
Phase 3) solve the same kind of problem — "which bucket does this argument belong to / where
does its data come from" — at adjacent layers of the pipeline, with no shared abstraction
between them.

**Must come after Phase 3b, not before.** 3b is exactly where the run-dispatch side's
classification model gets redesigned (dataclasses → real IR ops). Consolidating beforehand
would mean merging `suite_cap.py`'s classifier with the soon-to-be-replaced dataclass version,
then redoing the consolidation again once 3b lands — duplicate work for no reason.

**Must come before the (renumbered) Phase 5 slim-down/docs step**, so that step documents the
truly final structure once, not an intermediate one that's about to change again.

No further design decided yet beyond the sequencing — the actual shape of the shared
abstraction (a common classification module both `suite_cap.py`'s pass and `run_dispatch.py`
import? merged into one of the two?) is deferred until Phase 3 is done and this phase
actually starts.

### Investigation (2026-07-18): the coupling is broader — and different — than assumed

Before writing any code, mapped out both classification systems in detail. They are **not**
the same decision duplicated at adjacent layers, as the framing above assumed — they solve
genuinely different problems:

- `suite_cap.py`'s `_classify_args` decides the **suite's own subroutine signature** by
  intent/dims (`framework_vars` / `input_arg_list` / `output_arg_list` / `ncol_meta`).
- `run_dispatch.py`'s `ResolvedArgOp` classification decides, one layer up, **where a
  call-site argument's data comes from** (host var / DDT member / cap var / block arg).

The actual overlapping concept — "does the cap own this variable, or does it come from
outside?" — spans **three** files, not two:

1. `suite_cap.py`'s `_is_framework_managed` — excludes interstitial/advected/allocatable-real
   args from the suite's own subroutine signature (checks `is_interstitial` /
   `type==real` + `dimensions>0` + (`advected` or `allocatable`) attributes directly).
2. `ccpp_cap.py`'s `cap_var_map` construction (`_generate_ccpp_cap_module`, ~100 lines) — a
   *separate*, later heuristic that re-scans the suite's **already-built** public signature
   (`public_fns`) and promotes anything still unresolved (known framework arrays like
   `ccpp_constituents`, plus any unmatched scratch var with no host/HOST-table match) to a
   cap-owned module variable.
3. `run_dispatch.py`'s `ArgSourceKind.CapVar` — just *consumes* `cap_var_map` from #2 as a
   parameter (`std_name in cap_var_map`). Already a single source of truth; no duplication
   here despite being the piece named in the original framing above.

So the real risk is #1 vs #2: two **independently-implemented, sequentially-dependent**
heuristics for "is this cap-owned," computed via completely different logic, that could
silently disagree as the codebase evolves. (`_build_run_dispatch_chain` already has a runtime
`len(call_args) != len(callee_input_types)` check that would catch a resulting signature
mismatch with a clear error rather than silently miscompiling — so this isn't a live,
un-guarded bug today, just a structural risk.)

**Decision (2026-07-18, per project owner): narrow extraction now.** Move `_is_framework_managed`
(suite_cap.py) and the cap_var_map-building block (ccpp_cap.py) into named, independently
unit-testable functions in a shared module, called in their existing order — suite_cap.py still
decides its own signature first, ccpp_cap.py still does its "catch what's left over" pass after.
No behavior change, no new IR, `cap_var_map` stays a plain dict. Same risk profile as every
Phase 3a/3b stage: mechanical move, byte-identical verification.

**Deferred for later review: full IR unification.** Considered and set aside for now, not
because it lacks merit but because the payoff doesn't yet justify the cost at this project's
current scale (single contributor, thin test net). What it would be and why it matters is
summarized below; **the actual staged execution plan is now tracked separately as Phase 7**
(see below) rather than duplicated here.

- **What it would be:** a single classification decided *once*, upfront, as durable IR (in the
  same spirit as `ResolvedArgOp`), computed *before* `suite_cap.py` builds its subroutine
  signature. `suite_cap.py`, `ccpp_cap.py`'s cap_var_map logic, and `run_dispatch.py` would all
  read from that one decision instead of three sequential, independently-computed heuristics.
- **Long-term advantage:** eliminates the drift risk structurally rather than just making it
  easier to spot — with one decision point, #1-vs-#2 disagreeing stops being a possible bug at
  all, not just a less-likely one. Also extends Phase 3b's exact rationale ("resolution bugs
  and printing bugs are separately testable") one layer up, and gives future consumers (a new
  backend, a different cap layout, `--emit-mlir`-based debugging) the classification for free
  instead of each having to re-derive or trust the same fragile heuristics.
- **Revised (2026-07-19): it *is* decomposable into small stages, Phase-3b style — an earlier
  version of this write-up said otherwise, and that was overstated.** The original reasoning was
  that `ccpp_cap.py`'s cap_var_map is computed by inspecting `suite_cap.py`'s **already-built**
  signature (`public_fns`), so unifying them would mean restructuring pipeline order wholesale.
  On closer inspection that conflates an implementation convenience with a real dependency:
  `_is_framework_managed` is a pure function of arg attributes (`is_interstitial`, `type`,
  `dimensions`, `advected`, `allocatable`) already present in `meta_data` *before* `suite_cap.py`
  runs at all. `ccpp_cap.py` reading `public_fns` instead of calling the same predicate directly
  is a shortcut in today's code, not a fundamental ordering requirement — nothing stops it from
  computing the same classification independently, at the same early point `suite_cap.py` does.
  See Phase 7 for the resulting 4-stage plan and the one real wrinkle it surfaced (classification
  vs. type-dependent scratch-var construction).
- **Not foreclosed by doing narrow extraction first.** The narrow extraction's named functions
  (`_is_framework_managed`'s logic, the cap_var_map derivation) become the natural seed for
  Phase 7's Stage 1 — the hard-won domain knowledge doesn't need rediscovering.
- **Bonus for that later work: the 12 new unit tests are a correctness oracle, not just
  coverage.** `test_cap_shared.py`/`test_ccpp_cap.py` pin down exact input→output behavior for
  both functions in isolation, independent of any end-to-end Fortran example. When Phase 7
  eventually reimplements this logic as IR-emitting code, these tests (or fixtures adapted from
  them) let that work verify the new implementation classifies the same fixtures the same way,
  without needing to regenerate and diff whole Fortran outputs per case — a much tighter
  feedback loop than the FileCheck examples alone.

### Phase 4 outcome ✅ done (narrow extraction)

- **`_is_framework_managed`** moved from a `@staticmethod` on `suite_cap.py`'s
  `GenerateSuiteSubroutine` into a plain module-level function in `cap_shared.py` (already the
  established neutral-leaf home for cross-file cap-generation helpers). `suite_cap.py`'s
  `_classify_args` now imports and calls it directly.
- **A second, previously-undiscovered duplication was also closed as part of this move**:
  `cap_shared.py`'s `_get_suite_lifecycle_ret_info` had its own comment-flagged partial mirror
  of the same logic (`fn_arg.hasAttr("is_interstitial")` only, missing the
  advected/allocatable-real-array branch, with a comment literally saying "Mirror suite_cap.py's
  `_is_framework_managed` logic"). Swapped it to call the real shared function instead.
  Verified this is behavior-preserving, not just hopeful: that call site already requires
  `not has_dims` before reaching the interstitial check, and `_is_framework_managed`'s
  array-shaped branch requires `dimensions > 0` — mutually exclusive, so for every arg that can
  reach this code path the full check reduces to exactly the narrower one it replaced.
- **`_build_cap_var_map`** extracted from a ~100-line inline block in
  `_generate_ccpp_cap_module` into a named, module-level function in `ccpp_cap.py`, returning
  `(cap_var_map, host_var_map_lc, scratch_var_list)`. Kept as a separate function from
  `_is_framework_managed` deliberately — per the investigation above, this is a genuinely
  different, later-stage heuristic (re-scanning the suite's already-built public signature for
  what's still unresolved), not a duplicate of it; the function's docstring says so explicitly
  so a future reader doesn't try to merge them without re-reading this plan.
- **First direct unit tests for any of `cap_shared.py`, `ccpp_cap.py`, or `suite_cap.py`** —
  none had one before. Added `tests/unit/test_cap_shared.py` (7 tests covering
  `_is_framework_managed`'s interstitial/real-array/dims-guard branches) and
  `tests/unit/test_ccpp_cap.py` (5 tests covering `_build_cap_var_map`'s framework-array,
  scratch-var, host-matched-exclusion, and constituent-tendency cases, using the
  `XMLSuite`/`XMLGroup`/`XMLScheme` fixture classes already in `ccpp_descriptors.py`). All 12
  passed on first write.
- Verified byte-identical raw output across the same 4 target/example combinations used
  throughout Phase 3b (`kessler` ftn + cpp_header, `advection` — which exercises the
  advected/allocatable-real-array branch directly, `helloworld`+`ccpp_t`).
- Full suite: 301 passed (289 + 12 new), 1 xfailed. `ruff --select F401` clean except one
  pre-existing, unrelated finding (`i32` unused in `suite_cap.py`, confirmed present on `main`
  before this change via `git stash`) — left untouched per this project's established practice
  of not bundling unrelated cleanup into a structural-move PR.
- Full IR unification remains deferred — see the investigation section above for the complete
  writeup (what it would look like, long-term advantage, why it's harder than it looks, and why
  narrow extraction doesn't foreclose it).
- Done on local branch `phase4-cap-ownership-extraction`, uncommitted upstream as of this
  writing.

## Phase 5 — Slim `ccpp_cap.py` down to its real remaining job

After Phases 1–4, `ccpp_cap.py` should contain only `_build_suite_variables_fn` plus
`_generate_ccpp_cap_module` (now a thin orchestrator calling into the extracted modules) and
`apply()`.

- Update `DEVELOPERS.md` and the pipeline-position docstrings (which already document ordering
  like "Runs after `generate-ccpp-cap`...") to reflect the new sub-passes.
- Treat doc updates as part of this phase, not follow-up cleanup — doc/code drift is already
  a known weak spot in this project (e.g. `multi_instance_plan.md` describing an already-shipped
  feature as a future plan).

### Phase 5 outcome ✅ done

`ccpp_cap.py`'s structure already matched the target by the time this phase started — Phases
1-4 did the actual slimming; nothing left to restructure. Module-level: `_iter_schemes`,
`_collect_public_suite_functions`, `_build_cap_var_map` (all extracted in earlier phases).
Class `CCPPCAP`: `_derive_camel_case_name`, `_build_suite_variables_fn`,
`_generate_ccpp_cap_module`, `apply`. So this phase was pure documentation, as the plan
anticipated.

Checked every pipeline-position docstring across `xdsl_ccpp/transforms/` (found via grep for
"Runs after"/"Runs immediately after"/"Runs as its own pass"/"Runs before") against the actual
pass ordering in `ccpp_dsl.py`'s `_build_pipeline`. All but one were already accurate —
`cpp_interop.py` and `ccpp_cap.py` in particular were already correctly documented from Phase 1
onward. The one gap: `gpu_ccpp_cap_pass.py` said "Runs after generate-ccpp-cap and
generate-host-match," true but incomplete since Phase 1 added `generate-cpp-cap` between them —
fixed to also mention it.

`DEVELOPERS.md` itself was the real target, and was meaningfully stale:
- Never mentioned `generate-cpp-cap` at all, anywhere — not in the pass reference table, not in
  the transformation-passes table. A real registered pass (Phase 1) completely undocumented.
- Its Dialects table referenced a `ccpp_cap_dialect.py` file that **doesn't exist** — the actual
  file is `ccpp.py`. Unclear whether this predates the refactor or is a naming drift from it;
  either way, fixed with an accurate description of `ccpp.py`'s actual contents (suite-structure
  ops, metadata table ops, kind ops, `CcppHandleOp`, `ResolvedArgOp`/`ArgSourceKind`).
- No mention anywhere of `lifecycle_cap.py`, `constituent_cap.py`, or `run_dispatch.py` (Phases
  2/3a) — added a new subsection explaining these are plain modules `ccpp_cap.py` calls
  directly, not separately registered passes (ties into Phase 6's still-open decision).
- `cap_shared.py` (created in Phase 2, grown through Phase 4) wasn't in the shared-utilities
  table at all — added, with its current export list.
- Added a clarifying note that the driver's actual pass list (`ccpp_dsl.py`'s `_build_pipeline`)
  is conditional (`generate-host-match` only with `--host-files`; `generate-ccpp-cap`/
  `generate-cpp-cap` always as a pair) and doesn't match the doc's fixed example pass-list
  strings, so a reader doesn't assume the copy-paste examples are what the driver actually runs.

**Scoped out at the time, done later (2026-07-19):** `lower-ccpp-utils` and `fir-to-meta`
passes were also missing from `DEVELOPERS.md`'s pass reference table, but predated this refactor
and were unrelated to Phases 1-4, so left alone per this project's practice of not bundling
unrelated cleanup into a phase PR. Picked up as its own small, independent backlog item once
Phase 4/5/6/7 were all otherwise clear — see the backlog list above for the fix (both added to
the pass reference table, plus a note that neither is part of the main `ccpp_xdsl` pipeline,
since `fir-to-meta` is a standalone alternative frontend used by `fir2meta.py`/
`ccpp_validate_fir.py`/`ccpp_validate_source.py`, and `lower-ccpp-utils` lowers `ccpp_utils` ops
for consumers that need fully-lowered MLIR rather than printed Fortran).

Verified: 302 passed, 1 xfailed (unchanged — pure docs + one docstring edit, no behavior
change). `ruff --select F401` clean. Done on local branch `phase5-slim-down-docs`, uncommitted
upstream as of this writing.

## Phase 6 — Decide pass-status for the new pieces ✅ decided (2026-07-18)

Original framing (written before any of Phases 1-4 existed) grouped `cpp_interop` and
`run_dispatch` together as "substantial enough to justify full `ModulePass` registration," with
`lifecycle_cap`/`constituent_cap` as "more tightly coupled... likely fine as plain modules." That
grouping was drawing the line by size/substantiality. Having now actually built and lived in all
four pieces, the real dividing line turned out to be architectural shape, not size — and it cuts
differently than originally guessed:

- **`cpp_interop.py`**: already promoted, in Phase 1 — it's `generate-cpp-cap`. This one fits the
  pass model cleanly because it operates on an *already-complete, separate* downstream artifact:
  it runs after `generate-ccpp-cap` has finished and re-discovers the just-built ccpp module by
  scanning the block for `TablePropertiesOp`/`CcppHandleOp`, exactly the way a normal pass
  consumes a prior pass's output.
- **`run_dispatch.py`, `lifecycle_cap.py`, `constituent_cap.py`**: **decided to keep all three as
  plain internal modules, not registered passes.** All three are called *mid-construction* —
  contributing functions directly into the *same* ModuleOp `ccpp_cap.py` is still assembling —
  and depend on shared Python state (`host_var_map`, `cap_var_map`, the `ccpp_t` handle,
  `meta_data`) that exists only as plain function parameters, not durable IR. Promoting any of
  them to a standalone pass would require re-deriving that state from the IR the same way
  `cpp_interop.py` does today — which isn't possible until that state actually becomes durable
  IR. That's precisely what the deferred "full IR unification" design (recorded under Phase 4
  above) would provide: if it's ever done, this decision should be revisited, since it would
  remove the blocker for all three, not just `run_dispatch.py`.
- **Why the original grouping was off:** `run_dispatch.py`'s size/substantiality (~1,480 lines
  pre-Phase-3a) made it *look* like it belonged with `cpp_interop.py`, but size was never the
  actual criterion — architectural shape was. `run_dispatch.py` is called exactly the same way
  `lifecycle_cap.py`/`constituent_cap.py` are (mid-construction, same ModuleOp, shared Python
  state), so it belongs with them, not with `cpp_interop.py`.
- **No code changes from this decision** — it's a "keep as-is" outcome, recorded here (and in
  `DEVELOPERS.md`'s description of these three modules) so a future reader doesn't re-litigate it
  without first reading the full-IR-unification dependency above.

**This closes out the original 6-phase refactor plan.** All six phases are now done. Phase 7,
below, is a separately-tracked, deferred sub-plan — not part of the original scope, not
scheduled, and not a prerequisite for anything above.

---

## Phase 7 — Full IR unification (deferred sub-plan — not part of the original 6-phase scope)

Added 2026-07-19, after the Phase 4 investigation (see above) showed this is genuinely
stageable rather than the monolithic rewrite first assumed. **Stages 1-4 done (2026-07-20)** —
tracked here with an actionable staged plan so whoever does isn't starting from a paragraph of
rationale alone.

**Goal:** a single "does the cap own this variable, or does it come from outside" decision,
computed once and durable in IR, consumed by `suite_cap.py`, `ccpp_cap.py`'s cap_var_map logic,
and `run_dispatch.py` — replacing today's three sequential, independently-computed heuristics.
Full motivating rationale (why the current split exists, the long-term advantage) is under
Phase 4 above; this section is the execution plan.

- **Stage 1 — Define, don't wire. ✅ done (2026-07-20).** The open design question (candidate
  name `ccpp.arg_ownership`, or extend `ArgSourceKind`/`ResolvedArgOp`) resolved by comparing
  both bucket-sets against the actual code before writing anything: they're related but not the
  same classification. `_is_framework_managed`'s docstring is explicit that it decides
  suite-ownership *before* the suite's subroutine signature exists — interstitial/advected/
  allocatable args never become dummy args at all, so they never reach `ResolvedArgOp`'s world
  (there's deliberately no `SuiteOwned` case in `ArgSourceKind`, since the question never comes
  up there). Conversely `ArgSourceKind` splits host-matched into `Host`/`DdtMember` — a finer,
  later-stage distinction (does the SSA reference need a `member_path`) the ownership question
  doesn't care about. Checked `suite_cap.py:280`/`:697`'s direct `is_interstitial`/`allocatable`
  checks too, to confirm the new op doesn't need to carry *why* an arg is `SuiteOwned` — those
  are separate downstream concerns (rank-reducing slice construction, scratch-var allocation
  shape) that stay independent metadata queries. **Decision: a new, separate op**, not an
  extension — forcing a `SuiteOwned` case into `ArgSourceKind` would add a kind that never needs
  the SSA-construction payload the enum exists for.
  - Added to `ccpp.py`, mirroring `ResolvedArgOp`'s exact established pattern: `ArgOwnershipKind`
    (`StrEnum`: SuiteOwned/HostMatched/CapScratch/Block — explicit string values, not `auto()`,
    same reason `ArgSourceKind` uses them: `auto()` squashes `HostMatched`/`CapScratch` to
    `"hostmatched"`/`"capscratch"`, no underscore) + `ArgOwnershipKindAttr` (`EnumAttribute`
    wrapper) + `ArgOwnershipOp` (`ccpp.arg_ownership`): `arg_name` + `ownership_kind` (both
    required) + `std_name` (required only for HostMatched/CapScratch — the key into the
    existing `host_var_map_lc`/`cap_var_map` dicts; forbidden for SuiteOwned/Block). Custom
    `verify_()` enforces this, following `ResolvedArgOp`'s required/forbidden-per-kind
    precedent exactly. Both registered on the `CCPP` dialect.
  - 14 new unit tests in `tests/unit/test_arg_ownership_op.py` (dialect registration, one
    positive construct+verify case per kind — including the string-tag construction form — plus
    4 negative verify cases, one per required/forbidden-field violation). All passed on first
    write.
  - **Not called by any pass** — zero changes to `suite_cap.py`, `ccpp_cap.py`, or
    `run_dispatch.py`. Verified zero-impact by construction: full suite 392 passed (378 + 14
    new) unit, FileCheck unchanged at 44 passed + 1 xfailed (identical to the pre-Stage-1
    baseline). `ruff check` clean on the new test file; the one new finding in `ccpp.py` itself
    (a quoted type annotation in `ArgOwnershipOp.__init__`) intentionally left matching
    `ResolvedArgOp`'s own constructor's identical pre-existing style at the same file, rather
    than fixing only the new instance and introducing inconsistency.
- **Stage 2 — Dual-build, don't switch consumers. ✅ done (2026-07-20).**
  - **Placement decision, resolved before writing code:** `ArgOwnershipOp` (Stage 1) is never
    inserted into the module as real IR. Checked whether anything assumes an `ArgumentTableOp`'s
    block contains only `ArgumentOp`s — it does: `BuildMetaDataDescriptions`'s visitor asserts
    `self.arg_token is not None` right after dispatching each child, with no handler for any
    other op type, so inserting `ArgOwnershipOp` as a sibling would crash that visitor (used by
    nearly every classification consumer) the next time it ran. Also checked whether the
    classification is suite/group-scoped (which would rule out attaching it to the
    scheme-level `ArgumentOp`) — it isn't: every lookup involved (`is_interstitial` presence,
    `model_var_name` presence, the static frozensets, `host_var_map_lc`) is suite-independent, so
    the decision for a given arg is the same regardless of which suite/group uses it. **Chosen
    design (hybrid):** added `ownership_kind` as a new `opt_prop_def(ArgOwnershipKindAttr)`
    field directly on `ccpp.ArgumentOp` (moved `ArgOwnershipKind`/`ArgOwnershipKindAttr` earlier
    in `ccpp.py`, before `ArgumentOp`, so the field type is defined in time) — matching
    `HostVariableMatchPass`'s own exact precedent for `model_var_name`/`is_interstitial`, the
    one proven cross-pass-durability pattern in this codebase. `ArgOwnershipOp` itself is kept
    exactly as Stage 1 built it and still gets used, just not by insertion: the new
    classification function constructs and verifies one per arg (getting `verify_()`'s
    impossible-to-construct-inconsistent-state guarantee, and reusing Stage 1's tested type
    rather than idling it), then the pass copies only `.ownership_kind` onto the real
    `ArgumentOp` — reusing the arg's own existing `standard_name` property rather than storing
    `std_name` a second time. Exactly how `ResolvedArgOp` is already used today (constructed,
    verified, consumed — never inserted into a block).
  - **Early-computability, checked per bucket rather than assumed:** the 2026-07-19 revision's
    optimism ("`_is_framework_managed` is a pure function of arg attributes already present in
    `meta_data`") only actually covers the `SuiteOwned` bucket. Checked whether the same holds
    for `_build_cap_var_map`'s `HostMatched`/`CapScratch`/`Block` split — it does, but not for
    free: that function iterates `public_fns[_callee_cv]`'s *already-built* dummy-arg list, but
    every actual classification check inside the loop (`FRAMEWORK_STD_NAME_TO_CAP_VAR`,
    `CCPP_FRAMEWORK_STD_NAMES`, `CCPP_ERROR_STD_NAMES`, a HOST-type-table scan, `host_var_map_lc`)
    is itself meta_data-only, no signature dependency. The only reason `public_fns` appeared
    load-bearing was to know *which args exist as dummy args at all* — which is answered by
    `model_var_name` presence (HostMatched) or nothing further being needed (the classification
    doesn't require knowing whether an arg ends up on a signature, just what it *would* resolve
    to if it did). Confirmed empirically, not just reasoned: `classify_arg_ownership`, built
    purely per-`ArgumentOp` with zero suite/group iteration, agreed with `_build_cap_var_map`'s
    real output across every real example tested (see below) — the one true discrepancy found
    was a *test* scoping bug (below), not a classification bug.
  - **Implementation:** `cap_shared.py` gained `FRAMEWORK_STD_NAME_TO_CAP_VAR` (moved out of
    `_build_cap_var_map`'s function body, shared rather than duplicated), `_collect_host_block_std_names`
    (the HOST-type-table scan, same treatment), and `classify_arg_ownership(arg_op,
    host_var_map_lc, host_block_std_names) -> ArgOwnershipOp` (the actual classification,
    operating on the real `ccpp.ArgumentOp`'s typed properties — a different access pattern than
    `_is_framework_managed`'s `hasAttr`/`getAttr`, which is designed for the separate
    `CCPPArgument` descriptor form). New pass `ArgOwnershipPass` (`generate-arg-ownership`,
    `arg_ownership_pass.py`) walks every SCHEME-type `TablePropertiesOp`'s `ArgumentOp`s and
    copies each classification's `ownership_kind` onto the real op. Registered in `ccpp_opt.py`
    and inserted unconditionally into `ccpp_dsl.py`'s pipeline, right after the (still
    conditional) `generate-host-match` and before `generate-meta-kinds`/`generate-suite-cap` —
    unconditional because the classification is meaningful even without host metadata
    (`HostMatched` simply never triggers, same as `generate-host-match`'s own annotations in
    that case). `suite_cap.py`/`ccpp_cap.py`/`run_dispatch.py` are completely untouched — this
    stage is dual-build only, by construction, not just by discipline.
  - **Validation, the real point of this stage:** `tests/unit/test_arg_ownership_pass.py`, run
    against real examples (kessler, advection, helloworld — not synthetic fixtures, deliberately,
    since the goal is confirming agreement with production heuristics on production metadata:
    host matches, constituents, DDT plumbing) rather than small hand-built ones. For every real
    example, runs the *actual* `_is_framework_managed` and `_build_cap_var_map` (calling them for
    real, not reimplementing them) and compares their decision against
    `ArgOwnershipPass`'s real output, per scheme arg.
    - **One real discrepancy found, and it was a test bug, not a pass bug:** `advection`'s
      `dyn_const_ice`/`dyn_const` (constituent-registration args declared only in each scheme's
      `_register` table) initially showed mismatches — `_build_cap_var_map` never sees them at
      all (its loop is scoped to the physics/`_run` group callee specifically), so there was no
      real "old heuristic" ground truth for the CapScratch-vs-Block split on register/init/
      finalize-only args in the first place; the test's naive "not in cap_var_map → Block"
      fallback was simply wrong there. Fixed by restricting the strict CapScratch-vs-Block
      comparison to args declared in a `_run`-suffixed table (via `split_scheme_table_name`,
      matching `_build_cap_var_map`'s own scoping) — `SuiteOwned`/`HostMatched` aren't scoping-
      sensitive and are still checked unconditionally. Confirmed meaningful coverage remains
      after the fix (not just silencing everything): advection still strictly compares 38/52
      args across all four buckets, including 3 genuine `CapScratch` cases; kessler 44/52;
      helloworld 14/22.
    - 6 new tests (2 per example: full-agreement + no-scheme-arg-left-unclassified), all passing
      after the scoping fix.
  - Verified zero-impact by construction: full suite 398 passed (392 + 6 new) unit, FileCheck
    unchanged at 44 passed + 1 xfailed (identical to the pre-Stage-2 baseline, confirming the
    new pass — now wired into the *real* `ccpp_dsl.py` pipeline, not just constructed in
    isolation — produces zero observable difference in any generated Fortran output). `ruff
    check` clean on every new/touched file; pre-existing baseline findings in `ccpp.py`/
    `ccpp_dsl.py`/`ccpp_opt.py` confirmed unchanged via `git stash` comparison.
- **Stage 3 — Migrate one consumer at a time. ✅ done (2026-07-20).**
  - **Foundation, not named in the original plan text: `known_props` extension.** `_classify_args`
    and `_get_suite_lifecycle_ret_info` (see below) don't operate on real `ArgumentOp`s — they
    operate on `CCPPArgument` descriptors, built by `BuildMetaDataDescriptions.traverse_argument_op`
    copying a fixed `known_props` list from the real op's properties. Added `"ownership_kind"` to
    that list — one line, and every descriptor-based consumer gets the Stage 2 classification for
    free, with no other architecture change.
  - **Real consumer count: two, not three, as scoping suspected.** `suite_cap.py`'s `_classify_args`
    (line ~811): swapped `_is_framework_managed(a)` for
    `a.getAttr("ownership_kind") == ArgOwnershipKind.SuiteOwned`. `ccpp_cap.py`'s
    `_build_cap_var_map`: the membership decision (which args are HostMatched/CapScratch/Block)
    now reads a per-group `bare_name -> ownership_kind` map (built alongside the existing
    `_sno_cv`/`_dno_cv`/`_cno_cv` per-scheme scan, same loop, no new traversal) instead of
    re-deriving `_matched_cv` plus the `CCPP_FRAMEWORK_STD_NAMES`/`CCPP_ERROR_STD_NAMES`/
    `host_block_std`/`host_var_map_lc` exclusion-set check — all four folded into one
    `ownership_kind != CapScratch: continue`. The value construction (the `lc_<name>` var name,
    rank, alloc dims, constituent-tendency slicing) stayed exactly as before, per the wrinkle
    this stage's scoping flagged. `run_dispatch.py`'s `ArgSourceKind.CapVar` check needed **zero
    code changes** — confirmed it's a pure membership test against the `cap_var_map` dict
    `ccpp_cap.py` passes in, with no independent classification logic of its own for that case;
    migrating `_build_cap_var_map`'s membership decision already makes it read the same IR
    transitively.
  - **A fourth, previously-unnamed consumer, found by grepping for every `_is_framework_managed`
    call site rather than trusting the plan text's list of three:** `cap_shared.py`'s own
    `_get_suite_lifecycle_ret_info` (used for suite lifecycle return-value types) calls it too.
    Migrated identically (same `ownership_kind == SuiteOwned` swap). Stage 4 could not have
    actually deleted `_is_framework_managed` without this — it would have been deleting a
    function with a live caller left in place.
  - **A fifth thing found and *not* pulled into this stage's scope:** `run_dispatch.py` has its
    own separate, independent re-derivation of `host_var_map`/`host_block_std_names`/
    `constituent_std_names` (`_build_run_metadata_maps`) for its Host/DdtMember/Block decisions
    (a different concern than the CapVar case above) — including a **third** copy of the same
    HOST-type-table scan already found duplicated twice and consolidated into
    `_collect_host_block_std_names` during Stage 2. Real drift risk, but it also carries
    DDT-instance-path resolution (`ddt_instance_map`/`ddt_parent_map`) that `ownership_kind`
    doesn't model at all — migrating it properly is a bigger, separate job than this stage's
    scope. Left alone, flagged as a follow-on rather than folded in, matching this project's
    established discipline of not bundling unrelated cleanup into a structural-migration change.
  - **A real regression caught mid-migration, not by inspection but by the test suite doing its
    job:** after migrating `suite_cap.py`, two FileCheck tests failed — `advection`'s
    `cld_liq_array`/`cld_ice_array` (both genuinely `advected=true` real arrays, correctly
    `SuiteOwned`) started appearing in generated signatures where they shouldn't. Root cause:
    those FileCheck `.mlir` files have their own hardcoded `-p` pass list (bypassing
    `ccpp_dsl.py`'s pipeline construction entirely), and none of them included
    `generate-arg-ownership` — so `ownership_kind` was never set, and the migrated
    `_classify_args` silently treated every arg as "not SuiteOwned" (since
    `hasAttr("ownership_kind")` was always false) instead of correctly excluding them. Swept the
    entire repo for this gap rather than patching just the one failure: **33 FileCheck `.mlir`
    files** and **5 unit test files** (`test_ccpp_t_threading.py`,
    `test_gpu_directives.py`/`test_omp_directives.py`/`test_omp_hoisting.py`/
    `test_gpu_data_hoisting.py`) had a hardcoded pipeline invoking `generate-suite-cap`/`SuiteCAP`
    without `generate-arg-ownership`/`ArgOwnershipPass`. Only the `advection` FileCheck tests and
    `test_ccpp_t_threading.py` actually *failed* — the other 4 unit test files' fixtures simply
    don't happen to use any interstitial/advected/allocatable-real args, so the gap was silent
    there (same wrong answer either way, no observable difference) rather than loud. Fixed all
    38 by inserting the missing pass, confirmed via a repo-wide grep that zero files invoking
    `generate-suite-cap`/`SuiteCAP` are missing it anymore.
  - Also fixed 4 `test_ccpp_cap.py::TestBuildCapVarMap`/`TestBuildCapVarMapFlattensSubcycles`
    tests that construct `CCPPArgument` fixtures directly (bypassing IR/`ArgOwnershipPass`
    entirely) by setting `ownership_kind` explicitly on each fixture arg, matching what the real
    pass would compute for each case.
  - Verified byte-identical throughout: full suite 398 passed, 1 xfailed (unchanged from the
    pre-Stage-3 baseline) once all 38 pipeline-completeness gaps were closed. `ruff check` clean
    on every touched file; pre-existing baseline findings in `ccpp_cap.py`/`suite_cap.py`/
    `test_ccpp_t_threading.py` confirmed unchanged via `git stash` comparison.
  - **Post-merge hardening from Copilot review (PR #29):** both migrated `ownership_kind` reads
    (`suite_cap.py`'s `_classify_args`, `cap_shared.py`'s `_get_suite_lifecycle_ret_info`) treated
    a missing `ownership_kind` as "not SuiteOwned" rather than failing — the same silent-wrong-
    answer class of bug the 38-file pipeline gap above already demonstrated is real, just not yet
    guarded against in the production code itself. Rejected Copilot's suggested fix (fall back to
    the old heuristic when `ownership_kind` is absent): a permanent fallback would keep the exact
    duplicated logic this stage exists to eliminate, and would mask a misconfigured pipeline
    instead of surfacing it. Both now raise a `ValueError` naming the missing arg and pointing at
    `generate-arg-ownership`. Turning that silent case into a hard failure immediately surfaced
    two more real (previously latent) instances of the same 38-file-class gap that the original
    sweep's `SuiteCAP()`-call-syntax grep had missed: `test_optional_args.py` and
    `test_nested_ddt.py` build their pipelines as lists of pass *classes*
    (`[MetaCAP, MetaKind, SuiteCAP, ...]`) rather than `SuiteCAP().apply(...)` calls. Both fixed.
    Full suite green again afterward (397 passed, 1 xfailed, minus one pre-existing unrelated
    environmental failure — see below).
  - **Aside, not a repo issue:** one `test_build_integration.py` test shells out to the
    `ccpp_xdsl` CLI on `$PATH`, which on this machine resolves to a completely different, much
    older local clone (`/Users/dennis/Desktop/Work/xdsl-ccpp` — confirmed via `pip show
    xdsl-ccpp`'s `Editable project location`, and confirmed that clone still uses the pre-Phase-7
    `_is_framework_managed` directly). Its pass/fail is meaningless signal for work done in this
    repo; noted here so it isn't mistaken for a regression in some future stage.
- **Stage 4 — Remove the old paths. ✅ done (2026-07-20).**
  - Deleted `_is_framework_managed` from `cap_shared.py` outright — confirmed via grep it had
    zero remaining production callers (both real call sites were already migrated in Stage 3).
    `_build_cap_var_map` itself needed no further cleanup: Stage 3, as actually implemented, had
    already folded away the old `_matched_cv`/`CCPP_FRAMEWORK_STD_NAMES`/`CCPP_ERROR_STD_NAMES`/
    `host_block_std` exclusion checks and their imports rather than leaving them dead in place, so
    there was no separate "remove the now-unused locals" step left to do there.
  - Deleted `TestIsFrameworkManaged` (7 tests) from `test_cap_shared.py`, trimming the module
    docstring's now-obsolete opening paragraph.
  - Rewrote `test_arg_ownership_pass.py`: its whole premise was Stage 2's cross-check ("does
    `ArgOwnershipPass` agree with the old heuristics on real examples?"), which has nothing left
    to compare against once the heuristics are gone. Deleted `test_ownership_matches_old_heuristics`
    (3 parametrized cases) and the `expected`-side of its helper (which called
    `_is_framework_managed` and cross-referenced `_build_cap_var_map`'s `cap_var_map`, requiring
    `SuiteCAP`/`BuildSchemeDescription`/`_collect_public_suite_functions` just to build a
    comparison value nothing uses anymore). Kept `test_every_scheme_arg_gets_classified`
    (still a real, independent check — no scheme arg left unclassified), simplified to build only
    the `actual` bucket.
  - Updated docstrings/comments that described `_is_framework_managed` as a still-live, parallel
    mechanism to compare against (`ArgOwnershipKind` in `ccpp.py`; `ArgOwnershipPass`'s own
    docstring, which had drifted since Stage 3 — it still said Stage 2's "no observable effect on
    generated output," which stopped being true the moment Stage 3 shipped; `classify_arg_ownership`'s
    "Mirrors suite_cap.py's `_is_framework_managed`" docstring line in `cap_shared.py`).
  - Net: 10 tests removed (7 + 3), 1 function deleted, several stale docstrings brought current.
    Not a large line-count reduction — Stage 3, as actually executed, had already done most of the
    real deletion work rather than leaving scaffolding behind for this stage, so what remained
    here was mostly the dead function itself plus its test/doc fallout.
  - Verified: full suite 387 passed, 1 xfailed (397 minus the 10 intentionally-removed tests,
    ignoring the one unrelated environmental CLI test above). `ruff check` clean; the 11
    pre-existing baseline findings confirmed byte-identical via `git stash` comparison.
  - **Deliberately left out of this stage** (per explicit user decision, not an oversight):
    `run_dispatch.py`'s own third independent copy of the HOST-table standard_name scan
    (`_build_run_metadata_maps`'s `host_block_std_names`, duplicating
    `cap_shared._collect_host_block_std_names`) — a different duplication (Host/DdtMember/Block
    decisions, not ownership) than what this stage's migration targeted.

**Follow-on: `run_dispatch.py` host-block-std-names dedup. ✅ done (2026-07-20).** The item
deferred above. Swapped `_build_run_metadata_maps`'s inline 9-line HOST-table standard_name scan
for a direct call to `cap_shared._collect_host_block_std_names(meta_data)` — confirmed
byte-for-byte identical logic beforehand (same `CCPPType.HOST` filter, same
`arg_tables`/`getFunctionArguments`/`standard_name.lower()` scan), so this is a pure dedup with
no behavior change. `CCPPType` import kept (still used elsewhere in the file for the
DDT/MODULE/SCHEME checks). Verified: full suite 387 passed, 1 xfailed (unchanged from the
post-Stage-4 baseline); `ruff check` clean, the same 16 pre-existing baseline findings confirmed
byte-identical via `git stash` comparison.

**Scope note:** bigger and riskier than any single Phase 3b stage — Phase 3b's producer and
every consumer lived inside one file's function-call chain; this needs a new early computation
point, likely spanning a pass boundary, and touches every generated suite subroutine's shape
rather than just run-dispatch call sites. Treat it with the same discipline as every phase
above: one branch per stage, byte-identical verification, full test suite green throughout.

**Also revisit when this is done:** the Phase 6 pass-status decision for
`run_dispatch.py`/`lifecycle_cap.py`/`constituent_cap.py` — this is the prerequisite that
decision was waiting on.

---

## Backlog — capgen-v1 end-to-end-tests capability gaps (added 2026-07-20)

Classified 2026-07-20 by cloning `NCAR/ccpp-framework` at `feature/capgen-v1` and comparing its
`end-to-end-tests/` directory against xdsl-ccpp's current source (duplicates: `advection`,
`capgen`, `ddthost`; low-priority partial: `advection_auto_clone`, which capgen-v1's own code
labels a transient legacy shim for one host). What follows is an implementation plan with effort
estimates for every genuine gap found, so picking one up later doesn't require re-deriving scope
from scratch. Effort tiers are relative to this session's own completed work as a yardstick: **S**
≈ a focused session, comparable to one Copilot-review-fix round; **M** ≈ comparable to one Phase 7
stage (Stage 3/4-sized); **L** ≈ bigger than any single Phase 7 stage, a multi-session effort in
its own right. None of this is scheduled — pick items independently, in any order, except where a
dependency is noted.

- **`var_compat`'s other pieces, separate from nested-subcycle:**
  - **Vertical array flipping (`top_at_one=true`) — fixed.** Reverses vertical-index array
    sections when a scheme's own declared top-at-one convention differs from other schemes
    sharing the same standard_name. `effr_calc`'s `effrr_in`/`effrs_inout` and `effr_diag`'s
    `effrr_in` declare it; `effr_pre`/`effr_post`/`effrs_calc` don't, and no host file in this
    port declares an explicit counterpart to compare against, so schemes that don't declare it
    define the shared, not-flipped representation. Confirmed the existing
    `RowMajorConvertOp`/`RowMajorWriteBackOp` pair (row-major/column-major conversion) is inserted
    at a *different* generated subroutine (the host-facing run-dispatch chain in
    `run_dispatch.py`) than the one that actually matters here (`suite_cap.py`'s suite-cap
    subroutine, which is where `effr_calc`/`effr_diag` are actually called), so it wasn't reused
    directly.
    - **Fixed**: added `top_at_one` to the recognized metadata keys (`ccpp.py`'s
      `ArgumentOp.KNOWN_PROPS`/boolean-flag list, `ccpp_descriptors.py`'s
      `BuildSchemeDescription`) — previously silently dropped with an unrecognised-key warning.
      Added a new `VerticalFlipOp`/`VerticalFlipWriteBackOp` pair in
      `xdsl_ccpp/dialects/ccpp_utils.py`, modeled directly on `KindCastOp`/`KindWriteBackOp` but
      reversing an array section along the vertical dimension (identified per-scheme from the
      argument's own `dim_names`, via a new `is_vertical_dimension`-based
      `_vertical_dim_index` helper) rather than converting a value, using `size(...)`-based
      section bounds so no named dimension variable needs to be in scope. Generalized the
      divergent-standard-name detection built for the kind/unit fix above (add `top_at_one`
      presence to the per-scheme signature tuple `_build_arg_tables` compares) and extended
      `generateSchemeSubroutineCallOps`'s per-call marshaling chain to include the flip as a
      third step alongside kind cast and unit convert — `effrs_inout`'s real case chains all
      three on the same call (kind, then units, then flip forward; write-back unwinds flip, then
      units, then kind, in reverse), confirmed correct against the real regenerated output. A
      vertical flip is type/kind-invariant, so it composes with the other two steps in either
      order without changing the result. `effr_calc`'s/`effr_diag`'s own arithmetic on these
      variables is uniform across vertical levels, so this specific synthetic example's own
      numeric check can't independently distinguish a correct flip from a no-op one —
      verification here is about correct, valid generated Fortran syntax and correct call-site
      placement, not an independent numeric proof from this particular test. Regression coverage:
      `tests/unit/test_top_at_one_recognized.py`, `tests/unit/test_vertical_flip_op.py`,
      `tests/unit/test_suite_vertical_flip_marshaling.py`.
  - **Kind conversion (`kind_phys`↔`8`) — confirmed working, and a real, unrelated bug found and
    fixed along the way.** `effr_calc`'s `effrs_inout` declares `kind = 8`; every other occurrence
    of the same standard_name uses `kind_phys`. The `generate-meta-kinds`/`KindCastOp`/
    `KindWriteBackOp` machinery (`ccpp_dsl.py::_build_pipeline`, `TypeConversions`) already
    handles this class of problem correctly for the ordinary case. While exercising it against
    this example's real output, found and fixed a real, pre-existing bug in `suite_cap.py`'s
    `_build_block_signature`: its `data_ops`/`final_values` bookkeeping stored the raw
    `KindCastOp`/`UnitConvertOp` operation objects instead of their result values, unlike every
    other entry in that dict — harmless everywhere else because operand-consuming constructors
    auto-unwrap a single-result operation, but it crashed the moment a scalar `intent(inout)` arg
    with a real unit mismatch hit `_assemble_func`'s `return_types = [v.type for v in
    inout_return_vals]`, which accesses `.type` directly. Fixed by storing `.res` consistently.
  - **Unit conversion for `m`↔`um`, `km`↔`m`, and `j kg-1`↔`m2 s-2` — fixed; these were simply
    missing `UNIT_CONVERSIONS` table entries, not a mechanism gap.** `effr_pre`'s `effrr_inout`
    (units `m`) vs `effr_calc`'s `effrr_in` (units `um`), same standard_name, and several others in
    this suite. The unit-conversion mechanism itself (`UNIT_CONVERSIONS` in
    `ccpp_conventions.py`, and its detection/insertion pipeline in `host_var_match_pass.py`/
    `suite_cap.py`) was already correct and proven for other pairs (K↔°C, Pa↔hPa, m↔cm, ...) —
    the specific pairs this example needs just weren't in the table. Added `um`↔`m` and `km`↔`m` as
    real conversions; `j kg-1`↔`m2 s-2` and `m+2 s-2`↔`m2 s-2` turned out to be the same physical
    unit written two ways (the latter fixed via a `normalize_units` tweak stripping an explicit
    `+` sign on a positive exponent, rather than a real conversion factor).
  - **Suite signature construction assumed every scheme sharing a standard_name declares the same
    kind/units as each other — a real, previously-unknown bug, found and fixed while regenerating
    this example's output after the unit-table fix above.** Two standard_names here are declared
    with genuinely different units or kind by *different schemes*, not just different from the
    host: `effr_pre`/`effr_post` declare the rain-particle radius in meters (matching the host)
    while `effr_calc`/`effr_diag` declare the *same* standard_name in micrometers; `effrs_calc`
    declares the snow-particle radius in meters/`kind_phys` (matching the host) while `effr_calc`
    declares the *same* standard_name in micrometers/`kind = 8`. `suite_cap.py`'s
    `_build_arg_tables` only ever keeps ONE scheme's declaration per standard_name (`all_args`,
    first-write-wins), and `_build_block_signature` converted the whole suite-level dummy argument
    ONCE, against the host, based on that single canonical entry — so every OTHER scheme sharing
    the name silently received whichever representation the canonical scheme happened to need,
    regardless of its own actual declaration. Confirmed via the real generated output:
    `effr_calc_run`/`effr_diag_run` were receiving the rain-particle radius still in raw,
    unconverted meters (their own metadata says micrometers — off by a factor of a million, no
    warning at all), and `effrs_calc_run` was receiving the snow-particle radius already converted
    to micrometers/`kind = 8` for `effr_calc`'s benefit, when its own declaration matches the host
    exactly and needs no conversion. The underlying per-scheme detection was never actually
    missing — `HostVariableMatchPass` already loops over every scheme's own copy of every argument
    independently (not deduplicated by standard_name at all) and annotates
    `model_var_kind_mismatch`/`model_var_unit_mismatch` directly on each scheme's own
    `ArgumentOp`; the gap was entirely in how `suite_cap.py`'s call-building code consumed it.
    **Fixed**: `_build_arg_tables` now also computes a `divergent_std_keys` set (standard_names
    where two or more schemes' own declarations disagree with each other on kind or units).
    `_build_block_signature` skips its suite-boundary conversion entirely for these — the shared
    value stays in the host's own native representation for the whole function body — and
    `generateSchemeSubroutineCallOps` independently marshals *each individual call* to that call's
    own scheme's already-known mismatch, converting immediately before the call and writing back
    immediately after (reusing the exact same `KindCastOp`/`UnitConvertOp`/`KindWriteBackOp`/
    `UnitWriteBackOp` already used for the non-divergent case — no new IR). A kind mismatch and a
    unit mismatch on the same argument chain together, and the write-back correctly unwinds in
    reverse (unit first, then kind). Fixing this also surfaced and required a matching fix in
    `print_ftn.py`: its kind-cast/unit-convert declaration scan only walked top-level block ops
    (these conversions had only ever been emitted at the top level before), so a per-call
    conversion nested inside a subcycle loop body went undeclared — fixed by switching to a
    recursive walk, matching the already-established pattern used for `RowMajorConvertOp`
    declarations right below it. Two per-call conversion instances sharing the same scheme-derived
    name (e.g. `effr_calc`'s and `effr_diag`'s own `effrr_in_unit_conv`) also needed the same
    `_get_variable_name_for` de-duplication already used for local allocas, for the identical
    reason as the historic `ccpp_loop_cnt` duplicate-declaration bug. Every non-divergent
    standard_name (the vast majority) is completely unaffected. Regression coverage:
    `tests/unit/test_suite_cross_scheme_unit_kind.py`.
  - **Fixed — host-facing wrapper subroutine used to declare `scalar_var`/`tke_inout`/
    `tke2_inout` `intent(in)` while the suite-cap subroutine it calls correctly declares them
    `intent(inout)`.** Root cause, traced in `run_dispatch.py` (a separate code path from
    `suite_cap.py`, owning the combined `ccpp_cap.py` wrapper's own generation): the suite
    callee's leading (inout-position) return values get a copy-back in
    `_build_run_dispatch_chain`, but that loop only ever special-cased three framework things —
    `ccpp_error_message`, `ccpp_error_code`, and a `ccpp_t` handle. An ordinary scheme-declared
    `intent=inout` scalar with no dedicated framework meaning of its own (`scalar_var`/
    `tke_inout`/`tke2_inout` — no host variable match, not one of the three specials) fell
    through with no copy-back at all, so the value never reached the wrapper's own block
    argument, and `print_ftn.py` (which declares a scalar dummy argument `intent(inout)` only
    when it appears in the function's own `ReturnOp`) always saw it as `intent(in)`. **Fixed**
    by a new `_get_suite_leading_inout_ret_info` helper (`cap_shared.py`) that name-resolves this
    leading-region case the same way the pre-existing `_get_suite_lifecycle_ret_info` helper
    already resolves the trailing alloc-region case, plus recording each echoed block arg so
    `_assemble_run_fn`'s own `ReturnOp` includes it too.

    This surfaced a second, closely related bug in `print_ftn.py`'s `_print_kw_call`: once the
    copy-back target is the same variable already passed in as an input (the common case here,
    since these scalars have no host match and flow straight through as caller-supplied block
    arguments), the keyword-call printer must suppress the synthetic `_out_N=` echo it would
    otherwise print — printing the same variable under two different keyword names bound to what
    is really the same dummy argument is also invalid Fortran. The positional-call printer
    (`_print_call`) already had this suppression (matching on the resolved destination name
    against the printed input names); `_print_kw_call` needed a matching value-based fix.

    Also fixed retroactively, as a side effect of the same `run_dispatch.py` change: `examples/
    capgen` and `examples/ddthost` each had a latent call-arity bug in their own combined
    `_ccpp_physics_run`/lifecycle wrapper — a leading inout return with no copy-back (there, a
    cap-owned/host-matched DDT scalar, e.g. `vmr`) fell through to a *different*, pre-existing
    fallback (the "untracked call result" mechanism in `print_ftn.py`'s function printer), which
    synthesized an anonymous local (`ccpp_tmp_0`) and printed it as an *extra* positional call
    argument the callee's own declared signature didn't actually have one for — an arity mismatch,
    also invalid Fortran. Confirmed by direct inspection: `ddt_suite_data_prep` declares
    exactly 8 dummy arguments, but the call previously passed 9. Covered by
    `tests/unit/test_run_dispatch_inout_echo.py` (3 tests, sabotage-verified for both the
    copy-back fix and the keyword-dedup fix independently). All affected FileCheck goldens
    (`var_compat-xml`, `capgen-xml`, `ddthost-py`, `ddthost-xml`, both `completed_ir` and
    `end_to_end` tiers) regenerated and passing.
  - **Two more real gaps found trying to actually build `examples/var_compat` with gfortran for
    the first time.**
    - **Fixed — `module_rad_ddt.meta` was missing from this port's generation inputs (a port
      mistake, not an `xdsl_ccpp` code gap).** Initial investigation (via a research fork)
      hypothesized this was a real code gap in `suite_cap.py`'s `use`-statement construction not
      consulting `ddt_source_module` the way `ccpp_cap.py` does — that hypothesis was wrong.
      The actual root cause, confirmed by directly regenerating with the file added: the real
      capgen-v1 source keeps `rad_lw`/`rad_sw`'s DDT type definitions (`ty_rad_lw`/`ty_rad_sw`) in
      their own separate file rather than bundled into a scheme's own `.meta` (unlike e.g.
      `examples/ddthost`'s `make_ddt.meta`, which declares its DDT type and the scheme that uses
      it in the same file) — but this port's `--scheme-files` list (the Makefile's
      `CAPS_SCHEMES` and all three `tests/filecheck` var_compat-xml.mlir RUN lines) never included
      `module_rad_ddt.meta`, so its DDT table definitions were never parsed at all. This one
      omission silently caused two separate, real symptoms once actually compiled: (1) the
      suite-cap module declared `fluxLW` as `type(ty_rad_lw)` (a whole-DDT host match) without
      ever importing the module that defines it, since `collect_ddt_source_modules` had no DDT
      table to map `ty_rad_lw` to a source module at all; (2) `rad_sw_run`'s `sfc_up_sw`/
      `sfc_down_sw` arguments (individual DDT-*member* standard_names, members of the host's
      `ty_rad_sw` DDT, not a whole-DDT match like `fluxLW`) were silently dropped from the suite
      signature entirely, since the DDT-member-matching machinery had no DDT definition to match
      against at all. **Fixed** by adding `module_rad_ddt.meta` to the four input-file lists;
      confirmed both symptoms disappear with zero `xdsl_ccpp` code changes.
    - **Fixed — a dynamic-count subcycle's loop bound used to be emitted as the raw standard_name
      string, never resolved to the host's own local name.** `suite_cap.py`'s `_emit_subcycle`
      passed the XML's `loop="..."` string straight through unresolved when it wasn't a literal
      integer — for `<subcycle loop="num_subcycles_for_effr">`, that string is the
      *standard_name* (`num_subcycles_for_effr`), not a real Fortran identifier; the host's own
      local name for it is `num_subcycles` (`test_host_data.meta`). Unlike `scheme_order_in_suite`
      (which flows through the ordinary scheme-arg host-matching path because several schemes
      declare it as their own arg), no scheme anywhere declares a matching arg for
      `num_subcycles_for_effr`, so it never entered `all_args`/`data_ops` through any existing
      pathway. **Fixed** by a new `_synthesize_dynamic_loop_count_args` method in `suite_cap.py`
      that scans the suite's subcycle structure for dynamic loop counts with no scheme-arg match,
      resolves the host's own local name for the standard_name by scanning every non-scheme host
      table (module, host, or ddt), and synthesizes a fresh `HostMatched` `CCPPArgument` for it —
      so it becomes a genuine, correctly-declared dummy argument the same way any other
      host-matched value does, and `_emit_subcycle` prints that argument's own name as the do-loop
      bound instead of the raw standard_name. Scoped to only the `_run` (physics) postfix that
      actually emits a `SubcycleLoopOp` using it — a scheme can have both a `_run` and an `_init`
      entry point, so an `arg_tables`-only check isn't sufficient on its own; the synthesis is
      additionally gated on `physics_mode`. Covered by `tests/unit/test_suite_dynamic_loop_count.py`
      (4 tests, sabotage-verified). If a dynamic loop count has no matching host variable anywhere,
      a clear `ValueError` is raised instead of emitting invalid Fortran.
    - **Fixed — a third gap found compiling with ifx after the two fixes above: "Error in
      opening the compiled module file" for `ccpp_constituent_prop_mod` and `ccpp_scheme_utils`,
      not an `xdsl_ccpp` code gap.** Every generated ccpp-cap module unconditionally emits a
      `<Host>_model_const_properties()` entry point (part of the mandatory CCPP host-facing API
      surface, not scheme-specific — this example declares no constituents at all), and its `use
      ccpp_constituent_prop_mod`/`use ccpp_scheme_utils` need real module files to compile
      against. Those two modules belong to the real CCPP framework library; every other example
      that's actually been build-tested (`examples/advection`, `examples/advection_flat_host`,
      `examples/constadv`, `examples/constprop`) carries its own small, fully generic stub
      implementation of both (byte-identical across all four) and wires it into its own
      Makefile — `examples/var_compat`'s Makefile simply never got the same two files, and
      neither did `examples/capgen` or `examples/ddthost` (both FileCheck-tested only, never
      actually compiled with a real Fortran compiler until now). **Fixed** for `var_compat` by
      copying the stub files in as `ccpp_constituent_prop_mod.F90`/`ccpp_scheme_utils.F90` and
      adding them to the Makefile's `SRCS` right after `GEN_KINDS`. `examples/capgen` and
      `examples/ddthost` would hit the identical error if actually compiled; not fixed here
      (out of scope — the user asked specifically about `var_compat`).
    - **Fixed — a fourth gap found while investigating why `test_host.F90` (a hand-written
      driver — deliberately not modified; verified by diffing against upstream capgen-v1's own
      `end-to-end-tests/var_compat/test_host.F90`, which confirmed this port's version was
      already a deliberate, intentional adaptation to `xdsl_ccpp`'s own generated-API
      conventions, not something to bring back in line with upstream byte-for-byte) only passes
      `suite_name`/`suite_part`/`col_start`/`col_end`/`errmsg`/`errflg` to
      `test_host_ccpp_physics_run`, while the generated signature required ~20 more arguments.**
      Root cause: `test_host_mod.meta`'s `[ccpp-table-properties]`/`[ccpp-arg-table]` blocks
      both declared `type = host` instead of `type = module` — a metadata typo, not a driver
      bug. `test_host_mod.F90` is a real, persistent Fortran module (module-level `phys_state`
      DDT instance, `effrs` array, `has_graupel`/`has_ice` parameters, initialized once via
      `init_data()`), not a caller-provided-each-call interface; `examples/capgen` and
      `examples/ddthost`'s own equivalent `test_host_mod.meta` files both correctly declare
      `type = module`, confirming this was an isolated port mistake. Because of the typo,
      `run_dispatch.py` treated `phys_state`'s own module-level instance as HOST-interface-only
      (never eligible for DDT-member `use`-based resolution — see its own "HOST-type tables are
      caller-provided interfaces, not Fortran modules" comment), so every DDT member (effrr,
      effrl, scalar_var, tke, tke2, fluxLW, sfc_up_sw/down_sw, etc.) got flattened into its own
      top-level caller-supplied dummy argument instead of being resolved internally via
      `use test_host_mod, only: phys_state`. **Fixed** by correcting both `type = host` lines to
      `type = module`; confirmed this collapses `test_host_ccpp_physics_run`'s signature from
      ~24 arguments down to `suite_name, suite_part, scalar_varA, scalar_varB, scalar_varC,
      num_subcycles, errmsg, errflg` — matching what the (unmodified) driver already expects,
      apart from the remaining four. All three var_compat FileCheck goldens (`frontend`,
      `completed_ir`, `end_to_end`) regenerated and passing.
    - **Fixed — two separate, real `run_dispatch.py` bugs, found while diagnosing why
      `scalar_varA`/`scalar_varB`/`scalar_varC`/`num_subcycles` still didn't resolve after the
      metadata fix above.**
      1. *Bare-name collision bug.* Confirmed directly in the IR: `HostVariableMatchPass`
         correctly resolves all three of `effr_pre`/`effr_post`/`effr_diag`'s own
         `scalar_var`-named args to their distinct `physics_state` DDT members (`model_var_name
         = scalar_varA`/`scalar_varB`/`scalar_varC` respectively) — the deliberate bare-name
         collision this example exists to test is resolved correctly at the host-matching layer.
         But `run_dispatch.py`'s own `_build_per_suite_run_info` built `local_to_host_info`
         keyed by each scheme's own literal `fn_arg.name` — "scalar_var" for all three, since the
         IR's `name` attribute is never rewritten to the disambiguated `model_var_name` — while
         the *lookup* uses the suite's already-disambiguated combined name
         (`_bare("scalar_varB")` = `"scalar_varB"`, a string that was never inserted as a key at
         all). Only the first-processed scheme's entry (which happened to keep the un-suffixed
         combined name `scalar_var`) resolved correctly; the other two silently fell back to
         `ArgSourceKind.Block`.

         **Fixed** by grouping host-matched `fn_args` by bare local name, deduplicated by
         standard_name (mirroring `suite_cap.py`'s own `all_args` construction, which dedupes by
         `std_key` — without this dedup step, several schemes correctly sharing one bare name for
         the *same* standard_name, e.g. every scheme's own `ncol`, get miscounted as a collision
         too, an over-eager first attempt at this fix that broke `ncol`/`effrr_inout`/
         `effrs_inout` resolution before landing on this version). A bare name backed by only one
         distinct standard_name keeps the simple bare-name key, unchanged from before; a bare name
         genuinely shared by 2+ distinct standard_names is instead keyed by each sibling's own
         `model_var_name` — precisely what `suite_cap.py` renamed that sibling's own dummy
         argument to. A second, blunter attempt (unconditionally also keying by `model_var_name`,
         without the collision/dedup grouping) was tried and rejected: it clobbered an unrelated
         arg's correct entry whenever one arg's `model_var_name` happened to coincide with a
         *different* arg's own bare local name — caught directly by the pre-existing
         `test_run_dispatch.py::TestBuildPerSuiteRunInfoResolvedArgOps` fixture (its `temp`/
         `rad_temp` args have exactly this coincidental collision).
      2. *`num_subcycles` DDT-table gap.* `num_subcycles` is a suite-level argument synthesized
         entirely by `suite_cap.py`'s `_synthesize_dynamic_loop_count_args` (see the subcycle
         loop-bound fix above) — it isn't declared in any scheme's own `.meta` at all. The
         fallback in `_build_per_suite_run_info` that resolves a callee arg's std_name when no
         scheme table has it only scanned `CCPPType.HOST`/`CCPPType.MODULE` tables, never
         `CCPPType.DDT` — so even with `physics_state` correctly module-hosted, this fallback
         never discovered that `num_subcycles` is really one of its members.

         **Fixed** by extending that scan to `DDT` tables too, and folding any such match into
         `local_to_host_info` as a `(member_name, ddt_type_name, is_ddt=True)` entry — the same
         shape the scheme-arg path already produces — so it resolves through the existing
         `_resolve_ddt_access_path` machinery instead of falling back to a caller-block argument.

      With both fixed, `test_host_ccpp_physics_run`'s signature collapses to just
      `suite_name, suite_part, errmsg, errflg`, confirmed by regenerating this example's real
      output. Both var_compat FileCheck goldens (`completed_ir`, `end_to_end`) regenerated
      and passing; direct regression coverage (sabotage-verified against both fixes
      independently, including the two rejected fix attempts above) in
      `tests/unit/test_run_dispatch_host_wrapper_resolution.py`.
    - **Fixed — `col_start`/`col_end` missing from `test_host_ccpp_physics_run`, found
      immediately after the two fixes above.** `test_host.F90`'s hand-written driver call
      (which must not be modified — see the "never change handwritten files" feedback memory)
      additionally passes `col_start`/`col_end` (6 arguments total), 2 more than the signature
      above. Diffing against real upstream capgen-v1 confirmed this example's schemes genuinely
      don't chunk by column: every one of them is dimensioned by the full `horizontal_dimension`,
      matching upstream's own design, not a porting omission — upstream's own `ccpp_physics_run`
      bundles `col_start`/`col_end`/`thread_num`/`nthreads`/`nphys_threads` into a fixed,
      always-present framework argument list regardless of scheme content, a convention
      xdsl-ccpp doesn't otherwise have. `col_start`/`col_end` only ever enter a suite callee's
      own signature via `suite_cap.py`'s `_classify_args`, which replaces a scheme-declared
      `horizontal_loop_extent` arg with synthetic `col_start`/`col_end` scalars — gated entirely
      on some scheme declaring `horizontal_loop_extent`. Since no scheme here does,
      `run_dispatch.py`'s per-suite-arg classification had nothing to discover, and the wrapper's
      own signature never picked them up either.

      Two candidate fixes were considered and rejected before this one: (a) making the generator
      unconditionally expose `col_start`/`col_end` whenever the host declares them, regardless of
      scheme content — rejected because every host `.meta` in this repo already declares them
      (universal boilerplate), but `examples/tinyddt`/`examples/nestedddt` (chost, C++ host) have
      no scheme declaring `horizontal_loop_extent` either and their already-working C++ drivers
      correctly don't pass `col_start`/`col_end` at all (the chost convention removes them
      entirely) — this would have silently added required arguments those drivers don't supply;
      (b) modifying `test_host.F90` itself to drop `col_start`/`col_end`, matching the precedent
      already set for `thread_num`/`nthreads`/`nphys_threads` at port time — rejected per explicit,
      unconditional user instruction: hand-written files are never modified, regardless of how
      well-evidenced the case for an edit looks.

      **Fixed generically for every Fortran example instead:** `run_dispatch.py`'s
      `_build_run_block_signature` now accepts `col_start`/`col_end` unconditionally whenever the
      host itself declares `horizontal_loop_begin`/`horizontal_loop_end` (every example's host
      metadata already does) and no suite here already supplied a `col_start`/`col_end`-equivalent
      under some other local name (checked via `seen_non_host_std_names`, keyed by standard_name
      so a differently-named host variable, e.g. `cols`/`cole`, still counts as already-supplied)
      — mirroring how `errmsg`/`errflg` are already always present regardless of scheme content.
      Confirmed safe: full suite is 480 passed, 1 pre-existing xfail, and every example other
      than `var_compat` is byte-identical, since
      they already receive `col_start`/`col_end` via the pre-existing `horizontal_loop_extent`-
      driven path and the new fallback correctly detects that and adds nothing extra.
      `test_host_ccpp_physics_run`'s signature is now exactly
      `suite_name, suite_part, col_start, col_end, errmsg, errflg` — matching `test_host.F90`'s
      existing call precisely, in both arity and argument order, with zero changes to any
      hand-written file.

      **One caveat this fix does not (and cannot, from the generator side) resolve:**
      `col_start`/`col_end` are accepted but genuinely unused inside `physics_run`'s body, since
      none of this example's schemes are chunk-aware. `test_host.F90` calls this suite part
      inside a 5-column chunking loop (modeled on `examples/advection`'s own driver convention),
      so — if actually compiled and run — the suite executes redundantly once per chunk over the
      *entire* array each time, and `effr_calc.F90` has a real accumulation
      (`effrs_inout = effrs_inout + (10.0 / 6.0)`), so the redundant calls would over-increment
      it. That's an inherent mismatch between the driver's chunking assumption and this suite's
      genuinely unchunked (upstream-matching) design — not something a generator-side fix can or
      should paper over. Both var_compat FileCheck goldens regenerated and passing; direct
      regression coverage (sabotage-verified, including a guard against double-inserting
      `col_start`/`col_end` for the already-working chunked examples) in
      `tests/unit/test_run_dispatch_col_bounds_fallback.py`.
    - **Fixed — a real `ifx` compile failure, found by the project owner actually trying to
      build `var_compat` with `ifx` after the fixes above.** gfortran silently accepted the
      offending Fortran and every FileCheck golden matched it byte-for-byte, so this survived
      completely undetected until a real, standards-strict compiler was tried:
      ```
      error #5192: Lead underscore not allowed
                num_subcycles=phys_state%num_subcycles, _out_0=ccpp_tmp_0, ...
      error #6784: The number of actual arguments cannot be greater than the number of dummy
                   arguments.
      error #6627: This is an actual argument keyword name, and not a dummy argument name.
                   [_OUT_0]
      ```
      Root cause, one layer deeper than either symptom: `run_dispatch.py`'s
      `_build_run_dispatch_chain` had no copy-back branch at all for a suite callee's own
      leading `intent(inout)` **scalar** return value when it's host-matched to a DDT member
      (`scalar_var`/`tke_inout`/`tke2_inout`, resolved to `phys_state%scalar_var` etc.) rather
      than a plain caller-block argument or plain host/cap-owned module variable — every
      existing branch (`block_arg_map`/`host_var_map`/`cap_var_map`) missed it. With no
      `CopyOp` consumer at all, `print_ftn.py`'s own "untracked call result" fallback took
      over: it invents a throwaway `ccpp_tmp_N` local for the value and, in the **plain
      positional-call path**, prints it as a genuine extra positional argument — a real arity
      mismatch that also silently shifts every later argument (including `errmsg`/`errflg`)
      into the wrong dummy-argument slot. In the **keyword-call path** (used whenever any of
      the suite's own inputs is optional, so Fortran correctly forwards `OPTIONAL` absence
      status — `var_compat`'s radiation group has several optional array args), the same
      untracked value additionally got a synthetic `_out_{i}` placeholder keyword name from a
      separate, earlier list comprehension that only recognized `errmsg`/`errflg` by type —
      invalid Fortran on two counts: the leading underscore (not a legal Fortran identifier
      start) and the resulting arity mismatch.

      **Fixed** with two complementary changes: (1) a new copy-back branch in the same `idx <
      len(_leading_inout_ret)` region reuses the exact same `HostVarRefOp` already built as
      the argument's own *input* reference (`host_var_ref_results`, populated once per callee
      arg before the call is built) as the copy-back target too — functionally a no-op
      (Fortran already reflects the update through the same aliased reference, so nothing
      needs copying), but it gives the result a real `CopyOp` consumer, so it never reaches
      the untracked-call-result fallback in the first place; this alone fixes the
      positional-call arity bug and eliminates the dead `ccpp_tmp_N` declaration entirely, not
      just its use. (2) The keyword-call path's `_result_names` construction was moved to
      after, and now reuses, the same leading-inout/trailing-alloc classification the
      copy-back loop already uses (`_get_suite_leading_inout_ret_info`/
      `_get_suite_lifecycle_ret_info`), computing each output position's real callee
      dummy-argument name instead of a synthetic `_out_{i}` placeholder — belt-and-suspenders
      alongside (1), and the only thing needed for positions (1) doesn't cover (a genuine
      trailing alloc-region scalar with no operand-side entry at all, which legitimately does
      need its own real keyword name printed).

      Confirmed via the real `Makefile` path (not just the raw CLI):
      `test_host_ccpp_physics_run`'s call to `var_compatibility_suite_radiation` now has
      exactly the right argument count, with no `_out_N`/`ccpp_tmp_N` anywhere. Both var_compat
      FileCheck goldens regenerated and passing; full suite 487 passed, 1 pre-existing xfail.
      Direct regression coverage (sabotage-verified against both the positional- and
      keyword-call symptoms independently) in `tests/unit/test_run_dispatch_kw_call_result_names.py`.
    - **Milestone: `examples/var_compat` builds and runs with `ifx` for the first time**,
      confirmed by the project owner — the fix above closed the last known compile blocker.
      The actual run then hit a real *runtime* mismatch: `test_host.F90`'s own `check_suite()`
      compares `ccpp_physics_suite_variables`'s reported input/output/required variable counts
      against hardcoded expected values (18/14/22) and got 16/15/21.

      **Fixed — three independent gaps in `ccpp_cap.py`'s `_build_suite_variables_fn`, none
      previously exercised by any other example (all three walk raw scheme/host `ArgumentOp`s
      directly, a separate code path from every fix above):**
      1. *Spurious extra output.* `effr_calc`'s `ncl_out` (`cloud_liquid_number_concentration`)
         is `optional`, `intent = out`, and no host `.meta` anywhere declares a match for it —
         it resolves to a throwaway cap-owned scratch variable (`lc_ncl_out`, `ArgOwnershipKind.
         CapScratch`) that never reaches the host in either direction, but was being listed as a
         real output regardless (declared intent alone drove the old logic, with no check
         against `ownership_kind` at all).

         **Fixed** by excluding an *optional*, unmatched, `CapScratch`-classified arg whose
         standard_name isn't a recognized framework array (`FRAMEWORK_STD_NAME_TO_CAP_VAR` —
         `ccpp_constituents` and friends still correctly appear, matching this function's own
         pre-existing `_INTERNAL` comment that they must). Two additional guards were needed,
         found via real regressions in the full repo test suite, not anticipated up front:
         - `host_std_names` must be non-empty and missing this std_name: `CapScratch` alone
           isn't enough to conclude "no host ever declares this" — a FileCheck-only invocation
           with no `--host-files` at all (`tests/filecheck/examples/end_to_end/
           helloworld-xml.mlir`, which deliberately omits it to exercise the scheme-only
           frontend path) makes *every* scheme var `CapScratch` regardless of whether a real
           host would match it — confirmed via helloworld's own `hello_world_mod.meta`, which
           genuinely does declare `potential_temperature`; only that specific host-less
           invocation makes it look unmatched.
         - The arg must be `optional`: `examples/advection`'s own end-to-end FileCheck golden
           runs a deliberately reduced pass list with no `generate-host-match` at all (confirmed
           via its own `// RUN:` line — matching `DEVELOPERS.md`'s own caveat that these
           manually-composed pass lists aren't a stand-in for the real driver pipeline), so
           `ownership_kind` alone is unreliable there: `tcld` (`minimum_temperature_for_cloud_
           liquid`, a genuine intra-suite interstitial the real pipeline's `generate-host-match`
           would mark `is_interstitial` and exclude via `interstitial_std_names` instead) and
           `cld_liq_tend` (`tendency_of_cloud_liquid_dry_mixing_ratio`, `constituent = True`,
           `_build_cap_var_map`'s own docstring names this as an intentional `CapScratch`
           example that must still appear here) both come out `CapScratch`-and-unmatched in that
           reduced pipeline, but neither is declared optional — unlike `ncl_out`, which is. A
           mandatory unmatched arg means the suite genuinely needs it; only an optional one can
           be silently absent, which is what makes exclusion safe for that case and not this one.
      2. *Two missing inputs, part one.* `num_subcycles_for_effr` is a suite-level dynamic
         subcycle loop count synthesized directly by `suite_cap.py`'s
         `_synthesize_dynamic_loop_count_args` — it never becomes a real scheme-table
         `ArgumentOp` anywhere (the synthesis only ever mutates that function's own in-memory
         `all_args` dict), so the scheme-table scan had nothing to discover.

         **Fixed** by a new pass scanning the suite's own subcycle structure directly (the same
         `XMLSubcycle` nodes `suite_descriptions` already exposes) for non-literal loop counts,
         adding their standard_name to `input_vars` regardless of whether any scheme declares it.
      3. *Two missing inputs, part two.* `flag_indicating_cloud_microphysics_has_ice` is
         referenced only inside `test_host_data.meta`'s own `active =
         (flag_indicating_cloud_microphysics_has_ice)` conditional-presence expressions on the
         `effri`/`nci` DDT members — never itself a scheme argument anywhere. `active` is a real
         `ArgumentOp` property (`ccpp.py`) but no pass currently evaluates it as a conditional
         (see this same backlog's "opt_arg's dead `active` property" item) — the flag it names is
         still a genuine host requirement regardless.

         **Fixed** by scanning every `active =` expression's referenced identifiers (via a
         small regex, excluding Fortran logical-expression keywords) module-wide. Deliberately
         scoped to modules with exactly one suite: this scan isn't filtered to "tables this
         suite's own schemes actually match", which is only safe with one suite to attribute the
         match to — confirmed via `examples/capgen` (the one example generating two suites,
         `ddt_suite` and `temp_suite`, from a single invocation sharing one `host_ftn/
         test_host_data.meta`, which has this exact same `active = (index_of_water_vapor_
         specific_humidity > 0)` pattern): without the single-suite guard, that referenced name
         leaked into both suites' lists, even though nothing in `temp_suite`'s own schemes ever
         references it. `examples/ddthost` hits the identical `active =` pattern in its own,
         single-suite `host_ftn/test_host_data.meta` — a genuine, additional correct inclusion
         confirmed via its own FileCheck goldens (regenerated, not previously exercising this
         path either).

      All three confirmed via the real `Makefile` path: `ccpp_physics_suite_variables` now
      reports exactly 18 input / 14 output / 22 required variables, matching
      `test_var_compat_host_integration.F90`'s hardcoded expected lists exactly (content, not
      just counts, verified by direct comparison). Full suite 493 passed, 1 pre-existing xfail;
      var_compat's two goldens plus ddthost's two goldens (a genuine additional fix, not a
      regression) regenerated and passing. Direct regression coverage (sabotage-verified against
      all three fixes independently, plus guard tests for the two false-positive traps found
      along the way) in `tests/unit/test_suite_variables_gaps.py`.

      **Still open at the time this was written:** whether `make check` actually reports PASS
      given the separate, already-documented `col_start`/`col_end` unused-but-driver-chunks issue
      above — no Fortran compiler available in this environment to confirm either way. In
      practice the project owner's next actual run instead hit a different, real *runtime* bug
      first (see immediately below), before column-chunking correctness could even be reached.
    - **Fixed — a real runtime failure, found by the project owner actually running the built
      executable:** `ERROR in initialize of var_compatibility_suite: ERROR: effr_pre_init()
      needs to be called first`. Root cause, in a third code path from every fix above (none of
      which touch lifecycle — init/finalize/timestep — dispatch at all): `effr_pre_init`/
      `effr_calc_init`/`effr_post_init`/`effr_diag_init` all share one `intent(inout)`
      `scheme_order` scalar (`scheme_order_in_suite`) that `HostVariableMatchPass` correctly
      resolves to a DDT member, `phys_state%scheme_order` — `test_host_data.F90` initializes it
      to `1` before `physics_initialize` runs, and each scheme's own `_init` checks it against
      its expected call position, then increments it, relying on Fortran's pass-by-reference
      semantics to thread the running count across the whole call sequence. `lifecycle_cap.py`'s
      `_generate_lifecycle_fn` (a separate module from `run_dispatch.py`, covering init/finalize/
      timestep dispatch rather than the physics "_run" dispatch) only ever checked whether a
      standard_name was a plain `MODULE`-table variable (`host_var_map`, built with
      `include_host=False`) — it had **no DDT-member resolution branch at all**, unlike
      `run_dispatch.py`'s own "_run" dispatch. A DDT-member match fell through to the same
      fallback used for genuinely unmatched optional/allocatable args: a fresh, uninitialized
      local alloca (`lc_scheme_order`), silently discarding the host's real initial value.

      **Fixed** by teaching `_generate_lifecycle_fn` the same DDT-member resolution
      `run_dispatch.py` already has, reusing (not duplicating) `cap_shared.py`'s
      `_build_ddt_resolution_maps`/`_resolve_ddt_access_path`/`_resolve_member_subscripts`: the
      scheme-arg scan now also captures each arg's own `model_var_name`/`model_module_name`/
      `model_var_is_ddt` (previously discarded — only `standard_name` was kept), and the
      resolution loop tries DDT-member resolution before falling back to a fresh local.
      Confirmed via the real `Makefile` path: `test_host_ccpp_physics_initialize`'s call to
      `var_compatibility_suite_initialize` now passes `phys_state%scheme_order` directly,
      with no `lc_scheme_order` anywhere. Both var_compat FileCheck goldens regenerated and
      passing; full suite 495 passed, 1 pre-existing xfail; no other example affected (this gap
      was never exercised by any other example's lifecycle dispatch). Direct regression coverage
      (sabotage-verified) in `tests/unit/test_lifecycle_ddt_member_resolution.py`.

    - **Fixed — a hand-written-file bug, found once `ifx` actually built the example
      successfully: `gfortran` refused to compile `test_var_compat_host_integration.F90` at
      all**, on all three of its string-array constructors (`test_invars1`/`test_outvars1`/
      `test_reqvars1`):
      ```
      Error: Different CHARACTER lengths (58/59) in array constructor at (1)
      ```
      Confirmed by diffing directly against upstream capgen-v1's own
      `test_var_compatibility_integration.F90`: upstream is perfectly consistent — all 54 string
      literals across the three arrays are exactly 58 characters, uniformly (Fortran array
      constructors require every element to share one length; `gfortran` enforces this strictly,
      `ifx` apparently pads/truncates silently instead). The ported version had 30 of 54 entries
      off by ±1–3 characters — a padding-count slip introduced when the array literals were
      reflowed/reformatted during the port, not an upstream issue and not a design problem with
      the data itself (every variable name was already correct — confirmed by comparing stripped
      identifier lists between the two versions, in order, before touching anything).

      **Fixed, per explicit user authorization to touch this specific hand-written file for this
      specific issue** (the project's standing rule is to never modify hand-written files
      without explicit authorization — see the "never change handwritten files" feedback memory)
      — every string literal re-padded to exactly 58 characters, matching upstream exactly.
      Verified programmatically both ways: all 54 entries now uniformly 58 characters, and every
      identifier's stripped text is byte-identical to before across all three arrays, in the same
      order — only trailing whitespace changed.
    - **Fixed — a real `gfortran` runtime crash, found by actually running the built
      executable:**
      ```
      At line 184 of file examples/var_compat/var_compatibility_suite_cap.F90
      Fortran runtime error: Attempting to allocate already allocated variable 'effrr_in_unit_conv'
      ```
      Root cause, in `print_ftn.py` (the Fortran backend, a different layer from every fix
      above): each "forward" conversion op (`CCPPKindCastOp`/`CCPPUnitConvertOp`/
      `CCPPVerticalFlipOp`/`CCPPRowMajorConvertOp` — allocates a local temp, converts into it) is
      paired with a "write-back" op that writes the temp back to the host and deallocates it —
      but the deallocate only ever happened inside the write-back case. `effrr_in` (consumed by
      `effr_calc_run`) is pure `intent(in)`, so it has no write-back at all — nothing ever
      deallocated its conversion temp. Invisible for a subroutine called only once (Fortran
      auto-deallocates non-`SAVE` locals on return), but
      `var_compatibility_suite_radiation` calls `effr_calc_run` inside a nested 3-level
      subcycle loop (`do ccpp_loop_cnt0 = 1, 2` / `do ccpp_loop_cnt = 1, 2`) — the same temp gets
      allocated a second time within the same subroutine invocation, before Fortran ever gets a
      chance to deallocate it.

      **Fixed** by printing a guarded deallocate (`if (allocated(x)) deallocate(x)` — the same
      pattern `CCPPSafeDeallocOp` already uses elsewhere in this file) immediately before every
      `allocate(...)` statement all four of these op cases print, independent of whether a
      write-back exists — safe for pure `intent(in)` values, and a no-op on first entry so it
      doesn't change behavior for the ordinary, non-looped case either. Confirmed via the real
      `Makefile` path: every conversion temp in `var_compatibility_suite_radiation`
      (`effrr_in_unit_conv`, `effrr_in_vert_flip`, `effrs_inout_kind_cast`, etc.) now has a guard
      immediately before its `allocate`. Generator-wide fix, not var_compat-specific:
      `examples/helloworld`'s own `ccpp_t` variant golden also legitimately changed (same guard,
      same reason) and was regenerated; no other example was affected. Full suite 498 passed, 1
      pre-existing xfail; ruff unchanged (3 pre-existing errors in `print_ftn.py`, none new).
      Direct regression coverage (sabotage-verified, covering three of the four affected op
      cases — `CCPPRowMajorConvertOp` shares the identical one-line fix in the same printer
      function but isn't separately fixtured, lower marginal risk) in
      `tests/unit/test_print_ftn_conversion_temp_dealloc.py`.

      Confirmed via the real `Makefile` path: `make check` then reported a real numeric mismatch
      (see below), not a build/link failure.

    - **Fixed — the col_start/col_end chunking-correctness gap flagged above as unresolvable
      from the generator side turned out to be a real, fixable generator bug, found by actually
      running capgen-v1's own generator on this same example (metadata/suite XML) and diffing
      its output against xdsl-ccpp's:**
      ```
      Error: max diff of            effrs from expected value exceeds tolerance:    0.6000000E-04 >    0.5300000E-09
      ```
      capgen-v1 slices every host-array reference passed into a suite-part call by
      `col_start:col_end` (e.g. `phys_state%effrr(col_start:col_end, pver:1:-1)`) and recomputes
      any `horizontal_dimension`-standard_name scalar as `col_end - col_start + 1` (e.g.
      `ncol=(col_end - col_start + 1)`), so a chunked call only ever touches its own column
      window. xdsl-ccpp did neither: `test_host_ccpp_physics_run` accepted `col_start`/`col_end`
      (the fix above) but called `var_compatibility_suite_radiation` with the whole,
      unsliced host array and the host's raw, full column count every time — so each of
      `test_host.F90`'s 3 chunked driver calls redundantly reprocessed the entire array, and
      `effrs_inout`'s real `+=` accumulation (the only non-idempotent operation among this
      suite's schemes) over-accumulated by exactly 3x (90 µm actual vs. 30 µm correct — the
      reported diff is exactly that 60 µm excess). Every other checked value happened to be
      idempotent under repetition (constant overwrites, min/max clamps, or never touched by the
      scheme body), which is why only `effrs` surfaced a failure.

      Traced to three independent, precisely-located bugs, all in `run_dispatch.py`:
      1. `_build_run_block_signature`'s host-driven col_start/col_end fallback (the fix above)
         registered them into `union_non_host_args` but never into `non_host_std_to_canonical` —
         the dict `_build_run_dispatch_chain`'s already-existing `ArraySectionOp`-slicing logic
         actually looks up, so that logic's own guard always saw nothing and skipped slicing
         unconditionally.
      2. A scheme-declared scalar arg whose own standard_name is `horizontal_dimension`
         (var_compat's own `ncol`, matching `rad_lw`/`rad_sw`/`effr_calc`) was passed the host's
         raw, full column count through the ordinary host-var-reference path, with nothing
         recomputing it as `col_end - col_start + 1`.
      3. A pre-existing, previously-unreachable bug in the same `ArraySectionOp` block required
         at least 2 resolved dimensions before slicing anything — silently skipping any
         genuinely 1-D `horizontal_dimension`-only host array (var_compat's own `fluxLW`,
         `sfc_up_sw`, `sfc_down_sw`), which would otherwise have regressed those checked values
         from correct-but-redundant to actively wrong (only ever writing the first chunk's
         columns) once (1) started slicing their 2-D siblings correctly.

      **Fixed** by (a) also registering the canonical col_start/col_end mapping in the same
      fallback block, (b) recomputing a `horizontal_dimension`-standard_name scalar via the same
      alloc/load/sub/add-one/store op sequence `suite_cap.py`'s own `_build_ncol_compute_ops`
      already uses for this exact computation, and (c) relaxing the 2-dimension requirement to
      accept a single resolved dimension. No changes needed to `suite_cap.py`'s `_classify_args`
      (`advection`'s separate, already-correct legacy `horizontal_loop_extent` mechanism —
      confirmed untouched and unaffected), `print_ftn.py` (temp allocation sizes already derive
      from whatever shape the sliced actual argument has), the suite callee's own Fortran
      signature (assumed-shape dummies adapt automatically to a sliced actual argument), or the
      existing `optional`/`target` handling (confirmed orthogonal).

      Confirmed via the real `Makefile` path: `test_host_ccpp_physics_run`'s call now reads
      `effrr_inout=phys_state%effrr(col_start:col_end, 1:pver)`, `ncol=ncol` with
      `ncol = col_end - col_start + 1` computed just above, and
      `fluxLW=phys_state%fluxLW(col_start:col_end)` /
      `sfc_up_sw=phys_state%fluxSW%sfc_up_sw(col_start:col_end)` — matching capgen-v1's own
      generated shape. Affects every example whose host declares
      `horizontal_loop_begin`/`horizontal_loop_end` and whose schemes rely on the
      `horizontal_dimension`-only fallback rather than `horizontal_loop_extent` (`var_compat`,
      `helloworld`, and the synthetic `array-layout-reshape` FileCheck fixture, whose stale
      "temperature passed through directly" comment was also corrected); every
      `horizontal_loop_extent`-based example (`advection`, `capgen`, `ddthost`, chost/bind-c) is
      confirmed unaffected. Full suite: 452 unit + 47 filecheck (1 pre-existing xfail, 1
      pre-existing unrelated failure in `test_ccpp_xdsl_generates_caps`, confirmed present before
      this change too via `git stash`). Direct regression coverage (sabotage-verified against all
      three fixes independently, including the pre-existing `advection`-style no-double-insert
      guard) in `tests/unit/test_run_dispatch_col_bounds_fallback.py`.

      Confirmed via the real `Makefile` path that the generated Fortran text now matches
      capgen-v1's own shape exactly, and the full unit + FileCheck suites re-ran clean.

    - **Follow-up — a real gfortran compile error, found immediately on the first real build
      attempt of the fix above:**
      ```
      Error: Symbol 'ncol' at (1) has no IMPLICIT type
      ```
      Root cause, in `print_ftn.py`: the recomputed `ncol` local (a genuinely new
      `memref.AllocaOp`) is necessarily constructed nested inside the suite_name/suite_part
      dispatch chain's `scf.IfOp`s, but `print_ftn.py`'s local-alloca declaration collector only
      ever scanned the function body's own top-level ops (`bdy.block.ops`), not recursively into
      nested regions — so the assignment and its use in the call were both printed correctly, but
      the `integer :: ncol` declaration was silently dropped. The very next code block in the same
      file (declaring `CCPPKindCastOp`/`CCPPUnitConvertOp` temporaries) already solves this
      identical problem via `bdy.block.walk()` — this collector was simply never updated to match,
      since no prior code path needed a genuinely new local alloca'd from inside this specific
      nested dispatch chain.

      **Fixed** by changing that one collector from `bdy.block.ops` to `bdy.block.walk()`,
      matching the existing pattern two blocks below in the same function. Purely additive (a walk
      includes the top level, so every previously-found declaration is unaffected) — confirmed via
      the real `Makefile` path: `test_host_ccpp_physics_run` now declares `integer :: ncol`
      immediately after `errflg`. Full unit + FileCheck suites re-run clean (500 passed, same 1
      pre-existing xfail and 1 pre-existing unrelated failure as before); no other example's
      generated output changed. Direct regression coverage (sabotage-verified) added as
      `test_ncol_local_is_declared` in `tests/unit/test_run_dispatch_col_bounds_fallback.py`.

      Confirmed: `make check` now reports PASS (correct `effrs`), and CI is green for
      `var_compat` — the original numeric-mismatch report is closed out end to end.

    - **Fixed — a known, pre-existing gap in the same `ArraySectionOp` machinery, found while
      auditing what the col_start/col_end fix above did and didn't cover.** `effr_calc`'s
      optional, unmatched output `ncl_out` (`cloud_liquid_number_concentration`) has no host-side
      match, so it falls back to a cap-owned scratch buffer (`lc_ncl_out`), sized to the full host
      column count and dimensioned by `horizontal_dimension`/`vertical_layer_dimension` — a
      `CapVar`-sourced argument, a different `ArgSourceKind` than the `Host`/`DdtMember` case the
      earlier fix covered. Its slicing gate was still keyed entirely to the legacy
      `horizontal_loop_extent` name, and even where that legacy gate did fire (`advection`'s own
      `tendency_of_cloud_liquid_dry_mixing_ratio`), it only ever built a single-dimension section —
      so `lc_ncl_out` was never sliced under the newer convention at all: every chunked call wrote
      only the first chunk's columns, leaving later chunks stale for any host that read it
      (invisible here since this test's own checks never reference it).

      **Fixed** by splitting the `CapVar` branch in two: the existing `horizontal_loop_extent` case
      is left completely untouched (still exactly one dimension, matching `advection`'s
      already-correct output byte-for-byte), and a new `horizontal_dimension` case reuses the same
      multi-dimension resolution loop the `Host`/`DdtMember` branch already has. Confirmed via the
      real generator path: the call now reads `ncl_out=lc_ncl_out(col_start:col_end, 1:pver)`;
      `advection`/`capgen`'s goldens (which exercise the legacy path) are byte-identical, only
      `var_compat`'s two goldens changed. Full unit + FileCheck suites re-run clean (502 passed,
      same 1 pre-existing xfail and 1 pre-existing unrelated failure). Direct regression coverage
      (sabotage-verified, plus a guard confirming the already-covered `Host`/`DdtMember` slicing in
      the same call is undisturbed) in `TestCapVarSlicedWhenRankTwo`,
      `tests/unit/test_run_dispatch_col_bounds_fallback.py`.

    - **Fixed — two robustness gaps in PR #44's own code, found by Copilot's automated review
      after the PR had already merged.** Both are latent (no example in this repo currently
      triggers either), not live failures:
      1. `ccpp_cap.py`'s Pass 2c `active =` expression token scan (added in this same PR) excluded
         boolean-expression keywords (`and`/`or`/`not`/`eqv`/`neqv`/`true`/`false`) but not
         Fortran's dotted relational operators (`.eq.`/`.ne.`/`.lt.`/`.le.`/`.gt.`/`.ge.`), which
         tokenize down to bare words (`eq`, `gt`, ...) once the regex strips the surrounding dots
         — `active = (x .gt. 0)` would have incorrectly added `gt` to the suite's variable list as
         if it were a real referenced standard_name. **Fixed** by adding all six to
         `_ACTIVE_EXPR_KEYWORDS`. Regression: `TestActiveExpressionRelationalOperatorNotMistakenForStdName`
         in `tests/unit/test_suite_variables_gaps.py` (sabotage-verified).
      2. `suite_cap.py`'s `_resolve_host_only_std_name` (also added in this PR, for dynamic
         subcycle loop-count resolution) compared `standard_name` case-sensitively, unlike every
         other standard_name lookup in this codebase (all lowercased). A host `.meta` spelling a
         standard_name with different capitalization than the suite XML would have silently failed
         to resolve, raising "Subcycle loop count ... has no scheme argument and no host match"
         even with a genuine match present. **Fixed** by lowercasing both sides of the comparison.
         Regression: `TestDynamicLoopCountCaseInsensitiveMatch` in
         `tests/unit/test_suite_dynamic_loop_count.py` (sabotage-verified).

      Full unit + FileCheck suites re-run clean (504 passed, same 1 pre-existing xfail and 1
      pre-existing unrelated failure as before).
- **`nested_suite` — Fixed 2026-07-27 (PR #47, merged), per the rescoped plan below.** Both
  features implemented exactly as scoped: `ccpp_xml.py`'s `_expand_nested_suites`/
  `_replace_nested_suite`/`_load_nested_suite_reference` (Feature 1, frontend-only, confirmed zero
  changes needed anywhere downstream); two new `SuiteOp` properties plus `suite_cap.py`'s
  `_build_suite_lifecycle_call_ops` (Feature 2). Ported `examples/nested_suite` from the real
  upstream test as the end-to-end proof — both features generated correctly against the real
  upstream files on the first attempt, no new generator bugs found. A Copilot review on the PR
  caught one real latent bug (a suite-level `<nested_suite>` naming a multi-child group produced
  several same-named groups instead of one, never triggered by the real example's own single-child
  groups) and one error-message typo, both fixed and sabotage-verified
  (`tests/unit/test_nested_suite_expansion.py`, `tests/unit/test_suite_lifecycle_hooks.py`). Added
  to `.github/workflows/compile-tests.yml`'s matrix. Not yet verified: an actual `gfortran`/`ifx`
  build-and-run (no compiler on this laptop) — that's the one remaining open item for this example
  specifically.

  **Original rescoped plan (2026-07-27), for reference:**
- **`nested_suite` — L. Rescoped 2026-07-27 after cloning capgen-v1's real
  `end-to-end-tests/nested_suite/` and reading the actual upstream Python source
  (`capgen/metadata/parse_tools/xml_tools.py`'s `expand_nested_suites`/`replace_nested_suite`/
  `load_suite_by_name`, `capgen/generator/suite_resolver.py`/`suite_cap.py`'s suite-level
  `<init>`/`<final>` handling) instead of guessing from the XML alone — corrects and replaces the
  prior (stale, unverified) scope note below.** Two loosely-coupled features under one SDF schema
  bump (`version="2.0"`); `XMLSuite` today only ever reads one file and only parses `<group>`
  children — `<nested_suite>`/`<init>`/`<final>` are currently silently skipped, not rejected.

  **Feature 1 — `<nested_suite name=... group=... file=.../>`:** splices groups/schemes from a
  *different* suite XML file into this one, at suite level or group level, recursively (2 levels
  deep in the real example: `radiation3_suite` → `radiation3_subsuite`). Confirmed this is a
  **pure XML-tree preprocessing pass** in capgen-v1 — run once, entirely before any suite/group/
  scheme object is built (`suite_xml.py:590-591`, right after `ET.parse`). Mechanics
  (`xml_tools.py:145-278`): iteratively re-scans for `<nested_suite>` under `<suite>` or `<group>`
  until none remain (capped at `max_iterations = 10`, clear error on a suspected cycle);
  `load_suite_by_name` validates the referenced file's own `<suite name=...>` actually matches
  before returning either the whole suite (`group=` omitted) or one named `<group>`;
  `replace_nested_suite` splices in deep copies of the *referenced element's own children*
  (unwrapping the group/suite tag) — with one non-obvious rule: a suite-level `<nested_suite>`
  that also names a `group=` gets its spliced children re-wrapped in a **fresh**
  `<group name=group_attr>`, everything else splices in as-is. Relative `file=` paths always
  resolve against the **original top-level** suite file's directory, not the referencing file's
  own directory. Because expansion happens before any object exists, **nothing downstream needs to
  change** — `XMLGroup`/`XMLScheme`/`XMLSubcycle`, the IR, `suite_cap.py`, `cap_shared.py`,
  `suite_variable_model.py` all just see an ordinary, larger suite XML once expansion is done. This
  is entirely a frontend, single-file (`ccpp_xml.py`) change.

  **Feature 2 — suite-level `<init>`/`<final>` scheme hooks:** a scheme's `init`/`final` phase
  called once per suite lifecycle, not per-group, declared as direct children of `<suite>`.
  Confirmed via `suite_resolver.py:2507-2540`: resolved exactly like an ordinary scheme call
  (same machinery, its own fresh local-name set since it lives outside every group), clear
  `CCPPError` if the named scheme has no matching phase. `suite_cap.py:766-775`/`:848-851`: emits
  exactly one extra call inside the suite's own `<suite>_init`/`<suite>_final` bodies (init after
  group state allocation, before flipping suite state to INITIALIZED; final mirrored), reusing the
  same single-call-emission helper every other lifecycle call already uses. Needs: `XMLSuite`
  parses `<init>`/`<final>` alongside `<group>`; two new optional `StringAttr` properties on
  `SuiteOp` (`ccpp.py`, alongside the existing optional `version` property); `suite_cap.py`'s
  per-suite `GenerateSuiteSubroutine` emits the extra call when set (exact insertion line not yet
  pinned down — identify during implementation). Open question: whether `ccpp_descriptors.py`'s
  IR-reconstruction path needs a mirrored field for any consumer besides `suite_cap.py` itself.
  Upstream's own test proves this cleanly: a minimal scheme with only `init`/`final` entry points
  increments a shared counter; the test's pass condition is exactly counter `== 2`.

  **Correction to the prior scope note (kept for history):** nested-subcycle support was NOT
  actually a blocker — that item was itself stale and has been deleted from this backlog (see
  history above); nested subcycles have been fully supported since var_compat's own port. Its
  scheme `.meta` files are **not** byte-identical to `var_compat`'s (checked directly — real
  diffs), but the differences are the same category already documented in
  `examples/var_compat/README.md`'s "Adaptations made during porting" section (reuse that recipe;
  one adaptation, the tight-bracket normalization, is no longer even needed post the `.meta`
  parser bracket-spacing fix). `version="2.0"` itself needs no special handling beyond being
  accepted — xdsl-ccpp does no XML schema validation today, so it's purely a marker upstream uses
  to select schema variants.
- **`constituents_dim` — Rescoped 2026-07-27 after cloning capgen-v1's real
  `end-to-end-tests/constituents_dim/` and actually running it through today's frontend + cap
  generation (no compiler needed for this part) instead of reasoning from the code alone. The
  original two-sub-item framing below is directionally correct about what's missing but
  **understates the severity** — both sub-items share one common root blocker, one layer earlier
  than either sub-item's own file:line citations suggest, and both currently produce a hard
  pipeline crash (unmatched host variable), not silently-wrong output.**

  The real example exercises three cases via `const_dim_producer`/`const_dim_consumer`: (1) a
  host-owned array dimensioned by `number_of_ccpp_constituents`, where the host never declares that
  count as its own scalar (the framework owns it); (2a) a non-allocatable suite-scoped scratch var
  dimensioned singly by the count, meant to be framework-allocated; (2b) an *allocatable*
  suite-scoped scratch var, scheme-allocated in `_run` using a scalar arg (`n_const`,
  standard_name `number_of_ccpp_constituents`) passed directly into the scheme.

  **Root blocker (shared prerequisite for everything below):** `HostVariableMatchPass` has no
  concept of a scalar argument being framework-injected (the way `ccpp_error_message`/
  `ccpp_error_code` already are) — `number_of_ccpp_constituents` is referenced in this codebase
  only as a *dimension name* (`ccpp_cap.py`), never recognized as a legitimate framework-provided
  *scalar argument* value. Confirmed empirically: running `const_dim_producer`'s own `n_const` arg
  through today's pipeline fails immediately with `ValueError: Host model variable matching/
  compatibility failed: ... argument 'n_const' ... has no matching host model variable` — well
  before `ccpp_cap.py`'s allocation-size logic (the code the original sub-item 1 note points at)
  or `constituent_cap.py`'s per-arg flag scan (sub-item 2's own target) are ever reached.

  - **Sub-item 1 (suite-workspace vars sized by constituent count) — narrower than originally
    scoped for the non-allocatable case, but case 2b needs the root blocker fixed first.**
    `ccpp_cap.py`'s `_DIM_TO_ALLOC` is *not* actually hardcoded to two literal variable names the
    way the phrasing here originally implied — it's already a generic dimension-standard_name →
    allocation-size-expression lookup, applied uniformly to any `CapScratch` var's declared dims,
    and its `number_of_ccpp_constituents → "lc_num"` entry is consumed by a genuinely generic loop
    in `constituent_cap.py` (where `lc_num` is already a real, in-scope local by the time it's
    used). For case 2a (non-allocatable, framework-allocated) this generic mechanism plausibly
    already produces valid Fortran with no new work — **this needs direct verification, not
    assumption**, since it wasn't run end-to-end in isolation. Case 2b (allocatable,
    scheme-allocated via `n_const`) is fully blocked by the root blocker above and never reaches
    this code at all.
  - **Sub-item 2 (cross-scheme constituent-flag inference) — confirmed real, but likely
    unreachable today for the same root-blocker reason before it would ever matter.**
    `const_dim_consumer.meta`'s own `qbase`/`qtend` args carry no `advected`/`constituent`
    property at all — only the producer's matching args do (confirmed directly: the upstream
    README states this is the deliberate point of the test). Every `advected`/`constituent`
    property read in this codebase (`constituent_cap.py`'s `_collect_constituent_info`,
    `cap_shared.py`'s classification checks) is confirmed strictly local to one scheme's own arg
    table — no module-wide "which standard_names has *any* scheme flagged" set exists anywhere.
    But since no host anywhere declares the underlying standard_names either (they only exist
    inside framework-owned constituent storage), the consumer's unflagged args would almost
    certainly also fail hard at host-matching first — the same class of failure as sub-item 1's
    `n_const` case, not silently-wrong classification.
  - **A third, previously-untracked gap surfaced while probing this:** working around the root
    blocker (via a throwaway fake host declaration, just to see further) reached a *second*,
    separate crash — an xDSL IR verifier error (`memref.copy` shape mismatch) somewhere in
    `register_consts`'s constituent-registration path (its own `dyn_const` allocatable DDT-array
    output). Not diagnosed; worth its own investigation before scoping implementation here.
  - **Recommended starting point for whoever picks this up:** decide how `HostVariableMatchPass`
    recognizes framework-injected scalars in general first (the shared prerequisite for both
    sub-items), rather than jumping straight to `ccpp_cap.py`'s allocation-size dict or
    `constituent_cap.py`'s per-arg flag scan as originally framed below.
  - **Re-confirmed 2026-07-29/30 while actually porting this example into `examples/constituents_dim/`
    (reusing the CMake build system, same as the other three items below).** Ported
    `register_consts`/`const_dim_producer`/`const_dim_consumer` + `host_data.meta` verbatim, folded
    `main.meta`'s `type=control` table into a `type=host` `test_host.meta` (same conversion as every
    other port here — see `chunked_data` below), and ran real cap generation against it — hit the
    exact same `ValueError` on `n_const`/`number_of_ccpp_constituents` quoted above, unchanged. The
    example's files and a `CMakeLists.txt` (using `xdsl_ccpp_capgen()`) exist in the repo now, but
    it is deliberately **not** `add_subdirectory`'d from the root `CMakeLists.txt` — doing so would
    `message(FATAL_ERROR)` at configure time for the whole project, not just this example. `main.F90`
    is still upstream's unadapted generic-dispatch driver (no point rewriting it against a cap that
    doesn't generate); re-adapt it to xdsl-ccpp's per-host-prefixed calling convention (pattern in
    `examples/chunked_data/main.F90`) once the root blocker above is fixed.
  - **RESOLVED — merged as PR #67 (2026-08-13), CI green.** Closed via four real xdsl_ccpp
    capability gaps, not vocabulary issues in this example's own `.meta` files (confirmed clean
    v1 vocabulary against real capgen-v1 upstream):
    1. The root blocker above — fixed by adding `number_of_ccpp_constituents` to
       `CCPP_FRAMEWORK_STD_NAMES`/`FRAMEWORK_STD_NAME_TO_CAP_VAR` (`ccpp_conventions.py`/
       `cap_shared.py`), resolving it to `size(lc_all_constituents)` when no host declares it.
       **False start, corrected via Copilot review:** the first attempt instead added
       host-match-priority logic to `HostVariableMatchPass`, specifically to avoid breaking
       `examples/constadv`'s own host-declared `number_of_ccpp_constituents` — traced back to
       `constadv` itself using a capgen-v0 pattern with no real capgen-v1 counterpart (audited
       every real capgen-v1 end-to-end test using this standard_name: `advection`,
       `advection_auto_clone`, `constituents_dim`, `instances_advection` — none ever
       host-declares it). Fixed `constadv_host_mod.meta` instead (removed the stale host
       declaration — `constadv` already registers its own `dyn_const` via the real v1
       mechanism, so the framework count is correct there too), keeping the simpler,
       unconditional fix and avoiding new xdsl_ccpp-side complexity for a pattern real capgen-v1
       never uses.
    2. Sub-item 2's predicted "cross-scheme constituent-flag inference" gap **did not
       materialize** — `const_dim_consumer`'s unflagged `qbase`/`qtend` sail through
       `HostVariableMatchPass` cleanly once (1) above is fixed; no cross-scheme std_name set was
       needed after all.
    3. A **new bug**, not predicted by either sub-item: `suite_cap.py`'s per-phase output-arg
       allocation tracked "already have errflg/errmsg" coverage by literal local name
       ("errflg") instead of standard_name (`ccpp_error_code`) — since this example's schemes
       name their own arg `errcode`, this produced a second, spurious return value in every
       `_run`-phase suite subroutine, corrupting the caller-side copy-back. This is almost
       certainly the real identity of the "third, previously-untracked gap" noted above (the
       `memref.copy` shape-mismatch crash) — once fixed, that crash didn't recur, and no
       separate constituent-registration bug was ever found.
    4. Once (1)-(3) landed, cap generation succeeded but produced Fortran that would crash at
       runtime: `cwork`/`awork` (Case 2a/2b) were declared but never allocated anywhere. Root
       cause: they're SuiteOwned scratch vars declared only in a scheme's own `_run` table
       (never `_init`/`_register`), and `_build_framework_refs`'s per-phase allocation attempt
       was gated to `_init`/`_register` postfixes only. Fixed by also attempting allocation
       during `_run`, gated on a `already_scheduled_allocs` set shared across all of one
       suite's phase calls, so a var *with* a real `_init`/`_register` occurrence doesn't also
       get a redundant second allocation. **False start, corrected:** the first version of this
       fix only tracked scheduling for the per-phase `framework_vars` loop, not the separate
       `SuiteVariableModel.suite_owned_vars()` sweep that's what actually covers `capgen`'s own
       `to_promote`/`promote_pcnst`/`temp_calc` — broke two already-passing filecheck goldens
       until both allocation mechanisms were tracked in the same shared set.
    5. `qbase` (advected, dims `horizontal_dimension`/`vertical_layer_dimension`) was *still*
       never allocated after (4) — its dims are declared only in `host_data.meta`, a
       `type=host` table, and `_find_loop_upper_bound`'s host-table fallback only ever scanned
       `type=module` tables (HOST-type vars are deliberately never `use`-associated anywhere in
       this codebase — confirmed this is consistent, not an oversight, by checking
       `run_dispatch.py`'s `host_block_std_names` handling). Fixed by adding a third fallback:
       derive the dimension from an already-in-scope, non-SuiteOwned array's own shape
       (`size(coupler_flux, 1)`, `size(qtend, 2)`) instead of requiring a host/module lookup at
       all. One bug found in the first version of this fix too: the new fallback initially
       matched `qbase` against its own dim entry (self-referential `size(qbase, 2)` on an array
       not yet allocated) — fixed by excluding SuiteOwned candidates from the scan.
    6. **Post-merge, Copilot-flagged on PR #67:** `ccpp_cap.py`'s constituent-API emission gate
       (`if dyn_names or fixed_adv or scratch_var_list`) never accounted for a scheme merely
       *referencing* `number_of_ccpp_constituents` with no dynamic registration or
       fixed-advected constituent of its own elsewhere in the suite — since (1)'s fallback
       resolves that standard_name to `size(lc_all_constituents)` unconditionally, such a
       (hypothetical, not exercised by this example) suite would reference an undeclared
       Fortran symbol and fail to compile. Fixed by extending `_collect_constituent_info` to
       also detect a bare reference and OR it into the gate.
    7. **Separate, unrelated finding surfaced along the way:** this example's own vendored
       `ccpp_constituent_prop_mod.F90`/`ccpp_scheme_utils.F90` (duplicated, byte-identical, in
       `examples/advection` too) turned out to be missing `diag_name`, a real field/
       `instantiate()` argument `register_consts.F90` (ported faithfully from real capgen-v1
       upstream) genuinely needs — confirmed **not** a capgen-v1 bug: real capgen-v1 has
       exactly one, canonical, ~2700-line implementation of this module
       (`capgen/src/ccpp_constituent_prop_mod.F90`, with its own further dependencies on
       `ccpp_hashable.F90`/`ccpp_hash_table.F90`), built against by every real end-to-end test
       with no per-test duplication at all. xdsl-ccpp's own choice to hand-duplicate a
       simplified stub per example is what let this drift silently — the stub only ever grew to
       cover whatever the *already-wired* examples happened to call, and `register_consts.F90`
       was the first scheme in the repo to actually need `diag_name`. Consolidated the
       simplified stub (not the full real library — xdsl_ccpp's own generator,
       `constituent_cap.py`, only ever targets the simplified API, never the real
       `ccpp_model_constituents_t` wrapper type real capgen-v1 actually uses) into a single
       source, `examples/shared/ccpp_constituent_prop_mod.F90`/`ccpp_scheme_utils.F90` (moved to
       `xdsl_ccpp/framework_src/` as of task #75, `capgen_v1_parity_backlog.md` -- `examples/shared/`
       no longer exists), compiled
       directly into each consuming example's own TESTLIB target — not a separate pre-built
       shared library at the root `CMakeLists.txt` level, which was tried first and failed
       (`Cannot open module file 'ccpp_kinds.mod'`): `ccpp_kinds.F90` is itself per-example
       *generated*, not a static file any root-scope target could depend on before that
       example's own cap generation has run. `examples/advection` still compiles its own
       separate, currently-identical copy for now — see the follow-up item below.
    8. `main.F90` rewritten to call xdsl_ccpp's own per-host-prefixed generated subroutine names
       instead of capgen-v1's generic dispatch convention (same rationale as `chunked_data`'s
       own `main.F90`). Surfaced a separate, cross-cutting finding while doing this — see the
       follow-up item below, not fixed as part of this.
- **Follow-up backlog items spawned by the `constituents_dim` fix above:**
  - Migrate `examples/advection` (and audit every other example for similarly duplicated
    per-example support files, not just these two) to link the single source
    `ccpp_constituent_prop_mod.F90`/`ccpp_scheme_utils.F90` (`xdsl_ccpp/framework_src/` as of
    task #75, `capgen_v1_parity_backlog.md` -- was `examples/shared/`) instead of its own local
    copy — see
    item 7 above for why this matters: a duplicated stub only ever grows to cover whatever's
    already been exercised, which is exactly what caused the `diag_name` compile bug in the
    first place, and it will keep happening again for any other file duplicated the same way.
  - Decide whether to change xdsl_ccpp's cap generator to match real capgen-v1's own bare
    (non-host-prefixed) subroutine naming convention (confirmed via
    `capgen/generator/host_cap.py`'s own docstring: real capgen-v1 host-prefixes only the
    *module*, `<host>_ccpp_cap.F90` — the public subroutines inside stay bare,
    `ccpp_physics_run` not `<host>_ccpp_physics_run`), or keep xdsl_ccpp's current
    host-prefixed-subroutine convention as a deliberate, documented extension every already-
    wired example's own driver already depends on. Also noted while investigating: xdsl_ccpp
    collapses capgen-v1's split suite-state lifecycle (`ccpp_init`/`ccpp_final`) vs. group-level
    scheme dispatch (`ccpp_physics_init`/`ccpp_physics_final`) into one combined entry point per
    phase — a related, possibly architectural difference, not just naming; not investigated
    further.
- **`suite_allocate` — L, plus one cheap independent bugfix.**
  - **Cheap fix, do first, unrelated to the rest — S.** `_build_cap_var_map`'s scratch-var
    allocation silently falls back to allocating size `"1"` for any dimension name not in
    `_DIM_TO_ALLOC` — a latent mis-allocation bug found while scoping this, unrelated to whether
    the larger `suite_allocate` pattern ever gets built. Should raise instead (same "raise, don't
    silently mask" precedent as the Phase 7 Copilot-review fixes), independent of everything else
    here.
    - **Correction, 2026-07-29/30, after actually porting and running this example (in
      `examples/suite_allocate/`) — this specific predicted bug does NOT reproduce.** Real cap
      generation against the ported `make_workspace`/`use_workspace`/`data.meta`/`test_host.meta`
      files succeeds cleanly, and the generated `suite_allocate_suite_cap.F90` allocates the
      scratch workspace (`work(:)`) at the *correct*, dynamically-determined size — `nw` is set by
      `use_workspace_timestep_init` in the timestep-initial phase and `work(nw)` is allocated with
      that real value in the run phase, not a hardcoded `"1"`. The size-`"1"` fallback described
      above may still be a real latent bug for some other dimension-name shape not exercised by
      this particular example, but it is not what blocks `suite_allocate` as ported.
    - **New bug found instead, 2026-07-29/30 — the actual reason this port can't pass a real
      ctest.** The generated `ccpp_physics_run` (bare name since Stage 5 of the
      vocabulary-resolution redesign, below) captures the `use_workspace` scheme's
      `workspace_checksum` output into a throwaway local temp (`ccpp_tmp_0`) and discards it when
      the subroutine returns — it is never `use`-associated from the host's own `data` module (the
      way `examples/helloworld`'s generated cap correctly does for its `type=module` host vars) nor
      threaded back out through the dispatch call's own argument list. `examples/suite_allocate/
      CMakeLists.txt` exists and cap-generates successfully but its `add_test(...)` is deliberately
      commented out, and the directory is not `add_subdirectory`'d from the root `CMakeLists.txt`,
      until this is fixed.
      - **Scoped precisely, 2026-08-13, after the vocabulary-resolution redesign landed (see that
        entry below) -- smaller than originally estimated, root cause fully located, not yet
        implemented.** `run_dispatch.py` builds its own `host_var_map` at line 121 via
        `_build_host_var_map(meta_data, include_host=False)` -- MODULE-type only, the exact same
        "HOST-type is never use-associated" assumption the redesign already disproved for
        `active=`-referenced vars. The write-back mechanism that would handle `checksum` already
        exists and works correctly for MODULE-type vars (line 1466: `elif ret_std_name and
        ret_std_name in host_var_map:` builds a `HostVarRefOp` + `memref.CopyOp` write-back) --
        `checksum` just never reaches it because it's filtered out of the map before that check
        runs. An identically-shaped check for `intent(inout)` results exists at line 1392, same
        bug class, not yet known to be exercised by any current example but worth fixing at the
        same time.
        - **The fix is reusing existing infrastructure, not building new machinery:** promote
          `_classify_host_table_vars` (currently a method on `suite_cap.py`'s
          `GenerateSuiteSubroutine`, Stage 1) into a shared free function in `cap_shared.py`
          (it only touches `self.meta_data`, trivial to extract, no behavior change to
          `suite_cap.py`) and use it in `run_dispatch.py` to build a second, enriched host-var map
          (MODULE-type + `state`-classified HOST-type, excluding `dispatch_scalar`-classified) --
          swapped in at just the two write-back sites (1392, 1466), **not** a blanket flip of
          `include_host` at line 121, since that map is also used for DDT-member resolution and
          array-section dimension-name resolution (lines 915, 1028/1128, 1224/1226) not yet
          verified safe to widen.
        - **Downgraded from L to M.** Remaining unknowns before calling it done: (a) whether
          `lifecycle_cap.py`'s own `use_workspace_timestep_init`-phase handling has the same gap
          for `nw` (the workspace-size output) -- untested, possibly a second instance of the same
          bug; (b) whether any *other* HOST-type-table var in some other passing example currently
          relies on falling through this same gap to a *different*, currently-correct path --
          widening the map could regress it.
      - **✅ Fixed (2026-08-17), exactly as scoped -- one stage, not multi-stage** (the M-vs-L
        downgrade held): `classify_host_table_vars` promoted from a method on `suite_cap.py`'s
        `GenerateSuiteSubroutine` (Stage 1) into a free function in `cap_shared.py` (only touched
        `self.meta_data`, mechanical extraction, no behavior change -- verified with the full
        suite green before touching `run_dispatch.py` at all). `run_dispatch.py` then builds a
        second map, `state_host_var_map` (`host_var_map`, MODULE-type only, enriched with
        `state`-classified HOST-type entries), computed once inside `_build_run_dispatch_chain`
        from the already-available `meta_data` parameter -- no new parameter threading needed
        anywhere else. Swapped in at exactly the two write-back sites identified during scoping
        (the `intent(inout)` case and the `intent(out)` case `checksum` actually hits); every
        other `host_var_map` usage (DDT-member resolution, array-section dimension-name
        resolution) deliberately left untouched, matching the scoping's own caution about not
        blanket-flipping `include_host`.
        - **Both open unknowns from the scoping resolved, not just assumed fine:** (a) `nw`
          (workspace_dimension) turns out to be a suite-cap-owned scratch variable -- a
          module-level local declared directly inside `suite_allocate_suite_cap`, never
          appearing in any host `.meta` table at all -- so it was never subject to this bug
          class in the first place, no fix needed. (b) the full pre-existing test suite (566
          tests, including `var_compat`'s and `opt_arg`'s own HOST-type-heavy goldens) passed
          unchanged after the `run_dispatch.py` change, confirming no other example silently
          relied on the old gap.
        - **Verified directly on the real generated output**, not just via the test suite:
          regenerated `examples/suite_allocate` via `xdsl_ccpp.tools.ccpp_dsl` (the tool CI's
          CMake step calls) and confirmed `use data, only: checksum` now appears, and
          `ccpp_physics_run` passes the use-associated `checksum` directly into
          `suite_allocate_suite_workspace_group`'s own `intent(out)` dummy argument --
          the `ccpp_tmp_0` throwaway local is gone entirely.
        - **Re-enabled and wired in:** `examples/suite_allocate/CMakeLists.txt`'s
          `add_test(...)` uncommented; `add_subdirectory(examples/suite_allocate)` added to the
          root `CMakeLists.txt`; matrix entry added to
          `.github/workflows/compile-tests-cmake.yml`. Not yet compile/run-verified on this
          laptop (no Fortran compiler available) -- CI is the first real check, same limitation
          as every other example ported this way.
  - **The actual pattern — L.** Scheme-allocated (not framework-allocated) suite-scoped scratch
    memory, dimensioned by a *different* scheme's `timestep_init`-phase output, allocated at
    run-time rather than init-time, relying on CCPP's phase-then-scheme execution ordering.
    `suite_variable_model.py`'s own docstring assumes init-time allocation with statically-known
    dimensions throughout — this needs a genuine new allocation-timing model plus
    cross-scheme-phase dependency awareness, not a variant of the existing path.
- **`chunked_data` — feasibility test done 2026-07-29/30, and it works: ported into
  `examples/chunked_data/`, wired into the root build.** Ran the real `chunked_data_scheme.meta` +
  `data.meta` through today's pipeline (bypassing CMake first, then via a real
  `xdsl_ccpp_capgen()`-based `CMakeLists.txt`) — cap generation succeeds cleanly with no errors,
  confirming the suspicion above: `thread_num`/`nphys_threads` are ordinary host-matched scalar
  args needing no special support, and the host driver just calls the same generated dispatch
  subroutine once per chunk with a different `[lb,ub]` (here `lb`/`ub`, matching upstream's own
  naming) range each time. `main.meta`'s upstream `type=control` table (same issue every other
  example in this backlog section hits) was folded into a `type=host` `test_host.meta`, dropping
  `suite_name`/`group_name`/`thread_num`/`nthreads`/`nphys_threads` and keeping only
  `lb`/`ub`/`errmsg`/`errflg` — precedent already set by `examples/var_compat`'s own port. One
  real nuance surfaced while adapting the driver: the generated `test_host_ccpp_physics_run` takes
  the chunked array (`chunked_data_instance%array_data`) as an **explicit caller-supplied
  argument**, unlike every other lifecycle phase (register/initialize/finalize/timestep_initial/
  timestep_final), which resolve it internally via `use` association with no caller involvement —
  and the generated suite cap does not slice by `[lb,ub]` internally, so the driver must pass the
  already-sliced `chunked_data_instance%array_data(lb:ub)` explicitly at each call. This is now
  `add_subdirectory`'d from the root `CMakeLists.txt` alongside the other 13 examples (not yet
  compile/ctest-verified — no Fortran compiler is available in this environment, matching the same
  limitation every other example already has here).
- **`instances`/`instances_advection` — M, and a real decision point, not just an estimate.**
  xdsl-ccpp already has a working multi-instance mechanism (`--num-instances` CLI flag →
  `ccpp_t`-handle-based per-instance state; the mechanism itself is real and unit/filecheck-tested
  (`tests/unit/test_ccpp_t_threading.py`, `tests/filecheck/.../helloworld-ccpp-t.mlir`, driven by
  `examples/helloworld/hello_world_host_ccpp_t.meta`) — **correction: that file is a side input,
  not actually wired into the compiled/ctest-run `examples/helloworld` example**, which only uses
  the plain `hello_world_host.meta`. So today this mechanism is only exercised at the unit/
  filecheck level, not as a real end-to-end example). Capgen-v1's pattern here is architecturally
  different: explicit `instance_number`/`number_of_instances` **scalar args** threaded directly
  into scheme signatures, plus host DDT arrays literally dimensioned by `number_of_instances` — no
  `ccpp_t` handle involved at all. Building this means recognizing `instance_number`/
  `number_of_instances` as ordinary host-matchable standard names and confirming array-
  dimensioning-by-them works generically (likely does, if dimension-name handling elsewhere is
  already name-agnostic — needs verification, not assumed). **Open question for the project
  owner:** is a second, structurally different multi-instance model actually wanted, given a
  working one already exists — or is this intentionally out of scope?
  - **Ported into `examples/instances/` and `examples/instances_advection/` 2026-07-30 (source
    brought in on request, decision on the architecture question deliberately deferred — neither
    is `add_subdirectory`'d from the root `CMakeLists.txt` yet).** Both needed the same
    `type=control`→`type=host` `main.meta` conversion as every other port in this backlog section,
    this time keeping `instance`/`ninstances` (standard_name `instance_number`/
    `number_of_instances`) as ordinary protected host scalars rather than dropping them — they're
    the mechanism under test, not dispatch plumbing to discard.
    - **`instances` — cap generation actually SUCCEEDS, but inspecting the generated Fortran shows
      the real per-instance mechanism isn't implemented.** `instance_data` (the host's own
      `instance_type` array, dimensioned by `number_of_instances`) never appears anywhere in
      either generated file. `data_array`/`data_array2`/`data_array_opt` (DDT members of
      `instance_type`) get resolved as ordinary top-level caller-supplied ("Block") arguments
      instead of being indexed through `instance_data(instance)%...` — `instance` itself is
      accepted and correctly forwarded into the scheme calls, but nothing generated ever uses it
      to select which instance's own storage to touch. Plausible reason, not confirmed: `_build_
      ddt_resolution_maps`/`_resolve_ddt_access_path` (`cap_shared.py`, `suite_cap.py` — the same
      DDT-chain machinery fixed for PR #54 earlier this session) resolves a DDT member access to a
      single, statically-known instance variable; `instance_data` being an *array* of DDT
      instances, addressable only via a runtime-only scalar, likely falls outside what that
      resolution can handle at all, so it silently falls back to Block-arg treatment rather than
      erroring. Not diagnosed further. A driver could still recover real per-instance separation
      by hand — passing `instance_data(ins)%data_array(:,2)` etc. explicitly at each call, the
      same shape of workaround `examples/chunked_data`'s driver already needed for its own
      explicit `[lb,ub]` array slicing — but that's a manual workaround standing in for capgen-v1's
      automatic per-instance dispatch, not a real port of the mechanism; building the automatic
      version means taking a position on the open architecture question above first, which is why
      `main.F90` was deliberately left as upstream's own unadapted driver for now.
    - **`instances_advection` — hard fails at cap generation**, confirmed by actually running it:
      ```
      xdsl.utils.exceptions.VerifyException: Expected source and destination to have the same shape.
        "memref.copy"(%9, %errmsg) : (memref<i32>, memref<512xi8>) -> ()
      ```
      an xDSL IR verifier crash inside the generated constituent-registration cap code (around
      `test_host_ccpp_register_constituents`/`is_scheme_constituent`). This is the same *class* of
      failure as the "third, previously-untracked gap" noted under `constituents_dim` above (also
      a `memref.copy` shape mismatch, also inside a constituent-registration path) — worth
      comparing the two directly before scoping either, they may share one root cause. Not
      diagnosed further.
  - **Architecture decision made (2026-08-18): build capgen-v1's real model (option B),
    not the existing `ccpp_handle`/`num_instances` mechanism (option A).** Re-examined
    option A before deciding: no example anywhere declares a ccpp-handle host var, and
    `ccpp_handle` resolves to `None` on every real build today -- it was never wired into
    a compiled/ctest-run example, only exercised at the unit/filecheck level (see the
    "Stage 1 done" note below for the corrected record of exactly what coverage it had).
    Removing option A is part of this task's scope, not a separate cleanup to schedule
    later: the rationale is "two structurally different multi-instance mechanisms is more
    than we want to maintain, and capgen-v1's model is the one that matches upstream,"
    not that option A was unused.
    - **What building option B actually requires**, narrowed down from the general
      architecture question to concrete engineering: `instance`/`ninstances`
      (`instance_number`/`number_of_instances`) as ordinary host-matched scalar args
      already works today with no changes -- confirmed by the 2026-07-30 port, cap
      generation for plain `instances` already threads `instance` correctly into every
      scheme call. The real, and only, generator gap is DDT-member resolution
      (`cap_shared.py`'s `_build_ddt_resolution_maps`/`_resolve_ddt_access_path`): it only
      knows how to resolve a member access to one statically-known Fortran symbol, so a
      HOST-owned array-of-DDT indexed by a runtime scalar (`instance_data(instance)%member`,
      dimensioned `number_of_instances`) silently falls back to flat Block-arg treatment
      instead of erroring or resolving correctly. Needs a new access-pattern case: recognize
      a HOST-owned array-of-DDT dimensioned by `number_of_instances`, and when resolving one
      of its members inside a call whose signature already carries an
      `instance_number`-standard-name arg, emit the `arr(instance)%member` subscript instead
      of resolving to a single symbol -- without disturbing the existing single-instance
      DDT-resolution path every other example relies on.
    - **Deliberately out of scope for now, sequencing decision, not a design question:**
      (a) whether this shares the missing "suite-data-module construction pass" concept
      that would also help the chained-interstitial ordering bug (separate Index entry) --
      not folding that in here; (b) `instances_advection`'s hard `memref.copy` verifier
      crash above -- get plain `instances` working end-to-end first, don't debug the
      constituents+multi-instance combination before the simpler mechanism is solid.
    - **Stage 1 done (2026-08-18): removed option A (`ccpp_handle`/`num_instances`)
      entirely.** Turned out bigger than "mechanical" once traced -- it wasn't an
      isolated add-on, it was woven into `run_dispatch.py`'s and `lifecycle_cap.py`'s
      shared block-signature/dispatch-chain/inout-echo machinery via a 3-way
      `if ccpp_info_type / elif ccpp_t_type / else` pattern at ~10 distinct sites,
      collapsed to a clean 2-way `if ccpp_info_type / else` everywhere (`ccpp_info_t`
      -- the real, distinct capgen-v1 mechanism -- untouched throughout). Also
      **corrected a wrong claim from the design-conversation scoping**: option A is
      not "dead code with zero exercised paths" -- `tests/unit/test_ccpp_t_threading.py`
      (12 tests) and `tests/filecheck/examples/end_to_end/helloworld-ccpp-t.mlir` were
      real and passing; that finding was made while investigating the scratchpad
      during the environment corruption described in the recovery note above, before
      it was known to be corrupted, and a stale/missing `.pyc`-only file was mistaken
      for a deleted one. Confirmed with the user before deleting anything anyway --
      the removal rationale shifted from "it's dead" to "two structurally different
      multi-instance mechanisms is more than we want to maintain, and capgen-v1's
      model is the one that matches upstream," not withdrawn.
      - **Removed:** `CcppHandleOp` (dialects/ccpp.py, class + dialect registration);
        its emission in `host_var_match_pass.py`'s `_build_model_var_index`; the
        `--num-instances` CLI flag and `ccpp.num_instances` IR attribute embedding
        in `ccpp_xml.py`; all `ccpp_handle`/`num_instances`/`ccpp_t_type`/
        `ccpp_data_block_arg`/`ccpp_t_var_name` plumbing in `suite_cap.py`,
        `ccpp_cap.py`, `lifecycle_cap.py`, `run_dispatch.py`; `CCPP_T_TYPE`,
        `CCPP_T_INSTANCE_STD_NAME`, `CCPP_NUM_INSTANCES` from `ccpp_conventions.py`
        (including removing `CCPP_T_INSTANCE_STD_NAME` from
        `CCPP_FRAMEWORK_STD_NAMES`); `tests/unit/test_ccpp_t_threading.py` (whole
        file); `TestCcppHandleRecognition` + its `_get_ccpp_handle` helper from
        `tests/unit/test_host_var_match.py`; `examples/helloworld/
        hello_world_host_ccpp_t.meta` and its `helloworld-ccpp-t.mlir` golden.
      - **Verified:** full suite green, 0 failures both before and after -- the only
        change in the total is exactly the 18 deleted tests (12 from
        `test_ccpp_t_threading.py` + 5 from `TestCcppHandleRecognition` + 1 filecheck
        golden), confirmed by diffing the pass count across the removal. (Absolute
        pass/skip counts aren't recorded here on purpose -- they shift for unrelated
        environment reasons, e.g. whether `fparser` is installed in the venv used for
        the run, and would go stale; see `git log`/CI for the actual current totals.)
        Regenerated `examples/helloworld` (both schemes, `hello_scheme` +
        `temp_adjust`, matching its real `CMakeLists.txt` invocation) and
        `examples/capgen` directly through the full pipeline: both succeed, and
        `grep` for `ccpp_t`/`ccpp_data`/`ccpp_handle` in the generated Fortran
        returns nothing.
      - **Stage 2 done (2026-08-18): `_build_ddt_resolution_maps`/`_resolve_ddt_access_path`
        now carry array-dimension info, with zero consumers yet -- pure plumbing, no
        behavior change.** `ddt_instance_map`'s per-type value grew a 3rd element,
        `instance_array_dim_std_name`: `None` for the ordinary scalar-instance case
        every ported example uses today, or the instance var's own first `dim_names`
        entry (e.g. `"number_of_instances"`) when it's array-dimensioned -- extracted
        straight off the existing `dimensions`/`dim_names` descriptor attributes
        (`ccpp_descriptors.py`'s `CCPPArgument`), no new metadata vocabulary needed.
        `_resolve_ddt_access_path` grew a matching 4th return element, propagated
        unchanged through nested-member recursion (it describes the base instance's
        own array-ness, independent of how many `%member`s get prepended to reach a
        leaf). Only the top-level module/host-level instance is covered -- a DDT
        member that's itself an array of a nested DDT type is out of scope, no real
        capgen-v1 example needs that shape.
        - **All 5 call sites of `_resolve_ddt_access_path`** (`run_dispatch.py`,
          `lifecycle_cap.py`, `suite_cap.py`'s `--emit-resolved-vars` path,
          `cap_shared.py`'s own recursive self-call and `_resolve_host_var_key`)
          updated to unpack the new 4-tuple; every site except `run_dispatch.py`'s
          (the one Stage 3 will actually change) discards the new value for now.
        - **Test fixtures fixed, not just production code**: two test files
          (`test_run_dispatch.py`, `test_run_dispatch_host_wrapper_resolution.py`)
          hand-construct `ddt_instance_map`/`_resolve_ddt_access_path` results as
          literal tuples rather than via the real builder -- all updated to the new
          shape, plus two new tests added (`test_array_instance_dim_reported_at_direct_level`,
          `test_array_instance_dim_propagates_through_nesting`) and a third
          (`test_ddt_instance_map_captures_array_instance_dim`) exercising the real
          extraction logic in `_build_ddt_resolution_maps` itself against a
          HOST-table array-of-DDT var shaped like `instances/data.meta`'s
          `instance_data` -- none of the pre-existing tests actually declared an
          array-dimensioned DDT instance, so this was previously untested even at
          the level `_resolve_ddt_access_path`'s own hand-built-dict tests now cover.
        - **Verified:** full suite green, 0 failures, +3 tests over pre-Stage-2 (2
          new `_resolve_ddt_access_path` tests + 1 new `_build_ddt_resolution_maps`
          test). No filecheck golden needed updating -- since those check exact
          generated IR/Fortran text across every DDT-touching example (`capgen`,
          `ddthost`, `var_compat`'s nested DDTs, etc.), that's direct confirmation
          this stage changed zero generated output, as intended.
      - **Stage 3 done (2026-08-18): `run_dispatch.py` now recognizes the
        array-of-DDT-instance case and constructs the extended resolved-arg
        shape carrying the index -- IR-level change only, generated Fortran
        text unchanged (print_ftn.py doesn't read it yet -- Stage 4's job).**
        `CCPP_INSTANCE_NUMBER_STD_NAME = "instance_number"` added to
        `ccpp_conventions.py` (real capgen-v1's own standard name for the
        per-call model-instance index scalar). `ResolvedArgOp` (dialects/ccpp.py)
        gained an optional `index_std_name` property, valid only for
        `DdtMember` -- deliberately a *standard name*, not a resolved local
        Fortran reference, since the local name isn't knowable yet at the
        point `_build_per_suite_run_info` runs (it depends on
        `non_host_std_to_canonical`, built later in a separate function).
        `HostVarRefOp` (dialects/ccpp_utils.py) gained a matching optional
        `index_expr` attribute (this one *is* the final resolved local
        Fortran name, since by the time `_build_run_dispatch_chain`
        constructs it, `non_host_std_to_canonical`/`block_arg_map` are both
        available) -- its docstring explicitly flags that the printer
        doesn't consume it yet.
        - **`_build_per_suite_run_info`'s DDT branch**: when
          `_resolve_ddt_access_path`'s 4th value (Stage 2) is not `None`,
          searches this same call's own `callee_input_names` for a sibling
          arg whose standard_name is `instance_number`; if found, builds
          `ResolvedArgOp(..., DdtMember, ..., index_std_name=...)` instead of
          the existing unconditional "instance lives in a HOST-type table ->
          Block" rule. If no sibling instance-number arg is present in this
          specific call, falls through to the *exact* prior behavior --
          real, tested guard, not just documented intent (see
          `test_no_sibling_instance_arg_falls_back_to_block`).
        - **`_build_run_dispatch_chain`'s `HostVarRefOp` construction site**:
          when `index_std_name` is set, resolves it via
          `non_host_std_to_canonical`/`block_arg_map` (the same mechanism
          already used for `col_start`/`col_end`) to the real local Fortran
          name, passed through as `index_expr`.
        - **Verified two ways.** Unit-level: 7 new tests (`ResolvedArgOp`
          construction + verify() rules for `index_std_name` across all 4
          source kinds; `_build_per_suite_run_info`'s positive case and its
          negative/guard case, shaped like `examples/instances/data.meta`'s
          real `instance_data` + `unit_conv_scheme_1`). Real-example,
          IR-level: regenerated `examples/instances` up through
          `generate-ccpp-cap` with `-t mlir` (not `-t ftn`, since the printer
          doesn't consume the new field yet) and confirmed
          `"ccpp_utils.host_var_ref"() <{var_name = "instance_data", ...}>
          {member_name = "data_array(:, 2)", index_expr = "instance"}` --
          the exact intended shape -- appears for all three `instance_data`
          members. Confirmed real Fortran generation for `examples/instances`
          is unaffected (still prints `instance_data%data_array(:, 2)`, no
          subscript, exactly as before) and every other example's full
          suite run is unaffected: 584 passed, 0 failures, +7 over
          pre-Stage-3 (exactly the new tests), no filecheck golden changed.
      - **Stage 4 done (2026-08-18): `print_ftn.py` now actually prints
        `HostVarRefOp.index_expr` -- `examples/instances`' real generated
        Fortran finally shows `instance_data(instance)%data_array2(lb:ub)`
        instead of the un-indexed `instance_data%data_array2(lb:ub)`.**
        The `CCPPHostVarRefOp` printer case now builds a `base_name` of
        `var_name(index_expr)` when `index_expr` is set (else plain
        `var_name`, unchanged), then appends `%member_name` as before.
        - **Found and fixed a real, previously-latent bug in the same
          printer file while verifying against the real example, not a
          synthetic case: `CCPPArraySectionOp`'s merge logic.** `data_array`/
          `data_array_opt` (whose own declared subscript is a fixed
          species index, e.g. `data_array(:, 2)`) printed correctly on the
          first try, but `data_array2` (a genuine 1-D
          `horizontal_dimension`-dimensioned member that the *existing*
          lb:ub column-chunking fallback wraps in an `ArraySectionOp`)
          printed as bare `instance_data(instance)` -- **the `%data_array2`
          member vanished entirely.** Root cause: the merge-existing-
          subscript logic located "the subscript to merge into" via
          `source_name.find("(")` -- the *first* `(` in the whole string.
          Once `HostVarRefOp` could also prepend an index_expr paren before
          the member, that first `(` became the instance index, not the
          member's own subscript; the merge logic treated `"instance"` as
          an existing placeholder token, discarded everything after its
          matching `)` (the real `%member` access), and rebuilt just
          `instance_data(instance)`. This is exactly the kind of arity/
          identity mismatch this session has hit before in unrelated
          contexts (wrong dummy-argument binding, not just a cosmetic
          miss) -- would have shipped silently, since no existing
          filecheck golden exercises an array-of-DDT member that also
          needs column-chunking. Fixed by searching for the member's own
          `(` only after the last `%`, which is a no-op when there's no
          `%` at all (the ordinary non-DDT-member array case) and correctly
          skips the instance-index paren when both are present.
        - **New dedicated regression test**
          (`tests/unit/test_run_dispatch_multi_instance_array_section.py`,
          shaped like `examples/instances/data.meta`'s real
          `instance_data`/`data_array2`, driven through the same
          `ArgOwnershipPass`→`SuiteCAP`→`CCPPCAP`→`print_to_ftn` in-process
          pipeline `test_run_dispatch_inout_echo.py`/
          `test_run_dispatch_col_bounds_fallback.py` already established
          for this class of printer bug) -- confirmed to actually catch the
          regression by temporarily reverting the fix and re-running (both
          new tests failed, as expected) before restoring it.
        - **Verified on the real example directly**: `examples/instances`
          now regenerates `instance_data(instance)%data_array(:, 2)`,
          `instance_data(instance)%data_array2(lb:ub)`, and
          `instance_data(instance)%data_array(:, 1)` -- exactly real
          capgen-v1's own shape, all three members, both the fixed-index
          and column-chunked cases. Full suite: 586 passed, 0 failures, +2
          over pre-Stage-4 (the new regression test), no filecheck golden
          changed (no existing example combines an array-of-DDT instance
          with a column-chunked member, so nothing else was ever exercising
          either the new index_expr path or the latent ArraySectionOp bug).
      - **Stage 5 done (2026-08-18): `examples/instances` wired into the real
        build, driver adapted, all 5 stages of this backlog entry now
        complete.**
        - **Driver (`main.F90`) adapted from real capgen-v1's own upstream
          driver**, keeping the loop-over-instances structure (the actual
          mechanism under test) unchanged, but dropping two things xdsl-ccpp
          doesn't generate: (1) the `ccpp_physics_init`/`ccpp_physics_final`
          calls -- confirmed by inspecting the real generated
          `test_host_ccpp_cap.F90` that xdsl-ccpp's `ccpp_init`/`ccpp_final`
          already do this work (they call the suite's own
          `_initialize`/`_finalize`), since xdsl-ccpp's lifecycle is still
          6-phase where real capgen-v1 splits further into 8 (the "Full
          6-phase to 8-phase lifecycle match" backlog entry, still open --
          this is exactly that gap, already tracked, not fixed here); (2)
          `group_name`/`thread_num`/`nthreads`/`nphys_threads` keyword args
          the generated signatures don't accept at all (confirmed via the
          real signatures, e.g. `ccpp_physics_run(suite_name, suite_part,
          lb, ub, instance, errmsg, errflg)` -- no thread-count params
          exist), replacing `group_name='all'` with the real
          `suite_part='unit_conv_group'` (the suite's actual group name,
          from `suite_unit_conv_suite.xml`). Both adaptations match
          `examples/opt_arg`'s own driver exactly -- same root cause, same
          fix shape, already precedented.
        - **`examples/instances/CMakeLists.txt`**: added the
          `if(XDSL_CCPP_HAVE_FORTRAN)` executable-build block
          (`INSTANCES_TESTLIB` + `instances.exe` + `ctest_instances`),
          mirroring `examples/opt_arg`/`examples/chunked_data`'s identical
          structure exactly. Refreshed the file's own header comment, which
          was still describing the pre-Stages-1-4 state (mechanism not
          implemented, cap generation producing silently-wrong output).
        - **Root `CMakeLists.txt`**: added `add_subdirectory(examples/instances)`;
          refreshed the stale "NOT wired in yet" comment block that used to
          cover both `instances` and `instances_advection` -- now only
          `instances_advection` remains excluded (separate, unrelated
          `memref.copy` crash, deliberately still deferred).
        - **`.github/workflows/compile-tests-cmake.yml`**: added the
          `instances` / `instances.exe` matrix entry, matching every other
          example's own entry shape. No `ctest_filter` needed (no other
          wired-in test name collides with the substring "instances" --
          `instances_advection` isn't wired in).
        - **Verified**: full CMake configure (not build -- no Fortran
          compiler on this laptop, matching every other example's own
          caveat throughout this repo) succeeds end to end for the whole
          repo with `examples/instances` included, through the real
          `xdsl_ccpp_capgen()` macro path (not a manual CLI invocation) --
          confirmed the generated Fortran via that path is byte-identical
          to the manual Stage 3/4 verification
          (`instance_data(instance)%data_array(:, 2)`,
          `instance_data(instance)%data_array2(lb:ub)`,
          `instance_data(instance)%data_array(:, 1)`, all three members
          correct). Python suite unaffected (586 passed, 0 failures --
          these changes are CMake/Fortran-only). **Not yet compile/run-
          verified** -- CI is the first real check, same limitation every
          other example ported this way already has.
        - **`examples/instances_advection` stays explicitly out of scope**
          until plain `instances` is proven in CI -- separate, unrelated
          `memref.copy` verifier crash to diagnose on its own first.
        - **Real gfortran CI build failure found and fixed after the above
          (2026-08-18): `active = <expr>` property resolution never handled
          a DDT-member reference at all -- a genuine pre-existing gap, not
          introduced by any of the 5 stages, just never exercised until
          `examples/instances`'s own `data_array_opt` (`active =
          (flag_for_opt_array)`, `flag_for_opt_array` a member of the
          `instance_type` DDT).** CI error: `Symbol 'flag_for_opt_array' at
          (1) has no IMPLICIT type` in the generated `unit_conv_suite_cap.F90`.
          `suite_cap.py`'s `_resolve_active_condition` (added for `opt_arg`'s
          own dead-`active` fix, task #2) only ever resolved a MODULE-type
          or 'state'-classified HOST-type standard-name reference to its
          real local name -- a DDT-member reference fell through to the
          "assume it's a Fortran keyword/operator, print verbatim" default,
          producing the bare, undeclared standard-name text.
          **This was never actually correct** -- it only ever "worked" for
          `examples/opt_arg`'s own `flag_for_opt_arg` because that example's
          local variable name happens to be spelled identically to its
          standard name, so printing the raw standard-name text verbatim
          happened to compile by pure coincidence.
          - **Fixed** by adding a new `_active_expr_ddt_member_indexes`
            helper (standard_name -> (member_local_name, ddt_type_name) over
            every DDT table) and extending `_resolve_active_condition` to
            resolve a DDT-member token via the same `_resolve_ddt_access_path`
            machinery `run_dispatch.py`'s own DDT-member resolution already
            uses -- including the array-of-DDT-instance case Stages 2-4
            built: when the DDT's module-level instance is itself a
            HOST-owned array (`instance_array_dim` set), the calling
            scheme's own `arg_table` (now threaded into
            `_resolve_active_condition`) is searched for a sibling
            `instance_number`-standard-name arg to index by, raising a
            clear error (matching the existing `dispatch_scalar` case's own
            philosophy) if there isn't one, rather than silently emitting
            an unindexed (and therefore wrong) reference.
          - **New regression test**
            (`tests/unit/test_active_condition_ddt_member.py`, shaped like
            the real `examples/instances` case) -- confirmed to actually
            catch the bug by stashing the fix and re-running (all 3 new
            tests failed, as expected) before restoring it.
          - **Verified**: full suite 589 passed (586 + 3 new), 0 failures.
            Regenerated `examples/instances` directly and via the real
            `xdsl_ccpp_capgen()` CMake macro path -- both now print
            `if ((instance_data(instance)%opt_array_flag)) then`, a real,
            valid Fortran reference, with exactly one `use data, only:
            instance_data` stub, no duplicates.
      - **Post-Stage-5 fix #2 (2026-08-18) — shared-scalar `ccpp_suite_state`
        broke multi-instance lifecycle ordering, caught by the real
        `ctest_instances` run.** CI error:
        ```
        An error occurred in ccpp_init:
        Invalid initial CCPP state, 'initialized' in unit_conv_suite_initialize
        instance: 2
        ```
        Root cause: `ccpp_suite_state` was (and, before this codebase's own
        multi-instance work, always had been) a single module-scope
        *scalar*. Once two model instances round-tripped through
        register/init independently, instance 2's `_initialize` call saw
        instance 1's own already-`'initialized'` value and errored --
        exactly the collision real capgen-v1's own array-per-instance model
        exists to avoid. Confirmed against
        `ccpp-framework-fresh/capgen/generator/suite_cap.py`: real capgen-v1
        makes `ccpp_suite_state` an **allocatable integer array** indexed by
        instance number, with dedicated `<suite>_suite_state_alloc`/
        `_dealloc` subroutines and integer-enum states (`CCPP_SUITE_
        UNREGISTERED`/`_REGISTERED`/`_FRAMEWORK_INITIALIZED`) -- a materially
        bigger, cross-cutting redesign than this bug needs (this codebase's
        existing 3-string-literal-state model, `'uninitialized'`/
        `'initialized'`/`'in_time_step'`, is a pre-existing, orthogonal gap
        from real capgen-v1's own 4-state model, tracked separately, not
        part of this fix).
        - **Two design forks surfaced and resolved with the user before
          implementing, per this backlog's own established practice for
          genuinely architectural (not just mechanical) gaps:**
          1. *Narrow fix (index the existing 3-state scalar per-instance)
             vs. full capgen-v1 match (integer enums + alloc/dealloc API).*
             User chose the **narrow fix** after asking how big the full
             match would be (answered: cross-cutting, touches the state
             *representation* everywhere, not just this bug -- better
             sequenced after task #28's 6-to-8-phase lifecycle match, not
             before).
          2. *Thread `instance`/`number_of_instances` through every
             lifecycle phase (matches capgen-v1 exactly) vs. have each
             phase operate on all instances at once.* User chose **thread
             through every phase**, discovered mid-implementation once it
             became clear the narrow fix alone couldn't avoid the
             collision without some way to know which instance a given
             register/init/finalize/timestep call is for.
        - **Fixed, in `suite_cap.py` unless noted:**
          - `generateStateCheckOps`/`generateStateAssignment` gained an
            `instance_local_name` parameter; when set, they tag their
            `ccpp_suite_state` `llvm.AddressOfOp`s with the (Stage 1-era,
            previously-orphaned) `ccpp_instance_ref` attribute --
            `print_ftn.py`'s `AddressOfOp` case already had a consumer for
            this attribute left over from the old, removed `ccpp_handle`
            mechanism; repurposed to print a plain `name(instance_var)`
            subscript instead of the old `%ccpp_instance` derived-type
            member access.
          - `_build_state_globals` declares `ccpp_suite_state` allocatable/
            deferred-shape (`character(len=16), allocatable, dimension(:)`)
            whenever the host declares `instance_number` at all --
            `number_of_instances` is itself a genuine runtime HOST scalar,
            never a compile-time constant, so a fixed-size array is not an
            option.
          - New `_build_suite_state_lazy_alloc` reuses the existing
            `ccpp_utils.LazyAllocOp` idiom (already used for suite-owned/
            framework arrays: `if (.not. allocated(x)) then allocate(...);
            x = init; end if`) to allocate + initialize `ccpp_suite_state`
            on first use, sized by `number_of_instances`. Wired into
            `generateSubroutineCall` for every phase that actually touches
            state (every non-run lifecycle phase except `_register`, which
            never checks/assigns state at all, plus each physics group's
            `_run`).
          - New `_synthesize_instance_number_arg`/
            `_synthesize_number_of_instances_arg` (mirroring the existing
            `_synthesize_dynamic_loop_count_args` precedent), called
            unconditionally from `_build_arg_tables` for every lifecycle
            phase: whenever the host declares `instance_number`/
            `number_of_instances` and no scheme's own entry point for this
            phase already provides one, synthesize a fresh `HostMatched`
            dummy argument for it. A no-op for non-multi-instance suites.
          - **A second layer of plumbing, discovered only once the above
            was regenerated and inspected**: the *outer* dispatcher
            wrappers (`ccpp_cap.py`'s `ccpp_register`/`ccpp_init`/
            `ccpp_final`/`ccpp_physics_timestep_init`/
            `ccpp_physics_timestep_final`, built by `lifecycle_cap.py`)
            don't automatically forward a newly-synthesized suite-callee
            arg -- `lifecycle_cap.py`'s own pre-scan only exposes a
            passthrough dummy arg for a bare name some *scheme's own*
            entry-point metadata declares for that specific phase, which
            `instance`/`ninstances` never are (only `_run` ever declares
            `instance_number`, and no scheme ever declares
            `number_of_instances` at all). Without a fix, these two args
            would have silently fallen to the wrapper's generic "no host
            match" branch -- a fresh, always-zero local `alloca` -- a
            silent-wrong-value bug, not a compile error. Fixed by adding an
            inverted (local-name -> standard_name) fallback lookup over
            `host_var_map_all`, mirroring `run_dispatch.py`'s own already-
            generic HOST/MODULE/DDT table name-matching fallback for the
            identical problem on the `_run`/`ccpp_physics_run` side (which
            needed no changes at all -- it already handled this case
            generically).
          - `examples/instances/main.F90` re-adapted to pass
            `instance=ins, number_of_instances=ninstances` into all six
            lifecycle/run calls (dropped in Stage 5 since those signatures
            didn't accept them yet).
        - **New regression test** (`tests/unit/test_multi_instance_suite_state.py`,
          5 cases) covering: `ccpp_suite_state` declared allocatable (not the
          old fixed scalar), lazily allocated + sized by `number_of_instances`,
          check/assignment indexed by `instance`, and every non-run lifecycle
          wrapper (including `ccpp_register`, which never itself
          checks/assigns state) correctly forwarding `instance`/`ninstances`
          as real passthrough dummy args rather than a fresh local. Confirmed
          to actually catch the regression by stashing the fix and
          re-running (all 5 new tests failed, as expected) before restoring it.
        - **Verified**: full suite 594 passed (589 + 5 new), 0 failures.
          Regenerated `examples/instances` directly and via the real
          `xdsl_ccpp_capgen()` CMake macro path -- `unit_conv_suite_cap.F90`
          now declares `character(len=16), allocatable, dimension(:) ::
          ccpp_suite_state`, lazily allocates it
          (`allocate(ccpp_suite_state(ninstances))`), and every state
          check/assignment indexes it by `instance`
          (`ccpp_suite_state(instance)`); `test_host_ccpp_cap.F90`'s
          `ccpp_register`/`ccpp_init`/`ccpp_final`/
          `ccpp_physics_timestep_init`/`ccpp_physics_timestep_final` all now
          accept `(suite_name, instance, ninstances, errmsg, errflg)` and
          forward `instance, ninstances` straight into the suite callee
          (not a local alloca). Real `ctest_instances` execution itself
          still can't be verified locally (no Fortran compiler on this
          laptop) -- left for the next CI run to confirm end-to-end.
      - **`instances_advection` re-investigated (2026-08-18, task #35) now that
        `instances` is CI-green — the originally-tracked crash is gone, but
        exposed a much bigger, previously-invisible gap.**
        - **The tracked `memref.copy` verifier crash no longer reproduces.**
          Confirmed by regenerating via the exact real CMake macro invocation
          (temporarily `add_subdirectory`'d, then reverted) on the current
          tip: cap generation succeeds cleanly, `ccpp_suite_state` is
          correctly allocatable and instance-indexed (this example also
          declares `instance_number`/`number_of_instances`, so it picked up
          the same fix `instances` did), and the constituent-registration
          code that used to crash now looks structurally sound. Most likely
          fixed as an incidental side effect of PR #76 (the 5-stage
          multi-instance migration + `ccpp_suite_state` fix), not by anything
          targeted at this bug -- never re-tested until now.
        - **But `main.F90` still can't build, for two different reasons:**
          1. **Mechanical** (same category `instances`/`opt_arg` already
             needed): calls `ccpp_physics_init`/`ccpp_physics_final` (this
             codebase's lifecycle is still 6-phase, not real capgen-v1's
             8-phase split -- task #28) and passes `group_name`/`thread_num`/
             `nthreads`/`nphys_threads`/`errcode` kwargs the generated
             signatures don't have (`errflg`, not `errcode`, etc.). Not yet
             fixed -- straightforward once the bigger item below is
             resolved, no point adapting the driver against an API that's
             about to change shape.
          2. **Architectural, genuinely new — the constituent-registration
             API (`constituent_cap.py`) has zero instance-awareness.**
             Confirmed by reading the whole file: `register_constituents`/
             `deallocate_dynamic_constituents`/`initialize_constituents`/
             `const_get_index`/`number_constituents`/`constituents_array`/
             `is_scheme_constituent`/`model_const_properties` all operate on
             a single shared set of module-level arrays (`lc_all_constituents`,
             `lc_constituent_array`, `lc_const_tend`, `lc_const_props`, each
             scheme's own `lc_<dyn_const_name>`, plus any scratch vars) --
             no `instance` parameter anywhere, no per-instance dimension on
             any of them. But `main.F90` calls every one of these with
             `instance=`/`ninstances=` (`ccpp_register_constituents(...,
             instance=ins, ninstances=ninstances)`,
             `ccpp_deallocate_dynamic_constituents(instance=ins)`,
             `ccpp_constituents_array(ins)` as a function *argument*, not
             today's zero-arg function) -- real capgen-v1 clearly gives each
             model instance its own constituent storage; this codebase has
             no equivalent concept at all.
          - Also touches `cap_shared.py`'s `FRAMEWORK_STD_NAME_TO_CAP_VAR`
            (`"ccpp_constituents" -> "lc_constituent_array"`,
            `"ccpp_constituent_tendencies" -> "lc_const_tend"`,
            `"number_of_ccpp_constituents" -> "size(lc_all_constituents)"` --
            plain hardcoded Fortran-text values) and its consumer in
            `suite_cap.py`'s `_build_framework_refs`/run-phase resolution:
            `instances_advection`'s own `apply_constituent_tendencies_run`
            consumes `ccpp_constituents`/`ccpp_constituent_tendencies`
            directly as `_run` args through exactly this path, so once the
            underlying arrays are per-instance, this resolution needs to
            know to index by `instance` too.
        - **Design sketch for the fix (scoped 2026-08-18, not yet
          implemented -- user explicitly asked to scope this before
          committing to implementation, given the size):**
          - The whole subsystem generates raw Fortran text directly
            (`ConstituentApiOp`'s body is a plain `StringAttr` -- no
            structured IR/dialect ops for the array accesses the way
            `suite_cap.py`'s own fix used), which is actually good news: no
            new dialect machinery needed, "just" a text-generation and
            signature change, mirroring the shape of the `ccpp_suite_state`
            fix rather than anything harder.
          - Introduce one new module-scope derived type (e.g.
            `<host>_lc_constituent_instance_t`) bundling every existing
            `lc_*` module var as a member (one per dynamic-array name, plus
            `all_constituents`/`constituent_array`/`const_tend`/
            `const_props`/any scratch vars) -- exactly the same
            "array-of-DDT-instance" shape `examples/instances`' own
            `instance_data` already establishes as this codebase's
            multi-instance storage idiom, just cap-owned/generated instead
            of host-declared. One module var, `lc_instances(:)`, allocatable,
            lazily allocated + sized by `number_of_instances` on first use
            -- reusing the exact `LazyAllocOp`-style guarded-allocate idiom
            `_build_suite_state_lazy_alloc` already established for
            `ccpp_suite_state`.
          - Every constituent-API subroutine gains an `instance` (and, where
            it allocates `lc_instances` itself, `ninstances`) dummy
            argument; every internal `lc_foo` reference becomes
            `lc_instances(instance)%foo`.
          - `FRAMEWORK_STD_NAME_TO_CAP_VAR`'s resolution in `suite_cap.py`
            needs to append `(instance)` indexing when the suite is
            multi-instance, mirroring how `generateStateCheckOps`/
            `generateStateAssignment` learned to do the same for
            `ccpp_suite_state`.
          - All of the above gated on the same check already established
            for the suite-state fix (`self._resolve_host_only_std_name(
            CCPP_INSTANCE_NUMBER_STD_NAME) is not None`, evaluated once per
            host since `_generate_constituent_api` is called once for the
            whole cap module, not per-suite) -- every existing
            non-multi-instance constituent-using example (`advection`,
            `constituents_dim`, `capgen`, `ddthost`, ...) must keep today's
            flat-scalar-module-var output byte-for-byte identical.
          - `main.F90`'s mechanical adaptation (item 1 above) still needed
            on top, once the API's real shape is settled.
        - **RESOLVED (2026-08-18) — implemented exactly against the sketch
          above, plus one thing the sketch didn't anticipate.**
          - **`xdsl_ccpp/dialects/ccpp_utils.py`**: `ConstituentApiOp`
            gained an optional `type_defs` property -- a derived-type
            definition that must print in the module's *specification*
            part (before `CONTAINS`), never inside it. Nothing before this
            fix ever needed to emit a derived-type *definition* (as
            opposed to a variable of an already-existing type) from this
            codebase's own generator, only host-declared ones.
          - **`xdsl_ccpp/backend/print_ftn.py`**: emits `type_defs`
            *before* the `CCPPModuleVarOp` preamble loop, not after --
            **the one thing the sketch missed, and a real bug caught by
            actually regenerating and reading the output**: Fortran
            requires a type be defined before any variable of that type is
            declared in the same specification part; printing `lc_instances`
            first produced `has no IMPLICIT type` on its own type name.
          - **`xdsl_ccpp/transforms/constituent_cap.py`**: `_generate_constituent_api`
            gained `instance_local_name`/`ninstances_local_name` params
            (both `None` by default, i.e. the non-multi-instance path is
            untouched). When set: emits `type :: <camel_name>_lc_instance_t`
            bundling every existing `lc_*` array (one member per
            dynamic-array name, plus `all_constituents`/
            `constituent_array`/`const_tend`/`const_props`/scratch vars,
            preserving each one's own `target`/`pointer` attributes) and a
            single `lc_instances(:)` module var; every one of the 8
            constituent-API subroutines gained an `instance` dummy arg and
            has every internal `lc_foo` reference rewritten to
            `lc_instances(instance)%foo`. `register_constituents` alone
            also gained `ninstances` and does the guarded lazy-allocate
            (`if (.not. allocated(lc_instances)) then allocate(lc_instances
            (ninstances)); end if`) -- discovered while implementing that
            only `register_constituents` ever receives `ninstances` from
            the driver at all (matches real capgen-v1's own driver:
            `ccpp_initialize_constituents`/`const_get_index`/
            `number_constituents`/`deallocate_dynamic_constituents` never
            get it), so every other subroutine's precondition check became
            "is `lc_instances` allocated at all" first, THEN "is this
            instance's own array allocated" -- two sequential guards, not
            one, since indexing an unallocated outer array is illegal
            Fortran regardless of the inner component's own allocation
            state.
          - **`xdsl_ccpp/transforms/ccpp_cap.py`**: `_generate_ccpp_cap_module`
            resolves `instance_local_name`/`ninstances_local_name` once per
            host (via `_build_host_var_map(meta_data, include_host=True)`,
            the same lookup shape `suite_cap.py`'s own
            `_resolve_host_only_std_name` uses) and threads them into both
            `_generate_constituent_api` and a new `instance_local_name`
            param on `_build_cap_var_map`. That second thread matters
            because `FRAMEWORK_STD_NAME_TO_CAP_VAR`'s resolution
            (`ccpp_constituents`→`lc_constituent_array`, etc., consumed
            verbatim by `run_dispatch.py` for a scheme's own `_run` args)
            and the CapScratch scratch-var branch (constituent-tendency
            vars like `cld_liq_tend`) both build their cap-var-map *value*
            in this one function -- wrapping it here, once, means
            `run_dispatch.py` needed zero changes (it just prints whatever
            text it's handed). Care taken to keep `framework_var_residency`
            (GPU-copyin bookkeeping) and `scratch_var_list` keyed by the
            *bare* name throughout, since `constituent_cap.py` applies its
            own identical wrapping when it consumes those -- wrapping both
            ends would have doubled the prefix.
          - **`examples/instances_advection/main.F90`** fully re-adapted
            (mirrors `examples/instances`' own Stage-5 adaptation):
            dropped `ccpp_physics_init`/`ccpp_physics_final` (this
            codebase's lifecycle is still 6-phase) and
            `group_name`/`thread_num`/`nthreads`/`nphys_threads`;
            `suite_part='physics'` in their place; `errcode` renamed to
            `errflg` throughout (the generated signatures never used
            `errcode`); constituent-API calls switched from upstream's
            bare `ccpp_register_constituents`-style names to the real
            generated `test_host_ccpp_register_constituents`-style names
            (matching `examples/constituents_dim`'s own driver
            convention -- xdsl-ccpp never aliases these to bare
            `ccpp_`-prefixed names the way lifecycle subroutines are).
          - **`examples/instances_advection/CMakeLists.txt`** rewritten
            following `examples/advection`'s own template for a
            constituent-using example (adds
            `ccpp_constituent_prop_mod.F90`/`ccpp_scheme_utils.F90` --
            `examples/shared/` at the time, moved to
            `xdsl_ccpp/framework_src/` as of task #75 -- to the TESTLIB, which
            `examples/instances`' own CMakeLists.txt didn't need since it
            has no constituents at all) plus `examples/instances`' own
            template for the `test_host.meta`-is-metadata-only host split.
            Root `CMakeLists.txt`: `add_subdirectory(examples/
            instances_advection)`. `.github/workflows/compile-tests-cmake.yml`:
            new matrix entry -- needed a `ctest_filter: "instances$"` on
            the *existing* `instances` entry (not the new one), since
            `instances` is a literal prefix of `instances_advection`'s own
            test name (`ctest_instances_advection`) and would otherwise
            also match and try to run an executable that entry's own job
            never built -- the exact collision class
            `advection`/`advection_flat_host` already needed the same fix
            for.
          - **New regression test**
            (`tests/unit/test_multi_instance_constituent_api.py`, 7 cases)
            covering: the bundle type printing before the variable that
            uses it, the old flat module-var declaration NOT surviving,
            `register_constituents`'s lazy-allocate, every subroutine
            gaining `instance`, the two-guard precondition check, and
            `FRAMEWORK_STD_NAME_TO_CAP_VAR`/scratch-var resolution both
            correctly instance-indexed inside `ccpp_physics_run`'s own
            dispatch. Confirmed to actually catch the regression by
            stashing the fix and re-running (all 7 new tests failed, as
            expected) before restoring it.
          - **Verified**: full suite 601 passed (594 + 7 new), 0 failures.
            Regenerated `examples/instances_advection` directly and via the
            real `xdsl_ccpp_capgen()` CMake macro path (both byte-identical)
            -- a full repo-wide `cmake -S . -B build` with
            `instances_advection` permanently wired in configures cleanly,
            zero errors, `ccpp_physics_run`'s own dispatch correctly prints
            `lc_instances(instance)%lc_constituent_array`/`lc_const_tend`/
            `lc_cld_liq_tend`. Real compilation/`ctest` execution still
            can't be verified locally (no Fortran compiler on this laptop)
            -- left for the next CI run.
          - **Real CI then found two more real bugs (2026-08-18), both
            fixed the same day -- exactly why this note keeps saying "left
            for the next CI run": there is no substitute for it on this
            laptop.**
            1. **Fortran forbids the `TARGET` attribute on a derived-type
               component** (`constituent_cap.py`'s first cut put it there
               directly, copying the plain-module-var version's own
               attribute list without checking it transfers) --
               `gfortran`: `"Attribute at (1) is not allowed in a TYPE
               definition"`, cascading into dozens of unrelated `"not a
               member of the structure"` errors for every other component
               once the type block's own parse got corrupted. **Fixed**:
               `target` moved to the containing `lc_instances(:)` variable
               itself -- Fortran's own attribute-propagation rule (`TARGET`
               on a variable propagates to every subobject, including
               allocatable components) makes every pointer association
               into it exactly as valid as before.
            2. **A genuine regression in the same code path, caught by the
               same build**: `cld_liq_register`'s own `dyn_const` output is
               referenced inside `ccpp_register` by a bare `lc_dyn_const`
               text that `lifecycle_cap.py`'s own dedicated `CapVarRefOp`
               branch for this exact arg shape emits *deliberately*,
               matching `constituent_cap.py`'s module-var naming
               convention on purpose (Fortran resolves the otherwise-
               undeclared identifier via ordinary same-module scoping --
               not a bug, and not the "discard" this was originally
               misdiagnosed as, see the corrected backlog entry below).
               Once `constituent_cap.py` moved that array into the new
               per-instance bundle, that branch kept emitting the bare,
               now-nonexistent name -- `gfortran`: `"Symbol 'lc_dyn_const'
               ... has no IMPLICIT type"`. **Fixed**: that branch now
               accepts `instance_local_name` and builds
               `lc_instances(<instance>)%lc_<bare>` when set,
               `lc_<bare>` unchanged otherwise -- confirmed
               `examples/advection`'s own (non-multi-instance) output is
               byte-identical before/after. New regression test
               (`TestSchemeLevelDynamicRegistrationOutputIsInstanceAware`
               in the same test file, using a fixture with a real
               `_register`-table `dyn_const` entry -- the original test
               fixture had none, which is exactly why it didn't catch
               this), confirmed via git-stash.
          - **Real CI then found a third bug, this time a metadata
            authoring mistake from the original 2026-07-30 port, not a
            generator bug**: `data.meta`'s own second table (`ncols`/
            `pver`/`dt`/`tfreeze`/`index_qv`/`phys_state`) was declared
            `type = host` even though `data.F90` genuinely is a compiled
            Fortran module (confirmed: `main.F90` already `use`s it
            directly) -- unlike `test_host.meta`'s own deliberately
            module-less host table (`instance`/`ninstances`/etc, no
            backing `.F90` at all). `examples/advection`'s own equivalent
            table (`test_host_mod.meta`) is correctly `type = module` for
            the identical situation. The practical effect: a DDT member's
            own named-array-slice subscript (`q(:,:,
            index_of_water_vapor_specific_humidity)`, resolved via
            `cap_shared.py`'s `_resolve_member_subscripts`, keyed against a
            MODULE-only host-var map) silently fell through to printing
            the bare, undeclared standard-name text whenever its resolving
            variable's own table was HOST- instead of MODULE-typed --
            `gfortran`: `"Symbol 'index_of_water_vapor_specific_humidity'
            ... has no IMPLICIT type"`. **Fixed**: `data.meta`'s second
            table changed to `type = module`. This one change also
            improved several OTHER call sites to match real capgen-v1's
            own convention far more closely than before: `ccpp_init`
            dropped `tfreeze` as an explicit call arg (now use-associated
            directly) and `ccpp_physics_run` dropped both `ncol` and
            `timestep` (now `ncol = ub - lb + 1`, matching the standard
            column-chunking idiom every other example already uses, and
            `timestep` is the use-associated `dt` directly) -- `main.F90`
            updated to match the new, shorter call signatures. Not a
            generator change at all; `xdsl_ccpp` behaved correctly once
            the metadata correctly described what `data.F90` actually is.
          - **Real ctest then found a fourth bug -- a genuine SEGFAULT,
            confirming the earlier assumption behind the dyn_const fix
            above ("only register_constituents ever needs ninstances, so
            only it needs to allocate lc_instances") was wrong for this
            specific case.** `ccpp_register`'s own call
            (`cld_suite_register(lc_instances(instance)%lc_dyn_const,
            ...)`) indexes straight into `lc_instances`, an OUTER array
            nothing has allocated yet -- the driver's own call order runs
            `ccpp_register` (the *lifecycle* register) before
            `test_host_ccpp_register_constituents` (the *constituent-API*
            register, where `lc_instances` is normally lazily allocated)
            ever gets a chance to run. Backtrace: `SIGSEGV` inside
            `cld_suite_register`, called from `MAIN__`. **Fixed**:
            `lifecycle_cap.py`'s own `CapVarRefOp` branch now also emits a
            guarded `LazyAllocOp` for `lc_instances` (sized by
            `ninstances`, which `ccpp_register`'s signature already
            carries from the earlier `_synthesize_number_of_instances_arg`
            work) immediately before the reference, emitted once per
            function even when multiple schemes each have their own
            dynamic-array output. New regression test
            (`test_ccpp_register_allocates_lc_instances_before_
            referencing_it`), confirmed via git-stash. Full suite 603
            passed (602 + 1 new), `examples/advection`'s own output
            confirmed unaffected.
          - **A separate, pre-existing, unrelated bug found while verifying
            this fix, explicitly out of scope for task #35, logged as its
            own new backlog item below ("Scheme-level dynamic constituent
            registration output discarded by `ccpp_register`'s own
            wrapper")**: `cld_liq_register`'s own `dyn_const` output (a
            scheme's own dynamically-registered constituent list) is
            passed into the suite call from a function-scoped local that
            `lifecycle_cap.py`'s generic "no host match" fallback hoists
            inside `ccpp_register` itself, then silently discarded the
            moment that subroutine returns -- confirmed this is **not**
            something this fix introduced by regenerating the
            already-CI-green `examples/advection` (which has the identical
            `cld_liq_register`/`cld_ice_register` scheme pair) and finding
            the exact same shape (`call cld_suite_register(lc_dyn_const,
            lc_dyn_const_ice, errmsg, errflg)`, both hoisted-and-discarded
            locals) already present there, unrelated to multi-instance.
          - **RESOLVED (2026-08-18) — Copilot review on PR #77 (3 comments) plus two
            self-found companion bugs of the same class, all fixed together.** Copilot
            flagged that `instance_local_name`/`ninstances_local_name` (resolved once in
            `ccpp_cap.py`'s `_generate_ccpp_cap_module`, threaded into `_build_cap_var_map`/
            `_generate_constituent_api`/`_generate_lifecycle_fn`) were being treated as two
            independent optionals rather than one paired contract — a host declaring only
            one of `instance_number`/`number_of_instances` (nothing in the `.meta` format
            stops this) could enable multi-instance wrapping with no matching allocation/
            signature support, e.g. a literal `"None"` spliced into generated Fortran, or a
            reference to `lc_instances` never allocated. Fixed at the single source
            (`ccpp_cap.py`: normalize to the pair, both set or both `None`) plus defensive
            asserts at the two downstream consumers (`constituent_cap.py`'s
            `_generate_constituent_api`, `lifecycle_cap.py`'s `_generate_lifecycle_fn`) —
            same "raise, don't silently mask" precedent as the Phase 7 Copilot-review fixes,
            with `cap_shared.py`'s `_assert_call_arg_count_matches_signature` as this
            codebase's own existing precedent for guarding a coupled-parameter invariant with
            an assert. While writing a regression test for this, found `suite_cap.py`'s own,
            separate `ccpp_suite_state` multi-instance gating (unrelated to what Copilot's
            review touched — a different subsystem, this suite's own allocation, not the
            constituent-API bundle) had the identical unpaired-gating flaw in three places:
            `_synthesize_instance_number_arg`/`_synthesize_number_of_instances_arg` (each
            gated purely on its own standard name) and `_build_state_globals` (gated
            `ccpp_suite_state`'s allocatable-array declaration on `instance_number` alone).
            Fixed by adding a shared `_is_multi_instance_host()` helper (true only when both
            names resolve) and gating all three on it. A **second, more subtle** companion
            bug surfaced while probing that fix: `generateSubroutineCall`'s own
            `instance_local_name` (fed to `generateStateCheckOps`/`generateStateAssignment`,
            which print `ccpp_suite_state(<instance_local_name>)`) can come from a *scheme's*
            own explicit `instance_number` arg declaration, not only from
            `_synthesize_instance_number_arg` — so it wasn't already guaranteed paired the
            way `_is_multi_instance_host`'s own callers are. With only `instance_number`
            declared, `_build_state_globals` correctly falls back to a plain scalar
            `ccpp_suite_state`, but this unpaired `instance_local_name` still indexed it as
            `ccpp_suite_state(instance)` — invalid Fortran against a scalar. Fixed by
            dropping `instance_local_name` back to `None` whenever
            `ninstances_local_name` is absent, right where both are resolved. Three new
            regression tests added to `tests/unit/test_multi_instance_constituent_api.py`
            (`TestPartialMultiInstanceMetadataStaysSingleInstance`), each confirmed via
            git-stash to fail without its corresponding fix. Full suite 606 passed, 1
            xfailed, no regressions. `examples/instances_advection` (a real, correctly-paired multi-instance host)
            regenerated via `python -m xdsl_ccpp.tools.ccpp_dsl` directly and confirmed
            byte-identical before/after all three fixes.
- **`opt_arg`'s dead `active` property — S/M.** `memory_space`'s silent-ignore sibling: `active`
  (a Fortran logical expression for conditional variable presence) is already a real
  `ArgumentOp` property (`ccpp.py`, `opt_prop_def(StringAttr)`) — parsed into IR, but zero passes
  ever read it. Likely reuses the existing `present()`-guard pattern already built for promoted
  optional args (Phase 1/2 of `test_optional_args.py`) rather than needing a new mechanism.
  Separately, S: add test coverage for optional args at `_timestep_init`/`_timestep_final` (not
  just `_run`) and optional+unit-conversion combined — likely already work today, just untested.
  - **Confirmed 2026-07-29/30 by actually porting the real example into `examples/opt_arg/`
    (`opt_arg_scheme`/`data.meta`/`suite_opt_arg_suite.xml`, `type=control`→`type=host`
    `test_host.meta` conversion, driver rewritten to xdsl-ccpp's per-host-prefixed calling
    convention) — the dead-`active` diagnosis above is correct: cap generation succeeds, but
    `opt_arg`/`opt_arg_2` are generated as unconditionally present regardless of
    `flag_for_opt_arg`'s value.
  - **A second, more severe, previously-undocumented bug found in the same generated output:**
    `test_host_ccpp_physics_timestep_initial`/`_timestep_final` declare **local, never-allocated**
    dummies (`lc_nx`, `lc_var(:)`, `lc_opt_var(:)`, `lc_opt_var_2(:)`) and pass those straight into
    the suite's own timestep subroutine, instead of `use`-associating the real host module's
    `nx`/`std_arg`/`opt_arg`/`opt_arg_2` the way `_register`/`_initialize`/`_run`/`_finalize`
    correctly do. Passing an unallocated allocatable as an `intent(in)`/`intent(inout)` array dummy
    is invalid at runtime regardless of the `active`-gating story above — this looks like a
    separate `HostVariableMatchPass` gap specific to the timestep-phase dispatch, not diagnosed
    further. Unconfirmed whether this actually crashes at runtime or a real Fortran compiler even
    accepts it at compile time — no compiler was available to check. `examples/opt_arg/
    CMakeLists.txt` exists, cap-generates successfully, and its `add_test` is left enabled (unlike
    `suite_allocate`'s equivalent caveat) since the executable at least links against the generated
    sources syntactically, but the directory is not `add_subdirectory`'d from the root
    `CMakeLists.txt` given these two confirmed bugs.
  - **RESOLVED (2026-08-13) — both bugs fixed, `add_subdirectory`'d into the root build.**
    - **Bug 1 (dead `active` property).** Root cause: no pass read `ArgumentOp.active` at all.
      Fixed by (a) `HostVariableMatchPass` now propagates a matched host/module var's own
      `active` expression onto the scheme arg as a new `model_var_active_expr` IRDL property
      (`ccpp.py`, mirroring the `model_var_is_host_table`/`model_var_is_protected` pattern from
      the `constituents_dim` Stage 7 work); (b) a new `ActiveCheckOp` IR op
      (`ccpp_utils.py`/`print_ftn.py`) prints `if (<condition_expr>) then ... else ... end if` —
      deliberately a *sibling* of the existing `PresentCheckOp`, not a generalization of it:
      `PresentCheckOp` tests Fortran's `present()` intrinsic for optional args inside a
      rank-reduction promotion loop, while `ActiveCheckOp` tests an arbitrary named host
      logical for the flat (non-promoted) case examples/opt_arg actually needs — different
      runtime questions, so kept as separate ops rather than risking the working promoted-arg
      path; (c) a new `suite_cap.py` method, `_build_active_gated_call_ops`, mirroring
      `_build_promoted_call_ops`'s own with/without-branch construction, wired into
      `_build_call_ops`'s flat (non-promoted) call site in place of the old direct
      `generateSchemeSubroutineCallOps` call.
      **Adjacent finding — fixed 2026-08-17 (see Index).** `_build_block_signature`'s
      kind/unit-conversion scratch-buffer allocation for an optional arg used to run
      unconditionally, calling `size()` on the source array before any presence check —
      invalid if the arg is genuinely absent (not just logically inactive). Pre-existing, would
      affect any optional+unit/kind-mismatched arg, not something the `active`-gating fix above
      introduced; not exercised by examples/opt_arg's own test since its driver always sets
      `flag_for_opt_arg = .true.` and always allocates `opt_arg`/`opt_arg_2`.
      - **Root cause, precisely:** the bug lives entirely in the *printer*
        (`print_ftn.py`), not in IR construction. `suite_cap.py`'s `_build_block_signature`
        builds one `KindCastOp`/`UnitConvertOp` (pre-call) and, for `intent(inout)`/`intent(out)`
        args, one paired `KindWriteBackOp`/`UnitWriteBackOp` (post-call) per kind/unit-mismatched
        arg — these IR ops carry no presence information themselves. `print_ftn.py`'s emission
        for all four op kinds printed their `allocate(...(size(...)))`/assignment/`deallocate`
        statements unconditionally, regardless of whether the underlying dummy argument was
        `optional`.
      - **Fix:** at print time, each of the four op cases (`CCPPKindCastOp`, `CCPPUnitConvertOp`,
        `CCPPKindWriteBackOp`, `CCPPUnitWriteBackOp`) now checks whether its array-typed
        source/`original_dest` operand is a block argument with a `"__opt"`-suffixed
        `name_hint` (the same marker `_build_block_signature`/`_hint_for` already stamps onto
        every optional dummy's own block arg, and which survives independently of the
        printer's own name-stripping/registration bookkeeping). When it is, the existing
        `allocated()`-guard/`allocate`/convert (or, for write-back, the assign+`deallocate`)
        lines are wrapped in `if (present(<name>)) then ... end if`, using the same
        `with self.descend() as inner:` indentation idiom already used elsewhere in this file
        (e.g. `CCPPLazyAllocOp`, `CCPPPresentCheckOp`). Non-optional args and scalar
        (non-array) optional args are untouched — printed exactly as before; the fix is scoped
        precisely to the confirmed defect (array `size()` calls on a possibly-absent optional),
        not generalized to the scalar case, which was never confirmed broken and wasn't asked
        for.
      - **Verified directly on regenerated Fortran** (`examples/var_compat`'s own
        `effr_calc`/`rad_lw` schemes, which already have a real optional+unit-mismatched array,
        `effrg_in`/`effri_out` — not something added for this fix): the pre-call buffer
        allocate/convert and (for `effri_out`, `intent(out)`) the post-call write-back are now
        both correctly wrapped in `if (present(effrg_in)) then` / `if (present(effri_out)) then`
        guards; the mandatory (non-optional) `effrl_inout` right alongside them is correctly
        left unconditional. Also directly confirmed on `examples/opt_arg`'s own `opt_var_2`
        (the exact arg this bug was originally found next to) across all three lifecycle
        functions it appears in (`_run`/`_timestep_initial`/`_timestep_final`) — all now
        correctly `present()`-gated.
      - Updated the one golden filecheck fixture this changed,
        `tests/filecheck/examples/end_to_end/var_compat-xml.mlir` (the only fixture with a
        real optional+unit-mismatched array case), to match the new, correct output. Full
        `tests/unit`+`tests/filecheck` suite: 566 passed (1 pre-existing, unrelated
        environment-only failure deselected — `ccpp_xdsl` console-script entry point isn't on
        PATH in this scratchpad, unaffected by this change).
      - Not yet compile/run-verified on this laptop (no Fortran compiler available) or via CI
        (GitHub outage as of this writing) — same standing limitation as every other fix this
        session; verified here by direct generated-Fortran inspection plus the full local test
        suite, per this repo's own established practice for this class of pass-internal,
        non-driver-facing bug.
    - **Bug 2 (timestep-phase local placeholders).** More precise root cause than originally
      diagnosed: not a `HostVariableMatchPass` gap -- `lifecycle_cap.py`'s `_generate_lifecycle_fn`
      (used for register/initialize/finalize/timestep_initial/timestep_final; `_run` goes through
      the separate `run_dispatch.py`) hardcoded the assumption that these phases have no host
      inputs at all, baked into its own docstring and control flow, true for every example ported
      so far but not derived from the actual scheme metadata. `opt_arg_scheme`'s own
      `timestep_init`/`timestep_final` entry points genuinely need `nx`/`var`/`opt_var`/
      `opt_var_2` from `data.meta` -- a HOST-type table, which (per this codebase's own standing
      rule) is never `use`-associated, always a caller-supplied block argument. Fixed with a
      pre-scan (before `new_block` is constructed, since the extra args must be part of its
      `arg_types` from the start) that discovers which HOST-type-table args a phase's own scheme
      entry point needs, exposes them as real dummy arguments on the outer
      `ccpp_physics_timestep_initial`/`_timestep_final` wrapper (mirroring how `_run`'s own
      wrapper already does this), threads inout ones back out through `func.ReturnOp` (the
      existing "inout-echo" convention `print_ftn.py` already uses for `ccpp_t`), and updates
      `examples/opt_arg`'s own driver to actually pass them in.
    - **A genuine xDSL framework gotcha, found and worked around while fixing Bug 2:**
      `xdsl.ir.core.IRWithName.extract_valid_name` silently strips any trailing `_<digits>` from
      a `name_hint` (its own SSA-value auto-disambiguation convention -- it assumes such a
      suffix is framework-generated, not semantic). `opt_arg_scheme`'s own `opt_var_2` collided
      with `opt_var` this way (`name_hint = "opt_var_2"` silently became `"opt_var"`),
      duplicating a dummy-argument name in the generated signature. Worked around with a new
      `"__hostarg"` marker suffix (doesn't end in digits, so xDSL leaves it alone), stripped back
      to the real name in `print_ftn.py`'s existing `__alloc`/`__opt`/`__in` suffix-stripping
      logic -- deliberately NOT added to that logic's intent-detection flags, since (unlike the
      other three) it carries no intent implication of its own; intent falls through to the
      ordinary array/inout-echo detection.
    - **Regression found and fixed while verifying:** the fix's own pre-scan initially also
      matched `ccpp_info`/`ccpp_t` (both legitimately declared in a HOST-type table themselves)
      and tried to expose them a second time alongside their existing dedicated handling,
      duplicating a block argument (`examples/ddthost`'s own `ccpp_info_t` pattern caught this).
      Fixed by excluding `std_name == "host_standard_ccpp_type"` and the `ccpp_t` derived type
      from the pre-scan explicitly.
    - **Verification:** full suite green throughout (`tests/unit` + `tests/filecheck`, 562
      passed, 1 xfailed pre-existing/unrelated, 1 failed pre-existing/unrelated -- the
      `test_build_integration.py` PATH-resolution issue, same as always); new dedicated coverage
      in `test_optional_args.py` (`TestActiveGatedOptionalArgs`, `TestTimestepPhaseHostTableArgs`
      -- the latter's own fixture deliberately uses a second arg named `nx2` to catch the
      name-collision regression directly). `var_compat`'s own real fixture (`effr_calc`'s
      `flag_indicating_cloud_microphysics_has_graupel`-gated args) exercises the same Bug-1 fix
      end-to-end and needed its two golden FileCheck files regenerated to match the now-correct
      output. `examples/opt_arg` is now `add_subdirectory`'d into the root build and added to
      `.github/workflows/compile-tests-cmake.yml`'s matrix -- not yet compile/run-verified on
      this laptop (no Fortran compiler available), so CI is the first real check.
    - **CI-CONFIRMED FOLLOW-ON BUG, found and fixed 2026-08-13 after the above landed:** CI
      (no local Fortran compiler exists to catch this) reported a real gfortran compile error on
      `examples/nested_suite` and `examples/var_compat` --
      `Error: Symbol 'flag_indicating_cloud_microphysics_has_graupel' at (1) has no IMPLICIT type`.
      Root cause: `ActiveCheckOp`'s `condition_expr` was being printed verbatim from the host's
      raw `active = <expr>` metadata text, which -- like `default_value`/dimension expressions --
      is written in *standard-name* space, not local-Fortran-variable space. It happened to
      compile in every case actually tested locally only because those cases' standard name and
      local name coincided; `effr_calc.meta`'s guard (`flag_indicating_cloud_microphysics_
      has_graupel`, whose real local name in `test_host_mod.meta` is `has_graupel`) was the first
      case where they differed, and no compiler was available locally to catch the mismatch before
      it reached CI. `opt_arg`'s own `flag_for_opt_arg` guard hit the same bug class (caught by my
      own `TestActiveGatedOptionalArgs` unit test raising a real error once resolution was added,
      before any CI run), for a second, independent reason described below.
      - **Fix, MODULE-type refs:** new `suite_cap.py` methods `_active_expr_var_indexes` (indexes
        `self.meta_data`'s MODULE- and HOST-type tables by standard name) and a rewritten
        `_resolve_active_condition` that tokenizes the raw expression
        (`_ACTIVE_EXPR_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")`), resolves each
        identifier-like token against that index, and for MODULE-type refs emits a deduped
        `llvm.GlobalOp` USE stub (`use test_host_mod, only: has_graupel`) alongside the resolved
        local name -- the same resolution capgen-v1 does implicitly by generating real Fortran
        rather than an intermediate IR. Confirmed correct end-to-end for `var_compat` and
        `nested_suite`'s real generated Fortran (`has_graupel` now a real dummy/use-associated
        name at every call site, guard reads `if ((has_graupel)) then`).
      - **Fix, HOST-type refs (the harder case, and why `opt_arg` hit this independently):** a
        HOST-type-table var referenced only inside an `active=` expression -- never a scheme's own
        declared arg -- needs threading as a real dummy argument, never `use`-associated, at *two*
        separate layers: (a) `suite_cap.py`'s own suite-cap-level function, via a new
        `_collect_active_gate_extra_args` pre-scan that appends a synthetic `CCPPArgument` to
        `input_arg_list` before `_build_block_signature` runs (wired into
        `generateSubroutineCall`); and (b) the *outer* wrapper `lifecycle_cap.py` builds around
        that call, which has no visibility into the synthetic arg since its own pre-scan only
        reads scheme metadata -- fixed by a fallback that treats a callee's bare arg name as a
        candidate standard name when no scheme's own metadata explains it (the exact shape
        `_collect_active_gate_extra_args` produces). Without fix (b), the outer wrapper compiled
        but silently declared an uninitialized local instead of threading the real host var through
        -- a correct-looking compile that would have been wrong at runtime, worse than the original
        compile error. `run_dispatch.py`'s own `_run`-path wrapper needed no change -- its
        arg-resolution was already generic enough to handle this shape.
      - **Golden-file fallout:** both `var_compat` FileCheck goldens (`end_to_end/
        var_compat-xml.mlir`, `completed_ir/var_compat-xml.mlir`) needed more than a text-only
        fix -- MODULE-type resolution now emits a genuinely new `llvm.mlir.global`/USE-stub pair
        for `has_graupel` that didn't exist in the old (bugged) output at all, so the goldens
        needed that new line inserted (in both the raw-MLIR and use-statement sections), not just
        the guard condition's text corrected.
      - **Verification:** full suite green (562 passed, 1 xfailed, 1 failed -- same pre-existing
        `test_build_integration.py` PATH issue as always, unrelated). `var_compat` and
        `nested_suite` real generated Fortran directly inspected and confirmed correct
        end-to-end. `opt_arg`'s own generated Fortran also directly inspected and confirmed
        correct. Not yet re-verified: an actual gfortran compile (still no local compiler --
        CI is the next real check on this fix, same limitation as before).
    - **CI/build follow-on, found and fixed 2026-08-13:** CI caught a real gfortran type
      mismatch on `examples/opt_arg`'s own driver (`test_opt_arg_host_integration.F90`):
      `flag_for_opt_arg` is threaded as a genuine dummy argument on
      `test_host_ccpp_physics_timestep_initial`/`_timestep_final`/`_run` (part of the HOST-type
      fix above), and the driver's positional calls hadn't been updated to pass it, shifting
      every argument after that slot. Fixed by adding it at the correct position in all three
      call sites, confirmed against the actual generated cap signatures (via
      `xdsl_ccpp.tools.ccpp_dsl`, the same tool CI's CMake step uses) rather than guessed.
    - **PR #70 Copilot review, addressed 2026-08-13** (two of three comments; third deliberately
      deferred, see below):
      - **Multi-condition active-gating was a real, live bug, not hypothetical.**
        `_build_active_gated_call_ops` originally grouped *all* of a scheme's active-gated
        optional args under whichever distinct `model_var_active_expr` it encountered first,
        silently mis-gating every other condition. Adding a defensive raise for this (the
        initially-planned "cheap guard") immediately tripped on `examples/var_compat`'s own
        `effr_calc_run`, which genuinely has two independent conditions --
        `effrg_in`/`ncg_in` gated by `has_graupel`, `nci_out`/`effri_out` independently gated by
        `has_ice` (from `test_host_data.meta`'s own `active=` properties). The merged, previously
        "passing" golden Fortran had been silently wrong the whole time: with `has_graupel`
        picked as the sole condition, `nci_out`/`effri_out` were computed even when `has_ice` was
        false, and dropped even when `has_ice` was true and `has_graupel` false. Fixed properly
        (not just guarded) with nested `ActiveCheckOp`s, one level per distinct condition, so
        every combination of N conditions' truth values reaches the one call variant with exactly
        the right args included (2**N leaf calls; N is the number of distinct conditions on one
        scheme, not the number of gated args -- 2 today). Both `var_compat` goldens regenerated
        (a substantially bigger diff than the earlier text-only fixes -- the nested structure
        roughly quadruples that function's line count) and re-verified against fresh tool output
        rather than hand-edited guesswork.
      - **`suite_use_stubs` default of `None` silently dropped USE stubs** if
        `_build_active_gated_call_ops` were ever called without it (not currently live -- the one
        caller always passes it -- but exactly the function Stage 2a of the vocabulary-resolution
        redesign (see Index) plans to route more traffic through). Fixed by making it a required
        keyword-only parameter instead of a risky default.
      - **Deliberately deferred:** synthetic HOST-table args from `_collect_active_gate_extra_args`
        missing `model_var_name`/`model_module_name`/`model_var_is_host_table` (can spuriously
        trip the suite dummy-arg name-collision fallback, and degrades `--emit-resolved-vars`
        accuracy for these args). Real bug, but lives entirely inside
        `_collect_active_gate_extra_args`, which the redesign's Stage 2a/3 deletes outright once
        HOST-type vars move to use-association like MODULE-type already does -- fixing it now
        would be thrown-away work.
      - **Verification:** full suite green again (562 passed, 1 xfailed, 1 failed -- same
        pre-existing `test_build_integration.py` PATH issue, unrelated).
- **Vocabulary-resolution redesign — matching real capgen-v1's use-association model — L, staged.**
  Prompted directly by the `active=` fix above: real capgen-v1's own generated caps (confirmed by
  running its actual `capgen/ccpp_capgen.py` against `opt_arg`, `var_compat`, and `chunked_data`
  from the reference `feature/capgen-v1` checkout) never thread host-owned state as call
  arguments at all -- every host-declared variable, regardless of table type, is resolved via
  `use <module>, only: <var>` wherever referenced, with only a small fixed set of generic
  dispatch scalars (loop bounds, error handling) threaded as plain arguments. xdsl_ccpp's own
  HOST-type table conflates the two, forcing every genuine host-state HOST-type reference to be
  threaded as a block argument -- the direct cause of this session's `_collect_active_gate_extra_args`/
  two-layer `lifecycle_cap.py` propagation/`__hostarg` xDSL-workaround machinery. Unifying
  HOST-type resolution with the MODULE-type use-association path that already exists (and already
  correctly resolves `has_graupel`) is expected to let a meaningful fraction of that machinery be
  deleted outright rather than maintained. Staged so each piece lands and is tested independently:
  - **Stage 1 — Classify, don't act. ✅ Done (2026-08-13).** New `DISPATCH_SCALAR_STD_NAMES`/
    `is_dispatch_scalar_std_name` in `ccpp_conventions.py` and
    `GenerateSuiteSubroutine._classify_host_table_vars` in `suite_cap.py` (returns
    `std_name.lower() -> 'state'|'dispatch_scalar'` for every var in a HOST-type table). No
    behavior change -- nothing reads this yet. **Correction to the original Stage 1 sketch:**
    the plan assumed the classifier could check "is this var backed by a real compiled Fortran
    module" -- turns out that fact isn't visible to the Python tool at all (which HOST_FILES
    entries get a `.F90` compiled is a CMake-level decision the tool never sees; it only gets a
    flat `--host-files` list). The real, actually-implementable signal, confirmed by direct
    inspection of every example's own generic control-derived host table (`opt_arg`/`var_compat`/
    `chunked_data`/`suite_allocate`/.../`test_host.meta`): every one of them declares exactly the
    same 4 standard names (`horizontal_loop_begin`, `horizontal_loop_end`, `ccpp_error_message`,
    `ccpp_error_code`) and nothing else -- no example's `.meta` anywhere declares a standard_name
    for `thread_num`/`nthreads`/`nphys_threads`/`suite_name`/`group_name`; those are synthesized
    directly by the code generator, never host-matched. So the classifier is a small fixed
    allowlist, not a module-existence check. Covered by
    `tests/unit/test_host_var_classification.py` (3 tests, fixture shape mirrors `opt_arg`'s own
    `data.meta`/`test_host.meta` verbatim).
  - **Stage 2a — use-associate `state`-classified HOST vars at the innermost call layer
    (`suite_cap.py`). ✅ Done (2026-08-13).** `_active_expr_var_indexes` now returns
    `(use_associated_index, dummy_arg_index)` instead of `(module_var_index, host_var_index)`:
    `use_associated_index` merges every MODULE-type var (unchanged) with every
    `state`-classified HOST-type var (new); `dummy_arg_index` keeps only
    `dispatch_scalar`-classified HOST-type vars (in practice always empty today -- no example
    gates on a loop bound or error code, kept for correctness rather than assumed impossible).
    `_resolve_active_condition` and `_collect_active_gate_extra_args` both switched to the new
    names/semantics; a `state`-classified HOST-type ref now gets the exact same USE-stub
    treatment a MODULE-type ref already did, so `_collect_active_gate_extra_args` no longer
    synthesizes a dummy arg for it at all.
    - **Bigger-than-expected win, confirmed by direct inspection:** the outer
      `lifecycle_cap.py`/`ccpp_cap.py` wrapper layer needed *no change at all* -- it derives its
      own "extra host arg" list by inspecting the inner suite-cap function's own actual
      signature (built by this session's earlier two-layer propagation fix) rather than
      recomputing membership independently, so once Stage 2a's change made the inner function
      stop declaring `flag_for_opt_arg`/`flag_for_opt_var` as a dummy arg, the outer wrapper
      automatically stopped requesting it too -- confirmed against both `opt_arg`'s real
      generated Fortran (`OptArg_ccpp_physics_timestep_initial` no longer takes
      `flag_for_opt_arg`, calls the inner function with the exact matching smaller arg list)
      and the simpler `active_gated_scheme`/`active_gated_host` unit fixture
      (`ActiveGated_ccpp_physics_run` likewise). Stages 2b/2c are very likely no-ops as a
      result -- kept as separate backlog items to explicitly re-confirm and go looking for any
      now-dead code, not because a fix is expected to be needed.
    - **New regression coverage:** `TestActiveGatedOptionalArgs::
      test_flag_is_use_associated_not_threaded_as_arg` (`tests/unit/test_optional_args.py`) --
      the 4 pre-existing tests in that class only ever asserted the *condition* text and which
      args appear in the with/without call branches, never *how* the flag itself was threaded,
      so they passed unchanged through this fix without actually exercising the new behavior;
      this new test locks in the USE-associated form directly.
    - **Verification:** full suite green (566 passed, 1 xfailed, 1 failed -- same pre-existing
      `test_build_integration.py` PATH issue, unrelated). Both `var_compat` FileCheck goldens
      unchanged and still passing, confirming MODULE-type resolution (`has_graupel`/`has_ice`)
      is untouched by the `_active_expr_var_indexes` restructuring. `opt_arg`'s own real
      generated Fortran directly inspected end-to-end.
    - **CI follow-on, found and fixed 2026-08-13:** `examples/opt_arg`'s own driver
      (`test_opt_arg_host_integration.F90`) still passed `flag_for_opt_arg` positionally to
      `test_host_ccpp_physics_timestep_initial`/`_run`/`_timestep_final` -- exactly the
      argument Stage 2a just stopped exposing on those signatures, so every actual argument
      after that slot shifted by one (gfortran caught real type mismatches: LOGICAL passed
      where CHARACTER(512) was expected, etc.). This is the literal mirror image of the fix
      needed right before Stage 2a landed (that one *added* the positional arg; this one
      *removes* it) -- exactly the "this proves the point" moment anticipated when Stage 2a's
      note above was written. Fixed by removing it from all three call sites; the driver still
      `use`s and sets `flag_for_opt_arg` from `data` (unchanged), it just no longer threads it
      through the call. Confirmed against the actual regenerated signatures before editing,
      same as before. CI green after this fix.
  - **Stage 2b — confirm the outer lifecycle wrapper (`lifecycle_cap.py`) needs no change.
    ✅ Confirmed, no code change (2026-08-13).** Exhaustively checked every example in the repo
    that declares an `active =` property (found via `grep -rl '^\s*active\s*=' examples
    --include='*.meta'`): `capgen`, `ddthost`, `instances`, `nested_suite`, `opt_arg`,
    `var_compat`. Regenerated each via `xdsl_ccpp.tools.ccpp_dsl` (the same tool CI's CMake
    step calls) and inspected the actual output:
    - `opt_arg`, `var_compat`, `nested_suite` -- HOST/MODULE-type `active=` refs, exactly
      Stage 2a's target case. All three confirmed correct end-to-end (`var_compat`/
      `nested_suite`'s MODULE-type `has_graupel`/`has_ice` were never affected by Stage 2a to
      begin with; `opt_arg`'s HOST-type `flag_for_opt_arg` now resolves via use-association at
      every layer, outer wrapper included, with no manual change needed there).
    - `capgen`/`ddthost`/`instances` -- **found a separate, pre-existing, out-of-scope gap**:
      each of these declares its `active=` property on a member of a `type = ddt` table (e.g.
      `instances`/`data.meta`'s `instance_type` DDT gates `data_array_opt` on
      `flag_for_opt_array`, itself another member of the same DDT), not a `type = host` or
      `type = module` table. `_active_expr_var_indexes` only ever scanned MODULE/HOST tables,
      even before this redesign -- DDT-type `active=` support was never built at all, in either
      the old or new resolution model. Not a Stage 2a/2b regression: `capgen`/`ddthost`'s own
      DDT member (`index_of_water_vapor_specific_humidity`) turns out unexercised by any actual
      optional arg in those examples' own suites (doesn't appear in either's generated Fortran
      at all), so it's silently inert rather than silently wrong. `instances`' own case is real
      but already known-broken for an unrelated, already-tracked reason (see
      `instances`/`instances_advection` backlog entry above: the whole array-of-DDT-instances
      access pattern isn't implemented yet, pending an architecture decision). Logging this as
      its own thing to fold into Stage 4's `instances` rollout (or the architecture decision
      itself) rather than fixing now -- out of Stage 2b's scope, which is the HOST/MODULE-type
      redesign specifically.
    - No `lifecycle_cap.py` code change needed or made. `_generate_lifecycle_fn`'s own
      HOST-exclusive-arg fallback (the "`_std_name is None and _bare_name.lower() in
      host_var_map_all`" branch, added for this session's original Bug 2 fix) is now
      unreachable for every current example -- it only ever existed to handle
      `_collect_active_gate_extra_args`'s synthesized args showing up in a callee's own
      signature, and Stage 2a means that no longer happens for `state`-classified vars. Left in
      place rather than deleted (that's Stage 3): it's still the correct fallback for a
      hypothetical future `dispatch_scalar`-classified active-gated ref, and confirming
      "unreachable today" isn't the same as "provably dead for all time."
  - **Stage 2c — confirm `run_dispatch.py` needs no change. ✅ Confirmed, no code change
    (2026-08-13).** Same underlying reason as Stage 2b, traced through a different mechanism:
    `_build_run_block_signature`'s own `non_host_args` (the source of the outer `_run`
    wrapper's own extra block args) is built by classifying each of the *actual* callee's real
    `callee_input_names`/`callee_input_types` as `ArgSourceKind.Host` (resolvable via
    use-association) or `ArgSourceKind.Block` (must be threaded) -- it iterates the callee's
    own already-generated signature, not an independently-recomputed metadata scan. Since Stage
    2a means a `state`-classified HOST-type var no longer appears in that signature at all
    (replaced by an internal `use` statement), this classification loop never encounters it as
    a candidate in the first place, for the identical structural reason `lifecycle_cap.py`'s
    own mechanism self-adjusted in Stage 2b. Confirmed directly: `opt_arg`'s
    `test_host_ccpp_physics_run(suite_name, suite_part, col_start, col_end, nx, var, opt_var,
    opt_var_2, errmsg, errflg)` has no `flag_for_opt_arg`, and `var_compat`'s
    `test_host_ccpp_physics_run(suite_name, suite_part, col_start, col_end, errmsg, errflg)`
    correctly `use`-associates `has_graupel` (MODULE-type, unaffected either way) and threads it
    correctly into the inner call (`has_graupel=has_graupel`) with no manual change needed.
  - **Stage 3 — delete now-dead code. ✅ Done (2026-08-13).**
    - **`suite_cap.py`:** `_collect_active_gate_extra_args` deleted outright, along with its
      call site in `generateSubroutineCall`. `_active_expr_var_indexes` simplified to return a
      single `use_associated_index` dict (was a `(use_associated_index, dummy_arg_index)`
      tuple) -- `dummy_arg_index` had no remaining consumer once the synthesis function that
      built entries for it was gone. `_resolve_active_condition`'s fallback for an unresolved
      `dispatch_scalar`-classified reference changed from *silently* threading a
      never-exercised dummy-argument workaround to **raising a clear error** instead: gating an
      optional arg's presence on a loop bound or error code has no example, no clear Fortran
      realization, and simply deleting the fallback with no replacement would have silently
      regressed to printing the raw standard name verbatim -- the exact "no IMPLICIT type" bug
      class this whole `active=` fix started from. An explicit, documented boundary beats
      either silently-untested support or a silent reintroduction of the original bug.
    - **`lifecycle_cap.py`:** removed the now-fully-dead `_std_name is None and
      _bare_name.lower() in host_var_map_all: _std_name = _bare_name.lower()` fallback --
      its only purpose was recognizing `_collect_active_gate_extra_args`'s synthetic args
      (never any scheme's own declared arg) reaching this scan; nothing produces such an arg
      any more. The surrounding `extra_host_args`/`extra_host_arg_index`/`__hostarg` machinery
      is **kept, not dead** -- confirmed still load-bearing for genuinely scheme-declared
      HOST-type args (`opt_arg`'s own `nx`/`var`/`opt_var`/`opt_var_2` for
      `timestep_init`/`timestep_final`), a case Stages 2a-2c never touched (they were scoped to
      HOST-type vars referenced *only* inside an `active=` property, never a real scheme
      argument). Updated the pre-scan's own comment, which had drifted into a now-inaccurate
      blanket claim ("HOST-type table variables are deliberately never use-associated anywhere
      in this codebase") now that Stage 2a use-associates `state`-classified ones -- just at a
      different layer (inside `suite_cap.py`'s own generated function, not here).
    - **Net code-volume effect, measured, not assumed:** modest, and deliberately scoped --
      +6/-7 lines net across `suite_cap.py`/`lifecycle_cap.py` since Stage 1 started. This
      stage only unwound the complexity this session's *own* `active=`-verbatim-text fix
      introduced (a real, contained win: the synthesis function, its call site, and the dead
      fallback are gone). It does **not** touch the much larger, pre-existing "every
      scheme-declared HOST-type arg is threaded as a block argument" pattern used throughout
      `suite_cap.py`/`lifecycle_cap.py`/`run_dispatch.py` for genuine scheme args (`opt_arg`'s
      own `nx`/`var`/`opt_var_2`, `var_compat`'s `phys_state%effrr` slicing, etc.) -- Stages
      2a-2c were deliberately scoped to the `active=`-only synthetic case, not a general
      HOST-type-resolution rewrite. Extending use-association to genuine scheme args too (the
      larger prize the original capgen-v1 comparison pointed at) would be a separate, much
      bigger future redesign, not something Stages 1-4 as planned actually deliver.
    - **Verification:** full suite green (566 passed, 1 xfailed, 1 failed -- same pre-existing
      `test_build_integration.py` PATH issue, unrelated). `opt_arg`'s real generated Fortran
      re-inspected directly and confirmed byte-identical to before this cleanup.
  - **Stage 4 — roll out to the rest of the examples. ✅ Done (2026-08-13), turned out to be
    pure verification, not new work.** Stages 2a-2c's code change is a general mechanism inside
    `suite_cap.py` (`_classify_host_table_vars`/`_active_expr_var_indexes`), not per-example
    wiring -- it already applies to every example the moment its cap is regenerated. There was
    no per-example "port" step left to do; "rolling out" meant confirming the whole repo still
    generates cleanly. Ran the real `xdsl_ccpp.tools.ccpp_dsl` tool (the same one CI's CMake step
    calls) against every one of the repo's 19 real `xdsl_ccpp_capgen()` invocations (found via
    `grep -rl 'xdsl_ccpp_capgen(' examples --include=CMakeLists.txt`; `atmospheric_physics` and
    `shared` aren't real cap-generation targets, confirmed by inspection), resolving each
    example's own HOSTFILES/SCHEMEFILES/SUITES/HOST_NAME from its CMakeLists.txt. All 19
    succeeded (exit 0): `advection`, `advection_flat_host`, `capgen` (both plain and chost
    invocations), `chararg`, `chunked_data`, `constadv`, `constituents_dim`, `constprop`,
    `ddthost` (both invocations), `helloworld`, `instances`, `instances_advection`, `kessler`
    (all three: plain/bindc/chost), `nestedddt`, `suite_allocate`, `tinyddt` -- plus `opt_arg`,
    `var_compat`, `nested_suite`, already verified in detail across Stages 2a-2c.
    - **Bonus finding, not caused by this redesign:** `instances_advection` was documented above
      (under the `instances`/`instances_advection` backlog entry) as hard-failing at cap
      generation with `xdsl.utils.exceptions.VerifyException: Expected source and destination
      to have the same shape` inside the constituent-registration path. That failure **no
      longer reproduces** -- cap generation now succeeds and produces a complete-looking
      `test_host_ccpp_register_constituents`/`test_host_ccpp_is_scheme_constituent` etc. Likely
      fixed as a side effect of task #1's `constituents_dim` host-matching fix earlier this
      session (the backlog entry itself already suspected the two examples "may share one root
      cause"), not by anything in Stages 1-3. Not independently re-verified beyond "it no longer
      crashes" -- the array-of-DDT-instances access-pattern gap `instances`'s own backlog entry
      describes (`data_array`/`data_array2` resolved as flat Block args instead of
      `instance_data(instance)%...`) was **not** re-checked and should not be assumed fixed.
      Worth a fresh look at task #4's premise before relying on this, but out of scope to chase
      further under "Stage 4."
    - **Verification:** full suite still green throughout (566 passed, 1 xfailed, 1 failed --
      same pre-existing `test_build_integration.py` PATH issue, unrelated) -- this stage made no
      source changes at all, confirmation only.
  - **Stage 5 — optional, separable naming cleanup. ✅ Done (2026-08-13), best-fit rename.**
    Host-prefixed subroutine names -> capgen-v1-style generic names, keeping xdsl_ccpp's own
    existing 6-phase lifecycle structure exactly as-is (see the follow-on backlog item just
    below for the *8*-phase question, deliberately out of scope here):
    | Old (host-prefixed) | New (bare) |
    |---|---|
    | `<host>_ccpp_physics_register` | `ccpp_register` |
    | `<host>_ccpp_physics_initialize` | `ccpp_init` |
    | `<host>_ccpp_physics_finalize` | `ccpp_final` |
    | `<host>_ccpp_physics_timestep_initial` | `ccpp_physics_timestep_init` |
    | `<host>_ccpp_physics_timestep_final` | `ccpp_physics_timestep_final` |
    | `<host>_ccpp_physics_run` | `ccpp_physics_run` |

    The **module** itself stays host-prefixed (`module <host>_ccpp_cap`), unchanged --
    matching real capgen-v1's own convention exactly (its own `--host-name` help text: drives
    the module name "so multiple host integrations can co-exist in one executable"; the bare
    subroutines inside don't need to disambiguate, Fortran module namespacing already does that).
    - **`ccpp_cap.py`:** `lifecycle_specs`' first tuple element changed from a suffix
      (`"_ccpp_physics_register"`, appended to `camel_name`) to the bare final name directly;
      both `fn_name=camel_name + fn_suffix` call sites became `fn_name=fn_suffix`.
      `_inject_capscratch_gpu_exit`'s hardcoded `camel_name + "_ccpp_physics_finalize"` lookup
      updated to the literal `"ccpp_final"`.
    - **`gpu_ccpp_cap_pass.py`:** `_LIFECYCLE_FN_SUFFIX_TO_PHASE`'s keys updated to the bare
      names. **A real bug, caught by the test suite, not by inspection:** the separate
      `"_ccpp_physics_run" in fn_name` check (run's dispatch shape differs from the other five,
      so it isn't in that dict) still had its leading underscore, silently no longer matching
      `"ccpp_physics_run"` at all -- GPU data-hoisting directives stopped being inserted into
      the run function's body entirely, with no error, just an empty/wrong result. Found via
      `test_gpu_data_hoisting.py`'s own assertions failing with a suspiciously *empty* function
      body rather than a naming-string mismatch -- worth remembering as a class of bug this kind
      of rename can hide: a substring check silently returning nothing, not a loud break.
    - **`cpp_interop.py`, the deepest ripple:** the "chost" (C++ interop) naming convention
      (`_chost_fn_name`) derived its own name by string-replacing `"_ccpp_physics_"` with
      `"_chost_physics_"` inside the plain cap's own bind-C function name -- broke completely
      once that name lost its host prefix and, for register/init/final, lost the substring
      `"physics_"` entirely. chost naming is xdsl_ccpp-specific (no capgen-v1 equivalent to
      align with) and deliberately kept host-prefixed as before (e.g. still
      `Kessler_chost_physics_run`) -- not part of this rename's scope. Fixed by reconstructing
      the chost name from `camel_name`/the lifecycle-phase key directly
      (`f"{camel_name}_chost_physics_{lc}"`) instead of parsing it out of the plain name, since
      the plain name no longer carries the information needed to derive it. Required threading
      `camel_name` into `_chost_fn_contexts` (a new parameter, 3 call sites) and fixing the
      matching `_LIFECYCLE` dict in the same file (same bug class as `gpu_ccpp_cap_pass.py`'s).
    - **Fallout, mechanical but large:** 24 filecheck goldens and 14 unit test files asserted
      exact old subroutine-name text. Batch-fixed via a scoped regex substitution
      (`\b\w+_ccpp_physics_(register|initialize|finalize|timestep_initial|timestep_final|run)\b`
      -> the corresponding new bare name) across `tests/unit/*.py` and
      `tests/filecheck/**/*.mlir`, which handled most of it; a further manual pass fixed (a)
      wrapped/continuation lines in filecheck goldens whose line length changed enough to
      shift or eliminate the wrap point (the blind regex correctly renamed the text but
      couldn't re-flow line wrapping) and (b) a handful of bare string-literal
      `.endswith("_ccpp_physics_...")` checks in `test_ccpp_t_threading.py` that the regex's
      "must be part of a longer identifier" pattern didn't match.
    - **Verification:** full suite green (566 passed, 1 xfailed, 1 failed -- same pre-existing
      `test_build_integration.py` PATH issue, unrelated).
  - **Follow-on, logged per project owner request (2026-08-13): full 6-phase -> 8-phase
    lifecycle match with capgen-v1 — task #28. ✅ Done (2026-08-20), Stages 1-4 of the
    dedicated 5-stage plan; Stage 5 spun off as its own backlog item below.** Real capgen-v1
    doesn't have 6 lifecycle entry points, it has 8 -- it splits what this codebase called
    "initialize" into two distinct phases (`ccpp_init` at the suite level, `ccpp_physics_init`
    at the per-group level) and "finalize" likewise (`ccpp_physics_final` + `ccpp_final`).
    Genuine new architecture, not a rename, done as its own branch
    (`lifecycle-8phase-stage3-physics-init-final`) across 4 stages:
    - **Stages 1-2** (mechanical): generalized the existing `run`-only per-group dispatch
      machinery (`suite_cap.py`/`run_dispatch.py`) to a `phase`-parameterized mechanism, moving
      `ccpp_physics_timestep_init`/`_final` to the correct group-scoped signature (they
      pre-existed under the wrong, flat signature).
    - **Stage 3** (the real architecture change): added net-new `ccpp_physics_init`/
      `ccpp_physics_final`, and made the flat `ccpp_init`/`ccpp_final` stop calling schemes
      directly (`emit_scheme_calls=False`), matching capgen-v1's actual split. Surfaced and
      fixed several real, pre-existing-or-newly-exposed generator bugs, each confirmed via
      direct MLIR/Fortran regeneration and/or a real CI build or runtime failure, not just
      filecheck: an `emit_scheme_calls` over-broad suppression that also silently dropped
      instance/ninstances threading; a stale `table_postfix` causing an arg-count mismatch; a
      duplicate `ccpp_info` dummy argument in `examples/ddthost`; a missing
      `_LC_TO_ENTRY_SUFFIX` entry that silently dropped a DDT arg from a chost wrapper; a
      type-check-before-position-check ordering bug in `run_dispatch.py`'s
      `_build_call_and_copy_back_ops` that corrupted `errflg` and lost a real scheme-arg
      write-back (`examples/nested_suite`/`examples/var_compat`); subcycle-loop wrapping
      applied to `_init`/`_finalize` group dispatch when real capgen-v1 only ever loops
      subcycles for `_run` (`examples/nested_suite`'s `effr_calc_init` called 4x instead of
      once, tripping its own ordering check); a redundant explicit `deallocate()` immediately
      before Fortran's own automatic scope-exit deallocation in the chost DDT cleanup path
      (`cpp_interop.py`); and, unrelated to the generator, a pre-existing driver bug in
      `examples/capgen/host_cpp/driver_capgen_chost.cpp`'s `State` constructor call (arguments
      passed in the wrong order relative to the generated struct, silently mis-sizing
      `temp_interfaces` and causing a real heap buffer overflow -- "double free or corruption
      (out)" in CI).
    - **Stage 4** (driver rollout): happened reactively during Stage 3's CI-failure debugging
      rather than as its own separate pass -- `examples/capgen` (both ftn and cxx),
      `examples/kessler` (both cxx and the plain ftn+cxx driver), `examples/ddthost`,
      `examples/tinyddt`, `examples/nestedddt`, and `examples/advection`'s `test_host.F90` (a
      `check_constituent_indices` assertion had to move from right after `ccpp_init` to right
      after `ccpp_physics_init`, since the scheme that populates those indices moved with it)
      all needed real updates; verified via full CI, now green across the board.
    - **Stage 5 deliberately not attempted as part of this effort** -- see its own backlog
      entry immediately below.
  - **Stage 5 of task #28: match capgen-v1's `''`/`'all'`-group fan-out call shape exactly —
    logged separately (2026-08-20), not started.** Real capgen-v1's own driver convention calls
    each `ccpp_physics_*` entry point once per timestep with `suite_part=''`/`'all'`, letting the
    generated dispatch fan out over every group internally, rather than the caller looping over
    group names itself (this codebase's own convention, and functionally equivalent -- Stages
    1-4 already achieve full behavioral parity without this). Only `examples/ddthost` and
    `examples/capgen`'s `temp_suite.xml` have more than one `<group>`, so only those two
    examples' drivers/fixtures could even show a difference; every other example is
    unaffected either way. Scope: one more dispatch-generation change of the same *kind* as
    Stage 3 (add a branch to the existing per-group dispatch that fans out over all groups when
    `suite_part` is empty/`'all'`, instead of requiring a name match) -- smaller in file/example
    footprint than Stage 3, but the same *class* of change (new dispatch logic, not a rename),
    so carries the same real risk of CI-round-trip-only-discoverable bugs Stage 3 hit repeatedly.
    📋 Backlog (size S-M, purely cosmetic call-shape parity, blocks nothing) -- build only if the
    reviewer wants literal call-shape parity with upstream's own driver convention.
  - **Task #11 scoping pass (2026-08-20): the three remaining lower-priority legacy/compat
    vocabulary gaps.** None currently exercised by any end-to-end test on either side. Read
    real capgen-v1's own upstream source (`ccpp-framework-fresh/capgen/metadata/`) for each:
    1. **`number_of_openmp_threads` -> `number_of_threads` rename.** Real capgen-v1:
       `metadata/legacy_compat.py`'s `_LEGACY_NAME_MAP`, one more entry gated behind the same
       `--legacy-mode` shim as `horizontal_loop_extent`. xdsl-ccpp already has the matching
       hook: `CCPP_DEPRECATED_STD_NAMES` (`ccpp_conventions.py:199`), consulted by
       `deprecated_std_name_warning()` from `ArgumentOp.__init__` (`ccpp.py:452-466`) — a real
       dict, not a single hardcoded name, so adding an entry is genuinely mechanical.
       **But:** confirmed by reading both code paths that xdsl-ccpp's `--legacy-mode` gate only
       *warns and accepts* a deprecated name — unlike capgen-v1's own `translate()`, it never
       actually rewrites the name for downstream matching. `horizontal_loop_extent` still works
       under this design only because it and `horizontal_dimension` are *also* both members of
       `CCPP_HORIZONTAL_DIMENSIONS`, consulted separately by `dims_compatible()`
       (`ccpp_conventions.py:105-118`) wherever host/scheme dims are matched.
       `number_of_openmp_threads`/`number_of_threads` are scalar *count* variables, not
       dimension names — there is no equivalent equivalence-class mechanism for them today,
       only the instance_number-specific one item 3 below describes. **Net: adding the map
       entry alone is S-sized but cosmetic-only (suppresses the reject error, nothing else) —
       it isn't a meaningful fix until item 3's mechanism (or some equivalent) exists to make
       the renamed value actually resolve anywhere.** Not independent of item 3, despite being
       filed as a separate gap originally.
    2. **`--gfs-dim-aliases`-style vertical-axis equivalence
       (`adjusted_vertical_layer_dimension_for_radiation` /
       `vertical_composition_dimension` => `vertical_layer_dimension`).** Real capgen-v1:
       `metadata/dim_aliases.py`, an opt-in, warned, transient shim collapsing these only at
       the point of host/scheme dim-identity comparison (deliberately *not* a rename -- each
       name also carries meaning as its own standalone control variable elsewhere). xdsl-ccpp
       already has the exact right-shaped mechanism for this: `dims_compatible()` +
       `CCPP_VERTICAL_DIMENSIONS` (`ccpp_conventions.py:85-92`) is already a set-membership
       equivalence class, not a hardcoded pairwise map -- adding these two GFS-specific names
       to that frozenset would make `dims_compatible()` treat them as equivalent immediately,
       no new mechanism needed. **Real divergence to weigh, not just an implementation
       detail:** `CCPP_VERTICAL_DIMENSIONS` has no opt-in gate at all (always on for its
       existing members) where capgen-v1 deliberately gates this exact collapsing behind
       `--gfs-dim-aliases` (not on by default) precisely because it's a lossy, GFS-physics-
       specific collapse that could be wrong for a hypothetical host using these names
       non-equivalently. Adding them unconditionally would be a real, deliberate divergence
       from capgen-v1's own posture, not a neutral port. **Net: S-sized to wire in, but the
       first real decision is whether to add gating to `dims_compatible()` at all (new,
       possibly reusable machinery) or accept the divergence and go always-on** -- worth a
       one-line decision from the project owner before touching code.
       - **Done (2026-08-24), task #68.** Project owner chose gating, matching capgen-v1's own
         posture rather than the always-on divergence. Added `CCPP_GFS_DIM_ALIASES`
         (`ccpp_conventions.py`) and a new `gfs_dim_aliases: bool = False` parameter on
         `dims_compatible()` (canonicalizes both sides through the map before the existing
         exact-match/equivalence-class checks, only when `True`). Threaded through as a new
         `gfs_dim_aliases: bool = False` dataclass field on `HostVariableMatchPass`
         (`host_var_match_pass.py`) rather than a process-global flag like `--legacy-mode` --
         host-var-matching only ever runs inside the `ccpp_opt` subprocess, so there's no
         in-process ArgumentOp-construction call site needing a global the way `--legacy-mode`
         does. Wired to a new `--gfs-dim-aliases` CLI flag on `ccpp_dsl.py` that appends
         `generate-host-match{gfs_dim_aliases=true}` to the pass pipeline when set, mirroring
         the existing `--bind-c` -> `generate-ccpp-cap{bind_c=true}` pass-parameter convention
         already used in this exact file (`_build_pipeline`), not a new global+subprocess-argv
         scheme. Verified: 6 new unit tests in `test_host_var_match.py` (both aliases, both
         directions, cross-alias compatibility with each other, and a negative check it doesn't
         leak into the horizontal equivalence class); full suite 628 passed (622 + 6)/1
         xfailed/0 failed; ruff unchanged (276, git-stash baseline); a real end-to-end CLI
         smoke test (minimal scheme+host `.meta` pair with a GFS-alias dim mismatch) confirming
         the flag correctly gates rejection vs. acceptance through the actual subprocess
         pipeline and pass-parameter string parsing, not just the Python-level unit tests.
    3. **`registered_dimensions.py`'s general scalar-index substitution
       (`number_of_threads`/`thread_number`, e.g. `physics%Interstitial(thread_number)%alpha`).**
       Real capgen-v1: a single table, `SCALAR_INDEX_DIMS` (`metadata/registered_dimensions.py:135`),
       with exactly two entries -- `number_of_instances -> instance_number` (which xdsl-ccpp
       already implements, task #4/#63) and `number_of_threads -> thread_number` (which it
       doesn't). Confirmed by reading capgen-v1's own module docstring that both pairs are
       meant to share *one* general mechanism by design ("Rule 1 generalization lets capgen
       support multi-instance and per-thread container DDTs from one mechanism -- no
       per-dimension code path"). xdsl-ccpp's own port did **not** build it that way:
       `CCPP_INSTANCE_NUMBER_STD_NAME`/`CCPP_NUMBER_OF_INSTANCES_STD_NAME`
       (`ccpp_conventions.py:150,159`) are two hardcoded constants, and the substitution logic
       built around them is spread across 8 files (`print_ftn.py`, `lifecycle_cap.py`,
       `run_dispatch.py`, `suite_cap.py`, `constituent_cap.py`, `ccpp_cap.py`,
       `ccpp_utils.py`, `ccpp_conventions.py`) with no shared table a second pair could plug
       into. **Net: this is the real one -- M-L, not S.** Adding `thread_number` support
       properly means either (a) generalizing the existing instance_number machinery into a
       real `SCALAR_INDEX_DIMS`-style registry first (a genuine refactor across 8 files, with
       the same false-unification risk #56/#65 already flagged elsewhere in this doc if done
       carelessly), or (b) duplicating the whole mechanism for a second pair (worse -- doubles
       the maintenance/bug surface capgen-v1's own design explicitly avoids). Also needs a
       brand-new test fixture/example from scratch (a per-thread container DDT), since nothing
       in the repo exercises this today, mirroring how `examples/instances`/
       `instances_advection` were built for the instance_number case.
    - **Overall sizing: items 1 and 3 are coupled (1 has no real effect without 3 or an
      equivalent); item 2 is genuinely independent and by far the cheapest of the three, with
      one open design decision (gate or not) rather than any real implementation risk.
      Recommended order if picked up: item 2 first (cheap, decision-then-two-line-fix), item 3
      next only if per-thread container DDT support is actually wanted (M-L, own test fixture),
      item 1 as a trivial follow-on once 3 lands.** Not done in this pass -- scoping only, per
      explicit instruction; task #11 stays a backlog item, not closed.
  - Hold `suite_allocate`/`instances`+`instances_advection`/kind_spec/interstitial-variable
    backlog items (all cap-generation-adjacent) until Stage 3 lands -- building on the model
    being replaced would be redone. **Stage 3 landed 2026-08-13; `suite_allocate` (2026-08-17)
    and metadata `kind_spec` support (2026-08-17, see the Index and its own entry below) are
    now both done. `instances`/`instances_advection` and interstitial-variable remain backlog.**
- **Metadata `kind_spec` support — Done (2026-08-17), S/M as scoped.** Real capgen-v1 lets a
  `.meta` table's `[ccpp-table-properties]` block declare
  `kind_spec = <module>:<kind_name>=>spec` (or the `<module>:<spec>` shorthand) to say a kind
  comes from a real host/scheme Fortran module instead of the hardcoded ISO_FORTRAN_ENV table
  this codebase's own `generate-meta-kinds` (`suite_kinds.py`'s `MetaKind` pass) previously
  always assumed. Confirmed as a real, not hypothetical, gap: `examples/capgen`'s own
  `scheme/temp_set.meta`/`temp_adjust.meta` are ported from capgen-v1's upstream
  `end-to-end-tests/capgen/{source_dir2/temp_set,temp_adjust}.meta`, and the real originals
  declare `kind_spec = temp_kinds:kind_temp=>temp_r8` for their `to_promote` argument's kind
  (`kind_temp`) — the port had silently dropped the `kind_spec` line (the parser's own
  attribute allow-list would otherwise crash on it) and substituted `kind_phys` for the real
  `kind_temp` throughout.
  - **Parsing.** `ccpp_xml.py`'s `CCPPTableProperties` gained `kind_spec` on its allow-list,
    accumulating into a new `kind_specs: list[tuple[kind_name, module, spec]]` (a table may
    declare more than one, matching real capgen-v1), parsed by a new `_parse_kind_spec_value`
    mirroring capgen-v1's own `metadata_table.py:_parse_kind_spec_value` regex exactly.
  - **IR.** Forwarded onto `TablePropertiesOp`'s attributes (as `kind_specs`, an `ArrayAttr` of
    `"<module>:<kind_name>=>spec"`-encoded `StringAttr`s -- one canonical encoding decoded by
    the same helper on both ends) from both `.meta`-parsing frontends that build this op:
    `ccpp_xml.py`'s `build_meta_ir` *and* `py_api.py`'s `_table_properties_op`/
    `TableDescriptor`/`SchemeDescriptor` (the two frontends share `parse_meta_file` but each
    had their own, independently-incomplete attribute-forwarding code -- `py_api.py` had the
    exact same array_layout/language-only gap).
  - **Resolution.** `suite_kinds.py`'s `MetaKind` pass gained `_collect_metadata_kind_specs`
    (mirrors capgen-v1's own `ccpp_capgen.py:_collect_metadata_kind_specs`): aggregates
    `kind_name -> (module, spec)` across every table, raising `ValueError` on a genuine
    conflict (two tables declaring different specs for the same kind_name). A kind_spec
    resolution takes priority over the hardcoded `CCPP_KIND_TO_ISO` table; a kind with no
    kind_spec declaration falls back to exactly the pre-existing behavior, so every example
    that never declares one (i.e. all of them except capgen's `temp_set`/`temp_adjust`) is
    byte-for-byte unaffected.
  - **IR/codegen threading.** `ccpp.KindOp` and `ccpp_utils.KindDefOp` both gained a `module`/
    `kind_module` property (default `"iso_fortran_env"`, matching the prior implicit
    behavior), threaded through `generate_kinds.py`. `print_ftn.py`'s `ccpp_kinds` module
    preamble now groups kind renames by `kind_module`: the existing
    `use ISO_FORTRAN_ENV, only: name => value` path is untouched (same condition as before,
    now additionally gated on `kind_module == "iso_fortran_env"`), and a new, purely additive
    branch emits a plain `use <module>, only: name => spec` rename for any other module,
    grouped/sorted by module -- xdsl_ccpp's own existing "declare a kind by rename-on-import"
    design generalized to a real module instead of always assuming ISO_FORTRAN_ENV, rather
    than porting capgen-v1's own `kinds_writer.py` verbatim (which declares a separate new
    parameter after a plain, non-renaming `use`) -- keeps every existing example's
    `ccpp_kinds.F90` output identical.
  - **Verified directly on regenerated output.** `examples/capgen`'s `temp_set.meta`/
    `temp_adjust.meta` restored to their real upstream `kind_spec` declaration and `to_promote`
    kind (`kind_temp`, was silently `kind_phys`); `temp_set.F90`/`temp_adjust.F90` updated to
    `use ccpp_kinds, only: kind_phys, kind_temp` and declare `to_promote` as `real(kind_temp)`,
    matching real capgen-v1's own scheme source exactly (confirmed by reading capgen-v1's own
    `temp_adjust.F90`/`source_dir2/temp_set.F90` -- schemes always `use ccpp_kinds`, never the
    underlying kind_spec module directly, so `kind_temp` and `kind_phys` are indistinguishable
    to scheme code, exactly as this fix's design intends). Added the real upstream
    `adjust/temp_kinds.F90` (ported verbatim) to `examples/capgen/scheme/` and wired it into
    `capgen_ftn_host.exe`'s source list. Regenerated `ccpp_kinds.F90` now reads:
    `use ISO_FORTRAN_ENV, only: kind_phys => REAL64` / `use temp_kinds, only: kind_temp =>
    temp_r8`, and the suite cap correctly declares/passes `to_promote` as `real(kind=kind_temp)`
    throughout. New unit tests: `tests/unit/test_kind_spec.py` (parser edge cases, kind_spec
    resolution, fallback-when-absent, and the conflict-detection error). Updated the
    `ccpp_utils.kind_def`/`ccpp.kind` IR-text golden fixtures the new `module`/`kind_module`
    property changed (`completed_ir/{var_compat,helloworld,ddthost,capgen,advection}-xml.mlir`,
    `completed_ir/{helloworld,ddthost}-py.mlir`) and the `capgen`-specific frontend/completed_ir/
    end_to_end fixtures affected by the restored `kind_temp`. Full suite: 574 passed (566 +
    8 new), 1 pre-existing unrelated environment failure deselected (same `ccpp_xdsl` PATH
    issue as every other fix this session), 1 xfailed.
  - **Not included, deliberately** (would creep into other backlog items): `dependencies`/
    `source_path`/`dependencies_path` metadata threading (tracked separately, same
    `setAttr`/`build_meta_ir` functions but a distinct gap -- see the "Restore real
    dependencies/source_path tracking" item), real capgen-v1's own hard-error-if-kind-
    unresolved behavior (would break every example that relies on the implicit `kind_phys`
    default; not adopted), and a `--kind-type` CLI flag (capgen-v1 has one; this codebase's
    existing narrower `--extra-kind`/`--extra-iso` analog was left as-is).
- **Interstitial-variable register-phase mechanism — scoped 2026-08-17, turns out to be mostly
  already implemented.** Real capgen-v1's rule (`generator/suite_resolver.py`'s own module
  docstring, "Section 8.4"): for each standard_name a scheme argument requests, if it's not in
  the flat host/control dict and its *first* use across the suite is `intent(out)`, it's a
  suite-owned ("interstitial") variable -- the framework synthesizes storage for it (in real
  capgen-v1, a generated `ccpp_<suite>_data.F90` module); if its first use is `intent(in)`/
  `inout`, that's a hard error ("used before it is provided"). `examples/capgen`'s own upstream
  `temp_adjust.meta` exercises exactly this: `interstitial_var` is produced `intent(out)` by
  `temp_adjust_run` and consumed `intent(in)` by `temp_adjust_final` -- a genuinely cross-phase
  case (producer and consumer are different generated Fortran subroutines, called separately by
  the host, potentially timesteps apart). Our own ported `temp_adjust.meta` drops this argument
  entirely (see the rank-re-sync entry right below, found together with it).
  - **What's already there, confirmed by reading the code, not assumed:** `host_var_match_pass.py`
    already implements the *exact* detection rule above -- `_build_model_var_index`'s
    `produced_in_init` dict (any scheme's `_register`/`_init`/`_timestep_init`/`_run` intent=out/
    inout arg with no host match) and `_match_and_validate`'s branch that marks a matching
    unmatched arg `is_interstitial` (or raises the same "no matching host model variable" error
    real capgen-v1 raises, if there's truly no producer). `cap_shared.py`'s
    `classify_arg_ownership` already routes any `is_interstitial` arg to
    `ArgOwnershipKind.SuiteOwned`. `suite_cap.py`'s `_build_module_vars` already declares real
    module-level storage for every `SuiteOwned` var (real/integer/logical/character/DDT, correct
    kind/rank) and `_build_framework_refs` already emits a guarded `LazyAllocOp`
    (`if (.not. allocated(x)) allocate(x(...))`) sized from whichever of three sources resolves
    first: a scheme's own dimension arg, a MODULE-type host table, or another in-scope array's
    own shape (`_find_loop_upper_bound`, already handles `examples/constituents_dim`'s own
    `cwork`/`awork`, dimensioned by a similarly-discovered `number_of_ccpp_constituents`).
  - **Verified directly, not just read** (a minimal two-scheme/one-host scratch fixture, not
    committed anywhere): a same-phase producer→consumer (both in one generated `_run`/physics
    function) allocates and threads correctly; a **cross-phase** producer→consumer (producer in
    `_run`, consumer in a separately-called `_finalize`, the exact shape of real capgen-v1's own
    `interstitial_var` test) also works correctly with zero code changes -- the module-level
    Fortran variable `_build_module_vars` declares simply persists across the separate subroutine
    calls, the way any module variable does; no dedicated "suite data module" or explicit
    persistence mechanism is needed the way real capgen-v1 built one.
  - **Confirmed gap (narrow):** `_find_loop_upper_bound` has no fourth fallback deriving
    `horizontal_dimension` as `col_end - col_start + 1` from the protected
    `horizontal_loop_begin`/`horizontal_loop_end` scalars alone -- if literally no host/module
    array anywhere shares the interstitial's dimension name (a suite with no state arrays at
    all), allocation silently never happens (empty `dim_var_refs`, so no `LazyAllocOp` is
    emitted, and the var stays unallocated when a scheme call needs it). Confirmed via the
    scratch fixture above with `col_start`/`col_end`-only host metadata and no state array.
    Narrow: every real example in this repo has genuine state arrays to derive dimensions from.
  - **Genuinely untested, not just unverified-by-me:** DDT-typed interstitials (the
    `_build_module_vars` branch for `entry.is_ddt` exists but nothing in `tests/` or `examples/`
    exercises it); non-`real` interstitial arrays (integer/logical/character -- only the `real`
    case is proven, via `to_promote`).
  - **Confirmed real bug (2026-08-17), not just an untested edge case — chained interstitial
    sizing.** Real capgen-v1's own `interstitial_var` (`temp_adjust.meta`) is dimensioned by
    `dimension_for_interstitial_variable` -- itself a *separate* interstitial scalar, produced
    by a different scheme's own `_register` phase (`temp_calc_adjust_register`'s `dim_inter`,
    intent=out). Reproduced this exact chained shape in a scratch fixture (scheme_c's `_register`
    produces a scalar `dim_inter`; scheme_a's `_run` produces an array dimensioned by it): the
    generated register-phase preamble allocates the array **before** the call that sets its own
    sizing scalar:
    ```fortran
    if (.not. allocated(produced)) then
      allocate(produced(dim_inter))     ! dim_inter still unset here
    end if
    if (errflg .eq. 0) then
      call scheme_c_register(dim_inter=dim_inter, ...)   ! sets it AFTER
    end if
    ```
    Root cause: `_generate_lifecycle_fn`'s fixed two-block shape -- `_build_framework_refs`
    always builds a preamble (all framework refs + all `LazyAllocOp`s) *before*
    `_build_call_ops` builds the scheme-call sequence, for every phase function. A SuiteOwned
    var whose sizing dimension is itself a same-phase SuiteOwned producer needs the opposite:
    allocate *after* the specific call that produces its dimension, not in the shared preamble.
    Assessed as real, separate follow-on work (not folded into this fix) -- tracked as task #30.
  - **Task #30 fix design — revised 2026-08-19, M-L as scoped. Chosen design: a bounded,
    per-phase dependency-based allocation scheduler, deliberately going beyond what real
    capgen-v1 itself does.** Project intent (explicit, 2026-08-19) is to exceed capgen-v1's
    design where it's genuinely better, not just match it -- so this supersedes an earlier
    same-day pass at this design (see git history of this entry) that proposed adopting real
    capgen-v1's own mechanism verbatim, after checking its actual source
    (`ccpp-framework-fresh/capgen/generator/suite_data.py`): capgen-v1 pre-allocates every
    suite-owned var it can, sorted merely alphabetically by standard_name -- no ordering logic
    at all -- and sidesteps the chained case with one guard (`suite_data.py:365`):
    `if suite_var.dimensions and not suite_var.allocatable:` -- skip pre-allocating entirely,
    trusting the *scheme itself* to declare its own output `allocatable, intent(out)` and
    perform the `allocate()` inside its own hand-written Fortran body. Real example of this
    exact pattern already in this repo: `examples/advection/dlc_liq.F90`'s
    `dyn_const` (`type(ccpp_constituent_properties_t), allocatable, intent(out) :: dyn_const(:)`
    + a hand-written `allocate(dyn_const(1), stat=errflg)` inside `dlc_liq_init`) --
    `xdsl_ccpp` never parses or type-checks this file at all, it only reads `dlc_liq.meta`'s
    declared interface shape and trusts that the real Fortran matches it.
    **Why not just adopt that mechanism as-is (rejected):** it pushes a real, unverifiable
    cross-file consistency burden onto every scheme author who needs this (the `.meta`
    `allocatable` flag, the matching Fortran dummy declaration, and the hand-written
    `allocate()` call all have to agree, with nothing in the generator able to check that they
    do -- exactly the "two things must independently stay in sync" bug shape this whole
    engagement keeps finding via Copilot review, PR #77/#79/#82, except here one of the "two
    things" is hand-written scheme Fortran the generator never even reads); it doesn't cover a
    SuiteOwned var that isn't any single scheme's own `intent(out)` output at all; and it
    silently trusts the SDF's (suite definition file's) own scheme-call order to already
    respect the dependency, with no way to catch a wrong-order mistake at generation time.
    **A genuine, useful nuance found while verifying, folded into the design below**:
    `examples/suite_allocate/make_workspace.F90` -- an existing real example, not a
    hypothetical -- is itself scheme-self-allocated exactly like `dlc_liq.F90`
    (`real(kind=kind_phys), allocatable, intent(out) :: work(:)` + its own `allocate(work(nw))`,
    with an explicit comment: "this scheme owns it; final_fields frees it"). But
    `suite_variable_model.py:353-360` currently forces primitive-type `allocatable` args into
    unconditional suite pre-allocation regardless ("Framework-managed arrays (advected/
    allocatable) are always suite-owned"), so *today's* generated output for this example
    **also** pre-allocates `work` in the suite-cap preamble
    (`if (.not. allocated(work)) allocate(work(nw))`) -- functionally moot, not wrong, only
    because `intent(out)` on an allocatable dummy auto-deallocates on entry (confirmed via
    direct regeneration: `work` gets allocated by the suite, immediately auto-deallocated the
    instant `make_workspace_run` is entered, then re-allocated by the scheme's own `allocate()`
    call), but genuinely redundant, wasted work that the corrected classification below
    eliminates as a side effect. Also confirmed via direct regeneration that removing
    `allocatable = True` from `make_workspace.meta` changes nothing in the generated output
    today -- for this specific example, `work`'s first occurrence is already `intent = out`,
    which the classifier's separate "Case 2" path already forces into suite-ownership on its
    own, so the flag is currently non-load-bearing here (it matters for a first-occurrence
    `intent = inout` case instead, per the same code comment -- not this example).
    **Chosen design.** Two independent, complementary mechanisms, not one:
    1. **Explicit scheme-self-allocation** (fixes the `make_workspace` redundancy): honor
       `allocatable = True` on a primitive-type SuiteOwned var the same way the DDT-constituent
       case already does -- `_build_framework_refs` skips emitting a `LazyAllocOp` for it
       entirely (module-level storage still declared, per `print_ftn.py`'s existing
       declaration/allocation decoupling, e.g. `ccpp_suite_state`'s own pattern at
       `print_ftn.py:1320-1327`), and generation trusts the scheme's own `.F90` to allocate it,
       exactly as `dlc_liq.F90`/`make_workspace.F90` already do today. No new capability here,
       just correcting a classification that currently does redundant, if harmless, extra work.
    2. **Chained-dimension deferral** (the actual #30 bug, and the new capability): for an
       *ordinary* SuiteOwned array (no `allocatable` flag needed at all -- indistinguishable in
       `.meta` from any other suite-owned array) whose allocation dimension's standard_name
       doesn't resolve via any of `_find_loop_upper_bound`'s existing three paths (in-scope arg,
       MODULE host table, another array's shape), add a fourth check: does this standard_name
       match another SuiteOwned var that's an `intent = out` output of some scheme within this
       *same phase's* call sequence? If so, return a deferred marker (not an SSA value) instead
       of `None`. `_build_framework_refs` queues that var as a **pending allocation** (keyed by
       its producer scheme's full name) rather than emitting its `LazyAllocOp` in the preamble.
       `_build_call_ops`'s existing per-scheme call-sequence walk (`_emit_ordered_list` and
       friends) checks, immediately after emitting each scheme's own call ops, whether any
       pending allocation's producer scheme just ran and its dimension is now in `data_ops` --
       if so, splice that var's `LazyAllocOp` in immediately after those call ops, before
       anything downstream needs the array. **No topological-sort library or general graph
       needed**: the SDF's own call sequence is already a candidate total order; walking it
       once and resolving pending allocations opportunistically as their producer's output
       becomes available *is* the topological resolution, given the call sequence order is
       assumed valid. **The validation benefit capgen-v1 itself doesn't have**: if the call
       sequence finishes with any pending allocation still unresolved, raise a clear error
       naming the var and its unmet dependency -- catching a genuinely wrong-order SDF mistake
       at generation time instead of either capgen-v1's silent trust or this repo's own
       pre-fix silent-wrong-order Fortran. **Deliberately narrow for the first cut**: if a
       pending allocation's producer scheme sits inside a `PromotionLoopOp` or `SubcycleLoopOp`
       body (nested call emission, not the flat top-level sequence), raise a clear
       "not supported yet" error rather than guessing at a splice point -- matching this
       codebase's established philosophy for genuinely-hard shapes (dispatch_scalar refs,
       unindexed multi-instance DDT array refs) -- since no real example needs the nested case
       today.
    **`.meta`/scheme-Fortran impact**: mechanism 2 needs *no* new metadata property and *no*
    change to the producing scheme's own `.F90` at all -- the array's `.meta` entry and its
    scheme's own dummy-argument declaration look exactly like the ordinary, already-working
    non-chained case; the complexity is entirely absorbed by the generator, invisible to the
    scheme author. This is the concrete form of "exceeding capgen-v1" here: real capgen-v1
    requires every scheme author needing this shape to correctly hand-author the self-allocate
    contract; this design requires nothing extra of them at all.
    **Verification plan**: extend the existing scratch fixture (scheme_c's `_register`
    produces `dim_inter`, scheme_a's own array is dimensioned by it) into a permanent
    `tests/unit/` regression test pinning the corrected allocate-after-producer-call order;
    add a negative test for the new "SDF calls the consumer before the producer" error path;
    add a regression test confirming `make_workspace`'s own preamble no longer redundantly
    pre-allocates `work` (mechanism 1); full suite + `ruff` + the standard byte-diff regen
    across the 47-file filecheck corpus (expect the *only* other example to change output at
    all is `suite_allocate`, since it's the one existing real user of primitive-type
    `allocatable`).
    **Sequencing**: no longer needs task #60's arg-resolution-unification foundation (that
    concern applied to the earlier, rejected interleaved-preamble sketch, not to this
    call-sequence-walk-based design) -- this can proceed independently of #57/#60/#28.
  - **Task #30 — RESOLVED (2026-08-19), implemented exactly per the design above.** Both
    mechanisms landed in `suite_cap.py`:
    - **Mechanism 1** (`_build_framework_refs`'s `framework_vars` loop): a primitive-type
      SuiteOwned arg with `fw_arg.hasAttr("allocatable")` now skips `LazyAllocOp` emission
      entirely -- generalizing the DDT-constituent case's own existing pattern
      (`constituent_cap.py`) rather than building new machinery. Module-level storage is still
      declared unconditionally (unchanged); only the allocation itself is skipped, trusting the
      scheme's own hand-written Fortran to self-allocate, exactly as `examples/advection/
      dlc_liq.F90` and `examples/suite_allocate/make_workspace.F90` already do. Confirmed by
      direct regeneration: `examples/suite_allocate`'s own redundant
      `if (.not. allocated(work)) allocate(work(nw))` preamble line is gone;
      `make_workspace_run`'s own call and its own internal (unseen by xdsl_ccpp) self-allocation
      are completely unaffected.
    - **Mechanism 2** (new method `_resolve_alloc_dim_var_refs`, new free function
      `_find_producer_scheme`, new dataclass `_PendingAlloc`): both of `_build_framework_refs`'s
      allocation sites (the `framework_vars` loop and the `suite_owned_vars()` sweep) now route
      through this one shared resolver. When an allocation dimension's `matching` arg is itself a
      same-phase `SuiteOwned`/`intent=out` var (a framework var whose own `data_ops` ref already
      exists unconditionally, per its own ref-creation earlier in the same loop, but whose real
      *value* isn't valid until its own producing scheme's call runs -- this codebase always
      builds the entire preamble before any call ops exist, so this can never be safe to read
      at that point), resolution returns a deferred marker instead of trusting `data_ops`. The
      var is queued in a new `pending_allocs: dict[producer_scheme, list[_PendingAlloc]]`,
      returned from `_build_framework_refs` as a third value and threaded into `_build_call_ops`.
      `_build_call_ops`'s existing `_emit_ordered_list` (used for both the flat top-level call
      sequence and, transitively, subcycle bodies via `_emit_subcycle_items`) now adds each
      scheme's own name to a `resolved_producers` set immediately after emitting its call ops,
      then retries any `pending_allocs` entries keyed to that scheme -- on success, splices a
      freshly-built `LazyAllocOp` directly into `call_ops` right there, exactly after the call
      that makes it safe. No topological sort or dependency graph was needed: the SDF's own call
      sequence, walked once, already gives the correct order once "wait for the producer" is
      respected. A **found bug while implementing**: the `suite_owned_vars()` sweep's own
      existing dedup guard (`already_allocated = {op.var_name.data for op in lazy_alloc_ops}`)
      only recognized vars already given a *real* `LazyAllocOp` by the first loop -- a var the
      first loop had just *deferred* (not yet in `lazy_alloc_ops`) was invisible to it, so the
      second loop independently rediscovered the same var and queued a *second*, duplicate
      pending allocation for it, producing two identical `allocate()` guards in the repro's own
      output. Fixed by also unioning in every var already claimed across `pending_allocs`.
      Caught immediately by manual regeneration (a real "verify, don't just reason" moment,
      not a hypothetical). If a `pending_allocs` entry is still unresolved once the entire call
      sequence has been walked (the producer's call never appeared in this phase's sequence at
      all, or -- confirmed narrower than originally scoped, see below -- it's nested inside a
      `PromotionLoopOp` body), `_build_call_ops` raises a clear `ValueError` naming the var and
      its expected producer, rather than silently emitting wrong-order Fortran -- the real
      validation benefit over capgen-v1's own silent-trust design.
    - **A pleasant surprise found while testing, better than originally scoped**: a producer
      scheme nested one level inside a `<subcycle>` body is *not* out of scope after all --
      `_emit_subcycle_items` routes its own flat scheme children through the exact same
      `_emit_ordered_list` used at the top level, so the retry/splice logic already applies
      there for free. Only a `PromotionLoopOp`-nested producer (inside `_flush_promoted`, which
      has no retry logic) remains genuinely unsupported, correctly caught by the final
      validation rather than silently mishandled.
    - **Verified**: reproduced the exact upstream shape (a scratch fixture mirroring
      `temp_calc_adjust_register`'s `dim_inter`/`temp_adjust_run`'s chained array) and confirmed
      the fix directly on generated Fortran -- the `call scheme_c_register(...)` now precedes
      `allocate(produced(dim_inter))`, which precedes `call scheme_a_register(...)`, with the
      allocate emitted exactly once. Full suite 619 passed (615 + 4 new), 1 xfailed; `ruff check`
      shows the same 2 pre-existing findings before/after (confirmed via git-stash, neither
      touched); the 47-file filecheck corpus is exercised inside that same pytest run and stayed
      byte-identical -- confirming zero behavior change for every example that doesn't hit this
      exact pattern (only `examples/suite_allocate` changed at all, via mechanism 1, exactly as
      expected). New tests in `tests/unit/test_chained_interstitial_allocation.py` (4 cases:
      allocation-after-producer ordering, exactly-once emission, the subcycle-nested-producer
      case, and `suite_allocate`'s own no-longer-redundant preamble); confirmed 3 of the 4
      actually fail against the pre-fix code via git-stash (the 4th, exactly-once, trivially
      passed pre-fix too since the old code only ever emitted one, just wrongly-placed,
      allocation -- not a coverage gap). **Not attempted**: a regression test for the final
      validation error path itself (a producer nested inside a `PromotionLoopOp`, or a call
      sequence that genuinely never calls the producer at all) -- constructing a valid,
      correctly-classified `is_promoted` fixture from scratch proved more involved than this
      pass justified; the code path is covered by direct reasoning and `py_compile`/type
      correctness, but not by a dedicated test. Flagged as a small, honest gap, not silently
      skipped.
  - **PR #83 Copilot review, addressed (2026-08-19) -- two real findings, both confirmed against
    a real example already in this repo, not hypotheticals.**
    1. **The `suite_owned_vars()` sweep (the second of `_build_framework_refs`'s two allocation
       sites) never checked `allocatable` at all**, so a var reachable only through that sweep
       -- not the `framework_vars` loop, which already had the mechanism-1 guard -- still got a
       `LazyAllocOp` scheduled, reintroducing exactly the redundant/wrong-order allocation
       mechanism 1 exists to prevent. Copilot's own example (`environ_conditions.meta`'s
       `model_times`) turned out to be real, not illustrative: it already exists at
       `examples/capgen/scheme/environ_conditions.meta`, dimensioned by
       `number_of_model_times`, itself produced by the very same scheme's very same `_init`
       call (`environ_conditions_init` does `ntimes = input_model_times; allocate(model_times(
       ntimes))` itself, confirmed by reading `environ_conditions.F90`) -- and it's marked
       `allocatable = True`. Reproducing it directly showed the bug precisely: BOTH a
       redundant `use test_host_mod, only: num_model_times` plus two separate wrong
       `allocate(model_times(...))` blocks -- one in `ddt_suite_register` keyed to the
       *host's* `num_model_times` (found via the sweep's own fallback to
       `_find_loop_upper_bound`'s MODULE-table path, since `environ_conditions`'s `_init`-only
       table isn't part of `_register`'s own `arg_tables`, yet the sweep runs for both `_init`
       and `_register`), one in `ddt_suite_initialize` keyed to the scheme's own `ntimes`
       (found via the framework_vars loop's mechanism-2 deferral) -- confirming `model_times`
       was being independently, wrongly allocated by *both* loops at once. **Fixed** by adding
       an `allocatable: bool` field to `SuiteVarEntry` (`suite_variable_model.py`, set from the
       first-writer's own arg in `_make_entry`) and skipping the sweep entirely when
       `entry.allocatable` is set -- mirroring the framework_vars loop's own existing guard,
       just expressed through the suite-wide model instead of a live arg object (the sweep
       walks `SuiteVarEntry` objects spanning every phase, not `all_args`, which is why it
       needed its own lookup path rather than reusing `fw_arg.hasAttr("allocatable")`
       directly). Verified on the real regenerated output: no `allocate(model_times...)` or
       `num_model_times` use-stub appears anywhere in the suite-cap module's own generated
       code any more (the driver/`main.F90`'s own, unrelated `test_host_mod`-side
       `model_times`/`num_model_times` references -- a *different* pair of host module vars
       with the same names, used as actual arguments when the driver calls the suite -- are
       correctly untouched). Updated 4 golden `CHECK` blocks that had pinned the old, wrong
       behavior (`tests/filecheck/examples/{completed_ir,end_to_end}/{capgen,ddthost}-xml.mlir`
       -- `ddthost` hits the identical pattern via its own copy of `environ_conditions.meta`).
       New regression test (`TestSchemeSelfAllocatedPrimitiveViaSuiteOwnedVarsSweepSkipsPreamble`
       in `test_chained_interstitial_allocation.py`, using the real `examples/capgen` files
       directly rather than a synthetic fixture, since the real one already exercises the exact
       shape), confirmed via git-stash to fail against the pre-fix code.
    2. **The unresolved-pending-allocation error message was factually wrong**: it claimed a
       producer nested inside "a promoted-dimension or subcycle loop body" was unsupported and
       told the user to make the producer run "un-nested" -- but the subcycle case already works
       (see task #30's own "pleasant surprise" note above: `_emit_subcycle_items` routes through
       the same `_emit_ordered_list` the flat case uses, and a dedicated test already asserts
       this). **Fixed**: reworded to name only `PromotionLoopOp` nesting as unsupported, and
       dropped the inaccurate "un-nested" requirement -- a subcycle-nested producer is fine, a
       promoted-dimension-nested one is not.
    Verified: full suite 620 passed (619 + 1 new)/1 xfailed; `ruff check` shows the same 3
    pre-existing findings before/after across both touched files (confirmed via git-stash,
    including a pre-existing `I001` import-order finding in `suite_variable_model.py` that
    predates this change); the 47-file filecheck corpus stayed green after the 4 golden updates
    above.
  - **Task #65, logged separately (2026-08-19) — broader allocation-dependency model, deliberately NOT
    part of #30's own scope.** While scoping #30's design, several adjacent improvements were
    raised as possible "free" side benefits of a dependency-graph approach; checked honestly
    against #30's actual bounded, per-phase design and confirmed none of them fall out of it
    automatically -- each is genuinely separate, additional work:
    1. **Cross-phase unification with `already_scheduled_allocs`.** #30's scheduler only
       reasons about ordering *within* one phase's own call sequence; the existing
       `already_scheduled_allocs` set (tracking whether an earlier phase, e.g. `_register`,
       already allocated a var so a later phase, e.g. `_run`, doesn't redundantly try again)
       is a separate, still-ad-hoc side-channel that #30 doesn't touch or replace. Folding both
       into one principled dependency model (tracking allocation state across the *whole*
       suite lifecycle, not just one phase at a time) is a real, larger undertaking.
    2. **DDT-typed interstitial coverage.** #30 touches `_find_loop_upper_bound`/
       `_build_framework_refs`/`_build_call_ops`/`suite_variable_model.py`'s *primitive*-type
       classification only. The separate `_build_module_vars` branch for `entry.is_ddt` is
       untouched -- still "genuinely untested, not just unverified" per the interstitial-
       variable gaps entry above.
    3. **Non-`real` interstitial array verification.** The scheduler likely generalizes to
       integer/logical/character arrays without code changes (`LazyAllocOp` already handles
       arbitrary kinds elsewhere), but "likely" isn't "verified" -- needs its own dedicated
       test fixture, not something #30's own test plan produces as a side effect.
    4. **Extending validation past same-phase ordering.** #30 catches a same-phase SDF-ordering
       mistake (consumer scheme listed before its producer within one call sequence); a fuller
       model could also validate cross-phase ordering assumptions the same way.
    None of these block or are blocked by #30 -- logged as its own backlog item, size TBD
    (bigger than #30's M-L; closer to the original, broader dependency-graph scope this whole
    discussion started from), deliberately deferred until #30 itself lands and proves the
    pattern out in the simpler, contained case first.
  - **Task #65 scoping, revisited (2026-08-20) -- honest downgrade after checking each of the
    4 items above against the current, post-#56/#57 code.** None of the 4 items turned out to
    need a broader dependency-graph model at all:
    1. **Cross-phase unification with `already_scheduled_allocs`** -- no forcing bug. The five
       lifecycle phases run in a fixed, generator-controlled order
       (`_generate_lifecycle_fns`, `suite_cap.py`), so a same-suite var produced in an earlier
       phase is always genuinely available by the time a later phase reads it. Unifying this
       with #30's own scheduler would be a DRY/elegance refactor, not a bug fix -- downgraded to
       "revisit only if a real need arises," folded into task #61's cleanup bucket rather than
       kept as its own item.
    2. **DDT-typed interstitial coverage** -- confirmed unrelated to the allocation-dependency
       mechanism at all: `_build_module_vars` (`suite_cap.py`) never routes a DDT-typed
       SuiteOwned var through `LazyAllocOp`/the allocation scheduler in the first place
       (`entry.is_ddt` means `needs_allocation()` is false -- a DDT interstitial is a module-scope
       non-allocatable scalar). This is a standalone test-coverage gap on DDT interstitial
       *declaration*, mis-filed under #65 by proximity, not a design task.
    3. **Non-`real` interstitial array verification** -- also just a standalone test-coverage
       task (confirm `LazyAllocOp`/the scheduler generalizes to integer/logical/character arrays
       without code changes), independent of any design work.
    4. **Extending validation past same-phase ordering** -- no realistic trigger given (1): the
       phase order is fixed and generator-controlled, not something an SDF author can get wrong.
    **Net effect: #65 as a single tracked epic doesn't hold up.** Items 2/3 are worth picking up
    opportunistically as small, bounded test-writing tasks (no design work required); items 1/4
    are deferred indefinitely with no open action. Not closed as a separate task -- folded into
    this note and the interstitial-variable-gaps entry above.
  - **Task #60, `lifecycle_cap.py`/`run_dispatch.py` arg-resolution unification -- scoped and
    RESOLVED (2026-08-20).** Read `run_dispatch.py`'s `ResolvedArgOp`/`ArgSourceKind` machinery
    (`ccpp.py:473-609`, `_build_per_suite_run_info`) and `lifecycle_cap.py`'s
    `_generate_lifecycle_fn` in full before designing anything. Findings:
    - **Full `ResolvedArgOp` unification rejected.** `lifecycle_cap.py`'s "no match" tail has
      three genuinely distinct outcomes (`ccpp_info_t` passthrough, `extra_host_arg_index`
      promotion to a real wrapper dummy arg, or a plain fallback local) that `ArgSourceKind.Block`
      doesn't distinguish -- squashing them into one `Block` case would lose real information
      rather than unify anything, the same class of false-unification #56 Stage 3 and #48 already
      declined elsewhere in this codebase.
    - **The Host/DdtMember "shared helper" half of the original plan also didn't hold up.** The
      actual path-resolution primitives (`_resolve_ddt_access_path`, `_resolve_member_subscripts`,
      `_build_ddt_resolution_maps`) are already factored into `cap_shared.py` and both files
      already call them identically (confirmed via grep). What's left divergent in each file --
      which args are DDT-matched in the first place, and durable-op-emission vs. immediate
      inline ref-construction -- is genuinely call-site-specific, not an accidental duplicate.
    - **The one real, confirmed gap:** `run_dispatch.py`'s own `_run`-dispatch input classification
      explicitly checks `std_name in cap_var_map` to resolve a cap-owned input
      (`ArgSourceKind.CapVar`); `lifecycle_cap.py`'s input-arg resolution never did the same check
      for register/init/finalize/timestep_* -- an unresolved cap-var input silently fell through
      to a fresh, uninitialized local, the same bug class as this file's own pre-existing
      DDT-member fix (`test_lifecycle_ddt_member_resolution.py`) and the opt_arg HOST-table bug.
      Confirmed latent, not live: no current example's non-`_run` phase needs this today (grepped
      every example's `.meta` for a non-run-phase arg beyond errmsg/errflg/suite_name/instance
      args; zero hits), and the function's own docstring already said as much.
    - **Fixed, narrower than first drafted.** Initial fix checked `std_name in cap_var_map`
      unconditionally (mirroring `run_dispatch.py`'s own check literally) -- caught a real
      regression against `examples/ddthost` during verification: `cap_var_map` also accumulates
      plain CapScratch *scratch* vars keyed only by `standard_name`
      (`ccpp_cap.py::_build_cap_var_map`'s `scratch_var_list` branch), and standard_name is NOT a
      reliable identity there -- `examples/ddthost`'s own `make_ddt_run` declares an intent(in)
      "vmr" (standard_name `volume_mixing_ratio_ddt`, no host match) that lands in `cap_var_map`
      as a scratch entry; a same-named but semantically unrelated intent(in) "vmr" on
      `make_ddt_timestep_final` was wrongly redirected to that scratch entry instead of getting
      its own fresh local (the correct, pre-existing behavior) -- confirmed via direct
      byte-diff against `examples/ddthost`'s real generated Fortran, not just reasoning. Narrowed
      the fix to only fire when `std_name in FRAMEWORK_STD_NAME_TO_CAP_VAR` (`ccpp_constituents`,
      `ccpp_constituent_tendencies`, `number_of_ccpp_constituents`) -- the one class where "same
      standard_name" is a real design guarantee (always the one shared, always-declared framework
      array), not a coincidence. Also gated to `intent in ("in", "inout")` only, via a new
      `intent_of` dict built alongside the existing `std_name_of` scan -- an intent(out)-only arg
      (e.g. `environ_conditions_init`'s own "o3"/"hno3" outputs, real args in this same example)
      needs a fresh writable local exactly as before; the ungated version, before the intent fix,
      also briefly mis-resolved these the same way, caught by the same ddthost byte-diff.
    - **Verified:** new regression test
      (`tests/unit/test_lifecycle_capscratch_input_resolution.py`), confirmed via git-stash to
      fail against the pre-fix code; since the real bug is latent (no example naturally populates
      `cap_var_map` with a non-`_run`-consumed entry), the test monkeypatches
      `ccpp_cap.py::_build_cap_var_map` to inject one, isolating the resolution fix itself from
      the separate question of how `cap_var_map` gets populated -- documented explicitly in the
      test's own docstring so this isn't mistaken for full coverage of the population path. Full
      suite 605 passed (603 + 2 new) plus the pre-existing, unrelated `python3`-subprocess PATH
      environment failures (confirmed identical via git-stash); `ruff check` clean before and
      after; byte-identical regeneration confirmed directly on `examples/ddthost` (the one example
      that actually exercises this code path, and the one that caught the regression) plus the
      full 47-file filecheck corpus via the same pytest run.
  - **Done (2026-08-17):** restored the real `interstitial_var` argument into `examples/capgen`'s
    `temp_adjust.meta`/`.F90` (`temp_adjust_run` produces it `intent(out)`,
    `temp_adjust_finalize` consumes it `intent(in)` -- genuinely cross-phase, separate generated
    Fortran subroutines), deliberately dimensioned by `horizontal_dimension` rather than
    upstream's chained `dimension_for_interstitial_variable`, to prove the working mechanism on
    a real example without depending on the separately-tracked ordering bug above. Verified on
    the real regenerated output: `interstitial_var` gets correct module-level allocatable
    storage, a `LazyAllocOp` guard that runs during `_register`/`_initialize` (sized from a real
    host array's shape via `_find_loop_upper_bound`, same mechanism `to_promote` already used),
    and `temp_suite_finalize` correctly references the same already-allocated module
    variable with no re-allocation attempt. `temp_adjust_run`'s Fortran body sets
    `interstitial_var = 6` (ported from capgen-v1's own test logic); `temp_adjust_finalize`
    checks `interstitial_var(1) /= 6` and errors if not, proving the value survives the gap
    between the two separate calls. Added `tests/unit/test_interstitial_variable.py`: an
    isolated two-scheme/one-host fixture (independent of `examples/capgen`'s own DDT/multi-suite
    complexity) asserting the module-level declaration, allocate-before-producer-call ordering,
    and cross-phase consumption -- the regression coverage that didn't exist before. Also
    confirmed, empirically, that the rank re-sync below eliminated `temp_adjust_run`'s own
    per-vertical-layer promotion-loop dispatch entirely: once its own args are genuinely 2D
    (matching the caller's arrays), no slicing/promotion is needed at all -- one direct call
    with the whole array, exactly matching real capgen-v1's own dispatch shape (its
    `temp_adjust_run` does its own internal `do col_index = 1, foo` loop, never externally
    sliced). Full suite: 577 passed (574 + 3 new), 1 pre-existing unrelated environment failure
    deselected, 1 xfailed.
  - **Not done, deliberately deferred:** (1) the narrow `col_start`/`col_end`-only sizing
    fallback (no current real example needs it); (2) DDT-typed and non-`real` interstitial
    spot-checks (still genuinely unexercised); (3) the chained-dimension case itself, tracked as
    its own item above.
- **`temp_adjust`/`temp_calc_adjust`/`temp_set` rank/dimensionality re-sync to real upstream —
  Done (2026-08-17), S as scoped.** `examples/capgen`'s ported `temp_set.meta` already matched
  upstream's dimensionality exactly; `temp_adjust.meta` did not: upstream's
  `temp_prev`/`temp_layer`/`qv`/`to_promote` are all `(horizontal_dimension,
  vertical_layer_dimension)`, 2D; the port had flattened them to `(horizontal_dimension)` only,
  1D. Confirmed this wasn't a real xdsl-ccpp capability gap forcing the simplification: 2D
  optional real arrays already worked correctly (`examples/var_compat`'s own `effrg_in`, the
  exact pattern the unit-conversion buffer-allocate fix above was verified against) -- so
  restoring the real ranks was a mechanical `.meta` + `.F90` dimension/declaration change, not
  new generator work, confirmed by direct regeneration with zero xdsl_ccpp code changes needed.
  Also dropped the stray `state_variable = true` on `ps`, which upstream's `temp_adjust.meta`
  doesn't set.
  - **One additional divergence found while restoring, not in the original scope note:**
    `temp_calc_adjust.meta`'s own `temp_calc` output (matched by standard_name
    `potential_temperature_at_previous_timestep` against `temp_adjust_run`'s `temp_prev`) was
    *also* still 1D in our port (upstream's is 2D too) -- since `temp_adjust_run`'s `temp_prev`
    is now 2D, leaving `temp_calc` at 1D would have been a genuine rank mismatch between a
    scheme's own declared output and its consumer's now-2D input (an invalid Fortran
    assumed-shape actual/dummy rank mismatch). Fixed the same way, in both
    `temp_calc_adjust.meta` and `.F90`.
  - **Verified directly on regenerated output**, and found a genuinely pleasant side effect:
    with `temp_adjust_run`'s own args now truly 2D (matching its caller's arrays), the generator
    no longer needs a per-vertical-layer promotion loop to slice them down to 1D before calling
    it -- the whole call collapsed to one direct invocation with the full arrays, which is
    exactly real capgen-v1's own dispatch shape (`temp_adjust_run` does its own internal
    per-column loop, never externally sliced/promoted). Updated
    `tests/unit/test_optional_args.py::TestSuiteCapDeclaration::test_qv_is_array` (asserted the
    old 1D shape) and the `frontend`/`completed_ir`/`end_to_end` capgen-xml.mlir filecheck
    goldens to match. Full suite: 577 passed, 1 pre-existing unrelated environment failure
    deselected, 1 xfailed.
- **Metadata `dependencies`/`dependencies_path`/`source_path` tracking — Tier 1 done (2026-08-17).**
  Real capgen-v1's own three-key convention (`metadata/metadata_table.py`'s
  `MetadataTable.apply_table_props`): `source_path` locates a scheme's real `.F90`
  relative to its `.meta` file; `dependencies` lists extra source files a scheme
  needs; `dependencies_path` is the base directory for resolving `dependencies`
  entries. All three feed a generated `datatable.xml` real capgen-v1's own build
  system reads to auto-discover what to compile -- no human hand-lists dependency
  files in a real capgen-v1 build script.
  - **xdsl-ccpp's prior state, confirmed broken, not just incomplete:**
    `dependencies` was accepted by the parser but never forwarded into IR or used
    anywhere -- a pure no-op. `source_path` wasn't even in the allow-list --
    any real `.meta` file declaring it crashed the parser (confirmed: this is
    exactly why the ported `examples/capgen/scheme/temp_set.meta` silently
    dropped its real upstream `source_path = source_dir2` line during the
    port, same silent-drop pattern `kind_spec` had). `relative_path` -- a key
    **xdsl-ccpp invented**, not real capgen-v1's -- was accepted in its place;
    confirmed it was actually holding upstream's `dependencies_path` *value*
    under the wrong name (`temp_adjust.meta`'s real `dependencies_path = adjust`
    became the port's `relative_path = adjust`, identical value, wrong key).
    No `datatable.xml`-equivalent exists in xdsl-ccpp at all -- every example's
    CMakeLists.txt hand-lists scheme `.F90`/dependency files directly.
  - **Deliberately no behavior change to generated Fortran/C++**, unlike
    `kind_spec`: these three keys are pure build-tooling metadata with zero
    downstream consumer today (unlike `kind_spec`, which fixed a real
    wrong-kind bug in generated code). This fix's value is fixing the
    `relative_path` naming bug, no longer crashing on `source_path`, and
    restoring metadata fidelity to match upstream text -- not new generated
    output.
  - **What Tier 1 does:** `ccpp_xml.py`'s `CCPPTableProperties` now accepts
    the real key names (`source_path`, `dependencies_path`, dropping
    `relative_path` entirely) and accumulates `dependencies` into a list
    across possibly-multiple `dependencies = ...` lines (each itself
    optionally comma-separated), skipping the `"none"` sentinel -- mirroring
    real capgen-v1's own accumulation and sentinel handling exactly. Forwarded
    onto `TablePropertiesOp`'s IR attributes from both `.meta`-parsing
    frontends (`ccpp_xml.py`'s `build_meta_ir` and `py_api.py`'s
    `_table_properties_op`/`SchemeDescriptor`/`TableDescriptor`, via a new
    shared `_dependencies_kwargs` helper to avoid tripling the three
    optional-attribute ternaries across `ccpp_scheme_from_meta`/
    `ccpp_host_from_meta`/`ccpp_ddt_from_meta`). Also fixed the identical
    `relative_path` naming bug in `transforms/util/ccpp_descriptors.py`'s own,
    separate `CCPPTableProperties` class (the internal IR→descriptor
    reconstruction used by `suite_cap.py` etc. via `self.meta_data`) for
    consistency, though nothing populates these three fields there yet either
    (deliberately not extended -- no consumer needs `self.meta_data` to carry
    them; a future consumer, following `kind_spec`'s own precedent, would
    most likely read straight off `TablePropertiesOp.attributes` the way
    `suite_kinds.py`'s `MetaKind` pass already does for `kind_specs`, not
    through this reconstruction layer).
  - **Restored on a real example, and found a second real bug while doing
    it.** `examples/capgen/scheme/temp_set.meta`/`temp_adjust.meta` now
    declare `dependencies = temp_kinds.F90` (a genuine, applicable
    dependency, matching upstream's own logical intent -- not
    `dependencies_path`-adjusted subdirectory paths like upstream's literal
    text, since this port deliberately flattened `temp_kinds.F90` directly
    into `examples/capgen/scheme/` with no subdirectories at all; restoring
    upstream's literal `adjust`/`source_dir2` path text would have pointed at
    directories that don't exist in this checkout). `temp_calc_adjust.meta`'s
    `dependencies = foo.F90, bar.F90` -- confirmed via `find` that neither
    file exists anywhere in the repo -- was a **synthetic placeholder someone
    added purely to exercise comma-separated multi-value parsing**, not a
    real upstream value (real upstream's own `dependencies` for this table is
    empty); restored to match upstream (empty) now that
    `tests/unit/test_dependencies_source_path.py` covers the multi-value case
    directly instead.
  - **Second finding, not part of Tier 1, logged as its own item above:**
    `examples/ddthost` has its own, independent copies of
    `temp_set.meta`/`temp_adjust.meta`/`temp_calc_adjust.meta` (confirmed via
    `diff` against `examples/capgen`'s copies) that predate *all* of this
    session's fixes to these files -- missing `kind_spec`, `interstitial_var`,
    the 2D rank re-sync, and even a `temp_adjust_register` entry point
    `examples/capgen`'s copy has. Not touched here -- syncing them is a
    distinct, separable task, not part of restoring dependencies/source_path
    parsing.
  - **Regression hotfix (2026-08-17), found via a real CI build failure:**
    `examples/ddthost/scheme/temp_adjust.meta` still declared the old, just-
    removed `relative_path = adjust` key, and `examples/ddthost`'s own
    CMakeLists.txt (`examples/ddthost/CMakeLists.txt:27`, the "plain"
    generation target) passes `temp_set.meta`/`temp_calc_adjust.meta`/
    `temp_adjust.meta` straight into real cap generation -- a live build
    path that, unlike `examples/capgen`'s copies, has **no filecheck or unit
    test coverage at all** (confirmed: `ddthost-xml.mlir`'s own frontend
    filecheck only exercises `make_ddt.meta`/`environ_conditions.meta`), so
    the 591-test run done for Tier 1 never touched it and the crash only
    surfaced in CI. This is exactly the "ddthost's copies have fallen behind"
    finding above, just discovered the hard way. Fixed the immediate crash by
    removing the invalid key and, matching the same real-vs-fabricated
    judgment call made for `examples/capgen`'s copies, cleared
    `temp_adjust.meta`'s `dependencies = qux.F90` (nonexistent file; unlike
    `examples/capgen`'s `temp_adjust.meta`, ddthost has no `temp_kinds.F90`
    counterpart to point to instead, since ddthost doesn't have `kind_spec`
    support ported yet either) and `temp_calc_adjust.meta`'s
    `dependencies = foo.F90, bar.F90` (also nonexistent) to `dependencies =`,
    matching real upstream's own empty declaration. Verified by reproducing
    the exact `examples/ddthost/CMakeLists.txt:27` frontend invocation
    directly (all six plain-target scheme files plus both suites) -- exits 0
    now, was crashing with the reported `AssertionError` before. Full
    suite re-run: 591 passed, 1 xfailed, 1 environment-only failure
    (`test_ccpp_xdsl_generates_caps`, pre-existing and unrelated -- fails with
    `pyenv: ccpp_xdsl: command not found` when the console-script entry point
    isn't installed on `PATH` in this shell, not a code issue). This hotfix
    does **not** close out the broader ddthost-sync backlog item above --
    `kind_spec`/`interstitial_var`/rank-resync/`temp_adjust_register` are
    still missing from ddthost's copies and remain deferred to that task.
  - **Task #33 detailed scoping (2026-08-24), not started -- upgraded from S-M to M.** Read
    real `diff`s against `examples/capgen`'s current copies (not just the summary above) and
    found more surface area than the original one-line description captured, plus a real
    cross-file coupling:
    - **`temp_set`**: beyond `kind_spec`, capgen's copy also adds four variables the original
      description never mentioned -- `temp_diag` (new 2D array), `slev_lbound` (a new scalar),
      `soil_levs` (a new array using a *bound-expression* dimension,
      `lower_bound_of_vertical_dimension_of_soil:upper_bound_of_vertical_dimension_of_soil`, not
      just a plain size), and `var_array` (a new 4D array). None of `ddthost`'s host files
      (`host_ftn/test_host_data.meta`, `host_ftn/test_host_mod.meta`) declare matching host
      variables for any of these -- confirmed via grep -- so this needs real host-side
      additions, not just a scheme-file copy. Independent of `temp_adjust`/`temp_calc_adjust`.
    - **`temp_calc_adjust` + `temp_adjust` are coupled, not two separate mechanical edits.**
      `temp_calc_adjust`'s `temp_calc` (intent=out) and `temp_adjust`'s `temp_prev` (intent=in)
      share the exact same standard_name, `potential_temperature_at_previous_timestep` --
      confirmed directly in both `.meta` files -- so capgen's 1D->2D rank change on this value
      had to land in both files atomically; they can't be staged independently, or host/scheme
      rank matching breaks mid-way. `temp_adjust` also separately adds: the new
      `temp_adjust_register` entry point (with its own `config_var` arg, needing a host-side
      addition `ddthost` doesn't have yet, and a module-level `module_level_config` state
      variable gating `_run`'s own behavior); the `interstitial_var` producer/consumer chain
      (produced in `_run`, consumed in `_finalize` -- not host-matched at all in capgen's own
      host files, so likely no host-side addition needed for this one); and `kind_temp` on
      `to_promote` (paired with `temp_set`'s own `kind_spec` need -- both need
      `examples/ddthost/scheme/temp_kinds.F90`, which doesn't exist yet, ported verbatim from
      capgen's copy, a tiny shared prerequisite for either stage's `kind_spec` piece).
    - **Not expected to touch `xdsl_ccpp/` generator source at all.** Every construct being
      ported -- `kind_spec`, a bound-expression-dimensioned array, a 4D array, a `_register`
      entry point, the interstitial-variable chain, rank changes -- already works in capgen's
      own copy of these files today, which passes real generation and `capgen_ftn_host.exe`'s
      own ctest. This is applying already-proven patterns to a second example, not new
      generator capability. (Caveat: this session repeatedly found real generator bugs when a
      *specific combination* of already-working features got exercised together for the first
      time in a new example -- e.g. the Stage 3 subcycle/init-dispatch bugs, the capgen driver
      `State` constructor bug -- so this is the expected scope going in, not a guarantee.)
    - **Real staging, given the coupling above: a tiny shared prerequisite plus 2 stages, not
      3 independent per-file edits.** (1) Port `temp_kinds.F90` verbatim, wire into
      `examples/ddthost/CMakeLists.txt`. (2) `temp_set` alone: `kind_spec` + the 4 new
      variables + matching `ddthost` host-side additions -- independently verifiable via
      regeneration + the real `ddthost_ftn_host.exe` ctest. (3) `temp_calc_adjust` +
      `temp_adjust` together: the coupled rank re-sync, `temp_adjust_register`/`config_var`
      (+ host-side addition), `interstitial_var`, `kind_temp` on `to_promote` -- also
      independently verifiable, but must land as one unit given the shared standard_name.
    - **Deliberately not started.** The project owner is prioritizing items that either block
      starting CAM-SIMA testing or are small, low-risk cleanups; this is neither (real M-sized
      scheme/host work spanning two examples, no urgency). Left as a fully-scoped backlog item
      for whenever it's picked up.
  - **RESOLVED (2026-09-29), via PR #104.** Implemented the prerequisite (`temp_kinds.F90`
    ported verbatim) and both stages exactly as scoped above: `temp_set` gained `kind_spec` plus
    the four new variables (`temp_diag`, `slev_lbound`, `soil_levs`, `var_array`), with matching
    host-side additions in `test_host_data.meta`/`test_host_mod.meta`; `temp_calc_adjust` +
    `temp_adjust` landed together as one unit (2D rank re-sync on the shared
    `potential_temperature_at_previous_timestep` standard_name, the `temp_adjust_register` entry
    point + `config_var` host addition, the `interstitial_var` producer/consumer chain, `kind_temp`
    on `to_promote`) -- `ddthost`'s pre-existing `ps` `state_variable = true` addition was
    deliberately preserved rather than dropped while merging in capgen's changes.
    - **Two real bugs found and fixed during CI verification, both distinct from the scoped port
      itself.** (1) `test_host_mod.F90`'s `init_data()` read `cind` uninitialized before its first
      use (undefined behavior identically present in `examples/capgen`'s own copy, not something
      the port introduced) -- confirmed against real upstream `capgen-v1`
      (`origin/feature/capgen-v1:end-to-end-tests/capgen/test_host_mod.F90`, fetched into the
      `ccpp-framework` checkout) that upstream explicitly sets `cind = 1` before the loop; fixed
      identically in both examples' copies to match upstream's literal structure, not just its
      numerical effect. (2) `examples/ddthost/host_ftn/test_host.F90` never called the newly
      generated `ccpp_register` entry point at all (a straight omission in the port -- `examples/
      capgen`'s own driver does call it) -- so `temp_adjust_register` never ran,
      `module_level_config` stayed `.false.`, and `temp_adjust_run` silently took its no-op early
      return every time, producing runtime answers off by a uniform, timestep-count-scaled
      constant offset in both `temp_midpoints` and the first constituent's `q`. Fixed by adding the
      missing `use`/call, matching `ddthost`'s own `ccpp_info_t`-bundled calling convention (not
      capgen's separate errmsg/errflg-argument convention).
    - **Verified:** both `ddthost_ftn_host.exe` and `ddthost_cxx_host.exe` build and run clean
      (`ctest_ddthost_ftn_host`/`ctest_ddthost_cxx_host` pass), and `capgen_ftn_host.exe`/
      `capgen_cxx_host.exe` still pass unaffected by the shared `cind` fix. Regenerated the
      `frontend`/`completed_ir` `ddthost-xml.mlir` filecheck goldens (purely additive lines for the
      new host variables, reviewed before accepting -- `end_to_end`/both `-py.mlir` variants were
      unaffected). Full suite: 709 passed, 1 xfailed.
  - **Verified:** regenerated `examples/capgen`'s frontend/completed_ir/end_to_end
    output directly -- `dependencies`/`source_path`/`dependencies_path` are
    only ever visible at the frontend (pre-pass) stage; `strip-ccpp` removes
    the whole `ccpp.table_properties` op (and its attributes) before
    `completed_ir`/`end_to_end` output, so only frontend-stage filecheck
    goldens needed updating (`capgen-xml.mlir`, and `var_compat-xml.mlir` --
    `examples/var_compat`'s own `rad_lw.meta`/`test_host_data.meta` already
    had real `dependencies = module_rad_ddt.F90` declarations that were
    silently dropped before this fix and are now correctly visible). New
    tests: `tests/unit/test_dependencies_source_path.py` (single/comma-separated/
    repeated/empty/`"none"`-sentinel `dependencies` parsing, `source_path`/
    `dependencies_path` acceptance, and a negative test confirming
    `relative_path` no longer parses at all). Full suite: 591 passed (583 + 8
    new), 1 pre-existing unrelated environment failure deselected, 1 xfailed.
  - **Tier 2, not attempted, logged as its own item above:** actually emitting
    a dependency manifest and teaching `cmake/xdsl_ccpp_capgen.cmake` to
    consume it (so CMakeLists.txt stops hand-listing dependency files) is real
    automation value but overlaps architecturally with the "CMake cap
    generation runs at configure time" item below -- both are about how CMake
    and the Python generator discover file lists from each other, and would
    be worth designing together rather than separately if ever tackled.
- **`advection`'s error-path bonus, found while confirming the core suite was a duplicate --
  RESOLVED (2026-08-18, task #10).** Real capgen-v1 has a deliberate negative test
  (`dlc_liq`/`cld_suite_error.xml`): declaring a `ccpp_constituent_properties_t`-typed arg outside
  the register phase must error. Confirmed xdsl-ccpp had **no such check** -- and the actual
  failure mode was worse than a silent no-op. `constituent_cap.py`'s own dynamic-constituent scan
  (`_collect_constituent_info`, gated on `table_name.endswith("_register")`) and
  `suite_variable_model.py`'s allocatable-DDT skip (the "DDT allocatable arrays ... passed as
  arguments by the ccpp cap" branch, right after the host-matched Case 1 check) both silently
  ignore any `ccpp_constituent_properties_t` arg outside `_register` -- so regenerating the real
  `dlc_liq` (`_init` phase) + `cld_liq` (`_register` phase) fixture end-to-end showed `dlc_liq`'s
  own `dyn_const` bare local name (coincidentally identical to `cld_liq`'s own `_register`-phase
  `dyn_const` arg) get silently wired to `cld_liq`'s *already-registered* module-level constituent
  array by bare-name match alone, in the wrong lifecycle phase -- active data corruption, not just
  a dropped arg. Fixed in `host_var_match_pass.py`'s `_match_and_validate`, right where the
  existing `if arg_op.allocatable is not None: continue` guard already skips these args for
  host-matching: now also raises (folded into the existing collected-`all_errors`/single-`ValueError`
  pattern) when the arg's type is `ccpp_constituent_properties_t` and its own entry-point table name
  doesn't end in `_register`. New tests in `tests/unit/test_host_var_match.py`
  (`TestConstituentPropertiesOutsideRegisterPhase`), confirmed via git-stash to fail without the
  fix. Also ported real capgen-v1's *other* deliberate advection negative/edge case while here:
  `cld_shadow`, a scheme whose own local arg names (`cld_ice_array`, `ncols`) coincide with names
  already used elsewhere in the group cap for unrelated standard_names (GitHub issues #772/#774).
  Regenerating `examples/advection` with `cld_shadow` added surfaced a **second, independent real
  bug**: `suite_variable_model.py`'s `_resolve_name_collisions` only ever compared SuiteOwned
  entries against each other, never against a MODULE-type host variable's own bare name that the
  same suite already `use`-associates -- so `cld_shadow`'s own unrelated "ncols" scratch var
  produced a literal duplicate `real ... :: ncols(:)` declaration alongside
  `use test_host_mod, only: ncols` in the same module scope (invalid Fortran). Fixed by tracking,
  per-suite, the bare names of MODULE-type host matches this suite's own schemes actually resolve
  (via the same Case 1 loop, not a blanket whole-metadata scan -- an earlier, over-broad version of
  this fix false-triggered on `examples/capgen`'s `environ_conditions`/`model_times`, a scheme's own
  allocatable output that shares a standard_name, but not a Fortran module scope, with an unrelated
  host module var of the same name) and reusing the existing rename-on-collision logic against that
  set too. New test in `tests/unit/test_suite_arg_name_collision.py`
  (`TestSuiteOwnedCollisionWithModuleVar`), confirmed via git-stash to fail without the fix. Added
  `cld_shadow.F90`/`.meta` (wired into `cld_suite.xml`/`CMakeLists.txt`/`README.md`) and
  `dlc_liq.meta`/`cld_suite_error.xml` (fixture-only, matching upstream's own "not part of the
  main build" treatment) to `examples/advection`; updated all 3 existing advection filecheck
  goldens (`frontend`, `completed_ir`, `end_to_end`). Verified byte-identical via git-stash across
  all 26 other end_to_end filecheck examples (including `capgen`, the one that would have caught
  the over-broad false positive) and the full unit suite -- 611 passed/1 xfailed, `ruff check`
  clean on both touched production files.
- **Retire the legacy `horizontal_loop_extent` vocabulary — migrated 2026-07-27.** xdsl-ccpp
  supported two parallel conventions for "how many columns is this call processing": the older
  `horizontal_loop_extent` (a scheme-declared scalar synthesized into `col_start`/`col_end` via
  `suite_cap.py`'s `_classify_args`) and capgen-v1's current, sole convention,
  `horizontal_dimension` (the array-dimension name itself, resolved via `run_dispatch.py`'s
  host-declaration-driven fallback). All nine examples still using the old name
  (`advection`, `advection_flat_host`, `capgen`, `chararg`, `constadv`, `constprop`, `ddthost`,
  `helloworld`, `kessler`) have been renamed onto `horizontal_dimension`, verified against a full
  FileCheck + unit suite run after each stage (only pre-existing, unrelated failures remain: the
  `test_ccpp_xdsl_generates_caps` build-integration test, which fails identically on unmodified
  `main`). `helloworld`'s Python-frontend example (`helloworld_py.py`) was extended with real
  host-descriptor loading (`ccpp_host_from_meta`, matching the pattern already used by
  `kessler_py.py`/`advection_py.py`/`ddthost_meta_py.py`) so its goldens stay in sync with the
  XML-frontend ones rather than silently diverging in test coverage.
  - **Two real generator bugs found and fixed along the way, both in
    `suite_cap.py`'s `_build_promoted_call_ops`** (the per-vertical-level scheme-call promotion
    loop, exercised by capgen's `temp_adjust` call in `temp_suite_physics2`): (1) a `KeyError`
    on `data_ops["ccpp_lbound_one"]` — that key was only ever populated by the legacy
    `_classify_args` → `_build_ncol_compute_ops` path (triggered by a scheme declaring
    `horizontal_loop_extent` directly), so any scheme reaching this promotion code under the new
    convention crashed outright; fixed by lazily creating the constant-1 alloca on first use
    instead of assuming it was pre-populated. (2) A silent wrong-value bug one layer deeper: the
    slice's column-range upper bound fell back to `data_ops.get("ncol", loop_var_memref)`, and
    since `"ncol"` is never in `data_ops` under the new convention, it silently substituted the
    *promotion loop's own vertical-layer index* as the column count — producing a slice range
    that grows with the loop (`qv(1:vertical_layer_index, vertical_layer_index)`) instead of the
    real column range (`qv(1:ncol, vertical_layer_index)`). This one produced syntactically valid
    but numerically wrong Fortran with no crash, so it would have shipped silently without direct
    inspection of the generated output. Fixed by resolving the real column count via the
    existing `_find_loop_upper_bound` helper (already used to resolve the promoted dimension's
    own upper bound) against `CCPP_HORIZ_DIM_STD_NAME`, threaded into `_build_promoted_call_ops`
    as a new `ncol_ref` parameter. Regression coverage:
    `tests/unit/test_optional_args.py`'s new `TestPromotedArgsOnHorizontalDimension` class
    (sabotage-verified against both bugs). Also fixed one now-stale assertion in the same file
    (`test_optional_args.py`'s old `test_suite_call_includes_col_start_and_col_end`, renamed
    `test_physics_run_declares_col_start_and_col_end`) that assumed `col_start`/`col_end` are
    always forwarded from the top-level dispatch into the suite-level call — no longer true now
    that capgen's schemes resolve their own per-call column count internally.
  - **Not part of this migration, tracked separately:** retiring the actual legacy
    `CCPP_LOOP_EXTENT_STD_NAME` code paths in `xdsl_ccpp` itself (`ccpp_conventions.py`,
    `cpp_interop.py` — including its C++-side fallback naming preference, `run_dispatch.py`,
    `ccpp_cap.py`, `suite_cap.py`'s own now-provably-dead-for-every-example
    `_classify_args`/`_build_ncol_compute_ops` synthesis path) now that no example anywhere in
    the repo references the old name — needs its own investigation to confirm what's safely
    deletable. A full re-sync of `advection`/`capgen`/`ddthost` to capgen-v1's exact current
    upstream state (rank changes, missing entry points, `kind_spec`/`dependencies_path`/
    `source_path` metadata-parser support) is also explicitly out of scope here — a separate,
    larger effort.
  - **Update (2026-08-13): the "needs its own investigation" note above is now partly
    addressed — not by deleting the legacy code paths, but by gating them behind an opt-in
    `--legacy-mode` flag, matching real capgen-v1's own precedent (`capgen/ccpp_capgen.py`'s
    three legacy shims — `--legacy-mode`, `--gfs-dim-aliases`, `--legacy-auto-clone-constituents`
    — all off by default, all self-contained/deletable).** Prompted by a broader vocabulary
    sweep (task-tracking backlog item #13) confirming zero current examples use
    `horizontal_loop_extent`, plus a live concern that xdsl-ccpp's simultaneous support for both
    the deprecated and current standard-name conventions was itself a source of bugs (several
    found and fixed this session trace back to exactly this dual-support surface — see the
    `constituents_dim` entry above).
    - **What changed:** `ArgumentOp.__init__` (`xdsl_ccpp/dialects/ccpp.py`) now raises `ValueError`
      by default when a deprecated standard_name (currently just `horizontal_loop_extent`) is
      declared, instead of only warning. A new `set_legacy_mode`/`is_legacy_mode` pair
      (`ccpp_conventions.py`, a process-global rather than a threaded parameter — `ArgumentOp` is
      constructed from dozens of call sites across three independent frontends) downgrades this
      back to the original warn-and-accept behavior. `--legacy-mode` was added to all three
      frontends' own CLI surfaces: `ccpp_dsl.py` (the main entry point — sets the flag before any
      op is built, and forwards it into whichever subprocess it spawns), `frontend/ccpp_xml.py`
      (its own argparse, since it always runs as a subprocess), and `frontend/py_api.py` (no
      argparse of its own — scans `sys.argv` directly for the bare token, mirroring the existing
      `ccpp_param()` convention in that same file).
    - **Investigation finding, not yet acted on:** the downstream machinery this flag actually
      gates — `suite_cap.py`'s `_build_ncol_compute_ops`/`ncol_meta` host-fallback/`physics_mode`
      col_start/col_end synthesis, `run_dispatch.py`'s CAM-SIMA-specific fallback,
      `cpp_interop.py`'s `is_ncol` checks, `host_var_match_pass.py`'s `dims_compatible` equivalence
      class — turned out to be real, distinct column-chunking functionality
      (`col_end - col_start + 1`), not simply duplicate vocabulary for the same thing. Confirmed via
      `suite_cap.py`'s own comments citing CAM-SIMA fixtures that depend on it. That means this
      flag does **not** shrink or consolidate that code — it only fences it off behind an explicit,
      testable, opt-in boundary. Real consolidation (rewriting at the `ArgumentOp` boundary the
      way capgen-v1's own shim rewrites the name away entirely) is only safe if the chunking
      semantics really are equivalent to the `horizontal_dimension` path — unverified, and blocked
      on re-validating the CAM-SIMA/loop-chunking parity work against the current capgen-v1 tip
      (tracked separately; see Index).
    - **Task #18 investigation (2026-08-24): traced all 4 files, corrected an earlier premise.**
      `cpp_interop.py`'s `is_ncol` and `host_var_match_pass.py`'s `dims_compatible`/
      `CCPP_HORIZONTAL_DIMENSIONS` were already properly unified — both treat
      `horizontal_loop_extent`/`horizontal_dimension` as one concept, no duplication there, nothing
      to fix. `suite_cap.py`'s `ncol_meta` synthesis (`_classify_args`) and `run_dispatch.py`'s
      array-section-slicing genuinely do have separate code paths for the two names (a narrower
      single-dimension branch for `horizontal_loop_extent` vs. a fully general multi-dimension one,
      `_resolve_extra_dim_bounds`, for `horizontal_dimension`) — confirmed via `grep` that **zero**
      examples in this repo's own `examples/` directory declare `horizontal_loop_extent` anywhere
      anymore, so these branches are only reachable under `--legacy-mode`, and the run_dispatch.py
      comment justifying keeping them separate cited `examples/advection` specifically, which has
      since migrated off it — that citation had gone stale. **Initially concluded this meant the
      legacy branches were dead code, safe to consolidate — corrected by the project owner**: real
      CAM-SIMA still uses this exact convention. Confirmed directly against the CAM-SIMA-fresh
      checkout: `test/unit/python/sample_files/write_init_files/temp_adjust.meta` (and
      `temp_adjust_scalar.meta`) declare `horizontal_loop_extent` both as a scalar arg
      (`standard_name = horizontal_loop_extent`) and as an array dimension
      (`dimensions = (horizontal_loop_extent, vertical_layer_dimension)`) — exactly the two code
      paths in question. This repo has no vendored fixture exercising it, but CAM-SIMA's own
      `test/unit/python/test_write_init_files.py` does (the same harness Workstream 2's DDT-
      redefinition fix, above, was verified against) — so a real regression-test path exists, just
      not inside this repo. **Decision: defer any actual consolidation until a CAM-SIMA-backed
      fixture exists in this repo to test against locally** — theoretically safe (the
      `horizontal_dimension` branch's general multi-dim logic is a strict superset of the
      single-dim-only legacy branch), but not worth touching working code against only a synthetic
      fixture when a real external consumer depends on it. Fixed the stale `examples/advection`
      citation in `run_dispatch.py`'s own comment (`_build_array_section_ops`, near
      `CCPP_LOOP_EXTENT_STD_NAME`) to record this finding directly at the code site. No functional
      change; full suite still 628 passed/1 xfailed/0 failed.
    - **Regression scope, once the default flipped:** far larger than the 9-file grep for the
      standard-name string suggested. 103 unit tests across 18 files failed immediately — not
      incidental naming, but *deliberate* regression coverage for the legacy path itself, written
      specifically to catch bugs found while migrating `capgen`/`ddthost` off it (one file's own
      comment: "Phase 3: same scenario, but on the current `horizontal_dimension` convention
      instead of the legacy `horizontal_loop_extent` one"). Fixed by adding `legacy_mode`/
      `legacy_mode_module` pytest fixtures (`tests/unit/conftest.py`) and applying them via
      `pytestmark` to each affected file — deleting or renaming these tests' fixtures would have
      thrown away real coverage for exactly the mechanism this flag exists to protect.
      Separately, 7 FileCheck fixtures needed the same triage: `language_suite.py` and the
      `language_cxx` scheme `.meta` pair used the deprecated name purely incidentally (no host
      file, no chunking involved) and were migrated to `horizontal_dimension`; `array_layout_suite.py`,
      the `chost_r3` fixtures, and (initially assumed incidental, then proven otherwise —
      renaming it changed the expected generated signature from
      `col_start, col_end, lev, errmsg, errflg` back to a bare `ncol`) `kw_override_suite.py` were
      all deliberately exercising the legacy no-host-match/chunking mechanism and got
      `--legacy-mode` added to their `RUN:` lines instead, left otherwise untouched.
    - **CAM-SIMA caveat, explicitly flagged rather than resolved:** CAM-SIMA is reportedly
      mid-conversion to capgen-v1 itself, so its own use of `horizontal_loop_extent` may already
      be stale relative to its own upstream defaults — the decision to default `--legacy-mode`
      off (matching capgen-v1's current strict posture) was made on that basis, not on a confirmed
      re-check of CAM-SIMA's actual current requirements. If a CAM-SIMA-driven build breaks on
      this default, `--legacy-mode` is the immediate workaround; whether that's a permanent
      accommodation or a sign the chunking mechanism should be revisited is exactly the still-open
      investigation above.
    - **Verification:** full suite green after both the flag work and the two test-fixture
      fixes — `tests/unit` + `tests/filecheck` together, 554 passed, 1 xfailed (pre-existing,
      unrelated — the rank-3 chost issue), 1 failed (pre-existing, unrelated —
      `test_build_integration.py` invokes the `ccpp_xdsl` console script, which on this laptop
      resolves via PATH to a separate persistent checkout, not this session's scratchpad clone).
    - **Unblocked (2026-09-29), by project-owner judgment, not by a new in-repo fixture.** The
      2026-08-24 decision above deferred consolidation until "a CAM-SIMA-backed fixture exists in
      this repo to test against locally" — that fixture still does not exist. Instead, the project
      owner judged this session's extensive external `/cam-sima-regression` testing (real CIME
      builds/runs against a separate `CAM-SIMA.xdsl-ccpp` checkout, spanning several weeks of work
      recorded elsewhere in this file) sufficient evidence to proceed with consolidation anyway.
      Recorded here explicitly so a future reader doesn't mistake "unblocked" for "a fixture was
      added" — the underlying test-coverage gap this repo has for the legacy `horizontal_loop_extent`
      chunking path (unit tests + 2 non-XFAIL FileCheck goldens only, no `examples/` build exercises
      `--legacy-mode` at all) is unchanged; the risk is simply judged acceptable to proceed against.
      Consolidation work itself tracked as `BACKLOG.md`'s `hle-chunk-consolidate` item.
    - **Stage 1 (2026-09-29): unified the `ncol` computation.** `suite_cap.py`'s
      `_build_ncol_compute_ops` and `run_dispatch.py`'s inline block in `_build_host_var_refs`
      built the identical 7-op alloc/load/load/sub/const/add/store sequence independently
      (`run_dispatch.py`'s own comment already said as much) -- extracted into
      `cap_shared.build_ncol_compute_ops`, taking plain SSA-value refs so each caller keeps its
      own `data_ops`/`block_arg_map` lookup. Pure refactor, zero behavior change by construction.
      Added a unit test (`test_run_dispatch_col_bounds_fallback.py::TestNcolComputeIsActuallyUnified`)
      that patches the shared function with a `wraps=`-mocked spy in both `suite_cap`'s and
      `run_dispatch`'s own module namespaces and asserts both call sites actually invoke it --
      proves genuine unification, not just coincidentally-identical output.
    - **Stage 3 (2026-09-29): unified the CapVar branch in `_build_array_section_ops`, with one
      real, deliberate behavior change.** Found a divergence the 2026-08-24 investigation didn't
      catch: the legacy `horizontal_loop_extent` CapVar branch called `_resolve_extra_dim_bounds`
      and discarded its return value, so it always built an `ArraySectionOp` from whatever partial
      `lowers`/`uppers` got appended -- even when an extra dimension's standard_name had no host
      var match, silently emitting a possibly rank-mismatched section. The `horizontal_dimension`
      sibling branch already checked the return value (`if not _cv_valid: continue`) and skipped
      the section entirely on the same failure. So "the general path is a strict superset of the
      narrow one" (the 2026-08-24 justification) held only on the success path. Collapsed both
      branches into one (keyed only by which standard name matched `_cv_dims[0]`, since
      `dims_compatible` already treats the two as equivalent) and adopted the stricter guard for
      both -- a deliberate fix, not a silent one. Also extracted the "look up
      `col_begin_key`/`col_end_key`, None-guard against `ctx.block_arg_map`, seed
      `lowers`/`uppers`" 6-line idiom (repeated 3x across the CapVar and Host/DdtMember branches)
      into one shared closure, `_seed_horiz_bounds`.
      - Added a behavior-pin test (`TestCapVarLegacyBranchUnresolvableExtraDim`) *before* making
        the change, confirmed it captured the old (buggy) behavior, then updated its assertion in
        the same commit as the merge -- the fix is a visible, deliberate diff in one test, not a
        silent regression. The new behavior turned out better than expected: the call falls
        through to the CapVar's own rank-aware whole-array reference (`lc_z_out(:, :)` for a
        rank-2 var, built earlier in `_build_host_var_refs`'s CapVar case) rather than a bare,
        unranked name.
      - **Deviation from the original plan, noted explicitly**: the plan called for a new
        FileCheck golden exercising this branch (e.g. via `array_layout_suite.py`). On inspection,
        that fixture is declared `array_layout="row_major"`, which makes every one of its array
        args take the separate `RowMajorConvertOp` path (`_build_array_section_ops` explicitly
        skips any arg in `local_to_array_layout`) -- it was never actually reachable from the
        CapVar branch being changed, and extending it would have added a fixture that still didn't
        cover this code. Substituted the unit test above instead, which runs the real
        `ArgOwnershipPass`/`SuiteCAP`/`CCPPCAP` passes (not mocks) and pins exact generated
        Fortran -- equivalent real-generator coverage without a fixture that wouldn't have worked.
      - **Verification**: full suite green after both stages -- `tests/unit` + `tests/filecheck`,
        711 passed, 1 xfailed (pre-existing, unrelated -- the rank-3 chost issue), 0 failed. All
        pre-existing legacy-mode tests/goldens listed in the plan (`test_deprecated_std_names.py`,
        `test_run_dispatch_col_bounds_fallback.py`'s other 3 classes, `test_suite_cap_resolved_vars.py`,
        `test_optional_args.py`, `array-layout-*`/`kw-override-py` goldens, `chost-r3-ftn.mlir`
        staying `XFAIL`) pass unmodified.
      - **RESOLVED (2026-09-29): `/cam-sima-regression` confirmed.** Ran the full `aux_sima`
        suite against `CAM-SIMA.xdsl-ccpp` (test ID `xdsl43g`, `gnu` compiler only -- a single
        compiler is sufficient here since this change is pure code-generation logic with no
        compiler-specific or GPU/OpenACC paths touched). Result: 28/31 cases pass, 2 timed out in
        the PBS queue behind the rest (never reached a FAIL), 1 known pre-existing, unrelated
        failure -- `F2000_C7`/cam7's `MODEL_BUILD` (missing physics host-var matches, already
        confirmed elsewhere in this file to fail identically under real capgen-v1, not something
        this change touches). Zero unexpected failures, including both MPAS-dycore cases
        (`kessler_mpas`, `kessler_mpas_derecho_history`) and both real SE-dycore/`--legacy-mode`-
        adjacent cases this backlog item's own code paths are most directly exercised by. This
        satisfies the plan's verification bar -- `hle-chunk-consolidate` is now fully resolved.
    - **`hle-vocab-retire` re-scoped (2026-09-29): deferred indefinitely, not a schedulable
      near-term task.** This backlog item ("actual code-path deletion" of the legacy
      `horizontal_loop_extent` machinery, the one piece of the 2026-07-27 migration left open)
      rested on that migration's own premise that the legacy code path was "now-provably-dead-for-
      every-example." The 2026-08-24 investigation above already corrected that premise once (real
      CAM-SIMA still declares `horizontal_loop_extent` directly), and this session's own
      `/cam-sima-regression` run (`xdsl43g`, done for `hle-chunk-consolidate`'s own verification,
      immediately above) reconfirmed it against real CAM-SIMA test cases. Net effect: the legacy
      code path (`ccpp_conventions.py`'s `is_legacy_mode()` gate, `cpp_interop.py`'s C++-side
      fallback naming, `run_dispatch.py`, `ccpp_cap.py`, `suite_cap.py`'s `_classify_args`/
      `_build_ncol_compute_ops` synthesis) must be retained for as long as `--legacy-mode` itself
      is supported -- deletion is only safe once CAM-SIMA migrates off `horizontal_loop_extent`
      upstream, an external dependency this repo has no control over and no visibility into a
      timeline for. Not scheduled; re-check only if/when CAM-SIMA's own upstream state changes.

---

## Backlog — other flagged issues

- **`generateSchemeSubroutineCallOps`'s errflg-guard ops are inserted out of
  SSA def-use order — S, cosmetic only, but repo-wide blast radius if fixed
  (flagged 2026-07-23, via a Copilot review comment on PR #40).** `suite_cap.py`
  (~line 606) returns `[err_const_comp, cmp, load_op, conditional_op]` for the
  `scf.if errflg == 0` guard wrapping every scheme call in a suite's lifecycle
  functions — `cmp` (the `arith.cmpi`) is listed, and therefore inserted into
  the block, *before* `load_op`, even though `cmp` consumes `load_op`'s result.
  Should be `[err_const_comp, load_op, cmp, conditional_op]`.
  - **Not introduced by PR #40** (the `cld_ice_final` alias fix) — confirmed via
    repo-wide grep that the identical pattern already exists in 56 other places
    across 7 `tests/filecheck/examples/completed_ir/*.mlir` golden files
    (advection, ddthost ×2, capgen, helloworld ×2, kw-override). PR #40 only
    added one more instance of an already long-standing, systemic quirk by
    faithfully matching real generator output in its two updated goldens.
  - **Confirmed cosmetic, not a real correctness bug:** the ordering artifact
    only ever surfaces in the raw MLIR text dump (`completed_ir` goldens) — the
    Fortran printer collapses this same comparison+load into a clean
    `if (errflg .eq. 0) then` regardless of block insertion order, and the
    pattern never appears in any `end_to_end` (Fortran) golden file. Zero
    effect on any actually-compiled output.
  - **Why not fixed inline with PR #40:** fixing the root cause means
    regenerating and re-diffing all 7 affected `completed_ir` golden files
    repo-wide, not just the two this PR touched — a separate, independently
    verifiable change, per this project's established practice of not
    bundling unrelated fixes into one PR.
  - Project owner is replying to the Copilot comment on PR #40 directly
    (its suggested fix — swapping the two `CHECK` lines — is wrong on its own:
    the golden file must match real generator output, so swapping only the
    `CHECK` lines without also fixing `generateSchemeSubroutineCallOps` would
    make the test fail instead of passing).
  - **RESOLVED (2026-09-29), `errflg-guard-order`.** Fixed at the root cause:
    `generateSchemeSubroutineCallOps` (`suite_cap.py`) now returns
    `[err_const_comp, load_op, cmp, conditional_op]`, matching true SSA
    def-use order (`load_op` before the `cmp` that consumes it). Blast
    radius was one file larger than originally flagged — `var_compat-xml.mlir`
    joined the affected set since being added after this was first logged, for
    8 affected `completed_ir` goldens total (`advection-xml`, `capgen-xml`,
    `ddthost-py`/`-xml`, `helloworld-py`/`-xml`, `kw-override-py`,
    `var_compat-xml`), all regenerated via `update-filecheck-test.py` and
    diff-reviewed before accepting. **Bonus finding while reviewing the
    diff**: `git diff -w` (ignore-whitespace) showed the real content diff was
    far smaller than the raw diff suggested (114 vs. 2244 lines for
    `capgen-xml` alone) — the out-of-order emission had also been confusing
    the pretty-printer's indentation tracking for these exact lines
    (2-space instead of the surrounding 8-space indent), a second, related
    cosmetic artifact fixed as a side effect of the same one-line change.
    Full suite green: 711 passed, 1 xfailed (unchanged, pre-existing,
    unrelated), 0 failed.

- **Move examples' build system from hand-written per-example Makefiles to
  CMake — size TBD, project owner preference (flagged 2026-07-23).** Every
  example under `examples/` (11 today, 12 once the var_compat port lands) has
  its own hand-maintained `Makefile`, none using CMake — confirmed via a
  repo-wide search: zero `CMakeLists.txt` files exist anywhere in this repo.
  Project owner prefers CMake over raw Makefiles. Worth noting: capgen-v1's
  own upstream `end-to-end-tests/*` examples (the source every one of this
  project's examples gets ported from) already ship a `CMakeLists.txt` +
  `ctest` setup — today's port process explicitly *drops* that file in favor
  of a hand-written Makefile (see e.g. `examples/advection`'s own port), so a
  move to CMake could mean future ports carry the upstream `CMakeLists.txt`
  over with much lighter adaptation instead of hand-authoring an equivalent
  Makefile from scratch each time.
  - **Not scoped or investigated yet** — no design decided on scope (all
    examples at once vs. incremental/one-at-a-time, matching this project's
    usual staged-migration discipline) or on preserving today's per-example
    `make [all|run|check|clean|caps]` target vocabulary that
    `.github/workflows/compile-tests.yml` already depends on directly (its
    `run: make -f examples/${{ matrix.example }}/Makefile check` step would
    need an equivalent `ctest`-based invocation, or a compatibility shim, for
    every example in that workflow's matrix).
  - **Sequencing note:** the var_compat port (in progress) still uses the
    existing Makefile convention, per the approved plan for that work —
    revisit this item once that lands, so a build-system migration doesn't
    get tangled up with an in-flight example port.

- **Fixed — `.meta` argument-bracket parser required exact spacing
  (`[ name ]`, not `[name]`) to tell an argument name apart from an
  unrecognized token — found while porting var_compat (2026-07-23), fixed
  2026-07-27.** `ccpp_xml.py`'s
  `parse_meta_file` (~line 313 onward) strips only the `[`/`]` characters
  from a bracketed line, then disambiguates purely on whether the
  *remaining* string has a leading or trailing space:
  `elif token[0] == " " or token[-1] == " ": ... current_arg = CCPPArgument(token.strip())`,
  `else: raise AssertionError(...)`. capgen-v1's own `.meta` files
  (`var_compat`'s `effr_pre.meta`/`effr_calc.meta`/etc., 14+ occurrences
  across the ported files) use the tight `[effrr_in]` form with no reader
  that requires spacing either way — this project's own convention is simply
  a stricter subset of what's actually valid CCPP metadata.
  **Fixed** exactly as scoped above: dropped the `token[0] == " " or
  token[-1] == " "` condition entirely, replacing the `elif`/`else`
  (space-heuristic / `AssertionError`) pair with a single unconditional
  `else` branch that treats any non-header bracketed token as an argument
  name — the header check above it already does an exact literal match
  against the two known keywords regardless of spacing, so nothing else
  relied on the space heuristic, and a `.meta` file's grammar has no other
  bracketed construct left to disambiguate. `.strip()` still normalizes both
  spaced and tight forms to the identical bare name. No change needed on the
  writer side (`meta_from_module` et al. already only ever emit the spaced
  form). Direct regression coverage (sabotage-verified, confirming both
  forms parse identically and that the tight form no longer raises) in
  `tests/unit/test_meta_parser_bracket_spacing.py`. Full unit + FileCheck
  suites re-run clean (506 passed, same 1 pre-existing xfail and 1
  pre-existing unrelated failure as before). This does *not* retroactively
  un-normalize var_compat's own already-ported `.meta` files (see
  `examples/var_compat/README.md`'s "Adaptations made during porting"
  section) — it only means a *future* port can skip that normalization step.

  **Follow-up (found by Copilot's review of that fix, PR #46):** turning the old space-heuristic
  `elif`/`else` pair into a single unconditional `else` also removed the only remaining
  validation in that branch, exposing two malformed-input cases to a confusing crash instead of a
  clear error. An argument-shaped bracket appearing before any `[ccpp-arg-table]` header
  (`current_arg_table` still `None`) didn't fail immediately — the crash only surfaced the *next*
  time a bracket was seen, when the pending argument was attached to a still-nonexistent table
  (`AttributeError: 'NoneType' object has no attribute 'setFunctionArgument'`), far from the line
  with the actual mistake. And an empty or whitespace-only bracket (`[]`) silently became an
  argument with an empty name instead of being rejected. **Fixed** by validating both explicitly
  (with `ValueError`s naming the file and line number, right at the point the raw `.meta` text is
  parsed — a system boundary), plus tracking line numbers via `enumerate` for the error messages.
  Direct regression coverage (sabotage-verified, both cases) added to the same
  `tests/unit/test_meta_parser_bracket_spacing.py`. Full unit + FileCheck suites re-run clean (514
  passed, same 1 pre-existing xfail and 1 pre-existing unrelated failure as before).

- **Fixed — three more of the same class of bug, found by auditing the frontend parser for
  other whitespace-has-a-particular-meaning spots after the bracket-spacing fix above
  (2026-07-27).** Same shape each time: user-authored text taken at face value without
  stripping, relying entirely on everyone happening to format things the same tight way. None
  were live failures — every suite XML/CLI invocation in this repo already avoids the incidental
  whitespace — but all three would previously have failed silently or confusingly:
  1. `XMLScheme.scheme_name` (a `<scheme>` element's text content) was used unstripped. Every
     suite XML in this repo writes the name tight against the tags on one line, but XML preserves
     indentation whitespace verbatim in element text — an indented `<scheme>\n  x\n</scheme>`
     would have produced a `scheme_name` that never matches anything in scheme metadata, with no
     clear error pointing at whitespace as the cause.
  2. `XMLSubcycle`'s own `loop` attribute was read unstripped — same bug, lower likelihood
     (attribute values rarely pick up incidental whitespace, since nobody indents inside a quoted
     attribute).
  3. Both `ccpp_xml.py`'s `ccppXML.build_options_db_from_args` and `ccpp_dsl.py`'s
     `ccppMain.build_options_db_from_args` split `--scheme-files`/`--host-files`/`--suites` on
     comma with no per-entry stripping — `"a.meta, b.meta"` would silently produce a path with a
     leading space, failing to open with a confusing error (confirmed directly via sabotage
     testing: `FileNotFoundError: Input file not found: ' examples/helloworld/temp_adjust.meta'`)
     instead of being tolerated the way most CLI tools handle incidental whitespace.

  **Fixed** by adding a `.strip()` at the point each raw value is taken, in all four spots (two
  files for the CLI comma-split). Direct regression coverage (sabotage-verified, all three) in
  `tests/unit/test_frontend_whitespace_tolerance.py`. Full unit + FileCheck suites re-run clean
  (512 passed, same 1 pre-existing xfail and 1 pre-existing unrelated failure as before).

- **`[ccpp-table-properties]`'s `module_name` override isn't supported — S,
  found while porting var_compat (2026-07-23).** capgen-v1 lets a table's
  logical/suite-visible name (e.g. `effr_pre`, the name used in
  `<scheme>effr_pre</scheme>`) differ from the Fortran module that actually
  implements it (e.g. `mod_effr_pre`), via a `module_name` key on
  `[ccpp-table-properties]`. `xdsl_ccpp/transforms/util/ccpp_descriptors.py`'s
  `CCPPTableProperties.setAttr` only allows `name`/`type`/`dependencies`/
  `relative_path`/`array_layout`/`language` — `module_name` raises
  (`CCPPItem.setAttr`'s allow-list check). xdsl-ccpp assumes the Fortran
  module name always equals the table name; every existing example already
  follows that convention, so this has never surfaced before. Ported
  `var_compat`'s `effr_pre.F90`/`module_rad_ddt.F90` had their real
  capgen-v1 module names (`mod_effr_pre`/`mod_rad_ddt`) renamed to match the
  table/file name instead of teaching the parser the real attribute — see
  the same README section. Not scoped further; would need a plan for how
  the renamed-module name flows through to `print_ftn.py`'s `use` statement
  generation and any other place that currently assumes table name == module
  name.

- **`type = control` (capgen-v1) has no xdsl-ccpp equivalent — a real,
  currently-inconsequential modeling gap, found while porting var_compat
  (2026-07-23).** Checked capgen-v1's own validator source directly
  (`ccpp_validator.py`, `VALID_TABLE_TYPES` in `metadata_table.py`):
  `control` is a distinct table type from `host`, not just a naming
  variant. `host` tables describe variables with a real backing Fortran
  declaration, cross-validated against actual source; `control` tables
  (`suite_name`/`group_name`/`thread_num`/`col_start`/`col_end`/`errmsg`/
  `errflg` in `var_compat`'s real `test_host.meta`) have **no** backing
  Fortran declaration at all — the validator's own docstring says they are
  "framework-injected at the cap call sites" and are explicitly
  silent-skipped by source-cross-validation for that reason.
  `xdsl_ccpp/transforms/util/ccpp_descriptors.py`'s `CCPPType` enum has only
  `SCHEME`/`MODULE`/`DDT`/`HOST` — no `CONTROL` — so this project's own
  `examples/advection`/ported-`var_compat` `test_host.meta` already declares
  exactly this same category of variable (`col_start`/`col_end`/`errmsg`/
  `errflg`) under `type = host`, collapsing capgen-v1's two concepts into
  one.
  - **Why this doesn't bite today:** xdsl-ccpp has no equivalent of
    capgen-v1's meta-vs-Fortran-source cross-validation step for host
    tables in the first place, so there's currently nothing for the missing
    `real declaration` vs. `framework-injected, no declaration` distinction
    to break.
  - **Worth tracking anyway** in case a future feature needs to tell the two
    apart (e.g. if xdsl-ccpp ever adds its own host-side meta-vs-source
    validation, or needs to know which host vars are safe to assume have a
    real Fortran symbol behind them vs. which are purely call-site
    conventions). Not scoped further.
  - Distinct from (but related in spirit to) the already-tracked
    `chunked_data`/`instances` backlog items above, which cover
    `thread_num`/`nthreads`/`nphys_threads` specifically (real,
    thread-parallel-dispatch capability gaps) — this item is about the
    *table-type modeling* gap (`control` vs `host`), not about any one
    variable's semantics.

- **Suite signature generation ignored the host's own already-unique local
  name and used each scheme's own (colliding) local name instead — found by
  actually running the real driver end-to-end against the ported var_compat
  example, fixed in `suite_cap.py` (2026-07-23).** `effr_pre`/`effr_post`/
  `effr_calc`/`effr_diag` each independently declare an unrelated scalar
  argument (`scalar_variable_for_testing_a`/`_b`/plain/`_c` respectively —
  capgen-v1's own README calls these out by name as a deliberate test of this
  exact scenario) using the identical bare Fortran name `scalar_var` in their
  own scheme source. This is correct, idiomatic CCPP metadata, not a
  `.meta`-authoring mistake — a scheme's local dummy-argument name is private
  and arbitrary; only `standard_name` needs to be consistent across schemes.
  **Proof this was meant to be supported, not just tolerated:** var_compat's
  own real host metadata (`test_host_data.meta`, the `physics_state` DDT)
  already declares all four standard_names with distinct, collision-free
  local names of its own — `scalar_var`/`scalar_varA`/`scalar_varB`/
  `scalar_varC` — precisely so a generated cap can reference each via the
  host's own unique name instead of the scheme's, but `suite_cap.py`'s
  `_build_block_signature` never consulted `model_var_name` (the
  host-matched canonical name `host_var_match_pass.py` already annotates
  onto each `ArgumentOp` when a match is found) at all, always using each
  arg's own bare `.name` unconditionally. This is the same *class* of bug as
  the `ccpp_loop_cnt` duplicate-declaration bug fixed during the
  nested-subcycle work's Stage 4 (two unrelated things independently
  choosing the same bare name, nothing de-duplicates) — a different,
  unrelated site with nothing to do with subcycling.
  - **Fixed** in `_build_block_signature`: computes each arg's default hint
    (its own scheme's local name, unchanged for the common case) first, and
    only when two different standard_names' schemes genuinely collide on
    the same default hint does it fall back to `model_var_name` for just
    those entries (raising a clear `ValueError` if no host match is
    available to disambiguate with) — every non-colliding arg keeps its
    exact original name. The data wiring needed the same treatment: `data_ops`
    (keyed by the scheme's own bare arg name) can't distinguish colliding
    entries either, so each entry is also registered under a
    `("std_name", ...)`-tagged key, populated from an index-keyed
    `final_values` list (not from the name-keyed dict, which is itself
    collision-prone) so every scheme call still receives its own correct
    value regardless of which one is processed last.
  - This fix requires the `generate-host-match` pass to have already run so
    `model_var_name` is set — which the production `ccpp_xdsl` tool always
    does whenever host files are supplied (`ccpp_dsl.py`'s `_build_pipeline`),
    so no user-facing invocation changes. The two var_compat FileCheck
    goldens' hand-written `-p` pass lists (copied from examples/advection's
    pattern, which never needed host-matching) were missing this pass and
    have been corrected to match.
  - Regression coverage: `tests/unit/test_suite_arg_name_collision.py`
    (collision resolved via host name, both the printed signature and each
    scheme's actual call-site value; and a negative test confirming a clear
    `ValueError` when no host match exists to disambiguate with).

- **CMake cap generation runs at configure time, not build time, so every
  wired-in example's caps regenerate on every CI job regardless of which
  target that job actually builds — flagged 2026-08-13, size TBD.**
  `cmake/xdsl_ccpp_capgen.cmake` calls `ccpp_xdsl` via `execute_process()`,
  which runs synchronously while CMake is still processing
  `CMakeLists.txt` files (configure time), not later when `cmake --build`
  actually compiles targets. Since the root `CMakeLists.txt` does
  `add_subdirectory(examples/X)` for every wired-in example, and each of
  those directories' own `CMakeLists.txt` calls `xdsl_ccpp_capgen()`
  unconditionally as soon as CMake reaches it, a single `cmake -S . -B
  build` regenerates every wired-in example's caps up front — before the
  separate, later `--target <one-example>` build step even runs. Each of
  `.github/workflows/compile-tests-cmake.yml`'s ~16 matrix jobs runs its
  own fresh configure, so this means all ~16 examples' caps get generated
  in every one of the 16 jobs, not just the one each job actually tests.
  - **Why it's built this way:** modeled directly on capgen-v1's own
    `cmake/ccpp_capgen.cmake` precedent (see this file's own header
    comment) — running synchronously at configure time lets the
    `CMakeLists.txt` immediately parse the generated file list
    (`CCPP_CAPS_LIST`, read back from `--emit-datatable`'s output) and feed
    it straight into `add_library(...)` in the same pass, rather than
    needing `add_custom_command(OUTPUT ...)`'s more awkward
    statically-declared-output-filenames machinery.
  - **The real cost isn't just wasted CI time:** `xdsl_ccpp_capgen()` calls
    `message(FATAL_ERROR)` on a cap-generation failure, which aborts
    configure *entirely* — for every job, not just whichever example
    failed. This is exactly why `instances_advection` (a confirmed
    cap-generation hard-failure) is deliberately kept out of
    `add_subdirectory` rather than fixed later — see this repo's root
    `CMakeLists.txt`'s own header comment.
  - **Not attempted:** deferring cap generation to build time (e.g. via
    `add_custom_command(OUTPUT ...)`, gated per-target so each CI job only
    generates the one example it's actually building) would be a real CMake
    restructuring, not a small patch — every example's `CMakeLists.txt`
    would need its own output-file list known statically at configure time
    (today it's discovered dynamically, after the tool already ran and
    wrote `datatable.xml`), which likely means `xdsl_ccpp_capgen()`'s own
    interface changes too. Sizing this needs a closer look before deciding
    whether it's worth doing.

- **~~Scheme-level dynamic constituent registration output discarded by
  `ccpp_register`'s own wrapper~~ — CORRECTED, not a bug (found 2026-08-18,
  corrected same day).** Originally logged as a suspected discard bug:
  `cld_liq_register`'s own `dyn_const` output is referenced as a bare
  `lc_dyn_const` inside `ccpp_register`'s generated body, with no local
  declaration anywhere in sight, which looked exactly like a function-scoped
  local silently discarded on return.
  - **Traced fully while fixing a real, related regression in the same code
    path (below) and found it's by design, not a bug.**
    `lifecycle_cap.py`'s own dedicated `CapVarRefOp` branch for this exact
    arg shape (allocatable `ccpp_constituent_properties_t`) emits that bare
    text *deliberately*, matching `constituent_cap.py`'s own module-var
    naming convention (`lc_<bare>`) exactly on purpose -- Fortran resolves
    an otherwise-undeclared identifier inside a subroutine via ordinary
    module scoping to the module-level variable of the same name in the
    *same* module (no `use` needed, since `ccpp_register` and
    `constituent_cap.py`'s own declarations live in the one combined cap
    module). Nothing is discarded: that bare name IS the persistent module
    variable `test_host_ccpp_register_constituents` later reads from.
  - **The real, adjacent bug this same investigation found**: this
    mechanism is a genuine coupling between two independently-generated
    parts of the file (`lifecycle_cap.py`'s reference text and
    `constituent_cap.py`'s declaration), held together only by matching
    naming convention -- and multi-instance broke exactly that coupling.
    Once `constituent_cap.py` moved `lc_dyn_const` into the new per-instance
    bundle (`lc_instances(instance)%lc_dyn_const`, task #35's own fix),
    `lifecycle_cap.py`'s branch kept emitting the bare, now-nonexistent
    name -- a real gfortran CI failure (`"Symbol 'lc_dyn_const' ... has no
    IMPLICIT type"`), not a hypothetical one. **Fixed**: that branch now
    accepts `instance_local_name` and builds
    `lc_instances(<instance>)%lc_<bare>` when set, `lc_<bare>` unchanged
    otherwise -- confirmed `examples/advection`'s own (non-multi-instance)
    output is byte-identical before/after. New regression test
    (`tests/unit/test_multi_instance_constituent_api.py`'s
    `TestSchemeLevelDynamicRegistrationOutputIsInstanceAware`, confirmed via
    git-stash to catch the regression).
  - **A second, independent real bug caught by the same CI run**: Fortran
    forbids the `TARGET` attribute on a derived-type *component*
    (`constituent_cap.py`'s first cut put it there directly, copying the
    plain-module-var version's own attribute list without checking it
    transfers) -- `gfortran`: `"Attribute at (1) is not allowed in a TYPE
    definition"`, cascading into dozens of unrelated `"not a member of the
    structure"` errors for every OTHER component once the type block's own
    parse got corrupted. Fixed: `target` moved to the containing
    `lc_instances(:)` variable itself, where Fortran's own attribute-
    propagation rule (`TARGET` on a variable propagates to all its
    subobjects, including allocatable components) makes every pointer
    association into it exactly as valid as before.

- **Full capgen-v1 `ccpp_suite_state` match — integer-enum allocatable array
  + dedicated alloc/dealloc subroutines — L, deliberately deferred
  (2026-08-18).** The `instances`/`instances_advection` multi-instance fix
  (see above) gave `ccpp_suite_state` a per-instance allocatable array, but
  kept this codebase's own pre-existing state *representation* — 3
  string-literal states (`'uninitialized'`/`'initialized'`/`'in_time_step'`)
  — rather than switching to real capgen-v1's own model, confirmed against
  `ccpp-framework-fresh/capgen/generator/suite_cap.py`:
  - An integer enum (`CCPP_SUITE_UNREGISTERED=0`/`CCPP_SUITE_REGISTERED=1`/
    `CCPP_SUITE_FRAMEWORK_INITIALIZED=2`), not string comparison — a real
    **4th state** this codebase's model has no equivalent of at all (this
    codebase conflates "registered" and "framework-initialized" into one
    `'initialized'` state; capgen-v1 keeps them distinct).
  - Dedicated, publicly-exposed `<suite>_suite_state_alloc`/`_dealloc`
    subroutines, not an internal lazy-allocate-on-first-use (this codebase's
    narrow fix's own choice, reusing the existing `LazyAllocOp` idiom —
    functionally equivalent for the one example that exercises it today, but
    not a byte-for-byte API match).
  - Why deferred rather than done now: the user explicitly asked how big the
    full match would be before choosing the narrow fix; the answer was that
    the state *representation* is cross-cutting — every suite's generated
    cap (not just multi-instance ones) constructs/compares these string
    literals via `generateStateCheckOps`/`generateStateAssignment`/
    `_build_state_globals`, so swapping to integer enums touches all of
    them, not just `examples/instances`. Also gains a genuine 4th state with
    no current equivalent, which interacts with task #28 (the pending full
    6-phase to 8-phase lifecycle match with capgen-v1 above) — sequencing
    this *after* #28 avoids redoing the state-check/assignment call sites a
    second time once the phase split changes what needs checking/setting.
  - **Not scoped in detail yet** — the above is a sizing sketch from reading
    real capgen-v1's own `suite_cap.py`, not a staged plan. Revisit once #28
    lands.

---

## Codebase complexity/duplication audit (2026-08-18)

User-requested full-codebase health check, prompted by "it's been a while since we looked at overall code complexity." Six parallel research passes (forked, read-only) covered every production file under `xdsl_ccpp/` (~24,500 lines): `suite_cap.py` alone; the `lifecycle_cap.py`/`constituent_cap.py`/`ccpp_cap.py`/`cap_shared.py` cluster; `run_dispatch.py` plus the GPU passes (`gpu_ccpp_cap_pass.py`/`gpu_data_pass.py`/`host_var_match_pass.py`/`arg_ownership_pass.py`); the dialects (`ccpp.py`/`ccpp_utils.py`) plus the Fortran/C++ printers (`print_ftn.py`/`print_cpp_header.py`/`lower_ccpp_utils.py`); the frontend/interop/util layer (`ccpp_xml.py`/`py_api.py`/`cpp_interop.py`/`ccpp_descriptors.py`/`suite_variable_model.py`/`typing.py`/`ir_utils.py`/`ccpp_conventions.py`); and the meta/FIR tooling + CLI layer (`fir_to_meta.py`/`fparser2_to_meta.py`/`validate_fir.py`/`suite_meta.py`/`suite_kinds.py`/`generate_kinds.py`/`strip_ccpp.py`/`visitor.py`/all of `xdsl_ccpp/tools/`).

**Cross-cutting observation from every fork independently**: this codebase is unusually well-commented for its size and intricacy — most apparent duplication turned out to be deliberate and explained (a documented reason two similar blocks are genuinely different), not sloppy copy-paste. The findings below are the ones that survived that filter.

Findings triaged into four tiers, each now a tracked task:

- **Tier 1 — real drift risks, not just style** (tasks #37-#41): two independent flang-invocation implementations have already diverged (one is missing a compiler-search fallback the others have) — **RESOLVED (2026-08-18, task #37):** turned out to be three independent copies (`ccpp_validate_fir.py`, `ccpp_validate_source.py`, `fir2meta.py`), not two — `fir2meta.py`'s own `_run_flang` hardcoded the literal string `"flang"` with no fallback to `flang-new`/`flang-18`/etc. and no `FileNotFoundError` handling, so on any system with only a versioned Flang binary on PATH it crashed with an uncaught Python traceback instead of the other two tools' clean, documented error message (confirmed live on this dev machine, which has no Flang at all: `fir2meta.py` now prints the same clean error and exits 1, matching `ccpp_validate_fir.py`/`ccpp_validate_source.py`'s existing behavior instead of crashing). Fixed by extracting `find_flang()`/`run_flang()` into a new shared `xdsl_ccpp/tools/flang_utils.py`, used by all three tools; each tool keeps its own "no Flang found" message wording (genuinely call-site-specific: generic vs. `--backend flang`-requested vs. fparser2-fallback-available). Full suite still 606 passed/1 xfailed, `ruff check` clean; `ccpp_prebuild.py`'s hand-copied CLI options dict is already missing flags `ccpp_dsl.py` supports — **RESOLVED (2026-08-18, task #38):** confirmed 9 keys missing (`py`, `directive`, `kind_map`, `emit_datatable`, `no_memory_space_warning`, `emit_html`, `emit_resolved_vars`, `bind_c`, `legacy_mode`); one of them (`self.options_db["py"]`, a direct-index read in `run_py_frontend`) was a live `KeyError` landmine, not yet triggered only because `ccpp_prebuild.py` happens to call `run_frontend` rather than `run_py_frontend`. Fixed by adding `ccppMain.default_options_db()` (`vars(self.initialise_argument_parser().parse_args([]))` — the parser's own defaults, no required-arg validation) as the single source of truth; `ccpp_prebuild.py` now builds `tool.options_db` by calling that and overlaying only the keys it actually resolves from config (`suites`/`scheme_files`/`host_files`/`out`/`tempdir`/`verbose`), so any option added to `ccpp_dsl.py`'s parser in the future carries its real default into `ccpp_prebuild.py` automatically instead of silently vanishing. Verified with a smoke-tested `ccpp_prebuild_config.py` against `examples/advection`: output is byte-identical both to direct `ccpp_dsl.py` invocation on the same inputs and to the pre-fix `ccpp_prebuild.py`'s own output (three-way `diff -rq`, no differences). Full suite still 606 passed/1 xfailed; `print_ftn.py`/`print_cpp_header.py` independently reimplement the same Fortran-intent rule with no shared code (the latter's own docstring admits it's a manual replica) — **RESOLVED (2026-08-18, task #39):** confirmed a real divergence, not just parallel style: `print_cpp_header.py`'s `_intent_from_arg` was missing the `__alloc`-suffix branch entirely (print_ftn.py's `_print_fn` treats a name-hinted allocatable, non-character arg as `intent(inout)` explicitly; the C++ header replica fell through to its array-dims check instead). Harmless today only because every current allocatable (non-character) argument also has array dims, so both land on "inout" anyway by different paths — but a future scalar allocatable argument (e.g. a scalar workspace scratch var) would get the wrong intent in the generated C++ header while the Fortran side stayed correct, with nothing to catch it. Fixed by extracting the exact decision tree into a new pure function, `classify_arg_intent()` (`print_ftn.py`, five boolean inputs, no xDSL type dependency), and routing both `_print_fn` and `_intent_from_arg` through it — the two printers can no longer independently drift on branch order. Verified via git-stash regeneration across 11 examples (including `kessler`/`tinyddt`, the only two `--bind-c` C++-header examples in the repo): byte-identical output before/after. Full suite still 606 passed/1 xfailed; `run_dispatch.py` has the same "two independent copies of one invariant" shape that caused this session's own real `ccpp_suite_state`/`dyn_const` regressions — **RESOLVED (2026-08-18, task #40):** the two copies were the CapVar-source and Host/DdtMember-source branches of `_build_run_dispatch_chain`'s ArraySectionOp construction, each independently resolving "every array dimension beyond the leading horizontal_dimension" to a host var ref (with its own external-global dedup and lazily-created shared `1` constant) -- structurally identical, both correct today, but with no shared code forcing them to stay that way. Extracted into one nested closure, `_resolve_extra_dim_bounds(dim_std_names, lowers, uppers)`, capturing the same enclosing-scope mutable state (`one_const_for_sections` via `nonlocal`, `host_name_to_ref_result`, `seen_host_globals`, `chain_global_ops`) both call sites already shared; preserves the original fail-fast semantics (stops and returns `False` at the first dim with no `host_var_map` entry, same as both call sites' original `break`). Verified via git-stash regeneration across the same 9 examples as task #39 (including `constituents_dim`/`var_compat`, the two exercising multi-dimension CapVar/host array sections): byte-identical output before/after. Full suite still 606 passed/1 xfailed; a "primitive CCPP type" set is redefined 3 times with different membership across two files.
- **Tier 2 — clean, low-risk mechanical extractions** (tasks #42-#55): one genuine byte-for-byte duplicate block in `suite_cap.py` (✅ task #42); the single most-repeated pattern in the whole codebase (a "walk table→arg_table→arg" triple-nested loop reimplemented 15+ times) with no shared helper (task #43 -- **RESOLVED (2026-08-18):** confirmed two distinct patterns, not one -- a raw-IR walk (~10 sites: 1 in `arg_ownership_pass.py`, 5 in `ccpp_cap.py`, 1 in `suite_kinds.py`, 3 in `host_var_match_pass.py`) each differing only in *which* `table_type`/`table_name` it filters for, and a much larger pre-built-`meta_data`-dict walk (~25+ sites across `cpp_interop.py`/`suite_cap.py`/`run_dispatch.py`/`lifecycle_cap.py`/`constituent_cap.py`/`gpu_ccpp_cap_pass.py`/`gpu_data_pass.py`/`suite_meta.py`) that's short enough per-site (2 lines) that a wrapper would mostly just rename it -- deliberately left alone (lower value than the raw-IR walk, and task #55's own dict consolidation already touched the one site, `ccpp_cap.py`'s `_build_cap_var_map`, where it would have mattered most). Implemented `iter_arg_tables(ccpp_mod, table_type=None, table_name_in=None)` in `cap_shared.py` -- yields `(table_prop_op, arg_table_op)` pairs, stopping one level short of `ArgumentOp` since every site's own per-arg filtering (entry-point suffix, standard_name presence, etc.) varies too much to fold in safely; `table_type` accepts a single value or a collection, so both "table_type == X" and "table_type in {a, b, c}" filters (both shapes were present across the real sites) are expressible without hiding either. Migrated all ~10 confirmed sites; `ccpp_descriptors.py`'s own canonical descriptor-builder traversal and `util/ir_utils.py`'s `build_host_var_index` deliberately left untouched (the former is what `meta_data` itself is built from; the latter is already its own established helper). Verified byte-identical across 11 examples (9 plus `kessler`/`tinyddt` bind_c) including `--emit-resolved-vars` JSON output, which directly exercises `host_var_match_pass.py`'s migrated `model_var_index` build. Full suite 607 passed/1 xfailed, `ruff check` clean. This also resolves task #52 Item B's deferred "`gpu_ccpp_cap_pass.py` suite-arg iterator" finding by explicit decision: it's an instance of the Shape B pattern, deliberately left un-extracted for the same reason); `_make_ctx()` duplicated verbatim across 5 CLI tools -- **RESOLVED (2026-08-18, task #44):** confirmed byte-identical (only doc-string differed) at exactly the 5 sites (`ccpp_dsl.py`, `ccpp_validate_fir.py`, `ccpp_validate_source.py`, `fir2meta.py`, `ccpp_datatable.py`), no divergence, no import-cycle risk. Extracted into new `xdsl_ccpp/tools/ctx_utils.py::make_ccpp_context()`, sibling to `flang_utils.py` (task #37's precedent); ~11 near-identical GPU omp/acc dispatch blocks -- **RESOLVED (2026-08-18, task #45):** actually 13 sites across `gpu_ccpp_cap_pass.py`/`gpu_data_pass.py`, of which 10 are genuine 1:1 op-class/kwarg substitutions and 3 have real ACC-clause-merging logic (`copy`/`copyin`/`copyout` collapsing into OMP's single, coarser `tofrom`, differently per call site) that would lose information if forced into a table. Extracted a shared `directive_op(directive, acc_cls, acc_kwargs, omp_cls, omp_kwargs)` into `cap_shared.py` (the module both files already import from) and routed the 10 safe sites through it; the 3 merge-case sites deliberately left hand-written. Verified via git-stash regeneration of `examples/advection` (the repo's only `memory_space`-bearing example) under both `--directive acc` and `--directive omp`: byte-identical; `print_ftn.py`'s 8 convert/write-back printer cases sharing one skeleton (task #46 -- **RESOLVED (2026-08-18):** verified the open question from scoping -- RowMajorConvertOp/WriteBackOp's missing `__opt` present-gate is architecturally safe to leave as-is: its source is always a `HostVarRefOp` (a host module-var reference), and `"__opt"` name-hints are only ever assigned by `suite_cap.py`'s `_hint_for` to *block args* (dummy arguments of the wrapper subroutine), so a host module var can never carry one -- confirmed via grep, the only site in the whole codebase that ever appends `"__opt"`. VerticalFlipOp/WriteBackOp's missing gate, however, turned out to be a **real latent bug**, just not yet exercised by any current example: it's only ever constructed via `suite_cap.py`'s `_apply_divergent_marshaling` (the cross-scheme kind/unit/top_at_one marshaling path), which does NOT exclude optional args from the top_at_one branch -- so an arg that is both `optional` and has a divergent `top_at_one` (no existing example combines the two, confirmed by grep across `examples/*/*.meta`) would crash calling `size()` on an absent optional array with no present() guard. Fixed by adding the same `__opt` gate Kind/Unit already have. Extracted two shared helpers, `_print_guarded_alloc_and_assign()`/`_print_guarded_writeback_and_dealloc()`, covering Kind+Unit+VerticalFlip (6 of 8 cases, all identical after the fix); RowMajorConvertOp/WriteBackOp correctly left as their own, structurally different implementation (rank/sizes come from an explicit `dim_exprs` attribute, not `_ftn_dim_suffix`). Added a new regression test (`test_suite_vertical_flip_marshaling.py::TestOptionalArgWithTopAtOneDivergence`), confirmed via git-stash to fail without the fix. Verified byte-identical across 9 examples including `var_compat` (the one real example exercising chained kind+unit+vertical-flip marshaling) -- full suite 607 passed (606+1 new)/1 xfailed, `ruff check` clean on new code); ~15 op `__init__`s in `ccpp_utils.py` repeating string-coercion boilerplate -- **RESOLVED (2026-08-18, task #47):** confirmed all 15 identical, no divergence; also found 4 more sites of the same boilerplate class (2 int-coercion in `VerticalFlipOp`/`VerticalFlipWriteBackOp`, 2 list-coercion in `RowMajorConvertOp`/`RowMajorWriteBackOp`) and folded them in too. Added `_coerce_str_attr()`/`_coerce_int_attr()`/`_coerce_str_list_attr()`; a near-verbatim `CCPPType`/`CCPPItem`/`CCPPArgument` duplication between `ccpp_xml.py` and `ccpp_descriptors.py` (task #48 -- **RESOLVED (2026-08-18):** confirmed only 3 of 8 same-named class pairs are actually identical; `CCPPArgumentTable.setAttr` has a real assert-vs-silently-ignore behavioral difference, and `CCPPTableProperties`/the `XMLSuite*` family aren't duplicates at all despite sharing names -- different pipeline stages (XML-text parsing vs. IR-reconstruction) -- both deliberately left alone in each file. Moved just the 3 genuinely-identical classes into new `xdsl_ccpp/util/ccpp_item.py`; both original files now import from there. Aside: found `ccpp_descriptors.py`'s `CCPPTableProperties.setArgTable` is dead code (asserts against the wrong class, `isinstance(v, CCPPArgument)` where `v` should be a `CCPPArgumentTable` -- never called anywhere, so never triggered; folded into task #61). Verified byte-identical across 9 examples); and several smaller ones (`constituent_cap.py`'s signature-splicing/precondition-guard patterns, `run_dispatch.py`'s inout-echo search, `cpp_interop.py`'s ad hoc arg-info dicts, `host_var_match_pass.py`/`gpu_ccpp_cap_pass.py`/`ccpp_descriptors.py`/`py_api.py` small helpers, `suite_meta.py`'s vestigial branch, `ccpp_cap.py`'s `_build_cap_var_map` dict consolidation). Tasks #44/#45/#47: full suite still 606 passed/1 xfailed after each, `ruff check` clean on all touched files.

**Tasks #49-#55, scoped 2026-08-18** (all of them turned out narrower, or shaped differently, than their one-line descriptions):
- **#50 (`run_dispatch.py` inout-echo search) -- RESOLVED:** confirmed exactly 2 byte-identical sites (the leading-inout-return and trailing-alloc-return branches' own `elif cap_var_map:` fallback). Extracted a nested closure `_find_cap_var_inout_ref(ret_type)`, same idiom as task #40's `_resolve_extra_dim_bounds` -- pure lookup, no insertion-order/anchor interaction, low risk. Verified byte-identical across 9 examples.
- **#53 (small cleanups B) -- RESOLVED, both items:** `ccpp_descriptors.py`'s `traverse_argument_op` had 10 identical `if "<flag>" in arg_op.properties: arg.setAttr("<flag>", True)` blocks -- collapsed into one `_ARG_BOOLEAN_FLAG_PROPS` tuple + loop, with every flag's own explanatory comment (6 of the 10 carried real institutional knowledge, e.g. a `capgen_v1_parity_backlog.md` Stage 7 citation) preserved verbatim in the tuple's own module-level comment rather than dropped. `py_api.py`'s `ccpp_ddt`/`ccpp_module`/`ccpp_host` were 3 byte-identical bodies (differing only in the literal table-type string) -- collapsed into `_table_descriptor_from_class(cls, table_type)`; `ccpp_scheme` correctly left alone (genuinely different: builds `entry_points` via a fixed list, not a `cls.__dict__` scan). Both verified byte-identical (the `py_api.py` decorators are also directly exercised by 4 passing test files).
- **#54 (`suite_meta.py` vestigial intent) -- RESOLVED:** confirmed genuinely vestigial -- all three intent branches plus the no-intent case did the exact same `in_args.append(arg_type)`, and `out_args` was always `[]`. Simplified to one unconditional append per arg, keeping the real `AssertionError` guard on an unrecognized intent value (moved to a single upfront check). Pure no-op refactor, verified byte-identical.
- **#49 (constituent_cap patterns) -- RESOLVED (2026-08-18):** signature-splicing was already unified for 4 of 8 subroutines; only `ca_lines`/`mp_lines`'s duplicated ternary was left, extracted as a shared `_instance_sole_arg` expression (sibling of the existing `_instance_arg`/`_instance_decl`). Precondition-guards are 4 distinct semantics (silent-skip, bare-return, **lazy-allocate** -- opposite polarity, full-error-return) -- only the 4 full-error-return sites (`ic_lines` x2, `ci_lines` x2) were merged into one `_error_guard(condition, errmsg_text)` nested helper; the other 3 guard shapes deliberately left untouched (collapsing them would paper over a real semantic difference, the same bug class Copilot's PR #77 caught). Verified byte-identical across 9 examples including both multi-instance ones (`instances`/`instances_advection`).
- **#51 (`cpp_interop.py` arg-info schema) -- RESOLVED (2026-08-18):** the original scoping's "3 construction sites" undercounted -- exhaustive re-read found **7**: `_chost_arg_info`'s canonical return, `_chost_expand_ddt_arg`'s DDT-member `ai`, `_chost_out_infos`'s 3 separate literals (errmsg/scheme_name/errflg), and one each in `_chost_maybe_inject_ncol`/`_chost_maybe_inject_nz`. Exhaustive grep across the whole file for every dict-access pattern (`ai[...]`, `.get(...)`, bracket-assignment) confirmed only bracket-read, `.get()`-read, and bracket-assignment mutation are ever used on these dicts -- no `**` unpacking, `.items()`, or containment checks anywhere -- which made a drop-in replacement safe. Implemented `ChostArgInfo`, a real `@dataclass` with all ~24 union fields declared and defaulted (each default matching what the read sites already assumed via their own `.get(key, default)` calls), plus `__getitem__`/`__setitem__`/`get()` methods as thin `getattr`/`setattr` wrappers -- so all ~100+ existing read/mutate call sites needed zero changes; only the 7 construction sites changed from `dict(...)` to `ChostArgInfo(...)`. The `rank`-computation-basis question from scoping (`_chost_arg_info` counts dynamic memref dims; `_chost_expand_ddt_arg` uses the DDT member's static `ndim`) is a divergence in what `rank` *means* at each site, not a schema gap -- both sites already unconditionally populate the field, so there's nothing for the schema to paper over; left the actual computations untouched as a deliberately separate, orthogonal question. `local_info` (a genuinely different dict built alongside DDT expansion, and `ctx`/`li` dicts read elsewhere) confirmed out of scope, left as plain dicts. Verified byte-identical raw output (not just FileCheck patterns) via git-stash across all 16 chost/bind(C)-exercising end-to-end targets (`kessler` x7, `tinyddt` x3, `chost-f32`/`chost-r3` x3, `ddt-intent-in/out-chost-ftn` x2, `bindC-cpp-header-xml`, `bindC-helloworld-xml`) -- the module's entire real usage surface, since `cpp_interop.py` is only ever invoked by `generate-cpp-cap`, which none of the 9 standard non-bind_c examples run. Full suite 607 passed/1 xfailed, `ruff check` clean (10 pre-existing F541 findings, confirmed identical via git-stash, already folded into task #61).
- **PR #78 Copilot review, addressed (2026-08-18):** three follow-on comments on the Tier 1/2
  cleanup PR, fixed independently of any single task above. (1) `cpp_interop.py`'s
  `ChostArgInfo.__getitem__` (task #51) raised `AttributeError` on a missing key instead of
  `KeyError`, breaking its own "drop-in dict replacement" contract for any future
  `except KeyError` caller -- fixed by catching and re-raising. (2) `ccpp_utils.py`'s
  `_coerce_str_attr` (task #47) was annotated `-> StringAttr` but `StrCmpOp.__init__` calls it
  unconditionally on its own `literal: str | StringAttr | None = None` param, so it can genuinely
  return `None` -- no runtime bug (the `None` is handled correctly downstream), just an inaccurate
  annotation; widened to `(str | StringAttr | None) -> (StringAttr | None)`. (3) `suite_cap.py`'s
  per-arg intent classification (`if intent in ("in", "inout", "out"):`, near task #42's own
  merged branch) silently dropped any arg with an unrecognized `intent` value instead of erroring
  -- likely unreachable today (intent is validated at `.meta`-parse time), but a silent-failure
  risk rather than fail-fast; added an explicit `raise ValueError` for the unrecognized case and
  de-indented the now-single-condition body (matching task #54's own precedent of moving an
  intent guard to a single upfront check). All three verified byte-identical across the full
  end_to_end filecheck set; full suite 607 passed/1 xfailed; `ruff check` shows the same
  pre-existing findings before/after (already tracked under task #61).
- **#52 (small cleanups A) -- Item A RESOLVED (2026-08-18), Item B deferred:** `host_var_match_pass.py`'s dim-split (2 identical 12-line `dim_names`-parsing blocks) extracted into a module-level `_parse_dim_names(arg_op)`, deliberately not merged with `validate_fir.py`'s superficially similar block (that one also lowercases and excludes digit-literal dims for a different purpose). Verified byte-identical. Item B (`gpu_ccpp_cap_pass.py` suite-arg iterator) is the same pattern as task #43's own "Shape B" (~25+ sites) -- folded into #43's eventual fix rather than a bespoke helper here.
- **#55 (`ccpp_cap.py` dict consolidation) -- RESOLVED (2026-08-18), narrowed per its own scoping:** the 4 top-level dicts `_build_cap_var_map` returns are NOT redundant (different consumers) and were left alone. The real opportunity -- 5 parallel per-arg dicts inside the per-group loop, all keyed by the same bare name, built in one pass -- was consolidated into one `dict[str, _CVArgInfo]` (a small dataclass: `std_name`/`dim_names`/`ownership_kind` keep "first occurrence wins" semantics via `None`-means-unset; `is_constituent`/`needs_gpu` are sticky-True). The "lc_instances lazy-alloc duplication" half of the original title didn't hold up (already covered by task #49's guard-check consolidation) and was dropped, as recommended during scoping. Verified byte-identical across 9 examples including `constituents_dim` (the CapScratch/framework-var-heaviest example).
- **Tier 3 — structural decomposition, started 2026-08-19** (tasks #56-#60): `suite_cap.py`'s `GenerateSuiteSubroutine` is a 2,929-line, ~50-method god-class with no single responsibility; `run_dispatch.py`'s `_build_run_dispatch_chain` is an ~800-line monolith breaking the file's own otherwise-good pattern of small dataclass-returning helpers; `print_ftn.py`'s `_print_fn` and `ccpp_cap.py`'s `_build_suite_variables_fn` each do 5-6 distinct jobs in one function; `suite_cap.py`'s kind/unit-cast construction and `_build_block_signature` have their own decomposition opportunities (the latter tied directly to task #30's existing chained-interstitial bug — fix together); and an open design question (not a mechanical fix) about whether `lifecycle_cap.py`'s inline arg-resolution dispatch should be unified with `run_dispatch.py`'s cleaner `ResolvedArgOp`/`ArgSourceKind` pattern. These touch the highest-traffic, most heavily-used files in the pipeline and need careful staged review with full regeneration/test verification at each step — the same discipline this engagement already used for the vocabulary-resolution redesign (Stages 1-4) and the multi-instance migration (5 stages). Scoped 2026-08-19 (re-verified sizes: `GenerateSuiteSubroutine` now 2,954 lines/49 methods; `_build_run_dispatch_chain` ~789 lines with **no internal seams at all** — a 14-param free function, one sprawling loop, no nested helper defs, genuinely the highest-risk item since it needs real semantic restructuring, not just code movement); recommended order **#58 → #56 → (fix #30) → #59 → #57**, #60 parked as a standalone design discussion. **#58 fully RESOLVED (2026-08-19)** — both halves done, see below.
  - **#58, `ccpp_cap.py::_build_suite_variables_fn` — RESOLVED (2026-08-19).** The function was already almost exactly two independent halves: (A) per-suite classification into an `(input, output, required)` variable-name tuple (its own already-labeled Pass 1a/1b/2/2b/2c/3 comments), and (B) rendering the resulting dict into the `ccpp_physics_suite_variables` Fortran text — B has zero dependency on A's internals. Extracted each labeled pass into its own module-level function (`_collect_interstitial_and_unit_mismatch_names`, `_classify_scheme_args_io`, `_add_dynamic_subcycle_input_names` + its `_collect_dynamic_subcycle_std_names` recursive helper, `_add_active_expr_referenced_names`, `_add_dimension_only_names`) plus `_render_suite_variables_subroutine` for part B, hoisting the two local constant aliases (`_INTERNAL`/`_ACTIVE_EXPR_KEYWORDS`) to module scope as `_SUITE_VARS_INTERNAL_STD_NAMES`/`_ACTIVE_EXPR_KEYWORDS` since they're now shared across multiple functions instead of one. The method itself shrank from ~362 lines to ~45, now a pure orchestrator calling the extracted pieces in sequence — pure code movement, every comment/docstring preserved verbatim (relocated, not rewritten), zero behavior change. Verified byte-identical across all 47 filecheck examples in the repo (`frontend`/`completed_ir`/`end_to_end`, not just the subset this function touches) plus the full unit suite (612 passed/1 xfailed, same as before); `ruff check` clean with zero findings (up from clean already). Landed on its own branch, `decompose-suite-variables-fn`, off the post-PR-#79 `main` tip.
  - **#58, `print_ftn.py::_print_fn` — RESOLVED (2026-08-19).** More entangled than the `ccpp_cap.py` half (a live print context, not a pure classification scan), but decomposed along its own already-clear comment boundaries into: a pure-analysis `@staticmethod _analyze_fn_body(bdy)` returning a new `_FnBodyAnalysis` dataclass (arg-name suffix-stripping, ReturnOp inout/output split, local-alloca collection, untracked-call-result collection, including the nested `_has_copy_consumer` closure, unchanged); `_setup_bind_c_char_conversions` (the BIND(C) char-remap side effect on `inner.variables`); `_declare_fn_arguments` (the dummy-argument declarations -- input + output, a natural pair matching Fortran's own arguments-then-locals declaration order); `_declare_fn_locals` (every local declaration: non-returned allocas, kind-cast/unit-convert/vertical-flip temps, row-major transpose temps, untracked-call-result locals, and the BIND(C) char/loop-counter buffers); and `_print_c_to_f_char_conversions`/`_print_f_to_c_char_conversions` (kept as two separate methods rather than one parameterized by direction, since the two loop bodies are genuinely asymmetric -- the C→F side additionally null-terminator-scans and blank-inits, the F→C side additionally appends the null terminator after -- forcing them into one shape would paper over that difference). `_print_fn` itself shrank from ~330 lines to ~45, now a pure orchestrator preserving the exact original call order (each step's dependency on the previous step's side effects -- e.g. `_setup_bind_c_char_conversions` must run after the input/output `inner.variables` registration so its `_f`-suffixed remap isn't immediately overwritten -- was checked and confirmed unchanged). Every comment/docstring preserved verbatim. Fixed 5 self-introduced `ruff` UP037 findings (unnecessarily-quoted `"ftnPrintContext"` forward-reference annotations -- unnecessary since the file already has `from __future__ import annotations`); the 3 remaining findings are pre-existing, confirmed identical via git-stash. Verified byte-identical across all 47 filecheck examples (this function is exercised by literally every example that gets Fortran-printed, so this is its entire real usage surface) plus the full unit suite (612 passed/1 xfailed). Landed on the same `decompose-suite-variables-fn` branch as the `ccpp_cap.py` half.
  - **PR #80 Copilot review, addressed (2026-08-19) — a design decision, not just a bug fix.**
    Flagged a real out-of-bounds write in `_print_f_to_c_char_conversions`'s F→C character
    marshaling: `c_name(len_trim(ftn_local)+1) = c_null_char` writes past the buffer if
    `ftn_local` (a `character(len=512)` local) is fully non-blank (`len_trim == 512`), since
    `c_name` is an assumed-size `character(*)` BIND(C) dummy -- the generated Fortran code has
    no way to know the caller's real buffer size at all. First fix attempt: clamp the copy
    length to `min(len_trim(ftn_local), len(ftn_local) - 1)`, silently dropping the 512th
    character in that one case. **Reverted per explicit user direction**: since the C++
    interop layer is entirely xdsl-ccpp's own invention (the CCPP specification only covers
    Fortran host models -- there is no external convention for C++ callers at all) and has zero
    real external users yet (only the examples/CI), baking in a silent truncation corner case
    was judged worse than fixing the actual root problem: the generated header never told
    callers how big to make the buffer. Real fix: `print_cpp_header.py` gained
    `_char_buffer_comment()`, emitting `/* caller must allocate >= N+1 bytes (N + null
    terminator) */` on every intent(out)/intent(inout) character BIND(C) parameter (and
    `/* null-terminated string, max N chars */` for intent(in), `/* ... any length */` for a
    dynamic/assumed-length `character(len=*)` param like `suite_name` -- guarded explicitly
    against printing the raw `DYNAMIC_INDEX` sentinel as a bogus length, caught while verifying
    the fix). `print_ftn.py` itself is unchanged from before this PR. Confirmed the same class
    of unguarded `len_trim(...)+1` write exists in `cpp_interop.py`'s own F→C copy loop (`do i =
    1, len_trim(...)`) but is NOT a live bug there: that code path is only ever fed by
    `cpp_interop.py`'s own generated C++ convenience wrapper, which already allocates
    `char errmsg[CCPP_ERRMSG_LEN + 1]` (513 bytes) -- confirmed by reading that wrapper's own
    generation code, not assumed. That wrapper's own header section (a separate, verbatim
    `cpp_text` code path, not touched by `print_cpp_header.py`) doesn't yet carry the same
    buffer-size documentation for the underlying BIND(C) functions it wraps, in case anyone
    calls them directly instead of through the wrapper -- flagged as a possible follow-up, not
    done here (genuinely a different file/code path, no live bug pushing it). Verified: full
    suite 612 passed/1 xfailed; `ruff check` shows the same 4 pre-existing findings before/after;
    byte-identical regeneration across the full 47-file filecheck corpus except the 7 files that
    exercise character BIND(C) params (all gained the new comment, confirmed harmless); added an
    explicit `CHECK` for the new comment text to `bindC-cpp-header-xml.mlir` so it's actually
    regression-guarded, not just incidentally unbroken by the existing prefix-only `CHECK`
    patterns.
  - **#56, `suite_cap.py::GenerateSuiteSubroutine` — scoped (2026-08-19), staged plan agreed.**
    Re-read the full 2,954-line/49-method class fresh (not relying on the earlier size estimate)
    and grouped its methods into roughly 9 clusters by what they actually depend on: (1)
    multi-instance synthesis (`_is_multi_instance_host`, `_synthesize_instance_number_arg`,
    `_synthesize_number_of_instances_arg`, `_instance_arg_local_name`,
    `_number_of_instances_local_name`, `_build_suite_state_lazy_alloc`) — pure functions of
    `self.meta_data`/explicit args, no other instance state; (2) dynamic-subcycle-count synthesis
    (`_synthesize_dynamic_loop_count_args` + its nested closures) — same shape; (3)
    active-expression conditional gating (`_ACTIVE_EXPR_TOKEN_RE`,
    `_active_expr_var_indexes`/`_active_expr_ddt_member_indexes`/`_resolve_active_condition`) —
    same shape, only `_build_active_gated_call_ops` itself stays behind since it also calls
    `self.generateSchemeSubroutineCallOps`; (4) the `--emit-resolved-vars` introspection
    bookkeeping block inlined in `generateSubroutineCall` — genuinely needs `self.resolved_vars`/
    `self.ddt_resolution_maps`/`self.host_var_index`, so it becomes a method, not a free
    function, but is still a clean single-purpose extraction; (5) kind/unit-cast construction;
    (6) `_build_block_signature`; (7) DDT-resolution-map plumbing (tangled with task #57's
    `_build_run_dispatch_chain` coupling — deferred, not mechanical); (8) the core
    `generateSubroutineCall`/`_build_arg_tables` orchestration (stays, it's the class's real
    reason to exist); (9) misc small helpers. Clusters 1-4 are pure mechanical extractions with
    no design judgment calls — recommended as **Stage 1**. Cluster 5-6 line up with task #59's
    existing description (kind/unit-cast helpers + `_build_block_signature` decomposition) —
    recommended as **Stage 2 = task #59**. Cluster 7 is tied to task #30's chained-interstitial
    bug fix and shouldn't be untangled before that bug is fixed — recommended as **Stage 3**,
    sequenced after #30. Cluster 9 folds into whichever stage touches its caller. Agreed order:
    Stage 1 (this task, mechanical) → Stage 2 (= #59) → fix #30 → Stage 3. User approved: "Go
    ahead and implement stage 1."
  - **#56 Stage 1 — RESOLVED (2026-08-19).** Extracted clusters 1-3 verbatim into new
    module-level free functions inserted in the pre-class free-helpers zone (same zone task #58
    used): `_resolve_host_only_std_name`, `_synthesize_dynamic_loop_count_args` (nested
    `_subcycle_has_active_schemes`/`_collect_dynamic_counts` closures preserved),
    `_is_multi_instance_host`, `_synthesize_instance_number_arg`,
    `_synthesize_number_of_instances_arg`, `_instance_arg_local_name`,
    `_number_of_instances_local_name` (both `_*_local_name` functions inline the
    `a.getAttr("standard_name").lower() if a.hasAttr(...) else a.name` std-key check that used to
    live in a shared private helper, since neither depends on other instance state),
    `_build_suite_state_lazy_alloc` (trivial move, was already `@staticmethod`), plus a new
    module constant `_ACTIVE_EXPR_TOKEN_RE` and free functions
    `_active_expr_var_indexes`/`_active_expr_ddt_member_indexes`/`_resolve_active_condition`
    (nested `_resolve_ddt_member`/`_substitute` closures preserved). `_build_active_gated_call_ops`
    stays on the class (per the scoping note above) but now calls
    `_resolve_active_condition(self.meta_data, ...)` instead of `self._resolve_active_condition(...)`.
    Cluster 4 (`--emit-resolved-vars` bookkeeping) became a new method,
    `_record_resolved_vars_for_phase`, since it genuinely needs `self.resolved_vars`/
    `self.ddt_resolution_maps`/`self.host_var_index` — the ~50-line inline block in
    `generateSubroutineCall` is now a single call to it. All 8 call sites across
    `_build_active_gated_call_ops`, `_build_arg_tables`, `generateSubroutineCall`, and
    `_build_state_globals` updated to the new free-function/method calls; confirmed via grep that
    zero stray `self._` references to any moved method remain. Pure code movement, every
    docstring/comment preserved verbatim, zero behavior change. Verified: full suite 612
    passed/1 xfailed (unchanged); `ruff check xdsl_ccpp/transforms/suite_cap.py` shows the same 2
    pre-existing findings before/after (unused `i32` import, `F841 scheme_entries` unused local at
    line 2845 in `generateSubroutineCall` — confirmed via git-stash, neither touched by this
    stage); the 47-file filecheck corpus is wired into the pytest run itself (`tests/conftest.py`
    discovers every `*.mlir` under `tests/filecheck/`), so the same 612-passed run already is the
    byte-identical regeneration check — no separate diff pass needed. Landed on branch
    `decompose-generate-suite-subroutine`, off `main` at `2c7c390` (the post-PR-#80 merge tip).
    Stage 2 (task #59) and Stage 3 (after task #30) not started — staged plan, one stage at a
    time per this engagement's established pattern.
  - **#56/#59 Stage 2 — RESOLVED (2026-08-19).** Target: cluster 5 (kind/unit-cast
    construction) and cluster 6 (`_build_block_signature`) from the Stage 1 scoping note above.
    (Cluster 4, `--emit-resolved-vars` bookkeeping, was already folded into Stage 1 as
    `_record_resolved_vars_for_phase` -- task #59's description names all three, but two were
    already done by the time this stage started.) First promoted 5 small `@staticmethod`
    helpers used throughout `_build_block_signature` (and ~15 other call sites across the
    class) to true module-level free functions, since none of them touch instance state:
    `_std_key`, `_vertical_dim_index`, `_has_dims`, `_arg_dims`, `_block_arg_kind` -- every
    `self._x(...)` call site across the whole class updated to `_x(...)` (mechanical rename,
    confirmed via grep no `self._std_key`/etc. references remain except one bare
    `self._std_key` passed as a callback into `SuiteVariableModel(...)`, updated to the bare
    function reference `_std_key`). Then decomposed `_build_block_signature` itself (previously
    ~227 lines, one long function building the Block, resolving dummy-arg name-hint collisions,
    applying kind casts, applying unit conversions, allocating output/error args, and tagging
    data_ops by standard-name) along its own already-commented boundaries into:
    `_build_block_and_name_hints` (Block construction + collision-disambiguated name hints +
    initial `data_ops`/`final_values`), `_apply_kind_casts`/`_apply_unit_conversions` (the two
    "kind/unit-cast helpers" the task title names -- kept as two functions rather than one
    parameterized by cast-kind, matching the same reasoning task #58 used for
    `_print_c_to_f_char_conversions`/`_print_f_to_c_char_conversions`: the two loop bodies use
    genuinely different ops/type-conversion arguments, not just a swapped direction flag),
    `_alloc_output_error_args` (the errflg/errmsg fallback-allocation block), and
    `_tag_data_ops_by_std_name` (the final `("std_name", ...)`-tagged registration loop).
    `_build_block_signature` itself shrank to a ~20-line orchestrator, still a method (its
    signature/return type `_BlockSignature` is unchanged) since it's the one piece
    `_assemble_func`/`generateSubroutineCall` actually call. Every docstring/comment preserved
    verbatim, pure code movement, zero behavior change. Left `_build_suite_lifecycle_call_ops`'s
    own `_apply_divergent_marshaling` closure untouched -- it's the per-scheme-call-site
    counterpart for divergent standard_names (already cross-referenced by a comment at this
    function's own site before this stage), genuinely a different call site with different
    write-back-op types, not a duplicate of the extracted loops. Verified: full suite 612
    passed/1 xfailed (unchanged); `ruff check` shows the same 2 pre-existing findings before/after
    (unused `i32` import, `F841 scheme_entries` unused local -- both untouched by this stage,
    already confirmed pre-existing during Stage 1's own verification); the 47-file filecheck
    corpus is exercised inside that same pytest run, so no separate byte-diff pass was needed.
    `GenerateSuiteSubroutine` is now 34 methods / ~2,245 lines, down from 49 methods / 2,954
    lines at the start of task #56. Landed on branch `decompose-suite-cap-stage2`, off `main` at
    `d2472b1` (the post-Stage-1-merge tip). Stage 3 (DDT-resolution-map plumbing, sequenced
    after task #30's fix) not started.
  - **#56 Stage 3 — redirected (2026-08-19) before implementation, then RESOLVED against the
    redirected target the same day.** Re-checked the original "Cluster 7: DDT-resolution-map
    plumbing" scope fresh against the current code before touching anything, since Stage 1/2 and
    task #30's fix had since reshaped large parts of the class. Found the original scope had
    already evaporated: what's left of the DDT-resolution plumbing inside
    `GenerateSuiteSubroutine` is just the constructor storing `ddt_source_module`/
    `host_var_index`/`ddt_resolution_maps` plus three small read-sites
    (`_apply_ddt_chain(...)`, `self.host_var_index.get(...)`,
    `_collect_ddt_use_stubs(...)`) -- the actual resolution logic
    (`_build_ddt_resolution_maps`/`_resolve_ddt_access_path`) already lives in `cap_shared.py`
    as free functions, already shared by both `suite_cap.py` *and* `run_dispatch.py` (confirmed
    by grep -- no duplication between them to unify, contrary to the original "tangled with
    task #57" concern). No large method left in this cluster to decompose.
    **Redirected instead to the real complexity hotspot that emerged from task #30's own
    implementation**: `_build_call_ops` and `_build_framework_refs` had grown to 278 lines each
    -- now the two largest methods in the class, bigger than anything Stage 1/2 had already
    extracted from, entirely as a side effect of adding the `pending_allocs`/
    `resolved_producers` mechanism-1/2 logic into both without decomposing the surrounding
    structure at the time.
    - **`_build_call_ops`**: its four nested closures (`_flush_promoted`, `_emit_ordered_list`,
      `_emit_subcycle_items`, `_emit_subcycle`) shared mutable state (`fn_sigs`,
      `resolved_producers`, `pending_allocs`, `hoisted_allocas`) entirely via Python closure
      capture. Converted each into a proper method, threading the previously-closed-over
      read-only parameters through a new `_CallSeqContext` dataclass (bundling `all_args`/
      `data_ops`/`framework_ref_ops`/`suite_use_stubs`/`actual_postfixes`/
      `tgt_subroutine_postfix`/`physics_mode`/`scheme_overrides`/`divergent_std_keys`/
      `arg_tables` -- ten params that don't change across the whole call-sequence walk) and
      passing the genuinely-mutated accumulators (`fn_sigs`, `resolved_producers`,
      `pending_allocs`, `hoisted_allocas`) as explicit arguments, exactly as Stage 1/2 already
      did for other shared-mutable-state extractions. Additionally pulled the retry-and-splice
      block out of `_emit_ordered_list` into its own `_resolve_and_splice_pending_allocs` method,
      and the final unresolved-pending-allocs error into a free function,
      `_raise_unresolved_pending_allocs_error`. `_build_call_ops` itself shrank from 278 lines to
      a ~65-line orchestrator.
    - **`_build_framework_refs`**: decomposed along its own three already-distinct phases into
      `_build_framework_var_ref` (HostVarRefOp/ArraySectionOp construction for one framework
      var), `_maybe_schedule_framework_var_alloc` (task #30's mechanism-1/2 allocation decision
      for one var), and `_sweep_suite_owned_var_allocations` (the whole `suite_owned_vars()`
      sweep, as its own method since it's fully self-contained once handed the shared
      accumulators). The small tail aliasing loop became a free function,
      `_alias_canonical_data_ops` (previously uncommented inline code; given a docstring since
      extraction is a natural point to explain what it does). `_build_framework_refs` itself
      shrank from 278 lines to a ~65-line orchestrator.
    Pure code movement, every comment/docstring preserved verbatim (or added, for the two
    previously-uncommented tail blocks); zero behavior change. Verified: full suite still 620
    passed/1 xfailed (unchanged); `ruff check` shows the same 2 pre-existing findings
    before/after; the 47-file filecheck corpus is exercised inside that same pytest run, so no
    separate byte-diff pass was needed. `GenerateSuiteSubroutine` is now 43 methods/~2,487
    lines (methods count went up, since splitting one large method into several smaller named
    ones adds some `def`/docstring overhead per Stage 1/2's own established pattern -- the real
    win is that the two largest remaining methods are now ~65 lines each instead of 278).
    **Task #56 is now fully complete** -- all three stages done, no further stages planned.
  - **PR #82 Copilot review, addressed (2026-08-19) — a real, pre-existing correctness bug,
    surfaced (not introduced) by Stage 2's decomposition.** Flagged: when a single arg carries
    BOTH a kind mismatch and a unit mismatch against the host at once (e.g. host declares
    kind_phys/meters, scheme declares kind=8/centimeters -- the ordinary non-divergent case,
    every scheme sharing the standard_name agrees with every other scheme, only the host
    differs), `_apply_kind_casts` and `_apply_unit_conversions` each independently read from
    and wrote back to the raw original block arg instead of chaining, so "the kind write-back
    can be overwritten by the unit write-back." Reproduced directly (single-scheme suite, arg
    with both mismatches, intent inout): the forward direction happened to end up numerically
    right by accident (Fortran auto-promotes real-kind in expressions, so computing the unit
    scale directly from the untouched host value rather than from the kind-cast result still
    lands on the same number) but generated a fully dead, disconnected `_kind_cast` temp; the
    write-back direction was worse -- both write-backs targeted the same original arg, and only
    got the right *final* answer because `_assemble_func` happens to always emit all
    kind-write-backs before all unit-write-backs, so the unit one (reading the real, post-call
    value) always overwrote the kind one (reading a stale pre-call snapshot) last. Confirmed via
    `git blame`-equivalent reasoning this predates Stage 1/2 entirely -- both stages preserved
    the logic verbatim per this engagement's "pure code movement" discipline; Copilot's review
    just happened to land on a PR whose diff touches these lines. No existing test exercised
    this combination (`test_suite_cross_scheme_unit_kind.py`'s own `TestDivergentKindAndUnitsChain`
    tests the DIFFERENT, already-correct cross-scheme-divergent case, which goes through
    `_apply_divergent_marshaling` instead). Fix: merged `_apply_kind_casts`/`_apply_unit_conversions`
    into one `_apply_kind_and_unit_casts`, mirroring `_apply_divergent_marshaling`'s own
    proven-correct chain/reversed-writeback pattern exactly -- build a per-arg forward chain
    (kind cast, then unit convert, each reading the previous step's own result), then on
    write-back walk that chain in reverse, emitting fully-built `KindWriteBackOp`/
    `UnitWriteBackOp` instances directly into a single ordered `writeback_ops` list (replacing
    the old `kind_writeback_pairs`/`unit_writeback_pairs`, which could only represent "all kind
    write-backs, then all unit write-backs" globally -- structurally unable to express "this
    arg's unit write-back before this arg's own kind write-back," which chaining requires).
    `_BlockSignature`/`_assemble_func`'s signatures updated accordingly (both have exactly one
    caller, so the blast radius was contained). Verified generated Fortran directly: forward
    `x_kind_cast = real(x, kind=8)` then `x_unit_conv = x_kind_cast * 100.0_8` (now chained, was
    `x * 100.0_8`); write-back `x_kind_cast = x_unit_conv * 0.01_8` then
    `x = real(x_kind_cast, kind=kind_phys)` (unit undone first into the kind-cast's own temp,
    then kind undone into the true original -- matching `_apply_divergent_marshaling`'s own
    "must be undone unit-first, kind-second" comment). Added
    `tests/unit/test_suite_boundary_kind_and_unit_chain.py` (3 tests) pinning this exact
    chained forward/write-back shape; confirmed each test actually fails against the pre-fix
    code via git-stash (not just passes against the fix). Full suite now 615 passed/1 xfailed
    (612 + 3 new); `ruff check` unchanged (same 2 pre-existing findings, new test file itself
    clean). Landed on the same `decompose-suite-cap-stage2` branch.
  - **Task #57, `run_dispatch.py::_build_run_dispatch_chain` — RESOLVED (2026-08-20).** Re-scoped
    fresh before touching anything, since this was flagged (2026-08-19 scoping) as genuinely the
    highest-risk item in Tier 3 -- "a 14-param free function, one sprawling loop, no nested
    helper defs" with "no internal seams at all," unlike `suite_cap.py`'s own decompositions
    which could hang off already-separate closures. Read the full 789-line body end to end
    before designing anything (deliberately not just skimming for `def` boundaries, since the
    earlier scoping already confirmed there weren't any at the top level). Found the function
    actually does have real internal structure, just not expressed as nested `def`s: a
    two-level loop (per suite name, then per suite part, both walked in `reversed()` order to
    build the nested if/else chain inside-out) whose inner body is organized into four
    already-comment-delimited sections ("HostVarRefOps", "ArraySectionOps",
    "RowMajorConvertOps", the call-building + copy-back block), plus three small nested
    closures (`_find_cap_var_inout_ref`, `_resolve_extra_dim_bounds`, `_result_keyword_name`)
    redefined on every inner-loop iteration, capturing per-suite-part loop-local state. The one
    genuinely tricky spot: `_build_array_section_ops`'s own per-arg loop has a shared tail (var-
    descriptor lookup + column-chunk bound resolution) reached by *both* the Host and DdtMember
    branches falling through (not `continue`-ing), while the CapVar branch and the `else`
    always `continue`s before reaching it -- extracted as one cohesive per-arg decision, not
    split further, to avoid disturbing that control-flow relationship.
    **Design**: bundled the invariant, read-only parameters (`block_arg_map`,
    `non_host_std_to_canonical`, `host_var_map`, `meta_data`, `cap_var_map`,
    `state_host_var_map`, plus the two mutable-but-shared-throughout accumulators
    `seen_host_globals`/`chain_global_ops`) into a new `_RunChainCtx` dataclass, mirroring
    `suite_cap.py`'s own `_CallSeqContext` from task #56 Stage 3 -- the same shape of problem
    (many params invariant across a whole call-sequence walk) got the same solution. Extracted,
    in dependency order: `_build_state_host_var_map` (the small preamble block),
    `_build_suite_part_not_found_branch`, `_build_cap_var_std_to_dims`, `_build_host_var_refs`,
    `_build_array_section_ops` (kept `_resolve_extra_dim_bounds` as a nested closure inside it,
    unchanged, rather than converting its `nonlocal one_const_for_sections` into an artificial
    mutable-box parameter -- the nesting relationship to its own enclosing function is identical
    to before, just one level shallower overall), `_build_row_major_convert_ops`,
    `_build_call_args`, `_build_call_and_copy_back_ops` (kept `_find_cap_var_inout_ref`/
    `_result_keyword_name` as nested closures for the same reason), and
    `_build_one_suite_part_dispatch` (the per-suite-part orchestrator, called once per inner-
    loop iteration). `_build_run_dispatch_chain` itself shrank from 789 lines to a ~100-line
    orchestrator (mostly docstring) walking `per_suite_grouped` and delegating each suite part
    to `_build_one_suite_part_dispatch`. Pure code movement, every comment/docstring preserved
    verbatim, zero logic changes.
    **One real (if minor) finding, not a regression**: `_build_array_section_ops`'s own
    DdtMember branch unpacks `instance_var, instance_module, member_name = (...)` but never
    reads `instance_var` -- true in the *original* code too, but `ruff`'s F841 check hadn't
    flagged it there because the *other* DdtMember branch (now `_build_host_var_refs`, which
    *does* use `instance_var`) shared the same enclosing scope in the original monolithic
    function; per-name dead-store analysis apparently doesn't distinguish separate bindings of
    the same name within one scope as finely as it does across genuinely separate function
    scopes. Splitting the two branches into their own functions correctly surfaces the
    already-dead second binding. Fixed inline (renamed to `_instance_var`, matching this
    codebase's existing convention for intentionally-unused unpacked values) rather than left
    as a new finding, since it's a trivial, zero-behavior-change, one-line fix directly caused
    by this decomposition.
    **Verified**: full suite still 620 passed/1 xfailed (unchanged); `ruff check` shows the same
    16 pre-existing findings before/after once the `instance_var` fix above is applied
    (confirmed via git-stash: 16 before this change, 17 immediately after extraction, 16 again
    after the one-line fix); the 47-file filecheck corpus is exercised inside that same pytest
    run and stayed byte-identical -- confirming zero behavior change, including through the
    trickiest shared-tail control flow in `_build_array_section_ops`. No new test added:
    `_build_run_dispatch_chain` is exercised by every example with a `_run`-phase dispatch (63
    existing unit tests directly targeting array-section/row-major/DDT-member behavior, plus
    the full filecheck corpus), giving strong existing regression coverage for pure code
    movement with no logic change -- matching how #56 Stage 3's own pure-movement work was
    verified. Landed on branch `decompose-run-dispatch-chain`, off `main` at `c95eabe` (the
    post-Stage-3-merge tip).
  - **PR #85 Copilot review, addressed (2026-08-20).** Flagged `cv_type` unpacked from
    `cap_var_map` but never read, at two sites (`_build_host_var_refs` and
    `_build_call_and_copy_back_ops`'s own `_find_cap_var_inout_ref` closure). Confirmed
    pre-existing (checked against `main`, unchanged by the decomposition -- these lines just
    moved location) and, unlike the `instance_var` case above, genuinely the odd one out: the
    *third* element of the same tuple unpack is already marked `_ftn`/`_` at both sites for
    being unused, so `cv_type` never getting the same treatment looks like a plain oversight
    rather than a deliberate choice. Fixed both to `_cv_type`, matching the codebase's own
    existing convention. Verified: full suite still 620 passed/1 xfailed; `ruff check` unchanged
    (same 16 pre-existing findings -- this specific pattern isn't one `ruff`'s own F841 rule
    currently flags at all, since it doesn't apply unused-variable checks to tuple-unpacking
    from a non-literal right-hand side the way it does for the `instance_var` case's literal
    tuple; fixed anyway since Copilot's underlying code-quality point holds regardless of which
    linter happens to catch it).
- **Tier 4 — minor/verify-first, deliberately deferred** (tasks #61-#62): a handful of small items needing confirmation before touching (two flagged-deprecated op aliases that may be dead, a possibly-fully-subsumed `ArraySectionOp`, a possibly-superseded CLI tool, a possibly-dead-or-possibly-buggy branch in `visitor.py`, a raise-to-fall-through control-flow pattern, cosmetic nits) plus a security/robustness item (`ccpp_dsl.py`'s `os.system()` calls with interpolated paths, alongside the same duplication this whole audit is about). **Updated 2026-08-18:** task #61 also now folds in a batch of pre-existing `ruff check` findings (unsorted imports, unused imports, 15 unused locals from dataclass-unpacking in `run_dispatch.py`) noticed incidentally while verifying tasks #37-#40 -- confirmed via git-stash to predate all of them, zero-behavior-change cleanup, not fixed inline since out of scope for those specific tasks.

**Execution decision (user, 2026-08-18): log everything as tracked tasks (done, tasks #37-#62 above), then execute Tier 1 + Tier 2 in this session; Tier 3 and Tier 4 stay backlog for a dedicated future session.** See each task's own description for the full finding detail — not duplicated in prose here to avoid the two ever drifting apart.

- **Task #62 — Done (2026-08-24).** Replaced all four `os.system(f"...")` shell-string calls in
  `ccpp_dsl.py` (`run_frontend`, `run_py_frontend`, `run_opt`, `generate_cpp_headers`) with a new
  shared `run_pipeline_stage(cmd, out_path, label)` helper built on `subprocess.run(cmd,
  stdout=out_f)`, `cmd` now an argv list rather than an interpolated string -- matching the
  pattern `ccpp_validate_fir.py`/`fir2meta.py`/`flang_utils.py` already use elsewhere in this
  same `tools/` directory. Only stdout is redirected to a file (matching each stage's own prior
  `> "{out}"` shell redirection); stderr is left to inherit the parent process, unchanged from
  `os.system()`'s own behavior, so a subprocess crash's traceback still surfaces directly rather
  than being silently swallowed.
  - **Found and fixed a real latent regression risk while doing this, not just the requested
    duplication/injection fix.** `_build_pipeline`'s `--emit-resolved-vars` handling built
    `generate-suite-cap{emit_resolved_vars=\"{path}\"}}` with backslash-escaped quotes --
    necessary *only* because the whole pipeline string used to be re-embedded inside its own
    double-quoted shell argument (`-p "{pipeline}"`), relying on the shell to unescape `\"` into
    a literal `"` before `ccpp_opt.py`'s own pass-pipeline lexer
    (`xdsl.utils.parse_pipeline`'s `STRING_LIT` token, which requires genuine unescaped `"`
    delimiters) ever saw it. With the shell layer removed, that escaping would have reached the
    lexer as literal backslash-quote characters, breaking `--emit-resolved-vars` outright.
    Confirmed by reading `xdsl/utils/parse_pipeline.py`'s own `STRING_LIT` regex directly, not
    by inference. Fixed by dropping the backslash escaping now that there's no shell to strip it.
  - **Verified beyond the unit suite, which doesn't actually exercise this code path** (every
    filecheck/unit test invokes `ccpp_opt`/`ccpp_xml` directly, not through `ccpp_dsl.py`'s own
    orchestration) -- ran the real CLI end-to-end three ways: (1) a plain run (no flags), (2)
    `--bind-c --emit-resolved-vars <path>` (the exact path the quoting fix touches, plus
    `generate_cpp_headers`'s own separate `subprocess.run` call), confirming the emitted
    `resolved_vars.json` parses correctly and contains real `phases`/`host_vars` content: and
    (3) a deliberately malicious output path
    (`tricky $(touch /tmp/PWNED)'dir`) to prove the injection surface is actually closed, not
    just theoretically -- generation succeeded normally into that path and the injected command
    never executed. Full suite: 628 passed/1 xfailed/0 failed; `ruff` unchanged (276, git-stash
    baseline).
  - **Copilot review follow-up on PR #91 (2026-08-24), fixed.** Copilot correctly flagged that
    `run_pipeline_stage()` ignored the subprocess's own exit status entirely: a nonzero exit
    that still wrote *some* (partial/wrong) non-empty content to `out_path` would slip past
    `post_stage_check`'s existence/non-empty check undetected, and a missing executable would
    surface as an uncaught `FileNotFoundError` traceback rather than a clean CLI error (genuinely
    new relative to `os.system()`, which never raised that). Fixed: capture the
    `CompletedProcess`, exit with a clear message + the subprocess's own exit code on nonzero
    return, and catch `FileNotFoundError` with a message matching `flang_utils.py`'s own
    `run_flang` style. stderr still isn't captured, so failures remain immediately visible.
    Verified with a real malformed-but-existing suite file that crashes the frontend subprocess
    -- confirmed the pipeline now stops immediately with a clear error instead of proceeding
    past the failed stage -- plus a nonexistent-executable case (clean error, no traceback) and
    a full suite re-run (628/1/0, `ruff` unchanged). Landed as a second commit on the same PR,
    not an amend.
- **Task #61 (2026-08-24): scoped in full, doesn't hold up as one atomic task -- split.** Read
  all 9 items in the original 2026-08-18 audit description against the current, real code (not
  the audit's own claims) before touching anything:
  - **Confirmed genuinely dead/trivial, zero real risk (items 1-5 as split for execution,
    tackled as one batch):** `AllocatableModVarOp`/`ModuleTypeVarOp` (zero callers anywhere
    beyond their own definitions); `util/visitor.py`'s unreachable `visit_*` dispatch branch
    (confirmed genuinely dead, not a latent bug -- zero subclasses anywhere define a `visit_*`
    method, only `traverse_*` is ever used); `ccpp_descriptors.py`'s `setArgTable` (zero callers
    -- its own type-contract bug, asserting the wrong class per its own docstring, never fires);
    the stray `# end if`/`# end while` comments (`suite_cap.py`'s own instances are *already
    gone*, cleaned up incidentally during this session's own heavy editing of that file --
    confirmed via `grep`; only `util/ir_utils.py:64` remains); and the bulk of the pre-existing
    `ruff` findings from the original audit's item 8 (confirmed still present: 63 of the current
    276 total findings are in the 7 files the audit listed, mostly `--fix`-able I001/F401).
  - **Needs care but still small (items 6-8, deferred to a later pass, not split into their own
    tasks):** `run_dispatch.py`'s deliberately-raised-`AssertionError`-as-control-flow (confirmed
    still present, now around line ~1170 -- line numbers drifted from this session's own
    editing); the ~15 F841 unused-locals in `run_dispatch.py` (each needs a per-case delete-vs-
    underscore-prefix judgment call, not a blind fix); `_result_keyword_name`'s closure (real,
    but "hoist to module level" isn't a one-line move -- it captures `ctx` and 3 other locals,
    so hoisting means real parameter-threading).
  - **Bigger or less certain than the original audit assumed -- split into their own backlog
    items rather than left under #61:** task #70 (`ArraySectionOp` vs `RankReducingSliceOp` --
    `ArraySectionOp` is not dead, actively used across 5 files including the highest-risk
    dispatch code in this repo, so this is a real M-sized refactor, not a minor cleanup); task
    #71 (`ccpp_validate_fir.py` vs `ccpp_validate_source.py --backend flang` -- strong evidence
    of redundancy, but needs a real diff + a `DEVELOPERS.md` update decision, not a same-sitting
    deletion).
  - **Items 1-5 — Done (2026-08-24).** Deleted `AllocatableModVarOp`/`ModuleTypeVarOp`
    (`ccpp_utils.py`, re-confirmed zero callers beyond their own definitions immediately before
    deleting); `util/visitor.py`'s unreachable `visit_*` dispatch branch (re-confirmed zero
    subclasses anywhere define one); `ccpp_descriptors.py`'s dead `setArgTable` (re-confirmed
    zero callers; also confirmed removing it doesn't affect `arg_tables` population elsewhere,
    since nothing populated it through this method's own wrapper anyway); all 4 stray
    `util/ir_utils.py` end-marker comments (a broader sweep than the original audit's own
    two-pattern grep found all 4 -- `# end if`/`# end for` x3 -- not just the one the narrower
    search caught). Ran `ruff check --fix` for the safe-fix portion of item 8's ruff findings.
    **First attempt overshot scope significantly**: running `--fix` unscoped touched 51 files
    across the whole repo, not the 7 files item 8's own audit identified -- reverted the 43
    files outside that intended scope via `git checkout --` before proceeding, keeping only the
    fix in the files actually in scope (6 of the original 7 -- `ccpp_validate_source.py` had
    nothing auto-fixable, so it stayed untouched). Verified the ~15 F841 unused-locals in
    `run_dispatch.py` (item 7, explicitly deferred) were never touched by this pass -- confirmed
    via diff inspection, only an import-sort line changed in that file. Full suite: 628
    passed/1 xfailed/0 failed (unchanged). `ruff`: 276 -> 225 (51 fixed, matching the scoped
    portion of item 8 exactly).
  - **Items 6-8 — Done (2026-08-24), all in `run_dispatch.py`.** Item 6: replaced the
    `try/except (KeyError, AssertionError)` control-flow pattern (a deliberately-raised
    `AssertionError` used as a goto into the "search DDT tables instead" branch) with explicit
    `in mod_arg_table.function_arguments` membership checks -- exactly equivalent, not just
    similar, since `getFunctionArgument`'s only possible exception is the `KeyError` from its
    own plain dict lookup. Item 7: the ~15 F841 unused-locals from the `_maps`/`_sig`/`_pre`
    dataclass-unpacking pattern -- each is genuinely a documentation-style "spell out every
    field this helper returns" unpack, so `_`-prefixed rather than deleted, preserving that
    readability rather than leaving gaps a reader might mistake for missing fields. Item 8:
    hoisted `_result_keyword_name` out of `_build_call_and_copy_back_ops`'s own body (where it
    was a closure rebuilt fresh on every call -- once per suite part) to module level, threading
    `ctx`/`n_inout_ret`/`leading_inout_ret`/`run_ret_alloc` through as explicit parameters
    instead of closure capture, matching this file's own established convention of module-level
    helpers taking `ctx` as their first parameter. Verified: full suite 628 passed/1 xfailed/0
    failed (unchanged); `run_dispatch.py` itself now has zero `ruff` findings at all (was 15);
    total `ruff`: 225 -> 210.
- **Task #66 — double-`"_suite"` naming convention (scoped 2026-08-24, Stage 1 done
  2026-08-24).** `suite_cap.py` builds every generated Fortran dispatch function name as
  `suite_name + "_suite" + phase` (e.g. `_register`/`_init`/`_run`/...). Real capgen-v1 never
  inserts that infix at all -- confirmed directly against
  `ccpp-framework-fresh/capgen/generator/suite_cap.py:1284-1290`, which builds dispatch names as
  plain `suite_name + phase`. Because 19 of this repo's ~24 example suites already name
  themselves ending in `_suite` (a convention this codebase itself established, not one
  capgen-v1 requires), the result is names like `kessler_suite_suite_register` -- a real
  double-`"suite"` artifact, not a typo, and not merely cosmetic: it means this codebase's own
  generated symbol names don't match what a real capgen-v1-driven host (i.e. CAM-SIMA) expects
  to link against. Initially assessed (wrongly) as low-priority/purely-cosmetic; corrected after
  confirming with the user that CAM-SIMA compatibility is exactly why this needs fixing, not an
  optional polish item.
  - **Scoping.** The infix turned out to be duplicated as ~15-20 independent literal-string
    occurrences, not a single shared helper: two construction sites in `suite_cap.py` itself
    (the FuncOp name builder and an `endswith("_suite_finalize")` check); a separate constituent-
    callee construction site plus all 8 entries of the `lifecycle_specs` table in `ccpp_cap.py`;
    and `gpu_data_pass.py`/`gpu_ccpp_cap_pass.py`, each with their own independent copy of
    suffix-matching logic for GPU-directive dispatch. 26+ existing filecheck fixtures already
    contain the literal `"suite_suite"` string, an undercount of the true impact since it only
    counts sites where the golden file happens to substring-match, not every generation path
    that builds the name. Agreed 2-stage plan with the user: **Stage 1** centralizes the infix
    into one shared constant with zero behavior change (verifiable against the existing
    fixture/unit suite, no golden files need updating); **Stage 2** is the actual rename
    (dropping the infix), deliberately deferred as its own, higher-risk step -- filecheck can
    catch a *missed* literal-string site turning into a compile-time link failure, but can't by
    itself rule out a silently-wrong GPU-directive-matching regression, so Stage 2 will need real
    CI, not just the local suite, before being called done.
  - **Stage 1 -- Done (2026-08-24).** Added `SUITE_FN_INFIX = "_suite"` to
    `xdsl_ccpp/transforms/util/cap_shared.py` (alongside its existing `LIFECYCLE_POSTFIX_ALIASES`/
    `_PHASE_SUFFIXES` naming-convention constants) as the single source of truth, then replaced
    every one of the ~15-20 literal `"_suite"` construction/matching sites in `suite_cap.py`,
    `ccpp_cap.py`, `gpu_data_pass.py`, and `gpu_ccpp_cap_pass.py` with references to it.
    Deliberately left untouched: `ccpp_cap.py`'s `_derive_camel_case_name`'s own
    `if name.endswith("_suite")` check -- a different, unrelated mechanism (stripping a suite's
    *own declared name* for CamelCase conversion, nothing to do with the dispatch-name infix) --
    and `suite_cap.py`'s pre-existing `errmsg_fn_name` construction, which already omits the
    infix today (used only for error-message text, not the real function name), a pre-existing
    inconsistency with the real function name that Stage 1 intentionally left alone since fixing
    it would change observable error-message text -- worth revisiting once Stage 2 lands, since
    matching capgen-v1's real convention exactly would make both names agree for free. Verified
    zero behavior change three ways: full suite `python -m pytest tests/filecheck tests/unit -q`
    -> 628 passed/1 xfailed (byte-identical to the pre-Stage-1 baseline, meaning every one of the
    26+ `"suite_suite"` fixtures still matches); `ruff check .` -> 210 (unchanged); and a live
    regeneration diff on `examples/kessler` (git-stash the Stage 1 changes, regenerate into
    `/tmp/kessler_before`, pop the stash, regenerate again into `/tmp/kessler_after`, `diff -r`
    the two) -- the only difference was `datatable.xml`'s own embedded absolute output paths
    (an artifact of the two runs using different `-o` directories, not a real diff); the actual
    generated `kessler_suite_cap.F90`/`Kessler_ccpp_cap.F90`/`ccpp_kinds.F90` were byte-identical.
    Files modified (uncommitted, on branch `double-suite-naming-stage1`):
    `xdsl_ccpp/transforms/util/cap_shared.py`, `xdsl_ccpp/transforms/suite_cap.py`,
    `xdsl_ccpp/transforms/ccpp_cap.py`, `xdsl_ccpp/transforms/gpu_data_pass.py`,
    `xdsl_ccpp/transforms/gpu_ccpp_cap_pass.py`. Stage 2 (the actual rename) not started --
    awaiting go-ahead given its blast radius (near-universal fixture updates expected, real risk
    of a missed site surfacing only as a link failure or a silent GPU-directive mismatch, neither
    fully catchable by the local suite alone).
  - **Stage 2 -- Done (2026-08-24).** Real CI confirmed Stage 1 green; user gave the go-ahead to
    proceed on the same branch (`double-suite-naming-stage1`), no new branch needed. The actual
    change: `cap_shared.py`'s `SUITE_FN_INFIX` set from `"_suite"` to `""` -- the single edit
    Stage 1's centralization was built to make possible. Verified functionally correct via real
    regeneration *before* touching any golden files (per an explicit ask this round: confirm the
    generator itself is right first, since golden-file updates can't distinguish "correctly
    updated" from "regenerated against a still-broken pipeline"): `examples/kessler` regenerated
    cleanly with e.g. `kessler_suite_register` (was `kessler_suite_suite_register`), and as a
    bonus the pre-existing `errmsg_fn_name` divergence Stage 1 flagged and deliberately left alone
    resolved itself for free -- the error-message text (which never had the infix) now matches
    the real function name exactly, since neither has it anymore.
  - **Real bug found and fixed by this verify-before-golden-updates discipline, not by Stage 1's
    own original audit.** A first regeneration attempt on `examples/kessler --bind-c` showed the
    generated C++ header/wrapper output collapse from 462 lines to 109 -- the whole ergonomics
    wrapper (`inline Status initialize() { ... }` etc.) silently disappeared. Root cause:
    `cpp_interop.py`'s `_suite_fns_for` (6 call sites, e.g. `f"{suite_name}_suite_{grp.attributes
    ['name']}"`) builds its own, independent, hardcoded `"_suite_"` infix to look up real suite
    cap function names in `public_fns` -- a **sixth** site Stage 1's own audit ("~15-20 sites
    across `suite_cap.py`/`ccpp_cap.py`/`gpu_data_pass.py`/`gpu_ccpp_cap_pass.py`") never found,
    since it never grepped for the substring `"_suite_"` embedded inside a longer f-string, only
    the standalone `"_suite"` token. Once `suite_cap.py`/`ccpp_cap.py` stopped emitting the infix
    (Stage 2's real change) but `cpp_interop.py` kept looking for names that included it, every
    lookup silently missed, and the wrapper generator quietly produced almost nothing instead of
    erroring -- exactly the "missed literal-string site" risk flagged when this stage was
    originally scoped, caught here specifically because verification happened before golden
    files were touched rather than after (a stale golden would have masked this by "passing"
    against equally-wrong regenerated content). Fixed by importing `SUITE_FN_INFIX` into
    `cpp_interop.py` and rebuilding all 6 sites as `f"{suite_name}{SUITE_FN_INFIX}_..."`, matching
    the other 4 files' own convention. Re-verified via the same `--bind-c` regeneration (462 lines
    restored, `inline Status initialize()` present, correct un-doubled names throughout) plus a
    second real suite (`examples/nested_suite`, a multi-group, non-`_suite`-suffixed suite name)
    regenerated cleanly with no errors.
  - **Full verification after the fix.** Confirmed a repo-wide grep for any other hardcoded
    `"_suite_" + <phase>` construction turns up nothing beyond comments/docstrings (the
    `cpp_interop.py` site was the only other real one). Regenerated the 25 real (non-`cpp_header`)
    filecheck fixtures affected via `tests/filecheck/examples/update-filecheck-test.py` -- the 5
    `cpp_header`/wrapper-format fixtures needed no golden changes at all, since their own CHECK
    content only ever referenced the fixed generic dispatch names (`ccpp_register` etc.), never
    the internal per-suite Fortran symbol names; regenerating them anyway would have silently
    baked in wrong content, since that script's formatter-selection only branches on `-t ftn` vs.
    everything else (defaulting to the MLIR-IR formatter, which mishandles blank lines in
    C++-header text) -- confirmed by inspection before deciding not to touch them. Hand-fixed the
    ~21 unit test files with hand-authored hardcoded `"..._suite_suite_..."`/`"..._suite_<phase>"`
    literal name strings (a mechanical, ordered literal-substring collapse: longest/most-specific
    phase keywords first, then a generic catch-all for the plain-run-phase, arbitrary-group-name
    case) plus one file (`test_ccpp_cap.py`) with a hand-built `public_fns` dict keyed by the old
    name directly (`"testsuite_suite_run"` -> `"testsuite_run"`) rather than parsed Fortran text.
    Final state: full suite `python -m pytest tests/filecheck tests/unit -q` -> 628 passed/1
    xfailed (identical to both the pre-Stage-1 and post-Stage-1 baselines); `ruff check .` -> 210
    (unchanged; one transient +1 from the new `cpp_interop.py` import was itself an import-order
    fix, not a real finding); a final real regeneration smoke test on `examples/kessler --bind-c`
    confirming clean, single-infix names end-to-end. Files modified (uncommitted, same branch):
    the 5 from Stage 1 plus `xdsl_ccpp/transforms/cpp_interop.py` (the real fix), 25 filecheck
    `.mlir` fixtures, and 21 `tests/unit/*.py` files with hardcoded name literals.

- **Order by risk, not just size.** Extract the most self-contained clusters first (chost/C++
  backend) and save the most interconnected, highest-blast-radius cluster (run-dispatch) for
  last.
- **No behavior changes bundled with structural moves**, except in Phase 3b, which is called
  out explicitly as the one deliberately behavioral step.
- **Full FileCheck + unit suite must stay green after every phase.** With one contributor,
  these golden-file tests are the practical substitute for code review — don't skip re-running
  them at each boundary.
- **Expect roughly flat total line count**, not a dramatic reduction. The one place a real
  (not just relocated) reduction is plausible: `suite_cap.py`'s `_ArgClassification`/
  `_classify_args` and the run-dispatch cluster's own argument-resolution logic solve the same
  kind of problem at adjacent pipeline layers without a shared abstraction — now tracked as its
  own step, Phase 4, sequenced after Phase 3b and before the slim-down/docs phase.

- **Task #72 — SuiteOwned dimension var from prior phase silently dropped from allocation —
  RESOLVED (2026-09-09).** Found during xdsl23 rrtmgp debug run: `Fortran runtime error:
  Array bound mismatch for dimension 2 of array 'pint_day' (1/60)` at
  `rrtmgp_inputs.F90:197`. Root cause: `_resolve_alloc_dim_var_refs` only searches
  `all_args` for the **current phase**. `nlayp` (`number_of_vertical_interfaces_in_RRTMGP`)
  is produced as `intent=out` in `rrtmgp_inputs_setup._init` and never re-declared in any
  `_run` arg table, so it is absent from `all_args` during run-phase allocation. All three
  fallback paths (`dims_compatible` with `pverp`, `_find_loop_upper_bound`, MODULE-table
  scan) also failed. The allocator silently returned `([], None)` and skipped
  `allocate(pint_day(nday, nlayp))` entirely. `nlayp` IS in `data_ops` as a SuiteOwned
  `HostVarRefOp` (placed there by `_build_framework_refs`), but was never consulted.
  Fix: added a final fallback in `_resolve_alloc_dim_var_refs` (after all three existing
  paths fail) that looks up `data_ops.get(("std_name", alloc_dim.lower()))`. If found, the
  SuiteOwned scalar from a prior phase is used as the allocation bound. 8-line addition,
  no behavior change for any variable whose dimension is already resolvable by the existing
  paths. Full suite 644 passed/1 xfailed (up from 628 — 16 new tests landed between
  #66 and this fix). No scheme source files changed.

---

## CAM-SIMA integration parity backlog (merged from capgen_v1_parity_backlog.md, 2026-09-29)

### Context

This backlog came out of an investigation into swapping xdsl_ccpp in for
capgen-v1 (`NCAR/ccpp-framework@feature/capgen-v1`) inside CAM-SIMA's build.
The original approach built a shim (`Claude0728/xdsl-ccpp/scripts/`) that
vendored a large slice of capgen-v1's own Python internals so CAM-SIMA's
unmodified `write_init_files.py` could keep working unchanged. That shim
served its purpose as a diagnostic harness -- it's what actually surfaced
the two items below -- but it is not a direction to continue: it makes
xdsl_ccpp depend on capgen-v1's own code to function, which is backwards
for a project whose point is to be an independent alternative.

This backlog is the corrected plan: give xdsl_ccpp the native capability it
currently lacks, and adapt CAM-SIMA's consumer to a small, backend-neutral
interface instead of either framework's native shape. The vendored shim
should not be carried forward once this work lands.

Two independent workstreams. They don't block each other and can proceed
in parallel; if sequencing matters, Workstream 2 (the DDT bug) is smaller,
more bounded, and blocks correctness of real generation (not just
introspection), so it's reasonable to land first.

---

### Workstream 1: Native introspection API + `ResolvedVar` adapter

##### Problem

CAM-SIMA's `src/data/write_init_files.py` (~1,570 lines, ~60% of it
CAM-SIMA-specific Fortran-generation logic, the rest introspection-API
consumption) needs, for every CCPP lifecycle phase, the resolved list of
variables required by that phase's active schemes -- each with its
standard name, intent, constituent/protected flags, host module binding,
and dimension category. capgen-v1 answers this via
`capgen(run_env, return_db=True)` returning a `CCPPDatabaseObj` with
`.host_model_dict()` and `.call_list(phase)`. xdsl_ccpp has no native
equivalent -- it computes nearly all of this same information internally
during generation (`HostVariableMatchPass`'s `model_var_name`/
`model_module_name`, `suite_cap.py`'s `_build_arg_tables`/
`_classify_args` per-phase resolution, the descriptor layer's
already-copied `standard_name`/`intent`/`dimensions`/etc.) but discards it
once generation finishes.

##### Structural note

The two `ResolvedVar` translation functions (Stage 4, Stage 5 below) live
in **CAM-SIMA's own repo**, not xdsl_ccpp's -- CAM-SIMA already depends on
real `ccpp-framework` via its own submodule, so it's the one piece of this
whole picture that's supposed to know about both frameworks. xdsl_ccpp's
repo only ever grows the native capability (Stages 1-3); it never touches
capgen-v1 code. That's what actually resolves the "xdsl_ccpp depending on
capgen-v1" problem, as opposed to the vendored shim.

##### Plan: staged, one stage at a time, pause for review between each

**Progress (updated 2026-08-13): Stages 0-3 done, awaiting review; Stages 4-7 done.** Stage 8 not started and
now explicitly **paused pending a direction decision** -- see the
"Re-validation (2026-08-13)" entry under Stage 8 below for why: CAM-SIMA's
real migration off legacy capgen turned out to go through capgen-v1's own
separate integration path, not this one. Update the status line per stage
as work lands (`not started` / `in progress` / `done, awaiting review` /
`done`).

**Stage 0 -- Lock the contract. [done, awaiting review]**

Exhaustively re-audited every `.get_prop_value(...)`/`.source.*`/
`.array_ref()`/`.call_string(...)`/`.get_dimensions()`/
`.has_vertical_dimension()`/`.has_horizontal_dimension()`/
`.intrinsic_elements()`/`.find_variable(...)` call site in
`write_init_files.py` directly (not from memory) -- this is richer than
the original 8-field sketch. Finalized contract:

```python
@dataclass
class ResolvedVar:
    standard_name: str
    local_name: str
    intent: str                          # 'in' | 'out' | 'inout'
    is_protected: bool
    is_advected: bool
    is_constituent: bool                 # advected/constituent are checked
                                          # separately in the real code
                                          # (`advected or constituent`), not
                                          # one merged flag -- keep distinct
    is_host_table_var: bool              # True iff source.ptype == 'host'
                                          # (passed via arg list, always
                                          # considered initialized)
    host_module: str | None              # source.name -- module to `use`
    dimensions: list[str]                # dimension standard names, from
                                          # get_dimensions()
    has_horizontal_dim: bool
    vertical_dim_name: str | None        # local name of vertical dim, else
                                          # None -- from has_vertical_dimension()
    array_ref_dims: list[str] | None     # dimension-index standard names
                                          # needing their OWN resolution --
                                          # from array_ref()
    intrinsic_element_names: list[str] | None  # sub-variable standard names
                                          # for DDT expansion -- from
                                          # intrinsic_elements()
    call_string_expr: str                # precomputed Fortran reference
                                          # expression, from
                                          # call_string(host_dict)
```

**Design point surfaced by this audit** (important for Stage 6, not just a
detail): `array_ref_dims` and `intrinsic_element_names` both mean "this
variable isn't fully resolved on its own -- go look up these *other*
standard names too," and the real code (`_find_and_add_host_variable`,
`_get_host_model_import`) already does this recursively via
`host_dict.find_variable(name)`. Rather than have each backend's adapter
try to eagerly pre-flatten this recursion (duplicating non-trivial logic
once per backend), each adapter should additionally provide a lookup
function:

```python
def resolve_by_standard_name(stdname: str) -> ResolvedVar | None: ...
```

and Stage 6's refactor of `_find_and_add_host_variable`/
`_get_host_model_import` should be a *minimal* edit -- swap
`host_dict.find_variable(x)` for `resolve_by_standard_name(x)`, keep the
existing recursive structure intact. Lower risk than restructuring the
recursion itself, and there's only one copy of it (in `write_init_files.py`),
not one per backend.

**Oracle -- doesn't need to be captured, it already exists.**
CAM-SIMA's own test suite already checks in curated, capgen-v1-produced
golden files (`sample_files/write_init_files/phys_vars_init_check_*.F90`
/ `physics_inputs_*.F90`) that `test_write_init_files.py` diffs against --
better than anything captured fresh this session, since these are already
the trusted reference. Confirmed the full test-method -> fixture-file
mapping (29 test methods total); chosen representative subset for Stage
6/7 validation, covering the three main complexity dimensions:

| Test | Fixture files | Covers |
|---|---|---|
| `test_simple_reg_write_init` | `*_simple.F90` | Baseline case |
| `test_simple_reg_constituent_write_init` | `*_cnst.F90` | `advected`/`constituent` flags |
| `test_ddt2_reg_write_init` | `*_ddt2.F90` | DDT expansion (`intrinsic_elements()`) |

Exit criteria met: dataclass defined, lookup-function design point
identified, oracle located (not captured, already exists) and
representative subset chosen.

**Stage 1 -- Prove xdsl_ccpp can expose the data at all. [done, awaiting review]**

Added a module-level `DEBUG_RESOLVED_VARS` dict in `suite_cap.py`, stashed
right after `_classify_args` computes `framework_vars`/`input_arg_list`/
`output_arg_list`, keyed by `(tgt_subroutine_postfix,
generated_subroutine_posfix, physics_mode)`. Ran the real pipeline
in-process (frontend + full pass pipeline) against `examples/helloworld`
and inspected the `_run`-phase entry.

**Result: 8 of 12 variables match capgen-v1's real `call_list(run)`
exactly** (`horizontal_dimension`, `vertical_layer_dimension`,
`vertical_interface_dimension`, `time_step_for_physics`,
`potential_temperature_at_interface`, `potential_temperature`,
`ccpp_error_message`, `ccpp_error_code`). The 4 that don't are explained,
not bugs:

- `suite_name`/`suite_part` -- capgen-v1's `API.__init__` synthesizes
  these itself and adds them directly to every phase's call list
  (framework bookkeeping for the dispatch subroutine's own signature,
  never sourced from scheme/host `.meta`). The stash point sits right
  after metadata-derived resolution; these are added on a separate path
  (building the actual Fortran signature) not yet hooked.
- `horizontal_loop_begin`/`horizontal_loop_end` -- capgen-v1's older
  begin/end-pair convention for the horizontal loop bound vs. xdsl_ccpp's
  newer single-extent `horizontal_dimension` convention (already present
  in the list, just represented differently) -- the same vocabulary
  migration already merged upstream, not a new discrepancy.

Exit criteria met: the concept is proven -- xdsl_ccpp's internal
resolution produces the same semantic variable set as capgen-v1 for
metadata-derived variables. Stage 2 needs to explicitly account for (a)
where the framework-bookkeeping vars (`suite_name`/`suite_part`) get
added, and (b) normalizing the horizontal-loop-bound representational
difference into `ResolvedVar`'s dimension fields.

**Stage 2 -- Extend to full coverage. [done, awaiting review]**

No new source changes needed -- Stage 1's raw-object stash already
exposes everything, since `HostVariableMatchPass` and the descriptor
layer already populate `model_var_name`/`model_module_name`/`dim_names`
on the same objects. This stage was pure validation: captured the real
MLIR for `test_simple_reg_constituent_write_init` (the constituent
fixture from Stage 0's representative set) and inspected all six phases
with host-binding and dimension classification extracted (using
xdsl_ccpp's own existing `is_horizontal_dimension`/`is_vertical_dimension`
helpers from `ccpp_conventions.py` -- no new classification logic needed
either).

**Confirmed working:**
- All six phases populate (three are legitimately empty for this suite --
  no register/timestep-phase scheme entry points declared, not a bug).
- Host-variable binding is correct for real host-matched variables, e.g.
  `potential_temperature` -> `model_var='theta'`,
  `module='physics_types_simple'`; `vertical_layer_dimension` ->
  `model_var='pver'`, `module='simple_sub'`.
- Dimension classification correctly derived: `potential_temperature` ->
  horizontal+vertical, `air_pressure_at_sea_level` -> horizontal, etc.

**Two design nuances surfaced, both need handling in Stage 4's adapter:**
1. **Constituent variables have no host-variable binding at all**
   (`model_var_name`/`model_module_name` both `None` for the one
   `advected=True` var in this fixture). This isn't a bug -- constituents
   are handled through CCPP's constituent object/array, never a direct
   host `use`-association -- and it matches `write_init_files.py`'s own
   existing logic, which already explicitly skips constituents when
   building host-module imports. Confirms the `is_advected`/`is_constituent`
   fields in `ResolvedVar` are load-bearing, not redundant with
   `host_module`.
2. **Some resolved args have no `standard_name` at all** -- two
   synthetic `col_start`/`col_end`-style scalars showed up in the `_run`
   phase (introduced by `_classify_args`'s physics-mode loop-extent
   synthesis), purely Fortran-level loop bounds with no CCPP metadata
   identity. Stage 4's adapter needs to filter these out before producing
   `ResolvedVar`s -- `write_init_files.py`'s consuming logic keys
   everything off `standard_name` and has no notion of a nameless var.

Exit criteria met: full phase/binding/dimension coverage confirmed against
a constituent-using fixture, zero new source risk introduced (validation
only, `git diff --stat` empty against tracked files throughout).

**Stage 3 -- Design the real exposure mechanism. [done, awaiting review]**

**Decision made, and it's *not* what the stage description guessed:**
extending `--emit-datatable` turned out to be the wrong fit, not just a
less-natural one. Traced `_run_datatable`'s actual call site in `run()`:
it re-parses the *original pre-pass* frontend MLIR (`mlir_file`, from
`run_frontend`) in a step that runs *after* `run_opt`'s entire pass
pipeline has already completed and exited its own subprocess. The
resolved-variable data (host bindings, ownership classification,
per-phase aggregation) only exists as transient Python state *during*
`generate-suite-cap`'s execution, inside `run_opt`'s subprocess -- by the
time `--emit-datatable`'s mechanism runs, that process is long gone and
the data was never persisted anywhere `_run_datatable` could re-derive it
from. Piggybacking on it would have meant either reimplementing
`_build_arg_tables`'s aggregation a second time (exactly the
"independent, byte-identical implementation" antipattern
`_collect_ddt_use_stubs`'s own docstring already warns against elsewhere
in this codebase) or restructuring `--emit-datatable` itself.

**What got built instead**: a new pass parameter, following the exact
precedent `host_name`/`kind_map` already established (real pass
parameters threaded through `_build_pipeline()`'s spec string, not a
separate post-hoc step):

- New CLI flag `--emit-resolved-vars FILE` (`ccpp_dsl.py`).
- Threaded into the pipeline spec as
  `generate-suite-cap{emit_resolved_vars="FILE"}` (quoted -- the
  pass-pipeline spec lexer doesn't accept unquoted `/` in an arg value,
  which paths always have; discovered by hitting the parse error directly).
- `SuiteCAP` gains an `emit_resolved_vars: str | None = None` field.
- `GenerateSuiteSubroutine` gains a real instance-level
  `self.resolved_vars: dict` accumulator (replacing Stage 1/2's module-level
  debug global entirely -- superseded, not kept alongside), populated by
  `generateSubroutineCall` exactly where the Stage 1 stash was, keyed by
  the friendly CCPP phase name (`register`/`initialize`/`finalize`/
  `timestep_initial`/`timestep_final`/`run`) rather than the raw postfix
  tuple.
- `SuiteCAP.apply()` serializes `generator.resolved_vars` to JSON (deduped
  by `standard_name` per phase -- capgen-v1's own `call_list(phase)` is
  likewise one combined list per phase across all groups/suites, not
  per-group) after the rewrite completes, only if `emit_resolved_vars` was
  set.
- Records use the Stage 0 `ResolvedVar` field names directly
  (`standard_name`, `intent`, `is_advected`, `is_constituent`,
  `is_protected`, `is_optional`, `model_var_name`, `model_module_name`,
  `dim_names`, `ownership_kind`), filtering out nameless synthetic args
  (Stage 2's `col_start`/`col_end` finding) at the source.

**Verified against both fixtures via the real CLI** (`ccpp_opt` with
`--emit-resolved-vars`, not just in-process tracing):
- `examples/helloworld`: clean JSON, all 6 phases, correct host bindings
  (e.g. `potential_temperature` -> `model_var='temp_midpoints'`,
  `module='hello_world_mod'`).
- CAM-SIMA's constituent fixture: 7 run-phase vars (correctly excludes
  the 2 nameless synthetic scalars), constituent var
  (`super_cool_cat_const`) correctly has `model_var_name`/
  `model_module_name` both `null`, matching Stage 2's finding.
- Full CAM-SIMA regression suite: unchanged at 3/16 collections failing
  (same pre-existing, unrelated missing-CIME-external issue) --
  `test_write_init_files.py` still fully passing.

Exit criteria met: stable, documented, tested artifact format,
independent of any host-model concern, ready for its own PR.

**Post-PR Copilot review (PR #51) caught a real bug my own testing missed:**
`_build_pipeline()`'s `emit_resolved_vars="{path}"` embeds literal double
quotes into the pipeline spec string, which itself later gets embedded
inside its *own* double-quoted shell argument (`-p "{pipeline}"`) in
`run_opt()`/`generate_cpp_headers()`, both of which shell out via
`os.system()`. My Stage 3 testing called `ccpp_opt` directly with a
properly shell-quoted argv, which never exercised the actual
`os.system()`-based path real usage goes through -- so the collision went
undetected. Reproduced it directly via `sh -c` with the exact command
`run_opt()` constructs (confirmed broken: `PassPipelineParseError`, no
output file), fixed by escaping the inner quotes (`\"` instead of `"`) so
they survive the outer shell-argument quoting, and reconfirmed producing
correct output through that same real code path. Also fixed a docstring
inaccuracy Copilot caught in the same review (the flag is defined on the
`ccpp_xdsl` CLI, not directly on `ccpp_opt`/`ccpp_xml`).

**Stage 4 -- Write the xdsl_ccpp-side adapter. [done]**

Implemented in CAM-SIMA's own repo (`reference/CAM-SIMA`, branch
`stage4-resolved-var-adapter`): `src/data/resolved_var.py` (the
`ResolvedVar` dataclass itself, shared by both backends' adapters) and
`src/data/resolved_var_xdsl_ccpp.py` (`XdslCcppResolvedVars`, loading
Stage 3's JSON and exposing `.call_list(phase)` /
`.resolve_by_standard_name(name)`, reusing xdsl_ccpp's own
`is_horizontal_dimension`/`is_vertical_dimension` directly rather than
re-implementing dimension classification).

**Validated against the real capgen-v1 oracle**, not just eyeballed:
instrumented the vendored shim to dump `cap_database.call_list(phase)`'s
real standard names for the constituent fixture, and diffed against the
adapter's output phase-by-phase. Two categories of discrepancy found:

1. **Confirmed harmless** -- `suite_name`, `suite_part`,
   `ccpp_error_message`, `ccpp_error_code` are missing from the adapter's
   output in various phases (matching Stage 1's finding that these are
   capgen-v1-synthesized framework bookkeeping, added on a code path
   Stage 3 doesn't hook). Checked directly against
   `write_init_files.py`'s own `_EXCLUDED_STDNAMES` set: all four are
   members. `write_init_files.py` ignores them regardless of whether
   they're present, so this costs nothing functionally.

2. **A real gap, found and fixed**: `horizontal_dimension` was missing
   from the adapter's `run`-phase output for the constituent fixture --
   and critically, this name is *not* in `_EXCLUDED_STDNAMES`, unlike the
   framework vars above, so it actually mattered to `write_init_files.py`'s
   real logic. Root cause: `_classify_args`'s physics-mode handling
   replaces the loop-extent arg with synthetic, nameless `col_start`/
   `col_end` scalars for suites using per-column dispatch (Stage 2's
   finding), and `_resolved_var_record` (Stage 3) filters out anything
   with no `standard_name`, silently dropping the horizontal-dimension
   identity along with the genuinely-nameless scalars.

   **Fix** (`xdsl_ccpp/transforms/suite_cap.py`): `_classify_args` already
   computes `ncol_meta` -- the *original*, unmodified loop-extent
   `CCPPArgument`, still carrying its real `standard_name`, before the
   col_start/col_end substitution. `generateSubroutineCall` now includes
   `ncol_meta` alongside `framework_vars`/`input_arg_list`/`output_arg_list`
   when building the resolved-vars stash, so the loop-extent variable's
   identity survives even when it's no longer directly represented in the
   call's own arg list. Also added `_normalize_std_name`, mapping through
   the existing `CCPP_DEPRECATED_STD_NAMES` table (applied to both
   `standard_name` and each entry of `dim_names`), since the scheme
   metadata for this fixture declares the deprecated
   `horizontal_loop_extent` name but capgen-v1's own output normalizes to
   `horizontal_dimension` -- without this the adapter would've reported
   the right variable under the wrong (stale) name.

   **Verified against the real capgen-v1 oracle**: re-ran
   `--emit-resolved-vars` against both the constituent fixture and
   `examples/helloworld`; the constituent fixture's `run` phase now
   reports `horizontal_dimension`, matching the oracle exactly, and
   helloworld (which was already correct, no col_start/col_end synthesis
   triggered there) is unaffected. Full CAM-SIMA regression suite (16
   test collections, `run_python_unit_tests.sh`) and xdsl_ccpp's own
   pytest suite (539 passed) both still pass; the one xdsl_ccpp pytest
   failure (`test_ccpp_xdsl_generates_caps`) was confirmed pre-existing
   and unrelated (a stale `ccpp_xdsl` console-script install resolving
   against a different checkout -- the same PYTHONPATH/namespace-package
   issue noted earlier in this doc -- reproduced identically with the fix
   stashed out).

   **Two adjacent gaps surfaced by the oracle diff, not yet fixed** (out
   of scope for this fix -- neither was part of the original loss, both
   are pre-existing absences):
   - `horizontal_loop_begin`/`horizontal_loop_end`: capgen-v1's oracle
     output gives the loop-bound scalars their own standard-name identity
     in the `run` phase. xdsl_ccpp's synthetic `col_start`/`col_end`
     replacements are still nameless (by design -- `_resolved_var_record`
     correctly drops them), so these two never appear. Interestingly, the
     xdsl_ccpp pytest fixture (`ddt_suite.xml`'s `make_ddt` scheme) shows
     this *can* work when the host metadata declares `cols`/`cole` args
     with those standard names directly (`model_var_name=col_start`/
     `col_end`) rather than relying on synthesis -- suggesting the gap is
     specifically in the synthesized-scalar path, not a fundamental
     limitation.
   - `suite_name`/`suite_part`: framework-injected suite metadata vars,
     not modeled by Stage 3 at all (distinct from the `_EXCLUDED_STDNAMES`
     framework vars in point 1 above, which Stage 3 *does* see but
     `write_init_files.py` ignores regardless).

   Revisit both before Stage 6 if a fixture actually needs them --
   neither is in `_EXCLUDED_STDNAMES`, so both could matter to real
   `write_init_files.py` logic depending on which host variables a given
   suite's schemes reference.

Everything else (the fields validated in Stages 1-2 -- host-variable
binding, dimension classification for non-loop-extent dimensions,
constituent/protected/optional flags) matches correctly. `array_ref_dims`/
`intrinsic_element_names` remain unpopulated (see resolved_var.py's
docstring) -- tested against the `ddt2` fixture specifically and found it
doesn't actually exercise host-side DDT sub-element expansion in its
resolved-variable data at all (the complexity there is in host-side DDT
representation, which Stage 3's JSON doesn't capture), so this wasn't
resolved, just confirmed out of scope for the fixtures tested so far.

**Stage 5 -- Write the capgen-v1-side adapter. [done]**

Implemented in CAM-SIMA's own repo (`reference/CAM-SIMA`, still on branch
`stage4-resolved-var-adapter`): `src/data/resolved_var_capgen_v1.py`
(`Capgenv1ResolvedVars`, wrapping a real `CCPPDatabaseObj` and exposing the
same `.call_list(phase)` / `.resolve_by_standard_name(name)` shape as
`resolved_var_xdsl_ccpp.py`), reusing capgen-v1's own
`is_horizontal_dimension`/`is_vertical_dimension` (`var_props.py`) directly,
same pattern as the xdsl_ccpp-side adapter reusing xdsl_ccpp's.

Field mapping, from `Var`'s real API (confirmed by reading
`write_init_files.py`'s existing calls, not guessed): `get_prop_value(...)`
for standard_name/intent/protected/advected/constituent/optional/local_name;
the `host_interface_var` property (`source.ptype == 'host'`) for
`is_host_table_var`; `source.name` for `host_module` (populated
unconditionally, matching `_get_host_model_import`'s own behavior --
`is_host_table_var` is the separate flag that tells a consumer whether a
`use` statement is actually needed, not `host_module` being `None`);
`get_dimensions()` for `dimensions`, passed straight through *un-flattened*
(capgen-v1's own dims can be compound colon-forms like
`ccpp_constant_one:vertical_layer_dimension`, which
`is_horizontal_dimension`/`is_vertical_dimension` already parse directly --
confirmed via their own docstrings); `array_ref()` for `array_ref_dims`;
`intrinsic_elements()` for `intrinsic_element_names`.

**Validated against a real `CCPPDatabaseObj`** (not just eyeballed):
constructed one via `ccpp_capgen.capgen(run_env, return_db=True)` against
the real `reference/ccpp-framework` checkout (not the `ccpp_framework`
symlink, which points at the xdsl_ccpp sandbox), using the same
`simple_host.meta`/`suite_simple.xml`/`temp_adjust.meta`/`simple_reg.xml`
fixture set `test_write_init_files.py::test_simple_reg_write_init` already
uses. Confirmed: dimension classification correctly handles capgen-v1's
compound colon-forms; `host_module` populated for both host-table and
module-type vars; `resolve_by_standard_name` returns a different (correct)
view of the same standard name than `call_list` does, when host-table vs.
scheme-call perspectives genuinely differ (e.g. `horizontal_dimension`'s
`intent`/`is_host_table_var` differ between "as declared on the host" and
"as seen by the calling scheme" -- both correct, not a bug).

**One real bug found and fixed during validation**: `intrinsic_elements()`
returns a variable's own standard name as a bare *string* when it's already
an intrinsic leaf with nothing to expand (only genuine DDT sub-element
lists are meaningful) -- confirmed directly from `write_init_files.py`'s
own `_find_and_add_host_variable`, which explicitly gates on
`isinstance(ielem, list)`. The adapter's first draft passed this bare
string through unfiltered, which would have made every ordinary scalar
variable look like a DDT with one bogus "sub-element" (itself). Fixed by
adding the same `isinstance(..., list)` gate before assigning
`intrinsic_element_names`.

Like Stage 4, `array_ref_dims`/`intrinsic_element_names`'s list-producing
paths remain unexercised: the available fixtures (including `ddt2`, tried
again here) don't route a DDT or array-ref standard name through
`call_list`/`resolve_by_standard_name` in a way that actually triggers
either. Unlike Stage 4, the *code path* for both is real and implemented
(not stubbed to `None`/approximated) since capgen-v1's own `Var` object
supports them directly -- only real-fixture coverage is missing. Revisit
if Stage 6/7 needs a fixture that does.

**Stage 6 -- Refactor `write_init_files.py` to consume only `ResolvedVar`. [done]**

Touched `gather_ccpp_req_vars`, `_find_and_add_host_variable`,
`collect_host_var_imports`/`_get_host_model_import`, `get_dimension_info`,
and the top-level `write_init_files()` entry point -- all now take/thread a
backend-neutral `resolved_vars` adapter instead of a raw `CCPPDatabaseObj`/
`host_dict`. `write_init_files.py` no longer imports anything from
capgen-v1 (`ccpp_state_machine`, `var_props`) -- `CCPP_PHASES` and
`is_horizontal_dimension`/`is_vertical_dimension` now live in
`resolved_var.py` itself (ported verbatim from `var_props.py`; a shared
CCPP vocabulary convention, not backend logic, mirroring how xdsl_ccpp
keeps its own independent copy in `ccpp_conventions.py`).

The bulk of the actual Fortran-string-emission code (the `outfile.write(...)`
calls, control flow, use-statement formatting) is genuinely untouched, as
planned. But the "~970 lines stay untouched" framing undersold how many
distinct Var-API surfaces those functions actually call (`get_prop_value`,
`source.ptype`/`source.name`, `has_horizontal_dimension()`/
`has_vertical_dimension()`, `call_string()`, `get_dimensions()`,
`array_ref()`, `intrinsic_elements()`, plus a `VarDDT`-specific `.var`
property) -- every one of those needed a mechanical attribute-access rename
or, in a few cases (below), a real design decision. `get_dimension_info`
also got a genuine simplification: it no longer re-parses a raw vertical-
dimension string into 'lev'/'ilev' since `ResolvedVar.vertical_dim_name` is
already normalized by the adapter.

**Three real bugs found and fixed during validation** (all found by running
the refactor through the real capgen-v1 adapter against
`test_write_init_files.py`'s fixtures with `filecmp.cmp(..., shallow=False)`,
not by inspection):

1. **`ResolvedVar` was unhashable.** `write_init_files()` itself dedupes its
   required-variable lists via `OrderedDict.fromkeys(all_req_vars)`, which
   needs identity-hashable entries -- exactly what real capgen-v1's `Var`
   class provides (no `__eq__`/`__hash__` override). A plain `@dataclass`
   defaults to `eq=True`, which sets `__hash__` to `None` on a mutable
   class. Fixed with `@dataclass(eq=False)`, restoring identity-based
   equality/hashing to match `Var`.

2. **Adapter-side caching gap.** Even after fixing hashability,
   `Capgenv1ResolvedVars` still built a *new* `ResolvedVar` object on every
   `call_list`/`resolve_by_standard_name` call -- so the same inout
   variable, resolved once via `in_vars` and once via `out_vars`, produced
   two distinct objects that identity-based dedup could no longer tell
   apart, silently duplicating the variable in generated output (`phys_var_num`
   off by one, extra IC-name/array entries). Real capgen-v1 avoids this
   because `host_dict`/`call_list` return the *same* `Var` instance on
   repeat lookups. Fixed by caching `ResolvedVar` construction in
   `Capgenv1ResolvedVars`, keyed by the underlying `Var` object's identity.
   `resolved_var_xdsl_ccpp.py` already got this right in Stage 4 (its
   `_flat`/`_by_phase` dicts are built once and reused).

3. **A single `local_name` field can't represent capgen-v1's DDT
   sub-element naming.** For a DDT sub-element (e.g. `potential_temperature`,
   a field of a `phys_state` DDT), real capgen-v1's `VarDDT` genuinely
   distinguishes three different names, confirmed directly against the
   `ddt`/`ddt2`/`ddt_array` fixtures (previously believed "out of scope,
   not exercised" per Stage 4/5 -- turned out to be very much exercised
   once write_init_files.py's real call sites were touched):
   - `get_prop_value('local_name')` delegates to the *leaf* field, giving
     the bare name (`"theta"`) -- used as the IC-file variable-name
     fallback.
   - the root DDT variable's own name (`"phys_state"`, reached only via
     `VarDDT`'s `.var` property, which returns a base-class view of self
     bypassing the leaf-delegating override) -- used in `use module, only:`
     import statements.
   - `call_string(host_dict)` builds the full dotted chain
     (`"phys_state%theta"`) -- used at the actual Fortran call site, and
     also resolves array-ref index variables (e.g. `foo(bar)`) the same
     way.

   `ResolvedVar` gained two new fields, `import_name` and `call_expr`,
   alongside `local_name` (now specifically the bare/leaf name) to carry
   these independently. `resolved_var_capgen_v1.py` populates all three
   correctly; `resolved_var_xdsl_ccpp.py` defaults `import_name`/`call_expr`
   to `local_name` (Stage 3's JSON has no DDT-chain data, so this is
   correct for every fixture validated so far, same class of gap as
   `array_ref_dims`/`intrinsic_element_names` -- revisit together if Stage 7
   needs a DDT fixture).

**Also found and fixed**: a real, non-test production call site --
`cime_config/cam_autogen.py`'s `generate_init_routines()` calls
`write_init_files()` directly as part of CAM-SIMA's actual build (not just
`test_write_init_files.py`). Updated it to wrap `cap_database` with
`Capgenv1ResolvedVars` before calling `write_init_files()`. Hardcoded to the
capgen-v1 adapter for now, with a comment flagging that Stage 7 needs to
make this backend-selectable once xdsl_ccpp enters the picture here.

**Validation**: all 16 `test_write_init_files.py` fixtures pass with
byte-identical output (`filecmp.cmp(..., shallow=False)`) against real
capgen-v1, including the three DDT fixtures that surfaced bug #3 above.
Full CAM-SIMA regression suite (`run_python_unit_tests.sh`, 16 test
collections including `test_cam_autogen.py`'s `test_generate_init_routines`,
which exercises the real `cam_autogen.py` call site) passes. Test files
themselves needed mechanical updates too: `test_write_init_files.py`'s 15
call sites now build `resolved_vars = Capgenv1ResolvedVars(cap_database)`
and pass that instead of the raw `cap_database`. All of this was run with
the real `reference/ccpp-framework` checkout prepended to `PYTHONPATH`
(bypassing this sandbox's own `ccpp_framework` symlink override, which
points at the xdsl_ccpp checkout for the eventual Stage 7 test) --
confirms Stage 6 is validated against genuine capgen-v1, not the xdsl_ccpp
shim, matching the stage's own stated goal.

**Stage 7 -- Validate xdsl_ccpp end-to-end through the refactored file. [done
-- found the central capability gap this whole effort was looking for]**

**Setup**: ran the real `xdsl_ccpp.tools.ccpp_dsl` CLI (not the vendored
shim) with `--emit-resolved-vars` against CAM-SIMA's actual fixture
scheme/host `.meta` + suite XML files, loaded the JSON through
`resolved_var_xdsl_ccpp.py`, and called the Stage 6-refactored
`write_init_files()` with it -- the same fixtures `test_write_init_files.py`
already validates against real capgen-v1.

**Result on the real fixtures: all 16 fail**, but all for the *same*,
single, well-understood reason (not 16 independent problems):

**The confirmed capability gap**: every one of CAM-SIMA's existing scheme
`.meta` fixtures declares the legacy `horizontal_loop_extent` convention
(triggers `_classify_args`'s physics-mode `col_start`/`col_end` synthesis,
per the Stage 4 fix). Real capgen-v1 independently host-matches the
resulting `horizontal_dimension` identity against the host's own direct
declaration (`pcols` in `simple_host.meta`) via its `VarLoopSubst`/
`CCPP_LOOP_DIM_SUBSTS` substitution machinery -- confirmed directly:
capgen-v1's own `call_list('run')` includes a *separate*, properly
host-bound `horizontal_dimension` entry (`local_name='pcols'`), distinct
from the scheme's own loop-extent arg. **xdsl_ccpp's `HostVariableMatchPass`
has no equivalent** -- the loop-extent arg (`ncol_meta`, recovered by the
Stage 4 fix so its *identity* survives) never gets matched against any host
variable, so `model_var_name`/`model_module_name` stay `None` for it. Since
Stage 3's `--emit-resolved-vars` JSON only records args actually resolved
by a suite's own calls (not a full host-variable dictionary the way
capgen-v1's `host_model_dict()` is), there's no way for the CAM-SIMA-side
adapter to recover `pcols` from data that was never captured in the first
place -- this needs an actual xdsl_ccpp capability addition, not just an
adapter-side fix.

Confirmed this is specifically about the *loop-extent-synthesis* path, not
host-matching in general, by isolating the two mechanisms:
- Scheme declaring `horizontal_loop_extent` (physics-mode synthesis
  triggered): `horizontal_dimension` resolves with `model_var_name=null` --
  the gap.
- Scheme declaring `horizontal_dimension` directly (no synthesis): resolves
  correctly to `model_var_name="pcols"`, `model_module_name="simple_sub"`,
  `ownership_kind="host_matched"`.

**Confirmed the rest of the pipeline is genuinely correct, not just
"probably fine"**: built a minimal scheme declaring `horizontal_dimension`
directly (avoiding the gap) plus a registry-generated module variable
(`potential_temperature`/`theta`), ran it through the full real
`ccpp_dsl` -> `resolved_var_xdsl_ccpp.py` -> refactored `write_init_files()`
chain, and got `retmsg=''` with fully correct generated Fortran --
`use simple_sub, only: pcols` and `use physics_types_simple, only: theta`,
exactly matching capgen-v1's own use-statement/local-name shape for both a
host-type var and a registry-generated module-type var. This isolates the
loop-extent gap as the *specific, singular* blocker, not a sign of broader
plumbing problems in Stages 3/4/6.

**A real robustness gap found and fixed along the way** (in
`write_init_files.py`, backend-neutral, benefits both backends):
`_find_and_add_host_variable` treated any non-`None` `resolve_by_standard_name`
result as "found," even when `local_name` was itself `None` (no real host
binding) -- surfaced as a raw `TypeError: object of type 'NoneType' has no
len()` three functions deep in `write_ic_params`, instead of the normal,
clear "Error: Missing required host variables: ..." reporting this
function already has for genuinely-unresolvable names. Fixed by treating
`hvar.local_name is None` the same as "not found." Never triggers on
capgen-v1 (its `Var` objects always have a `local_name` when
`find_variable()` returns non-`None`) -- confirmed via the full
capgen-v1 regression suite still passing unchanged after the fix.

**Two remediation paths for the core gap** (not attempted -- this is a real
xdsl_ccpp capability addition, not a Stage 7 "just validate" task, and
warrants a decision before committing to one):
1. Extend `HostVariableMatchPass` (or a new pass) to also match the
   loop-extent-derived dimension identity (`horizontal_dimension`, and
   ideally `horizontal_loop_begin`/`horizontal_loop_end`) against host
   declarations, independent of how the *scheme* itself expresses its own
   loop-bound argument. Would also naturally fix `ncol_meta`'s
   `model_var_name`/`model_module_name` gap, since Stage 3's existing
   per-call JSON would then just capture the match correctly -- no new
   artifact needed.
2. Add a broader "full host-variable table" introspection artifact
   (closer to capgen-v1's `host_model_dict()`) that `resolve_by_standard_name`
   could fall back to. More invasive; (1) seems more consistent with
   xdsl_ccpp's existing design and narrower in scope.

This is the concrete, load-bearing capability gap the whole Workstream 1
effort set out to find: xdsl_ccpp cannot currently drop in for any CAM-SIMA
suite using the (still-valid, still-supported) per-column
`horizontal_loop_extent` chunking convention, until one of the above is
implemented.

##### Post-Stage-7 follow-up: implemented Option 1, both parts

User's call: rather than migrate CAM-SIMA's fixtures off
`horizontal_loop_extent` (the lower-effort path), implement Option 1
natively in xdsl_ccpp, since the effort estimate came back small (the hard
part -- host-variable-by-standard-name indexing -- already existed and was
reusable) and closing the actual capability gap has more lasting value than
routing around it.

**Part 1 -- host-match the loop-extent-derived `horizontal_dimension`
identity.** Added `build_host_var_index(ccpp_mod)` to
`xdsl_ccpp/transforms/util/ir_utils.py` -- a small, side-effect-free sibling
of `HostVariableMatchPass._build_model_var_index` (deliberately *not*
reused directly: that method also emits a `CcppHandleOp` as a side effect,
which must only ever happen once, during the real `generate-host-match`
pass). `SuiteCAP.apply()` builds this index once per module and threads it
into `GenerateSuiteSubroutine`; `generateSubroutineCall`'s resolved-vars
stash now falls back to it for `ncol_meta` specifically (not
`framework_vars`/`input_arg_list`/`output_arg_list`, which can be
legitimately host-unmatched by design) when `ncol_meta`'s own
`model_var_name` is `None`. Confirmed via the "simple" fixture: `horizontal_dimension`
now resolves to `model_var_name="pcols"`, `model_module_name="simple_sub"`,
matching real capgen-v1 exactly.

**Part 2 -- `is_host_table_var` was hardcoded `False`.** Fixing Part 1
immediately exposed this second, previously-documented-but-inert gap (Stage
4's `resolved_var_xdsl_ccpp.py` comment) as now concretely blocking: host-
table vars (`pcols`/`pver`/`dtime_phys` in `simple_host.meta`) were
incorrectly included in `write_init_files.py`'s required-variable list
instead of being excluded (host-table vars are passed via the host's
argument list, never read from an IC file). Fixed the same way as Part 1 --
`HostVariableMatchPass._build_model_var_index`/`_match_and_validate` now
also records and annotates whether a match came from a HOST-type (not
MODULE-type) table (`model_var_is_host_table`, a new `ccpp.arg` IRDL
property in `xdsl_ccpp/dialects/ccpp.py` -- the underlying IR op is a
strict, statically-typed schema, so a new property key needs an actual
IRDL declaration, not just a dict write, confirmed the hard way via a
`VerifyException` the first time this was missed). Threaded through
`ccpp_descriptors.py`'s `BuildMetaDataDescriptions` (mirroring the existing
`model_var_is_ddt` copy pattern), `_resolved_var_record`'s JSON output, and
`resolved_var_xdsl_ccpp.py`'s `_to_resolved_var` (no longer hardcoded).

**Validation**: full xdsl_ccpp pytest suite (543 tests) confirmed clean
after each part -- the IRDL-property miss above was caught here (3 filecheck
regressions, `VerifyException: property 'model_var_is_host_table' is not
defined by the operation 'ccpp.arg'`), fixed, then reconfirmed at 542
passed / 1 pre-existing unrelated failure (the stale `ccpp_xdsl`
console-script issue, same as always) / 1 xfail -- unchanged from
pre-Stage-7 baseline.

**Full re-sweep across 13 of the 16 `test_write_init_files.py` fixtures**
(excluding `meta_file_reg` and `bad_vertical_dimension`, not adapted into
the sweep harness; DDT fixtures included) through the real xdsl_ccpp CLI ->
`resolved_var_xdsl_ccpp.py` -> refactored `write_init_files()`, diffed
against golden capgen-v1 output:

- **8/13 now byte-identical**: `simple`, `simple_reg_constituent`,
  `no_reqvar`, `host_input_var`, `no_horiz_var`, `scalar_var`, `4d_5d_var`,
  `simple_constituent_dim`. (Two of these initially showed spurious diffs
  from a bug in the *sweep harness itself* -- hardcoding empty
  `ic_names`/`constituents`/`vars_init_value` instead of each fixture's
  real `gen_registry()` return values; fixed and reconfirmed MATCH.)
- **2/13 (`protected`, `parameter`) revealed a new, small, same-pattern
  gap -- found and fixed**: `is_protected` wasn't propagated from a
  host/module declaration onto a matched scheme arg's resolved-var record
  either -- e.g. `g` (declared `protected = True` in the registry) showed
  `is_protected=False` through xdsl_ccpp, so `write_init_files.py`
  incorrectly tried to read it from an IC file instead of skipping it as
  already-initialized. Exact same shape as `is_host_table_var`: extended
  `_build_model_var_index`/`build_host_var_index`'s tuples with
  `is_protected` (`arg_op.protected is not None` on the HOST/MODULE
  declaration), annotated the matched scheme arg via a new
  `model_var_is_protected` IRDL property (`ccpp.py`; learned from the
  `model_var_is_host_table` miss to add the IRDL declaration up front this
  time -- confirmed clean on the first pytest run, no regressions), threaded
  through `ccpp_descriptors.py`, and OR'd into `_resolved_var_record`'s
  `is_protected` (a scheme arg's own `protected` property is never set
  directly; only `model_var_is_protected`, from the match, actually fires
  in practice). `ncol_meta`'s host-var-index fallback OR's in the 4th tuple
  element the same way. Reconfirmed via the full sweep: `protected` and
  `parameter` now MATCH too.
- **3/13 (`ddt`, `ddt2`, `ddt_array`) confirmed the already-known DDT-chain
  gap -- found and fixed.**

##### Post-Stage-7 follow-up: the DDT-chain gap

**Investigated first, not guessed at.** A research pass found that DDT
chain resolution *already exists* in xdsl_ccpp -- just not where the
`--emit-resolved-vars` introspection code was looking. It lives in
`xdsl_ccpp/transforms/util/cap_shared.py`, already shared between two real
cap-generation consumers (`run_dispatch.py`, `gpu_ccpp_cap_pass.py`):
`_build_ddt_resolution_maps(meta_data)` builds a DDT type name -> instance
variable map (and a nested-DDT parent map) by scanning MODULE/HOST tables
for a variable whose own `type` matches the DDT's name; `_resolve_ddt_access_path`
recursively walks nesting to build the `%`-chain; `_resolve_member_subscripts`
resolves array-section index tokens within a member reference. All three
are pure functions of the same metadata dict `suite_cap.py` already builds
-- reusing them for introspection wasn't "build new resolution logic," it
was "call the existing logic from a third place."

**The fix** (`suite_cap.py`): `SuiteCAP.apply()` now builds these same maps
(gated on `self.emit_resolved_vars`, same reasoning as the host-var-index
fix -- zero cost when nobody asked for resolved-vars output) and threads
them into `GenerateSuiteSubroutine` as `ddt_resolution_maps`. A new
`_apply_ddt_chain(record, arg, ddt_resolution_maps)` patches every
resolved-var record for an arg with `model_var_is_ddt` set: what
`_resolved_var_record` left in `model_module_name` is actually the DDT
*type* name, not a real module -- `_apply_ddt_chain` resolves it to the
real instance variable/module and rewrites `model_module_name`
(now correct for `use` statements), plus two new record fields,
`import_name` (the instance variable, e.g. `"phys_state"`) and `call_expr`
(the full chain, e.g. `"phys_state%theta"`).

**A second gap found along the way**: even with the chain resolved, the
`ddt_array` fixture's array-index variable (`index_of_potential_temperature`)
still failed with "Missing host indices" -- `resolve_by_standard_name`
had no way to find it, since (like the original `horizontal_dimension`/
`pcols` gap) it's a real host variable that's never itself a scheme
argument, so never appears in any phase's own call list.  Fixed by
serializing `cap_shared.py`'s `_build_host_var_map` (already computed for
DDT resolution) into the JSON as a new top-level `"host_vars"` key -- a
genuine standard_name -> (local_name, module_name) dictionary over *every*
HOST/MODULE variable, not just ones some suite call happened to resolve.
`resolved_var_xdsl_ccpp.py`'s `resolve_by_standard_name` now falls back to
it when the per-phase flat lookup misses.

**Validation**: full xdsl_ccpp pytest suite clean throughout (542/543,
same pre-existing unrelated failure). Full sweep re-run: `ddt` and `ddt2`
now byte-identical; `ddt_array` produces fully correct output with one
remaining single-character cosmetic difference -- the array member's local
name is declared `"T"` (uppercase) in the registry, and real capgen-v1
emits it lowercased (`phys_state%t(...)`) somewhere in its own Fortran-
emission pipeline that a quick search didn't pin down, while xdsl_ccpp
preserves the declared case (`phys_state%T(...)`). Functionally identical
Fortran (case-insensitive language); not chased further since it's cosmetic
only, not a correctness gap. **12/13 fixtures now byte-identical, the 13th
(`ddt_array`) functionally correct with one cosmetic byte-diff** -- up from
0 before Stage 7's fixes.

**On the `T`/`t` diff specifically: this is capgen-v1's behavior diverging
from the registry's own declared name, not an xdsl_ccpp gap.** xdsl_ccpp
preserves the local name exactly as declared (`"T"` in, `"T"` out) --
arguably the more predictable, defensible behavior of the two. Real
capgen-v1 changes the case somewhere between parsing and Fortran emission;
searching `metavar.py`, `mkcap.py`, `ddt_library.py`, `metadata_table.py`,
and `suite_objects.py` didn't turn up the exact responsible line, so it's
unclear whether this is (a) a deliberate style normalization to lowercase
in capgen-v1's Fortran-emission layer, or (b) an accidental side effect of
one of the several `.lower()` calls used elsewhere in that codebase for
case-insensitive dictionary lookups/matching, whose lowercased copy then
gets reused for printing instead of the original declared case. Either
way, there is nothing here for xdsl_ccpp to "fix" to achieve parity in any
meaningful sense -- both outputs are the identical Fortran reference to a
case-insensitive language; this is recorded for transparency, not as an
open action item.

**Stage 8 -- Real integration / upstream PRs.** [not started]
Stage 3's work as a PR to xdsl_ccpp (same workflow as the DDT fix);
Stages 4-7 as a PR to CAM-SIMA (`johnmauff/CAM-SIMA` fork ->
`ESCOMP/CAM-SIMA`).

Stages 1-3 can proceed independently of anything CAM-SIMA-side; 4-7 depend
on Stage 3 landing (or at least stabilizing) first.

##### Re-validation (2026-08-13): --legacy-mode impact, a stale adapter, and a
##### bigger strategic finding -- PAUSED here by request, awaiting direction

**Trigger**: the `--legacy-mode` work (`CHANGELOG.md`) flipped
`ArgumentOp`'s default from warn-on-deprecated-name to reject-by-default.
Every fixture this whole Workstream validates against declares
`horizontal_loop_extent`, so this needed re-confirming before treating
Stage 7's findings as still current.

**Confirmed intact.** Pulled `johnmauff/CAM-SIMA@xdsl-ccpp-adapter` fresh
(this is PR #2 on that repo, open, base `development` -- see below) and ran
a real fixture (`temp_adjust.meta` + `simple_host.meta`) through the current
xdsl_ccpp pipeline end-to-end, through the actual committed
`resolved_var_xdsl_ccpp.py`. Fails without `--legacy-mode` (by design); with
it, reproduces exactly the Post-Stage-7 resolution: `horizontal_dimension`
-> `local_name='pcols'`, `host_module='simple_sub'`, `is_host_table_var=True`,
`is_protected=True`. `--legacy-mode` is a strict superset of the old
warn-only behavior for this path -- nothing regressed.

**Found: the committed CAM-SIMA-side adapter is stale.** `johnmauff/CAM-SIMA`
PR #2's own description says "10/13 produce byte-identical output... the
remaining 3 (DDT-member variables) have a known, documented gap" -- that's
the pre-Post-Stage-7 state (Stage 4-6 level), not the 12/13-plus-one-cosmetic
state this doc claims above. Confirmed directly: xdsl_ccpp's
`--emit-resolved-vars` JSON still emits a correct top-level `"host_vars"` key
today, but `resolved_var_xdsl_ccpp.py` on that branch never reads it, and
still aliases `import_name`/`call_expr` to `model_var_name` instead of the
dedicated fields the DDT-chain fix added. DDT/array-ref fixtures (`ddt`,
`ddt2`, `ddt_array`) would very likely still show the old 10/13-level gap on
that branch -- the "Post-Stage-7 follow-up: the DDT-chain gap" section
above's byte-identical claim was validated against a local/scratch copy of
the adapter that was never pushed to CAM-SIMA.

**A bigger finding: real capgen-v1 has already built its own, separate,
apparently production-track integration path for CAM-SIMA**, independent of
anything in this Workstream. capgen-v1's own repo docs
(`doc/capgen_compat_layer.md`, `doc/migration.md` §4.5, both current as of
the 2026-08-10 `feature/capgen-v1` tip) describe `cime_config/capgen_compat/`
-- a facade living in the CAM-SIMA tree that lets CAM-SIMA's *unmodified*
`write_init_files.py`/`cam_autogen.py`/`generate_registry_data.py` keep
calling the old ccpp-capgen Python API (`cap_database.host_model_dict()`,
`.call_list(phase)`, `Var.get_prop_value(...)`, ...) while capgen-v1
generates underneath. Per that doc's own "Status" section: three real suites
(`kessler`, `rrtmgp`, and the full `cam7` suite via `se_cslam`) already
**build and run to completion on Derecho, bit-comparable, under both gnu and
intel**. This has nothing to do with xdsl_ccpp's `ResolvedVar` bridge, and is
a working migration path already in place.

That same doc states capgen-v1's own long-term "Convergence goal" explicitly:
CAM-SIMA talking to capgen-v1 through **three CLI utilities plus the
on-disk `datatable.xml` contract**, not a Python object model -- notably
closer to xdsl_ccpp's already-existing `--emit-datatable`/`ccpp_datatable.py`
than to this Workstream's `ResolvedVar` approach.

**Also confirmed via GitHub**: `johnmauff/CAM-SIMA`'s `xdsl-ccpp-adapter`
branch has an open PR (#2, -> `development`), whose own description frames
it as exploratory -- "Not wired into `cam_autogen.py`... kept on its own
branch while xdsl_ccpp itself is still under evaluation" -- consistent with
everything above; it was never intended as the production integration path.

**Implication, not yet acted on.** This doesn't make Workstream 1 wrong or
wasted -- it proved xdsl_ccpp *can* expose this information natively, a real
capability it previously lacked, and that capability is confirmed intact
today. But CAM-SIMA's actual migration off legacy capgen went through
capgen-v1 directly, not through this bridge, and capgen-v1's own stated
target interface (CLI + `datatable.xml`) is a different shape than what this
Workstream built. **Paused here by explicit request (2026-08-13)**, pending
a decision on whether to: (a) finish Stage 8 as originally scoped (sync the
stale CAM-SIMA-side adapter, land the xdsl_ccpp-side Stage 3 work as a real
PR) purely as a capability proof; (b) leave Workstream 1 as-is and instead
investigate whether `--emit-datatable` already satisfies (or could be
extended to satisfy) capgen-v1's own stated convergence interface; or (c)
deprioritize this entirely now that CAM-SIMA's real path is confirmed not to
depend on it.

##### Decision (2026-08-24): resume as Stage 8+, scoped against the real `cam_autogen.py` call sites, not just as a capability proof

**Decision: pursue (a) and (b) together, not as alternatives.** Finishing
Stage 8 (syncing the stale CAM-SIMA-side adapter) is small and already
proven; it's also a real prerequisite for (b), not a separate track --
`cam_autogen.py` needs *both* pieces (resolved-var data and the
`datatable_report()` query path) working before xdsl_ccpp can generate a
single real suite cap for CAM-SIMA. This session traced `cam_autogen.py`
itself (not just this doc's own prior notes) to pin down exactly what those
two pieces need to do, plus a third piece neither (a) nor (b) covered:
cap-generation invocation and backend selection, which don't exist at all
today.

**What `cam_autogen.py` actually calls, confirmed by direct read
(`johnmauff/CAM-SIMA@xdsl-ccpp-adapter`):**
- `generate_physics_suites()` (`cam_autogen.py:657`) unconditionally calls
  real capgen-v1's Python API: `capgen_db = capgen(run_env,
  return_db=True)` (imported `from ccpp_capgen import capgen` at line 48).
  No xdsl_ccpp branch exists.
- The same function then queries the generated `ccpp_datatable.xml`
  (`cap_output_file`) exactly twice, both via real capgen-v1's own
  `ccpp_datafile.py` (imported directly from the vendored
  `ccpp_framework/capgen/` checkout, *not* through
  `cime_config/capgen_compat/`'s shim layer -- confirming it's treated as
  the stable, non-shimmed interface): `DatatableReport("utility_files")`
  (`cam_autogen.py:731`) and `DatatableReport("dependencies")`
  (`cam_autogen.py:735`). These are the *only* two `datatable_report()`
  queries this file makes -- not the full `required_variables`/
  `input_variables`/`suite_variables`/etc. surface `ccpp_datafile.py`
  exposes, so the real scope here is narrower than "full datatable schema
  parity."
- `generate_init_routines()` (`cam_autogen.py:801`) hardcodes
  `resolved_vars = Capgenv1ResolvedVars(cap_database)`, with its own
  comment: "Only one such adapter exists today... this call would need to
  become backend-selectable if a second CCPP-framework implementation is
  ever adopted alongside it." Confirms no backend-selection mechanism
  exists anywhere in this file.
- `generate_registry()`/`generate_registry_data.py` (imports
  `parse_metadata_file` from `metadata_table` at
  `generate_registry_data.py:37`) is a **separate, orthogonal step** --
  it parses the CAM registry's own `.meta` files to emit host-model data
  structures, independent of which backend generates *suite* caps. It
  already depends on real capgen-v1's metadata parser today and keeps
  doing so regardless of this workstream; not part of this scope.

**Real capgen-v1's own `ccpp_datatable.xml` schema** (confirmed directly
from `ccpp_datafile.py`'s own doctests in the vendored
`ccpp-framework-fresh/capgen/ccpp_datafile.py`, not guessed): root
`<ccpp_datatable version="1.0">`; a `<capgen_files>` section containing
typed sub-elements (`<host_files>`, `<suite_files>`, `<scheme_files>`,
`<utility_files>`), each holding `<file>` entries as **element text**;
a separate `<dependencies>` section holding `<dependency>` entries the
same way. xdsl_ccpp's own `--emit-datatable` output uses a different, ad
hoc schema (file paths as **attributes**, no `dependencies`/
`utility_files` sections at all -- this is exactly why `ccpp_cap_refactor_
plan.md`'s task #32/"Tier 2 of #6" was logged as not-yet-attempted).

**Schema decision (2026-08-24, user confirmed): match real capgen-v1's
schema exactly**, not a parallel xdsl_ccpp-specific reader. This lets
`cam_autogen.py`'s existing `from ccpp_datafile import DatatableReport,
datatable_report` calls read xdsl_ccpp's datatable.xml with **zero
`cam_autogen.py` code changes** -- the same reader module, already
vendored, just pointed at a different generator's output. Matches
capgen-v1's own declared convergence goal (`doc/capgen_compat_layer.md`:
"CAM-SIMA interacts with capgen through... `datatable.xml`" as "the
non-negotiable cross-language contract") instead of entrenching a second,
competing schema.

**Staged plan:**
- **Stage 8a -- Done (2026-08-24).** Pushed to
  `johnmauff/CAM-SIMA@xdsl-ccpp-adapter`; PR #2's CI (including the
  `pylint` gate this fix specifically targeted) is green.
  `resolved_var_xdsl_ccpp.py` now reads
  `import_name`/`call_expr` straight off each JSON record (suite_cap.py's
  `_resolved_var_record` already sets both to `model_var_name` for every
  record, and `_apply_ddt_chain` overwrites them in place for a DDT
  member -- reading them directly, rather than re-deriving from
  `model_var_name` in this adapter, is what makes DDT resolution flow
  through at all) and `array_ref_dims` off the record too (was hardcoded
  `None`); `resolve_by_standard_name` now falls back to a new
  `self._host_vars` dict (the JSON's top-level `"host_vars"` key) for a
  name that never appears in any phase's own call list, degrading cleanly
  (no `host_vars` lookup, no error) when that key is absent from an older
  JSON. Also fixed two real `pylint` findings CI caught on this file
  independently (`W1514` unspecified-`open()`-encoding,
  `C0116` missing docstring on `resolve_by_standard_name`) -- both real,
  not config noise (the `test/.pylintrc` `E0015` in the same CI output is
  a pre-existing, unrelated pylintrc-vs-installed-pylint-version mismatch,
  not something this file's own diff caused or should fix). Local
  `pylint --rcfile=test/.pylintrc`: 10.00/10 (was 9.17/10, CI's own
  reported score, below the 9.5 gate).
  - **Verified directly against real xdsl_ccpp CLI output, not by
    inspection.** Built a minimal DDT fixture (mirroring
    `tests/unit/test_ddt_chain_resolved_vars.py`'s own
    `TestDdtChainModuleTableInstance` scenario: a `phys_state_t` DDT
    instance in a MODULE table, a scheme reading/writing one of its
    members) and ran it through the real `ccpp_dsl.py` CLI end-to-end.
    Confirmed the emitted JSON already carries the correct chain
    (`import_name="phys_state"`, `call_expr="phys_state%counter"`), then
    fed that same JSON through the fixed adapter and confirmed the
    resulting `ResolvedVar` carries them through unchanged (would have
    read `import_name="counter"`, `call_expr="counter"` before this fix --
    exactly the bug this stage closes). Separately built a second fixture
    with a host variable declared but never referenced by any scheme arg
    (mirroring the `ddt_array` fixture's `index_of_potential_temperature`
    class of gap) and confirmed `resolve_by_standard_name` finds it via
    the `host_vars` fallback, that a genuinely unknown standard name still
    correctly returns `None` (not a spurious match), and that the ordinary
    per-phase lookup still takes priority when a name is in both places.
    Also confirmed the adapter degrades cleanly (no crash, same behavior
    as before this fix) against a JSON with the `"host_vars"` key
    stripped out, simulating an older xdsl_ccpp build.
  - **Deliberately deferred, still not done: the full 13-fixture
    `write_init_files.py` byte-identical re-verification** the original
    Stage 8a plan called for. Attempted directly against
    `CAM-SIMA-fresh`'s own `test/unit/python/test_write_init_files.py`
    fixtures, but that harness needs real capgen-v1's own
    `framework_env.py`/`ccpp_capgen.py` (via CAM-SIMA's `ccpp_framework`
    git submodule, currently unpopulated in this checkout, and pointed at
    the wrong fork in `.gitmodules` besides -- the user confirmed the real
    one for this integration is `johnmauff/ccpp-framework`, not
    `NCAR/ccpp-framework`) to run `gen_registry`/`capgen()` at all -- an
    environment-setup gap unrelated to this fix. Deferred by explicit
    request (2026-08-24), not attempted further. The narrower, real-CLI
    verification above confirms the fix itself is correct; the full
    fixture sweep should still happen once that submodule is populated
    from the right fork.
  - **Update (2026-09-29): superseded, not a live blocker.** Extensive real
    CIME regression testing since this was written (the `/cam-sima-regression`
    xdsl4x suite runs, spanning several weeks, plus the Kessler CPU/GPU
    parity work) has exercised `write_init_files.py` against real
    xdsl_ccpp-generated resolved vars across many real cases. This narrower
    byte-identical unit-fixture sweep is no longer treated as an open item
    -- the live regression evidence is more thorough than what it would
    have added.
- **Stage 8b -- Done (2026-08-24), `dependencies` implemented and directly
  verified against real capgen-v1's own reader; `utility_files` left
  empty-but-schema-valid by deliberate scope decision (user-confirmed),
  not populated with real content.**
  - **What real capgen-v1 actually does, read directly from
    `ccpp-framework-fresh/capgen/generator/datatable.py` (the real
    *writer*, not just `ccpp_datafile.py`'s reader this doc originally
    scoped against) -- corrects this entry's own earlier guess.**
    `<capgen_files><utilities>` is **not** derived from `.meta`-declared
    data at all -- confirmed via `ccpp_capgen.py:1065-1069`, it's a fixed
    list the driver assembles itself: `ccpp_kinds.F90`, a generated
    `ccpp_host_constituents.F90`, plus framework-bundled support files
    (`_resolve_framework_f90_files()`, e.g. `ccpp_constituent_prop_mod.F90`/
    `ccpp_scheme_utils.F90`-equivalents, resolved from the vendored
    `ccpp_framework/` checkout itself). `<dependencies>`, by contrast, is
    exactly what this doc originally expected: sourced from each
    `MetadataTable.dependencies` (`ccpp_capgen.py:1121-1130`), with a real
    filter -- host/DDT-adjacent tables' dependencies always contribute;
    a scheme table's own dependencies only contribute if that scheme is
    actually referenced by some resolved suite's group membership (an
    unreferenced scheme passed on the CLI for build-system convenience
    shouldn't leak its dependencies into the datatable).
  - **The real, separate gap this surfaced**: xdsl_ccpp's own equivalents
    of capgen-v1's bundled framework support files
    (`ccpp_constituent_prop_mod.F90`/`ccpp_scheme_utils.F90`) currently
    live only in `examples/shared/` -- fine for this repo's own example
    harness, but not resolvable from an installed `xdsl_ccpp` package or a
    real host model like CAM-SIMA. Deciding where these should actually
    live (vendored into the installed package, analogous to real
    capgen-v1's own `_resolve_framework_f90_files()`) is a real design
    question, not a filename-pattern-heuristic guess -- **deliberately not
    solved here** (user-confirmed 2026-08-24: implement `dependencies` now,
    scope `utility_files` content as its own follow-up).
  - **Implementation** (`xdsl_ccpp/tools/ccpp_datatable.py`): `<dependencies>`
    added as a new top-level sibling of the existing `ccpp_files`/`schemes`/
    `api`/`var_dictionaries` sections (confirmed real capgen-v1's own
    `ccpp_datafile.py` never validates the root element's own tag name, only
    looks up direct children by tag -- so this file's own `<datatable>` root,
    unlike real capgen-v1's `<ccpp_datatable>`, needed no change for this to
    work), populated via a new `_collect_dependencies()` reading each
    `TablePropertiesOp`'s `dependencies`/`dependencies_path` attributes
    (task #6 Tier 1's already-IR-forwarded data) and a new
    `_used_scheme_names()` replicating real capgen-v1's own reference
    filter (reusing the same group-membership walk the existing `<api>`
    section already does). Also added a minimal,
    schema-valid (but content-empty) `<capgen_files><utilities>/<host_files>/
    <suite_files></capgen_files>` -- **required**, not optional, once
    real testing showed `DatatableReport("utility_files")` raises
    `CCPPDatatableError("Element type, 'capgen_files', not found in
    table")` with no `<capgen_files>` element present at all, which
    `cam_autogen.py:731` calls unconditionally; this makes that query
    return an empty list instead of crashing, without deciding what
    should populate it.
  - **Known limitation, documented in code, not solved here**: each
    dependency path is joined with its own table's `dependencies_path`
    (when set) via a plain relative `os.path.join`, not resolved to an
    absolute path -- real capgen-v1's own convention resolves
    `dependencies_path` relative to the *original .meta file's own
    directory*, but `build_datatable()` only receives parsed MLIR text and
    a cap-files list (`ccpp_dsl.py:697`), not the original
    `--scheme-files`/`--host-files` search paths needed to do that
    resolution. A caller needing an absolute path must resolve this
    relative path against its own known scheme/host search directory.
  - **Verified directly against real capgen-v1's own unmodified
    `ccpp_datafile.py`, not by inspection of the written XML alone.**
    Generated a real datatable.xml via `examples/capgen` (both suites, six
    scheme files) and ran `ccpp_datafile.py <path> --dependencies
    --separator ";"` from the real `ccpp-framework-fresh/capgen/` checkout
    directly against it: returned `temp_kinds.F90` (deduped -- both
    `temp_set.meta` and `temp_adjust.meta` declare the identical
    dependency), exit 0. Ran `--utility-files` the same way: empty output,
    exit 0 (was a hard crash before the `<capgen_files>` stub was added).
    Separately built a minimal two-scheme fixture (one referenced by the
    loaded suite, one not, each with its own distinct `dependencies`
    entry) and confirmed the unreferenced scheme's dependency is correctly
    excluded -- proving the reference filter, not just the happy path.
    Full suite: 628 passed/1 xfailed (unchanged); `ruff` unchanged (the
    one finding in this file, an import-sort issue, confirmed pre-existing
    via git-stash comparison, not introduced by this change).
  - **Copilot review follow-up on PR #94 (2026-08-24), fixed -- a real
    correctness bug, not a style nit.** `_used_scheme_names()` reused
    `_iter_schemes_in_group()`, which only descended one `SubcycleOp`
    level; real suites nest deeper (confirmed against
    `examples/var_compat/var_compatibility_suite.xml:5-11`, three levels
    to reach `effr_calc`), and `_used_scheme_names()` also never checked
    `SuiteOp.init_scheme`/`final_scheme` (the v2.0 SDF suite-level
    lifecycle hook) at all. Either gap meant a real scheme's own
    `dependencies` could be silently excluded from the datatable --
    exactly the kind of missing-compile-dependency failure a host build
    would only discover as an opaque link error, not something caught
    here. Fixed: `_iter_schemes_in_group` now recurses into arbitrarily-
    nested `SubcycleOp` (a 3-line change -- `GroupOp`/`SubcycleOp` share
    the same body-region shape, so the function calls itself unchanged);
    `_used_scheme_names()` now also adds `init_scheme`/`final_scheme` when
    set, matching real capgen-v1's own `used_scheme_names` gate exactly
    (`ccpp_capgen.py`'s own `suite_init_call`/`suite_final_call` handling).
    Verified fail-before/pass-after, not just pass-after: two new
    regression tests (`TestDependenciesSection::
    test_deeply_nested_subcycle_scheme_included`, mirroring
    `var_compatibility_suite.xml`'s own 3-level nesting exactly, and
    `test_suite_init_scheme_dependency_included`) confirmed failing
    against the pre-fix code via `git stash` before confirming they pass
    against the fix. Also re-ran the real `var_compat` example end-to-end
    and confirmed `effr_calc` (the 3-levels-deep scheme) now correctly
    appears in the generated `<api>` section too -- a direct side-benefit
    of fixing the shared `_iter_schemes_in_group` walker, not something
    separately implemented. Full suite: 637 passed/1 xfailed (635 + 2
    new); `ruff` unchanged.

- **Task #75 (Stage 8b follow-up) -- Done (2026-08-24): vendor the
  `<capgen_files><utilities>` content for real, matching real capgen-v1's
  own pattern exactly.** Real capgen-v1's own answer (`ccpp_capgen.py:
  110-165`, read directly, not guessed): `_FRAMEWORK_SRC_DIR =
  os.path.join(_SCRIPT_DIR, 'src')` -- a `src/` directory shipped inside
  the capgen-v1 package itself, not supplied by the host model at all
  ("capgen ships self-contained -- no external src/ companion needed");
  `_FRAMEWORK_F90_FILES`, a fixed filename list
  (`ccpp_constituent_prop_mod.F90`, `ccpp_hashable.F90`,
  `ccpp_hash_table.F90`, `ccpp_scheme_utils.F90`);
  `_resolve_framework_f90_files()` joins the two, hard-erring (not silently
  skipping) if any file is missing, with a message telling the deployer
  exactly what to do ("Vendor the missing file(s) into capgen/src/").
  - **Implementation, the same pattern exactly**: moved
    `ccpp_constituent_prop_mod.F90`/`ccpp_scheme_utils.F90` from
    `examples/shared/` (a checkout-only location, unreachable from an
    installed package or a real host model) to `xdsl_ccpp/framework_src/`
    -- inside the installed package itself. Added `_FRAMEWORK_SRC_DIR`/
    `_FRAMEWORK_F90_FILES`/`_resolve_framework_f90_files()` to
    `xdsl_ccpp/tools/ccpp_datatable.py` (same names, same hard-fail-with-
    message behavior as real capgen-v1's own). Wired into the
    `<capgen_files><utilities>` section Stage 8b left empty: now lists
    `ccpp_kinds.F90` (picked out of the already-generated `cap_files` list
    by name -- it's always generated, unconditionally, same as real
    capgen-v1's own first `utility_paths` entry) plus the two resolved
    framework files. `pyproject.toml` gained a
    `[tool.setuptools.package-data]` entry (`xdsl_ccpp =
    ["framework_src/*.F90"]`) so these ship in a real wheel/install, not
    just a dev checkout.
  - **`examples/shared/` removed** (user-requested, once #75 landed) --
    updated all 8 `CMakeLists.txt` files that referenced it by path
    (`examples/advection`, `advection_flat_host`, `constadv`,
    `constituents_dim`, `constprop`, `instances_advection`, `nested_suite`,
    `var_compat`) plus the root `CMakeLists.txt`'s own comment, to
    `${XDSL_CCPP_ROOT}/xdsl_ccpp/framework_src/...` instead. Confirmed
    `XDSL_CCPP_ROOT` (`set(XDSL_CCPP_ROOT "${CMAKE_SOURCE_DIR}")`, root
    `CMakeLists.txt`) is already visible in every example's own
    `add_subdirectory()`-inherited scope, so no new CMake variable needed.
  - **Verified for real, not by inspection alone**: regenerated
    `examples/var_compat`'s real datatable.xml and confirmed
    `<capgen_files><utilities>` now lists all three real file paths;
    ran real capgen-v1's own unmodified `ccpp_datafile.py
    --utility-files` against it and got the same three paths back, exit
    0 (previously: a hard `CCPPDatatableError` with no `<capgen_files>`
    at all, then an empty-but-valid list after Stage 8b, now real
    content). Confirmed the exact `${XDSL_CCPP_ROOT}/xdsl_ccpp/
    framework_src/...` path CMake now substitutes resolves to real files
    on disk. **Built a real wheel** (`python -m build --wheel`) and
    confirmed both `.F90` files are actually present inside it
    (`xdsl_ccpp/framework_src/ccpp_constituent_prop_mod.F90`/
    `ccpp_scheme_utils.F90`) -- proving the `package-data` declaration
    genuinely works for a real install, not just an editable dev
    checkout, which is the exact scenario a real host model like
    CAM-SIMA needs. Confirmed the file move itself is a pure rename with
    zero content changes (`git diff` on the moved files: empty). Full
    suite 628 passed/1 xfailed (unchanged); `ruff` unchanged (same
    pre-existing baseline finding as Stage 8b, confirmed via git-stash
    comparison). Could not run a real Fortran compile of any affected
    example locally (this machine has no Fortran compiler) -- the file-
    existence-at-resolved-path check above is the practical substitute;
    a real compile/link check should still happen on the user's own CI.
- **Stage 9 -- Backend selection + real invocation wiring in
  `cam_autogen.py`. Implemented (2026-08-24), matching the detailed scope
  below exactly.** All in
  `CAM-SIMA-fresh`, none of it in `xdsl-ccpp-fresh` -- Stages 8a/8b already
  gave `cam_autogen.py` everything it needs to *consume*
  (`ResolvedVar` adapter, schema-compatible `datatable_report()` queries);
  Stage 9 is entirely about *calling* xdsl_ccpp instead of real capgen-v1
  and picking which adapter to build from the result.

  - **Real call chain, traced directly, not assumed**: `cam_config.py`'s
    `ConfigCAM.generate_cam_src()` (the CIME buildcpp-style driver) reads
    CIME case XML variables via `case.get_value(...)` (e.g.
    `self.__gpu_flag = case.get_value("OPENACC_GPU_OFFLOAD")`,
    `cam_config.py:191`, declared as an `<entry id="OPENACC_GPU_OFFLOAD">`-
    style block -- the exact shape confirmed via `CAM_DYCORE`'s own entry,
    `cime_config/config_component.xml:106-118`), then calls
    `generate_registry()` -> `generate_physics_suites()` ->
    `generate_init_routines()` in sequence (`cam_config.py:867-904`).

  - **(1) New CIME xml variable.** Add an `<entry id="CCPP_GENERATOR">`
    block to `cime_config/config_component.xml`, matching `CAM_DYCORE`'s
    exact shape (`type=char`, `valid_values=capgen,xdsl_ccpp`,
    `default_value=capgen` -- the default MUST stay real capgen-v1, so
    every existing case/test keeps building exactly as it does today with
    zero opt-in required; `group=build_component_cam`,
    `file=env_build.xml`). Read it in `cam_config.py` alongside
    `self.__gpu_flag` (`case.get_value("CCPP_GENERATOR")`), thread it as a
    new parameter into the `generate_physics_suites(...)` and
    `generate_init_routines(...)` calls.

  - **(2) `generate_physics_suites()` (`cam_autogen.py:484-745`): branch
    on the new parameter.** The `capgen` branch is the *entire existing
    function body, byte-for-byte unchanged* -- this is the one thing Stage
    9 must not touch, since it's CAM-SIMA's real, currently-working
    production path. The `xdsl_ccpp` branch is genuinely new code:
    1. Build the equivalent xdsl_ccpp CLI invocation from the same
       `host_files`/`scheme_files`/`sdfs`/`host_name`/`genccpp_dir`
       variables the `capgen` branch already computes earlier in the same
       function (suite/scheme/host discovery is backend-agnostic --
       nothing there needs duplicating).
    2. **Invoke as a subprocess, not xdsl_ccpp's Python API in-process --
       a specific, evidence-based choice, not a style preference.** Traced
       `ccpp_dsl.py`'s own methods directly: several (e.g.
       `run_pipeline_stage`'s own error path) call `sys.exit(1)` on
       failure rather than raising a catchable exception -- confirmed via
       this doc's own "Smaller interface-shape gaps" note below ("No
       `CCPPError`-equivalent exception type"). Calling these Python
       methods in-process from `cam_autogen.py` would let a cap-generation
       failure kill CIME's *entire build process* with a bare exit code,
       not a clean, catchable `CamAutoGenError` the way every other
       failure path in this file works. A subprocess call isolates that:
       `cam_autogen.py` checks `CompletedProcess.returncode` and raises
       `CamAutoGenError` itself on nonzero, exactly like every other error
       path in this file already does. This also matches capgen-v1's own
       stated convergence goal (`doc/capgen_compat_layer.md`,
       re-confirmed via the 2026-08-13 re-validation above): CLI
       invocation is the *preferred* interface, Python API only when CLI
       is impossible -- it isn't impossible here.
       **Update (2026-09-29): this specific blocker is fixed.**
       `ccpp_dsl.py` no longer calls `sys.exit()` internally except at its
       own CLI `main()` -- failures now raise a catchable `CcppDslError`,
       making `ccppMain().run()` safe to call in-process. The subprocess
       choice documented here was correct when made and CAM-SIMA's own
       production path (subprocess + `--emit-resolved-vars` JSON) doesn't
       need to change on this basis alone, but the door is now open to an
       in-process alternative if a future in-process, object-returning API
       (tracked in `BACKLOG.md`) makes that worthwhile.
    3. Command shape (confirmed against `ccpp_dsl.py --help` and
       `ccpp_prebuild.py`'s own precedent for the same option set):
       `--host-files`/`--scheme-files`/`--suites` each want one
       comma-joined string, not a repeated flag (`CHANGELOG.md`'s
       own "Smaller interface-shape gaps" note below already flags this
       list-vs-string mismatch -- this call site is where it has to be
       handled, via `",".join(...)`); plus `--host-name`, `-o
       <genccpp_dir>`, `--tempdir`, `--emit-datatable <cap_output_file>`
       (same path the `capgen` branch already computes and later queries
       via `datatable_report()` -- unchanged), and a **new**
       `--emit-resolved-vars <json_path>` (e.g.
       `os.path.join(genccpp_dir, "resolved_vars.json")`).
    4. On nonzero exit, raise `CamAutoGenError` with the subprocess's
       captured stderr, matching this file's own existing error-message
       conventions elsewhere.
    5. **The `utility_files`/`dependencies` `datatable_report()` calls
       immediately after (`cam_autogen.py:731-745`) need zero changes for
       either backend** -- this is Stage 8b's actual payoff: real
       capgen-v1's own vendored `ccpp_datafile.py` reads xdsl_ccpp's
       `datatable.xml` exactly as it reads real capgen-v1's own, so this
       whole block (`DatatableReport("utility_files")`,
       `DatatableReport("dependencies")`, the RRTMGP dependency-path
       adjustment, `_update_genccpp_dir`) is genuinely backend-agnostic
       already and needs no branch.
    6. **Known, accepted consequence of leaving `<capgen_files><utilities>`
       empty (Stage 8b, task #75 follow-up)**: for the `xdsl_ccpp` branch
       specifically, the `utility_files` query will always return an empty
       list until task #75 lands, so `_update_genccpp_dir` copies nothing
       via that path for an xdsl_ccpp-generated build. Not a Stage 9 bug --
       an explicit, already-tracked gap; Stage 9 should not attempt to
       work around it by inventing a filename-pattern heuristic here
       either (same reasoning as Stage 8b's own deferral).
    7. **Return-value naming wart, worth fixing while touching this
       code, not required**: `generate_physics_suites()`'s own return
       tuple's `capgen_db` position becomes backend-dependent (a real
       `CCPPDatabaseObj` for `capgen`, a JSON file path string for
       `xdsl_ccpp`) -- consider renaming to something backend-neutral
       (e.g. `resolved_vars_source`) at both this function's own return
       and `generate_init_routines()`'s own parameter, so the dual meaning
       is visible in the name rather than only in a comment.
  - **(3) `generate_init_routines()` (`cam_autogen.py:754-811`): branch on
    the same parameter.** `capgen` branch unchanged
    (`Capgenv1ResolvedVars(cap_database)`); `xdsl_ccpp` branch imports
    `XdslCcppResolvedVars` (`from resolved_var_xdsl_ccpp import
    XdslCcppResolvedVars`, same `sys.path` convention the rest of this
    file already relies on) and constructs `XdslCcppResolvedVars(cap_database)`
    -- where, per the naming wart above, `cap_database` in this branch is
    actually the resolved-vars JSON path, not a database object; pass the
    backend selection explicitly as a new parameter here too rather than
    inferring it from `cap_database`'s own type, since explicit is safer
    than type-sniffing for a cross-backend branch like this.
  - **Verification plan, staged**: (a) `CCPP_GENERATOR=capgen` (the
    default) produces a byte-identical build to today's -- this is the
    regression check that matters most, since it's the only currently
    real production path; (b) `CCPP_GENERATOR=xdsl_ccpp` against a
    minimal real CAM-SIMA test case, confirming cap generation succeeds,
    `write_init_files.py` runs against `XdslCcppResolvedVars`, and the
    build at least compiles (full run-to-completion comparison against
    real capgen-v1's own output is a stretch goal, not a Stage 9 blocker,
    given the still-open items below); (c) a deliberate cap-generation
    failure (e.g. a malformed suite XML) under `CCPP_GENERATOR=xdsl_ccpp`,
    confirming it surfaces as a clean `CamAutoGenError`, not a raw
    subprocess traceback or a silently-succeeded partial build.
  - **Open items this stage does not resolve, inherited from 8a/8b,
    listed here so Stage 9 isn't blocked pretending they don't exist**
    (as originally drafted, before task #75 and the Copilot PR #94 fix
    landed later the same day -- **correction, 2026-09-29: both of those
    were in fact resolved before this document's own Stage 9 write-up was
    finished; the list below originally named them "still open" by
    drafting-order accident, not because they genuinely were.** Only the
    first item was ever a real, still-open gap, and it's since been
    superseded too -- see the note under Stage 8a above):
    the deferred 13-fixture `write_init_files.py` byte-identical sweep
    (superseded, see above); ~~task #75 (`utility_files` vendoring)~~
    (done, see Stage 8b follow-up above); ~~the narrower suite-level-
    `<init>`/`<final>`-scheme-reference gap in Stage 8b's own dependency
    filter~~ (done, see the Copilot PR #94 follow-up under Stage 8b above).

  - **Implementation, matching the scope above exactly (`CAM-SIMA-fresh`,
    branch `xdsl-ccpp-adapter`)**: `<entry id="CCPP_GENERATOR">` added to
    `cime_config/config_component.xml` (`valid_values=capgen,xdsl_ccpp`,
    `default_value=capgen`); `cam_config.py` reads it via
    `case.get_value("CCPP_GENERATOR")` alongside `self.__gpu_flag`, threads
    it into both `generate_physics_suites(...)` and
    `generate_init_routines(...)` calls (renaming the unpacked return value
    at this call site from `capgen_db` to `resolved_vars_source`, per the
    naming-wart note above -- the function-internal variable name stays
    `capgen_db` inside `generate_physics_suites` itself, to keep the diff
    to the untouched `capgen` branch minimal). `generate_physics_suites()`
    and `generate_init_routines()` both gained a `ccpp_generator="capgen"`
    parameter (default matches the CIME variable's own default, so any
    other caller that doesn't yet pass it keeps today's behavior) and an
    `if ccpp_generator == "xdsl_ccpp": ... else: <original code, unchanged
    except for reindentation>` branch exactly where scoped. The
    `XdslCcppResolvedVars` import is deliberately **not** added alongside
    `Capgenv1ResolvedVars` at this file's own top-of-file import block --
    it transitively imports `xdsl_ccpp` itself, and an unconditional
    top-level import would make every `ccpp_generator=capgen` build (the
    only real production path) fail on any system without `xdsl_ccpp`
    installed. Deferred to a local import inside
    `generate_init_routines()`'s own `xdsl_ccpp` branch instead, with
    `sys.path` temporarily re-extended with `_REG_GEN_DIR` around it
    (mirroring this file's own top-of-file append/remove pattern, since
    that directory was already removed from `sys.path` by the time this
    branch runs).
  - **Verified for real, in the two ways actually available without a
    working CIME case (the `ccpp_framework` submodule gap above blocks a
    true end-to-end CIME run just like it blocked Stage 8a's own full
    sweep)**: (1) `pylint --rcfile=test/.pylintrc` on both modified `.py`
    files: 9.89/10 (baseline, confirmed via git-stash comparison: 9.88/10)
    -- every finding present in both runs is pre-existing (same functions,
    shifted line numbers only); the one genuinely new finding
    (`import-outside-toplevel` on the deliberately-deferred import) is
    suppressed with a targeted `#pylint: disable`/`#pylint: enable` pair,
    matching this file's own existing suppression convention. (2) Built a
    minimal real fixture (one host module, one scheme, one suite) and ran
    the *exact* command shape `generate_physics_suites()`'s new branch
    constructs directly against it: produced the caps, `resolved_vars.json`,
    and `ccpp_datatable.xml` in one call, exit 0; fed the resulting JSON
    through the real `XdslCcppResolvedVars` adapter (confirming
    `generate_init_routines()`'s own new branch consumes it correctly) and
    separately through real capgen-v1's own unmodified `ccpp_datafile.py`
    (confirming the unchanged `datatable_report()` calls right after still
    work, per Stage 8b) -- both succeeded. Also ran a deliberately broken
    invocation (nonexistent scheme file) and confirmed a clean nonzero exit
    (1) with an informative stderr message, exactly what the new
    `if result.returncode != 0: raise CamAutoGenError(...)` check needs --
    not a hang, a traceback leaking past the subprocess boundary, or a
    silent partial success.
  - **Not verified, and can't be without the submodule gap closing
    first**: a true end-to-end CIME case build with
    `CCPP_GENERATOR=xdsl_ccpp` set, and the `capgen` branch's own
    regression check (confirming `CCPP_GENERATOR=capgen`, the default,
    still produces byte-identical output to today) -- the code path is
    unchanged from before this stage (verified by inspection: the only
    difference is one extra level of `if/else` nesting, no logic edits),
    but hasn't been re-run through a real case build this session.

Stages 8a/8b can proceed independently and in parallel; Stage 9 depends on
both landing first (it wires together exactly what they each produce).

---

### Workstream 2: Fix the DDT redefinition bug -- RESOLVED

##### Problem (as understood before investigation)

Confirmed, reproducible bug: when a suite (a) generates both a host cap
and a suite cap, and (b) references a DDT shared between host and scheme
(e.g. `ccpp_constituent_prop_ptr_t`), xdsl's IR verifier rejected the
combined module with `Redefinition of symbol
"ccpp_constituent_prop_ptr_t"`. Reproduced via CAM-SIMA's
`test_simple_reg_constituent_write_init` fixture.

##### Actual root cause (confirmed by direct MLIR inspection)

Not a duplicate *type definition* -- a duplicate *use-association stub*
(an `llvm.GlobalOp` named after the DDT, tagged with which Fortran module
to `use`), and confined entirely to `ccpp_cap.py` (`suite_cap.py` was
never at risk -- it only has one stub-emission path). `_generate_ccpp_cap_module`
had two independent paths that could each decide to emit a stub for the
same DDT without knowing about the other:

1. `_generate_constituent_api()` (`constituent_cap.py`) unconditionally
   emits its own hardcoded stubs for `ccpp_constituent_properties_t`/
   `ccpp_constituent_prop_ptr_t` whenever constituent handling is needed
   -- necessary, since the constituent-registration code it generates
   references these types regardless of whether any *parsed metadata
   arg* happens to be typed with them.
2. A generic scan (`_collect_ddt_use_stubs`, fed by `ddt_source_module`)
   over every arg table's declared argument *types*, emitted afterward.

Both got added to `_generate_ccpp_cap_module`'s `all_globals` list; path 1
was tracked in a local dedup set (`shared_seen_host_globals`), but path 2
used `_collect_ddt_use_stubs`'s own fresh, local `seen` set and never
checked path 1's output -- so when a scheme's arg table also referenced
`ccpp_constituent_prop_ptr_t` by type (the common case), both paths
independently added a same-named `GlobalOp`, producing the collision.

Confirmed via direct MLIR inspection at each pass boundary (dumping every
submodule's child symbol names) that exactly two `GlobalOp`s named
`ccpp_constituent_prop_ptr_t` existed inside the generated
`<Host>_ccpp_cap` submodule as of right after `generate-ccpp-cap` --
nothing to do with `TablePropertiesOp`/type-definition duplication at
all.

##### Fix applied

`xdsl_ccpp/transforms/ccpp_cap.py`, in `_generate_ccpp_cap_module`: route
the second (generic) stub-emission path through the same
`shared_seen_host_globals` dedup already used for the constituent-API
stubs, instead of a raw `all_globals.extend(...)`. Six-line change,
`constituent_cap.py` untouched (its stubs are still necessary on their
own). Diff lives uncommitted in the sandbox
(`xdsl_ccpp/transforms/ccpp_cap.py`) pending review.

##### Verification

- Direct MLIR inspection: zero duplicate symbols in the generated
  submodule after the fix; `module.verify()` passes.
- `test/unit/python/test_write_init_files.py` (CAM-SIMA, real subprocess
  path, all 16 tests): `FAILED (errors=15)` -> `OK`.
- Full `test/run_python_unit_tests.sh`: `4 out of 16 test collections
  FAILED` -> `3 out of 16` (the remaining 3 are the pre-existing, unrelated
  missing-CIME-external issue, not this bug).
- `examples/helloworld` smoke test (non-constituent case): still passes,
  no regression.

##### Remaining follow-up (not yet done)

- Add a permanent filecheck regression test under `tests/filecheck/`
  covering host-cap + suite-cap + constituent-variable generation
  together, so this doesn't silently regress.
- Consider whether `_generate_constituent_api`'s hardcoded stub list
  should eventually be unified with the generic `ddt_source_module`
  mechanism rather than living as a second parallel path at all --
  today's fix makes the two paths *coexist safely*, it doesn't merge
  them.

---

### Smaller interface-shape gaps (fold into Workstream 1's adapter boundary)

Found alongside the two items above; small individually, but the kind of
thing the `ResolvedVar`/adapter boundary should absorb rather than leave
for every caller to work around independently:

- `options_db` takes comma-joined **strings** for file-list arguments;
  capgen-v1 takes plain Python lists. A real format mismatch, not just
  cosmetic.
- No `CCPPError`-equivalent exception type -- xdsl_ccpp uses
  `print()`/`sys.exit()` internally rather than raising something a
  caller can catch programmatically.
- Multi-step manual pipeline (`run_frontend` -> `run_opt` ->
  `split_fortran_output` -> ...) vs. capgen-v1's single `capgen()` call.
  Ergonomics, not a capability gap, but worth a convenience wrapper.

### Not gaps (confirmed, don't re-litigate)

- `degC` vs `C` unit-string handling, and metadata declaring a custom
  kind (`kind_dyn_val`-style) with no backing Fortran declaration: both
  were strictness differences in the *vendored capgen-v1 parser*, not
  xdsl_ccpp. xdsl_ccpp handled both cases natively without issue.
- `memory_space` (GPU-directive metadata extension) and the
  `horizontal_loop_extent` -> `horizontal_dimension` vocabulary migration
  are one-directional xdsl_ccpp extensions/improvements, not gaps.

### Untested -- unknown, not confirmed either way

- ~~Real production physics suites from `NCAR/atmospheric_physics`.
  Everything exercised so far was either xdsl_ccpp's own demo examples
  or CAM-SIMA's synthetic unit-test fixtures.~~ -- **resolved, no longer
  untested (`camsima-untested-confirm`, 2026-09-29).** See the combined
  write-up below (folded together with the next two bullets, since all
  three turned out to share the same evidence).
- ~~The `datatable_report()`/`DatatableReport` query path itself...~~ --
  **resolved, no longer untested (2026-08-24, Stages 8b/9/task #75).**
  Directly verified: xdsl_ccpp's own `<capgen_files><utilities>`/
  `<dependencies>` output, read by real capgen-v1's own unmodified
  `ccpp_datafile.py`, returns correct `utility_files`/`dependencies`
  results; `cam_autogen.py`'s own call sites now wired to actually invoke
  xdsl_ccpp (Stage 9). See that section's own write-up above for the full
  verification detail.
- ~~Nested suites, subcycles, multi-suite builds, and GPU/`memory_space`
  directives in an actual CAM-SIMA context (only tested in isolation via
  xdsl_ccpp's own examples) -- still genuinely untested.~~ -- **partially
  resolved (`camsima-untested-confirm`, 2026-09-29); one sub-claim
  narrowed and kept open, see below.**
- ~~Real production physics suites from `NCAR/atmospheric_physics`,
  exercised through the real, now-wired-up `cam_autogen.py` pipeline.~~ --
  **resolved (`camsima-untested-confirm`, 2026-09-29).**
  The single biggest open risk for a first real test: everything this
  whole engagement has exercised was either xdsl_ccpp's own toy examples
  or CAM-SIMA's synthetic unit-test fixtures, never an actual production
  CCPP suite through the real integration path.

**`camsima-untested-confirm` (2026-09-29): confirm-and-close pass on the three bullets above,
against real evidence, not just accumulated session confidence.** Checked each of the four
distinct sub-claims individually rather than treating the group as one item -- they didn't all
turn out equally confirmed:

- **Real production physics suites -- CONFIRMED covered.** This session's own `/cam-sima-regression`
  runs (most recently `xdsl43g`, done for `hle-chunk-consolidate`'s verification) built and ran
  real `cam4`/`cam7` physics compsets (`F1850_C4`/`F2000_C4`/`QPC4` on `se_cam4`; `F2000_C7` on
  `se_cslam`) through the actual, wired-up `cam_autogen.py` pipeline -- not toy examples or
  synthetic unit-test fixtures. `suite_cam4.xml`/`suite_cam7.xml` (`src/physics/ncar_ccpp/suites/`
  in `CAM-SIMA.xdsl-ccpp`) are the real production suite definitions used.
- **Subcycles in an actual CAM-SIMA context -- CONFIRMED covered.** `suite_cam7.xml` declares two
  active `<subcycle loop="number_of_diagnostic_subcycles">` blocks (plus one currently
  commented-out `cld_macmic_num_steps` subcycle). The `F2000_C7`/`se_cslam_analy_ic` case's
  `SHAREDLIB_BUILD` phase -- where xdsl_ccpp's own cap generation actually runs -- passed cleanly
  against this exact suite file. (That case's later `MODEL_BUILD` failure is the separate,
  already-diagnosed, unrelated missing-physics-registry gap tracked elsewhere in this file --
  confirmed not a subcycle-handling issue.)
- **"Nested" suites/subcycles specifically -- not applicable, not a real gap.** Checked
  `suite_cam7.xml`'s actual subcycle nesting depth directly (parsed the XML): maximum depth is 1
  -- no real CAM-SIMA suite today nests a subcycle inside another subcycle. The original claim
  can't be confirmed *or* refuted by real testing because the situation it describes doesn't
  currently exist in any real suite; revisit only if a future suite actually adds nested
  subcycles.
- **GPU/`memory_space` directives in an actual CAM-SIMA context -- CONFIRMED covered.** This
  session's separate GPU work (se_cslam_gpu duplicate-copyout fix, se_cslam_gpu/multitape_gpu
  multi-group residency fix, MPAS+kessler GPU isolation fix, shared-lib `__acc_compiled`
  contamination fix -- all found and fixed against real CIME `nvhpc`/OpenACC builds on Derecho, not
  isolated xdsl_ccpp examples) is exactly this claim's own evidence, just recorded separately at
  the time each bug was found rather than cross-referenced here.
- **Multi-suite builds in an actual CAM-SIMA context -- genuinely still untested, kept open.**
  Checked every real CAM-SIMA test case's own `CAM_CONFIG_OPTS` (`--physics-suites <name>`) across
  every test-ID directory still on disk in this session's `fphys_xdsl_test` tree: every single one
  declares exactly one suite name. `--physics-suites` is plural-named and both CAM-SIMA's own CLI
  and xdsl_ccpp's generator (`examples/ddthost`'s own dual `ddt_suite`+`temp_suite` build is an
  existing in-repo proof the generator itself handles it) support more than one, but no real
  CAM-SIMA case anywhere in this environment has ever actually exercised it. Narrower and smaller
  than the original bullet, but a real, honestly-still-open gap -- not tracked as its own numbered
  backlog item (no urgency, no current CAM-SIMA use case for it), just recorded here so a future
  session doesn't need to re-derive this from scratch.

---

## atmospheric_physics duplication analysis (merged from duplication_analysis_summary.md, 2026-09-29)

**Repo analyzed:** local clone of `NCAR/atmospheric_physics` (companion to `ccpp-framework`), HEAD `b45efc1`, clean working tree.
**Scope:** Fortran source (`schemes/`, `phys_utils/`, `to_be_ccppized/`), CCPP metadata (`.meta`), and suite-definition files (SDF, `suites/*.xml`, `test/test_suites/*.xml`).

### Executive summary

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

### 1. Fortran-layer duplication

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

### 2. SDF (suite XML)-layer duplication

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

### 3. CCPP metadata (`.meta`)-layer duplication

Not initially in scope — added after being asked directly whether `.meta` files had been checked (they hadn't).

**Method:** same clone-detection approach adapted to `.meta`'s INI-like block structure (`[ccpp-table-properties]`, `[ccpp-arg-table]`, per-variable `[ varname ]` sections).

**First pass (exact match): only 237 of 23,862 lines (1.0%)** — surprisingly low, and traced to a real bug-and-finding combination: `wet_to_dry_water_vapor.meta`'s `qv` variable is missing a `long_name` field that the sibling `qc`/`qi`/`qr` blocks all have. That's a genuine small inconsistency in the repo, and it also broke exact-match comparison (one incidental optional-field difference made otherwise-identical blocks look "different").

**After normalizing away that purely-documentary field: 607 duplicated lines (2.5%)** — and the families that appear track almost exactly onto the CCPP-scheme-bound Fortran families (`wet_to_dry_*`/`dry_to_wet_*` alone account for 370 of the 607 lines), plus two `.meta`-only matches (`rrtmgp_{lw,sw}_calculate_heating_rate`, `convect_shallow_diagnostics`/`rk_stratiform_diagnostics`).

---

### 4. The bigger question: how much of `.meta` duplicates the Fortran itself?

This turned out to matter more than intra-`.meta` duplication. Field-by-field classification across all ~3,596 variable-argument blocks in the corpus:

| Category | Fields | Lines | % of `.meta` |
|---|---|---|---|
| Fully derivable from Fortran | variable-name header, `type`, `intent` | 10,788 | 45.2% |
| Mixed | `dimensions` (rank derivable; which standard-named quantity each axis represents is not) | 3,596 | 15.1% |
| Must be human-supplied, load-bearing | `standard_name`, `units` | 7,192 | 30.1% |
| Optional, human-added, sparse | `long_name` (present in only ~7.7% of blocks), `advected`, `persistence` | 302 | 1.3% |
| Structural boilerplate | table headers, separators, blank lines | 1,984 | 8.3% |

So **roughly 45% of every `.meta` file is a mechanical mirror of the Fortran signature** (type, intent, argument name), **~15% is half-mechanical** (dimension count, but not meaning), and **~30% (`standard_name`/`units`) is genuinely irreducible information that cannot be derived from Fortran at all** — this is the actual reason `.meta` exists, since CCPP's cross-scheme wiring depends entirely on `standard_name` matching. This matches the repo's own tooling instructions (`scheme_diagnostics_template.F90`): run `ccpp_fortran_to_metadata.py` to get the skeleton, then "complete the metadata (fill out standard names, units, dimensions)" by hand.

##### Proposed intervention: put `standard_name`/`units` in the Fortran source itself

Rather than accepting `.meta` as a permanently separate, hand-synchronized file, embed the non-derivable fields directly at the declaration site via a structured comment:

```fortran
real(kind_phys), intent(in) :: qv(:,:)  !! standard_name=water_vapor_mixing_ratio_wrt_moist_air_and_condensed_water units=kg kg-1
```

This is not a foreign idea for this codebase — it already does the equivalent twice: the `!> \section arg_table_X_run` Doxygen-style markers, and the pervasive `!$acc parallel loop collapse(2)` OpenACC directives throughout `kessler.F90`, `kessler_update.F90`, `wv_sat_methods.F90`. Both are "semantic information a bare type signature can't express, embedded in a structured comment co-located with the code it describes." `standard_name`/`units` would be a third instance of the same house style.

**Practically achievable without changing CCPP itself:** `capgen` only ever consumes `.meta` as a file, indifferent to its provenance. A local pre-build step (extending the already-referenced `ccpp_fortran_to_metadata.py`) could parse the annotated Fortran and mechanically emit `.meta` in full — turning it from hand-maintained source into a generated build artifact that can never drift from the declarations it describes, eliminating exactly the class of bug found in §3 (the missing `qv` `long_name`) by construction.

**Caveats:** a few things aren't naturally per-argument-line (table-level scheme name, cross-references to other schemes' declared dimension standard-names) and need a modest annotation-scheme extension beyond one tag per line; and this fixes the *two-sources-of-truth* problem, not the *N-named-entry-points-per-family* problem from §1 — the two ideas compose (a `scheme_family` generator could emit annotated Fortran per tracer, and this extraction step turns that into `.meta` "for free," with zero un-derivable residue left).

##### Magnitude comparison

| Intervention | Lines eliminable | What kind of win |
|---|---|---|
| `scheme_family` generator (§1) | ~320-360 | Deduplicating copies of a formula *within* Fortran |
| Python SDF DSL (§2) | ~280 | Deduplicating copies of a scheme sequence *within* XML |
| Eliminate `.meta` as hand-maintained shadow file (§4) | **~14,300+** (the derivable+mixed 60.3% of 23,862 lines that would no longer need separate authorship, review, or sync) | Eliminating an entire *second representation* of information that already exists elsewhere |

The third is not just larger, it's a different category of fix — the first two remove redundant copies of the same kind of artifact; the third removes the need for an entire redundant artifact format to exist as hand-written source at all. It is also the one requiring the most new tooling investment (an annotation parser and a pre-`capgen` generation step), versus the other two, which are purely local Python authoring-layer changes with no build-pipeline impact.

---

### 5. Effort assessment: eliminating the `.meta` shadow file

This section evaluates how hard the §4 proposal (embed `standard_name`/`units` in the Fortran source and generate `.meta` mechanically) would actually be to build, grounded in a review of the real source of [`johnmauff/xdsl-ccpp`](https://github.com/johnmauff/xdsl-ccpp) — an experimental MLIR/xDSL-based alternative to `ccpp_capgen` under active development — rather than assessed in the abstract.

**Most of the required architecture already exists:**

- **Two independent "derive from Fortran" extractors are already implemented** — `fparser2_to_meta.py` (pure-Python parse) and `fir_to_meta.py` (via Flang/HLFIR compilation) — and both docstrings independently state the exact same gap this analysis derived from `atmospheric_physics` data: *"Information NOT available from Fortran source text: `standard_name`/`long_name`, `units`, kind name."* This is convergent validation of the §4 field-derivability split from a completely independent source.
- **`ccpp_generate_meta.py` already generates stub `.meta` skeletons** from either extractor, filling unresolvable fields with placeholders (`std_name_001`, `enter_units`) — matching the existing `ccpp_fortran_to_metadata.py` workflow, i.e. "generate skeleton, then hand-edit," not yet closing the loop.
- **The IR already has zero-cost room for the missing fields.** `ArgumentOp` in `xdsl_ccpp/dialects/ccpp.py` already declares `standard_name`, `units`, `long_name`, `dim_names` as first-class optional properties, currently populated from the XML/`.meta` frontend or the Python `py_api` inline-authoring mode. The `.meta`-text writer (`meta_from_module`) already prints these generically from whatever's on the op. **Adding a third way to populate the same properties — from a parsed Fortran comment — requires no dialect change and no writer change**, only a change to the extraction step.
- **A Python suite-authoring frontend already exists** (`xdsl_ccpp.frontend.py_api`, `@ccpp_suite`/`@ccpp_scheme`/`forLoop`), independently arriving at the same "suites should be composable Python, not XML" idea proposed in §2 — though without a `dry_basis`/`theta_basis`-style auto-bracketing combinator yet.

**The hard technical fork:** annotation-based generation can only ever work through the `fparser2` path, never the Flang/FIR path. Once Flang compiles source to FIR/HLFIR, comments are gone — `fir_to_meta.py` reads compiler IR that never retained them. So this only ever extends `fparser2_to_meta.py`; the compiler-validated route stays `.meta`-consuming, not `.meta`-producing, for this purpose.

##### Resolved: how `fparser2` actually handles the annotation

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

##### Resolved: the line-length concern, checked against the real corpus

Pulled the actual `standard_name` length distribution across all 3,596 variable blocks in `atmospheric_physics`:

| Threshold | Count exceeding | % |
|---|---|---|
| > 60 chars | 1,363 | 37.9% |
| > 80 chars | 590 | 16.4% |
| > 100 chars | 224 | 6.2% |
| > 132 chars (traditional Fortran free-form limit) | 27 | 0.8% |

Median is 53 characters, max is 167. `units` values are short and negligible (median 15, max 31 chars). So the risk is real but narrow — under 1% of variables would push a trailing-comment line past 132 characters from the standard name alone.

More importantly: **this isn't a new problem the proposal introduces.** The current `.meta` file already contains an unwrapped ~186-character line for that same worst-case name, sitting in the repo today without remark, because plain-text `.meta` was never subject to any line-length convention. What's new is only that Fortran source is traditionally held to a stricter one — so the proposal relocates an existing "some names are long" reality rather than creating it.

##### Refined design: name-tagged annotation block, not trailing-per-line comments

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

##### Bonus finding: `memory_space` is likely derivable too — from existing GPU directives, not a new annotation

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

### Files produced during this analysis

- `suite_kessler_example.py` — worked Python SDF DSL sketch for `suite_kessler.xml`, corrected for the `kessler`/`kessler_update` adjacency and crossed-bracket issues discussed in §2.
- Clone-detection scripts (Fortran, SDF-block, `.meta`) were run from scratch space and are not preserved in this directory, but all reported numbers are reproducible from the methods described above.

---

## EAMxx bridge automation design proposal (merged from EAMxx/EAMxx-bridge-automation.md, 2026-09-29)

This document is a forward-looking design proposal, not a record of work already done (see
`EAMxx/kessler-README.md` for that). It addresses: given both the CPU and GPU (OpenACC) Fortran versions of a
scheme like Kessler, how would `xdsl-ccpp` need to be used and extended to automatically generate
all of the code required to call it from EAMxx, including the EAMxx `AtmosphereProcess` C++
interface itself, not just the Fortran bridge/cap layer? Investigated 2026-07-29 by reading the
`xdsl-ccpp` generator source (`xdsl_ccpp/transforms/`) in addition to its docs. No code changes were
made; nothing here has been implemented.

---

### What already exists in xdsl-ccpp that's reusable

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

### Phase A -- Teach the metadata format about CPU/GPU scheme variants

This directly fixes bugs #2/#3 from `EAMxx/kessler-README.md` at the tool level instead of via a hand-patched meta
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

### Phase B -- Make the chost cap's device-pointer contract explicit

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

### Phase C -- A new "EAMxx AtmosphereProcess" printer

This is the actual "generate the whole C++ interface" ask. Nothing like it exists in xdsl-ccpp today
-- `multilanguage_plan.md` only ever generates a flat C header plus a thin C++ ergonomics wrapper
(`Kessler_chost.hpp`), never a framework-integrated host class. It would be a new backend module,
e.g. `xdsl_ccpp/backend/print_eamxx_process.py`, consuming the same completed IR that
`cpp_interop.py` already builds.

##### Mechanical part (low risk -- the IR already has what's needed)

- `initialize_impl` / `run_impl` / `finalize_impl` bodies that call the generated
  `Kessler_chost_physics_*` entry points in the correct lifecycle order. This is a direct readout of
  the suite's lifecycle function list, which `cpp_interop.py` already computes internally.

##### Requires genuinely new, EAMxx-specific metadata vocabulary

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

##### Should stay hand-written -- permanently, not just for now

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

### Revision (2026-07-29): the real suite XML changes the "hand-written" assessment

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

##### Category 1 -- Real CCPP schemes, formulas match, kept hand-fused purely for performance

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

##### Category 2 -- Nominally generatable; needs manual/metadata verification of matching conventions, not an assumption

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

##### Category 3 -- Real schemes, structurally superseded by EAMxx's own centralized infrastructure

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

##### `geopotential_temp` -- a fourth, distinct case: linked but dead

`geopotential_temp` is in the suite, and its `.F90` is already linked into
`kessler/CMakeLists.txt`'s source list, but it is never actually called anywhere -- `z_mid` is instead
derived by a hand-written Kokkos team-parallel-scan (`calculate_z_int`/`calculate_z_mid`). Unlike
Category 3's entries, there is no comment establishing this as a deliberate, verified substitution --
it reads as linked dead code rather than a documented architectural decision.

##### A cheaper, higher-value piece of tooling than the full `AtmosphereProcess` printer

Reading the real suite XML suggests a "suite-coverage checker": a small script that diffs the real
suite XML's `<scheme>` list against the `<scheme>` tracking comments already present in
`eamxx_kessler_process_interface.cpp`, and flags any suite entry with no corresponding comment at
all. That check alone would have flagged the wet/dry conversion question mechanically (it turned out
to be a non-issue for Kessler, but the bridge gave no evidence of having checked), and would catch the
same class of silent gap for every future scheme brought in this way. It requires no new xdsl-ccpp
printer and no new metadata vocabulary -- just a script comparing two lists of scheme names -- and
would be worth building well before Phase C.

---

### Recommended order

Do Phase A and Phase B first. They are a direct, generalizable fix for a bug already found and
documented in `EAMxx/kessler-README.md`, require no new printer, and immediately make `ccpp_xdsl` produce a
correct dual-variant chost cap for Kessler with no manual patching of generated output. The
suite-coverage checker above is a similarly cheap, high-value addition and should happen around the
same time -- it needs no generator changes at all. Phase C is the larger "generate the whole
interface" ask, but it is an order of magnitude more implementation effort, and even fully built would
still leave some hand-written code inside `run_impl`: the QA-check bounds and energy-fixer bookkeeping
permanently (see above), and the Category 1 preprocessing kernels (`calc_exner`/
`temp_to_potential_temp`) by deliberate performance choice rather than necessity. "Automatically
generate all of the code" is realistically achievable for the bridge/cap layer and the
lifecycle-orchestration skeleton, but not for the entire file.
---

## TDB-002 resolution: constituent API raw-string assembly converted to typed IR (2026-09-30)

Archived from `BACKLOG.md`'s "Technical debt" section on resolution, matching this
repo's standard practice of moving resolved items out of the open-items list and
into this file, with only a short pointer left behind.

**File**: `xdsl_ccpp/transforms/constituent_cap.py`. **Added 2026-09-06;
extended 2026-09-15; narrowed 2026-09-29; RESOLVED 2026-09-30.**

**Original problem** (kept for context/citation, since `TDB-003`/`TDB-004`
reference this item by number): all constituent API subroutines were
built as raw Python f-strings emitted verbatim by `print_ftn.py`, instead
of going through typed MLIR IR the rest of xdsl_ccpp uses.

**Resolution, staged as originally scoped (a/b/c/d/e/f)**:
- **(a)** Removed `ConstituentApiOp` (the op this item's original text was
  written against) as dead code — confirmed never constructed anywhere;
  superseded by `CamHostConstituentApiOp`/`NonCamHostConstituentApiOp`
  since commit `125cfe2`, which the original scoping note hadn't caught up
  to. **Stage C was therefore already done** before this item's own work
  began, just via a different op family than planned.
- **(b)** Wired in 4 already-existing-but-unused ops (`SafeDeallocOp`,
  `NullifyPointerOp`, `AllocateOp`, `ZeroFillOp`) for their direct-fit
  statements.
- **(c)+(d)+(e) (merged during implementation — found interleaved within
  the same subroutines, not cleanly separable as originally staged)**:
  designed and added 5 new ops (`PointerAssignOp`, `DdtMethodCallOp`,
  `ErrorGuardOp`, `IfThenOp`, `TextBoundedDoLoopOp`); converted all 10
  subroutines; gave `ScopedBlockOp` its first real usage anywhere in the
  codebase; removed the now-dead `_error_guard()` Python helper.
- **(f)**: finished Stage A for the one piece the original scoping
  correctly identified as still-raw — the multi-instance per-instance
  bundle derived type. Two more new ops (`DerivedTypeDefOp`,
  `DdtComponentDeclOp`); changed `NonCamHostConstituentApiOp`'s own
  signature (dropped its `type_defs: StringAttr` property in favor of a
  `DerivedTypeDefOp` region child).
- **Bonus**: added a 5th FileCheck golden (`instances_advection-xml.mlir`,
  ×3 dirs) — the only example that exercises the multi-instance path at
  all, closing a real pre-existing coverage gap.

**A few one-off `RawFortranLinesOp` text leaves remain deliberately**
(plain scalar assignments, one `write()` call, `#ifdef USE_GPU` directive
blocks, an `allocate(x, stat=errcode)` STAT-clause form) — not a scoping
miss, a deliberate boundary: converting *statement shape* (if/else,
do-loops, type-bound calls) is what this item was about, and is done.
Eliminating those remaining leaves entirely, and the deeper issue that
even the now-typed ops still carry raw Fortran-syntax *expression text*
in their string properties, is `lang-neutral-expr-ir` (new item, added
2026-09-30, sequenced after the chost cap's own conversion below; given a
`TDB-004` numeric ID at the time this entry was written, renamed to this
stable slug shortly after — see `BACKLOG.md`'s Technical Debt section
intro).

**Verification**: full `pytest tests/` green throughout (714 passed, 1
xfailed after the bonus golden), all FileCheck goldens regenerated and
manually diff-reviewed before accepting at each stage. Final
`/cam-sima-regression` run (test ID `xdsl44g`, gnu): 30/31 aux_sima cases
pass, 1 known pre-existing unrelated failure (`F2000_C7`/cam7
`MODEL_BUILD`, same root cause as confirmed during `hle-chunk-consolidate`'s
own verification — tracked separately, not a `tdb-002` regression).
Several of the passing cases (`se_cam4`, `se_cslam`, `F2000_C7`'s own
`SHAREDLIB_BUILD` phase) directly exercise the converted constituent API
against real CAM-SIMA builds.

**Effort actually spent**: roughly matches the corrected estimate made
before starting (~1.5-2 weeks of nominal effort, not the original stale
"~2-3 weeks" figure) — confirming ~60% of the originally-scoped work
(Stage A's common case, all of Stage C) was already done by an unrelated
commit before this item's own work began.

## TDB-003 resolution: `cpp_interop.py` raw C++/Fortran text converted to typed IR (2026-09-30)

Archived from `BACKLOG.md`'s "Technical debt" section on resolution, matching this
repo's standard practice of moving resolved items out of the open-items list and
into this file, with only a short pointer left behind.

**File**: `xdsl_ccpp/dialects/ccpp_utils.py` (`CHostCapOp`),
`xdsl_ccpp/transforms/cpp_interop.py`, `xdsl_ccpp/backend/print_ftn.py`,
`xdsl_ccpp/backend/print_cpp_header.py`. **Added 2026-09-29** (PR 5 of
`ir_cleanup_and_lifecycle_dedup_plan.md`); **RESOLVED 2026-09-30.**

**Original problem**: `CHostCapOp` (the C++ host-model/"chost" BIND(C) cap
generator) carried its entire output — a complete Fortran module, a C
header, and a C++ ergonomics wrapper — as three flat `StringAttr`
properties built by raw Python f-string assembly in `cpp_interop.py`,
instead of going through typed MLIR IR the rest of xdsl_ccpp uses. The
original scoping text left this deliberately unscoped, citing a "larger
design discussion" needed for "abstract ops that both the Fortran and C++
printers can handle." Corrected scope at the start of this work: the file
had grown to 1785 lines/~183 f-strings (not the ~734/~132 the original
note cited), and the "two-printer abstraction" question was already
answered by existing precedent (`KindDefOp`/`func.FuncOp`, both already
printed correctly by both printers off the same typed properties) — the
real job was applying that already-proven pattern to `CHostCapOp`'s
payload at ~3x `TDB-002`'s scale, not inventing a new architectural
concept.

**Resolution, staged 3 ways as planned**:

- **Stage 1 — `_build_chost_ftn_text`** (pure Fortran, 350 lines, lowest
  risk). `CHostCapOp`'s container shape decided: one op, `ftn_body`
  (region, replacing `ftn_text: StringAttr`), `cpp_text`/`wrapper_text`
  staying `StringAttr` until their own stages (deferred deliberately —
  `print_cpp_header.py` had no op-dispatch printer yet, so region-izing
  those immediately would have meant inventing that infrastructure
  speculatively). New ops: `AssignOp`, `BindCSubroutineOp` (covers both
  `subroutine` and `function ... result(...) bind(C, ...)` shapes),
  `CToFortranStringCopyOp`/`FortranToCStringCopyOp`, `CallStatementOp` +
  a shared column-wrap helper (unifying what `_emit_subr_header`/
  `_emit_call` each hand-rolled separately — both removed as dead code).
  `_chost_fn_contexts`'s 3x-independent call (one per builder, on
  identical inputs) folded into a single shared call. Declaration-only
  boilerplate (module/use/private/public/BIND(C) struct def) stays a
  single `RawFortranLinesOp`, matching the existing convention that
  declarations stay opaque text everywhere else in this codebase.
  Verified: `chost-r3-ftn.mlir` re-confirmed XFAIL for its same
  pre-existing documented reason (not silently "fixed" as a side effect);
  GitHub CI green; `/cam-sima-regression` run `xdsl45g`: 28/31 pass + 1
  known pre-existing unrelated failure (`F2000_C7`/cam7 `MODEL_BUILD`,
  same root cause tracked since `hle-chunk-consolidate`/`TDB-002`, not a
  `TDB-003` regression).

- **Stage 2 — `_build_chost_cpp_text`** (C header, 77 lines, design-heavy
  not volume-heavy). `cpp_text: StringAttr` → `cpp_body` (region). New
  ops: `CppIncludeOp`, `ExternCGuardOp`, `CFunctionSigOp` (covers both C
  prototypes and, for Stage 3, inline C++ definitions), `CppFieldDeclOp`,
  `CppStructDefOp` (POD-only at this point). `print_cpp_header.py` gained
  its own op-dispatch printer (`_print_cpp_op`, mirroring `print_ftn.py`'s
  `print_op`) plus a shared banner constant, which also let
  `_emit_cap_header` (the regular Fortran-host `ccpp_cap.h` path) drop its
  own hand-duplicated copy of the same guard/banner text. Verified: **zero**
  goldens needed regeneration — output matched the pre-existing
  absolute-indentation format exactly; constituent-struct/prototype path
  manually verified via the `constprop` example (no existing golden
  covers it).
  **Deferred deliberately, not rushed**: unifying `_chost_cpp_type`
  (`cpp_interop.py`) with `_cpp_type` (`print_cpp_header.py`) into one
  shared type-decision table — the two key off structurally different
  inputs (a resolved `ChostArgInfo` dict vs. an MLIR type) with several
  independently-evolved edge cases (`is_ncol`/`is_nz` special-casing;
  rank-0 reals always being `value, intent(in)` regardless of actual
  intent) that need careful reconciliation to merge safely. Tracked as a
  new backlog item (`cpp-type-table-unify`) rather than left implicit.

- **Stage 3 — `_build_chost_wrapper_text`** (genuine C++ ergonomics
  wrapper, ~246 lines, the real design risk — no existing op precedent).
  `wrapper_text: StringAttr` → `wrapper_body` (region), completing the
  container-shape migration for all three outputs. New ops:
  `CppNamespaceOp`, `CppCallStatementOp` (C++ sibling of
  `CallStatementOp`; the shared Fortran column-wrap helper was
  generalized with a `cont_marker` parameter — default `" &"` preserves
  both existing Fortran call sites byte-for-byte — and renamed
  `wrap_paren_list` so `print_cpp_header.py` could import it
  cross-module, same pattern already used for `classify_arg_intent`),
  `CppConstructorOp` (member-initializer-list constructors, no
  `struct_name` of its own — the containing struct supplies it at print
  time), `CppBraceInitCallOp` (the designated-initializer struct-literal
  idiom), `RawCppLinesOp` (permanent escape hatch, C++ sibling of
  `RawFortranLinesOp` — also used as the Stage-3-step-1 staging vehicle).
  Extended: `CFunctionSigOp` gained `is_const`; `CppFieldDeclOp` gained
  `init_expr`/`type_width` (padding formula changed to pad-plus-
  mandatory-space — verified byte-identical to Stage 2's own 3 actual
  type strings, and incidentally fixed a latent bug in the old pad-only
  formula that silently dropped the separating space for any type name
  ≥9 chars, never triggered before Stage 3 needed wider ones);
  `CppStructDefOp` gained `methods`/`private_members` regions with real
  `is_pod` enforcement (raises if either is non-empty while
  `is_pod=True` — previously `is_pod` had no printer effect at all).

  Converted in 6 steps (container-shape migration → peel banner/namespace
  into fixed printer-side text and a real `CppNamespaceOp` → pilot
  (`Status` struct + constituent-query functions + one zero-arg
  lifecycle) → generalize to all per-lifecycle functions → `State`
  struct/constructor/`allocate()`/overloads → final review), per a
  dedicated Stage 3 design pass (the original plan explicitly left this
  stage as an unscoped sketch pending Stages 1-2 landing). That design
  pass, cross-checked by an independent review against the real code,
  dropped 3 of the originally-sketched ops as unnecessary
  (`CppVectorAllocFieldOp` — the alloc/vector field pairing was already
  just two independent `CppFieldDeclOp` calls; `CppExprStatementOp`/
  `CppVarDeclOp` — printer-identical to each other and to `RawCppLinesOp`,
  collapsed into one escape hatch matching the `RawFortranLinesOp`
  precedent).

  Found and fixed 4 real bugs during implementation, all caught by local
  verification before reaching any golden: C++ inline functions need `()`
  not `(void)` for zero params (was a C-prototype-only convention
  inherited from Stage 2); `CppCallStatementOp` was initially missing its
  leading indent; `CFunctionSigOp`'s non-empty-body branch had a spurious
  trailing blank line (causing a double blank between wrapper sections);
  and the single-line-vs-multiline parameter list choice needed to key
  off `is_inline` rather than param count (the 3-param loop-bounds
  overload signature needed single-line too, not just the 1-param case).
  The deliberate column-budget-vs-chunks-of-4 call-wrap normalization
  (same kind already established in Stages 1-2) is the one expected,
  intentional output difference from the original hand-rolled wrapping.

  Verified: `g++ -std=c++17 -Wall -Wextra` compile checks at every step
  (approved by the project owner for this stage specifically, given its
  novelty — not a standing practice for future stages) — zero warnings
  throughout, including linking and exercising the actual `State`/
  `allocate()`/`run()` API surface for `kessler` and `tinyddt`, and the
  constituent-query path via `constprop`. The two wrapper goldens
  (`kessler-chost-wrapper.mlir`, `tinyddt-chost-wrapper.mlir`) already
  passed unmodified — their loose `CHECK:` substring matching tolerated
  the call-wrap normalization — so were left untouched rather than forced
  through the auto-updater, which (same issue hit regenerating Stage 1's
  `chost-f32-ftn.mlir`) blows sparse, richly-commented goldens into
  undifferentiated exhaustive dumps with no net coverage gain.

**A real adjacent inefficiency, confirmed still out of scope**: the two
printers run as two fully separate `ccpp_opt.py` subprocess invocations
from `ccpp_dsl.py`, each re-running the entire pipeline independently
(rebuilding `CHostCapOp` from scratch twice). Tracked as a new backlog
item (`cpp-dual-print-pipeline`).

**Verification**: full `pytest tests/` green throughout all 3 stages (714
passed, 1 xfailed). GitHub CI (`tests.yml` + `compile-tests-cmake.yml`)
confirmed green by the project owner after each stage. `/cam-sima-regression`
run once, after Stage 1 only (per the approved plan — the chost/C++ host
path is confirmed unreachable from any real CAM-SIMA `aux_sima` case, so a
repeat run after Stages 2/3 would verify nothing new).

**Follow-on items opened**: `cpp-type-table-unify` (unify
`_chost_cpp_type`/`_cpp_type` into one shared type-decision table) and
`cpp-dual-print-pipeline` (the two-subprocess pipeline inefficiency
above) — both explicitly deferred during this item's own work, not
discovered after the fact. (Note: both were given `TDB-NNN` numeric IDs
at the time this entry was first written; renamed to stable kebab-case
slugs shortly after, matching every other item in `BACKLOG.md` — see that
file's Technical Debt section intro.)

## `lang-neutral-expr-ir` Stages 0-4: expression IR designed and piloted on two real files (2026-10-04)

**Not a full resolution** — kept in `BACKLOG.md`'s Tier 1, re-scoped
rather than archived here, since the item's own Stage 5 (propagate to
every remaining file) is real, separately-scoped future work. This entry
records what Stages 0-4 (the design-and-pilot phase) actually delivered.

**File**: `xdsl_ccpp/dialects/ccpp_utils.py`, `xdsl_ccpp/backend/
print_ftn.py`, `xdsl_ccpp/backend/print_cpp_header.py` (new
`expr_to_cpp_str`, its first-ever expression printer), new
`xdsl_ccpp/backend/expr_precedence.py`, `xdsl_ccpp/transforms/
constituent_cap.py`, `xdsl_ccpp/transforms/cpp_interop.py`. Committed
across 8 commits on branch `lang-neutral-expr-ir` (not yet merged):
`37ae6cc` Stage 0, `ec68e87` Stage 1a, `856847e`/`82db811` Stage 1b+2,
`4cdbd75` PR #109 Copilot review fixes, `e24da85`/`bd07875` Stage 3a,
`cf405c2` Stage 3b.

**Central decision**: reuse xDSL's own `arith`/`math` dialects directly
for arithmetic/logical/comparison/numeric-literal expressions (confirmed,
by reading xDSL's installed dialect source, that an earlier draft
proposing brand-new `BinaryExprOp`/`UnaryExprOp`/`LiteralExprOp` ops
would have reinvented machinery that already exists) — completing
`print_ftn.py`'s own existing-but-unused `register_binops`/`_binops`/
`_cmp_ops` scaffolding instead of building a parallel system next to it.
Seven genuinely new custom ops were added only for what `arith`/`math`
cannot express: `StringLiteralExprOp`, `StringConcatExprOp`,
`VarRefExprOp`, `MemberAccessExprOp`, `IndexExprOp`/`SliceExprOp`,
`CallExprOp`/`KeywordArgExprOp`, `ArrayConstructorExprOp`.

**What shipped**:
- **Stage 0**: `WriteStmtOp`, `PreprocDirectiveOp`, `AllocateOp.stat_var` —
  closed `constituent_cap.py`'s last few raw-string leaves.
- **Stage 1a**: completed `print_expr`'s `arith`/`math` coverage
  (`MuliOp`/`DivSIOp`/`DivUIOp`/`AndIOp`/`OrIOp`/`AddfOp`/`SubfOp`/
  `MulfOp`/`DivfOp`/`CmpfOp`/`math.Pow*`, i1-aware boolean literals) —
  byte-identical output confirmed for every existing real call site
  (pure extension of dead scaffolding, zero new op definitions).
- **Stage 1b+2**: the 7 new ops above, `expr_precedence.py` (precedence/
  parenthesization, shared by both printers), `print_cpp_header.py`'s
  first expression printer (`expr_to_cpp_str`). A real architecture gap
  was found and fixed along the way: building a fresh `arith`/custom-op
  tree and wrapping only its root in a region crashes `module.verify()`'s
  real `IsolatedFromAbove` check — fixed via `_flatten_floating_deps`
  (walks an op's operand tree, attaches every unattached dependency into
  the same region, root last) plus converting 4 ops' shared-sibling
  regions to one-region-per-item (`var_region_def`); this also
  retroactively fixed the same latent bug in `UnitConvertOp`/
  `UnitWriteBackOp`. 15 GitHub Copilot review comments on PR #109 (the
  Stage 1b+2 PR) triaged and fixed: precedence-table gaps, NaN-unsafe
  C++ comparison predicates, negative-literal `**` parenthesization,
  block-argument operand handling in both printers, and 6 cases where
  the new C++ printer now explicitly raises (`TrimOp`, `StrCmpOp`,
  `math.IPowIOp`, `StringConcatExprOp`, two-literal concatenation) rather
  than silently emitting wrong C++ for shapes no real call site exercises
  yet.
- **Stage 3a** (pilot 1, `constituent_cap.py`): all 7 targeted op kinds
  converted from raw text to the new IR, one at a time, full `pytest`
  green between each — `IfThenOp.condition_expr`, `ActiveCheckOp.
  condition_expr`, `ErrorGuardOp.condition`, `DdtMethodCallOp.obj_expr/
  args/kwargs` (the largest, 13 call sites), `PointerAssignOp.rhs_expr`,
  `AllocateOp.dims`, `ModuleVarOp.init_value`. Every op kept an additive
  shape (legacy `StringAttr`/`ArrayAttr` text form fully preserved
  alongside the new structured form) even where nothing else in the
  codebase still used the legacy form, for consistency. A handful of
  real call sites deliberately stayed on the legacy text form where
  structuring would buy nothing (trivial/empty cases) or actively
  regress output (one array-constructor initializer whose Fortran
  line-continuation formatting the generic printer doesn't replicate) —
  each documented inline at its call site.
- **Stage 3b** (pilot 2, `cpp_interop.py`): `CppBraceInitCallOp.
  field_values`, `CppCallStatementOp.call_args`, `CppFieldDeclOp.
  init_expr` converted, proving `MemberAccessExprOp`'s `.`-access through
  the new C++ `expr_to_cpp_str` path specifically (this item's own
  stated acceptance bar for this slice).
- **Stage 3c** (one concrete `UnitConvertOp`/`UnitWriteBackOp` K↔°C
  retrofit): attempted, found genuinely blocked, deferred rather than
  forced — every real `unit_convert` call site operates on this dialect's
  own `RealKindType` (a Fortran generic-kind placeholder), and `arith.
  AddfOp`/`SubfOp`'s operand constraint only accepts builtin
  `Float16/32/64Type`, confirmed directly against xDSL's source. Revisiting
  this needs new `RealKindType`-compatible constant/binary-op vocabulary
  first — real additional scope, not a quick fix, so left for later
  rather than invented under pressure to close out this pilot.
- **Stage 4**: full local `pytest tests/` green throughout every single
  increment above (722 passed, 1 xfailed, unchanged count end to end);
  every FileCheck golden diff touched was regenerated and manually
  diff-reviewed before accepting (never blanket-trusted — the
  auto-updater silently reformatted unrelated, untouched content twice
  during this work, caught both times by hunk-size review and
  hand-patched instead). Final `/cam-sima-regression` run (test ID
  `xdsl36g`, gnu, 31 cases): 30/31 pass, 1 known pre-existing unrelated
  failure (`F2000_C7`/`se_cslam_analy_ic` `MODEL_BUILD`, same root cause
  tracked since earlier items, not a regression from this work).

**Remaining work, now unblocked rather than blocked**: Stage 5 (propagate
the same retrofit to `suite_cap.py`, `run_dispatch.py`, `lifecycle_cap.py`)
and the deferred Stage 3c both stay open in `BACKLOG.md`'s
`lang-neutral-expr-ir` entry — the vocabulary and both printers are now
proven against two real, independent files, so neither is a design
question anymore, just incremental follow-on effort.

## `lang-neutral-expr-ir` Stage 5: propagated to `suite_cap.py`, done in one sitting (2026-10-04)

Direct follow-on to the "Stages 0-4" entry above, same day. Planned as
"propagate to 3 remaining files" per `BACKLOG.md`'s own item text;
turned out to be real work in exactly one of them.

**File**: `xdsl_ccpp/dialects/ccpp_utils.py` (3 op shape changes),
`xdsl_ccpp/backend/print_ftn.py` (3 printer updates),
`xdsl_ccpp/transforms/suite_cap.py` (the actual call-site conversions).

**Scope correction before starting**: a background-agent survey
suggested meaningful retrofit work existed in all 3 remaining files
(`suite_cap.py`, `run_dispatch.py`, `lifecycle_cap.py`). Direct
line-by-line verification (every call site actually read) found this
overstated the scope: `lifecycle_cap.py`'s one `LazyAllocOp` call never
passes `init_value` at all, and `run_dispatch.py`'s one `KeywordCallOp`
always passes an empty override dict while its one `WriteErrMsgOp` has
static literal message fragments with no sub-structure to extract. Both
files needed zero code changes. The entire real scope was 4 op kinds in
`suite_cap.py`.

**Converted, one op kind at a time, full `pytest` green between each**:
- `LazyAllocOp.init_value` (3 real call sites) — one hardcoded string
  literal -> `StringLiteralExprOp`; two `.meta`-sourced `default_value`
  sites (unknown lexical shape, could be `"0.0_kind_phys"`, `".true."`,
  a bare number, ...) -> verbatim `VarRefExprOp` atom, same judgment
  call as Stage 3a's text-atom leaves.
- `ModuleVarOp.init_value` (`lc_const_indices`, 1 site) — the structured
  form already existed from Stage 3a; this was a pure call-site
  conversion (`ArrayConstructorExprOp` of `arith.ConstantOp` ints), zero
  `ccpp_utils.py` changes. Surfaced one benign formatting difference:
  the structured printer's canonical `[ 1, 2 ]` spacing vs. the legacy
  `f"[{init_vals}]"` -> `[1, 2]` (no spaces) — same category as Stage
  1a's operator-spelling normalizations, 2 `end_to_end` goldens updated.
- `SubcycleLoopOp.loop_count` (1 site, 2 branches) — literal branch ->
  real `arith.ConstantOp`; resolved-standard-name branch -> `VarRefExprOp`.
  Self-caught the same dict-insertion-order bug as the "Stages 0-4"
  entry's `ErrorGuardOp` incident (building `is_literal` before
  `loop_count` in the new `props` dict, reversed from the original
  order) — caught by the shape-change-alone `pytest` step before
  touching the call site, fixed immediately.
- `KeywordCallOp.overrides` (1 site with real values) — reused the
  already-existing `KeywordArgExprOp` as the per-entry representation
  rather than inventing a new dict-shaped op. **Caught a real
  implementation bug via the verification discipline itself, before it
  reached the user**: an initial version unconditionally built
  `override_ops=[]` whenever the Python-side dict was empty, which takes
  the "structured but empty" branch instead of the legacy `overrides =
  {}` property — broke every `KeywordCallOp` call site across 8
  goldens (not just the 1 with real overrides), since every no-override
  site silently lost its `overrides = {}` property. The call-site
  conversion's own `pytest` run caught this immediately (9 failures
  instead of the expected 1); fixed by only using the structured path
  when the override dict is actually non-empty, re-verified down to the
  single expected golden.

**Verification**: full `pytest tests/` green after every shape-change
and every call-site conversion — **722 passed, 1 xfailed** throughout,
unchanged from every increment since Stage 1a. 5 `completed_ir` goldens
and 2 `end_to_end` goldens touched in total, every one diff-reviewed
before accepting (one of the `end_to_end` diffs was the intentional
array-constructor spacing normalization noted above; the rest were pure
structural StringAttr-to-region expansions). No new
`/cam-sima-regression` run — not requested for this slice, and
`suite_cap.py`'s own existing coverage (every real suite exercises it)
plus clean `pytest` stands on its own, same reasoning as the "Stages
0-4" entry's Stage 3b discussion.

**Item status after this entry**: `lang-neutral-expr-ir`'s only
remaining open thread is the deferred Stage 3c (`RealKindType` vs.
`arith`'s float-only operand constraint, documented in the "Stages 0-4"
entry) — design, the two-file pilot, and full propagation to every
file with real retrofit candidates are all done.

## `cpp-dual-print-pipeline` resolution: Fortran and C++ header printers now run from one pipeline pass (2026-10-05)

Archived from `BACKLOG.md`'s open-items list on resolution, matching this
repo's standard practice of moving resolved items out of the open-items
list and into this file, with only a short pointer left behind.

**File**: `xdsl_ccpp/tools/ccpp_opt.py`, `xdsl_ccpp/tools/ccpp_dsl.py`,
`tests/unit/test_build_integration.py`. **Added 2026-09-30** (confirmed
out of scope while the chost cap's raw-string-to-typed-IR conversion and
`lang-neutral-expr-ir` were still in progress); **RESOLVED 2026-10-05.**
PR github.com/johnmauff/xdsl-ccpp/pull/110.

**Original problem**: `ccpp_dsl.py` generated a C++ host's `.F90` caps
and C++ headers by invoking `ccpp_opt` as two fully independent
subprocesses — one for `-t ftn`, one for `-t cpp_header` — each
re-parsing the frontend IR and re-running the *entire* pass pipeline
from scratch, including rebuilding every `CHostCapOp` from scratch
twice, just to print two different views of what was otherwise the same
transformed module. `CHostCapOp`'s payload being typed IR now (not raw
text, since the chost-cap conversion/`lang-neutral-expr-ir`) made this
tractable to fix: both printers can safely run against the same
in-memory module from one pipeline run.

**Resolution**:
- `ccpp_opt.py` gained a new `ftn_and_cpp_header` pipeline target —
  calls `print_to_ftn` then `print_to_cpp_headers` against the same
  `prog`. The C++ section is buffered into an `io.StringIO` first so the
  `// -----` divider between sections is only emitted when there's
  actually C++ content to follow, matching each printer's own existing
  "no content, no FILE marker" convention (needed since neither printer
  knows about the other's output when called back-to-back).
- `ccpp_dsl.py`'s `run_opt()` gained a `target: str = "ftn"` parameter.
  The default preserves `ccpp_prebuild.py`'s own existing Fortran-only
  call site exactly (that caller never wants C++ header output, so it's
  deliberately unaffected by the combined-target path). `apply()` now
  picks `ftn_and_cpp_header` instead of `ftn` when a C++ host is
  detected (`language = c++` in a host `.meta`, or `--bind-c`), instead
  of making a second `generate_cpp_headers()` subprocess call.
  `generate_cpp_headers()` itself was deleted (folded into the combined
  target); its "no BIND(C) functions found" diagnostic was preserved,
  now derived from `split_fortran_output()`'s return value (the list of
  section filenames it found, which that method's own signature was
  extended to return) instead of checking a separate intermediate
  file's size.
- **Copilot review round (2 comments, both real, both fixed)**:
  (1) `run_opt`'s own docstring initially over-claimed support for
  `target="cpp_header"` as a standalone value — nothing in the codebase
  actually calls it that way, but if something did, `post_stage_check`'s
  unconditional non-empty-output check would wrongly reject a
  cpp_header-only run's legitimate empty output (no BIND(C) content) as
  a failure, a case the old, deleted `generate_cpp_headers` had handled
  explicitly. Fixed by narrowing the docstring to only document the two
  values actually used ("ftn"/"ftn_and_cpp_header") and explicitly
  warning against the standalone cpp_header case, rather than adding
  unneeded special-case branching for a value nothing calls.
  (2) The new integration test initially only asserted the output files
  existed — which the OLD two-subprocess implementation would also
  produce unchanged, so the test gave no real regression coverage for
  the PR's own defining single-pipeline claim. Fixed by running with
  `--verbose 2` and asserting the `ccpp_opt` subprocess string appears
  in stdout exactly once.

**Verification**: full `pytest tests/`: 723 passed (722 + 1 new
integration test), 1 xfailed — zero FileCheck goldens touched, since
none of them exercise `ccpp_dsl.py`'s orchestration (they invoke
`ccpp_opt` directly with a single `-t`, bypassing this entirely). New
end-to-end CLI test (`test_ccpp_xdsl_generates_both_ftn_and_cpp_headers_
in_one_run`, using the `tinyddt` C++-host example) covers the combined
path through the real `ccpp_xdsl` entry point for the first time.
Manually confirmed the combined target's output is byte-for-byte
identical to `(old -t ftn output) + "// -----\n" + (old -t cpp_header
output)`. Measured wall time on that example: ~1.04s (two subprocesses)
-> ~0.54s (one subprocess), roughly 2x -- savings scale with
suite/scheme count for real builds.

**Risk of leaving as-is**: none -- fully resolved. Output content is
unchanged (verified byte-identical above); this was purely a
process-count/performance fix. `ccpp_prebuild.py`'s own `run_opt()` call
site is unaffected (still defaults to "ftn" only, never requests C++
headers, matching its pre-existing behavior exactly).
