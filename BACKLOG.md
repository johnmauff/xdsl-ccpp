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
| `chost-column-major` | 2-5 days (re-scoped 2026-10-27: `row_major` exists; verify/test on the chost path; more if the conversion must be wired in there) | S |
| `cxx-scheme-no-e2e-test` | 5-10 days (open-ended scope) | M |
| `cxx-scheme-annotations` | 8-14 days (+3-5 for the optional `memory_space` derivation from `#pragma acc`; after `cxx-scheme-no-e2e-test`) | M-L |
| `direct-fortran-ingest` | 6-10 days (now that Stage 1's extraction infrastructure has landed — see scoping below) | M |
| `eamxx-phaseA-variant-tag` | 8-15 days (on hold — motivation under review, may be obsolete) | M-L |
| `chost-gpu-memory` | 10-20 days | M-L |
| `suite-state-full-match` | (file's own prior note: "L") | L |
| `dup-meta-shadow-elim` — Stage 2 (full, real corpus) | 18-30 days | L |
| `composite-scheme` — Stage 2 follow-ons (core S2-0..S2-3 resolved; see the `composite-scheme` section and `composite_scheme_plan.md` §11) | umbrella: package caps 2f/2g done (GPU validated by the Kessler gate), default switch deferred; open follow-ons sized in the `composite-*` and `package-cap-*` rows below | -- |
| `package-cap-loop-gpu-sync` | 3-6 days (syncs inside package-only loops, shared with the suite cap's same gap; OpenMP target equivalent) | S-M |
| `package-cap-runtime-loop-count` | 1-3 days (pass the count to the segment as an argument) | XS-S |
| `package-cap-tooling` | 4-8 days (constituents, resolved-vars, scheme I/O capture, variable tracking -- each a separate consumer) | S-M |
| `package-cap-segment-names` | 1-2 days (new segment-naming scheme; regenerate RRTMGP/Kessler package caps) | XS |
| `canonical-error-arg-order` | 2-4 days (small code change; baseline review across all configurations) | S |
| `package-scheme-list-order` | 1-2 days | XS |
| `composite-when-gating` | 2-5 days (plan estimate S) -- deferred by the user, would change RRTMGP's diagnostics history | S |
| `composite-multi-package-scoping` | 6-12 days (needs a multi-package composite suite, e.g. CAM4/QPC4, before the scoping rules can be tested) | M |
| `composite-forloop-index` | 2-4 days (loop index from `forLoop`; then drop RRTMGP's `next_call` hook and subcycle counter) | S |
| `derecho-false-run-pass` | 1-3 days (detection done in the skills and the CIME fork's `cs.status`; fixed upstream in cime6.6.2 (ESMCI/cime#5033, #5063); CAM-SIMA issue #575 asks to update its cime pin) | XS |
| `nvhpc-ncdata-roundoff` | 1-2 days (tolerance and per-testmod overrides in place; confirm in the next nvhpc and an intel regression) | XS |
| `pumas-ncdata-diffs` | 1-3 days (covered by the cross-compiler tolerance; confirm in a run) | XS-S |
| `zm-ncdata-diffs` | 5-10 days (cause not yet known; fails on every compiler) | M |
| `suites-py-xml-omissions` | <1 day (raise two likely cam5 XML omissions with the atmospheric_physics developers) | XS |
| `generation-error-output` | 2-4 days (legacy warnings tied to `--verbose`, carried to the `ccpp_opt` subprocess; plain error exit without a traceback; quiet the fparser2 warning) | S |
| `rrtmgp-wrapper-acc-trigger` | 1-2 days (one confirming GPU run, then a one-line `Depends.nvhpc` change if confirmed) | XS |
| `cam-sima-build-time` | 3-6 days per lever (nvhpc measurement first) | S-M |
| `acc-meta-residency-check` | 2-4 days; now the first stage of `acc-derive-memory-space` (counted in its row) | S |
| `gpu-ci` | 10-20 days engineering (once a GPU runner is chosen -- the infrastructure decision itself is unquantifiable) | M-L |
| `gpu-conversion-residency` | 2-5 days (after `xdsl-upgrade`) | S-M |
| `xdsl-upgrade` | 2-5 days, depending on API changes | S-M |
| `constituent-device-residency` | 5-10 days (enter/exit and entry/exit syncs are small; the per-call last-writer tracking across views, the whole array and tendency appliers is most of it; plus a GPU regression) | M |
| `gpu-ddt-deep-copy-residency` | 6-12 days (component discovery from DDT metadata, enter/exit/update sequences for acc and omp, partial-update routing, a new GPU example; allocatable components only); phase 2 (nested, polymorphic, for RRTMGP) +5-10 days | M (L with phase 2) |
| `gpu-fphystest-pumas` | umbrella, ~30-50 days in total: the sum of its steps below plus `acc-derive-memory-space`, `constituent-device-residency` and `gpu-ddt-deep-copy-residency` phase 1; plus ESCOMP/PUMAS review time | XL |
| `gpu-fphystest-rrtmgp` | umbrella, ~50-80 days in total: its steps below plus `acc-derive-memory-space`, `constituent-device-residency` and `gpu-ddt-deep-copy-residency` phases 1-2 (items shared with `gpu-fphystest-pumas` count once if both are done) | XL-XXL |
| `gpu-pumas-testmod` | 1-2 days | XS |
| `pumas-module-props-device` | <1 day of code (plus ESCOMP/PUMAS review) | XS |
| `gpu-port-pumas-interface-schemes` | 2-5 days (4 small schemes: reshapes and limiters; plus `micro_pumas_ccpp_run` directives and ESCOMP/PUMAS review) | S |
| `gpu-port-shared-utility-schemes` | 6-12 days (small kernels incl. the 10 state converters, but used by every suite: regression on CPU and GPU) | M |
| `gpu-fphystest-kessler` | umbrella, ~25-45 days in total: `gpu-sync-intent-aware`, `scheme-io-capture-ddt-args` (constituent-properties case), `scheme-io-capture-group-replay`, `acc-derive-memory-space`, Kessler's 12 of `gpu-port-shared-utility-schemes` and `constituent-device-residency` (most shared with the PUMAS and RRTMGP umbrellas; count once) | L-XL |
| `gpu-sync-intent-aware` | 2-4 days | S |
| `cap-oracle-ci` | 3-6 days (committed input fixtures or a CAM-SIMA checkout in CI; a ccpp_framework checkout for `capgen`) | S |
| `cap-oracle-kessler-capgen` | 1-2 days | XS |
| `suite-cap-mode-flags` | 10-20 days (separate the products the suite-cap generator builds under `physics_mode`/`emit_scheme_calls`/package-cap/instances/CAM flags) | L |
| `split-large-generators` | 10-20 days, opportunistic (the five 350-900-line generator functions) | L |
| `py-api-docs-current-style` | 2-4 days (README Python-API section rewrite, `emit_ir` deprecation, in-repo example scripts and the goldens that run them) | S |
| `active-pointer-association` | 4-8 days (pointer wrapper types or typed local pointers, call-site association/nullify, transform temps as targets, the non-optional guard, regenerate var_compat/instances/advection goldens, compile and run the examples) | S-M |
| `gpu-port-rrtmgp-wrapper-schemes` | 12-20 days (21 schemes, most manipulating rte-rrtmgp objects; McICA reproducibility) | L |
| `gpu-port-scheme-checklist` | tracking table only; the work is sized in the three `gpu-port-*` rows | -- |
| `suite-cap-loop-gpu-sync` | 3-5 days | S |
| `acc-derive-memory-space` | 4-7 days (hand-written `.meta` pairing, `default(present)`, DDT components, precedence and warnings; entry-point body only; includes `acc-meta-residency-check`'s 2-4) | S-M |
| `scheme-io-capture-multi-call-site` | 1-3 days | XS-S |
| `scheme-io-capture-optional-args` | 2-4 days | S |
| `scheme-io-capture-fixture-storage` | 2-4 days engineering (once a storage approach is picked — the decision itself is unquantifiable) | S |
| `scheme-io-capture-staleness-check` | 3-6 days | S-M |
| `scheme-io-capture-netcdf` | 6-10 days | M |
| `scheme-io-capture-ddt-args` | 4-8 days (component discovery, recursive capture/restore of allocatable and fixed-size numeric components; or a constituent-properties special case first, ~2-3 days) | S-M |
| `scheme-io-capture-group-replay` | 6-12 days (group-level capture point incl. suite module state, driver with host-cap residency emulation, GPU build and compare; reuses the v1/v2 capture library and tolerance code) | M |
| `scheme-io-capture-ctest-automation` | 6-10 days (genuinely new ground — this repo has zero precedent for a dynamically-registered CMake test today) | M |
| `call-site-arg-rebind` | 4-8 days | S-M |
| `process-split-region` | 15-25 days (CPU only; assumes `process-split-combine-policy` is settled first) | L |
| `process-split-gpu` | 10-20 days (on top of `process-split-region`) | M-L |
| `eamxx-phaseC-printer` | ~60-150+ days (high uncertainty — no existing analog/technique to build from, unlike every other item above) | XXL |

`hle-vocab-retire` is intentionally not sized — it's blocked on an
external dependency (CAM-SIMA migrating off `horizontal_loop_extent`
upstream), not a schedulable estimate. `process-split-combine-policy` is
likewise not sized — it's a science decision for the physics developers,
not engineering work. `composite-package-caps` is not sized either: 2f/2g are
done, and what remains -- making package caps the default -- is a decision
the user has deferred until more testing; its open gaps are the
`package-cap-*` rows.

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
| `derecho-false-run-pass` | CIME reports `RUN PASS` for CAM runs that aborted; past regression counts were overstated | XS (tooling done; fixed upstream in cime6.6.2; CAM-SIMA #575 to update the pin); found 2026-10-21 (see below) | -- |
| `nvhpc-ncdata-roundoff` | 7 nvhpc FPHYStest cases abort on `ncdata_check` differences vs gnu snapshots (5 at <=4.2e-12; uw_vdiff 1.4e-10, rrtmgp 1.6e-9) | S; cross-compiler tolerance 1e-11 (CAM-SIMA, uncommitted), awaiting gnu/intel/nvhpc regressions | -- |
| `pumas-ncdata-diffs` | `SMS_D` pumas FPHYStest aborts on small `ncdata_check` differences, gnu and nvhpc | S; its snapshot is intel-made, so likely rounding; covered by `cross_compiler_check_tolerance`, awaiting a run | -- |
| `zm-ncdata-diffs` | zm FPHYStest differs from its snapshot on every compiler; `ncdata_check_err` now on, so it fails until fixed | M; xdsl55n, xdsl56g/i/n | -- |
| `suites-py-xml-omissions` | cam5's XML (and its Python copy) likely omits two schemes cam4 and cam7 have | XS; raise with the atmospheric_physics developers | -- |
| `generation-error-output` | A failed cap generation buries a good error message in ~1,600 warning lines and two tracebacks | S; found 2026-10-24 comparing gw_cam7 failures (xdsl57n vs capgen); design: legacy warnings follow `--verbose`; deferred | -- |
| `rrtmgp-wrapper-acc-trigger` | GPU RRTMGP 'partially present' abort apparently happens only because our `ccs_config` compiles the RRTMGP `ccpp_*` wrappers with `-acc` | XS; found 2026-10-24 (tpr_n capgen GPU RRTMGP passes without the fix) | -- |
| `cam-sima-build-time` | Where CAM-SIMA case build time goes, and cheaper levers than a prebuilt base library | S-M per lever; gnu measured 2026-10-21 (xdsl56g); **repeat for nvhpc** (xdsl56n) | -- |
| `canonical-error-arg-order` | Generated routines take the CCPP error arguments in whatever order and names their first scheme uses | S code, M review (touches nearly every configuration's generated code); found 2026-10-23 (s27b) | -- |
| `package-scheme-list-order` | With package caps, `ccpp_physics_suite_schemes` lists a segment's schemes where the segment first appears, not in call order | S; found 2026-10-23 (s27b, s29a); only affects the order CAM reads scheme namelists | -- |

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
`kessler`, `microp_aero_bam`, `rk_stratiform`, `rrtmgp` and `uw_vdiff` abort on
`ncdata_check` against the gnu snapshots (xdsl55n; `gw_cam7` also in
xdsl50n). Largest differences, read from the differences table (rows with a
location; the "Variable Checked ... Avg" table lists averages, not
differences): kessler 1.6e-16, microp_aero_bam 2.3e-14, gw_cam4 1.0e-12,
rk_stratiform 1.7e-12, hb_vdiff 4.2e-12 -- double-precision-level -- but
uw_vdiff 1.4e-10 and rrtmgp 1.6e-9 (corrected 2026-10-24: first recorded as
4.5e-15 and 9.4e-14, misread; xdsl55n and xdsl57n show the same values). nvhpc is already built with `-Kieee -Mnofma
-MllvmO0`, so the likely source is math-library differences (exp/log/pow/
gamma) and `-Mflushz` (inferred, not measured). Change (CAM-SIMA,
uncommitted): include-only testmod `cam/cross_compiler_check_tolerance`, in
the 18 CPU FPHYStest snapshot testmods. Its `shell_commands` reads the
snapshot's compiler from the `ncdata_check` file name (all gnu except pumas,
intel) and, only when it differs from the case's `COMPILER`, sets
`min_difference` in `user_nl_cam` (replacing the testmod's 2e-15/1e-15, or
adding one) to 1e-11 -- or to the value of a
`! cross_compiler_min_difference = <v>` comment line in the testmod's
`user_nl_cam` (pumas 1e-9, uw_vdiff 1e-9, rrtmgp 1e-8; the last two added
2026-10-24). Same compiler, or none in the name: unchanged.
First set to 1e-8 (2026-10-21; xdsl56n passed all seven with it), tightened
to 1e-11 on 2026-10-22 because 1e-8 is close to single-precision agreement.
Close once gnu, intel and nvhpc regressions pass with 1e-11 -- the margin
over the observed 4.2e-12 is thin, so a case landing between 4e-12 and
1e-11 gets its own justified override, not a looser default. Status
(2026-10-24): gnu xdsl57g passes (same compiler as the snapshots); nvhpc
xdsl57n passes the other five at 1e-11; rrtmgp and uw_vdiff failed at 1e-11,
and their measured maxima are below their new overrides, so the next nvhpc
regression confirms them. Still to do: an intel regression.

**`pumas-ncdata-diffs`** -- `SMS_D_Ln2...cam-outfrq_pumas_derecho` aborts on
`ncdata_check` under gnu (xdsl51g, 52g, 54g) and nvhpc (xdsl50n, 55n). Its
snapshot is intel-made (`..._derecho_intel_after_c20260820.nc`), and
intel matches it exactly (xdsl56i). Against it, gnu and nvhpc differ by up
to 2e-10 and 5e-10, largest in the droplet and rain number concentrations
and the droplet distribution slope (temperature and mixing ratios <=1e-12):
PUMAS's size distributions use powers and gamma functions throughout. Its
testmod sets `! cross_compiler_min_difference = 1e-9` (see
`nvhpc-ncdata-roundoff`); with 1e-8, gnu and nvhpc reached `END OF MODEL
RUN` (xdsl56g, xdsl56n). Close once they also pass with 1e-9.

**`zm-ncdata-diffs`** -- `SMS_Ln2...cam-outfrq_zm_derecho` differs from its
(gnu-made) snapshot under gnu, intel and nvhpc alike: 16-18 variables in
xdsl56g/i/n (42 in xdsl55n), e.g. `air_temperature` at ~3400-3800 points,
max difference 1.1e-4, and much larger differences in the cloud/rain/snow
number concentrations. Not rounding: gnu matches the snapshot's compiler,
and the cross-compiler tolerance (1e-8) does not remove it. The test still
passes because `cam/outfrq_zm_derecho/user_nl_cam` sets `ncdata_check` but
not `ncdata_check_err = .true.` (and no `min_difference`), so differences
are only printed. (`hack_shallow` is set up the same way; its differences are
rounding-sized, ~1e-15.) `ncdata_check_err = .true.` turned on in the zm
testmod 2026-10-22 (CAM-SIMA, uncommitted), so the zm test now FAILS until
this is fixed. To do: find whether the ZM scheme or its snapshot moved
(compare with a capgen build; check the snapshot's date, c20250116,
against ZM changes).

**ID: `rrtmgp-gpu-partially-present`. Resolved (2026-10-24)** -- `rrtmgp_post` now frees the gas-concentration objects (atmospheric_physics PR #468); GPU RRTMGP pair s34a completes. Trigger is our build config, see `rrtmgp-wrapper-acc-trigger`. CHANGELOG.md L12785.

**ID: `cloud-water-ncdata-diffs`. Resolved (2026-10-28)** -- fixed by `advected-constituent-host-binding`; gnu cloud_water clean in xdsl58g. CHANGELOG.md L12823.

**ID: `advected-constituent-host-binding`. Resolved (2026-10-28, PR #164)** -- advected args are host-cap constituent views, as in original capgen. CHANGELOG.md L12823.

**ID: `rk-top-lev-host-match`. Resolved (2026-10-28)** -- the host cap reads suite argument standard names recorded by the suite cap; rasch_kristjansson and cam4 caps match original capgen. CHANGELOG.md L12925.

**ID: `tendency-view-lookup-silent`. Resolved (2026-10-28)** -- a tendency without its advected constituent is a generation error (as in original capgen); a failed run-time lookup now sets `errflg`. CHANGELOG.md L12900.

**ID: `suites-py-verification`. Resolved (2026-10-24)** -- the Python suites match their XML suites (IR, generated caps, and cam4 bit-for-bit at runtime). CHANGELOG.md L12747.

**`suites-py-xml-omissions`** -- found while writing the Python suites;
they reproduce the XML on purpose. cam5 runs ZM's energy check without
`zm_prepare_flux_for_check_energy`, and the orographic gravity wave source
without `gravity_wave_drag_orographic_diagnostics`; cam4 and cam7 have
both. Likely XML omissions: raise with the atmospheric_physics developers,
and fix the XML and `suites-py/suite_cam5.py` together if confirmed.

**`generation-error-output`** -- found 2026-10-24 comparing the gw_cam7
FPHYStest failure under both generators. xdsl-ccpp's message is the better
one: `host_var_match_pass` lists every unmatched argument at once (scheme,
argument, standard name: `prec_dp`, `prec_sh`, `prec_str` of
`compute_total_precipitation_rate`), where capgen stops at the first and
omits the argument name. But in xdsl57n's `TestStatus.log` it is buried:
- 1,580 `Warning(LEGACY): arg '...': standard_name 'horizontal_loop_extent'
  is deprecated` lines, printed by the arg op's verifier in
  `xdsl_ccpp/dialects/ccpp.py` each time it runs (so repeated across
  passes);
- an unrelated `Warning: fparser2 failed to parse ... qneg.F90 for
  Fortran-vs-.meta validation: tuple index out of range`
  (`tools/ccpp_dsl.py`);
- the `ValueError` arrives inside the optimizer's Python traceback, which
  `cam_autogen.py` wraps in CIME's.

**Design decision (user, 2026-10-24): tie the legacy warnings to
`--verbose`.** Both views are useful: the full per-argument list is a guide
to which `.meta` files still need updating, and normal builds should be
quiet. So `--verbose 2` keeps every `Warning(LEGACY)` line (as now); the
default level prints a short summary (each deprecated name once, with a
count); `--verbose 0` prints none. There is no such control today: the
warning is printed unconditionally from `ArgumentOp.__init__` in
`dialects/ccpp.py` (once per argument, and again whenever IR is re-parsed,
e.g. in the `ccpp_opt` subprocess), and `--verbose` only reaches
`ccpp_dsl.py`'s `print_verbose_message`. The level must be carried to the
`ccpp_opt` subprocess and the Python-suite frontend (which reads `sys.argv`
itself), e.g. as a module setting next to `set_legacy_mode` in
`util/ccpp_conventions.py`; `cam_autogen.py` can then choose the level.
Not started (user deferred).

Also to do: report user-input errors such as host-match
failures as a plain `Error:` message with exit status 1, keeping the
traceback for internal errors or a verbose flag; show the fparser2 warning
only when verbose (and check why qneg.F90 fails to parse).

**`rrtmgp-wrapper-acc-trigger`** -- found 2026-10-24. Upstream's capgen GPU
RRTMGP test (CAM-SIMA tpr_n, `development`, no atmospheric_physics #468)
reaches `END OF MODEL RUN` with a clean `ncdata_check`; our xdsl-ccpp builds
aborted without #468. Compile-flag comparison of the two builds:
`ccpp_gas_concentrations.F90` (the `ty_gas_concs_ccpp` wrapper, copied from
`schemes/rrtmgp/objects/` into `bld/atm/obj/ccpp`) gets `-acc` only in ours,
via the `ccs_config` branch's `Depends.nvhpc` `CCPP_CAP_OBJS` rule (every
`.F90` in `obj/ccpp`). `mo_gas_concentrations.F90` is `-acc` in both.
To do: (1) confirm with one xdsl GPU RRTMGP run with the pre-#468
`rrtmgp_post` and `ccpp_gas_concentrations.o` excluded from `CCPP_CAP_OBJS`
(expect completion); (2) if confirmed, decide whether the RRTMGP `ccpp_*`
wrappers (and other copied scheme utility files) should be excluded from
`CCPP_CAP_OBJS`, and whether nvfortran's skipped finalization of a component
deallocated through `intent(out)` is worth a compiler bug report.

**`cam-sima-build-time`** -- measured 2026-10-21 from the xdsl56g (gnu) build
logs and object mtimes, read-only; scripts, README and the gnu result
(`res_xdsl56g_gnu.json`) are in `/glade/derecho/scratch/dennis/Claude.CAM-SIMA/tools/cam_sima_buildtime/`. Fresh-case `case.build` median wall time: FPHYStest
51 s (generation 12, CIME ~9, atm compile span 22, link 5); SE 58 s (compile
36); MPAS kessler 158 s (compile 129, of which ~100 s is MPAS built partly
with `gmake -j 1`); cam4 suites (DEBUG) 120-235 s, generation 53-109 s. The
first case on a sharedlibroot adds 65-100 s (gptl, csm_share, CDEPS).
Rebuilding an existing case takes 35-60 s and recompiles only the ~30
generated/copied objects, nothing in core or the dycore -- so for iterating
on one case the incremental build already acts like a base library.

A prebuilt base library (infrastructure + dycore + unmodified schemes) would
save ~120 of 158 s for MPAS (libmpas has no dependency on generated code) but
only ~5-10 s for FPHYStest/SE: ~50 core modules and 43 of 57 SE dycore modules
transitively `use` per-suite generated modules (`physics_types`,
`cam_ccpp_cap`, `phys_vars_init_check`). Cheaper levers, roughly in order:
- generation runs twice per build (buildnml, then buildlib in 22 of 25 cases
  on a `cam_autogen.py` cache mismatch) and again at `case.run`: fixing the
  mismatch saves 5-9 s (FPHYStest) to ~26 s (cam4) per build;
- xdsl-ccpp generation for the cam4 suites is itself slow (53-109 s);
- MPAS built partly serially: parallelising it recovers much of ~100 s;
- 16 RRTMGP `mo_*.F90` files compile in suites that don't use RRTMGP;
- ~25 unchanged `ccpp_physics/*.F90` utility files are re-copied by every
  generation pass and so recompile on every rebuild;
- for regression suites: build cases in parallel (PBS job, `xargs -P`)
  and skip cases whose generated caps are byte-identical to the last passing
  run -- both outweigh everything above.

**To do: repeat the measurement for nvhpc** (xdsl56n once built). nvhpc
compiles more slowly and adds OpenACC for the GPU cases, so the compile
share -- and with it the case for a base library -- may be larger.

**`canonical-error-arg-order`** -- a generated group routine's dummy
arguments are collected from its schemes in call order, so its error
arguments take the order and names of the first scheme in that phase.
In kessler_test the reference's `kessler_test_final_physics_before_coupler`
ends `(..., errcode, errmsg)` (from `qneg_final`), while the package-cap
composite's ends `(..., errmsg, errflg)` (from `kessler_state_delete_finalize`),
and `col_start`/`col_end` move position the same way. Not a correctness
problem: scheme calls use keyword arguments, and `cam_ccpp_cap.F90` calls the
group routines positionally but from the same signature, with explicit
interfaces, so a swapped `integer`/`character` pair would fail to compile.
It is noise: any change to which scheme comes first in a phase reorders
the signature and shows up in reference/composite comparisons (s27b
`cam-sima-test` check). Fix: always put the error arguments last, as
`errmsg, errflg` with those names (capgen's convention), in every
generated routine. Changes the generated code of nearly every
configuration, so needs a baseline review.

**`package-scheme-list-order`** -- `cam_ccpp_cap.F90`'s `scheme_list`
(`ccpp_physics_suite_schemes`) takes a segment's schemes from its synthetic
scheme's `segment_schemes`, all at the position of the first segment that
contains them -- often an init-phase segment -- so they move ahead of host
schemes they follow in the suite: in kessler_test, `kessler_update` (in the init
segment with `kessler`) is listed 8th instead of 12th, ahead of
potential_temp_to_temp and the dry_to_wet hooks; in rrtmgp,
`solar_irradiance_data` moves from 14th to 19th. The only consumer is
CAM's `cam_read_ccpp_scheme_namelists` (`runtime_opts.F90`), so only the
order scheme namelists are read in changes; calls run in the right order.
Fix: build the list from the flattened call order of the run phase (the
order the XML suite gives), not from segment positions.

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
plumbing this would need (the `fparser2_to_meta.py`
extractor, `ArgumentOp`'s already-optional `standard_name`/`units`/
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
  results. **Re-scoped 2026-10-27:** the `array_layout = row_major` host
  `.meta` option already exists (commit `2111339`): the frontends parse
  it, `run_dispatch.py` inserts `RowMajorConvertOp`/`RowMajorWriteBackOp`
  (a Fortran `RESHAPE` in, write-back out) for rank >= 2 arguments, tested
  in `tests/filecheck/examples/end_to_end/array-layout-reshape.mlir`.
  What's still open: (1) no test combines `row_major` with `--bind-c`/the
  chost cap, and `cpp_interop.py` has no row-major handling, so it's
  unconfirmed that a C++ host calling through BIND(C) gets the conversion;
  (2) `RESHAPE` is CPU-only — GPU-resident data still has to arrive
  column-major; (3) a caller passing row-major data while declaring
  column-major can't be detected from raw pointers (document it).
  Verify/test first; it only grows if the chost path needs the conversion
  wired in. `multilanguage_limitations.md` §1.
- `chost-thread-safety` — **Thread safety — `ccpp_suite_state`** — concurrent C++ threads calling
  the chost cap race on the module-level suite-state variable. Safe today
  only because every C++ driver is single-threaded (eight under
  `examples/*/host_cpp/` plus `examples/kessler/host_ftn/driver_kessler_cpp.cpp`,
  checked 2026-10-27). Coordinate with `suite-state-full-match`, which
  rewrites the same variable.
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

## C++ scheme source annotations (a `!$ccpp` equivalent)

ID: `cxx-scheme-annotations` (added 2026-10-27)

A Fortran scheme can carry its CCPP metadata as `!$ccpp [name] key = value`
comment tags beside its declarations (`examples/advection_nometa`), and
`ccpp_generate_meta` / `py_api.ccpp_scheme_from_source` derive the `.meta`
from it via `fparser2_to_meta.py`; `memory_space = device` is derived from
the routine's own `!$acc present(...)` clauses. A C++ scheme
(`language = c++`) has no equivalent, so it always needs a hand-written
`.meta` — the duplication `dup-meta-shadow-elim`/`direct-fortran-ingest`
remove for Fortran stays for C++.

**Scope:**
1. **Annotation convention** (1-2 days): a comment form parallel to the
   Fortran one, e.g. `// $ccpp [name] key = value` beside each
   `extern "C"` entry point's parameters (comments survive any compiler and
   need no macros or attributes). Decide it with the C++ developers.
2. **Extractor** (3-5 days): parse `extern "C"` entry points and their
   parameters into the same `ArgumentTableOp`/`ArgumentOp` IR
   `fparser2_to_meta.py` produces, so `ccpp_generate_meta`'s
   `meta_from_module` writer is reused unchanged. Parser choice is the main
   decision: libclang (`clang.cindex`, accurate, new optional dependency —
   not installed here today) vs a restricted hand-written parser limited to
   the C-compatible subset an `extern "C"` signature allows.
3. **Type mapping** (1-2 days): C types to CCPP type/kind via
   `cpp_interop.py`'s existing Fortran↔C kind map in reverse
   (`double` → `real`/`kind_phys`, `int` → `integer`, `bool`/`int` →
   `logical`, `char*` + length → `character`). C source carries less than
   Fortran: a pointer has no rank and `const T*` only proves `intent(in)`,
   so `dim_names` and `intent` (`out` vs `inout`) must be tagged explicitly
   where Fortran infers them.
4. **Integration** (1-2 days): accept `.cpp`/`.cc`/`.hpp`/`.h` in
   `ccpp_generate_meta` and `py_api._load_scheme_file` (today it checks for
   `.f90`/`.f` only), setting `language = c++` automatically.
5. **Tests and example** (2-3 days): unit tests for the extractor, plus a
   tagged C++ twin of the `cxx-scheme-no-e2e-test` scheme whose generated
   `.meta` must match the hand-written one.
6. **Optional — `memory_space` derivation** (+3-5 days): derive
   `memory_space = device` from `#pragma acc ... present(...)`/`deviceptr(...)`
   in the scheme body, as the Fortran extractor does from `!$acc`. Kokkos
   schemes have no pragma to read and would need an explicit tag.

**Estimate:** 8-14 days (M-L), plus 3-5 for item 6.

**Dependencies:** do `cxx-scheme-no-e2e-test` first — it supplies the real
`extern "C"` scheme to annotate and a compiled test proving the generated
`.meta` is correct. Coordinate with `acc-meta-residency-check` (same
`memory_space`-from-pragmas logic, Fortran side) and with
`direct-fortran-ingest`, whose design should allow C++ sources too.

## Someday-maybe: EAMxx bridge automation (merged from `EAMxx/EAMxx-bridge-automation.md`, 2026-09-29)

ID: `eamxx-bridge-automation`

A design proposal (2026-07-29/08-06), not a record of work done — nothing
in it has been implemented, confirmed against current source (no
`variant` metadata tag, no `gpu_pointer_mode` property, no suite-coverage
checker script anywhere in `xdsl_ccpp/`). Full proposal lives in
CHANGELOG.md ("EAMxx bridge automation design proposal", ~L8764). Addresses: given both CPU and GPU (OpenACC)
Fortran variants of a scheme, how would xdsl-ccpp generate a real C++
host's *entire* bridge, not just the Fortran cap layer — motivated by
`EAMxx/kessler-README.md`'s real downstream integration (a different
repo, kept here as reference, not tracked as this repo's own backlog).
Three phases, recommended in this order:

- `eamxx-phaseA-variant-tag` — **Phase A — metadata `variant` tag** (moderate effort): teach the
  `.meta` format that a scheme has CPU and GPU (OpenACC) variants with
  different argument lists, so `suite_cap.py` can emit an `#ifdef`
  branch automatically instead of requiring a hand-patched meta per
  build config. CHANGELOG.md "Phase A -- Teach the metadata format..." (~L8800).
  **ON HOLD (2026-10-27): revisit motivation before any work starts.**
  This predates the XML auto-generation capability (suite XML derived
  from source-code analysis and directives), which may make the
  hand-maintained, divergent CPU/GPU `.meta` problem it targets
  obsolete. Re-check whether the motivating Kessler CPU/GPU signature
  divergence still exists and whether that capability already covers it
  before re-scoping or closing.
- `eamxx-phaseB-deviceptr` — **Phase B — explicit device-pointer contract** (small): a
  `gpu_pointer_mode = deviceptr` host-meta property so `cpp_interop.py`
  knows to pass GPU pointers straight through with zero data-staging
  directives, instead of silently assuming the scheme's own directives
  happen to do the right thing. CHANGELOG.md "Phase B -- Make the chost cap's device-pointer contract explicit" (~L8826). Related: this is a
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
  built. CHANGELOG.md "Phase C -- A new EAMxx AtmosphereProcess printer" (~L8843).

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

**ID: `scheme-io-capture-ddt-args`. Capture derived-type arguments.**
Added 2026-10-28. The capture pass's type scope is {integer, logical,
real(kind_phys)} x rank 0-3 (`scheme_io_capture_pass.py`, module
docstring); a derived-type argument is skipped, and the generated driver
declares and passes it uninitialized, so a scheme that reads one replays
wrong. First case: `geopotential_temp_run`'s `cprops`
(`ccpp_constituent_prop_ptr_t`), one of the 12 Kessler GPU ports
(`gpu-fphystest-kessler`); `qneg`'s properties appear only in its
timestep-final/final phases. Later cases: PUMAS's `micro_proc_rates`
(`proc_rates_type`, 119 allocatable components) and the rte-rrtmgp
objects (`gpu-fphystest-pumas`, `gpu-fphystest-rrtmgp`). Approach:
capture the components the scheme can read, found from the type's
definition (DDT `.meta` table, or fparser2 on the defining module):
allocatable and fixed-size numeric components recursively, allocation
status and bounds included; rebuild the object in the driver before the
call. The constituent properties are a pointer type wrapping
`ccpp_constituent_properties_t`, whose fields are set through
type-bound procedures, so a special case that captures the property
values (standard name, molar mass, water-species and dry/moist flags,
minimum value) and reconstructs them through the same setters may be
simpler than generic recursion. Polymorphic (`class(...)`) components
are out of scope at first.

**ID: `scheme-io-capture-group-replay`. Replay a whole generated group
subroutine.** Added 2026-10-28. Per-scheme replay checks one scheme's
numerics but not the data movement the generated suite cap does between
schemes on the GPU (`copy`/`present` regions, `update self/device`
around CPU schemes), which is where `gpu-sync-intent-aware` and
`constituent-device-residency` can go wrong. Instead, capture one
group's subroutine (e.g. `kessler_test_physics_before_coupler`) on the
CPU: every argument at entry, the suite cap's module variables the group
reads (`exner`, `theta`, `qv_dry`, `temp_prev`, ...), and every
`intent(out/inout)` value at exit. Generate a driver that restores them,
emits the residency the host cap would establish around the call
(`enter data`/`exit data` for the variables `GPUCcppCapPass` makes
resident; the generator knows them), calls the real generated group
subroutine linked with the real scheme objects, and compares against the
capture with the existing tolerance config. Built with `-acc` on a GPU
node, it runs in minutes; it generalizes `examples/kessler`'s
hand-written `run_cpu_gpu_parity.sh`/`check_cpu_gpu_parity.py` (six
global sums, bit-for-bit only, one suite) to any suite and whole fields.
Open: replay at the group level (driver emulates the host cap's
residency and constituent views) vs at `ccpp_physics_run` (covers the
host cap's own directives, but its inputs are host-model module
variables); suite state that crosses phases (capture it at group entry,
or replay timestep_init -> run -> timestep_final). Needs
`scheme-io-capture-ddt-args` for groups with derived-type arguments and
a decision on `scheme-io-capture-fixture-storage`. A flattened composite
has no subroutine of its own; package caps (2f) would allow
package-scoped replay later.


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
  - `composite-when-gating` — **S2-4, run-time conditional** (`with when(...)`) — deferred: gating
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
  - `composite-package-caps` — **2f/2g, per-package cap with GPU residency** — designed 2026-10-20,
    `composite_scheme_plan.md` §12 (segmentation at hooks in every phase,
    package-private state in the package cap, package caps never move data,
    kessler FPHYStest on GPU as the gate). Staged: 2f-1 segmentation
    analysis (`transforms/package_segments.py`, in `--list-package-scope`);
    2f-2 package caps on CPU; 2g on GPU; then a default-switch decision.
    2f-1 and 2f-2 done (`--package-caps`; RRTMGP pair s25f accepted
    2026-10-21); 2g done (Kessler gate, CPU s27b and GPU s29a passed
    2026-10-23). Remaining: the default switch -- deferred by the user
    (2026-10-23): XML stays the default until package caps are tested
    further -- and the open gaps below.
  - **ID: `chunked-column-slicing` (was `package-cap-private-slicing`). Resolved (2026-10-23)** — suite-owned arrays are now allocated over all columns and sliced to the current ones, in suite caps and package caps. CHANGELOG.md L12709.
  - `package-cap-loop-gpu-sync` — **no host/device syncs for calls inside a
    package-only loop; OpenACC only** — 2g-2's syncs
    (`_inject_suite_owned_gpu_update`, `_inject_segment_interface_gpu_update`)
    see only the error-guarded calls at a segment's top level, so a host
    scheme inside a loop held by a segment gets no `update self/device` (the
    suite cap has the same gap for its own variables). The syncs are emitted
    as OpenACC only; the OpenMP target backend has no package-cap
    equivalent. Plan §12, 2g-2.
  - `package-cap-runtime-loop-count` — **package-only loops with a run-time
    count are rejected** — `lower_packages._check_loops` refuses a loop that
    holds only package code unless its count is a literal, since the segment
    would need the count as an argument. RRTMGP's diagnostic loop holds a
    hook, so it stays in the suite cap and is unaffected. Plan §12, 2f-2.
  - `package-cap-tooling` — **consumers that don't look inside package
    caps** — constituents declared or used inside a package (correctness, if
    a package ever needs them), the `resolved_vars.json` details of segment
    arguments, scheme I/O capture and variable tracking (completeness). These
    passes see the synthetic segment schemes, not the schemes inside the
    `ccpp.package_cap` op. Plan §12, 2f-2.
  - `package-cap-segment-names` — **routine names repeat the phase** —
    non-run segments are named `<entry>_<phase>_<n>` (so they don't share a
    scheme name with run segment `<entry>_<n>`), and CCPP appends the phase
    again: `kessler_microphysics_init_1_init`, `rrtmgp_prepare_init_1_init`.
    Dropping the phase from the segment name would make run and init
    segments one scheme, called in both phases at both places; shortening
    needs a different segment-naming scheme. Cosmetic. Plan §12, 2g.
  - Behaviour-neutral differences from the flattened cap, found by the
    Kessler gate: `canonical-error-arg-order`, `package-scheme-list-order`
    (see "Other flagged issues").
  - `composite-multi-package-scoping` — **Scoping between packages** — needs a multi-package suite (e.g. a
    CAM4/QPC4 composite); the RRTMGP test has one package.
  - `composite-forloop-index` — **Loop index from `forLoop`** — would remove the `next_call` hook and the
    `rrtmgp_subcycle` counter.

  Cross-group agreement on the public radiation interface is governance,
  not a sizable task.

Upstream atmospheric_physics prerequisites (not xdsl tooling, recorded in
the plan doc):
- `rrtmgp-split-mixed-schemes` — split the four mixed host/package schemes
  (`rrtmgp_pre`, `rrtmgp_post`, `rrtmgp_inputs`, `*_calculate_fluxes`); the
  `rrtmgp_pre`/`rrtmgp_post` split is worked out in plan §11.6 (shared state
  13 → 2);
- `rrtmgp-heating-rate-names` — decide separate standard names for RRTMGP's
  heating rates and CAM's carried-over heating (the remaining 2 shared-state
  names);
- `rrtmgp-iter-num-column-bug` — fix the latent `iter_num` column-block bug
  in `rrtmgp_sw_gas_optics`/`rrtmgp_sw_rte`/`rrtmgp_lw_gas_optics`.

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
  `validate_source.compare_modules`, which compares type/rank/intent/
  optional/kind/extra args but not `memory_space`. Extend it to compare
  each argument's declared `memory_space` with what the routine's own
  `!$acc present(...)`/`deviceptr(...)` clauses imply (the derivation
  `fparser2_to_meta.py` already performs for `!$ccpp`-tagged sources), and
  report mismatches the same way (warn-only first, like the existing
  check). Subsumed by `acc-derive-memory-space` (2026-10-28), which
  derives `memory_space` from the source and warns where an explicit
  `.meta` value disagrees; do it as that item's first stage. Needs no GPU, would have flagged the `cld_ice` bug at generation
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
- `constituent-device-residency` — **Keep the constituents on the device
  across calls (performance).** Since `advected-constituent-host-binding`,
  `generate-gpu-data` wraps each scheme call that takes a
  `memory_space = device` constituent view in its own
  `!$acc data copy(<view>)` region
  (`GPUDataPass._emit_constituent_view_copies`). That is correct by
  construction but moves each view host→device→host on every device call,
  every step. Instead: `enter data` `lc_constituent_array` once in
  `<host>_ccpp_initialize_constituents` and `exit data delete` it in the
  deallocate routine; `update device` at physics entry and `update self`
  before returning to the host model; inside the suite, track per call
  which side last wrote each constituent and `update self`/`update device`
  only where that changes, run device calls under `present`. The hard
  part is aliasing: the same memory is reached through per-constituent
  views, the whole array (`ccpp_constituents`, e.g. `qneg`) and the
  tendency appliers, so the existing per-cap-var divergence routing
  (`find_diverged_capscratch_vars`) must treat a view and the whole array
  as overlapping. The host model's syncs also change if CAM's dynamics
  moves to the GPU. A missed sync gives silently wrong values, so it needs
  a GPU Kessler/advection regression with physics checks. Related: a
  device-resident whole-array `ccpp_constituents` arg still makes
  `lc_constituent_array` resident (`framework_var_residency`), and a
  per-call `copy` of a view of it then degenerates to `present` with no
  sync; no current suite has that mix. Worth doing once GPU physics
  coverage is large enough for the transfers to matter.
- `gpu-ddt-deep-copy-residency` — **Device residency for derived-type
  arguments with allocatable components.** Found 2026-10-28 while scoping
  a GPU PUMAS test. The GPU passes handle a derived type only through its
  members as host variables (`phys_state%T` etc., via
  `_build_ddt_resolution_maps` in `gpu_ccpp_cap_pass.py`); a whole
  derived-type argument gets no residency. Making one resident takes a
  deep copy: `enter data copyin(x)` of the parent, then `enter data` of
  each allocated component (attach), the reverse on exit, and `update`
  of individual components where the host reads or writes them (e.g.
  diagnostics). Motivating case: PUMAS's `micro_proc_rates`
  (`proc_rates_type`, `micro_pumas_diags.F90`, 119 allocatable
  components), produced by `micro_pumas_ccpp` and read by later schemes.
  `micro_pumas_tend`'s own data region `copyin`s it and `copyout`s its
  components every call; with the parent and components already present
  those clauses would move nothing. Needs: which components are
  device-resident, derived from clauses on the components at the entry
  point (as `micro_pumas_tend` writes them today,
  `copyout(proc_rates%qcsevap, ...)`) by `acc-derive-memory-space`
  rather than declared in `.meta`, the component list from the type's definition (the
  `.meta` DDT table, or fparser2 on the defining module), the generated
  enter/exit/update sequences for `--directive acc` and `omp`
  (`target enter data map(to:)` per component), and a GPU test that
  checks the data (an example scheme passing a DDT with allocatable
  components between two device schemes and a host scheme). Also
  covers OpenACC's lack of automatic deep copy for pointer components;
  allocatable-only first. Not needed for a first GPU PUMAS test (PUMAS
  copies its own data); needed for PUMAS to stay resident with its
  neighbours, alongside `constituent-device-residency`. Phase 2, for
  `gpu-fphystest-rrtmgp`: nested and polymorphic components (rte-rrtmgp's
  `class(ty_optical_props_arry)` inside the `*_ccpp` wrapper types, e.g.
  `lw_optical_props_clrsky%optical_props%tau`), which the RRTMGP
  wrappers deep-copy by hand today (`rrtmgp_lw_rte.F90`).

## GPU-enabling whole FPHYStest configurations

Goal (2026-10-28): run a whole FPHYStest suite on the GPU with its data
**resident within the physics run**: one transfer in at physics entry,
one out at exit, and `update self` only where a host consumer needs a
value (history output from the diagnostics schemes, which the existing
divergence routing in `generate-gpu-data` already emits). The dycore and
coupler stay on the CPU, so the entry/exit transfers remain. Acceptance:
the Physics Check against the testmod's snapshot passes (within the
cross-compiler tolerance, `nvhpc-ncdata-roundoff`), and an
`NV_ACC_NOTIFY=2` (or nsys) audit shows no host/device transfers between
entry and exit other than the diagnostics' `update self`.

PUMAS and RRTMGP today run every scheme on the CPU as far as the cap is
concerned: no `.meta` in either suite declares `memory_space = device`.
The GPU code that exists sits below the CCPP interface and moves its own
data per call. Kessler is partly there: its two physics schemes are
device-resident, and the cap syncs around the CPU schemes between them. No `.meta` file needs to change for this goal: residency
is derived from the Fortran source's OpenACC clauses
(`acc-derive-memory-space`), so the scheme work is adding OpenACC to the
`.F90` only.

- `gpu-fphystest-pumas` — **PUMAS FPHYStest
  (`cam/outfrq_pumas_derecho`, `suite_pumas.xml`, 18 schemes) fully
  GPU-resident.** PUMAS (the ESCOMP/PUMAS submodule,
  `schemes/pumas/pumas`, tag `pumas_cam-release_v1.41`) has ~170
  `!$acc parallel` regions one call below `micro_pumas_ccpp_run`, and
  one large `copyin`/`copyout` data region over `micro_pumas_tend`;
  every other scheme in the suite is CPU-only. The suite cap has no
  unit or kind conversions (checked 2026-10-28), so
  `gpu-conversion-residency` is not needed unless a port adds one.
  Steps, in order:
  1. `gpu-pumas-testmod` — PUMAS's own kernels on the GPU, cap
     unchanged.
  2. `pumas-module-props-device` — PUMAS's module-level props resident
     (upstream, ESCOMP/PUMAS).
  3. Add OpenACC directives (a data region with `present`/copy
     clauses for its arguments) to `micro_pumas_ccpp_run`, the routine
     `micro_pumas_ccpp.meta` describes, so `acc-derive-memory-space`
     sees them; it does not follow the call into `micro_pumas_tend`.
     `micro_pumas_ccpp.F90` lives in ESCOMP/PUMAS, so this is an
     upstream change (bundle `pumas-module-props-device` with it); no
     `.meta` change.
  4. `gpu-ddt-deep-copy-residency` — `micro_proc_rates`
     (`proc_rates_type`, 119 allocatable components; suite-owned in the
     generated cap).
  5. `constituent-device-residency` — PUMAS's main inputs (cloud
     liquid/ice, number concentrations, rain, snow, graupel) are
     constituents, copied per device call today.
  6. `gpu-port-pumas-interface-schemes` and
     `gpu-port-shared-utility-schemes` — the CPU schemes around PUMAS.
  7. Validation per the acceptance criteria above; tolerance per
     `pumas-ncdata-diffs` (its snapshot is intel-made).

  Optional: `gpu-ci` to keep it working.
- `gpu-fphystest-rrtmgp` — **RRTMGP FPHYStest
  (`cam/outfrq_rrtmgp_derecho[_gpu]`, `suite_rrtmgp.xml`, 40 calls / 38
  schemes) fully GPU-resident.** Further along than PUMAS in one way: a
  GPU testmod exists and passes (s34a). Only 4 schemes have OpenACC
  (`rrtmgp_{lw,sw}_gas_optics`, `rrtmgp_{lw,sw}_rte`), each wrapping
  the rte-rrtmgp kernels (`schemes/rrtmgp/ext`, earth-system-radiation
  v1.9.2) in hand-written deep-copy data regions; the other 34 are
  CPU-only. No unit or kind conversions in the suite cap (checked
  2026-10-28). Heavier than PUMAS: the data passed between schemes are
  rte-rrtmgp objects with nested, polymorphic components, and the
  shortwave diagnostic subcycle is a loop holding host schemes. Steps:
  1. `rrtmgp-wrapper-acc-trigger` — settle the build-flag question
     first.
  2. `acc-derive-memory-space` — derive the wrappers' device arguments
     (and derived-type components) from their existing data clauses.
  3. `gpu-ddt-deep-copy-residency`, including its phase 2 (nested,
     polymorphic components) for `ty_gas_concs_ccpp`,
     `ty_gas_optics_rrtmgp_ccpp`, `ty_optical_props_*_ccpp`,
     `ty_source_func_lw_ccpp` and `ty_fluxes_*_ccpp`.
  4. `constituent-device-residency` — the gas concentrations come from
     constituents.
  5. `suite-cap-loop-gpu-sync` — syncs for host schemes inside the
     subcycle loop (and `package-cap-loop-gpu-sync` for the composite
     package-cap variant).
  6. `gpu-port-rrtmgp-wrapper-schemes` and
     `gpu-port-shared-utility-schemes`.
  7. Validation per the acceptance criteria above, for both the XML and
     the composite (package-cap) suites.

  Optional: `gpu-ci`.
- `gpu-fphystest-kessler` — **Kessler FPHYStest
  (`cam/outfrq_kessler_derecho_gpu`, `suite_kessler_test.xml`, 16
  schemes) fully GPU-resident.** The smallest of the three and the
  natural first target. Today only `kessler` and `kessler_update` run on
  the device (their `.meta` declares `memory_space = device`); the other
  14 are CPU-only. The generated suite cap (checked 2026-10-28,
  `--directive acc`) therefore does about 30 `update self`/`update
  device` per step, one pair around each CPU scheme, plus a per-call
  `copy` of `qv`/`qc`/`qr` around `kessler_run`. No unit or kind
  conversions, so `gpu-conversion-residency` is not needed. The only
  derived-type argument is the constituent properties
  (`geopotential_temp_run`'s `cprops`), read-only host data; port
  `geopotential_temp` without putting it on the device (as for `qneg`,
  see `gpu-port-shared-utility-schemes`), so
  `gpu-ddt-deep-copy-residency` is not needed either.

  Order (decided 2026-10-28): build the fast test loop from the general
  scheme I/O capture generator rather than a Kessler-specific harness,
  so every later step is checked in minutes on a GPU node, with the
  CAM-SIMA regression only at milestones.
  1. `gpu-sync-intent-aware` — drop the redundant half of today's syncs.
     Generator-only, checked by pytest/FileCheck; confirm with one
     CAM-SIMA GPU Kessler case. Useful on its own, before any port.
  2. Capture gaps: `scheme-io-capture-ddt-args` (at least the
     constituent-properties case, for `geopotential_temp`) and a
     decision on `scheme-io-capture-fixture-storage` (local, gitignored
     fixtures regenerated from a CAM-SIMA capture run would do).
  3. `scheme-io-capture-group-replay` — replay
     `kessler_test_physics_before_coupler` on the GPU against a CPU
     capture: the check for the generator's cross-scheme data movement.
  4. `acc-derive-memory-space` — so the ported schemes need no `.meta`
     change (`kessler` and `kessler_update` keep their explicit
     `memory_space`, which then must agree with their source).
  5. `gpu-port-shared-utility-schemes`, Kessler's 12: the 10 state
     converters (`calc_exner`, `temp_to_potential_temp`,
     `potential_temp_to_temp`, `calc_dry_air_ideal_gas_density`,
     `wet_to_dry_*`, `dry_to_wet_*`), `qneg` and `geopotential_temp`.
     Each port checked by per-scheme replay on the GPU, and by group
     replay (the syncs around it should disappear).
  6. `constituent-device-residency` — `qv`/`qc`/`qr` and the whole
     array `qneg` takes. Riskiest step (a missed sync gives silently
     wrong values); checked by group replay.
  7. Validation per the acceptance criteria above, on every Kessler GPU
     testmod: FPHYStest, `se_cslam_gpu` and `se_cslam_multitape_gpu`,
     `kessler_mpas_derecho[_history]_gpu`, and the composite package-cap
     pair (`outfrq_kessler_composite_pkgcap_derecho_gpu`). Also run
     these after steps 1 and 5 as milestones.

  `sima_state_diagnostics` and `kessler_diagnostics` stay on the host
  (history output) and keep an `update self` before them throughout.

Supporting items (not tracked elsewhere):

- `gpu-sync-intent-aware` — **Skip host/device syncs an argument's
  intent makes redundant.** The per-call `update self`/`update device`
  pairs `generate-gpu-data` emits around a host scheme ignore intent:
  Kessler's cap pulls `exner` to the host before `calc_exner_run`,
  which only writes it (`intent(out)`), and pushes `cpair`, `rair`,
  `phis`, `dse`, `z`, `temp` and `precl` back after schemes that only
  read them (`intent(in)`). Emit `update self` only for `in`/`inout`
  and `update device` only for `out`/`inout`. The coalescing in
  `cap_shared.emit_coalesced_updates` must keep a run's boundary syncs
  correct when its calls differ in intent. Package caps' own syncs
  (`_inject_suite_owned_gpu_update`) need the same rule.

- `acc-derive-memory-space` — **Derive argument residency from the
  scheme's Fortran source instead of `.meta`.** The `.F90` already says
  which arguments the scheme uses on the device; `memory_space` in
  `.meta` duplicates it and can drift (the `cld_ice` bug above). The
  derivation exists in part: `_extract_device_resident_vars`
  (`transforms/fparser2_to_meta.py:365`) reads `present`/`deviceptr`/
  `copyin`/`copyout`/`copy` clauses, but only for `!$ccpp`-tagged
  sources whose `.meta` is generated, and only within the routine's own
  body. Extend it to:
  - every `--scheme-files` entry with hand-written `.meta`, using the
    `.meta`/`.F90` pairing `validate_fortran_sources` already does;
  - `default(present)` on a compute construct (Kessler): every
    argument referenced inside it is device-resident;
  - derived-type components named in clauses
    (`copyout(proc_rates%qcsevap)`,
    `copyin(sources%sources%lay_source)`), for
    `gpu-ddt-deep-copy-residency`.

  Classify `present`/`deviceptr` as "requires device" and the copy
  family as "either" (present-or-copy: the scheme works with host data
  and with data the cap keeps resident), and let the residency passes
  use that. An explicit `memory_space` in `.meta` stays as an override;
  a disagreement with the source warns. That warning is
  `acc-meta-residency-check`, which this item subsumes. Only the entry
  point's own body is read, never its callees: a scheme whose OpenACC
  sits deeper (PUMAS) gets directives added at the entry point, the
  routine its `.meta` describes. Without `-acc`
  in the scheme's build, the derived residency must be ignored (the
  directives are comments there); tie it to `--directive`.

- `gpu-pumas-testmod` — **First GPU PUMAS test.** New testmod
  `cam/outfrq_pumas_derecho_gpu`: the PUMAS `user_nl_cam` and snapshot
  plus `outfrq_kessler_derecho_gpu`'s xmlchanges (`OPENACC_GPU_OFFLOAD`,
  `GPU_TYPE=a100`, `NGPUS_PER_NODE=4`, `OVERSUBSCRIBE_GPU`) and an
  nvhpc entry in `testlist_cam.xml`. Check that the PUMAS `.F90` files
  get `-acc` in the build, and whether the snapshot needs a looser
  tolerance on the GPU. Exercises PUMAS's own data regions only.
  Set up 2026-10-28 (CAM-SIMA, uncommitted): standalone testmod with
  `min_difference = 5e-10` (the nvhpc GPU flags match GPU to CPU results), test `SMS_Ln2` nvhpc (not `SMS_D`: PUMAS
  gets `-acc` only when `DEBUG=FALSE` in `Depends.nvhpc`); awaiting its
  first run in the next regression sweep.
- `pumas-module-props-device` — **ESCOMP/PUMAS: make `mg_*_props`
  device-resident once.** Add the six `MGHydrometeorProps` module
  variables to the existing `!$acc declare create(...)`
  (`micro_pumas_utils.F90:289`) and `!$acc update device(...)` (`:390`,
  after they are set). Flat type, set only at init; `micro_pumas_tend`'s
  `copyin` then finds them present. Bit-for-bit; also applies to
  ESCOMP/CAM. Small gain, so bundle it with step 3 of
  `gpu-fphystest-pumas`.
- `gpu-port-pumas-interface-schemes` — **OpenACC ports of the PUMAS
  suite's own per-step CPU schemes** (5; see `gpu-port-scheme-checklist`):
  `micro_pumas_ccpp_dimensions_pre/post`, `pumas_post_main`,
  `micro_pumas_ccpp_optics_limiter` (atmospheric_physics), and
  entry-point directives in `micro_pumas_ccpp_run` (ESCOMP/PUMAS; its
  kernels are one call down). The suite's cloud-fraction schemes,
  `to_be_ccppized_temporary`, the stubs and `pumas_pre_main` are init- or
  register-only, so they need no port; `sima_state_diagnostics` stays on
  the host (history). Each port adds
  `!$acc` kernels to the `.F90` only (residency is derived by
  `acc-derive-memory-space`; the `.meta` is unchanged) and keeps the CPU
  path (directives are comments without `-acc`).
- `gpu-port-shared-utility-schemes` — **atmospheric_physics: OpenACC
  ports of the utility schemes every suite uses**:
  `apply_constituent_tendencies`, `apply_heating_rate`, `qneg`,
  `geopotential_temp`,
  `clamp_number_concentrations`, `calculate_net_heating`,
  `tropopause_find`, and the 10 state converters in
  `schemes/utilities/state_converters.F90` (`calc_exner`,
  `temp_to_potential_temp`, `potential_temp_to_temp`,
  `calc_dry_air_ideal_gas_density`, `wet_to_dry_*`, `dry_to_wet_*`;
  pointwise loops), plus the test scheme `initialize_constituents`
  (18 in all; see `gpu-port-scheme-checklist`). Shared by all three
  configurations; `apply_tendency_of_*_wind` joins the list for the full
  cam suites. `qneg` reads the constituent properties
  (`ccpp_constituent_prop_ptr_t`), a pointer derived type; port it with
  the minimum values passed as a plain array instead of putting the
  properties on the device. A regression across every suite that uses
  them, CPU and GPU.
- `gpu-port-rrtmgp-wrapper-schemes` — **atmospheric_physics: OpenACC
  ports of RRTMGP's 21 per-step CPU-only CCPP schemes** (see
  `gpu-port-scheme-checklist`: inputs/pre/post, cloud and aerosol
  optics, McICA subcolumn generation, flux and heating-rate calculation,
  gas-optics pre, solar variability, the subcycle counter).
  `solar_irradiance_data`, the three init-only `*_setup` schemes and the
  four `*_diagnostics` stay on the host. McICA's random numbers
  must stay reproducible against the snapshot (generate on the host and
  copy, or a matching device generator).
- `suite-cap-loop-gpu-sync` — **Host/device syncs for host schemes
  inside a suite-cap loop.** The suite-cap half of
  `package-cap-loop-gpu-sync`'s gap: `generate-gpu-data` only sees
  error-guarded calls at a function's top level, so a host scheme inside
  a `<subcycle>` loop gets no `update self/device`. Latent until a
  device scheme shares a loop with a host scheme (RRTMGP's shortwave
  diagnostic subcycle, during `gpu-fphystest-rrtmgp`).
- `gpu-port-scheme-checklist` — **Per-scheme status for the Kessler,
  PUMAS and RRTMGP FPHYStest GPU work** (computed 2026-10-28 from
  `test/test_suites/suite_{kessler_test,pumas,rrtmgp}.xml`). The three
  suites use 66 distinct schemes. 6 already run on the device:
  `kessler`, `kessler_update` (Kessler) and `rrtmgp_{lw,sw}_gas_optics`,
  `rrtmgp_{lw,sw}_rte` (RRTMGP). The other 60 are CPU-only: 44 need a
  port (18 shared utilities, 5 PUMAS, 21 RRTMGP), 9 are init- or
  register-only and need none, and 7 stay on the host (the 6
  history-diagnostics schemes and `solar_irradiance_data`). "CPU-only"
  means no `!$acc` in the scheme's `.F90` and no `memory_space = device`
  in its `.meta`; a port adds `!$acc` to the routine the `.meta`
  describes (`acc-derive-memory-space`). Tick a row off when its port
  is merged.

| Scheme | File | Needed by | Port item |
|---|---|---|---|
| `apply_constituent_tendencies` | `schemes/utilities/physics_tendency_updaters.F90` | pumas | `gpu-port-shared-utility-schemes` |
| `apply_heating_rate` | `schemes/utilities/physics_tendency_updaters.F90` | pumas, rrtmgp | `gpu-port-shared-utility-schemes` |
| `calc_dry_air_ideal_gas_density` | `schemes/utilities/state_converters.F90` | kessler | `gpu-port-shared-utility-schemes` |
| `calc_exner` | `schemes/utilities/state_converters.F90` | kessler | `gpu-port-shared-utility-schemes` |
| `calculate_net_heating` | `schemes/rrtmgp/utils/calculate_net_heating.F90` | rrtmgp | `gpu-port-shared-utility-schemes` |
| `clamp_number_concentrations` | `schemes/utilities/clamp_number_concentrations.F90` | pumas | `gpu-port-shared-utility-schemes` |
| `dry_to_wet_cloud_liquid_water` | `schemes/utilities/state_converters.F90` | kessler | `gpu-port-shared-utility-schemes` |
| `dry_to_wet_rain` | `schemes/utilities/state_converters.F90` | kessler | `gpu-port-shared-utility-schemes` |
| `dry_to_wet_water_vapor` | `schemes/utilities/state_converters.F90` | kessler | `gpu-port-shared-utility-schemes` |
| `geopotential_temp` | `schemes/utilities/geopotential_temp.F90` | kessler, pumas, rrtmgp | `gpu-port-shared-utility-schemes` |
| `initialize_constituents` (test scheme) | `test/test_schemes/initialize_constituents.F90` | pumas, rrtmgp | `gpu-port-shared-utility-schemes` |
| `potential_temp_to_temp` | `schemes/utilities/state_converters.F90` | kessler | `gpu-port-shared-utility-schemes` |
| `qneg` | `schemes/utilities/qneg.F90` | kessler, pumas | `gpu-port-shared-utility-schemes` |
| `temp_to_potential_temp` | `schemes/utilities/state_converters.F90` | kessler | `gpu-port-shared-utility-schemes` |
| `tropopause_find` | `schemes/tropopause_find/tropopause_find.F90` | rrtmgp | `gpu-port-shared-utility-schemes` |
| `wet_to_dry_cloud_liquid_water` | `schemes/utilities/state_converters.F90` | kessler | `gpu-port-shared-utility-schemes` |
| `wet_to_dry_rain` | `schemes/utilities/state_converters.F90` | kessler | `gpu-port-shared-utility-schemes` |
| `wet_to_dry_water_vapor` | `schemes/utilities/state_converters.F90` | kessler | `gpu-port-shared-utility-schemes` |
| `micro_pumas_ccpp_dimensions_post` | `schemes/pumas/micro_pumas_ccpp_dimensions_post.F90` | pumas | `gpu-port-pumas-interface-schemes` |
| `micro_pumas_ccpp_dimensions_pre` | `schemes/pumas/micro_pumas_ccpp_dimensions_pre.F90` | pumas | `gpu-port-pumas-interface-schemes` |
| `micro_pumas_ccpp_optics_limiter` | `schemes/pumas/micro_pumas_ccpp_optics_limiter.F90` | pumas | `gpu-port-pumas-interface-schemes` |
| `pumas_post_main` | `schemes/pumas/pumas_post_main.F90` | pumas | `gpu-port-pumas-interface-schemes` |
| `micro_pumas_ccpp` | `schemes/pumas/pumas/micro_pumas_ccpp.F90` | pumas | `gpu-port-pumas-interface-schemes` (entry-point directives; ESCOMP/PUMAS) |
| `aerosol_optics_zero_stub` | `schemes/chemistry/aerosol_optics_zero_stub.F90` | rrtmgp | `gpu-port-rrtmgp-wrapper-schemes` |
| `rrtmgp_constituents` | `schemes/rrtmgp/rrtmgp_constituents.F90` | rrtmgp | `gpu-port-rrtmgp-wrapper-schemes` |
| `rrtmgp_dry_static_energy_tendency` | `schemes/rrtmgp/utils/rrtmgp_dry_static_energy_tendency.F90` | rrtmgp | `gpu-port-rrtmgp-wrapper-schemes` |
| `rrtmgp_inputs` | `schemes/rrtmgp/rrtmgp_inputs.F90` | rrtmgp | `gpu-port-rrtmgp-wrapper-schemes` |
| `rrtmgp_lw_aerosols` | `schemes/rrtmgp/rrtmgp_lw_aerosols.F90` | rrtmgp | `gpu-port-rrtmgp-wrapper-schemes` |
| `rrtmgp_lw_calculate_fluxes` | `schemes/rrtmgp/rrtmgp_lw_calculate_fluxes.F90` | rrtmgp | `gpu-port-rrtmgp-wrapper-schemes` |
| `rrtmgp_lw_calculate_heating_rate` | `schemes/rrtmgp/rrtmgp_lw_calculate_heating_rate.F90` | rrtmgp | `gpu-port-rrtmgp-wrapper-schemes` |
| `rrtmgp_lw_cloud_optics` | `schemes/rrtmgp/rrtmgp_lw_cloud_optics.F90` | rrtmgp | `gpu-port-rrtmgp-wrapper-schemes` |
| `rrtmgp_lw_gas_optics_pre` | `schemes/rrtmgp/rrtmgp_lw_gas_optics_pre.F90` | rrtmgp | `gpu-port-rrtmgp-wrapper-schemes` |
| `rrtmgp_lw_mcica_subcol_gen` | `schemes/rrtmgp/rrtmgp_lw_mcica_subcol_gen.F90` | rrtmgp | `gpu-port-rrtmgp-wrapper-schemes` |
| `rrtmgp_post` | `schemes/rrtmgp/rrtmgp_post.F90` | rrtmgp | `gpu-port-rrtmgp-wrapper-schemes` |
| `rrtmgp_pre` | `schemes/rrtmgp/rrtmgp_pre.F90` | rrtmgp | `gpu-port-rrtmgp-wrapper-schemes` |
| `rrtmgp_subcycle` | `schemes/rrtmgp/rrtmgp_subcycle.F90` | rrtmgp | `gpu-port-rrtmgp-wrapper-schemes` |
| `rrtmgp_sw_aerosols` | `schemes/rrtmgp/rrtmgp_sw_aerosols.F90` | rrtmgp | `gpu-port-rrtmgp-wrapper-schemes` |
| `rrtmgp_sw_calculate_fluxes` | `schemes/rrtmgp/rrtmgp_sw_calculate_fluxes.F90` | rrtmgp | `gpu-port-rrtmgp-wrapper-schemes` |
| `rrtmgp_sw_calculate_heating_rate` | `schemes/rrtmgp/rrtmgp_sw_calculate_heating_rate.F90` | rrtmgp | `gpu-port-rrtmgp-wrapper-schemes` |
| `rrtmgp_sw_cloud_optics` | `schemes/rrtmgp/rrtmgp_sw_cloud_optics.F90` | rrtmgp | `gpu-port-rrtmgp-wrapper-schemes` |
| `rrtmgp_sw_gas_optics_pre` | `schemes/rrtmgp/rrtmgp_sw_gas_optics_pre.F90` | rrtmgp | `gpu-port-rrtmgp-wrapper-schemes` |
| `rrtmgp_sw_mcica_subcol_gen` | `schemes/rrtmgp/rrtmgp_sw_mcica_subcol_gen.F90` | rrtmgp | `gpu-port-rrtmgp-wrapper-schemes` |
| `rrtmgp_sw_solar_var` | `schemes/rrtmgp/rrtmgp_sw_solar_var.F90` | rrtmgp | `gpu-port-rrtmgp-wrapper-schemes` |
| `rrtmgp_variables` | `schemes/rrtmgp/rrtmgp_variables.F90` | rrtmgp | `gpu-port-rrtmgp-wrapper-schemes` |
| `cloud_fraction_options` | `schemes/cloud_fraction/cloud_fraction_options.F90` | pumas | none: init/register only |
| `clubb_stub` (test scheme) | `test/test_schemes/clubb_stub.F90` | pumas | none: init/register only |
| `compute_cloud_fraction_two_moment` | `schemes/cloud_fraction/compute_cloud_fraction_two_moment.F90` | pumas | none: init/register only |
| `hetfrz_classnuc_stub` | `schemes/microp_aero/hetfrz_classnuc_stub.F90` | pumas | none: init/register only |
| `pumas_pre_main` | `schemes/pumas/pumas_pre_main.F90` | pumas | none: init/register only |
| `rrtmgp_cloud_optics_setup` | `schemes/rrtmgp/utils/rrtmgp_cloud_optics_setup.F90` | rrtmgp | none: init/register only |
| `rrtmgp_inputs_setup` | `schemes/rrtmgp/rrtmgp_inputs_setup.F90` | rrtmgp | none: init/register only |
| `rrtmgp_sw_solar_var_setup` | `schemes/rrtmgp/rrtmgp_sw_solar_var_setup.F90` | rrtmgp | none: init/register only |
| `to_be_ccppized_temporary` | `schemes/utilities/to_be_ccppized_temporary.F90` | pumas | none: init/register only |
| `kessler_diagnostics` | `schemes/sima_diagnostics/kessler_diagnostics.F90` | kessler | none: stays on host (history output) |
| `rrtmgp_cloud_diagnostics` | `schemes/sima_diagnostics/rrtmgp_cloud_diagnostics.F90` | rrtmgp | none: stays on host (history output) |
| `rrtmgp_diagnostics` | `schemes/sima_diagnostics/rrtmgp_diagnostics.F90` | rrtmgp | none: stays on host (history output) |
| `rrtmgp_lw_diagnostics` | `schemes/sima_diagnostics/rrtmgp_lw_diagnostics.F90` | rrtmgp | none: stays on host (history output) |
| `rrtmgp_sw_diagnostics` | `schemes/sima_diagnostics/rrtmgp_sw_diagnostics.F90` | rrtmgp | none: stays on host (history output) |
| `sima_state_diagnostics` | `schemes/sima_diagnostics/sima_state_diagnostics.F90` | kessler, pumas | none: stays on host (history output) |
| `solar_irradiance_data` | `schemes/radiation_utils/solar_irradiance_data.F90` | rrtmgp | none: likely stays on host (1-D spectral data from file, no column loop; confirm), small `update device` of its output |

## Design problems: re-derived information and special-casing (review 2026-10-28)

Found while fixing `advected-constituent-host-binding` and
`rk-top-lev-host-match`, which had one root cause: a decision one pass made
(how the suite cap names, merges and classifies arguments) was not recorded
in the IR, so later passes re-derived it from scheme metadata keyed by local
name, each with its own collision rules, and disagreed with it. Since
`rk-top-lev-host-match`, suite subroutines carry each argument's standard
name and dimension names as `arg_attrs` (`suite_arg_attrs`,
`SUITE_ARG_STD_NAME`/`SUITE_ARG_DIM_NAMES`); the items below move the
remaining consumers onto it and remove the guessing; open items are taken
opportunistically.

- `lifecycle-cap-arg-std-names` — resolved 2026-10-28 (it was
  `ccpp_register`/`ccpp_init`/`ccpp_final`, not the group phases).
  CHANGELOG.md L13011.
- `cap-oracle-check` — resolved 2026-10-28: `xdsl_ccpp/tools/cap_oracle.py`
  (`diff`, `capgen`), usage in DEVELOPERS.md. CHANGELOG.md L12972.
- `cap-oracle-ci` — **Run cap_oracle in CI.** Today it runs on Derecho
  against built cases. In CI it needs the generator inputs (committed
  fixtures of the suites' `.meta`/suite files, or a CAM-SIMA checkout with
  submodules) and, for `capgen`, a ccpp_framework checkout. Start with
  `diff` against the PR's base on a fixed set of suites.
- `cap-oracle-kessler-capgen` — **capgen cannot check Kessler.** capgen
  rejects xdsl-only metadata (`memory_space` in `kessler.meta`), so
  `cap_oracle capgen` reports the Kessler suites as NO CAPGEN. Give capgen
  copies of the `.meta` files with xdsl-only properties removed; they do not
  change what CPU caps should do.
- `gpu-data-arg-std-names` — resolved 2026-10-28. CHANGELOG.md L13038.
- `chost-arg-std-names` — resolved 2026-10-28. CHANGELOG.md L13091.
- `cap-oracle-examples` — resolved 2026-10-28. CHANGELOG.md L13067.
- `arg-flags-not-in-names` — resolved 2026-10-29. CHANGELOG.md L13116.
- `raw-fortran-in-ir` — resolved 2026-10-29. CHANGELOG.md L13162.
- `fortran-decls-as-text` — resolved 2026-10-29. CHANGELOG.md L13210.
- `fortran-exprs-as-text` — resolved 2026-10-29. CHANGELOG.md L13259.
- `cpp-text-in-ir` — resolved 2026-10-29. CHANGELOG.md L13324.
- `active-condition-ir` — resolved 2026-10-30. CHANGELOG.md L13406.
- `gpu-debug-text` — resolved 2026-10-30. CHANGELOG.md L13371.
- `printer-trailing-whitespace` — resolved 2026-10-30. CHANGELOG.md L13406.

To re-measure target-language text in the IR: scan the transformed IR's string properties
(`tests/unit/test_ir_names_are_identifiers.py` does this for the
completed_ir goldens and a C++-host example) and the string literals (not docstrings) of
`xdsl_ccpp/transforms/` for Fortran/C++ syntax (`::`, `intent(`,
`.true.`, `/=`, statement keywords, intrinsic calls, `!$`), excluding the
frontends that parse Fortran input (`fparser2_to_meta`,
`fortran_preprocess`, `validate_source`, `module_dependency_resolver`),
diagnostic messages and single-token metadata keys.
- `suite-cap-mode-flags` — **One generator, several products.** The
  suite-cap generator branches on `instance_local_name` (71 uses),
  `physics_mode` (38), `cam_host` (18), `emit_scheme_calls` (16) and
  `getattr(self, "generating_package_cap", False)`. Special-purpose paths
  accumulate there (e.g. the removed `ConstituentsMixin`). Separate the
  products (suite cap, package cap, CAM wrappers) over a shared core.
- `split-large-generators` — **Very large functions** where special cases
  collect: `_generate_constituent_api` (904 lines),
  `_generate_lifecycle_fn` (657), `_generate_ccpp_cap_module` (454),
  `_build_chost_ftn_text` (404), `_generate_cam_lifecycle_wrappers` (354).
  Split by responsibility when touched. Related: comments and docstrings
  often narrate history (review rounds, earlier fix attempts) rather than
  describe the current design; trim them in the same edits.
- `dead-code-coverage` — resolved 2026-10-30. CHANGELOG.md L13467.
- `active-pointer-association` — **Pass `active`-gated optional
  arguments by pointer association, as capgen-v1 does.** xdsl-ccpp wraps
  the scheme call in one `ActiveCheckOp` per distinct condition and emits a
  copy of the call for each combination, omitting the inactive arguments
  (`suitecap/call_sequence.py` `_build_active_gated_call_ops`): 2**N calls
  for N conditions. capgen-v1 (`capgen/generator/suite_resolver.py`
  transform cases 2 and 4, `group_cap.py`) makes one call: each optional
  argument is passed through a pointer wrapper (types generated in
  `ccpp_<suite>_types.F90`), associated with the host variable (or a
  transform temporary declared `target`) when the condition holds and
  nullified otherwise; a disassociated pointer passed to a non-pointer
  optional dummy is not present. It also guards a non-optional argument
  whose host declares `active`: if the condition is false it sets
  errflg/errmsg and returns. xdsl-ccpp has no such guard. Build it from
  `scf.if`, `PointerAssignOp` and `NullifyPointerOp`; host variables must
  then be `target`s. Changes var_compat, instances and advection output.
- `py-api-docs-current-style` — **The documented Python API is the old
  style.** README's Python API section teaches `@ccpp_scheme`,
  `ccpp_scheme_from_meta` and `emit_ir`; CAM-SIMA's suites-py use
  `ccpp_scheme_ref`, `ccpp_composite`, `ccpp_package`, `forLoop` and
  `export_suite`. `emit_ir` is documented in py_api as the older name for
  `export_suite` but is still used by the README and the in-repo example
  scripts (`examples/{helloworld,advection,ddthost}/..._py.py`, run by the
  `-py` FileCheck goldens). `ccpp_scheme_from_source` and the script-side
  `--scheme-files` loading run only when a suite script is executed
  directly, never through `ccpp_dsl --py` (which merges the `.meta` files
  itself); only `test_py_api_composition.py` calls them. Rewrite the README
  section in the CAM-SIMA style, move the example scripts to
  `export_suite`, deprecate then remove `emit_ir`, and decide whether the
  standalone script path stays supported. Found by `dead-code-coverage`.
