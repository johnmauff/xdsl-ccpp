# Current Plan: `ccpp_cap.py` Refactor Backlog

Open items only. For the full narrative behind any item (why, how, what was
tried), see the `L<n>` pointer into `CHANGELOG.md` (line
numbers as of the split, 2026-09-29 — will drift as that file is edited; if
a number looks wrong, search for the quoted lead-in text instead, same
convention the archive's own Index already uses). Historical/completed
work — the full six-phase decomposition, Phase 7, every ✅ backlog item, and
the codebase complexity/duplication audit — lives only in the archive now.

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

| Item | Notes | Archive |
|---|---|---|
| Follow-up items spawned by `constituents_dim`: single-source migration for `advection`; naming-convention audit | | L3305 |
| Task #65 (downgraded, 2026-08-20): DDT-typed interstitial-declaration test coverage; non-`real` interstitial-array test coverage | Small, no design work — opportunistic test-writing only. The other 2 sub-items (cross-phase `already_scheduled_allocs` unification; cross-phase ordering validation) are deferred indefinitely, folded into task #61, no open action | L5326 |
| Metadata dependency-manifest automation for CMake (Tier 2 of dependency tracking — Tier 1 parse/IR-forward is done) | Size TBD, needs its own design pass; overlaps with the CMake-configure-time item below | L5465 |
| `examples/ddthost` has fallen behind `examples/capgen` (missing `kind_spec`, `interstitial_var`, rank re-sync, `temp_adjust_register`) | Scoped (2026-08-24): M, 1 prerequisite + 2 stages; real cross-file coupling (`temp_calc_adjust`+`temp_adjust` share a standard_name, must land together). Not started; not a CAM-SIMA blocker | L5531 |
| Retire the legacy `horizontal_loop_extent` vocabulary — actual code-path deletion | Examples migrated (2026-07-27) and `--legacy-mode` gate added (2026-08-13) already; only the deletion itself remains open | L5679 |
| Consolidate `horizontal_loop_extent`'s duplicate chunking code (`suite_cap.py`/`run_dispatch.py`) | Investigated 2026-08-24: 2 of 4 files already unified; the other 2 are real, still-used `--legacy-mode` code. Deliberately deferred until a CAM-SIMA-backed fixture exists to test a consolidation against | L5698 |
| Stage 5 of task #28: match capgen-v1's `''`/`'all'`-group fan-out call shape exactly | S-M, cosmetic, blocks nothing | L4820 |
| Task #11 items 1/3: `number_of_openmp_threads` rename; `registered_dimensions.py`'s `thread_number` scalar-index mechanism | Scoped 2026-08-20, not started; item 3 is the real one (M-L, needs its own test fixture) | L4835 |

## Other flagged issues

| Item | Notes | Archive |
|---|---|---|
| `generateSchemeSubroutineCallOps`'s errflg-guard SSA def-use order | S, cosmetic | L5825 |
| Move examples' build system from per-example Makefiles to CMake | Size TBD | L5856 |
| CMake cap generation runs at configure time — every example regenerates on every CI job | Size TBD | L6059 |
| `[ccpp-table-properties]`'s `module_name` override unsupported | S | L5955 |
| `type = control` (capgen-v1) has no xdsl-ccpp equivalent | Modeling gap, currently inconsequential | L5974 |
| Full capgen-v1 `ccpp_suite_state` match (integer-enum allocatable array + dedicated alloc/dealloc subroutines) | L; was deferred until after task #28 — task #28's Stages 1-4 are now done (archive L6148), so this is unblocked | L6148 |
| Task #70: consolidate `ArraySectionOp` into `RankReducingSliceOp` | M, real refactor — `ArraySectionOp` is actively used across 5 files including the highest-risk dispatch code in the repo, not dead code | L6593 |
| Task #71: decide fate of `ccpp_validate_fir.py` vs `ccpp_validate_source.py --backend flang` | S-M — strong evidence of redundancy, but needs a real diff + a `DEVELOPERS.md` update decision, not a same-sitting deletion | L6593 |

## New: in-process, object-returning API for `ccpp_dsl.py`

Added 2026-09-29, postdates the archive narrative entirely. `ccpp_dsl.py`'s
pipeline recently stopped calling `sys.exit()` internally (`CcppDslError`
now carries every failure up to `main()`, the only place that still exits
the process; currently uncommitted on this repo's `main` branch). That
makes `ccppMain().run()` safely callable in-process, but it still returns
nothing useful on success — a caller like CAM-SIMA's `cam_autogen.py` still
has to invoke it as a subprocess and re-derive everything it needs
(resolved vars, etc.) from the `--emit-resolved-vars` JSON artifact on
disk, rather than getting live Python objects back directly.

- **Scope**: design and implement a return value for `ccppMain().run()` (or
  a thin wrapper) that hands back the in-memory resolved-variable data
  (and whatever else a caller like CAM-SIMA's `resolved_var_xdsl_ccpp.py`
  adapter currently has to reconstruct from JSON) as real Python objects,
  as an alternative to writing the JSON file.
- **Not started.** Not obviously a pure win — needs its own design pass to
  decide the shape of the returned object and whether the JSON artifact
  stays as the CLI-facing contract with the object return as an
  in-process-only addition, or something else. Size TBD.
