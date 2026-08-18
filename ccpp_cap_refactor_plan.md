# Refactor Plan: Decomposing `ccpp_cap.py` in xdsl-ccpp

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
| `instances`/`instances_advection` | 📋 Backlog (M); needs an architecture decision first | L3296 |
| `opt_arg`'s dead `active` property | ✅ Done (2026-08-13) | L3350 |
| Unconditional unit-conversion buffer allocate for optional args (found while fixing the above) | ✅ Done (2026-08-17) | L3505 |
| Metadata `kind_spec` support (capgen/ddthost port completeness) | ✅ Done (2026-08-17) | L3966 |
| Interstitial-variable register-phase mechanism | ✅ Done (2026-08-17) — non-chained case restored/tested; chained case tracked separately | L4038 |
| `temp_adjust`/`temp_calc_adjust`/`temp_set` rank/dimensionality re-sync to real upstream | ✅ Done (2026-08-17) | L4098 |
| Chained-interstitial allocation-ordering bug (`_build_framework_refs`) | 📋 Backlog (M-L, confirmed real bug, not just untested) | L4085 |
| Metadata `dependencies`/`dependencies_path`/`source_path` tracking (Tier 1: parse + IR-forward, no build-system consumer) | ✅ Done (2026-08-17) | L4176 |
| Metadata dependency-manifest automation for CMake (Tier 2 of the above, overlaps with CMake configure-time item below) | 📋 Backlog (size TBD, needs its own design pass) | L4176 |
| `examples/ddthost`'s own copies of `temp_set`/`temp_adjust`/`temp_calc_adjust` have fallen behind `examples/capgen`'s (missing `kind_spec`, `interstitial_var`, rank re-sync, `temp_adjust_register`) | 📋 Backlog (S-M, found while scoping the above) | L4176 |
| `advection`'s error-path bonus (negative test for constituent-props-outside-register) | 📋 Backlog (S) | L3377 |
| Retire the legacy `horizontal_loop_extent` vocabulary | ✅ Examples migrated (2026-07-27); ✅ `--legacy-mode` gate added, default now rejects (2026-08-13); 📋 actual code-path deletion still open | L3383 |
| Vocabulary-resolution redesign (match capgen-v1's use-association model) | ✅ Stages 1-5 done (2026-08-13); 6-8-phase lifecycle match logged separately | L3589 |

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
    also invalid Fortran. Confirmed by direct inspection: `ddt_suite_suite_data_prep` declares
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
      `test_host_ccpp_physics_run`'s call to `var_compatibility_suite_suite_radiation` now has
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
      `var_compatibility_suite_suite_initialize` now passes `phys_state%scheme_order` directly,
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
      `var_compatibility_suite_suite_radiation` calls `effr_calc_run` inside a nested 3-level
      subcycle loop (`do ccpp_loop_cnt0 = 1, 2` / `do ccpp_loop_cnt = 1, 2`) — the same temp gets
      allocated a second time within the same subroutine invocation, before Fortran ever gets a
      chance to deallocate it.

      **Fixed** by printing a guarded deallocate (`if (allocated(x)) deallocate(x)` — the same
      pattern `CCPPSafeDeallocOp` already uses elsewhere in this file) immediately before every
      `allocate(...)` statement all four of these op cases print, independent of whether a
      write-back exists — safe for pure `intent(in)` values, and a no-op on first entry so it
      doesn't change behavior for the ordinary, non-looped case either. Confirmed via the real
      `Makefile` path: every conversion temp in `var_compatibility_suite_suite_radiation`
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
      (the fix above) but called `var_compatibility_suite_suite_radiation` with the whole,
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
       source, `examples/shared/ccpp_constituent_prop_mod.F90`/`ccpp_scheme_utils.F90`, compiled
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
    per-example support files, not just these two) to link `examples/shared/`'s single-source
    `ccpp_constituent_prop_mod.F90`/`ccpp_scheme_utils.F90` instead of its own local copy — see
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
          `suite_allocate_suite_suite_workspace_group`'s own `intent(out)` dummy argument --
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
  - **Follow-on, logged per project owner request (2026-08-13), not started: full 6-phase ->
    8-phase lifecycle match.** Real capgen-v1 doesn't have 6 lifecycle entry points, it has
    8 -- it splits what this codebase calls "initialize" into two distinct phases
    (`ccpp_init` at the suite level, `ccpp_physics_init` at the per-group level) and
    "finalize" likewise (`ccpp_physics_final` + `ccpp_final`). Stage 5 deliberately did *not*
    attempt this: it's genuine new architecture, not a rename -- would mean adding two new
    lifecycle phases throughout the generation pipeline (`lifecycle_cap.py`, the outer
    `ccpp_cap.py` wrapper, `suite_cap.py`'s own register/initialize/finalize functions) and
    updating every example's driver to call the new two-phase sequence. 📋 Backlog (size TBD,
    likely M-L) -- a separate, bigger effort from anything Stages 1-5 delivered.
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
    Assessed as real, separate follow-on work (not folded into this fix) -- see its own Index
    entry ("Chained-interstitial allocation-ordering bug") for the full risk writeup: requires
    `_build_framework_refs`/`_build_call_ops` to coordinate on interleaved (not flat
    preamble-then-calls) output, touches code shared by every example with any SuiteOwned var
    (`constituents_dim`, `capgen`, `opt_arg`, `suite_allocate`, `var_compat`, `advection`), has
    no existing test or failing example to converge against, and overlaps with the still-open
    `instances` multi-instance architecture decision (real capgen-v1 sidesteps this ordering
    problem entirely with a dedicated suite-data-module construction pass, not ad hoc
    per-phase-function preambles).
  - **Done (2026-08-17):** restored the real `interstitial_var` argument into `examples/capgen`'s
    `temp_adjust.meta`/`.F90` (`temp_adjust_run` produces it `intent(out)`,
    `temp_adjust_finalize` consumes it `intent(in)` -- genuinely cross-phase, separate generated
    Fortran subroutines), deliberately dimensioned by `horizontal_dimension` rather than
    upstream's chained `dimension_for_interstitial_variable`, to prove the working mechanism on
    a real example without depending on the separately-tracked ordering bug above. Verified on
    the real regenerated output: `interstitial_var` gets correct module-level allocatable
    storage, a `LazyAllocOp` guard that runs during `_register`/`_initialize` (sized from a real
    host array's shape via `_find_loop_upper_bound`, same mechanism `to_promote` already used),
    and `temp_suite_suite_finalize` correctly references the same already-allocated module
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
- **`advection`'s error-path bonus, found while confirming the core suite was a duplicate — S.**
  Real capgen-v1 has a deliberate negative test (`dlc_liq`/`cld_suite_error.xml`): declaring a
  `ccpp_constituent_properties_t`-typed arg outside the register phase must error. Unverified
  whether xdsl-ccpp's own constituent-registration code (`constituent_cap.py`) validates this at
  all today, or would silently accept/mishandle it. Small, self-contained check-and-raise if
  missing, matching this session's established validation-gap pattern.
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

---

## Guiding principles throughout

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
