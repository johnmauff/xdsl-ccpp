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
    - **(b)/(c): still not implemented, not scheduled.** (b) moving clause insertion from
      bracketing the *entire* suite-group dispatch call (today's granularity in
      `GPUCcppCapPass._wrap_scheme_call`) down to *individual* scheme calls within a group —
      `GPUDataPass._find_call_in_if` already finds calls at that granularity for host-less scratch
      vars, so this is an ownership/architecture question (does per-scheme-call clause routing move
      into `GPUDataPass`, which today only handles the host-less case, or does `GPUCcppCapPass`
      reach down into suite-level function bodies itself) rather than a small patch; (c) handling a
      group where two schemes touching the same host var need conflicting clauses — not separable
      work, falls out naturally once (b) is done.
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
      `ccpp_cap.py`'s) is different. Track as its own backlog item, separate from `CapScratch`
      residency above — not scheduled, not scoped in detail yet.
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

- **Nested `<subcycle>` support — M/L.** The single highest-value item: `var_compat`'s real suite
  XML nests `<subcycle>` two levels deep, but xdsl-ccpp actively rejects this today
  (`ccpp_xml.py`'s `XMLSubcycle.__init__` raises `ValueError` on a nested `<subcycle>` child, with
  a defense-in-depth second raise in `ccpp_descriptors.py`'s `traverse_group_op`). Read both
  rejection sites: this was a deliberate, considered decision (the `XMLSubcycle` docstring
  literally says "If a real need for nesting turns up later, this is the place to lift the
  restriction" — that need has now turned up). Fix requires, in order:
  1. `ccpp_xml.py`: `XMLSubcycle.__init__` recursively parses a nested `<subcycle>` child as
     another `XMLSubcycle` instead of raising.
  2. `ccpp_descriptors.py`'s mirrored IR-side rebuild: same recursive change.
  3. `cap_shared.py`'s `_iter_schemes` (its own docstring already flags this: "only exercising the
     one-level-deep subcycle case") needs to recursively descend, not just one level.
  4. `suite_variable_model.py`'s independently-duplicated subcycle-flattening copy (duck-typed via
     `"loop_count" in child.attributes`, per its own comment on why it isn't unified with
     `_iter_schemes`) needs the same recursive treatment, separately.
  5. `suite_cap.py`'s call-sequence builder (the `("subcycle", loop_count, is_literal, [...])`
     flat-tuple structure feeding its Fortran loop-emission code around line ~1107) needs to
     become recursive, and the actual generated-Fortran loop emission needs nested `do` loops with
     distinct, non-shadowing loop-index variable names per nesting level — the real design work
     here, not the parsing changes above.
  6. New unit + FileCheck coverage for nested-loop generation, replacing/extending
     `test_subcycle.py::test_nested_subcycle_is_rejected`.
  - Not verified: whether `run_dispatch.py` has its own independent subcycle-flattening
    assumption beyond what `_iter_schemes` covers — check this first before scoping further.
- **`var_compat`'s other two pieces, separate from nested-subcycle:**
  - **Vertical array flipping (`top_at_one=true`) — M.** Reverses vertical-index array sections
    when a scheme's declared top-at-one convention differs from the host's. Architecturally
    similar to the existing `RowMajorConvertOp`/`RowMajorWriteBackOp` pair (row-major/column-major
    conversion at the Fortran/C++ interop boundary) — likely a new `VerticalFlipOp` inserted at
    the same host/scheme arg-marshaling boundary, reusing that established pattern rather than
    inventing a new mechanism.
  - **Kind conversion (`kind_phys`↔`8`) — S/M, verify before assuming unbuilt.** xdsl-ccpp already
    has `generate-meta-kinds`/`--kind-map`/`extra_kind`/`extra_iso` machinery
    (`ccpp_dsl.py::_build_pipeline`, `TypeConversions`) for exactly this class of problem — check
    whether `var_compat`'s specific `kind_phys`↔`8` case is already handled by that machinery
    before scoping new work.
- **`nested_suite` — L, likely blocked on nested-subcycle above.** A real, unimplemented
  cross-file suite-composition mechanism: `<nested_suite name=... group=... file=.../>` inlines a
  *named group* from a *different* suite XML file, nestable 2 levels deep, under schema
  `version="2.0"`, plus suite-level `<init>`/`<final>` scheme hooks (today `XMLSuite` only ever
  reads one file and only parses `<group>` children — `<nested_suite>`, `<init>`, `<final>` are
  currently silently skipped, not rejected, since the parser just ignores unrecognized child
  tags). Needs: recursive cross-file loading with cycle detection, named-group extraction, and new
  suite-level (not group-level) lifecycle codegen for `<init>`/`<final>` hooks. Its scheme `.meta`
  files are byte-identical to `var_compat`'s, meaning its actual expanded suite structure likely
  *also* needs nested-subcycle support — do that item first. Open unknown: `version="2.0"` may
  imply other undiscovered schema changes beyond what's described here.
