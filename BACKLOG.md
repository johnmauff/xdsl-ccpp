# Current Plan: `ccpp_cap.py` Refactor Backlog

Open items only. For the full narrative behind any item (why, how, what was
tried), see the `L<n>` pointer into `CHANGELOG.md` (line
numbers as of the split, 2026-09-29 — will drift as that file is edited; if
a number looks wrong, search for the quoted lead-in text instead, same
convention the archive's own Index already uses). Historical/completed
work — the full six-phase decomposition, Phase 7, every ✅ backlog item, and
the codebase complexity/duplication audit — lives only in the archive now.

Every item below carries a stable ID (a short kebab-case slug in
backticks, e.g. `` `hle-vocab-retire` ``, not a plain integer — integers
were found to reshuffle depending on how the list gets presented/derived).
Where an item already had an established numeric identity elsewhere in the
repo/history (`Task #NN`, `TDB-NNN`), the slug incorporates it (e.g.
`task70-arraysection`) or the original ID is kept as-is (`tdb-001`). Use
these IDs, not position in the list, when referring to an item across
sessions.

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
| `task65-interstitial-tests` | Task #65 (downgraded, 2026-08-20): DDT-typed interstitial-declaration test coverage; non-`real` interstitial-array test coverage | Small, no design work — opportunistic test-writing only. The other 2 sub-items (cross-phase `already_scheduled_allocs` unification; cross-phase ordering validation) are deferred indefinitely, folded into task #61, no open action | L5326 |
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
| `table-props-module-name` | `[ccpp-table-properties]`'s `module_name` override unsupported | S | L5955 |
| `type-control-gap` | `type = control` (capgen-v1) has no xdsl-ccpp equivalent | Modeling gap, currently inconsequential | L5974 |
| `suite-state-full-match` | Full capgen-v1 `ccpp_suite_state` match (integer-enum allocatable array + dedicated alloc/dealloc subroutines) | L; was deferred until after task #28 — task #28's Stages 1-4 are now done (archive L6148), so this is unblocked | L6148 |
| `task70-arraysection` | Task #70: consolidate `ArraySectionOp` into `RankReducingSliceOp` | M, real refactor — `ArraySectionOp` is actively used across 5 files including the highest-risk dispatch code in the repo, not dead code | L6593 |
| `task71-validate-fir` | Task #71: decide fate of `ccpp_validate_fir.py` vs `ccpp_validate_source.py --backend flang` | S-M — strong evidence of redundancy, but needs a real diff + a `DEVELOPERS.md` update decision, not a same-sitting deletion | L6593 |

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

This closes out two older, related gaps merged in from
`capgen_v1_parity_backlog.md` (now archived in CHANGELOG.md): its "No
`CCPPError`-equivalent exception type" complaint is exactly what
`CcppDslError` above fixes, and its "multi-step manual pipeline
(`run_frontend` -> `run_opt` -> `split_fortran_output` -> ...) vs.
capgen-v1's single `capgen()` call" ergonomics note (CHANGELOG.md L8267) is
the same convenience-wrapper idea as the scope below — not tracked as a
separate item.

- `dsl-inprocess-api` —
  **Scope**: design and implement a return value for `ccppMain().run()` (or
  a thin wrapper) that hands back the in-memory resolved-variable data
  (and whatever else a caller like CAM-SIMA's `resolved_var_xdsl_ccpp.py`
  adapter currently has to reconstruct from JSON) as real Python objects,
  as an alternative to writing the JSON file. A single-call convenience
  wrapper around the current `run_frontend` -> `run_opt` ->
  `split_fortran_output` manual pipeline is part of the same scope.
- **Not started.** Not obviously a pure win — needs its own design pass to
  decide the shape of the returned object and whether the JSON artifact
  stays as the CLI-facing contract with the object return as an
  in-process-only addition, or something else. Size TBD.
- `optionsdb-list-format` — Also still open: `options_db` takes comma-joined **strings** for
  file-list arguments where capgen-v1 takes plain Python lists — a real
  format mismatch (CHANGELOG.md L8267), separate from the above.

## From `capgen_v1_parity_backlog.md` (merged 2026-09-29)

Two workstreams: the `ResolvedVar`/`cam_autogen.py` integration
(Workstreams 1, Stages 0-9, all done) and a DDT-redefinition bug fix
(Workstream 2, resolved). Nearly everything in that doc turned out to
already be done or superseded by this session's own extensive
`/cam-sima-regression` testing — see CHANGELOG.md's merged section for the
full history. Two small items survive as genuinely open:

- `ddt-redef-filecheck` — Add a permanent filecheck regression test under `tests/filecheck/`
  covering host-cap + suite-cap + constituent-variable generation
  together, so the DDT-redefinition bug (Workstream 2) doesn't silently
  regress. (CHANGELOG.md L8254)
- `constituent-ddt-stub-unify` — Consider whether `_generate_constituent_api`'s hardcoded DDT stub list
  should eventually be unified with the generic `ddt_source_module`
  mechanism rather than living as a second parallel path — today's fix
  makes the two paths coexist safely, it doesn't merge them. (CHANGELOG.md
  L8254)

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

