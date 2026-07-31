# Handoff: continuing the CAM-SIMA / xdsl_ccpp integration work elsewhere

Written 2026-07-29, for picking this project back up in a new environment
(e.g. an HPC system with a real Fortran compiler, which the sandbox this
work was done in does not have) or a new AI assistant session, without
re-deriving everything from scratch.

**Read `capgen_v1_parity_backlog.md` first.** That is the primary record --
every stage's motivation, findings, root causes, and validation results are
written there in detail, not just discussed in conversation. This document
covers specifically the things that *aren't* in that file: current
merge/branch state, local setup that deliberately isn't committed, ad hoc
validation recipes, and the reasoning behind the PR strategy.

## 1. Current state as of this writing

**xdsl_ccpp** (`johnmauff/xdsl-ccpp`):
- `main`: everything through the Stage 3-7 work is merged (PRs #48-#53) --
  vocabulary normalization, the DDT redefinition bug fix, the
  `--emit-resolved-vars` introspection mechanism, the `write_init_files.py`
  refactor's xdsl_ccpp-side support, host-table/protected-status
  propagation.
- `ddt-chain` branch: one commit on top of `main` ("Fixed DDT chaining
  issue") -- the DDT member chain-resolution fix (reusing
  `cap_shared.py`'s existing `_build_ddt_resolution_maps`/
  `_resolve_ddt_access_path`/`_resolve_member_subscripts`) plus the new
  `host_vars` JSON key. Not yet merged to `main` or PR'd.
- Untracked, deliberately never committed: `schema/`, `scripts/`, `src/` --
  vendored capgen-v1 reference material kept around for local comparison
  only (see backlog Context section for why these exist and why they were
  never meant to be a permanent dependency).

**CAM-SIMA** (`johnmauff/CAM-SIMA`):
- `development`: piece 1 merged (PR #1) -- the `ResolvedVar` abstraction
  (`resolved_var.py`), the capgen-v1 adapter (`resolved_var_capgen_v1.py`),
  and the refactored `write_init_files.py`/`cam_autogen.py` that consumes
  it instead of a raw `CCPPDatabaseObj`. This is a *behavior-preserving*
  refactor -- `cam_autogen.py` still hardcodes `Capgenv1ResolvedVars`, so a
  real CAM-SIMA build today still only ever uses real capgen-v1. Also
  includes the `pr_mod_file_tests.py` CI fix (resolves the target repo
  dynamically instead of hardcoding `ESCOMP/CAM-SIMA`, so the lint check
  works on forks).
- `xdsl-ccpp-adapter` branch: one commit ("Feature branch for the
  xdsl-ccpp adapter work") adding `resolved_var_xdsl_ccpp.py`, already in a
  **draft** PR against `johnmauff/CAM-SIMA`. As of this writing there is an
  **uncommitted** update to that same file on this branch (the DDT-chain
  consumption: reading `import_name`/`call_expr`/`array_ref_dims` from the
  JSON instead of defaulting them all to the bare local name, plus the
  `host_vars` fallback in `resolve_by_standard_name`) -- commit this before
  doing anything else with that branch.
- Not wired up anywhere: nothing in `cam_autogen.py` can select
  `XdslCcppResolvedVars` yet. Only `Capgenv1ResolvedVars` is reachable from
  the real build.

Validated so far (Stage 7 + the two follow-up fixes): 12 of 13
`test_write_init_files.py` fixtures produce byte-identical generated
Fortran through xdsl_ccpp vs. real capgen-v1; the 13th (`ddt_array`) is
functionally identical with one cosmetic, non-functional case difference
(see backlog for detail). **This is Python-level text-comparison only --
see section 4 below for exactly what that does and does not prove.**

## 2. Local setup that will NOT transfer via git

**The `ccpp_framework` symlink override.** CAM-SIMA's `ccpp_framework` is a
real git submodule (`fxtag = sima_2026-07-15`, pointing at
`NCAR/ccpp-framework`). In this sandbox it was replaced with a symlink
pointing at the local xdsl-ccpp checkout instead, so that CAM-SIMA's build
scripts (which do `sys.path.append(os.path.join(cam_root, "ccpp_framework",
"scripts"))` and then `from ccpp_capgen import capgen`) pick up
xdsl-ccpp's *vendored bridge script* (`xdsl-ccpp/scripts/ccpp_capgen.py`)
instead of real capgen-v1. This override:
- shows up as `git status`'s `T ccpp_framework` (type-changed) in the
  CAM-SIMA sandbox, every time
- must never be committed -- doing so would corrupt the submodule
  reference for anyone else who clones that branch
- needs to be recreated by hand in any new environment that wants to
  reproduce this same test setup: remove/rename the real submodule
  checkout, symlink `ccpp_framework` to wherever the xdsl-ccpp checkout
  lives locally

If you don't need the vendored-bridge test path (e.g. because you're
setting up a from-scratch environment specifically to test the *native*
`--emit-resolved-vars` path, not the bridge), you likely don't need this
symlink at all -- see section 4.

## 3. Ad hoc validation recipes (not saved as real scripts anywhere)

These were one-off scripts in a scratch directory, not committed. The
underlying recipe is worth preserving even though the exact scripts are
gone.

**Testing against real capgen-v1 directly (bypassing the symlink
override):** prepend the real `ccpp-framework` checkout's `scripts/`
directory to `PYTHONPATH` *before* CAM-SIMA's own `sys.path.append` runs --
since that append happens at import time, anything already on
`PYTHONPATH` takes precedence:
```bash
PYTHONPATH=/path/to/real/ccpp-framework/scripts \
  python3 -m pytest test_write_init_files.py test_cam_autogen.py -q
```
This is how Stage 6/7's "byte-identical against real capgen-v1" claims
were actually verified -- not through the symlink-overridden path.

**Testing the real xdsl_ccpp CLI end to end (the recipe behind the
Stage 7 sweep):**
1. Run `gen_registry(...)` (from CAM-SIMA's `generate_registry_data.py`)
   against the fixture's registry XML to get the registry-generated
   `.meta` file, exactly as `test_write_init_files.py` itself does.
2. Invoke the real xdsl_ccpp CLI as a subprocess, with `PYTHONPATH` set to
   the xdsl-ccpp checkout (not the symlink):
   ```bash
   PYTHONPATH=/path/to/xdsl-ccpp python3 -m xdsl_ccpp.tools.ccpp_dsl \
     --suites <suite.xml> --scheme-files <scheme.meta> \
     --host-files <host.meta>,<registry-generated.meta> \
     --host-name cam --tempdir <tmp> -o <tmp> \
     --emit-resolved-vars <tmp>/resolved_vars.json
   ```
3. Load that JSON via `resolved_var_xdsl_ccpp.py`'s `XdslCcppResolvedVars`,
   call `write_init_files.write_init_files(resolved_vars, ic_names,
   constituents, vars_init_value, ...)` -- **use whatever `ic_names`/
   `constituents`/`vars_init_value` that specific fixture's own
   `test_write_init_files.py` test method actually captures from its own
   `gen_registry()` call** (most pass empty defaults, but a few don't --
   this was a real bug in the first draft of the sweep harness, worth not
   repeating).
4. `diff` the generated `phys_vars_init_check_*.F90`/`physics_inputs_*.F90`
   against the golden files already checked into
   `test/unit/python/sample_files/write_init_files/`.

Repeating this loop across all (or a representative subset of) the ~16
fixtures in `test_write_init_files.py` is exactly how the 12/13 (soon
hopefully more) figure was produced.

## 4. What "12/13 byte-identical" does and does not prove

Said plainly, since it matters for scoping what's left: this is **Python
text-comparison of generated source only.**

Verified: the *text* of `write_init_files.py`'s output Fortran matches
what real capgen-v1 produces, for a curated set of 13 small test fixtures,
via the real xdsl_ccpp CLI (not the vendored shim).

**Not verified, and needed before anything resembling a real end-to-end
test:**
- **Compilation.** No Fortran compiler was available in the sandbox this
  work was done in. Zero evidence the generated code even parses.
- **The suite-cap/physics-dispatch Fortran itself.** Everything diffed was
  `write_init_files.py`'s output (variable registration + IC-file
  reading). The actual CCPP cap code that dispatches to physics schemes
  (`suite_cap.py`/`ccpp_cap.py`'s own output) was a necessary input to get
  the JSON, but was never diffed against capgen-v1's own suite-cap
  generation as part of *this* effort (it has its own, separate test
  coverage inside the xdsl-ccpp repo's own test suite, including some
  gfortran-verified cases -- see `tests/unit/test_run_dispatch_col_bounds_fallback.py`'s
  docstring for one example -- but that's a different, narrower scope than
  "matches capgen-v1 for a full CAM-SIMA-shaped suite").
- **Real build wiring.** `cam_autogen.py` cannot select xdsl_ccpp today --
  see section 1. Nothing has gone through the actual CIME/`cam_autogen.py`
  call path with xdsl_ccpp as the backend.
- **Real physics suites.** Only the 13 small `test_write_init_files.py`
  fixtures, not CAM-SIMA's actual `atmospheric_physics` scheme collection.
- **CAM-SIMA's own Fortran-level test tiers.** The repo has
  `test/unit/fortran` (a CMake/pFUnit-based Fortran unit test suite -- the
  natural next tier, actually compiling and running generated code in
  isolation) and `test/system` (full case-level build+run scripts -- needs
  a complete HPC build environment: MPI, NetCDF, etc.). Neither has been
  touched with xdsl_ccpp in the picture at all.

**Suggested order of next steps on a machine with a real compiler:**
1. Wire `cam_autogen.py` to actually be able to select
   `XdslCcppResolvedVars` (today it's hardcoded) -- probably behind an
   explicit flag/config value rather than silently swapping backends.
2. Get `test/unit/fortran` building and passing against xdsl_ccpp-generated
   code for at least one of the already-Python-validated fixtures. This is
   the first point anything gets *compiled*, not just text-diffed.
3. Only after that, consider a real physics suite and/or `test/system`.

## 5. Why piece 1 / piece 2 were split, and what that means going forward

Piece 1 (the `ResolvedVar` refactor, capgen-v1 adapter, `write_init_files.py`
changes) and piece 2 (the xdsl_ccpp adapter) were deliberately kept on
separate branches/PRs rather than one combined PR, because:
- Piece 1 is behavior-preserving and stands on its own architectural merit,
  independent of whether xdsl_ccpp ever becomes viable -- a reviewer can
  approve it without needing to evaluate xdsl_ccpp's readiness at all.
- Piece 2 is explicitly exploratory and still under active testing.
  Bundling it with piece 1 would mean every future rebase/review of the
  stable refactor drags the still-changing adapter along with it.
- This also means piece 2's branch should keep being rebased onto
  `development` as it evolves, rather than merged, until xdsl_ccpp's own
  testing (including the compiler-level work in section 4) is far enough
  along to actually propose adoption to someone else.

The DDT-chain fix (xdsl-ccpp's `ddt-chain` branch, and the corresponding
uncommitted update to CAM-SIMA's `resolved_var_xdsl_ccpp.py` on
`xdsl-ccpp-adapter`) belongs to piece 2 for the same reason -- it's real
progress, but on the still-exploratory side of the split.

## 6. If starting a fresh AI assistant session

Point it at both repos in their current states, and ask it to read
`capgen_v1_parity_backlog.md` and this file before doing anything else.
That should reconstruct the substance of this work without needing this
specific conversation. The one thing genuinely lost is this conversation's
moment-to-moment back-and-forth (what was tried and discarded, minor dead
ends) -- but the *findings* that survived that process are all written
down in the backlog, which is the part that actually matters.
