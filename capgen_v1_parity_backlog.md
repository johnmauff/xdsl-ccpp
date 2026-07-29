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

**Progress: Stage 1 done, awaiting review.** Update the status line per
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

**Stage 2 -- Extend to full coverage.** [not started]
All six lifecycle phases (`register`, `initialize`, `finalize`,
`timestep_initial`, `timestep_final`, `run`); host-variable binding
(`model_var_name`/`model_module_name`, already computed by
`HostVariableMatchPass`); dimension classification.
Exit: covers everything `ResolvedVar` needs, validated against a
CAM-SIMA fixture that exercises constituents (not just helloworld).

**Stage 3 -- Design the real exposure mechanism.** [not started]
In-process object vs. serialized artifact. xdsl_ccpp's generation already
crosses a subprocess boundary (`run_frontend`/`run_opt` each shell out),
so a serialized format -- likely extending `--emit-datatable` rather than
inventing a second artifact -- is probably the more natural fit. This is a
real design decision to make explicit, not a default to fall into.
Exit: a stable, documented API/format, independent of any host-model
concern. This is the piece that gets its own PR into xdsl_ccpp's repo.

**Stage 4 -- Write the xdsl_ccpp-side adapter.** [not started]
`_resolved_vars_from_xdsl_ccpp(...)`, in CAM-SIMA's repo, translating
Stage 3's output into `ResolvedVar`.
Exit: matches the Stage 0 oracle.

**Stage 5 -- Write the capgen-v1-side adapter.** [not started]
`_resolved_vars_from_capgen_v1(...)`, also in CAM-SIMA's repo -- a thin
translation over the `CCPPDatabaseObj`/`Var` objects CAM-SIMA's real
submodule already provides. Small, low-risk, no xdsl_ccpp involvement.

**Stage 6 -- Refactor `write_init_files.py` to consume only `ResolvedVar`.** [not started]
Touch `gather_ccpp_req_vars`, `_find_and_add_host_variable`,
`collect_host_var_imports`, `get_dimension_info` -- the ~970 lines of
CAM-SIMA-hardcoded Fortran-emission logic stay untouched. Validate by
running the refactor *through the capgen-v1 adapter* against CAM-SIMA's
existing `test_write_init_files.py` fixtures and confirming byte-identical
output -- proves the refactor itself didn't break anything, deliberately
before xdsl_ccpp enters the picture at all.

**Stage 7 -- Validate xdsl_ccpp end-to-end through the refactored file.** [not started]
Same fixtures, same refactored `write_init_files.py`, now through the
xdsl_ccpp adapter. This is the actual "does xdsl_ccpp work as a real
replacement" checkpoint, cleanly isolated from "did the refactor regress
anything" (Stage 6) and "is the adapter translation correct" (Stage 4/5).

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