## Technical debt (merged from `technical_debt.md` and
`ir_cleanup_and_lifecycle_dedup_plan.md`, 2026-09-29)

All three items confirmed still open and accurate as of the 2026-09-29
merge (verified directly against current source, not just carried over).
**Update 2026-09-30**: `TDB-002` is now resolved (see below); `TDB-001`
and `TDB-003` remain open; a new item, `TDB-004`, was added, scoped to
follow `TDB-003`. The `TDB-NNN` IDs are kept as-is (including for the
now-resolved `TDB-002`) since source comments in `ccpp_cap.py` and
elsewhere already cite them by number.

### TDB-001: Constituent API always generated for CAM host builds

ID: `tdb-001`

**File**: `xdsl_ccpp/transforms/ccpp_cap.py`, `_generate_ccpp_cap_module`
(the `or self.cam_host` condition gating the call to
`_generate_constituent_api`). **Added 2026-09-06.**

`_generate_constituent_api` is called unconditionally whenever
`cam_host=True`, even for suites with no CCPP constituents at all (no
dynamic arrays, no fixed-advected constituents, no scratch vars, no
`number_of_ccpp_constituents` references) — because CAM-SIMA's
`write_init_files.py` unconditionally imports `cam_constituents_array`/
`cam_model_const_properties` from `cam_ccpp_cap` and calls them in
`physics_read_data`/`physics_check_data`, regardless of whether the suite
actually has constituents (written to match capgen's own always-generate
behavior). Rather than make `write_init_files.py` constituent-aware
(non-trivial surgery, in CAM-SIMA's own repo), xdsl_ccpp was patched to
always emit the constituent API for CAM builds, producing empty stubs
when the suite has none.

**The right fix**: make `write_init_files.py` constituent-aware — gate
the `cam_constituents_array`/`cam_model_const_properties` `USE` imports,
call sites, and local declarations on `bool(constituent_set)` /
`bool(registry_constituents)`. Would let xdsl_ccpp revert the `cam_host`
guard and keep `_generate_constituent_api` conditional on actual
constituent presence.

**Risk of leaving as-is**: low. Generated empty stubs are harmless at
runtime (empty arrays, no-op register calls) — the only cost is a small
amount of dead code in `cam_ccpp_cap.F90` for constituent-free suites.

### TDB-002: Constituent API generation uses raw Fortran string assembly — RESOLVED

ID: `tdb-002`

**RESOLVED 2026-09-30.** All 10 `constituent_cap.py` subroutines converted
from raw-string `RawFortranLinesOp` blobs to typed IR (7 new ops designed;
`ScopedBlockOp` got its first real usage anywhere in the codebase;
`ConstituentApiOp`, the op this item's original text was written against,
removed as dead code — superseded by `CamHostConstituentApiOp`/
`NonCamHostConstituentApiOp` since commit `125cfe2`, which the original
scoping hadn't caught up to). Bonus: closed a real coverage gap with a new
FileCheck golden for the multi-instance derived-type path. Verified with
the full local suite (714 passed, 1 xfailed) and a final
`/cam-sima-regression` run (`xdsl44g`): 30/31 pass, 1 known pre-existing
unrelated failure. A few deliberate one-off text leaves remain (plain
assignments, a `write()` call, `#ifdef` directive blocks) — not a scoping
miss; closing those, plus the deeper issue that even the now-typed ops
still carry raw Fortran-syntax *expression text*, is `TDB-004` (sequenced
after `TDB-003`). Full staged history archived in `CHANGELOG.md` L9016.

### TDB-003: `CHostCapOp`/`cpp_interop.py` still carries raw C++/Fortran text — IN PROGRESS

ID: `tdb-003`

**File**: `xdsl_ccpp/dialects/ccpp_utils.py` (`CHostCapOp`),
`xdsl_ccpp/transforms/cpp_interop.py`. **Added 2026-09-29** (PR 5 of
`ir_cleanup_and_lifecycle_dedup_plan.md`, not tracked elsewhere before
this merge).

Staged 3 ways (Stage 1: pure-Fortran `_build_chost_ftn_text`; Stage 2:
`_build_chost_cpp_text`, the C header; Stage 3: `_build_chost_wrapper_text`,
the genuine-C++ ergonomics wrapper — the real design risk, no existing op
precedent). Full plan: `ir_cleanup_and_lifecycle_dedup_plan.md`-successor
plan, `i-need-you-help-typed-petal.md`.

**Stage 1 — DONE (2026-09-30).** `CHostCapOp`'s container shape decided:
one op, `ftn_body` (region, replacing `ftn_text: StringAttr`) +
`cpp_text`/`wrapper_text` staying `StringAttr` until Stages 2/3 (deferred
deliberately — `print_cpp_header.py` has no op-dispatch printer yet, so
region-izing those now would mean inventing that infrastructure
speculatively). New ops: `AssignOp`, `BindCSubroutineOp` (covers both
`subroutine` and `function ... result(...) bind(C, ...)` shapes),
`CToFortranStringCopyOp`/`FortranToCStringCopyOp`, `CallStatementOp` +
shared `_wrap_paren_list` column-wrap helper (unifying what
`_emit_subr_header`/`_emit_call` each hand-rolled separately — both now
removed as dead code). `_chost_fn_contexts`'s 3x-independent call (one per
builder, on identical inputs) folded into a single shared call in
`_generate_chost_cap_module`. `_build_chost_ftn_text` (350 lines) fully
converted to typed ops; declaration-only boilerplate (module/use/private/
public/BIND(C) struct def) stays a single `RawFortranLinesOp`, matching
the existing convention that declarations stay opaque text everywhere else
in this codebase. Verified: full local suite green (714 passed, 1
xfailed) throughout; `chost-r3-ftn.mlir` re-confirmed XFAIL for its same
pre-existing documented reason; affected FileCheck goldens regenerated and
reviewed (one, `chost-f32-ftn.mlir`, hand-fixed after the auto-updater
blew its targeted/commented structure into an undifferentiated exhaustive
dump); GitHub CI green; `/cam-sima-regression` run `xdsl45g`: 28/31 pass +
1 known pre-existing unrelated failure (2 cases were still in queue at
last check, unrelated to the chost path).

**Stage 2 — DONE (2026-09-30).** `CHostCapOp`'s `cpp_text: StringAttr` →
`cpp_body` (region); `wrapper_text` stays `StringAttr` until Stage 3. New
ops: `CppIncludeOp`, `ExternCGuardOp`, `CFunctionSigOp` (covers both C
prototypes now and, for Stage 3, inline C++ definitions), `CppFieldDeclOp`,
`CppStructDefOp` (POD-only for now — Stage 3 is expected to add an
optional `methods` region for the non-POD cases). `print_cpp_header.py`
gained its own op-dispatch printer (`_print_cpp_op`, mirroring
`print_ftn.py`'s `print_op`) plus a shared `_CPP_HEADER_BANNER` constant,
which also let `_emit_cap_header` (the regular Fortran-host
`ccpp_cap.h` path) drop its own hand-duplicated copy of the same guard/
banner text. `_build_chost_cpp_text` (77 lines) converted to typed ops.
Verified: full local suite green (714 passed, 1 xfailed); notably **zero**
goldens needed regeneration — output matched the pre-existing absolute-
indentation format exactly (no prior descend()-based convention to
normalize toward here, unlike Stage 1); constituent-struct/prototype path
manually verified via `constprop` (no existing golden covers it, same gap
as Stage 1's own constituent-query-function path).

**Deferred out of Stage 2, deliberately**: the original plan for this
stage also called for unifying `_chost_cpp_type` (`cpp_interop.py`, keyed
off a resolved `ChostArgInfo` dict) with `_cpp_type` (`print_cpp_header.py`,
keyed off an MLIR type) into one shared type-decision table. On inspection
this is riskier than scoped — the two key off structurally different
inputs with several independently-evolved edge cases (`is_ncol`/`is_nz`
special-casing in the chost version; rank-0 reals always being
`value, intent(in)` in the generated Fortran regardless of the scheme's
actual intent) that would need careful reconciliation to merge safely.
Left undone rather than rushed; a good small follow-up item once Stage 3
needs its own closer look at `_chost_cpp_type` anyway (Stage 3's
`_build_chost_wrapper_text` is `_chost_cpp_type`'s other real caller).

Also note (not a regression, no golden covers it either way): reusing the
same generic `CFunctionSigOp` printer for the two constituent-query
prototypes (`nconstituents`/`get_constituent_info`) instead of the
original's hand-written single-line declarations produces a slightly
different but valid whitespace layout — a deliberate normalization, same
category as Stage 1's own untested-path reformatting.

**Stage 3 — implementation complete, local verification green
(2026-09-30); awaiting GitHub CI confirmation before closing TDB-003 out.**
`CHostCapOp`'s `wrapper_text: StringAttr` → `wrapper_body` (region),
completing the container-shape migration for all three outputs. New ops:
`CppNamespaceOp`, `CppCallStatementOp` (C++ sibling of `CallStatementOp`,
reusing `print_ftn.py`'s `_wrap_paren_list` — generalized and renamed
`wrap_paren_list` with a `cont_marker` param so it's no longer
Fortran-only), `CppConstructorOp`, `CppBraceInitCallOp`, `RawCppLinesOp`
(permanent escape hatch, C++ sibling of `RawFortranLinesOp`, also used as
the staging vehicle). Extended: `CFunctionSigOp` gained `is_const`;
`CppFieldDeclOp` gained `init_expr`/`type_width` (its padding formula
changed to pad-plus-mandatory-space, verified byte-identical to Stage 2's
own 3 actual type strings — Stage 2's old pad-only formula had a latent
bug for any type name ≥9 chars, never triggered before Stage 3); `CppStructDefOp`
gained `methods`/`private_members` regions with real `is_pod` enforcement
(raises if either is non-empty while `is_pod=True`).

Converted in 6 steps per the dedicated Stage 3 plan
(`i-need-you-help-typed-petal.md`): container-shape migration → peel
banner/namespace → pilot (`Status` struct + constituent-query functions +
one zero-arg lifecycle) → generalize to all per-lifecycle functions →
`State` struct/constructor/`allocate()`/overloads → final review. Found
and fixed 4 real bugs along the way, all caught by local verification
before reaching any golden: C++ inline functions need `()` not `(void)`
for zero params (was C-prototype-only convention); `CppCallStatementOp`
was missing its leading indent; `CFunctionSigOp`'s non-empty-body branch
had a spurious trailing blank line (double-blank between sections); and
`_print_cpp_params` needs to key single-line-vs-multiline off `is_inline`,
not param count (the 3-param loop-bounds overload signature needed
single-line too). The deliberate column-budget-vs-chunks-of-4 call-wrap
normalization (same kind already established in Stages 1/2) is the one
expected, intentional output difference from the original.

Verified: full local suite green (714 passed, 1 xfailed) at every step;
`g++ -std=c++17 -Wall -Wextra` compile checks at every step (approved for
this stage specifically, not a standing practice) — zero warnings
throughout, including linking and exercising the actual `State`/
`allocate()`/`run()` API surface for `kessler` and `tinyddt`, and the
constituent-query path via `constprop`. The two wrapper goldens
(`kessler-chost-wrapper.mlir`, `tinyddt-chost-wrapper.mlir`) already pass
unmodified — their loose `CHECK:` substring matching tolerates the
call-wrap normalization — so left untouched rather than forced through
the auto-updater, which (same issue hit in Stage 1) blows sparse,
richly-commented goldens into undifferentiated exhaustive dumps.

**Next**: push for GitHub CI (`tests.yml` + `compile-tests-cmake.yml`,
leaning on the latter harder per the original plan, same reasoning as the
local `g++` checks above) — no `/cam-sima-regression` run, the chost path
is unreachable from any CAM-SIMA case. Once CI is green, close TDB-003 out
fully: move this full history to `CHANGELOG.md`, shrink this entry to a
short RESOLVED pointer (do not repeat the earlier mistake of leaving the
full writeup here), and open the two follow-on items TDB-003 itself
flagged as explicitly out of scope: the `_chost_cpp_type`/`_cpp_type`
unification deferred from Stage 2, and the two-subprocess-pipeline
inefficiency (`ccpp_dsl.py` running `print_ftn`/`print_cpp_header` as
fully separate passes, each re-deriving `CHostCapOp` from scratch) noted
in this item's own original scoping section above.

**Risk of leaving as-is**: low short-term, same shape as TDB-002 — correct
output today, cost is architectural (no IR-level analysis/GPU-pass
coverage of chost-generated code, drift risk between the two printers'
independent string logic).

### TDB-004: No language-neutral expression IR — blocks real multi-language support

ID: `tdb-004`

**File**: repo-wide — `xdsl_ccpp/dialects/ccpp_utils.py` (most op
definitions), `xdsl_ccpp/transforms/{suite_cap,run_dispatch,constituent_cap,
lifecycle_cap,cpp_interop}.py`. **Added 2026-09-30**, surfaced while
implementing TDB-002 and discussed directly with the project owner, whose
long-term goal is full multi-language support in xdsl_ccpp (both C++ as a
host model and C++ as a scheme implementation — see the "C++ host + C++
scheme track" priorities discussed this session).

**The gap, precisely**: TDB-002 converted `constituent_cap.py`'s raw
Fortran-string *statement bodies* into typed ops (`IfThenOp`,
`DdtMethodCallOp`, `PointerAssignOp`, etc.), so a second-language printer
could in principle decide how to render an `if`/`then`/`else`, a type-bound
call, or a pointer assignment in its own target syntax. But confirmed
directly: every one of those ops' *expression-bearing* properties —
`IfThenOp.condition_expr`, `ActiveCheckOp`/`PresentCheckOp`'s condition
text, `ErrorGuardOp.errmsg_text`, `DdtMethodCallOp.args`/`.kwargs`,
`PointerAssignOp.rhs_expr`, `AllocateOp.dims`, `ModuleVarOp.init_value` —
still hold raw Fortran-syntax *text* (`.or.`/`/=` operators, `errcode=errcode`
keyword-arg syntax, `[ character(len=8) :: 'foo' ]` array-constructor
literals, `.true.`/`''` literal spellings). This isn't specific to
`constituent_cap.py` or to TDB-002's new ops — it's the same pattern in
every op this codebase already treats as "converted" (`LazyAllocOp`,
`SafeDeallocOp`, `ArraySectionOp`'s bounds, `CamDirectCallOp`'s args, and
so on, going back to the original "Eliminate text strings" work). A
hypothetical C++ printer can't render `.or.` as `||` or `.true.` as `true`
without re-parsing Fortran syntax out of a string first — which defeats
the entire purpose of routing everything through a printer abstraction.
So today's IR genericizes *statement shape* (if/else, do-loop, call) but
not *expression content* — and expression content is exactly what differs
between Fortran and any other target language.

**Why this is the real prerequisite for the stated long-term goal**: the
multi-language direction this session settled on (TDB-002 → TDB-003 →
eventually a second-language printer) cannot actually reach a second
language until expression content stops being baked into the IR as
Fortran-syntax text at construction time. TDB-002/TDB-003 are necessary
groundwork (they at least stop hand-building whole statements as joined
strings) but not sufficient on their own — flagged here explicitly so the
gap doesn't get rediscovered as a surprise after TDB-003 lands.

**The right fix, staged**:

1. **Small, immediate, low-risk cleanup piece** (can land on its own,
   doesn't depend on anything else here): `constituent_cap.py` still has a
   handful of genuine one-off `RawFortranLinesOp` leaves left after TDB-002
   (plain scalar assignments like `errflg = 0`; one `write(errmsg, ...)`
   call; a few `#ifdef USE_GPU`/`!$acc` directive blocks; `allocate(x,
   stat=errcode)`'s STAT-clause form, which doesn't match `AllocateOp`'s
   plain shape). Add three small dedicated ops for these (`AssignOp`,
   `WriteStmtOp`, `PreprocDirectiveOp`), matching TDB-002's established
   op-design conventions exactly. This doesn't solve the expression-content
   problem (these ops would still hold Fortran-syntax text for their RHS/
   format-string content) but it does get `constituent_cap.py` itself to
   zero raw-string leaves, and gives 3 more small, real precedents before
   attempting the bigger design below.
2. **Design a small core expression-IR vocabulary**: literal ops
   (int/bool/string), a variable/member-reference op (covers both Fortran's
   `%` and a future C++ printer's `.`/`->`), a binary/unary-op op
   (parameterized by a language-neutral operator kind enum — `eq`/`ne`/
   `and`/`or`/`add`/... — not a pre-rendered token), a call-as-expression
   op (distinct from today's statement-level call ops), and an
   array-constructor op. Deliberately small and proven on one file first
   rather than designed in the abstract for the whole codebase at once.
3. **Retrofit one already-converted file's expression properties** to use
   the new vocabulary instead of `StringAttr`/`ArrayAttr[StringAttr]` —
   `constituent_cap.py` is the natural pilot (freshly converted, well
   covered by both unit tests and FileCheck goldens, including the new
   multi-instance golden). Expect this to reveal real gaps in the Stage 2
   vocabulary; iterate.
4. **Prove the abstraction actually holds** before committing to the full
   retrofit: sketch (doesn't need to be production-quality) how a second
   printer would render the same expression IR in a different target
   syntax. This is the real validation step — if the vocabulary can't
   cleanly support even a sketch of a second printer, stage 2's design
   needs another pass before stage 5 below begins.
5. **Propagate incrementally, file by file**, not a single rewrite:
   `suite_cap.py`, `run_dispatch.py`, `lifecycle_cap.py`, and (once TDB-003
   lands) `cpp_interop.py`'s own new ops all need the same retrofit
   eventually. Each file's own existing test/golden coverage is the
   regression net, same discipline as TDB-002.

**Sequencing: after TDB-003, per project-owner decision.** TDB-003
(`cpp_interop.py`'s own de-stringification, using the same statement-shape-
only pattern TDB-002 just established) gives a second, independent real
data point for exactly which expression-text shapes recur across the
codebase — Fortran-only patterns from `constituent_cap.py` alone risk
under-designing the vocabulary for C++ interop's own needs. Doing this
first would also further delay TDB-003's already-scoped work for a
design question TDB-003 doesn't itself require answered.

**Effort**: large — likely the single biggest item in this backlog,
bigger than TDB-002 and TDB-003 combined, given its breadth (every
expression-bearing property on every op in `ccpp_utils.py`, across five
transform files). Treat stages 1-4 above as a multi-week design-and-pilot
phase on their own, with stage 5's full propagation as further,
separately-scoped follow-on work per file, not one PR.

**Risk of leaving as-is**: unlike TDB-002/TDB-003 ("low short-term, correct
output today"), this one is different in kind — it's not a code-quality
cost that accumulates quietly, it's a hard blocker on the stated
multi-language goal. No second-language printer is achievable at all
until this lands, regardless of how much statement-shape conversion work
(TDB-002, TDB-003) happens first.

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
reference, not backlog noise). These 4 items are its only open ones as
of 2026-09-29 (10 of its 14 numbered items are already resolved); pointer
entries here so they surface in a backlog sweep too.

- `chost-rank3-bindc` — **Rank > 2 arrays, plain `--bind-c` path (no chost layer)** — a
  suspected assumed-size→assumed-shape rank mismatch between
  `ccpp_cap.py`'s flat `flux(*)` declaration and the suite cap's
  assumed-shape `(:,:,:)` dummy. Confirmed still unverified against a real
  Fortran compiler (the `chost-r3-ftn.mlir` golden test is still `XFAIL`ed
  for exactly this reason). This session ran on Derecho with real
  compilers throughout — worth actually verifying now rather than staying
  theoretical. `multilanguage_limitations.md` §5.
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