- **`constituents_dim` — two independent sub-items:**
  - **General suite-workspace vars sized by the live constituent count — M.** Both
    framework-allocated and scheme-allocated variants. Today `ccpp_cap.py`'s `_build_cap_var_map`
    only special-cases exactly two hardcoded framework arrays via `_DIM_TO_ALLOC`'s
    `number_of_ccpp_constituents → "lc_num"` entry — needs generalizing to any suite-workspace var
    dimensioned by the constituent count, not just those two names.
  - **Cross-scheme constituent-flag inference — M/L.** A consumer scheme reads a
    producer-flagged `advected`/`constituent` var without redeclaring the flag itself; capgen-v1
    infers constituent-hood from the producer alone. Today `constituent_cap.py`'s
    `_collect_constituent_info` and `cap_shared.py`'s `classify_arg_ownership` both check
    `advected`/`constituent` as purely local, per-arg properties — no cross-scheme propagation
    exists anywhere. Needs a new analysis step building a module-wide "which standard_names are
    advected/constituent, per any scheme's declaration" set, consulted during classification — a
    real architectural addition, not a small patch.
- **`suite_allocate` — L, plus one cheap independent bugfix.**
  - **Cheap fix, do first, unrelated to the rest — S.** `_build_cap_var_map`'s scratch-var
    allocation silently falls back to allocating size `"1"` for any dimension name not in
    `_DIM_TO_ALLOC` — a latent mis-allocation bug found while scoping this, unrelated to whether
    the larger `suite_allocate` pattern ever gets built. Should raise instead (same "raise, don't
    silently mask" precedent as the Phase 7 Copilot-review fixes), independent of everything else
    here.
  - **The actual pattern — L.** Scheme-allocated (not framework-allocated) suite-scoped scratch
    memory, dimensioned by a *different* scheme's `timestep_init`-phase output, allocated at
    run-time rather than init-time, relying on CCPP's phase-then-scheme execution ordering.
    `suite_variable_model.py`'s own docstring assumes init-time allocation with statically-known
    dimensions throughout — this needs a genuine new allocation-timing model plus
    cross-scheme-phase dependency awareness, not a variant of the existing path.
- **`chunked_data` — size unconfirmed, verify before assuming it needs work.** A host driver
  dispatching physics over `[lb,ub]` sub-ranges per thread (`thread_num`/`nphys_threads` as plain
  scheme args). The generated cap subroutines already accept `col_start`/`col_end`
  (`horizontal_loop_begin`/`horizontal_loop_end`) as bounds throughout this codebase — it's
  plausible the host driver just calls the same generated subroutine repeatedly with different
  `[lb,ub]` ranges per thread, with `thread_num`/`nphys_threads` being ordinary host-matched
  scalar args needing no special code-gen support at all. **Do a quick feasibility test first**
  (run `chunked_data_scheme.meta` through today's pipeline) before scoping this as new work — if
  it already works, this is **S** (just add the test); only escalate to **M** if something about
  sub-range handling genuinely breaks.
- **`instances`/`instances_advection` — M, and a real decision point, not just an estimate.**
  xdsl-ccpp already has a working multi-instance mechanism (`--num-instances` CLI flag →
  `ccpp_t`-handle-based per-instance state, exercised in `examples/helloworld`). Capgen-v1's
  pattern here is architecturally different: explicit `instance_number`/`number_of_instances`
  **scalar args** threaded directly into scheme signatures, plus host DDT arrays literally
  dimensioned by `number_of_instances` — no `ccpp_t` handle involved at all. Building this means
  recognizing `instance_number`/`number_of_instances` as ordinary host-matchable standard names
  and confirming array-dimensioning-by-them works generically (likely does, if dimension-name
  handling elsewhere is already name-agnostic — needs verification, not assumed). **Open
  question for the project owner:** is a second, structurally different multi-instance model
  actually wanted, given a working one already exists — or is this intentionally out of scope?
- **`opt_arg`'s dead `active` property — S/M.** `memory_space`'s silent-ignore sibling: `active`
  (a Fortran logical expression for conditional variable presence) is already a real
  `ArgumentOp` property (`ccpp.py`, `opt_prop_def(StringAttr)`) — parsed into IR, but zero passes
  ever read it. Likely reuses the existing `present()`-guard pattern already built for promoted
  optional args (Phase 1/2 of `test_optional_args.py`) rather than needing a new mechanism.
  Separately, S: add test coverage for optional args at `_timestep_init`/`_timestep_final` (not
  just `_run`) and optional+unit-conversion combined — likely already work today, just untested.
- **`advection`'s error-path bonus, found while confirming the core suite was a duplicate — S.**
  Real capgen-v1 has a deliberate negative test (`dlc_liq`/`cld_suite_error.xml`): declaring a
  `ccpp_constituent_properties_t`-typed arg outside the register phase must error. Unverified
  whether xdsl-ccpp's own constituent-registration code (`constituent_cap.py`) validates this at
  all today, or would silently accept/mishandle it. Small, self-contained check-and-raise if
  missing, matching this session's established validation-gap pattern.

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
