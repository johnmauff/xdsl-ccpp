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
| `hle-vocab-retire` | Retire the legacy `horizontal_loop_extent` vocabulary — actual code-path deletion | Examples migrated (2026-07-27) and `--legacy-mode` gate added (2026-08-13) already; only the deletion itself remains open. Confirmed 2026-09-29: `ccpp.py`'s `is_legacy_mode()` gate is still called, path not yet deleted | L5679 |
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
| `errflg-guard-order` | `generateSchemeSubroutineCallOps`'s errflg-guard SSA def-use order | S, cosmetic | L5825 |
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
them entirely.

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

`camsima-untested-confirm` — One item **probably** also superseded, flagging rather than closing
outright since it wasn't one of the three items already confirmed:
nested suites, subcycles, multi-suite builds, and GPU/`memory_space`
directives "in an actual CAM-SIMA context," and real production physics
suites from `NCAR/atmospheric_physics`, were marked "Untested" as of
2026-08-24 (CHANGELOG.md L8293). Given the GPU kessler/MPAS/se_cslam_gpu
work and the `/cam-sima-regression` xdsl4x suite runs done since, this
looks very likely covered now — worth a quick confirm-and-close rather
than treating as still open.

## Technical debt (merged from `technical_debt.md` and
`ir_cleanup_and_lifecycle_dedup_plan.md`, 2026-09-29)

All three items confirmed still open and accurate as of this merge
(verified directly against current source, not just carried over). The
`TDB-NNN` IDs are kept as-is since source comments in `ccpp_cap.py` and
`constituent_cap.py` already cite TDB-001/TDB-002 by number.

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

### TDB-002: Constituent API generation uses raw Fortran string assembly

ID: `tdb-002`

**File**: `xdsl_ccpp/transforms/constituent_cap.py`. **Added 2026-09-06;
extended 2026-09-15; narrowed 2026-09-29.**

All constituent API subroutines (both the generic and `cam_host` paths)
are built as raw Python f-strings stored in a `ConstituentApiOp(body=
StringAttr(...))` / per-function `RawFortranLinesOp` bodies and emitted
verbatim by `print_ftn.py`, instead of going through the typed MLIR IR
(`func.FuncOp`/`call.CallOp`/SSA values) the rest of xdsl_ccpp uses to
represent Fortran semantics and derive text from. Consequences: no
IR-level analysis/transformation can touch these subroutines;
line-length limits, continuation lines, USE deduplication, and
indentation are all managed by hand in Python instead of by the emitter;
extending the API means editing f-string templates instead of composing
IR ops.

**Narrowed 2026-09-29**: this item originally also named `ccpp_cap.py`'s
`_generate_cam_lifecycle_wrappers` (the `cam_ccpp_physics_*` wrappers) as
using the same raw-string pattern. Confirmed that's no longer true —
commit `125cfe2` ("Eliminate text strings phase 1", 2026-09-07, the day
after this item was first added) rewrote it to return real `func.FuncOp`
IR (`return wrappers, list(_seen_globals.values())`), matching
`lifecycle_duplication_report.md`'s Finding 2 "Phase B" proposal exactly
(that report, and its other 4 findings, are now fully resolved — deleted
2026-09-29, nothing else survived as open). Only `constituent_cap.py`
remains on the raw-string pattern.

**The right fix, staged** (merged in from `ir_cleanup_and_lifecycle_dedup_plan.md`'s
PR 3, 2026-09-29 — that plan's PRs 1/2/4 are done, see the "Narrowed"
note above; PR 3 is this item; PR 5 is TDB-003 below):

- **Stage A — declarations to `ModuleVarOp`.** All 7 declaration types
  currently built as raw strings in `type_defs_lines` become `ModuleVarOp`
  instances, using the `is_pointer`/`is_target` boolean properties (already
  landed). E.g. `real(kind=kind_phys), allocatable, target ::
  lc_const_tend(:,:,:)` becomes `ModuleVarOp("lc_const_tend", "real",
  kind="kind_phys", is_target=True, rank=3)`. Delete `type_defs_lines`,
  `type_defs_text`, and the `type_defs=` argument to `ConstituentApiOp`.
