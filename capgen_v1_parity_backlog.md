# capgen-v1 parity backlog

## Context

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

## Workstream 1: Native introspection API + `ResolvedVar` adapter

### Problem

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

### Structural note

The two `ResolvedVar` translation functions (Stage 4, Stage 5 below) live
in **CAM-SIMA's own repo**, not xdsl_ccpp's -- CAM-SIMA already depends on
real `ccpp-framework` via its own submodule, so it's the one piece of this
whole picture that's supposed to know about both frameworks. xdsl_ccpp's
repo only ever grows the native capability (Stages 1-3); it never touches
capgen-v1 code. That's what actually resolves the "xdsl_ccpp depending on
capgen-v1" problem, as opposed to the vendored shim.

### Plan: staged, one stage at a time, pause for review between each

**Progress: Stage 2 done, awaiting review.** Update the status line per
stage as work lands (`not started` / `in progress` / `done, awaiting
review` / `done`).

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

### Post-Stage-7 follow-up: implemented Option 1, both parts

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
- **3/13 (`ddt`, `ddt2`, `ddt_array`) confirm the already-known DDT-chain
  gap unchanged**: diffs are exactly the documented Stage 4/6 shape (bare
  leaf name/module instead of the full dotted chain or array-ref
  resolution, e.g. `theta`/`physics_state` instead of `phys_state%theta`/
  `physics_types_ddt`) -- no new surprises, consistent with what Stage 4/6
  already flagged as unpopulated for this backend. **10/13 fixtures are now
  byte-identical to real capgen-v1 through xdsl_ccpp end to end** -- up
  from 0 before Stage 7's fixes.

**Stage 8 -- Real integration / upstream PRs.** [not started]
Stage 3's work as a PR to xdsl_ccpp (same workflow as the DDT fix);
Stages 4-7 as a PR to CAM-SIMA (`johnmauff/CAM-SIMA` fork ->
`ESCOMP/CAM-SIMA`).

Stages 1-3 can proceed independently of anything CAM-SIMA-side; 4-7 depend
on Stage 3 landing (or at least stabilizing) first.

---

## Workstream 2: Fix the DDT redefinition bug -- RESOLVED

### Problem (as understood before investigation)

Confirmed, reproducible bug: when a suite (a) generates both a host cap
and a suite cap, and (b) references a DDT shared between host and scheme
(e.g. `ccpp_constituent_prop_ptr_t`), xdsl's IR verifier rejected the
combined module with `Redefinition of symbol
"ccpp_constituent_prop_ptr_t"`. Reproduced via CAM-SIMA's
`test_simple_reg_constituent_write_init` fixture.

### Actual root cause (confirmed by direct MLIR inspection)

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

### Fix applied

`xdsl_ccpp/transforms/ccpp_cap.py`, in `_generate_ccpp_cap_module`: route
the second (generic) stub-emission path through the same
`shared_seen_host_globals` dedup already used for the constituent-API
stubs, instead of a raw `all_globals.extend(...)`. Six-line change,
`constituent_cap.py` untouched (its stubs are still necessary on their
own). Diff lives uncommitted in the sandbox
(`xdsl_ccpp/transforms/ccpp_cap.py`) pending review.

### Verification

- Direct MLIR inspection: zero duplicate symbols in the generated
  submodule after the fix; `module.verify()` passes.
- `test/unit/python/test_write_init_files.py` (CAM-SIMA, real subprocess
  path, all 16 tests): `FAILED (errors=15)` -> `OK`.
- Full `test/run_python_unit_tests.sh`: `4 out of 16 test collections
  FAILED` -> `3 out of 16` (the remaining 3 are the pre-existing, unrelated
  missing-CIME-external issue, not this bug).
- `examples/helloworld` smoke test (non-constituent case): still passes,
  no regression.

### Remaining follow-up (not yet done)

- Add a permanent filecheck regression test under `tests/filecheck/`
  covering host-cap + suite-cap + constituent-variable generation
  together, so this doesn't silently regress.
- Consider whether `_generate_constituent_api`'s hardcoded stub list
  should eventually be unified with the generic `ddt_source_module`
  mechanism rather than living as a second parallel path at all --
  today's fix makes the two paths *coexist safely*, it doesn't merge
  them.

---

## Smaller interface-shape gaps (fold into Workstream 1's adapter boundary)

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

## Not gaps (confirmed, don't re-litigate)

- `degC` vs `C` unit-string handling, and metadata declaring a custom
  kind (`kind_dyn_val`-style) with no backing Fortran declaration: both
  were strictness differences in the *vendored capgen-v1 parser*, not
  xdsl_ccpp. xdsl_ccpp handled both cases natively without issue.
- `memory_space` (GPU-directive metadata extension) and the
  `horizontal_loop_extent` -> `horizontal_dimension` vocabulary migration
  are one-directional xdsl_ccpp extensions/improvements, not gaps.

## Untested -- unknown, not confirmed either way

- Real production physics suites from `NCAR/atmospheric_physics`.
  Everything exercised so far was either xdsl_ccpp's own demo examples
  or CAM-SIMA's synthetic unit-test fixtures.
- The `datatable_report()`/`DatatableReport` query path itself
  (`utility_files`, `dependencies`, as called by `cam_autogen.py`) --
  every test so far used the vendored capgen-v1 implementation for this;
  xdsl_ccpp's own (differently-shaped) datatable output has not been
  checked against these same queries. This should fall out of
  Workstream 1's native introspection design.
- Nested suites, subcycles, multi-suite builds, and GPU/`memory_space`
  directives in an actual CAM-SIMA context (only tested in isolation via
  xdsl_ccpp's own examples).
