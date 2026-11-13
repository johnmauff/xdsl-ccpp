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
| `zm-number-concentration-compiler-diffs` | 2-5 days (number concentrations in the zm h1 output and a pairwise cprnc first; multi-step gnu/intel/nvhpc comparison of the number concentrations, DEBUG and NaN-init runs, read ZM's convtran/clamp/floor path for a real defect; decide tolerance or fix with the user) | S |
| `cap-clause-order-nondeterministic` | <1 day (find the set iteration; sort; check cap_oracle diffs are clean) | XS |
| `mcsp-number-concentration-compiler-diffs` | 1-3 days once `zm-number-concentration-compiler-diffs` is understood (likely the same cause; add the number concentrations to MCSP's h1 output, compare gnu/intel/nvhpc against the intel snapshot, confirm the ZM fix covers it) | XS-S |
| `suites-py-xml-omissions` | <1 day (raise two likely cam5 XML omissions with the atmospheric_physics developers) | XS |
| `rrtmgp-wrapper-acc-trigger` | 1-2 days (one confirming GPU run, then a one-line `Depends.nvhpc` change if confirmed) | XS |
| `nvhpc-gpu-build-flags-redesign` | 7-12 days: inventory 1-1.5, design 1-2, implement 2-3, verify (SE/multitape/MPAS CPU+GPU pairs, gnu, nvhpc regression) 2-3.5, upstream ccs_config/cime PRs 1-2; plus 2-6 weeks elapsed for upstream review. Risks: new hidden dependencies, upstream design pushback, narrowing `CCPP_CAP_OBJS` changes host-file flags | M |
| `gpu-acc-file-manifest` | 4-7 days: xdsl-ccpp manifest 1, CAM-SIMA buildlib + ccs_config rule 1-2, scheme-side GPU marking (metadata or suite) 1-2, verify (nvhpc CPU baseline + GPU regression) 1-2; plus upstream review if taken to ccs_config/CAM-SIMA | S-M |
| `cam-sima-build-time` | 3-6 days per lever (nvhpc measurement first) | S-M |
| `ccpp-opt-small-speedups` | 1-2 days (skip the pre-pipeline verify; the `getAttr`/`_find_loop_upper_bound` hot spots; function-level imports in hot loops) | XS |
| `in-process-pipeline` | 5-10 days (frontend + passes in one process; design for global state, `sys.exit` error paths, CLI-driven tests/goldens) | M |
| `suite-owned-framework-var` | 1-2 days (exclude framework cap variables such as the constituent tendencies from the suite-owned sweep) | XS |
| `cpu-cap-acc-updates` | 1-2 days (emit suite-owned and segment syncs only with `--directive`, or guard them; caps of CPU builds change) | XS |
| `registry-scheme-objects` | ~1 day read-only survey first; then 3-5 days for a suite-aware `metadata_file` filter, or more (unsized) to move scheme objects into package-owned state; both upstream CAM-SIMA changes needing design agreement | S-L |
| `package-shared-state-per-suite` | <1 day (narrow the warning in `package_scope.py`, note at `--verbose 2` otherwise, a unit test) | XS |
| `cam-autogen-repeat-generation` | <1 day (fix and regression test done locally; open the upstream PR) | XS |
| `gpu-ci` | 10-20 days engineering (once a GPU runner is chosen -- the infrastructure decision itself is unquantifiable) | M-L |
| `gpu-conversion-residency` | 2-5 days (after `xdsl-upgrade`) | S-M |
| `xdsl-upgrade` | 2-5 days, depending on API changes | S-M |
| `constituent-device-residency` | 5-10 days (enter/exit and entry/exit syncs are small; the per-call last-writer tracking across views, the whole array and tendency appliers is most of it; plus a GPU regression) | M |
| `constituent-residency-from-source` | 3-5 days (classifier: `enter`/`exit data` and phase-level `update` in a scheme's lifecycle routines mean "manages residency"; precedence over the automatic rule; a residency scheme and its metadata; Kessler GPU test) | S |
| `gpu-ddt-deep-copy-residency` | not planned (2026-11-02): schemes move their own derived-type data | -- |
| `gpu-fphystest-pumas` | umbrella, ~20-35 days in total: the sum of its steps below plus `constituent-device-residency`; plus ESCOMP/PUMAS review time | L-XL |
| `gpu-fphystest-rrtmgp` | umbrella, ~35-55 days in total: its steps below plus `constituent-device-residency` (items shared with `gpu-fphystest-pumas` count once if both are done) | XL |
| `pumas-module-props-device` | code done and verified (2026-11-12); only the ESCOMP/PUMAS PR and its review left | XS |
| `pumas-proc-rates-allocate-once` | 1-3 days (lazy allocate in the run or an init dimension, `inout` intent, device copies with the allocation, recapture, CPU/GPU replay and PUMAS GPU test) plus ESCOMP/PUMAS review; first a profile showing it matters | XS-S |
| `gpu-port-shared-utility-schemes` | 6-12 days (small kernels incl. the 10 state converters, but used by every suite: regression on CPU and GPU) | M |
| `gpu-port-dme-adjust` | 1-2 days (host-side constituent mask, one column-parallel kernel, capture replay CPU+GPU; on hold) | XS |
| `gpu-port-wv-saturation` | 2-5 days after the recapture (device `qsat` path through `wv_saturation`: `!$acc routine seq`, constants already on the device; `wv_sat_methods` already has its directives; tested through the `zm_conv_evap` GPU replay) | S |
| `pumas-refl-single-division-upstream` | <1 day plus PUMAS review (one-file PR, submodule bump) | XS |
| `zm-convr-init-gathered-outputs` | <1 day plus review (6 lines, regression run) | XS |
| `gpu-port-zm-convr` | 8-15 days after `gpu-port-wv-saturation` (~2640-line scheme; gather/scatter over convecting columns, scalar `qsat_hPa` inside column loops, module state from `zm_conv_options`; GPU replay in capture_zm) | M |
| `gpu-port-gw-orographic` | 8-15 days (`Coords1D` device handling or plain-array interface, `gw_common` path incl. `gw_drag_prof`/`gw_diffusion` tridiagonal solves as device routines, both GW schemes; full-model test only until their drivers build) | M |
| `gpu-history-accumulate` | design project first (user, 2026-11-10): a design document for device-resident history buffers before any estimate; implementation was guessed at 6-12 days plus upstream review | M-L |
| `gpu-port-vertical-diffusion-simple` | 2-4 days (nine small column/pointwise schemes, three replays CPU and GPU, hb_vdiff/uw_vdiff GPU FPHYStest) | S |
| `gpu-port-vertical-diffusion-solver` | 6-12 days (plain-array device path for `fin_vol_solve`/`TriDiagDecomp`, bit-for-bit with the operator code; three schemes; shared with `gpu-port-gw-orographic`) | M |
| `gpu-port-tropopause-find` | 2-3 days (~900 lines of column code, module constants on the device, optional arguments, host callers kept working; rk_stratiform and rrtmgp replays) | S |
| `tropopause-find-untested-algorithms` | 1-3 days (a capture or replay that selects analytic, Stobie and WMO through `tropopause_findWithBackup`, or a pFUnit test; then port them like the other five and check CPU and GPU) | XS-S |
| `cap-pulls-unwritten-device-data` | 1-3 days (track per variable whether any device scheme can write it; skip the pull at function/block entry when none does; cap_oracle cam4; GPU regression) | XS-S |
| `gpu-port-kessler-energy-utilities` | ~1 day (three pointwise kernels with present-or-copy clauses, `GPU_SCHEME_OBJS`, FKESSLER GPU run; optional capture replays) | XS |
| `gpu-port-check-energy-chng` | 4-8 days (port CAM's `cam_thermo` `get_hydrostatic_energy` and its module data to the device, keep error printing on the host, plus `check_energy_zero_fluxes`; FKESSLER GPU and cam-suite regressions) | S-M |
| `gpu-fphystest-kessler` | umbrella, ~16-28 days left: Kessler's 12 of `gpu-port-shared-utility-schemes`, `dropsonde-cuda-gdb-device-read` and `constituent-device-residency` (most shared with the PUMAS and RRTMGP umbrellas; count once) | L-XL |
| `cap-oracle-ci` | 3-6 days (committed input fixtures or a CAM-SIMA checkout in CI; a ccpp_framework checkout for `capgen`) | S |
| `cap-oracle-kessler-capgen` | 1-2 days | XS |
| `split-large-generators` | 10-20 days, opportunistic (the five 350-900-line generator functions) | L |
| `py-api-docs-current-style` | 2-4 days (README Python-API section rewrite, `emit_ir` deprecation, in-repo example scripts and the goldens that run them) | S |
| `active-pointer-association` | 4-8 days (pointer wrapper types or typed local pointers, call-site association/nullify, transform temps as targets, the non-optional guard, regenerate var_compat/instances/advection goldens, compile and run the examples) | S-M |
| `gpu-port-rrtmgp-wrapper-schemes` | 12-20 days (21 schemes, most manipulating rte-rrtmgp objects; McICA reproducibility) | L |
| `gpu-port-aerosol-optics` | 5-10 days plus ESCOMP review (host gather of per-bin properties from the polymorphic `aerosol_properties`/`aerosol_state` objects into plain arrays, device kernels for the column/level/wavelength loops, species-type flags precomputed; cam4 and rrtmgp replays) | S-M |
| `gpu-port-scheme-checklist` | tracking table only; the work is sized in the three `gpu-port-*` rows | -- |
| `suite-cap-loop-gpu-sync` | 3-5 days | S |
| `example-gpu-build-flags` | 1-2 days (`-acc` for the OpenACC examples, offload flags at link time, `OMP_TARGET_OFFLOAD=MANDATORY`/kernel check in the GPU tests; then fix whatever starts running on the GPU) | XS-S |
| `scheme-io-capture-multi-call-site` | 1-3 days | XS-S |
| `scheme-io-capture-optional-args` | 2-4 days | S |
| `scheme-io-capture-staleness-check` | 3-6 days | S-M |
| `scheme-io-capture-new-tests` | 4-7 days of setup and checking, spread over runs (six capture runs: mcsp, cloud_water, FHIST_C4, gw_cam7, microp_aero_bam, tracer_data_test; replay results, driver gaps logged as their own items); not urgent | S |
| `release-tagging` | 2-4 days (decide the xdsl-ccpp naming with the user; write the tagging skill + agent; dry run on the first candidate state) | S |
| `gpu-tests-without-device-code` | cloud_water 2-4 days; trcdata_bam = `gpu-port-tropopause-find`; microp_aero_bam 10-20 days (ndrop_bam, nucleate_ice; upstream review) | S-M |
| `untested-test-suites` | 2-4 days for rayleigh_friction + dry_adiabatic_adjust (testmods gnu/intel/nvhpc + _gpu, regression, baselines); tropopause_find and convection_permitting later | S |
| `scheme-io-capture-rte-objects` | 6-10 days (handlers for the RTE optical-property, source-function and flux types through their public procedures, with compare for outputs; then `ty_gas_concs`; `kdist` by setup-scheme replay; handler registry supplied by the physics side; tests; recapture rrtmgp and c03e) | S-M |
| `scheme-io-capture-group-replay` | 6-12 days (group-level capture point incl. suite module state, driver with host-cap residency emulation, GPU build and compare; reuses the v1/v2 capture library and tolerance code; not in the Kessler GPU plan) | M |
| `dropsonde-cuda-gdb-device-read` | 6-10 days (1-2 feasibility, 2-3 address table in xdsl-ccpp, 3-5 cuda-gdb read in dropsonde and `compare_captures.py`) | S-M |
| `scheme-io-capture-ctest-automation` | 2-4 days (only the in-repo `examples/` registration is left; the generated driver build exists) | S |
| `scheme-io-capture-generated-stubs` | 2-3 days (imported procedures' interfaces from their source, stub module as IR with error-exit bodies, kinds through the closure, tests) | XS-S |
| `acc-host-written-device-arg` | 1-2 days (classifier: written-in-kernel flag on ACC_HOST arguments; warning when device data elsewhere; tests) | XS |
| `scheme-io-capture-callee-device-args` | 1-2 days (device arguments from the present/copy clauses of the procedures a scheme calls, via the closure's call graph; tests; pumas GPU replay) | XS-S |
| `scheme-io-capture-generation-speed` | 1-2 days (scan the repository and source roots with the `--jobs` pool and seed the main process; closures only for schemes defining a read module; measure on c03e) | XS-S |
| `wv-sat-methods-move` | <1 day plus a coordinated PUMAS PR (one `dependencies` path in `micro_pumas_ccpp.meta`, PUMAS submodule bump, `git mv`) | XS |
| `scheme-io-capture-mpi-reach-renames` | 0.5 day (follow USE-renamed procedures in `mpi_reach`, as `module_state_access` does; test; check which captured phases it newly leaves out) | XS |
| `rrtmgp-dry-static-energy-intent-out` | 0.5 day (atmospheric_physics: `intent(inout)` in `.F90` + `.meta`, bit-for-bit; upstream PR) | XS |
| `rrtmgp-intent-out-unassigned` | 1-2 days (atmospheric_physics: ~10 schemes, `intent(inout)` or assign on every path, errmsg/errflg init; bit-for-bit check; upstream PR) | S |
| `scheme-io-capture-rrtmgp-coverage` | 0.5 day plus queue (cam4 recapture with the RRTMGP schemes in its list; check both radiation and non-radiation steps replay) | XS |
| `call-site-arg-rebind` | 4-8 days | S-M |
| `process-split-region` | 15-25 days (CPU only; assumes `process-split-combine-policy` is settled first) | L |
| `process-split-gpu` | 10-20 days (on top of `process-split-region`) | M-L |
| `expr-text-identity-keys` | 1-2 days (structural keys instead of text; same results in the passes that dedupe by them) | XS |
| `scheme-io-capture-size-bounds-recapture` | 0.5 day plus queue (two capture runs, CPU and GPU replays) | XS |
| `eddy-diffusivity-adjustment-gpu-coverage` | 0.5 day plus queue (one capture run with a non-default namelist, CPU and GPU replays) | XS |
| `vertical-diffusion-sponge-layer-gpu-coverage` | 0.5 day plus queue (one capture with `diff_sponge_fac > 0`; could share the eddy-diffusivity one) | XS |
| `generation-error-last` | 0.5 day (xdsl-ccpp stage-error suppression + CAM-SIMA message order, tests) | XS |
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
| `zm-number-concentration-compiler-diffs` | zm FPHYStest on intel differs from the gnu snapshot only in the hydrometeor number concentrations, cloud liquid number by up to 1.4e-6 (relative) -- too large for the user to accept as rounding | S; found 2026-11-09 (xdsl76i); may be a real defect that feeds into other fields later; same pattern in MCSP: `mcsp-number-concentration-compiler-diffs` | -- |
| `cap-clause-order-nondeterministic` | Two generations of the same cam4 inputs order the variables of `!$acc enter data copyin(...)` / `exit data copyout(...)` in `cam_ccpp_cap.F90` differently (`qrl, shfrc` vs `shfrc, qrl`) | XS; found 2026-11-10 (cap_oracle diff, base HEAD = working tree); harmless, but makes cap diffs noisy | -- |
| `mcsp-number-concentration-compiler-diffs` | MCSP FPHYStest on nvhpc differs from its intel snapshot in the hydrometeor number concentrations by up to 5.2e-6 (cloud liquid), while every other field is within 1.2e-11 | XS-S; found 2026-11-10 (xdsl76n rerun at 2.2e-16); same pattern as `zm-number-concentration-compiler-diffs` | -- |
| `suites-py-xml-omissions` | cam5's XML (and its Python copy) likely omits two schemes cam4 and cam7 have | XS; raise with the atmospheric_physics developers | -- |
| `rrtmgp-wrapper-acc-trigger` | GPU RRTMGP 'partially present' abort apparently happens only because our `ccs_config` compiles the RRTMGP `ccpp_*` wrappers with `-acc` | XS; found 2026-10-24 (tpr_n capgen GPU RRTMGP passes without the fix) | -- |
| `nvhpc-gpu-build-flags-redesign` | The nvhpc CPU/GPU build setup in `ccs_config`/`cime` is a stack of per-rule patches; each fix has exposed another hidden dependency | M; found 2026-11-04 (s51 CPU/GPU cases); deferred by the user to its own effort | -- |
| `gpu-acc-file-manifest` | Which files get `-acc` is decided by hand-kept lists and a filename wildcard in `Depends.nvhpc`; have the generator and the schemes declare it | S-M; found 2026-11-07 (xdsl66gpu Q-only diffs); part of `nvhpc-gpu-build-flags-redesign` | -- |
| `cam-sima-build-time` | Where CAM-SIMA case build time goes, and cheaper levers than a prebuilt base library | S-M per lever; gnu measured 2026-10-21 (xdsl56g); **repeat for nvhpc** (xdsl56n) | -- |
| `canonical-error-arg-order` | Generated routines take the CCPP error arguments in whatever order and names their first scheme uses | S code, M review (touches nearly every configuration's generated code); found 2026-10-23 (s27b) | -- |
| `package-scheme-list-order` | With package caps, `ccpp_physics_suite_schemes` lists a segment's schemes where the segment first appears, not in call order | S; found 2026-10-23 (s27b, s29a); only affects the order CAM reads scheme namelists | -- |
| `ccpp-opt-small-speedups` | Small `ccpp_opt` speed-ups left after `generator-speed` (under 1 s on cam4 together) | XS; found 2026-10-31 | -- |
| `in-process-pipeline` | Run the frontend and `ccpp_opt` passes in one process: removes the MLIR text round trip (~2 s of cam4's 6.6 s) | M; found 2026-10-31 | -- |
| `suite-owned-framework-var` | The suite cap declares an unused, never-allocated module array for the framework's constituent tendencies (`ptend_q`, microp_aero_bam) and warns about it | XS; found 2026-10-31 | -- |
| `cpu-cap-acc-updates` | CPU builds' suite caps contain unguarded `!$acc update` directives for suite-owned variables (inert, and not merged) | XS; found 2026-10-31 | -- |
| `registry-scheme-objects` | CAM-SIMA's registry pulls scheme-internal Fortran types (RRTMGP) into every build; blocks language-neutral host data for C++/Fortran scheme mixing | S-L; long-term architecture, upstream; discussed 2026-10-31 | -- |
| `package-shared-state-per-suite` | False `shared_state lists 'scheme_name', which is not shared state` warning: a package's `shared_state` is checked against one suite, but describes every suite using the package | XS; found 2026-10-31 (s43a build log, `kessler_test`) | -- |
| `cam-autogen-repeat-generation` | CAM-SIMA's `cam_autogen.py` regenerates the caps at `buildlib` and `case.run` after `buildnml` already did | XS; cause found and fixed locally 2026-10-31 (verified on s39a); upstream PR to ESCOMP/CAM-SIMA `development` pending | -- |

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

**ID: `zm-ncdata-diffs`. Resolved (2026-11-09)** -- by the sima0_25_000 / atmos_phys0_34_000 merge (new CAM7 snapshot, ZM transport of number concentrations); gnu zm passes (xdsl76g). CHANGELOG.md L14741.

**`zm-number-concentration-compiler-diffs`** -- added 2026-11-09. After the
merge the zm FPHYStest passes its physics check on gnu (the snapshot's
compiler, `min_difference = 2e-15`, xdsl76g) but intel (xdsl76i) aborts in
`ncdata_check`, and only on the number concentrations: cloud liquid number
46 points, max 1.4e-6 (relative); rain number 25 points, 2.8e-9; cloud ice
number 5 points, 3.6e-9. T, Q, Z and the other ZM outputs match at 2e-15.
nvhpc (xdsl76n, rerun at 2e-15) differs too, and more: cloud liquid
number 969 points, max 5.2e-6; rain number 1055 points, 1.6e-6; ice number
4.2e-10; snow number 4.8e-11 -- while every other field differs only at
1e-11 to 4e-15 (convective mass flux 1e-11, dT/dt 2e-12, winds ~4e-13, mixing
ratios <=8e-14), the size expected between compilers. So it is not intel
alone: both non-gnu compilers differ from the gnu snapshot, and the number
concentrations differ 5-6 orders of magnitude more than anything else.
ZM's own outputs agree across compilers at rounding level: cprnc of the
step-1 `cam.h1i` files (xdsl76g/76i/76n) gives normalized RMS 1e-13 to
1e-17 for all 31 ZM history fields in every pair (largest DLFZM: intel vs
nvhpc 7.8e-13, gnu vs intel 1.3e-13, gnu vs nvhpc 7.9e-13; gnu and intel
closest). The zm testmod's h1 file has no number concentrations, so the
fields that differ by up to 5.2e-6 could not be compared that way.
First step: add `hist_add_inst_fields;h1: NUMLIQ, NUMRAI, NUMICE, NUMSNO`
(sima_state_diagnostics' constituent diagnostic names; check them) to
`cam/outfrq_zm_derecho/user_nl_cam`, rerun zm on gnu, intel and nvhpc, and
cprnc the number concentrations pairwise: if intel and nvhpc differ from
each other about as much as each does from gnu (1e-6), the path is
sensitive or defective; if intel and nvhpc agree closely, look at what
gnu does differently.
The user considers 1.4e-6 too large to be compiler rounding: it may be a
real defect (e.g. an uninitialized or out-of-range value, a division by a
near-zero denominator, or an order-dependent sum) in the code atmos_phys
#453 added -- `zm_conv_convtran` now transports these number concentrations
(`doconvtran` set in `_init` by standard name), followed by
`clamp_number_concentrations` and `cloud_condensate_floor` -- and one that
would feed into other fields after more steps (number concentrations drive
the microphysics and radiation).
Investigate: run the zm test for more steps on gnu, intel and nvhpc and
compare the number concentrations and T/Q over time (growing or bounded?);
SMS_D runs with NaN/uninitialized-value trapping on all three compilers;
locate the differing points (levels 31-56, near the cloud top/base?) and
trace them through convtran's gather/scatter and the clamp/floor; compare
with CAM's `convtran` for number concentrations. If it is rounding, decide
the tolerance with the user; if a defect, fix upstream (atmospheric_physics).
Meanwhile (decided 2026-11-10): CAM-SIMA's zm and MCSP testmods set
`! cross_compiler_min_difference = 1e-11`, the tolerance every other
cross-compiler physics check uses. The number concentrations exceed it, so
zm (intel, nvhpc) and MCSP (gnu, nvhpc) keep failing their physics check
in every regression -- on purpose, as a reminder that this is open. (The
1e-5 used to generate the 20261109-efc0937-nvhpc baseline was never
committed.) The same differences appear in MCSP against its intel
snapshot: see `mcsp-number-concentration-compiler-diffs`.

**`cap-clause-order-nondeterministic`** -- added 2026-11-10. `cap_oracle
diff --base HEAD` on the xdsl77gpu SE F2000_C4 cam4 case, with no
generator change between base and head, reported `cam_ccpp_cap.F90`
DIFFERENT: the suite-level `!$acc enter data copyin(qrl, shfrc)` (init) and
`exit data copyout(qrl, shfrc)` (final) list the two variables in the
opposite order. Most likely a Python `set` (string hashing is randomized per
process) feeding the clause list of the framework-variable residency in
`ccpp_cap`. Harmless (clause order has no meaning), but a nondeterministic
generator makes every cap diff and oracle run noisy. Fix: sort, or keep
first-seen order; then `cap_oracle diff --base HEAD` should say IDENTICAL.

**`mcsp-number-concentration-compiler-diffs`** -- added 2026-11-10. The
MCSP FPHYStest (FHIST, ZM with the mesoscale coherent structure
parameterization; snapshot `..._zm_mcsp_snapshot_derecho_intel_after_c20261011.nc`)
on nvhpc, rerun with `min_difference = 2.2e-16` (xdsl76n, atm.log 8136233,
step 1): every field except the number concentrations differs at 4e-16 to
1.2e-11 (T 4.2e-16, mixing ratios <=9.4e-14, winds and their tendencies
<=5e-13, dT/dt 1.9e-12, deep convective mass flux 1.2e-11), but the number
concentrations differ far more: cloud liquid 5.2e-6 (1318 points), rain
8.9e-7, cloud ice 2.0e-9, snow 8.1e-11, graupel 1.0e-12. Cloud liquid
number is off by 5.2e-6 while cloud liquid mass is off by 2.2e-14. This is
the signature of `zm-number-concentration-compiler-diffs` (zm against its
gnu snapshot: nvhpc cloud liquid number 5.2e-6 too), so it is most likely
the same ZM number-concentration transport path (`zm_conv_convtran`,
`clamp_number_concentrations`, `cloud_condensate_floor`); work it as part
of that item, then confirm here: add the number concentrations to MCSP's
h1 output, rerun gnu/intel/nvhpc and check the fix (or the agreed
tolerance) covers MCSP. gnu against the intel snapshot has not been
measured at epsilon yet. The testmod sets
`! cross_compiler_min_difference = 1e-11` (with `include_user_mods` ->
`cross_compiler_check_tolerance`), so MCSP fails on gnu and nvhpc until
this is resolved -- deliberately, as a reminder. Note the Derecho false
pass (`derecho-false-run-pass`): the run aborts in `ncdata_check` but
TestStatus says RUN PASS; check atm.log.

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

**ID: `generation-error-output`. Resolved (2026-10-31)** -- CHANGELOG.md L13697.

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

**`nvhpc-gpu-build-flags-redesign`** -- found 2026-11-04. Deferred by the
user: fix it as its own piece of work, and don't add more side patches while
doing other tasks. Which flags a source file gets is decided in several places
that interact through the environment:
- `Depends.nvhpc`: `-acc -gpu=...` on whole object lists (`CCPP_CAP_OBJS` is
  every `.F90` in `bld/atm/obj/ccpp`, including host files with no `!$acc`
  such as `cam_thermo.F90`), `-Knoieee` (`GPU_SCHEME_MATH_FLAGS`) on GPU
  sources, and an explicit `$(ACC_OFF_FLAG)` (`-noacc`) added to every other
  rule;
- `cime`: `-noacc` added by hand to the GPTL Makefile rules and the libmpas C
  compiles; `MPAS_DYCORE_GPU_OFFLOAD` toggles MPAS's own flags;
- the environment: `cuda/12.9` sets `CRAY_ACCEL_TARGET`, which makes the Cray
  wrappers add OpenACC to any compile without an explicit `-acc`/`-noacc`
  (CPU links then fail on `__acc_compiled`), and which the wrapper also needs
  to link MPICH's `libmpi_gtl_cuda` (a GPU executable built without it aborts
  at MPI init). It is now cleared on CPU nvhpc cases only
  (`config_machines.xml`, `gpu_type="none"`);
- per-case copies: `Depends.nvhpc`, `cmake_macros/` and `env_mach_specific.xml`
  are copied at case creation, so a `ccs_config` fix doesn't reach existing
  cases; `--clean-all` also deletes the cached xdsl_ccpp interpreter path
  (`XDSL_CCPP_PYTHON` needed).
Goal: one place that decides, per source file, CPU or GPU flags (and math
flags), with nothing inherited implicitly from the module environment; a
check (e.g. `nm` for `__acc_compiled` in CPU executables, `ldd` for
`libmpi_gtl_cuda` in GPU ones) after each build. All the current patches are
uncommitted in the local `ccs_config` and `cime` checkouts.

**`gpu-acc-file-manifest`** -- found 2026-11-07. In xdsl66gpu, `Depends.nvhpc`
named only the Kessler suite caps in `CCPP_GPU_CAP_OBJS`, so every suite cap
that gained OpenACC directives through a scheme port was compiled `-noacc`.
Its `!$acc update self` before CPU schemes was dropped, and
`sima_state_diagnostics` wrote stale Q to history (Q-only GPU/CPU diffs in
dme_adjust, tj2016_after_coupler, pumas, SE FTJ16). The stopgap (ccs_config,
2026-11-07) takes every `$(EXEROOT)/atm/obj/ccpp/*_cap.F90` by wildcard; it
still depends on that directory, the `_cap` naming, and generation finishing
before make reads `Depends.nvhpc`. `GPU_SCHEME_OBJS` is still a hand-kept list
with the same drift risk. The cam-sima-regression/-test agents now flag any
cap containing `!$acc` that was compiled `-noacc`.
Proposed design: each tool reports what it produced instead of the Makefile
guessing.
- xdsl-ccpp writes a neutral manifest of the generated files it emitted with
  directives (its own output, no host build knowledge), e.g.
  `acc_files.txt` in the ccpp output directory.
- GPU-ported schemes are marked where they are defined (scheme metadata or
  the suite), not in `ccs_config`.
- CAM-SIMA `buildlib` turns both into the per-file `-acc` list (like it writes
  `capture_compile_flags.txt` today); `ccs_config` keeps only the policy
  (listed files `-acc`, everything else `-noacc`).
This also removes the MPAS reason for explicit lists (files are marked by
intent, not by containing `!$acc`).

**ID: `rrtmgp-gpu-cpu-diffs`. Resolved (2026-11-07)** -- nvhpc CPU verification builds compile the GPU rte-rrtmgp kernels (`RRTMGP_KERNELS=accel`, CAM-SIMA); xdsl70gpu 29/29 bit-for-bit vs 20261107-f669d35-nvhpc. CHANGELOG.md L14574.

**`cam-autogen-repeat-generation`** -- CAM-SIMA's
`cime_config/cam_autogen.py` (`generate_physics_suites`) regenerates the caps
when `build_cache.ccpp_mismatch(...)` reports changed inputs, or whenever the
scheme namelist reader is regenerated (`do_gen_nl` sets `do_gen_ccpp`). In
the xdsl56g build logs generation ran at `buildnml`, again at `buildlib` in
22 of 25 cases, and again at `case.run`; a build should generate once. Find
which cache field differs between the calls (inputs, preprocessor string,
`cache_generator`, or the namelist branch), and fix it in CAM-SIMA. Saves
5-9 s per FPHYStest build and ~26 s for cam4 (`cam-sima-build-time`).

Cause (2026-10-31): `ccpp_mismatch` checks `host_files` before the scheme
namelist `.meta` files are appended to that list, and `update_ccpp` then
cached the extended list, so every later check saw a different host-file set
(confirmed on xdsl60g's pumas cache: cached 33, checked 28, the 5 extra are
exactly its `scheme_namelist_meta_file`s). Upstream code (2021, `8f70d97`),
unnoticed because `test_cam_autogen.py` only uses a `FakeBuildCache`. Fixed
locally in CAM-SIMA's `xdsl-ccpp-adapter` checkout (uncommitted): cache the
list as checked (`cache_host_files`), plus a regression test
`test_generate_physics_suites_caches_checked_host_files` (fails on the old
code, passes with the fix). Verified on s39a (gnu pumas): caps generated
once per build, not at `case.run`; an unchanged rebuild does not regenerate
(13 s); editing `qneg_namelist.xml` still regenerates the namelist reader
and the caps. To do: upstream PR to ESCOMP/CAM-SIMA `development` (a branch
with only `cime_config/cam_autogen.py` and
`test/unit/python/test_cam_autogen.py`).

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
  mismatch saves 5-9 s (FPHYStest) to ~26 s (cam4) per build
  (`cam-autogen-repeat-generation`);
- xdsl-ccpp generation for the cam4 suites was itself slow (53-109 s);
  now ~6.6 s standalone and once per build (`generator-speed`, resolved;
  `cam-autogen-repeat-generation`);
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

**ID: `generator-speed`. Resolved (2026-10-31)** -- CHANGELOG.md L13651.

**`ccpp-opt-small-speedups`** -- left after `generator-speed` (cam4: 6.6 s,
of which `ccpp_opt` 4.1 s: MLIR parse ~1.2, passes ~1.6 -- `suite_cap`
0.73, `ccpp_cap` 0.36 --, two verifies ~0.6, Fortran print ~0.4, start-up
~0.3). Under 1 s together:
- skip the verify before the pipeline (~0.3 s): it only checks our own
  frontend's output and the final verify still runs; keep it under
  `--verify-each-pass` (tests, CI). A frontend bug would then surface as a
  pass failure, not a verifier error;
- hot spots in the passes (~0.2-0.4 s): 915,000 `ccpp_item.getAttr` calls
  (the same metadata looked up repeatedly), `promotion._find_loop_upper_bound`
  (1,010 calls, high per-call cost), ~200,000 function-level imports run in
  hot loops.
Profile with a scratch `sitecustomize` cProfile hook (see the
`generator-speed` CHANGELOG entry); scale cProfile times by ~0.38 for cam4.

**`cpu-cap-acc-updates`** -- found 2026-10-31 (`gpu-sync-intent-aware`
stage 2). `suitecap/gpu.py` (`_inject_suite_owned_gpu_update`,
`_inject_segment_interface_gpu_update`) calls `emit_coalesced_updates("acc", ...)`
whatever the build's `--directive` is, so the suite (and package) caps of
CPU builds carry `!$acc update self/device(...)` directives for suite-owned
variables: e.g. 17 in the CPU Kessler FPHYStest cap, not inside `#ifdef
USE_GPU` (unlike the same caps' `!$acc declare create`, which is). They are
inert (CPU builds do not compile OpenACC), but noise, and they diverge from
the GPU caps: `merge_adjacent_updates` runs in `generate-gpu-data`, which
CPU builds skip, so these stay unmerged. Fix: emit them only when a
directive is set (and with that directive, so `--directive omp` gets
OpenMP), or guard them like `declare create`; the merge question then goes
away. Changes CPU caps (comments only), so check with cap_oracle and one
CPU Kessler run.

**`registry-scheme-objects`** -- discussed 2026-10-31 (long-term
architecture; an upstream CAM-SIMA change). `src/data/registry.xml` lists
RRTMGP's derived-type metadata (`schemes/rrtmgp/objects/ccpp_{fluxes,
fluxes_byband,gas_concentrations,gas_optics_rrtmgp,optical_props,
source_functions}.meta`) as `metadata_file` entries. `generate_registry`
runs before the suites are known and is suite-independent, so every case
parses them and compiles the RRTMGP sources, Kessler included. Measured on
s38a (GPU Kessler): the objects are in `libatm.a`, but the linker drops
them (no RRTMGP symbol in `cesm.exe`), so there is no executable-size or
memory cost. The costs are compile time and fault isolation: an RRTMGP
change or compiler problem (e.g. the RRTMGP submodule's particle->crystal
rename drifting from `registry.xml`) can fail builds that never call radiation.

Long-term it also matters for mixing C++ and Fortran schemes: the host
registry should hold language-neutral data (arrays, scalars), which the caps
pass to a scheme in either language. A scheme's internal objects held as
Fortran types in the host tie that scheme to Fortran (a C++ RRTMGP could not
use them).

Options:
1. Suite-aware `metadata_file` filter: collect the derived types the
   configured suites use and skip unused `metadata_file` entries and the
   registry variables of those types (`generate_registry_data.py`, build-cache
   ordering in `cam_autogen.py`). A few days, but hides rather than fixes the
   language coupling.
2. Preferred: move scheme-internal objects out of the host registry into
   state the package owns (suite-owned / package-private state, see the
   composite-scheme work), leaving the registry language-neutral.
3. Filtering every registry variable per suite: not worth it (hand-written
   CAM-SIMA code uses registry variables directly).
First step (read-only): find which registry variables have RRTMGP types and
who uses them, to decide whether option 2 is practical. Note that
`generate_init_routines` is already suite-aware (reads only what the suites
need), so the suite information exists, just after the registry step.

**`package-shared-state-per-suite`** -- found 2026-10-31 in s43a's build
log (`kessler_test` with package caps): `xDSL-ccpp: Warning: Package
'kessler': shared_state lists 'scheme_name', which is not shared state (it
is an output); remove it from the list.` `PackageScope.interface_problems`
(`transforms/package_scope.py`) compares the package's declared
`shared_state` with the directions inferred for the suite being generated.
In `kessler_test` the only outside user of `scheme_name` is `qneg_run`,
which reads it, so it is an output there. But `suites-py/suite_kessler.py`
(`check_energy=True`) adds `check_energy_zero_fluxes_run`, which also
writes it (`name`, intent out): shared state, so removing the declaration
as the warning says would turn generating `kessler` into an error. The
declaration is right; the check sees only one suite. Fix: keep the warning
only for declarations wrong in every suite (the package does not touch the
name, keeps it private, or it is public for another reason: host,
framework, constituent, input); for a name that is an output or input in
this suite, print a note at `--verbose 2` (generation-error-output
conventions). Unit test in the package-scope tests; check that the
kessler_test pkgcap generation no longer warns.

**`suite-owned-framework-var`** -- found 2026-10-31 in the
`generation-error-output` survey. Generating microp_aero_bam prints
`suite_cap.py: UserWarning: xdsl_ccpp: cannot resolve allocation dimensions
for 'ptend_q' (std_name='ccpp_constituent_tendencies', dims=(horizontal_loop_extent,
vertical_layer_dimension, number_of_ccpp_constituents)) during suite-owned var
sweep -- no allocate() will be generated.` The suite cap
(`microp_aero_bam_cap.F90`) declares a module-level `real(kind_phys),
allocatable :: ptend_q(:,:,:)` that is never allocated or used: the run
routine takes `ptend_q` as a dummy argument (shadowing it), and
`cam_ccpp_cap.F90` passes the framework's `lc_const_tend`, which it
allocates. So the result is right (microp_aero_bam runs clean), but the
suite-owned sweep (`suitecap/suite_owned.py`) classifies a framework cap
variable (`FRAMEWORK_STD_NAME_TO_CAP_VAR`, here
`ccpp_constituent_tendencies`) as suite-owned. Exclude framework cap
variables from the sweep; the dead declaration and the warning go away.
Check which other suites declare such arrays (cap_oracle diff shows it).

**ID: `cap-oracle-jobs`. Resolved (2026-10-31)** -- CHANGELOG.md L13697.

**`in-process-pipeline`** -- run the frontend and the `ccpp_opt` passes in
one process. Today `ccpp_dsl` runs the XML frontend and `ccpp_opt` as
subprocesses that hand the module over as MLIR text: the frontend prints it
(~0.7 s with its start-up), `ccpp_opt` parses it back (~1.2 s) and starts a
second interpreter (~0.3 s) -- ~2 s of cam4's 6.6 s, the remaining gap to
original capgen (~5 s). Design questions: the subprocess isolates global
state (e.g. `set_legacy_mode`), keeps error paths that call `sys.exit` from
killing the caller (CAM-SIMA's `cam_autogen.py` runs xdsl_ccpp as a
subprocess partly for this), and is what the tests and FileCheck goldens
drive through `ccpp_opt`'s command line; passes monkeypatched in-process
today have no effect (see the `ccpp_opt` subprocess note). Keep `ccpp_opt`
as a CLI either way.

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
`.meta` is correct. Mirror `acc-derive-memory-space`'s Fortran classifier
(`fparser2_to_meta._classify_acc_residency`, device/either, done
2026-11-02) for the pragmas, and coordinate with
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

**ID: `scheme-io-capture-netcdf`. Resolved (2026-11-01).** CHANGELOG.md L13800.

**ID: `scheme-io-capture-gpu-residency`. Resolved (2026-10-18, PR #146).** CHANGELOG.md L12524.

**ID: `scheme-io-capture-gpu-verify`. Resolved (2026-10-18)** — real
`nvfortran -acc` run on an A100, confirmed with `nsys` (real
`cuLaunchKernel`/memcpy activity, not a host fallback). CHANGELOG.md L12524.

**ID: `scheme-io-capture-ctest-automation`. v2 follow-on: full CMake/ctest
automation.** Mostly done 2026-11-01 (CHANGELOG.md L13800): the generator
writes a CMake build and ctest tests for the drivers it writes. Left: the
in-repo registration below (an `examples/kessler` capture-and-replay test).
Already noted in this
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

**ID: `scheme-io-capture-fixture-storage`. Resolved (2026-11-01).** CHANGELOG.md L13800.

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

**ID: `scheme-io-capture-host-module-schemes`. Resolved (2026-11-06, PR #200).** CHANGELOG.md L14272.

**ID: `scheme-io-capture-rte-kernel-variants`. Resolved (2026-11-06, PR #201).** CHANGELOG.md L14333.

**ID: `scheme-io-capture-new-tests`. Capture data for the regression tests
the sima0_25_000 merge added, and for suites never captured.** Added 2026-11-09; low priority. Three tests
came in with the merge (CAM-SIMA xdsl-ccpp-adapter-merge-b942a2d): the
FPHYStest `outfrq_mcsp_derecho` (test suite `mcsp`: the full ZM sequence,
then `save_core_tend_from_convect_deep`, `zm_conv_cloud_top`, `mcsp`,
`mcsp_diagnostics`, and `clamp_number_concentrations` /
`cloud_condensate_floor`), the FPHYStest `outfrq_cloud_water_derecho`
(`convective_cloud_water`, `cloud_water_paths`), and the full-model
`SMS_D_Ln9 FHIST_C4 outfrq_se_cam4` (cam4 with transient historical
forcing). Capture each with `/cam-sima-capture` (`list` = every scheme of
the suite) and replay the drivers CPU and GPU, as for the existing
captures (/glade/derecho/scratch/dennis/capture_*). Expected gaps:
`mcsp` calls `vertinterp` from CAM-SIMA's `src/utils/interpolate_data.F90`
(a host module the capture support library does not provide; its
`.meta` has no `dependencies` line), and the ZM schemes that call `qsat`
did not build before `wv-saturation-ccppize` (recheck). FHIST_C4's value over the
existing cam4 captures is real time-varying input to `prescribed_ozone`,
`prescribed_aerosols`, `prescribed_volcanic_aerosol`,
`prescribed_aerosol_deposition_flux` and `solar_irradiance_data`, so
capture just those. Also the FPHYStest `outfrq_gw_cam7_derecho` (test
suite `gw_cam7_se`: `gravity_wave_drag_common`, `_prepare_profiles`,
`_top_taper`, `compute_total_precipitation_rate`, and the CAM7 sources
`_moving_mountain`, `_convection_deep`, `_frontogenesis`, `_ridge`,
`_ridge_beta`, with their diagnostics), never captured because until the
merge it failed MODEL_BUILD (no host variables for `prec_dp`/`prec_sh`/
`prec_str`, fixed by sima0_24_000's registry, CAM-SIMA #557); it now passes
on gnu, intel and nvhpc with no snapshot differences (xdsl76g/76i/76n).
Expected gap: in capture_gw_cam4, `gravity_wave_drag_prepare_profiles` and
`gravity_wave_drag_orographic` were NOT-BUILT (the `Coords1D` /
`gw_common` path, see `gpu-port-gw-orographic`); the CAM7 GW schemes
likely share it. The replays are what `gpu-port-gw-orographic` needs.
Also two older suites never captured (added 2026-11-09, for
`gpu-tests-without-device-code`): `microp_aero_bam` (`nucleate_ice_ccpp`,
`ndrop_bam_ccpp`, `compute_subgrid_vertical_velocity_clubb`,
`scale_subgrid_vertical_velocity`, `dust_default_radii`, with their
diagnostics -- none captured anywhere; the ports of `ndrop_bam_ccpp` and
`nucleate_ice_ccpp` need these replays) and `tracer_data_test`
(`prescribed_*` readers and `tropopause_find`, with this suite's own
tracer-data inputs). `rebin_seasalt` and `tropopause_find` already have
replays (capture_cam4/F2000_C4, capture_rk_stratiform/rrtmgp). Expect some
microp_aero_bam drivers NOT-BUILT at first (CAM aerosol code, possibly
CAM host modules).
Log each driver gap found as its own item.

**ID: `release-tagging`. A coordinated tag scheme across our repositories,
and a skill/agent the user runs to tag a tested state.** Added 2026-11-09.
Results are identified today by date-hash baseline names
(`20261109-efc0937-nvhpc`) and commit lists in perf files, across five
repositories (CAM-SIMA, atmospheric_physics, ccs_config and cime -- pinned by
CAM-SIMA -- and xdsl-ccpp, which is not a submodule).
Agreed so far (user, 2026-11-09): the upstream tag as the base plus our own
counter, `sima0_25_000-xdsl01`, `-xdsl02`, ... for the CAM-SIMA fork and
`atmos_phys0_34_000-xdsl01` for the atmospheric_physics fork (not
`simax0_25_000`: no room for our increments between upstream tags, and it
would collide with upstream's patch numbers); baselines could then be named
after the tag (`sima0_25_000-xdsl01-nvhpc`).
Open: the xdsl-ccpp naming (same name as CAM-SIMA, its own version, or the
commit recorded in the CAM-SIMA tag message) -- the user's decision, to be
coordinated across all repositories.
Then a skill (thin trigger) + agent (the procedure), run by the user when
they decide a state is a release point -- NOT part of /cam-sima-regression:
check every repository is clean and pushed and CAM-SIMA's submodule pointers
match the checkouts; find the regressions that passed at exactly these
commits (gnu, intel, nvhpc CPU baseline, nvhpc GPU compare) and show any
missing; propose the next tag name and an annotated message listing every
repository's commit, the baseline tag and the regression IDs; print the
`git tag -a` / `git push origin <tag>` commands for the user to run (lines
under 100 characters; the agent never tags or pushes). First candidate:
the sima0_25_000 merge once xdsl76n and its GPU compare pass and
`post-merge-generation-fixes` is merged.

**ID: `gpu-tests-without-device-code`. Three `aux_sima_gpu` tests run
(almost) nothing on the GPU.** Added 2026-11-09. Count of each GPU test's
suite schemes whose source has OpenACC and whose object is compiled `-acc`
(`Depends.nvhpc`): `cloud_water_gpu` 0 of 4 (`convective_cloud_water`,
`cloud_water_paths` and their diagnostics, all CPU); `trcdata_bam_gpu` 1 of
6, and that one is `sima_state_diagnostics` (conditional pulls, no kernels;
`prescribed_*` readers and `tropopause_find` on the CPU); `microp_aero_bam_gpu`
1 of 14 (`rebin_seasalt` only; `nucleate_ice_ccpp`, `ndrop_bam_ccpp`, the
subgrid vertical-velocity schemes, `tropopause_find`, `dust_default_radii`
on the CPU). They still build for the GPU and compare bit-for-bit with
their CPU baseline, so they show a GPU build of a CPU suite is unchanged,
but they exercise no device code. Every other GPU test has real GPU work
(e.g. kessler 15/16, cam4 50/158, cam7 41/130). Fix with at least one real
port each: cloud_water first (small column schemes, also in cam4 and
cam7: `convective_cloud_water`, `cloud_water_paths`); trcdata_bam via
`gpu-port-tropopause-find` (the readers stay on the host); microp_aero_bam
via `ndrop_bam_ccpp` and `nucleate_ice_ccpp` (CAM aerosol code, larger,
needs upstream review). Each port: OpenACC in the `.F90`, object in
`GPU_SCHEME_OBJS`, capture replay CPU and GPU, then the GPU test.

**ID: `untested-test-suites`. atmospheric_physics test suites no CAM-SIMA
test runs.** Added 2026-11-09. Of the 23 suites in
`src/physics/ncar_ccpp/test/test_suites/`, 18 have an FPHYStest testmod
(all run, with nvhpc and `_gpu` versions); five have none:
- `rayleigh_friction` (`rayleigh_friction`, its diagnostics, updaters): a
  snapshot exists, `cam_ne3pg3_rayleighfriction_snapshot_derecho_gnu_*_c20241210.nc`
  (/glade/campaign/cesm/amwg/soft_eng/sima_baselines/cam_sima_test_snapshots).
  Add `cam/outfrq_rayleigh_friction_derecho` like the other FPHYStests
  (gnu, intel, nvhpc; `cross_compiler_check_tolerance`) and its `_gpu`
  testmod. `rayleigh_friction` is not ported: small, a natural first GPU
  port for the test.
- `dry_adiabatic_adjust` (`dadadj` + updaters): `dadadj` is already ported
  and verified on the GPU in cam4; a dedicated test covers it alone. Its
  snapshot is a different setup,
  `cam_dry_adiabatic_adjust_SMS_Ln9_P1.ne5_ne5_mg37.QPC5HIST_gnu_*.nc`
  (ne5, QPC5HIST), so the testmod needs that grid and probably upstream's
  original settings (ask the atmospheric_physics developers how it was run).
- `tropopause_find` (`tropopause_find`, `tropopause_diagnostics`, `qneg`):
  no snapshot found; would need one from CAM. Pairs with
  `gpu-port-tropopause-find`. Later.
- `convection_permitting` (99 schemes): not an FPHYStest -- the physics of
  compset `CAM%MPASCP` (MPAS convection-permitting, analytic IC,
  `config_component.xml`); a later full-model regression or perf target.
- `file_io_test`: a test of the CCPP file-I/O interface
  (`test/test_schemes/file_io_test`); low value for us.
Then: new gnu/intel/nvhpc baselines include them; the regression agent's
expected counts change.

**ID: `scheme-io-capture-share-code`. Resolved (2026-11-06, PR #201).** CHANGELOG.md L14333.

**ID: `scheme-io-capture-generated-stubs`. Generate interface stubs for
modules a capture driver cannot build.** Added 2026-11-06 (from
`scheme-io-capture-share-code`). Utility modules that do nothing a replay
needs (logging, abort, I/O) block drivers when they cannot be built
standalone: CESM's `shr_log_mod`/`shr_sys_mod` need ESMF. For now the
capture support library has hand-written stand-ins
(`framework_src/capture_stubs/`) for the two procedures the physics
uses (`shr_log_errMsg`, `shr_sys_abort`, both only from
`to_be_ccppized/linear_1d_operators.F90`). Revisit if more such modules
block drivers: generate a stub module from the real source, holding
only the names the scheme's files import, with their real interfaces
(dummy-argument declarations), each procedure ending the replay with a
message; built as IR (functions with typed arguments and an error-exit
body) and printed by the Fortran printer. Runs only at generation and
reads a few declarations, so it costs no build time. Candidates:
`interpolate_data` (5 rrtmgp schemes) if they do not call it in the
replayed phases, `shr_infnan_mod`/`shr_assert_mod` (`.F90.in` templates
CESM generates at build time).

**ID: `scheme-io-capture-module-state-setup`. Resolved (2026-11-06, PR #202).** CHANGELOG.md L14397.

**ID: `scheme-io-capture-callee-device-args`. A GPU replay misses device
data the scheme's callees require.** Added 2026-11-06 (from
`scheme-io-capture-module-state-setup`). `test_pumas_post_main` passes
on CPU but stops on GPU (c03d): `data in PRESENT clause was not found on
device: name=qic(:vlen)` in `micro_pumas_utils.F90`,
`size_dist_param_basic_vect`. `pumas_post_main_run` has no OpenACC of
its own; the driver's device arguments come from the entry point's own
directives (`acc-derive-memory-space` rule (a)), not from the
procedures it calls, while in the model the cap's data region already
holds them. Wanted: also take the `present`/`copy` clauses of the
procedures the scheme reaches (the closure's call graph, as
`mpi_reach`/`module_state_access` follow it), mapped back to the
entry point's arguments.
Note 2026-11-08: generation now does one level of this for entry points
with no OpenACC of their own (`fparser2_to_meta.apply_callee_residency`,
callees in the same file or the `.meta` `dependencies`; CHANGELOG
`acc-copy-residency`), and the capture driver takes its device arguments
from the same classification. Check whether that already fixes
`test_pumas_post_main`; what is left here is callees more than one level
down (`size_dist_param_basic_vect` is reached through other routines) and
calls through the closure's call graph rather than `dependencies`.

**ID: `acc-host-written-device-arg`. Warn when a scheme argument the scheme
writes in a kernel is also used in its host code while device-resident.**
Added 2026-11-08 (found analysing the xdsl72gpu pumas diffs). An "either"
argument the entry point (or, through `apply_callee_residency`, its callee)
also references in host code is ACC_HOST: left on the host for that call,
and the cap syncs around it (`update self` before, `update device` after if
it may write). That is correct only when the kernels do not write it: if a
kernel writes it through a present-or-copy clause and the variable is
device-resident, the clause finds it present and copies nothing back, the
host code sees a stale copy, and the cap's push overwrites the kernel's
result. Not hit yet (the four pumas host arguments are intent(in)). Wanted:
a generation warning (classifier: the argument appears in a `copy`/
`copyout` clause or is assigned in a compute body, and is ACC_HOST, and is
device data elsewhere in the suite), naming the fix in the scheme: an
`update self(x) if_present` / `update device(x) if_present` around its
host use.

**ID: `wv-saturation-ccppize`. Resolved (2026-11-11).** CHANGELOG.md L14786.

**ID: `wv-sat-methods-move`. Move `wv_sat_methods.F90` out of
`to_be_ccppized/`.** Added 2026-11-11 (from `wv-saturation-ccppize`).
It already uses no host modules, but stayed in `to_be_ccppized/` because
PUMAS's `micro_pumas_ccpp.meta` (ESCOMP/PUMAS submodule) lists it as
`dependencies = ../../../to_be_ccppized/wv_sat_methods.F90`, a path
into atmospheric_physics' layout from inside another repository.
Moving it to `schemes/utilities/` beside `wv_saturation.F90` needs a
one-line PUMAS PR and the PUMAS submodule bump in the same
atmospheric_physics PR (else cam5, cam7 and pumas fail at generation).
Do it with the next PUMAS change; build-only, no answer change.

**ID: `scheme-io-capture-mpi-reach-renames`. The MPI check does not follow
renamed procedures.** Added 2026-11-06. `mpi_reach` follows calls by
procedure name only; a procedure USEd under another name (`use m, only:
local => remote`) is not followed, so an MPI call behind one is missed
and its phase captured. `module_state_access` resolves the renames
since `scheme-io-capture-ddt-args` (the `qsat_ice` case); do the same in
`mpi_reach` and check which captured phases it newly leaves out.

**ID: `scheme-io-capture-generation-speed`. Capture driver generation is
serial.** Added 2026-11-06. With `--capture-test-driver-dir`, the
statement scans behind the closures, the MPI check and the module-state
analysis run in the main process (c03e: ~58 s with capture vs ~20 s
without, both `--jobs 1`; the module-state closures of the suite's other
schemes are ~10 s of it); `--jobs` covers only the Fortran-vs-metadata
check, and the scan cache is per process. Generation without capture is
unaffected. Wanted: profile, then scan the scheme repository and source
roots with the `--jobs` pool and seed the main process's cache, and
compute closures only for schemes defining a module whose variables are
read.

**ID: `scheme-io-capture-driver-as-ir`. Resolved (2026-11-06, PR #199).** CHANGELOG.md L14223.

**ID: `scheme-io-capture-real-kinds`. Resolved (2026-11-05, PR #198).** CHANGELOG.md L14186.

**ID: `scheme-io-capture-uncaptured-phases`. Resolved (2026-11-05, PR #196).** CHANGELOG.md L14129.

**ID: `scheme-io-capture-skip-message`. Resolved (2026-11-05, PR #197).** CHANGELOG.md L14160.

**ID: `scheme-io-capture-kinds-deps`. Resolved (2026-11-05, PR #193).** CHANGELOG.md L14012.

**ID: `scheme-io-capture-log-unit`. Resolved (2026-11-05, PR #192).** CHANGELOG.md L13987.

**ID: `scheme-io-capture-exact-compare`. Resolved (2026-11-05, PR #191).** CHANGELOG.md L13959.

**ID: `scheme-io-capture-constituent-index-table`. Resolved (2026-11-05, PR #194).** CHANGELOG.md L14043.

**ID: `scheme-io-capture-rrtmgp-coverage`. The rrtmgp capture has no
non-radiation steps.** Found 2026-11-05: c02i (`SMS_Ln2`, `irad_always =
3`) runs radiation on every captured step, so `rrtmgp_pre` always sets
`dosw_heat = dolw_heat = .false.` (`dosw_heat = .not. dosw`) and the
`calc_*_heat = .true.` path of `rrtmgp_dry_static_energy_tendency` (and
any other non-radiation-step branch) is never captured. Plan
(2026-11-05): cover it from the cam4 capture instead -- cam4 (c02m:
`SMS_Ln9`, 30-minute steps, `iradsw = iradlw = irad_always = -1`)
radiates hourly, and all 25 RRTMGP run-phase schemes are now in
`/glade/derecho/scratch/dennis/capture_cam4/unit-tests.txt`. Wanted: that
cam4 recapture, after `rrtmgp-dry-static-energy-intent-out`, and a check
that its drivers replay both kinds of step.

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

**ID: `scheme-io-capture-ddt-args`. Resolved (2026-11-06, PR #203).** CHANGELOG.md L14461.

**ID: `capture-size-bounds`. Resolved (2026-11-06, PR #204).** CHANGELOG.md L14523.

**ID: `capture-compile-flags`. Resolved (2026-11-06, PR #204).** CHANGELOG.md L14523.

**ID: `scheme-io-capture-size-bounds-recapture`. Recapture gw_cam4 and
cam4.** Added 2026-11-06 (from `capture-size-bounds`). Their existing
captures lack the arguments PR #204 now records (gw_cam4 `egwdffi`,
`egwdffi_tot`, `kvt_gw`, `ni`, `rhoi`, `taua`, `ubi`; cam4 `p_lev`), and
their drivers predate the skip of unrecorded arguments, so those
arguments are not compared. Recapture both (production, so the flags
file applies) and replay on CPU and GPU.

**ID: `scheme-io-capture-rte-objects`. Capture the RTE-RRTMGP derived
types.** Added 2026-11-06 (from `scheme-io-capture-ddt-args`). The
generic capture records flat types only; every RRTMGP type is out of
its reach: the optical properties and the longwave source functions
(`ty_optical_props_{1scl,2str}`, `ty_source_func_lw`) have private
components in their base types (`ty_optical_props%band2gpt`,
`gpt2band`, `band_lims_wvn`, `ty_optical_props_arry%top_at_1`); the
fluxes (`ty_fluxes_{broadband,byband}`) have pointer components
(`flux_up`, `flux_dn`, ...); `ty_gas_concs` has private components and
character names; `kdist` (`ty_gas_optics_rrtmgp`) has private lookup
tables read from files at init. In c03e this leaves 11 RRTMGP schemes
(most phases of `rrtmgp_pre`, `_inputs`, `_post`, the sw/lw
`gas_optics`, `aerosols`, `rte`, `calculate_fluxes`, `cloud_optics`,
`mcica_subcol_gen`) without a replay. Wanted: handlers per type, as for
the constituent properties (`_DDT_CAPTURES`), through RTE's public
procedures -- the optical properties' public `tau`/`ssa`/`g` and their
band limits (`get_band_lims_wavenumber`, `get_band_lims_gpoint`),
rebuilt with `init` and `alloc_1scl`/`alloc_2str`; the fluxes' targets
as arrays the driver allocates and points the components at;
`ty_gas_concs` through `get_vmr`/`set_vmr`. `kdist` comes last (its
init reads files; replaying the setup scheme may be simpler). Needed for
scheme-by-scheme GPU checks of `gpu-fphystest-rrtmgp`.
Additions (2026-11-12, re-sized S -> S-M):
1. Compare, not only rebuild. A handled derived type is today only
   rebuilt from the capture and never compared (`capture_driver_ir`:
   "rebuilt from the capture ... never compared"). McICA's and cloud
   optics' main outputs are optical-properties objects, and the flux
   schemes write flux objects, so each handler also needs a compare --
   e.g. extract the public arrays (`tau`, `ssa`, `g`, band limits,
   fluxes) so the driver's existing array compare reports them.
2. Where the handlers live. `ccpp_constituent_prop_ptr_t` is a CCPP
   framework type, so its handler belongs in `xdsl_ccpp/framework_src`;
   RTE-RRTMGP is a physics library and xdsl-ccpp carries no physics
   knowledge. So the physics side (atmospheric_physics, beside
   `schemes/rrtmgp/objects`) provides the handler module and a neutral
   registration input (type -> module, write/read/compare routines, as
   `capture_compile_flags.txt` works); `_DDT_CAPTURES` becomes the
   built-in default plus that registry.
3. `kdist` by setup replay. McICA, cloud optics and gas optics all take
   `kdist`. The existing module-state setup (the driver calls
   `wv_saturation_init` before the pumas replay) sets module state, but
   `kdist` is an argument the setup scheme produces: extend the
   mechanism so a setup call's output feeds a replayed argument.

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
`scheme-io-capture-rte-objects` for groups with RTE-RRTMGP
derived-type arguments. A flattened composite
has no subroutine of its own; package caps (2f) would allow
package-scoped replay later.
Not in the Kessler GPU plan (2026-11-02, see `gpu-fphystest-kessler`):
the CAM-SIMA regression plus dropsonde covers cross-scheme data movement
without a driver that needs MPI and `cam_history` stand-ins. A
package-cap replay (a package's segments in order, its private state
carried between them, no host modules) is the possible middle ground if
package caps become the default.

**ID: `dropsonde-cuda-gdb-device-read`. Let dropsonde read GPU copies
through cuda-gdb.** Added 2026-11-02. dropsonde
(hplin-ucar/dropsonde, `dropsonde_gdb.py`) compares a CPU and a GPU
CAM-SIMA run scheme call by scheme call, under gdb, reading host memory
only: for device data it re-reads after the cap's own `!$acc update
self`. As the Kessler port removes those syncs (`gpu-fphystest-kessler`
steps 4 and 6), more arguments stay on the GPU and dropsonde reads stale
host copies. Do it once enough schemes are ported that this matters.
The approach tried in 2026-09 (gdb calling `acc_update_self` /
`acc_deviceptr` in the live model, under gdb and cuda-gdb) corrupted GPU
memory or hung and must not be retried. This one only reads:
- cuda-gdb reads GPU global memory passively at a host breakpoint
  (`print *(@global double *)ADDR@N`).
- The device address comes from a table the generated cap fills under a
  debug flag (xdsl-ccpp): per device-resident argument, host and device
  addresses from `acc_deviceptr` or `host_data use_device` -- compiled
  code calling the runtime is safe, gdb calling it is not. The
  alternative, decoding nvhpc's OpenACC present table, is undocumented
  and thread-local: not worth it.
- Kernels must have finished at the breakpoint: `NV_ACC_SYNCHRONOUS=1`
  or `CUDA_LAUNCH_BLOCKING=1` in the environment, no injected calls.
Plan: (1) feasibility, 1-2 days -- a small OpenACC Fortran program whose
kernel writes an array only on the device, read under a Python-enabled
cuda-gdb on Derecho through `@global`, first with the printed device
pointer, then through the address table; (2) the table in xdsl-ccpp
(flag, `--directive acc` only); (3) the read in dropsonde
(`nvhpc-gpu-support` lineage) and in `compare_captures.py`. Risks: the
unexplained SIGKILL of nvhpc DEBUG runs under gdb after each timestep
may recur; cuda-gdb's Python support on Derecho.


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

- **ID: `acc-meta-residency-check`. Resolved (2026-11-02, PR #187)** -- CHANGELOG.md L13862.
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
- `constituent-device-residency` — **Constituent views and the whole
  constituent array alias on the device: make the syncs correct by
  construction (correctness; reclassified from performance by the user
  2026-11-12).** Found 2026-11-12 in the PUMAS GPU cap (s61): the whole
  array is already resident -- `enter data copyin(lc_constituent_array)`
  in `ccpp_initialize_constituents`, `update device` at physics entry and
  `update self` on return (host cap) -- and the per-constituent views
  (`cldice_in`, ...) are pointers into it, so the per-call `data
  copy(<view>)` regions find the views present and move nothing. Hazard:
  the generator tracks a view and the whole array (`const`) as separate
  variables, so a CPU scheme writing a view (or the whole array) on the
  host between device schemes would leave the device copy stale with no
  error -- the per-call `copy` meant to protect the next device call
  degenerates to `present`. No current suite has such a writer (PUMAS
  CPU/GPU bit-for-bit). Fix: treat views and the whole array as one
  variable for last-writer tracking, `update self`/`update device` where
  the writing side changes, device calls under `present`. Original
  (performance) description: Since `advected-constituent-host-binding`,
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
- `constituent-residency-from-source` — **Let a scheme's own directives
  manage the constituents' device copy.** Added 2026-11-02, alongside
  `constituent-device-residency` (whose first version decides residency
  automatically: the constituent array goes on the device unless a CPU
  scheme writes it; CPU readers get an `update self`). Alternative kept
  in source code instead of in the generator or CAM-SIMA configuration: a
  small residency scheme in the suite whose phases hold the data
  management -- init `!$acc enter data create(q)`, timestep_init `update
  device(q)`, timestep_final `update self(q)`, final `exit data
  delete(q)` -- on its constituent-array argument (an `enter data` on a
  dummy maps the actual memory, the framework's array). Generator work:
  - the classifier treats an `enter`/`exit data` (and phase-level
    `update`) in a lifecycle routine as "this scheme manages the
    variable's device copy from this phase on", a classification beyond
    today's per-call device/either;
  - precedence: such a variable gets no generator `enter`/`exit data`
    (they would fight); the generator still emits `update self` before
    CPU readers inside groups, which the scheme cannot know about;
  - the scheme's `.meta` declares the constituent array in every phase
    (no `memory_space`).
  Weakness: the sync timing is host knowledge. The scheme's `update
  device` runs at physics timestep_init; if the host changes the
  constituents on the CPU after that and before the run group (coupler,
  after-coupler work, depending on configuration), the device copy is
  stale with no error. The generator's host-cap syncs around the group
  are placed by construction; a residency scheme is only as correct as
  its placement in the suite. Both can coexist: an explicit residency
  scheme overrides the automatic rule for its variables.
- `gpu-ddt-deep-copy-residency` — **Device residency for derived-type
  arguments with allocatable components. Not planned (2026-11-02).**
  Decision: xdsl-ccpp never moves derived-type data; the scheme moves
  its own, in its CCPP entry point (one level above the library it
  wraps), as RRTMGP's wrappers (`rrtmgp_*_gas_optics_run`,
  `rrtmgp_*_rte_run`) and PUMAS's `micro_pumas_tend` already do. Which
  components are allocated and needed, and the attach order, is the
  scheme author's knowledge; inferring it in the generator is complex
  and its bugs (partially-present errors, stale components) are the
  hardest to find. Cost: per-call transfers of those objects. If that
  matters, the scheme adds `enter data` in its init/timestep_init and
  `exit data` in final, so the per-call clauses find the data present;
  still no generator work. The generator rejects `memory_space =
  device` on a derived-type argument (`acc-derive-memory-space`).
  Original proposal, kept for reference: found 2026-10-28 while scoping
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
  All ESCOMP/PUMAS changes for this work collect on one local submodule
  branch, `props-device` (off the pin `e7377ae`; user, 2026-11-12):
  `pumas-module-props-device`, `pumas-proc-rates-residency` and the
  optional wrapper directives of step 3, `avg_diameter`'s `!$acc routine
  seq`, and the reflectivity rewrite (`13cd79d`, cherry-picked
  2026-11-12: the user needs CPU/GPU bit-for-bit now;
  `pumas-refl-single-division-upstream`).
  Steps, in order:
  1. `gpu-pumas-testmod` — PUMAS's own kernels on the GPU, cap
     unchanged. Done (CHANGELOG.md L14975): GPU test bit-for-bit with the
     nvhpc CPU test (xdsl80gpu, xdsl81gpu).
  2. `pumas-module-props-device` — PUMAS's module-level props resident
     (upstream, ESCOMP/PUMAS).
  3. Residency of `micro_pumas_ccpp_run`'s arguments. Done by the
     generator, not by directives in the wrapper: since
     `acc-copy-residency` (CHANGELOG.md L14606, 2026-11-08, "Residency
     through callees") an entry point with no OpenACC of its own takes
     each array it passes bare to a callee from that callee's
     directives (one call level; `micro_pumas_tend`'s data region).
     Result in the pumas GPU cap (xdsl81gpu): 97 arguments device, no
     syncs; 4 host (`relvar`, `accre_enhan`, `rndst`, `nacon`), one
     `update self` before the call.
     2026-11-12: the 4 are device too (CHANGELOG.md L15078: a mapped
     array passed to a call inside its data region is not a host use),
     so the `update self` is gone. Left, optional: an explicit
     `!$acc data present(...)` in `micro_pumas_ccpp_run`
     (ESCOMP/PUMAS) would make the residency visible in the wrapper
     itself and drop the one generator dependence on reading
     `micro_pumas_v1.F90`; no data-movement gain.
  4. `micro_proc_rates`: done 2026-11-12 (`pumas-proc-rates-residency`,
     CHANGELOG.md L15120); allocating it once is `pumas-proc-rates-allocate-once`.
  5. `constituent-device-residency` — PUMAS's main inputs (cloud
     liquid/ice, number concentrations, rain, snow, graupel) are
     constituents, copied per device call today.
  6. `gpu-port-pumas-interface-schemes` (done 2026-11-12, CHANGELOG.md
     L15030) and
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
  2. `acc-derive-memory-space` — done 2026-11-02: the wrappers'
     plain-array arguments from their existing data clauses (copy
     clauses: device only where another scheme keeps the variable on the
     GPU).
  3. The rte-rrtmgp objects (`ty_gas_concs_ccpp`,
     `ty_gas_optics_rrtmgp_ccpp`, `ty_optical_props_*_ccpp`,
     `ty_source_func_lw_ccpp`, `ty_fluxes_*_ccpp`) stay with the
     wrappers, which deep-copy them by hand today; residency across
     wrappers, if profiling asks for it, is scheme-side `enter`/`exit
     data` in their init/final (`gpu-ddt-deep-copy-residency`, not
     planned).
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
  1. `gpu-sync-intent-aware` — done 2026-10-31 (CHANGELOG.md L13758).
  2. Capture gaps — done 2026-11-01 (CHANGELOG.md L13800): constituent
     properties captured, local captures from a CAM-SIMA run; 14 of the
     16 schemes replay from one capture on CPU and GPU.
  3. `acc-derive-memory-space` — done 2026-11-02 (CHANGELOG.md L13862):
     ported schemes need no `.meta` change; the Kessler `.meta` files no
     longer declare `memory_space` (s44a passed).
  4. `gpu-port-shared-utility-schemes`, Kessler's 12: the 10 state
     converters (`calc_exner`, `temp_to_potential_temp`,
     `potential_temp_to_temp`, `calc_dry_air_ideal_gas_density`,
     `wet_to_dry_*`, `dry_to_wet_*`), `qneg` and `geopotential_temp`.
     Each port checked by per-scheme replay on the GPU; cross-scheme data
     movement by FPHYStest against the CPU snapshots, localized with
     dropsonde's CPU-vs-GPU comparison (`kessler_cpu_gpu`) while the
     cap still syncs to the host around most schemes.
  5. `dropsonde-cuda-gdb-device-read` — once enough schemes are ported
     that data stays on the GPU between them, dropsonde (host memory
     only) stops seeing it; read device copies through cuda-gdb.
  6. `constituent-device-residency` — `qv`/`qc`/`qr` and the whole
     array `qneg` takes. Riskiest step (a missed sync gives silently
     wrong values); localized with dropsonde's device reads (step 5).
  7. Validation per the acceptance criteria above, on every Kessler GPU
     testmod: FPHYStest, `se_cslam_gpu` and `se_cslam_multitape_gpu`,
     `kessler_mpas_derecho[_history]_gpu`, and the composite package-cap
     pair (`outfrq_kessler_composite_pkgcap_derecho_gpu`). Also run
     these after steps 1 and 4 as milestones.

  Testing split (decided 2026-11-02): per-scheme replay for a scheme's
  numerics; the CAM-SIMA regression for cross-scheme data movement, with
  dropsonde to find the first diverging call. A standalone group replay
  (`scheme-io-capture-group-replay`) was dropped from this plan: it would
  need MPI (qneg's summaries) and `cam_history` stand-ins (the
  diagnostics schemes), against the point of a simple unit test.

  `sima_state_diagnostics` and `kessler_diagnostics` stay on the host
  (history output) and keep an `update self` before them throughout.

Supporting items (not tracked elsewhere):

- **ID: `gpu-sync-intent-aware`. Resolved (2026-10-31)** -- CHANGELOG.md L13758.

- **ID: `acc-derive-memory-space`. Resolved (2026-11-02, PR #187)** -- CHANGELOG.md L13862.

- `example-gpu-build-flags` — **The OpenACC examples' GPU builds probably
  never ran on the GPU.** Found 2026-11-02 while testing
  `examples/kessler_omp`. With `-DARCH=GPU` and nvfortran,
  `examples/kessler` (`kessler_apply_arch_flags`) and `examples/advection`
  compile with `-mp=gpu` (OpenMP) and never `-acc`, and link with neither
  (flags.make/link.txt of a configured tree). nvfortran ignores `!$acc`
  without `-acc`, so their kernels and the caps' OpenACC directives most
  likely ran on the host and the GPU tests (`ctest_kessler_parity` on GPU,
  `ctest_kessler_cpu_gpu_parity`, `run_cpu_gpu_parity.sh`) compared host
  results. For `kessler_omp` the same missing link flag made every target
  region fall back to the host silently (`OMP_TARGET_OFFLOAD=MANDATORY`:
  "Could not run target region on device 0"; nsys: no CUDA kernels);
  fixed there with `target_link_options(-mp=gpu)` and MANDATORY on its
  GPU tests. To do: compile and link the OpenACC examples with `-acc`
  (plus `-mp=gpu` where hand-written OpenMP drivers need it), confirm
  kernels run (`NV_ACC_NOTIFY`/nsys), then fix what breaks once they do
  (the known `kessler_hand.exe`/C++ drivers "PRESENT clause was not
  found" cases). Not related to CAM-SIMA, whose GPU builds use `-acc`.
- **ID: `omp-derive-memory-space`. Resolved (2026-11-02, PR #188)** -- CHANGELOG.md L13916.
- **ID: `gpu-pumas-testmod`. Resolved (2026-11-12)** -- CHANGELOG.md L14975.
- **ID: `pumas-nvhpc-optimized-cpu-snapshot`. Resolved (2026-11-12)** -- CHANGELOG.md L15005.
- `eddy-diffusivity-adjustment-gpu-coverage` — **The GPU port of
  `eddy_diffusivity_adjustment_above_pbl` is not exercised by any test.**
  Added 2026-11-06. The scheme was ported to OpenACC (one `parallel loop
  collapse(2)` over columns and interface levels), but its whole loop sits
  under `if (kv_freetrop_scale /= 1 .or. (kv_top_scale /= 1 .and.
  kv_top_pressure > 0))`, and every test case runs with the namelist
  defaults (`kv_freetrop_scale = 1`, `kv_top_scale = 1`, `kv_top_pressure =
  0`): the uw_vdiff capture (c04d) replays "pass" with no kernel launched
  (`gpu_kernels.txt`: CPU-ONLY 0), and the model never runs the code.
  Wanted: a capture with non-default values that takes both branches
  (e.g. `kv_freetrop_scale = 0.5`, `kv_top_scale = 0.0` as in WACCM,
  `kv_top_pressure = 1000.0`), replayed CPU and GPU; such a run differs
  from the uw_vdiff snapshot, so the case needs `ncdata_check_err =
  .false.` (edited in place in `user_nl_cam`, not added twice), or a
  testmod of its own.
- `vertical-diffusion-sponge-layer-gpu-coverage` — **The GPU port of
  `vertical_diffusion_sponge_layer` is not exercised by any test.** Added
  2026-11-06. Its run phase adds `diff_sponge_fac * kvm_sponge(k)` to the
  top levels of `kvm` only if init allocated `kvm_sponge`, which it does
  only for `diff_sponge_fac > 0` (profiles chosen by `ptop_ref`, WACCM or
  CAM7 MT/LT tops). The F2000_C4 and cam4 replays pass with no kernel
  launched (CPU-ONLY 0). Wanted: a capture with `diff_sponge_fac > 0`
  (init replayed first, `scheme-io-capture-module-state-setup`), replayed
  CPU and GPU; like `eddy-diffusivity-adjustment-gpu-coverage`, the run
  then differs from its snapshot (`ncdata_check_err = .false.`). Both
  could share one capture.
- `pumas-module-props-device` — **ESCOMP/PUMAS: make `mg_*_props`
  device-resident once.** Add the six `MGHydrometeorProps` module
  variables to the existing `!$acc declare create(...)`
  (`micro_pumas_utils.F90:289`) and `!$acc update device(...)` (`:390`,
  after they are set). Flat type, set only at init; `micro_pumas_tend`'s
  `copyin` then finds them present. Bit-for-bit; also applies to
  ESCOMP/CAM. Small gain.
  Code done and verified 2026-11-12: PUMAS commit `eb7078a` on the
  submodule branch `props-device` (see `gpu-fphystest-pumas`). The
  `copyin(mg_*_props)` in `micro_pumas_tend` and `pumas_post_main` stay;
  they now find the data present. GPU test s60
  (`SMS_Ln2...cam-outfrq_pumas_derecho_gpu`, xdsl-ccpp `main` 72f4788):
  RUN and MEMLEAK PASS, history file cprnc "IDENTICAL" against the nvhpc
  CPU baseline `20261109-efc0937-nvhpc`. Left: the ESCOMP/PUMAS PR (one
  PR from `props-device` with the other PUMAS GPU changes).
- **ID: `pumas-proc-rates-residency`. Resolved (2026-11-12)** -- CHANGELOG.md L15120.
- `pumas-proc-rates-allocate-once` — **ESCOMP/PUMAS: allocate the
  `proc_rates` DDT once, not every step.** Added 2026-11-12 (follow-on to
  `pumas-proc-rates-residency`). Today `micro_pumas_ccpp_run` allocates all
  119 components every call (`micro_pumas_ccpp.F90:516`, the `REMOVECAM`
  note calls it "a performance hit") and `micro_pumas_ccpp_timestep_final`
  frees them; in a GPU build each call also creates and deletes their
  device copies (`proc_rates_device_create/_delete`). Not measured yet --
  do it only if a profile shows the churn (nvhpc pools device memory, so
  the device side is likely cheap; the host allocate/free of 119 arrays
  per step is the part to time). Obstacles:
  - Size: `micro_ncol` is `microphysics_horizontal_loop_extent`, a
    run-time loop extent; init has no horizontal dimension. Either add one
    to `micro_pumas_ccpp_init` (new argument, standard name, CAM-SIMA host
    variable), or allocate lazily in the run -- allocate when not
    allocated or when the shape changed, free in `_final` -- which also
    covers CAM's varying `ncol` (no `REMOVECAM` switch needed).
  - Intent: `micro_proc_rates_out` is `intent(out)` in the run, which
    frees every allocatable component on entry; it must become `inout`
    (`.F90` and `.meta`) for the allocation to survive between calls.
  - Device copies: with the allocation kept, create them once with it and
    delete them in `_final` (no per-call create/delete). That is also what
    `gpu-history-accumulate`'s todo for the process rates needs (device
    copies alive until the diagnostics run).
  - Replay: as `inout`, the capture records `proc_rates` before the call
    too (`in/` group), so pumas needs a recapture, and the driver's
    back-to-back run calls then reuse one allocation.
  Bit-for-bit expected (no arithmetic changes). Goes on the PUMAS branch
  `props-device` with the ESCOMP/PUMAS PR, or after it.
- **ID: `gpu-port-pumas-interface-schemes`. Resolved (2026-11-12)** -- CHANGELOG.md L15030.
- `gpu-port-kessler-energy-utilities` — **OpenACC ports of the `kessler`
  suite's pointwise energy utilities.** Added 2026-11-02. The `kessler`
  suite (FKESSLER: SE and MPAS testmods) runs `kessler_test`'s 16 schemes
  plus seven CPU schemes; three are one-line pointwise updates:
  `check_energy_scaling` (`scaling_dycore = cpairv / cp_or_cv_dycore`),
  `dycore_energy_consistency_adjust` (`tend_dTdt_local = (scaling_dycore
  - 1) * tend_dTdt` under a flag) and `apply_tendency_of_air_temperature`
  (`temp += t_tend*dt`, `dTdt_total += t_tend`, `t_tend = 0`). Port each as
  a `parallel loop collapse(2)` with present-or-copy clauses (as the state
  converters, `gpu-fphystest-kessler` step 4) and add the objects to
  `GPU_SCHEME_OBJS` in `Depends.nvhpc`. Main gain:
  `apply_tendency_of_air_temperature` writes `temp` (device data), so on
  the CPU it forces syncs back to the device in the after-coupler group.
  `check_energy_zero_fluxes` was ported too (2026-11-05), although its
  outputs only feed the host scheme `check_energy_chng`
  (`gpu-port-check-energy-chng`), so on the device it adds per-call
  transfers; the user accepted that cost mid-port and will reevaluate
  performance once more schemes are ported. `sima_tend_diagnostics` stays on the
  host (history; `gpu-history-accumulate`). Test: per-scheme
  capture replays from an FKESSLER case (`/cam-sima-capture`), then the SE
  and MPAS Kessler GPU testmods.
- `gpu-port-check-energy-chng` — **GPU port of `check_energy_chng` (with
  `check_energy_zero_fluxes`).** Added 2026-11-02. The `kessler` suite's
  energy and water conservation check (also in the cam suites). Most of
  its work is CAM's own `get_hydrostatic_energy` (`src/data/cam_thermo.F90`,
  ~190 lines): index arrays allocated from module data
  (`thermodynamic_active_species_*`), a formula chosen by vertical
  coordinate, per-column vertical integrals. Porting means a device
  version of that routine (`!$acc routine` or a kernel inside it) and its
  module data on the device -- a CAM-SIMA change outside
  atmospheric_physics. The scheme also prints conservation errors
  (`write(iulog, ...)`), which must stay on the host (reduce on the
  device, print on the host). Port `check_energy_zero_fluxes` with it (its
  flux outputs feed only this scheme). Gain is small while the state
  diagnostics stay on the host: today it only reads device data (`temp`,
  `z`, `phis`, `q`) and costs one `update self` that
  `sima_state_diagnostics` right after it needs anyway.
- `gpu-port-dme-adjust` — **GPU port of `dme_adjust`. On hold
  (2026-11-05, user).** `schemes/conservation_adjust/dme_adjust/dme_adjust.F90`
  (`dme_adjust_run`, ~40 lines of work): rescales each layer's
  constituents and `pdel` by `fdq = 1 + (present - initial total water)`,
  then rebuilds `ps`, `pint`, `lnpint` and `rpdel` from the top down. In
  the `dme_adjust` FPHYStest suite and the cam suites (commented out in
  `suite_kessler.xml`). Capture `capture_dme_adjust` (c02h) exists and
  replays on the CPU.
  Plan:
  - `const_props(:)` (`ccpp_constituent_prop_ptr_t`, a pointer derived
    type with type-bound `is_water_species`/`is_thermo_active`) stays on
    the host (`gpu-ddt-deep-copy-residency`: not planned). The two flags
    depend only on the constituent index, yet today they are queried
    `pver x pcnst` times inside the `k` loop: evaluate them once on the
    host into `logical :: water_active(pcnst)` and pass that to the
    kernel with `copyin` (as `qneg` passes its minimum values as a plain
    array).
  - The `is_dycore_moist` early return stays on the host.
  - One kernel, a thread per column (`parallel loop gang vector`), the
    levels `loop seq`: `ps` and `pint(:,k+1)` are top-down recurrences
    (`pint(k+1) = pint(k) + pdel(k)`, `ps` accumulates), so only the
    column loop is parallel; keep the summation order for bit-for-bit.
    The local `fdq(ncol)`/`tot_water(ncol,2)` become per-thread scalars.
    The inner constituent loops (total water, rescale) stay in order.
  - `log` (`lnpint`) and the division (`rpdel`, rescale): expected
    bit-for-bit under `-Knoieee` + `math_uniform`, as Kessler's math.
  - Add `dme_adjust.o` to `GPU_SCHEME_OBJS` (`ccs_config/machines/Depends.nvhpc`).
  - `const_array` is the constituent array; its device residency comes
    from `constituent-device-residency`.
  Test: `build_capture_tests.sh --arch gpu|cpu --tests dme_adjust`
  (ON-GPU, bit-for-bit; check the captured calls have `is_dycore_moist`
  true: all 3 c02h calls do, so the real path is covered). No GPU testmod
  for the `dme_adjust` suite yet.
- `gpu-port-wv-saturation` — **Device `qsat` for the convection
  schemes.** Added 2026-11-05. `hack_convect_shallow` and `zm_conv_evap`
  (and `zm_convr`, `compute_cloud_fraction`, `prognostic_cloud_water`)
  call `qsat` from `src/physics/ncar_ccpp/schemes/utilities/wv_saturation.F90`
  (~1450 lines; a CCPP scheme since `wv-saturation-ccppize`; generic
  `qsat` over `qsat_line`/`qsat_vect`/`qsat_2D`,
  built on `wv_sat_methods`). Calling it inside a kernel needs
  `!$acc routine seq` on the call path down to `wv_sat_methods` and
  its module data present on the device. Since `wv-saturation-ccppize`
  the constants (`epsilo`, `latvap`, `latice`, `rh2o`, `cpair`, `tmelt`,
  `h2otrip`) are `wv_saturation` module variables with `!$acc declare
  create` and an `update device` at init, beside `estbl`, `omeps`, `c3`,
  `pcf`; still host-only: `wv_sat_methods`' `default_idx` (the selected
  method). Generation now notes that `compute_cloud_fraction_run` calls
  OpenACC code (`svp_ice_vect`) without directives of its own.
  `to_be_ccppized/wv_sat_methods.F90` already has its OpenACC (55
  directives, used from PUMAS's kernels); the gap is the `wv_saturation`
  wrapper (`qsat`, `qsat_water`, `calc_hltalt`, ... `!$acc routine seq`)
  and its module constants (`!$acc declare`, `update device` after init).
  Decided 2026-11-09: no standalone `qsat` test. First recapture zm,
  hack_shallow, rk_stratiform and pumas (`/cam-sima-capture`) and check
  the CPU replays of `zm_convr`, `zm_conv_evap`, `hack_convect_shallow`,
  `compute_cloud_fraction`, `prognostic_cloud_water` and
  `micro_pumas_ccpp` now build and pass (pumas failed with NaNs from an
  unset `h2otrip`); the capture's module-state setup must run
  `wv_saturation_init` (fix the capture if not; it does). Then this,
  tested through the GPU replays of its in-kernel callers (zero
  tolerance). Prerequisite for `gpu-port-zm-convr`.
  Narrowed 2026-11-11: `zm_conv_evap` and `compute_cloud_fraction` were
  ported without it (CHANGELOG.md L14878) -- they call the vector forms
  from the host, which already run their own kernels on present data.
  `hack_convect_shallow` was ported the same way (CHANGELOG.md L14909).
  Still needed for the
  scalar calls inside column loops: `zm_convr` (`qsat_hPa`, four sites,
  plus `qsat_water`), `prognostic_cloud_water` (`qsat`, `svp_to_qsat`,
  `estblf` per point; `findsp_vc`).
- **ID: `pumas-refl-cpu-gpu-diffs`. Resolved (2026-11-11)** -- CHANGELOG.md L14838.
- `pumas-refl-single-division-upstream` — **Upstream the PUMAS reflectivity
  rewrite.** Added 2026-11-11 (from `pumas-refl-cpu-gpu-diffs`). The local
  edit in the PUMAS submodule (`micro_pumas_v1.F90`, ice and snow terms of
  the radar-reflectivity loop: `*1.e4_r8` with one division instead of
  `/icldm*1000/0.1`) makes the nvhpc CPU and GPU reflectivity diagnostics
  bit-for-bit and removes two divisions per point. Needs an ESCOMP/PUMAS PR
  (answer change: those 5 diagnostics, by rounding, on every compiler) and
  the PUMAS submodule bump in atmospheric_physics; until then the edit
  lives only in this working tree.
  Deferred by the user 2026-11-11. Worked out then: there is no
  `johnmauff/PUMAS` fork yet (create one on GitHub). PR base: ESCOMP/PUMAS
  `main_cam` (default; 27f3a55), two answer-changing PRs (#80, #82) ahead
  of the submodule pin e7377ae (`pumas_cam-release_v1.41`), with the
  reflectivity lines identical, so the edit cherry-picks cleanly. Plan:
  in the submodule rename `origin` to `escomp`, add the fork as `origin`;
  commit the edit on a branch off the pin (`refl-single-division`, for
  local builds), cherry-pick onto `escomp/main_cam`
  (`refl-single-division-pr`), push, open the PR against `main_cam`. Keep
  the local pin (moving to `main_cam` would change answers). PR text:
  not bit-for-bit in general -- the 5 reflectivity diagnostics change by
  rounding on every compiler, nothing feeds back; nvhpc CPU and GPU now
  agree (c07g 624/624). Pointing atmospheric_physics at the fork's branch
  needs a `.gitmodules` URL change: do it with the submodule-pointer
  updates.
  2026-11-12: also cherry-picked onto the PUMAS branch `props-device`
  (`13cd79d`) for CPU/GPU bit-for-bit there; it may go upstream with that
  branch's PR instead of alone (the user decides).
- `zm-convr-init-gathered-outputs` — **Upstream the `zm_convr` output
  initialization.** Added 2026-11-11 (c07a replay). `zm_convr_run` now
  zeroes the intent(out) `mu`, `eu`, `du`, `md`, `ed`, `dp` over all
  columns (they were written only for the first `lengath`, and not at
  all when nothing convects). Local edit in the atmospheric_physics
  `xdsl-support` working tree, kept out of the `wv_saturation` PR by
  request; a small separate PR (bit-for-bit expected; confirm with a
  regression).
- **ID: `capture-gpu-status-own-kernels`. Resolved (2026-11-11)** -- CHANGELOG.md L14950.
- **ID: `gpu-port-hack-convect-shallow`. Resolved (2026-11-11)** -- CHANGELOG.md L14909.
- `gpu-port-zm-convr` — **GPU port of `zm_convr`.** Added 2026-11-11
  (the only CPU-ONLY driver left in capture_zm after the `zm_conv_evap`
  port). `schemes/zhang_mcfarlane/zm_convr.F90` (~2640 lines), the deep
  convection core of the `zm` suite (and cam4). Needs
  `gpu-port-wv-saturation`: `qsat_hPa` is called per point inside column
  loops (cape/buoyancy and the cloud-top search). Gathers convecting
  columns (`lengath`) before the core, so the port needs the gather and
  scatter on the device; module settings come from `zm_conv_options`.
  Test: its GPU replay (capture_zm `test_zm_convr`, zero tolerance).
- **ID: `gpu-port-zm-conv-evap`. Resolved (2026-11-11)** -- CHANGELOG.md L14878.
- `gpu-port-gw-orographic` — **GPU port of
  `gravity_wave_drag_prepare_profiles` and
  `gravity_wave_drag_orographic`.** Added 2026-11-05. The two CPU-only
  schemes left in the `gw_cam4` suite (also `gw_cam7_se`, cam4/5/7); the
  rest of its capture list was ported 2026-11-05 (untested), except
  `check_energy_chng` (`gpu-port-check-energy-chng`).
  - `Coords1D` (`to_be_ccppized/coords_1d.F90`): `prepare_profiles`
    builds `p = Coords1D(pint)` (a derived type with six allocatable
    components `ifc`, `mid`, `del`, `dst`, `rdel`, `rdst`), passed to
    `orographic` through the suite. xdsl-ccpp never moves derived-type
    data (`gpu-ddt-deep-copy-residency`), so either the schemes manage
    its device copy themselves (`enter data` of the object and its
    components where it is built, `present` where used, `exit data`
    when it is rebuilt or freed; the constructor reallocates it every
    step) or the interface changes to plain arrays. Decide first.
  - `orographic` calls the shared GW library in
    `schemes/gravity_wave_drag/gw_common.F90` (1033 lines):
    `gw_drag_prof` (which uses `gw_diffusion` `gw_ediff`/`gw_diff_tend`
    and `linear_1d_operators` `TriDiagDecomp`, a derived-type
    tridiagonal solver), `energy_change`, plus `gw_utils`
    `get_unit_vector`, `dot_2d` and `midpoint_interp` (array-valued
    functions). These need device versions (`!$acc routine` or kernels
    inside them); the library is shared with the other GW schemes
    (gw_cam7), so port it once for all of them.
  - Column-sequential parts: the source-level search walks up from the
    surface with an `all(src_level >= k)` early exit across columns,
    and the vertical sums must keep their order for bit-for-bit;
    `prepare_profiles` is pointwise apart from `midpoint_interp`.
  - Large automatic arrays in `orographic` (`tau(ncol, -ngwv:ngwv,
    pver+1)`, `gwut`, ...) become device temporaries.
  - Test: no per-scheme replay until their drivers build
    (`prepare_profiles` needed only `shr_kind_mod`, which capture drivers
    now take from `share/src` (PR #201); `orographic` also needs CAM's
    `interpolate_data`, so no replay);
    until then a full gw_cam4 GPU run against its
    CPU reference (no GPU testmod yet).
- `gpu-history-accumulate` — **Accumulate history fields on the GPU.**
  Added 2026-11-08. **A full design project (user, 2026-11-10), not
  GPU-optimization work:** the history buffers' redesign needs its own
  design document before implementation. It replaces the dropped
  `gpu-diagnostics-conditional-sync` (per-field pulls in the diagnostics
  schemes put data movement into scheme source -- the cap's job -- and
  every new diagnostics scheme would need them). Goal: diagnostics schemes
  stay unchanged, `history_out_field` accumulates on the device when its
  input is device data (decided at run time), and the cap stops pulling
  the diagnostics schemes' arguments. Notes so far:
  `history_out_field` (`src/history/cam_history.F90:636-782`)
  needs host data every step: `history_out_field` (`src/history/cam_history.F90:636-782`) still
  needs host data every step: per file it looks the name up
  (`find_in_field_list`) and calls `hist_field_accumulate`, which adds the
  values into the file's buffer (avg/var: add; min/max: compare; lst: copy)
  in `buff_1d_accum`/`buff_2d_accum` (`src/history/buffers/src/hist_buffer.F90`,
  ESMCI/history_output submodule `history01_02`). The ~30 cam4
  `_diagnostics` schemes call it every step and do almost no arithmetic
  themselves (unit scaling, gathered-to-column scatter, 0/1 flags), so the
  per-step cost on the GPU is the device-to-host copy plus a CPU
  accumulate. `history_out_field` has no time argument: output frequency
  and averaging live in `hist_configs` and are applied at
  `history_write_files`/`history_wrap_up`.
  Wanted: the accumulation buffers device-resident (allocated with `enter
  data` when the field is added), `buff_*_accum` as device kernels when the
  input is present (`if_present`/`present()` path, host path kept for CPU
  callers and host-only fields), and one `update self` of the buffer at
  write/normalization time instead of one copy of the field per step. The
  name lookup stays on the host (string hash); only the accumulate moves.
  Details to settle: `flag_xyfill` masking, `cols_or_block` indexing, the
  var accumulator, per-file buffers when a field is on several files, and
  instantaneous fields (only the written step matters; with device
  buffers they cost one kernel per step and no copy). Upstream: ESMCI/
  history_output and CAM-SIMA `cam_history`. Test: Kessler and cam4 GPU
  FPHYStest bit-for-bit against the nvhpc CPU baseline (avg normalization
  order must match), plus history_output's own unit tests on CPU.
  Todo (2026-11-12): **history output of derived-type data the scheme
  keeps on the device -- PUMAS's process rates.** Since
  `pumas-proc-rates-residency` (user's option (b)), a GPU build keeps
  `proc_rates` (`proc_rates_type`, 119 arrays) on the device for the
  `micro_pumas_ccpp_run` call only and never copies it back; the host
  copies are unset. Nothing outputs them today (`pumas_diagnostics_run` is
  a placeholder in no suite). The design has to cover them: the cap never
  moves derived-type data (`gpu-ddt-deep-copy-residency`), so the copy
  cannot be the cap's. Costs to weigh: averaged (`'A'`) fields need every
  step's values (accumulated every step), instantaneous ones only on
  written steps, inactive fields none -- usually a handful of the 119 or
  none; copying all ~80 that `micro_pumas_tend` writes every call was
  option (1), rejected. A per-field `update self(...) if(active)` in
  `pumas_diagnostics` is the pattern dropped with
  `gpu-diagnostics-conditional-sync`. Device-resident buffers would let
  `history_out_field` accumulate the components on the device directly,
  but then the device copies must live until the diagnostics run (delete
  in `micro_pumas_ccpp_timestep_final`, not right after
  `micro_pumas_tend`). Until then a tripwire stops a GPU run that outputs
  them: PUMAS `micro_pumas_diags` `proc_rates_on_host` (a parameter,
  `.false.` under `_OPENACC`) and a check at the top of
  `pumas_diagnostics_run` (atmospheric_physics) that returns
  `errflg = 1` while it is false.
- `gpu-port-vertical-diffusion-simple` — **GPU ports of the vertical
  diffusion schemes that do not call the solver.** Added 2026-11-08. Nine
  small schemes, all replayable on CPU and GPU (F2000_C4, uw_vdiff,
  hb_vdiff captures): `vertical_diffusion_prepare_inputs` (22 lines),
  `vertical_diffusion_set_total_surface_stress` (26),
  `compute_kinematic_fluxes_and_obklen` (44), and in
  `diffusion_solver.F90` `vertical_diffusion_set_temperature_at_toa_default`
  (14), `vertical_diffusion_set_dry_static_energy_at_toa_zero` (11),
  `vertical_diffusion_interpolate_to_interfaces` (64),
  `vertical_diffusion_wind_damping_rate` (20),
  `implicit_surface_stress_add_drag_coefficient` (31),
  `vertical_diffusion_tendencies` (51). Pointwise/column loops; the
  `coords1d` components they read are passed as plain arrays. Gain: cam4
  cap syncs around them (cap_oracle after `acc-copy-residency`:
  `compute_kinematic_fluxes_and_obklen` 7, `set_total_surface_stress` 6,
  `prepare_inputs` 4, `tendencies` 4, ... per step); the rest of the group
  stays synced until `gpu-port-vertical-diffusion-solver`. Test: the three
  replays CPU and GPU, then hb_vdiff/uw_vdiff GPU FPHYStest bit-for-bit
  against the nvhpc CPU baseline.
- `gpu-port-vertical-diffusion-solver` — **GPU ports of the three vertical
  diffusion schemes that call `fin_vol_solve`.** Added 2026-11-08.
  `vertical_diffusion_diffuse_dry_static_energy` (46 lines),
  `vertical_diffusion_diffuse_tracers` (78) and
  `vertical_diffusion_diffuse_horizontal_momentum` (189), all in
  `diffusion_solver.F90`. The hard part is the solver:
  `fin_vol_solve` and the object-oriented tridiagonal code in
  `to_be_ccppized/linear_1d_operators.F90` (`TriDiagDecomp`, operator
  derived types with allocatable components) need a plain-array device
  path (`!$acc routine seq` per column, or a column-parallel kernel),
  bit-for-bit with the operator code (same operation order). The same
  solver is used by `gw_common` (`gpu-port-gw-orographic`); do it once for
  both. Replays exist (F2000_C4, uw_vdiff, hb_vdiff). Gain: cam4 cap syncs
  around the three (`diffuse_horizontal_momentum` 6 per step, plus
  `kvq`/`cgh`-style syncs before the other two) and lets the whole vertical
  diffusion group stay on the device. Do after
  `gpu-port-vertical-diffusion-simple`.
- `gpu-port-tropopause-find` — **GPU port of `tropopause_find`.** Added
  2026-11-08 (split out of `gpu-port-shared-utility-schemes`). The run
  routine (197 lines) calls `tropopause_findWithBackup` six times; those
  use five algorithms (`twmo`, `climate`, `cpp`, `hybridstobie`,
  `findChemTrop`) and `interpolateP/T/Z`, about 700 lines of column code
  in `tropopause_find.F90`. Module constants (`cnst_*`) need `!$acc
  declare` and an update after init; `tropP/T/Z` and `hstobie_*` are
  optional all the way down (substitute locals in the dispatcher); the
  public `tropopause_findWithBackup` must keep working from host callers
  (present-or-copy clauses). Replays: rk_stratiform, rrtmgp. Gain: 9 cam4
  cap syncs per step (cap_oracle after `acc-copy-residency`); used by
  rk_stratiform and rrtmgp too.
- `cap-pulls-unwritten-device-data` — **The cap pulls device data no
  device scheme ever writes.** Added 2026-11-10 (`gpu-port-tropopause-find`
  cap_oracle). Once `tropopause_find` lists `lat` as `present`, latitude
  becomes device data (entered once with `copyin`), and the cam4 cap then
  issues `update self(lat)` four times per step, before each CPU reader at
  the start of a phase function or block, although no scheme writes `lat`
  and the host copy is always current. `emit_coalesced_updates` tracks host
  currency only within one block. Fix: a variable that every scheme takes
  as `intent(in)` (and the host does not change between calls) never
  needs a pull. Small here (one value per column), but the same applies to
  any read-only device input.
- `tropopause-find-untested-algorithms` — **Three `tropopause_find`
  algorithms have no test data and stay CPU-only.** Added 2026-11-10 (user
  request, during `gpu-port-tropopause-find`). `tropopause_find_run` uses
  only `twmo`, `climate`, `cpp`, `hybridstobie` and `findChemTrop`, so the
  capture replays (`capture_rk_stratiform`, `capture_rrtmgp`
  `test_tropopause_find`) exercise only those. `tropopause_analytic`,
  `tropopause_stobie` and `tropopause_wmo` are reachable only through the
  public `tropopause_findWithBackup` (kept for CAM, which picks the
  algorithm itself), are not covered by any capture, and were left as host
  code in the port (comment in `tropopause_findUsing`). Risk: a GPU-built
  caller selecting one of them while its data are device-resident would
  read stale host copies. Revisit: get test data for them (a capture of a
  host that selects them, or a pFUnit test of `tropopause_findWithBackup`
  with each algorithm), then port them the same way and check CPU and GPU
  bit-for-bit. Also untested: the `hybridstobie` path without the
  `hstobie_*` outputs and every path with `tropP/T/Z` absent (the run
  always passes them).
- `gpu-diagnostics-conditional-sync` — **Dropped (2026-11-10)** -- per-field pulls in the diagnostics schemes put data movement into scheme source; reverted, superseded by the `gpu-history-accumulate` design project. CHANGELOG.md L14749.
- `gpu-port-shared-utility-schemes` — **atmospheric_physics: OpenACC
  ports of the utility schemes every suite uses**:
  `apply_constituent_tendencies`, `apply_heating_rate`, `qneg`,
  `geopotential_temp`,
  `clamp_number_concentrations`, `calculate_net_heating`,
  `tropopause_find` (now `gpu-port-tropopause-find`), and the 10 state converters in
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
- `rrtmgp-dry-static-energy-intent-out` — **atmospheric_physics:
  `rrtmgp_dry_static_energy_tendency` leaves its `intent(out)` outputs
  unassigned.** Found 2026-11-05 replaying c02i: `qrs_prime`/`qrl_prime`
  are `intent(out)` but set only when `calc_sw_heat`/`calc_lw_heat`
  (`= .not. dosw/dolw`, from `rrtmgp_pre`) are true, i.e. on
  non-radiation steps. On radiation steps the model relies on the host
  arrays keeping their previous values, which is undefined for
  `intent(out)`; the replay (`test_rrtmgp_dry_static_energy_tendency`,
  `qrl_prime` max diff 0.42) shows it. On the GPU it would be wrong for
  real: the intent-aware cap (`gpu-sync-intent-aware`) does not copy
  `intent(out)` data to the device before the call, so a ported scheme
  would return stale device values. Fix: `intent(inout)` for both in
  `schemes/rrtmgp/utils/rrtmgp_dry_static_energy_tendency.{F90,meta}`
  (bit-for-bit); upstream PR to ESCOMP/atmospheric_physics. Check
  `calculate_net_heating` and the other rrtmgp utilities for the same
  pattern (done 2026-11-05: `calculate_net_heating` is fine; the other
  findings are `rrtmgp-intent-out-unassigned`). Status 2026-11-05: change
  made in the submodule (uncommitted); the c03a recapture replays
  `test_rrtmgp_dry_static_energy_tendency` cleanly (CPU). Still to do:
  bit-for-bit rrtmgp `/cam-sima-test` (CPU + GPU pair), commit, upstream
  PR.
- `rrtmgp-intent-out-unassigned` — **atmospheric_physics: other RRTMGP
  schemes leave `intent(out)` arguments unassigned.** Audit of
  `schemes/rrtmgp/*.F90` and `utils/calculate_net_heating.F90`
  (2026-11-05, while fixing `rrtmgp-dry-static-energy-intent-out`; all
  are `intent = out` in the `.meta`). "Rad-step" = skipped when
  `dosw`/`dolw` is false.
  - Partial extent: `rrtmgp_sw_calculate_heating_rate_run` sets
    `hrate_clrsky` only for `k = ktopcam..pver` and never zeroes it (the
    LW scheme zeroes both arrays first).
  - Early return before any assignment (rad-step):
    `rrtmgp_sw_solar_var_run` `sfac` (`.not. dosw .or. nday == 0`);
    `rrtmgp_sw_gas_optics_run` `toa_src_sw`; `rrtmgp_inputs_run` all 19
    outputs (`.not. dosw .and. .not. dolw`), and its SW/LW derived types
    are initialized only inside `if (dosw .and. nday > 0)` / `if (dolw)`;
    `rrtmgp_lw_cloud_optics_run` all 5 outputs; `rrtmgp_sw_cloud_optics_run`
    all 12 outputs; `rrtmgp_sw_mcica_subcol_gen_run` `cloud_sw` (only
    inside `if (nday > 0 .and. dosw)`).
  - Conditional (config): `rrtmgp_lw_rte_run` `lw_Ds` (only with
    `doLWclrsky`/`use_lw_optimal_angles`); `rrtmgp_lw_cloud_optics_run`
    `snow_lw_abs`/`grau_lw_abs` (only with `do_snow`/`do_graupel`, no
    else); `rrtmgp_inputs_setup_init` `nextsw_cday` (not on the first
    restart step).
  - errmsg/errflg left unset: `rrtmgp_sw_cloud_optics_run` (never
    initialized; on the `dosw` path `errflg` is read at L148 after
    `get_liquid_optics_sw`, which sets it only when some `lamc > 0`),
    `rrtmgp_sw_mcica_subcol_gen_run` (only on error branches),
    `rrtmgp_sw_solar_var_setup_init` (only with `do_spectral_scaling`);
    helper `gam_liquid_lw` returns early without setting them, feeding
    `rrtmgp_lw_cloud_optics_run`'s check.
  - Minor: `rrtmgp_constituents_register` `rrtmgp_dyn_consts` entries
    after the first blank `rad_climate` name are never instantiated.
  Why it matters: an `intent(out)` value is undefined on entry, so code
  relying on the previous value is wrong by the standard; on the GPU the
  intent-aware cap does not copy `intent(out)` data to the device
  (`gpu-sync-intent-aware`), so a ported scheme would return stale
  device data; a capture replay of such an argument compares undefined
  values (and an `intent(out)` derived type's allocatable components are
  deallocated on entry). Fix per case: `intent(inout)` where later
  schemes rely on the kept value (rad-step outputs that persist), or
  assign a value on every path; initialize errmsg/errflg at the top.
  Decide case by case with the scheme owners (upstream PR to
  ESCOMP/atmospheric_physics); check each change is bit-for-bit.
- `gpu-port-rrtmgp-wrapper-schemes` — **atmospheric_physics: OpenACC
  ports of RRTMGP's 21 per-step CPU-only CCPP schemes** (see
  `gpu-port-scheme-checklist`: inputs/pre/post, cloud and aerosol
  optics, McICA subcolumn generation, flux and heating-rate calculation,
  gas-optics pre, solar variability, the subcycle counter).
  `solar_irradiance_data`, the three init-only `*_setup` schemes and the
  four `*_diagnostics` stay on the host. McICA's random numbers
  must stay reproducible against the snapshot (generate on the host and
  copy, or a matching device generator).
- `gpu-port-aerosol-optics` — **atmospheric_physics: GPU port of
  `aerosol_optics`.** Added 2026-11-09. `schemes/chemistry/aerosol_optics.F90`
  (556 lines; cam4, cam5/7, rrtmgp) runs on radiation steps; its optical
  properties feed the RRTMGP wrappers. Not portable as written: its
  bin/species/level loops call type-bound procedures through polymorphic
  pointers (`class(aerosol_properties)`, `class(aerosol_state)`:
  `aeroprops%get`, `aerostate%get_ambient_mmr`, `aerostate%wet_volume`,
  `aerosol_optics_sw_bin/lw_bin`), and the column loop branches on
  `select case (trim(spectype_d))` and `associated(specrefindex_d)` --
  OpenACC has no device dynamic dispatch. Approach (like `qneg`'s
  constituent properties): per bin, gather on the host what the objects
  hold (densities, refractive indices, species types as integer flags,
  pointers to the state's mixing ratios) into plain arrays, then device
  kernels for the column/level/wavelength arithmetic; keep the objects on
  the host (`gpu-ddt-deep-copy-residency`, not planned). The objects are
  CAM's BAM/MAM aerosol abstraction (`aerosol_optics_core`, shared with
  CAM), so agree the split with ESCOMP. Do it with
  `gpu-port-rrtmgp-wrapper-schemes`: ported alone it saves little, since
  its consumers stay on the CPU until then. Test: capture replays (cam4,
  rrtmgp) CPU and GPU, then the rrtmgp and cam4 GPU regressions.
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
| `tropopause_find` | `schemes/tropopause_find/tropopause_find.F90` | rrtmgp | `gpu-port-tropopause-find` |
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
| `wv_saturation` | `schemes/utilities/wv_saturation.F90` | pumas | none: init/final only (its `qsat` helpers: `gpu-port-wv-saturation`) |
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
- `suite-cap-mode-flags` — resolved 2026-10-30. CHANGELOG.md L13536.
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
- `expr-text-identity-keys` — **`_expr_text` builds Fortran text as an
  identity key.** `transforms/util/cap_shared.py` `_expr_text` renders a
  reference as Fortran (`exner(col_start:col_end, 1:nz)`), and the passes use
  the string to decide whether two references are the same
  (`merge_adjacent_updates`, the section check before a device push,
  `gpu_debug_print_pass` bounds) and whether a value has a definite name.
  Nothing prints it, but it is target syntax in a transform. Replace it with a
  structural key (a tuple of op kind, names, literals and sub-keys) and
  `has_definite_name` (added by `capture-size-bounds`), which decides from the
  ops. Found 2026-11-06.
- `generation-error-last` — **A failed generation ends with a summary
  line, not the cause.** Added 2026-11-07 (xdsl66n, F2000_C7/gw_cam7). When
  the optimizer subprocess fails, it prints its `Error:` (e.g. the host
  variable matching failure), then `ccpp_dsl`'s `finish_pipeline_stage`
  adds `Error: running ccpp optimizer failed (exit code 1)`, and CAM-SIMA's
  `cam_autogen.py` prints all of it (`ERROR: xdsl_ccpp cap generation
  failed:`, warnings first, then the errors, then that summary) before
  CIME's traceback. Read from the end, the output shows only the summary
  and the traceback. Wanted: (1) xdsl-ccpp -- no generic "... failed (exit
  code N)" line when the stage's subprocess already printed an `Error:`
  (keep it when the subprocess died silently: crash, signal); (2)
  CAM-SIMA -- in the CamAutoGenError message, warnings first and the
  `Error:` lines last, directly above CIME's traceback. Unit tests for both.
  (The stray `'` after the summary comes from CIME's exception wrapping.)
- `capgen-api-qmin` — resolved 2026-10-31. CHANGELOG.md L13618.
- `generic-suite-schemes` — resolved 2026-10-31. CHANGELOG.md L13591.