- **Stage B — new statement ops for subroutine bodies**, each following
  the `LazyAllocOp`/`SafeDeallocOp` pattern (typed properties, no
  hand-built Fortran outside the printer): `DeallocateIfOwnedOp(var)` →
  `if (allocated(x)) deallocate(x)`; `NullifyPointerOp(ptr)` →
  `nullify(x)`; `AllocateOp(var, shape_ops)` → `allocate(x(n, m, k))`;
  `ZeroFillOp(var)` → `x = 0.0_kind_phys`; `PointerSliceAssignOp(ptr,
  array, index_var)` → `ptr => arr(:, :, idx)`;
  `ConstituentIndexLookupOp(obj, std_name, idx_var, errflg)` → `call
  obj%const_index(idx, 'std_name', errcode=...)`; `ScopedBlockOp(locals,
  body: Region)` → `block; ...; end block`.
- **Stage C — `ConstituentApiOp.body` from `StringAttr` to a `Region`**
  containing one `ConstituentFunctionOp` per subroutine (each with its own
  Stage B body Region); `print_ftn.py` walks the Region instead of
  printing a blob. Do both parallel paths
  (`_generate_constituent_api_cam_host` and `_generate_constituent_api`)
  together, since they share the same op definitions. Gate Stage C on
  Stage A/B passing cleanly first.

Each new op: define in `ccpp_utils.py` with typed properties (a
`StringAttr` only for names/labels, never code fragments) → add exactly
one printer case in `print_ftn.py` (the only place that op's Fortran
syntax appears) → update the transform call site to build the op instead
of a string. Clean examples already in the codebase to follow:
single-statement ops `LazyAllocOp`/`SafeDeallocOp` (no Region, printer
does all the syntax); Region-body ops `PromotionLoopOp`/`SubcycleLoopOp`
(`body = region_def("single_block")`, builder takes `body_ops`, printer
walks children); conditional-body ops `PresentCheckOp`/`ActiveCheckOp`
(two named Regions, printer emits `if/else/end if`). Verify after each
converted site: full test suite + a CAM-SIMA regression run.

Estimated effort (from the source plan): ~2-3 weeks, the largest of the
still-open IR-cleanup items — two parallel ~970-line f-string-heavy
functions, ~9 subroutine bodies each.

**Risk of leaving as-is**: low short-term — the raw strings produce
correct Fortran and pass all tests; the cost accumulates as the
constituent API grows (each new subroutine/argument is more raw-string
bookkeeping). Confirmed still the only pattern in use as of the
2026-09-16 `cam_advected_constituents_array` addition (`aca_op`) — added
using the same `RawFortranLinesOp`-body pattern deliberately, by explicit
user decision, rather than partially refactoring one function in
isolation; this doesn't change the scope or urgency of the fix above.

### TDB-003: `CHostCapOp`/`cpp_interop.py` still carries raw C++/Fortran text

ID: `tdb-003`

**File**: `xdsl_ccpp/dialects/ccpp_utils.py` (`CHostCapOp`),
`xdsl_ccpp/transforms/cpp_interop.py`. **Added 2026-09-29** (PR 5 of
`ir_cleanup_and_lifecycle_dedup_plan.md`, not tracked elsewhere before
this merge).

`CHostCapOp` carries the complete generated Fortran module text
(`ftn_text`), matching C++ header text (`cpp_text`), and C++ ergonomics
wrapper text (`wrapper_text`) as three separate pre-built `StringAttr`
fields — confirmed still true (`xdsl_ccpp/dialects/ccpp_utils.py`'s
`CHostCapOp` definition). Largest of the remaining string-built bodies:
~734 lines across ~132 f-strings in `cpp_interop.py`. Generated by
`generate-ccpp-cap` when the host declares `language = "c++"`; consumed
verbatim by `print_ftn.py` (`ftn_text`) and `print_cpp_header.py`
(`cpp_text`/`wrapper_text` as separate `// FILE:` sections).

**The right fix**: deliberately not scoped in detail yet — the source
plan explicitly deferred this "until PRs 1-4 establish the patterns...
[requires] defining abstract ops that both the Fortran and C++ printers
can handle — a larger design discussion." PRs 1/2/4 are now done and TDB-002
above is the in-progress PR 3, so the patterns this needs (the Step
1/2/3 conversion methodology, the op-design precedents) now exist to
draw on, but the two-printer (`print_ftn.py` *and* `print_cpp_header.py`)
abstraction question itself is still open and needs its own design pass
before implementation starts.

**Risk of leaving as-is**: low short-term, same shape as TDB-002 — correct
output today, cost is architectural (no IR-level analysis/GPU-pass
coverage of chost-generated code, drift risk between the two printers'
independent string logic).

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
