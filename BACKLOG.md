# Current Plan: `ccpp_cap.py` Refactor Backlog

## Effort sizing reference

Informal day-based sizing for open backlog items, using an
engineer-days metric (constructed 2026-10-14 — no pre-existing formal
scale exists in this file; most items only ever carried free-text
effort adjectives). Size bands: XS <2 days, S 2-5, M 5-12, L 12-25,
XL 25-50, XXL 50+.

**Maintain this table whenever backlog items change**: remove a row
when its item resolves (it already gets a one-line resolved-note
elsewhere in this file, per the file's usual convention — don't
duplicate that detail here); add or correct a row when an item is
newly estimated or re-scoped. Treat every estimate here as a rough
planning aid, not a commitment — these are judgment calls, not
measured data, and will drift as items are reassessed.

| ID | Estimate | Size |
|---|---|---|
| `task28-stage5-fanout` | 1-3 days | S |
| `framework-src-resolution-unify` | 2-4 days | S |
| `eamxx-suite-coverage-checker` | 1-3 days | S |
| `chost-thread-safety` | 3-6 days | S-M |
| `eamxx-phaseB-deviceptr` | 3-6 days | S-M |
| `dup-suite-composition-dsl` | 4-8 days | M |
| `dup-scheme-family-gen` | 5-10 days | M |
| `chost-column-major` | 5-10 days | M |
| `cxx-scheme-no-e2e-test` | 5-10 days (open-ended scope) | M |
| `direct-fortran-ingest` | 6-10 days (now that Stage 1's extraction infrastructure has landed — see scoping below) | M |
| `eamxx-phaseA-variant-tag` | 8-15 days | M-L |
| `chost-gpu-memory` | 10-20 days | M-L |
| `suite-state-full-match` | (file's own prior note: "L") | L |
| `dup-meta-shadow-elim` — Stage 2 (full, real corpus) | 18-30 days | L |
| `composite-scheme` — Stage 2 follow-ons (core S2-0..S2-3 resolved; see the `composite-scheme` section and `composite_scheme_plan.md` §11) | package cap 2f: L; GPU residency across the boundary 2g: M; S2-4 deferred; GPU validation of the composite path and multi-package scoping not yet sized | L |
| `acc-meta-residency-check` | 2-4 days | S |
| `gpu-ci` | 10-20 days engineering (once a GPU runner is chosen -- the infrastructure decision itself is unquantifiable) | M-L |
| `gpu-conversion-residency` | 2-5 days (after `xdsl-upgrade`) | S-M |
| `xdsl-upgrade` | 2-5 days, depending on API changes | S-M |
| `scheme-io-capture-multi-call-site` | 1-3 days | XS-S |
| `scheme-io-capture-optional-args` | 2-4 days | S |
| `scheme-io-capture-fixture-storage` | 2-4 days engineering (once a storage approach is picked — the decision itself is unquantifiable) | S |
| `scheme-io-capture-staleness-check` | 3-6 days | S-M |
| `scheme-io-capture-netcdf` | 6-10 days | M |
| `scheme-io-capture-ctest-automation` | 6-10 days (genuinely new ground — this repo has zero precedent for a dynamically-registered CMake test today) | M |
| `call-site-arg-rebind` | 4-8 days | S-M |
| `process-split-region` | 15-25 days (CPU only; assumes `process-split-combine-policy` is settled first) | L |
| `process-split-gpu` | 10-20 days (on top of `process-split-region`) | M-L |
| `eamxx-phaseC-printer` | ~60-150+ days (high uncertainty — no existing analog/technique to build from, unlike every other item above) | XXL |

`hle-vocab-retire` is intentionally not sized — it's blocked on an
external dependency (CAM-SIMA migrating off `horizontal_loop_extent`
upstream), not a schedulable estimate. `process-split-combine-policy` is
likewise not sized — it's a science decision for the physics developers,
not engineering work.

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
| `hle-vocab-retire` | Retire the legacy `horizontal_loop_extent` vocabulary — actual code-path deletion | **Re-scoped 2026-09-29: deferred indefinitely, not a schedulable near-term task.** Examples migrated (2026-07-27) and `--legacy-mode` gate added (2026-08-13) already, but the 2026-07-27 premise that the legacy code path was "provably dead for every example" was found false by the 2026-08-24 investigation (real CAM-SIMA still declares `horizontal_loop_extent` directly, e.g. `temp_adjust.meta`/`temp_adjust_scalar.meta`) and reconfirmed by this session's own `/cam-sima-regression` run (`xdsl43g`) against real CAM-SIMA test cases. The code path must be retained for as long as `--legacy-mode` itself is supported — deletion is only safe once CAM-SIMA migrates off `horizontal_loop_extent` upstream, an external dependency this repo can't resolve on its own. `ccpp.py`'s `is_legacy_mode()` gate is still called; not scheduled for removal | L5679 |
| `task28-stage5-fanout` | Stage 5 of task #28: match capgen-v1's `''`/`'all'`-group fan-out call shape exactly | S-M, cosmetic, blocks nothing | L4820 |

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
| `suite-state-full-match` | Full capgen-v1 `ccpp_suite_state` match (integer-enum allocatable array + dedicated alloc/dealloc subroutines) | L; was deferred until after task #28 — task #28's Stages 1-4 are now done (archive L6148), so this is unblocked | L6148 |
| `framework-src-resolution-unify` | `ccpp_datatable.py` now has three separate, inconsistent code paths deciding where a "framework" Fortran file comes from | S; found 2026-10-18 while fixing a real cam-host build failure for scheme-io-capture (see below) | -- |
| `derecho-false-run-pass` | CIME reports `RUN PASS` for CAM runs that aborted; past regression counts were overstated | S (tooling done; upstream reports open); found 2026-10-21 (see below) | -- |
| `nvhpc-ncdata-roundoff` | 6 nvhpc FPHYStest cases abort on `ncdata_check` differences of rounding size | S; CAM-SIMA tolerance change made 2026-10-21 (uncommitted), awaiting an nvhpc regression run | -- |
| `microp-aero-bam-nvhpc-diffs` | nvhpc `microp_aero_bam` FPHYStest: large `ncdata_check` differences in number concentrations | M; xdsl55n, hidden by `derecho-false-run-pass` | -- |
| `pumas-ncdata-diffs` | `SMS_D` pumas FPHYStest aborts on small `ncdata_check` differences, gnu and nvhpc | S; its snapshot is intel-made, so likely rounding; covered by `cross_compiler_check_tolerance`, awaiting a run | -- |
| `cloud-water-ncdata-diffs` | gnu `cloud_water` FPHYStest: large `ncdata_check` differences | M; xdsl54g (only run with this case), hidden by `derecho-false-run-pass` | -- |
| `rrtmgp-gpu-partially-present` | nvhpc `rrtmgp_derecho_gpu` aborts: OpenACC `this%concs(:)` partially present on the device | M; xdsl50n and xdsl55n; the GPU RRTMGP pair has never run to completion | -- |

**ID: `xml-unknown-element-silent-drop`. Resolved (2026-10-20)** — `frontend/ccpp_xml.py` now raises `ValueError` for any unhandled suite-XML element (`<time_split>`/`<process_split>`/`<subcol>` or a typo); capgen-v1's own copy of the bug remains upstream.

**`framework-src-resolution-unify`** -- found while diagnosing a real
CAM-SIMA build failure (`Cannot open module file 'ccpp_capture_mod.mod'`)
for the `scheme-io-capture` backlog item: `ccpp_datatable.py` resolves
"which Fortran framework files does this build need, and from where" via
three separate mechanisms, not one. (1) The non-`cam_host` path
(`_resolve_framework_f90_files()`/`_FRAMEWORK_F90_FILES`) pulls
`ccpp_constituent_prop_mod.F90`/`ccpp_scheme_utils.F90` from xdsl_ccpp's
own internal `_FRAMEWORK_SRC_DIR` (`xdsl_ccpp/framework_src/`). (2) The
`cam_host=True` path (`_REAL_FRAMEWORK_F90_FILES`) pulls a *different*,
larger set of same-named files from an entirely separate, externally-
supplied `framework_src_dir` -- confirmed directly to be the real
upstream `NCAR/ccpp-framework` git submodule CAM-SIMA vendors, whose
`ccpp_scheme_utils.F90`/`ccpp_constituent_prop_mod.F90` have genuinely
different APIs from xdsl_ccpp's own same-named files (confirmed via a
real diff, not assumed). (3) A third, newly-added one-off block (this
session, fixing the build failure above) pulls `ccpp_capture_mod.F90`
specifically from `_FRAMEWORK_SRC_DIR` *even when* `cam_host=True`,
because that file is xdsl_ccpp's own and will never exist in the real
upstream submodule path (2) resolves against. Three lookups, two
different source directories, overlapping but not shared logic, and
every future xdsl_ccpp-only framework file added under `cam_host=True`
will need its own one-off block like (3) unless this is unified first.
A cleaner design: one table mapping each logical framework file to
*which* source directory it comes from (xdsl_ccpp's own package vs. the
real external submodule), resolved and validated by one function instead
of three. Confirmed real and current, not hypothetical -- this is what
made diagnosing the `scheme-io-capture` build failure take real
investigation instead of being obvious from reading the code once.

**`derecho-false-run-pass`** -- on Derecho, TestStatus says `RUN PASS` for a
CAM run that aborted after writing its first history file. Two causes:
`mpibind` (`/glade/u/apps/opt/mpitools/bin/mpibind`) runs `mpiexec` and then
a cleanup block as its last command, so its exit status is 0 even after
`MPI_Abort(1)`; and for a CAM-only case (`is_comp_standalone()`), CIME's
`_post_run_check` (`cime/CIME/case/case_run.py`) only requires a non-empty
`atm.log`. Found when s25e (package-cap RRTMGP) aborted at nstep 2 with
`RUN PASS`. Done: the `cam-sima-regression` and `cam-sima-rrtmgp` agents now
require `END OF MODEL RUN` in every `atm.log`. Applied retroactively:
xdsl50n 36 RUN PASS / 10 false, xdsl51g and xdsl52g 30 / 1, xdsl54g 30 / 2,
xdsl55n 35 / 9 (so xdsl55n was 26/37, not 35/37). Also done (CAM-SIMA's
`cime` checkout, uncommitted): `cs.status` re-checks every `RUN PASS` against
the newest run's logs and reports FAIL when none contains CIME's own
`TERMINATION_TEXT` (`cs_status.py`, `TestStatus.override_status`, 6 new
pytest tests); TestStatus files are not changed. Open: report `mpibind`'s
exit status to CISL; upstream the `cs.status` change, and fix the
standalone post-run check itself (`_post_run_check`), to ESMCI/cime. The
failures it hid are the five items below; none is new since xdsl50n.

**`nvhpc-ncdata-roundoff`** -- nvhpc FPHYStest cases `gw_cam4`, `hb_vdiff`,
`kessler`, `rk_stratiform`, `rrtmgp` and `uw_vdiff` abort on `ncdata_check`
with few points differing and maximum differences of 1.6e-16 to 1.6e-9
(xdsl55n; `gw_cam7` also in xdsl50n): compiler rounding against the gnu
snapshots. Change (CAM-SIMA, uncommitted): an include-only testmod
`cam/cross_compiler_check_tolerance`. Its `shell_commands` reads the
snapshot's compiler from the `ncdata_check` file name
(`..._derecho_gnu_after_...nc`; all are gnu except pumas, intel) and, only
when it differs from the case's `COMPILER`, sets `min_difference = 1e-8`
(the GPU testmods' value) in `user_nl_cam`, replacing the testmod's own value
(2e-15 or 1e-15) or adding one. Same compiler, or no compiler in the name:
unchanged. Included by the 18 CPU FPHYStest snapshot testmods. Close once an
nvhpc regression shows these six reach `END OF MODEL RUN`.

**`microp-aero-bam-nvhpc-diffs`** -- unlike the cases above, nvhpc
`microp_aero_bam` (xdsl55n) differs at every point in several number
concentrations (e.g. `dust_number_concentration_by_size_bin_for_contact_freezing`,
112752 points, max 5.98E+03). Step 1 passed `ncdata_check`; not
investigated.

**`pumas-ncdata-diffs`** -- `SMS_D_Ln2...cam-outfrq_pumas_derecho` aborts on
`ncdata_check` under gnu (xdsl51g, 52g, 54g) and nvhpc (xdsl50n, 55n):
hundreds to thousands of points, maximum differences up to 1.3e-10 (gnu,
e.g. `mass_number_concentration_of_cloud_ice_water_crystals...`). Its
snapshot is intel-made (`..._derecho_intel_after_c20260820.nc`), so gnu and
nvhpc both run against another compiler's results: likely rounding, now
covered by `cross_compiler_check_tolerance` (see `nvhpc-ncdata-roundoff`).
Close once gnu and nvhpc runs reach `END OF MODEL RUN`.

**`cloud-water-ncdata-diffs`** -- gnu `cam-outfrq_cloud_water_derecho`
(xdsl54g) differs at every point: `water_vapor_mixing_ratio...` max 2.0E-03,
`gridbox_total_cloud_liquid_water_mixing_ratio...` max 4.6. A real error.
Possibly related to `F2000_C7/cam7`'s missing `cloud_water_paths` physics
(deferred upstream); not investigated.

**`rrtmgp-gpu-partially-present`** -- nvhpc
`SMS_Ln2...cam-outfrq_rrtmgp_derecho_gpu` aborts in both nvhpc regressions
(xdsl50n, xdsl55n) with `variable in data clause is partially present on
the device: name=this%concs(:)` -- an OpenACC data-placement error on the
gas-concentrations object. The XML GPU RRTMGP case has therefore never run
to completion; earlier GPU RRTMGP pair results judged by TestStatus need
rechecking against `END OF MODEL RUN`.

**Resolved since last verification (2026-10-14), removed from the list
above**: `ccpp-validator-length-check` — new `ccpp_validate_driver` tool
reuses the existing `compare_arg_tables`/`Mismatch` comparator (not new
bespoke logic) to check a driver program's `errmsg`/`errflg` locals against
the CCPP protocol's fixed convention; confirmed it detects
`examples/instances/main.F90`'s known mismatch and nothing else across all
112 example `.F90` files; wired into the existing `tests.yml` CI job (a
sweep test, no new workflow needed) so a future regression is now caught
automatically. CHANGELOG.md L11656.

**Resolved since last verification (2026-10-13), removed from the list
above**: `constituents-dim-runtime-crash` — root cause was a nested,
re-entrant Fortran automatic-finalization cascade in the shared
`ccpp_hash_table.F90` framework module (not `constituents_dim`-specific
code), crashing only under Intel `ifx`; fixed with an explicit iterative
chain walk; full example matrix + `pytest` confirmed no regressions.
CHANGELOG.md L11602.

**Resolved since last verification (2026-10-13), removed from the list
above**: `ci-multi-compiler` — added Intel (every PR/push) and NVIDIA HPC
SDK (manual-trigger-only) CI coverage; PR #133 merged, real CI run
confirmed fully green. CHANGELOG.md L11491.

**Resolved since last verification (2026-10-13), removed from the list
above**: `cmake-configure-regen` — cap generation deferred to build time
via `add_custom_command`; verified via a real local build. CHANGELOG.md L11397.

**Resolved since last verification (2026-10-09), removed from the list
above**: `type-control-gap` — added a real `CONTROL` table type and
migrated all 25 affected `.meta` files; fixed a live host-matching bug
and 2 other real regressions found along the way; confirmed via
`/cam-sima-regression` (`xdsl51g`, gnu). CHANGELOG.md L10610.

**Resolved since last verification (2026-10-09), removed from the list
above**: `table-props-module-name` — `module_name` override now
supported; two latent bugs fixed, `var_compat`'s workaround reverted.
CHANGELOG.md L10474.

**Resolved since last verification (2026-10-09), removed from the list
above**: `dsl-inprocess-api` — `ccppMain.run()` now accepts `options_db`
and returns a `CcppDslResult` instead of `None`; also fixed a
Copilot-flagged normalization bug. CHANGELOG.md L10381.

**Resolved since last verification (2026-10-09), removed from the list
above**: `task70-arraysection` — `ArraySectionOp` consolidated into
`RankReducingSliceOp` and deleted; 3 real bugs found and fixed along the
way (not just a mechanical rename). CHANGELOG.md L10289.

**Resolved since last verification (2026-10-12), removed from the list
above**: `scheme-registered-dimension-gap` — restored real capgen-v1's
`temp_calc_adjust_register`/`dim_inter` chained-interstitial-dimension
shape in `examples/capgen`; the generic mechanism task #30 built already
handled it, zero `xdsl_ccpp/` changes needed. CHANGELOG.md L10841.

**Resolved since last verification (2026-10-12), removed from the list
above**: `nested-suite-module-name-finish` — applied the already-proven
`module_name` fix (`table-props-module-name`) to `examples/nested_suite`,
matching `var_compat`'s own already-landed revert. CHANGELOG.md L10927.

**Resolved since last verification (2026-10-12), removed from the list
above**: `capgen-source-path-untested` — restored `examples/capgen`'s real
`source_path`/`dependencies_path` subdirectory layout
(`source_dir1`/`source_dir2`/`adjust`), matching real capgen-v1 exactly;
also fixed a second, independently-dropped `dependencies_path` on
`temp_adjust.meta` found via regeneration. CHANGELOG.md L10969.

**Resolved since last verification (2026-10-12), removed from the list
above**: `capgen-nested-ddt-dropped` — restored `make_ddt`'s nested-DDT
fields (`ddt2`-sourced `error_maybe` + inline `burma_shave`) and the
`dependencies` key in both `examples/capgen` and `examples/ddthost`;
confirmed pure fixture fidelity, zero generated-output change.
CHANGELOG.md L11055.

**Resolved since last verification (2026-10-12), removed from the list
above**: `task11-omp-thread` item 3 — generalized instance_number's
dispatch-resolution code into a real `CCPP_SCALAR_INDEX_DIMS` table and
added `thread_number`/`number_of_threads` on top. CHANGELOG.md L11105.

**Resolved since last verification (2026-10-12), removed from the list
above**: `task11-omp-thread-rename` — added `number_of_openmp_threads` to
`CCPP_DEPRECATED_STD_NAMES`, matching real capgen-v1's own legacy-mode
mapping. CHANGELOG.md L11245.

**Resolved since last verification (2026-10-13), removed from the list
above**: `cmake-dep-manifest` — CMake now consumes the generator's own
`<dependencies>` datatable section instead of hand-listed source files;
fixed a real relative-path bug along the way; CI-confirmed. CHANGELOG.md
L11272.

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
full history. No open items remain.

**Resolved since last verification (2026-10-09), removed from the list
above**: `constituent-ddt-stub-unify` — `_generate_constituent_api` now
resolves its DDT stub module names via `ddt_source_module`, fixing a
latent divergence bug. CHANGELOG.md L10554.

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

Two of the three proposals below remain not scheduled, not started
(unchanged status since first logged 2026-07-19) — real research, no
current commitment to act on it. `dup-meta-shadow-elim`'s Stage 1 is the
exception: started and finished 2026-10-15/16 (see its own entry below).
Full analysis, worked examples, resolved technical risks, and an effort
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
  CHANGELOG.md L8453. `composite-scheme` Stage 1 (resolved, below) supplies this
  item's composition mechanism (`dry_basis`/`theta_basis` become ordinary
  `with`-combinators); expect the residual estimate to shrink once it lands.
- `dup-meta-shadow-elim` — **Eliminate `.meta` as a hand-maintained shadow file** — the big one:
  tag `standard_name`/`units`/etc. directly in Fortran source comments
  (`!$ccpp [name] key = value`), generate `.meta` mechanically. **Stage 1
  (this repo's own `examples/`) is done** — 4 PRs/7 phases merged to
  `main` (#136-#140), two real demonstration examples
  (`threads_nometa`/`advection_nometa`) built, verified via real
  `cmake`/`ctest` builds, and passing in CI; 4 real pre-existing bugs
  found and fixed along the way (none specific to the demo examples
  themselves — all general xdsl_ccpp fixes). CHANGELOG.md L12027. **Stage
  2 (the real `NCAR/atmospheric_physics` corpus, ~36,431 `.meta` lines
  across 182 files — the part that actually delivers this item's
  motivating value) has not been started**; still requires that repo's
  own maintainers' buy-in first, a cross-repo coordination question
  outside this project's unilateral control. CHANGELOG.md L8467
  (original magnitude comparison) through L8577 (original verdict — since
  revised upward for Stage 2 specifically once `dependencies=` extraction
  and GPU-clause variety turned out larger in scope than first estimated;
  see the Stage 1 writeup at L12027 for the corrected numbers).

**`direct-fortran-ingest`** — a related but distinct, larger item, raised
2026-10-15 while discussing `dup-meta-shadow-elim`'s own scope: let
`ccpp_xdsl`'s real generation pipeline (`ccpp_dsl.py`) ingest annotated
Fortran source directly, making `.meta` an *optional* input rather than
a hard requirement, instead of always generating and still requiring it
(`dup-meta-shadow-elim`'s own scope stops at "stop hand-editing `.meta`"
— it never stops being produced, committed, or consumed, specifically
*so that* real capgen-v1 keeps working against the same schemes). This
item goes further: a scheme using the `!$ccpp`/`!$acc` annotation
convention could skip the `.meta`-generation step and the intermediate
artifact entirely when built with `ccpp_xdsl`.

**Explicit, acknowledged trade-off, not a refinement**: this would break
real capgen-v1 compatibility for any scheme that takes this path — real
capgen-v1 has zero ability to read annotated Fortran at all, confirmed
directly against its own source this session (`ccpp_capgen.py`'s CLI has
no concept of a Fortran-source input; only `.meta`/XML/`--output-root`).
Given this project's stated goal of being an interchangeable alternative
to capgen-v1 (not a wholesale replacement that drops compatibility), this
would need to be an explicit, scheme-by-scheme or build-configuration
opt-in, not a blanket default — and is a strategic/governance decision
(is sacrificing capgen-v1 compatibility ever acceptable, for which
schemes, decided by whom) at least as much as a technical one.

Builds directly on `dup-meta-shadow-elim`'s own `!$ccpp`-tag/`!$acc`-
directive extraction infrastructure (same mechanisms, different
consumer) — its own stated precondition, "not schedulable as its own
independent effort until that work has landed," is now satisfied (Stage
1 merged, L12027). Scoped directly against the real code, 2026-10-17, not
estimated from first principles:

**The real integration point is a single loop**, `xdsl_ccpp/frontend/
ccpp_xml.py`'s own `main()` (around line 751): `for scheme_file in
self.options_db["scheme_files"]: for c in parse_meta_file(scheme_file,
True): ir_ops.append(self.build_meta_ir(c, ...))` — every `--scheme-files`
entry is read as `.meta` text, unconditionally, today. (`ccpp_dsl.py`'s
own `merge_meta_files`, used only in `--py` mode, has the same shape at a
second, less-used call site.) Good news, confirmed directly: `fparser2_
to_meta.build_meta_module_from_source`/`build_meta_module_from_file`
(built across Stage 1) already produce IR using the *same* dialect op
classes (`TablePropertiesOp`/`ArgumentTableOp`/`ArgumentOp`) that
`build_meta_ir` does — this was never a format-translation problem, it's
a routing one. For a `.F90` entry in `--scheme-files`, the ingest path is
structurally just "call `build_meta_module_from_file` instead of
`parse_meta_file`+`build_meta_ir`, append its ops the same way" — sniffing
the file extension in that same loop, not a new CLI flag.

**Three things that aren't free, though:**
1. `dependencies`/`dependencies_path` are real `TablePropertiesOp`
   properties today populated from a `.meta` file's own `dependencies =`
   text line (`ccpp_xml.py` lines ~696-715). An ingested `.F90` has no
   such line — these would need to come from Stage 1's own
   `module_dependency_resolver.resolve_scheme_dependencies()` instead,
   which means `ccpp_xml.py` itself needs a `--root-dir`-equivalent
   option (today only `ccpp_generate_meta.py`, the separate `.meta`-text
   convenience tool, has one).
2. `ccpp_dsl.py`'s `--list-outputs` prediction and the incremental-build
   dependency-file (`.d`) generation (`cmake-dep-manifest`, already
   resolved) both currently assume a scheme's build-relevant source is
   its `.meta` file. A Fortran-ingest scheme's real dependency is the
   `.F90` file itself — CMake-facing tracking needs updating so an edit
   to that file actually triggers a reconfigure/rebuild, not just a
   Python-side concern.
3. The opt-in mechanism itself (not the governance *decision*, which
   stays non-technical and unresolved) — whatever a build declares to
   say "this specific scheme takes the Fortran-ingest path" needs an
   actual flag/config surface once that decision is made.

**Estimate: 6-10 days (M)** — extension of already-built, already-proven
infrastructure (1-3 days: the routing change + `--root-dir`-style
dependency wiring, directly reusing Stage 1's resolver), real but bounded
CMake/build-dependency tracking (2-4 days), the opt-in flag/config
surface once the governance question is answered (1-2 days), and
end-to-end verification against one real migrated example with full CI
(2-3 days). No open technical risk — every piece above has a direct,
already-built analog from Stage 1 to extend, unlike Stage 1 itself at the
time it was first scoped. The only genuinely open question is still the
non-technical one below.

Those three proposals target a different repo (`NCAR/atmospheric_physics`),
not this one -- unlike `direct-fortran-ingest` above, which is squarely
about this repo's own `ccpp_dsl.py`. Section 5's own architecture review
found most of the xdsl_ccpp-side
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

## Someday-maybe: scheme I/O capture + generated per-scheme unit tests

ID: `scheme-io-capture`. **v1 resolved (2026-10-17, PRs #141/#142/#143,
merged to `main`)** — opt-in `--capture-scheme`/`--capture-test-driver-dir`
capability, runtime Fortran capture library, and a generated
scheme-scoped test driver, real-verified end-to-end against
`examples/kessler` (CPU/gfortran). CHANGELOG.md L12255. Original design
proposal: CHANGELOG.md L11731. Follow-on work is tracked under its own
IDs below, not bundled here — see the sizing table at the top of this
file for the full list.

**ID: `scheme-io-capture-netcdf`. v2 follow-on: NetCDF capture format.**
v1's runtime library
(`ccpp_capture_mod.F90`) deliberately uses plain Fortran stream I/O, one
raw binary file per captured tag (no embedded variable name/shape
metadata beyond a leading rank+shape header) — a deliberate v1 choice to
keep the library small and avoid parallel-I/O coordination, confirmed
real: a 1000-column/56-layer kessler capture produces 23 files, ~6.1MB,
scaling linearly with `ncol*nz`. NetCDF would be a genuine improvement —
self-describing (names/shapes travel with the data, not just encoded in
the filename), one file per captured *call* instead of one per argument,
inspectable with standard tools (`ncdump`/`xarray`) instead of a bespoke
reader, built-in compression. Real cost: `examples/` has zero NetCDF
dependency today anywhere in this repo, so this would be a new build
dependency for a tool whose whole point was staying minimal/dev-only —
though notably a much smaller lift if this capability is ever wired into
real CAM-SIMA builds specifically, which already link NetCDF
everywhere. Not v1 scope; revisit once v1's real usage (and the "where do
captured fixtures live" question below) make the tradeoff concrete.

**ID: `scheme-io-capture-gpu-residency`. Resolved (2026-10-18, PR #146).** CHANGELOG.md L12524.

**ID: `scheme-io-capture-gpu-verify`. Resolved (2026-10-18)** — real
`nvfortran -acc` run on an A100, confirmed with `nsys` (real
`cuLaunchKernel`/memcpy activity, not a host fallback). CHANGELOG.md L12524.

**ID: `scheme-io-capture-ctest-automation`. v2 follow-on: full CMake/ctest
automation.** Already noted in this
session's own planning as explicitly out of v1 scope, recorded here so
it isn't lost to a plan file outside this repo: configure-time
test-driver-filename prediction (mirroring `--list-outputs`/
`predict_output_filenames()`'s existing pattern), a static `add_test()`
with a `DEPENDS` ordering between a "produce fixture" test and a
"consume fixture" test, and an opt-in `examples/kessler/CMakeLists.txt`
cache var. Confirmed this repo has zero precedent for a
dynamically-registered CMake test today — every `add_test()` is
currently static — so this is genuinely new ground, not a quick
extension of something already there.

**ID: `scheme-io-capture-fixture-storage`. v2 follow-on: where do
captured fixtures live.** Still an open
question, not yet decided. Captured `.ccppcap` files are real binary
data tied to one specific run; confirmed real size: a 1000-column/
56-layer kessler capture is 23 files, ~6.1MB, scaling linearly with
`ncol*nz` — a real CAM-scale column count would be substantially larger.
Options not yet weighed against each other: commit fixtures to git
alongside the generated driver (simple, but binary blobs that grow with
scheme complexity); regenerate fresh at build/test time by running the
capture-enabled executable (no binary data in git, but fixtures aren't
stable/reviewable across scheme changes without rerunning); or leave
fixture generation to a local, gitignored, explicitly-opt-in step.
Interacts with the NetCDF item above (one consolidated file per call
instead of one per argument would change the size/count math).

**ID: `scheme-io-capture-multi-timestep`. Resolved (2026-10-18, PR #145).** CHANGELOG.md L12473.

**ID: `scheme-io-capture-compare-diagnostics`. Resolved (2026-10-18, PR #145).** CHANGELOG.md L12473.

**ID: `scheme-io-capture-tolerance-config`. Resolved (2026-10-18, PR #145
+ a runtime-override follow-up).** CHANGELOG.md L12473.

**ID: `scheme-io-capture-staleness-check`. v2 follow-on: fixture/signature
staleness detection.** A captured
`.ccppcap` file carries no version stamp tying it to the scheme's
argument list (names/types/ranks) as it existed at capture time. If a
scheme's signature changes later (a renamed/retyped/added argument) and
the fixture isn't regenerated, today's shape-mismatch reporting in
`ccpp_capture_read_*` would surface *something* wrong but not clearly
say "this fixture predates the current scheme signature" -- worth a
clearer, purpose-built error for this specific, likely-common case.

**ID: `scheme-io-capture-multi-call-site`. v2 follow-on: multi-call-site
schemes.** Current driver generation
assumes one call site per table name per suite (`_maybe_emit_test_driver`
keys `captured_tables` by `table_name` alone) -- a scheme invoked at two
genuinely distinct call sites within the same suite would have the
second site's capture/driver silently overwrite the first's. Not hit by
kessler (single call site per phase), but worth a real check before
applying this to a busier suite.

**ID: `scheme-io-capture-optional-args`. v2 follow-on: `optional`-argument
support.** Deliberately out of v1 scope from the original design proposal
onward — confirmed zero occurrences of `optional` across the entire real
target corpus (183 `.meta` files under `src/physics/ncar_ccpp/schemes/`
in CAM-SIMA, zero in this repo's own `examples/`), so the real
implementation cost (synthesizing new control flow around a possibly-
absent array-section argument, in both the capture pass's IR insertion
and the generated test driver's own call/declaration logic) wasn't a
good trade against shipping v1 for schemes that actually exist. Revisit
if `--capture-scheme` is ever pointed at a scheme that genuinely uses
`optional`.

**ID: `scheme-io-capture-task-volume`. Resolved (2026-10-18, PR #144)** —
the `flag_for_mpi_root` guard closes both halves of this item's original
scope (the write race AND unbounded multi-task volume, by restricting
capture to one task) with a simpler mechanism than the task-id-in-
filename approach originally envisioned. CHANGELOG.md L12426.


## Someday-maybe: composite schemes (packages with slots and hooks)

ID: `composite-scheme`. **Stage 1 and the Stage 2 core resolved
(2026-10-19/20); follow-ons below are open.** Full design, worked RRTMGP
example and staged plans: `composite_scheme_plan.md`. CHANGELOG.md L12572.

Let a physics parameterization be written as an exchangeable **package**
(composite scheme): a Python function whose body composes schemes, with
**slots** (swappable science components with package defaults, e.g. cloud
optics, McICA/overlap) and **hooks** (host code the host must supply, e.g.
diagnostics, gas source). The package is called from a host-owned adapter
and from group functions (`def physics_after_coupler()`). Motivated by the
RRTMGP block of `suite_cam4.xml`: 40 entries, only 11 doing radiative
transfer.

- **Stage 1. Resolved (2026-10-19, PRs #148/#149 + RRTMGP example)** —
  Python composition, path-free `ccpp_scheme_ref`, CMake `PY_SUITE`, and
  helloworld/advection/RRTMGP composite examples. CHANGELOG.md L12600.
- **Stage 2 core (S2-0..S2-3). Resolved (2026-10-19/20, CAM-SIMA PR #3,
  PRs #151/#152/#153)** — CHANGELOG.md L12657.
- **Open follow-ons** (none scheduled; see plan §11):
  - **S2-4, run-time conditional** (`with when(...)`) — deferred: gating
    RRTMGP's entry points would change diagnostics history on non-radiation
    steps (see CAM-SIMA #482). Plan §11.3, "S2-4 decision".
  - **GPU residency validation of the composite path. Resolved for the
    flatten lowering (2026-10-20)** — unit test
    `test_private_device_array_keeps_gpu_residency` (`tests/unit/test_package_scope.py`):
    a package-private `memory_space = device` array gets the same OpenACC
    code (`declare create`, `enter data create`, `exit data delete`) as
    without the package. The RRTMGP GPU pair (`/cam-sima-rrtmgp <id> gpu`)
    only checks build and run, since RRTMGP declares no device-resident
    arguments. A compiled end-to-end check would need a composite version of a
    CAM-SIMA GPU suite with device-resident arguments (e.g. kessler).
  - **2f/2g, per-package cap with GPU residency** — designed 2026-10-20,
    `composite_scheme_plan.md` §12 (segmentation at hooks in every phase,
    package-private state in the package cap, package caps never move data,
    kessler FPHYStest on GPU as the gate). Staged: 2f-1 segmentation
    analysis (`transforms/package_segments.py`, in `--list-package-scope`);
    2f-2 package caps on CPU; 2g on GPU; then a default-switch decision.
  - **Scoping between packages** — needs a multi-package suite (e.g. a
    CAM4/QPC4 composite); the RRTMGP test has one package.
  - **Loop index from `forLoop`** — would remove the `next_call` hook and the
    `rrtmgp_subcycle` counter.

  Cross-group agreement on the public radiation interface is governance,
  not a sizable task.

Upstream atmospheric_physics prerequisites (not xdsl tooling, recorded in
the plan doc):
- split the four mixed host/package schemes (`rrtmgp_pre`, `rrtmgp_post`,
  `rrtmgp_inputs`, `*_calculate_fluxes`); the `rrtmgp_pre`/`rrtmgp_post`
  split is worked out in plan §11.6 (shared state 13 → 2);
- decide separate standard names for RRTMGP's heating rates and CAM's
  carried-over heating (the remaining 2 shared-state names);
- fix the latent `iter_num` column-block bug in
  `rrtmgp_sw_gas_optics`/`rrtmgp_sw_rte`/`rrtmgp_lw_gas_optics`.

SW/LW diagnostic-loop fusion was deliberately rejected (different
radiation frequencies).

## Someday-maybe: process splitting

ID: `process-split`. Added 2026-10-20. Neither capgen-v1 nor xdsl-ccpp can
run schemes process-split, where every process starts from the same state
and the increments are summed. Both support only time splitting (sequential
in-place updates). capgen-v1 never implemented it: the old capgen
`ProcessSplit` class was a stub that raised "not yet implemented". The
obstacle in capgen is that schemes update host arrays in place through
`intent(inout)`, the framework keeps no copies of state, and metadata
doesn't link a tendency to its state variable.

Approach for xdsl-ccpp: compute increments **by difference**, so neither the
schemes nor the metadata need to change. For each region: snapshot every
variable any scheme in it writes (`x0 = x`), run each process on its own
private copy (`x_i = x0`), then combine (`x = x0 + Σ(x_i − x0)`). A process
may be several schemes run in sequence. Existing machinery to build on: the
per-call-site temporary + write-back pattern of unit/kind conversion
(`KindCastOp`/`UnitConvertOp`/`*WriteBackOp` in `suite_cap`), the
`SubcycleOp` region lowering, per-call intents in `SuiteVarOccurrence`, and
the residency passes. The Python frontend would express it like
`forLoop`, and suits it better than XML because combine rules can be Python
objects:

```python
with process_split(combine={"air_temperature": SUM_INCREMENTS,
                            "precipitation_rate": EXCLUSIVE}):
    with process():
        deep_convection(); shallow_convection()
    with process():
        vertical_diffusion()
```

The analysis itself belongs in a pass, so an XML `<process_split>` element
could reach the same machinery.

- `call-site-arg-rebind` — **Rebind a scheme argument to a different
  variable at the call site** (S-M). Today a call-site keyword override
  accepts only a compile-time literal (`SchemeDescriptor.__call__` →
  `arg_overrides` → `name=literal`). Allowing e.g.
  `vdiff(air_temperature=copy_of("air_temperature"))` would let a suite
  author build process splitting by hand with small copy/sum schemes, like
  UFS's `phys_ps` group. It is useful independently and is a stepping stone
  to `process-split-region`.
- `process-split-region` — **`ProcessSplitOp` with increments by
  difference, CPU only** (L). Covers a new dialect op, Python frontend
  context managers (plus optionally an XML element), a pass that computes
  each region's write set, `suite_cap` lowering (snapshot, private copy,
  accumulate ops), `print_ftn` emission, and the datatable and
  variable-tracking tools. Touches roughly the same 8 files as `SubcycleOp`.
- `process-split-gpu` — **Device-resident snapshot and private copies**
  (M-L). Extends `gpu_data_pass`/`gpu_ccpp_cap_pass` to cover the new
  temporaries and keeps copy/accumulate on the device. Device memory grows
  with the number of processes per region.
- `process-split-combine-policy` — **Combine and fixer rules** (not sized;
  science decision). Summing increments works for temperature, winds and
  constituents, but not for integers, logicals, flags or characters, or for
  an `intent(out)` diagnostic written by two processes (error, sum, or
  last writer?). Summed increments can also push a constituent negative even
  when each process kept it positive, so positivity and energy fixers must
  run either per process or after combining. Also needs a rule for `errflg`
  across processes. Default should be an error for any variable without an
  explicit rule. Settle this with CAM/UFS physics developers before fixing
  the IR design of `process-split-region`.
- **ID: `process-split-terminology`. Resolved (2026-10-20)** — the four
  agent-written "process-split state update" comments on `apply_heating_rate()`
  in `composite_scheme_plan.md` and `cam_rrtmgp_adapter.py` now say time-split.

## GPU residency verification

Found 2026-10-19 while building `examples/advection_composite`:
`examples/advection/cld_ice.meta` (and `examples/advection_flat_host`'s
identical copy) declared `cld_ice_array` host-resident in `cld_ice_run`
although the routine's own kernel asserts
`!$acc parallel loop ... present(qv,cld_ice_array,temp)`. The generated
suite cap therefore wrapped `cld_ice_run` in
`!$acc update self/device(cld_ice_cld_ice_array)`, whose trailing
`update device` can overwrite the kernel's device-side result. Fixed in the
`composite-scheme` PR 2 (one `memory_space = device` line per file, plus
regenerated `advection-xml` FileCheck goldens); unit test
`test_py_composite_suite_generates_same_caps_as_xml` now cross-checks
advection's hand-written `.meta` against `.meta` generated from the
`!$ccpp`/`!$acc`-annotated sources. The bug survived since July because
nothing in CI ever executes generated OpenACC: the gnu/intel jobs ignore
`!$acc`, and the manual-only nvhpc job runs on a GPU-less runner with
`ARCH=CPU` (`-noacc`). Two follow-ons:

- `acc-meta-residency-check` — **Static `.meta` vs `!$acc` residency
  consistency check.** `ccpp_dsl.py`'s `validate_fortran_sources` already
  pairs each `--scheme-files` `.meta` with its `.F90` and runs
  `validate_fir.compare_modules`, which compares type/rank/intent/
  optional/kind/extra args but not `memory_space`. Extend it to compare
  each argument's declared `memory_space` with what the routine's own
  `!$acc present(...)`/`deviceptr(...)` clauses imply (the derivation
  `fparser2_to_meta.py` already performs for `!$ccpp`-tagged sources), and
  report mismatches the same way (warn-only first, like the existing
  check). Needs no GPU, would have flagged the `cld_ice` bug at generation
  time, and applies equally to CAM-SIMA's hand-written atmospheric_physics
  `.meta`.
- `gpu-ci` — **CI that actually runs generated OpenACC on a GPU.** GitHub's
  standard hosted runners have no GPU, so this needs a GPU-equipped runner:
  a paid GitHub GPU runner, or a self-hosted/scheduled job on NCAR
  hardware (e.g. a Derecho GPU node, with the PBS submission and
  credential handling that implies). Also requires the GPU-capable
  examples (`advection`, `advection_flat_host`, `advection_nometa`,
  `advection_composite`, `kessler`) to build with `ARCH=GPU`, and their
  host-integration checks to be sensitive enough to detect wrong data
  movement (not yet confirmed for `advection`'s `compare_data`). The
  runner/hosting choice is an infrastructure and funding decision outside
  this project's unilateral control.
- `gpu-conversion-residency` — **Device-resident args that need a unit or
  kind conversion get a host-only temporary.** The suite cap builds
  `<arg>_unit_conv`/`<arg>_kind_cast` (`suite_cap.py`, ~L1060-1120) as a
  whole-array host assignment, with no `!$acc`/`!$omp` directive, so a kernel
  asserting `present(<arg>)` would fail. Latent (checked 2026-10-20): none of
  the 6 CAM-SIMA GPU tests has a conversion; the only conversion in any
  CAM-SIMA suite is `dpdry` Pa→hPa for `zm_conv_convtran` (CPU-only today).
  Fix: create the temporary on the device and run the conversion (and the
  `inout`/`out` write-back) there -- `acc kernels` around the array
  assignment, or an explicit loop nest for `--directive omp` -- ideally with
  xDSL's `acc`/`omp` dialects (needs `xdsl-upgrade`). Must land before ZM
  convection, or any scheme whose units/kinds differ from the host's, runs
  on the GPU with device-resident args. Package caps (2f) inherit it.
- `xdsl-upgrade` — **Move the xDSL pin from 0.56.1 to 0.74.0**
  (`pyproject.toml`). 0.64.0+ ships a full port of MLIR's OpenACC dialect
  (`acc.parallel`/`kernels`/`loop`, `acc.data`/`enter_data`/`exit_data`/
  `update`, clause ops); `omp` is already present. ~18 releases: expect API
  changes in IRDL, the rewriter and parser/printer. Own PR, no behaviour
  change, full test suites + a CAM-SIMA regression run. Enables
  `gpu-conversion-residency` with upstream dialects and, later, replacing
  xdsl_ccpp's hand-written `Acc*`/`Omp*` data-directive ops.
