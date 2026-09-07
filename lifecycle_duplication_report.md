# xdsl_ccpp Lifecycle Code Duplication Report

**Date**: 2026-09-06  
**Scope**: Duplication between CAM-specific and non-CAM lifecycle code generation in `xdsl_ccpp/transforms/`

---

## Architecture Overview

xdsl_ccpp has two separate lifecycle code generation paths:

### Non-CAM (generic) path
- **`lifecycle_cap.py:_generate_lifecycle_fn`** — generates the flat lifecycle dispatchers (`ccpp_register`, `ccpp_init`, `ccpp_final`) and their phase variants as MLIR `FuncOp`s, using xDSL IR ops (`HostVarRefOp`, `CapVarRefOp`, `scf.IfOp`, `func.CallOp`, etc.)
- **`run_dispatch.py:_generate_run_fn`** — generates the per-group run-phase dispatchers (`ccpp_physics_run`, `ccpp_physics_timestep_init`, `ccpp_physics_init`, etc.) as MLIR `FuncOp`s with the same IR-based approach
- Both are called from `ccpp_cap.py:_generate_ccpp_cap_module`, driven by the `lifecycle_specs` table (lines 1279–1321)

### CAM-specific path
- **`ccpp_cap.py:_generate_cam_lifecycle_wrappers`** (lines 842–1228) — generates `cam_ccpp_physics_*` subroutines (register, initialize, finalize, run, timestep_initial, timestep_final) by **string concatenation**, producing raw Fortran lines wrapped in a `ConstituentApiOp`
- Gated by `if self.cam_host:` (line 1653), so non-CAM CI/examples builds are unaffected
- These wrappers call the IR-generated dispatchers above, bridging from the CAM host interface (simplified signatures, error propagation via `physics_types` module-level vars) to the generic CCPP protocol

---

## Already-Resolved Duplications

For reference, the following were identified and extracted into `cap_shared.py` before this audit:

| Helper | Previously in | Extracted to |
|--------|---------------|--------------|
| `_build_no_suite_matched_false_ops` | `run_dispatch.py` ×2, `lifecycle_cap.py` ×1 | `cap_shared.py:195` |
| `_assert_call_arg_count_matches_signature` | `lifecycle_cap.py`, `run_dispatch.py` | `cap_shared.py:149` |
| `_iter_schemes` | `ccpp_cap.py`, `suite_cap.py` | `cap_shared.py:172` |
| `_collect_ddt_use_stubs` | `ccpp_cap.py`, `suite_cap.py` | `cap_shared.py:96` |
| `_rank_of` | `ccpp_cap.py`, `run_dispatch.py` | `cap_shared.py:135` |
| `LIFECYCLE_POSTFIX_ALIASES` | `lifecycle_cap.py`, `suite_cap.py` | `cap_shared.py:231` |
| `SUITE_FN_INFIX` | ~15–20 hand-maintained copies | `cap_shared.py:253` |

These are resolved. The rest of this report covers remaining issues.

---

## Finding 1 (HIGH): Phase table duplication between `lifecycle_specs` and `_generate_cam_lifecycle_wrappers`

### Location
- `ccpp_cap.py` lines 1279–1321: `lifecycle_specs` — 7-row list controlling which dispatchers are generated
- `ccpp_cap.py` lines 987–1181 (inside `_generate_cam_lifecycle_wrappers`): 6 independent phase checks/blocks using `_has_group_lifecycle("init")`, `_has_group_lifecycle("final")`, `_has_group_lifecycle("timestep_init")`, `_has_group_lifecycle("timestep_final")`

### The duplication
`lifecycle_specs` is the authoritative table that drives the non-CAM dispatcher loop. `_generate_cam_lifecycle_wrappers` independently re-enumerates the same phases in its own parallel structure:

```python
# lifecycle_specs (line 1307-1320):
("ccpp_physics_run",            None,                  f"{SUITE_FN_INFIX}_",               "__per_group__"),
("ccpp_physics_timestep_init",  "_timestep_initialize", f"{SUITE_FN_INFIX}_timestep_init_", "__per_group__"),
("ccpp_physics_timestep_final", "_timestep_finalize",   f"{SUITE_FN_INFIX}_timestep_final_","__per_group__"),
("ccpp_physics_init",           "_init",               f"{SUITE_FN_INFIX}_init_",           "__per_group__"),
("ccpp_physics_final",          "_finalize",           f"{SUITE_FN_INFIX}_final_",          "__per_group__"),

# _generate_cam_lifecycle_wrappers (lines 987-990):
has_physics_init  = _has_group_lifecycle("init")
has_physics_final = _has_group_lifecycle("final")
has_tsinit  = _has_group_lifecycle("timestep_init")
has_tsfinal = _has_group_lifecycle("timestep_final")
```

Each phase that exists in `lifecycle_specs` also has a dedicated code block in `_generate_cam_lifecycle_wrappers` (register/initialize/finalize/run/timestep_initial/timestep_final).

### Risk
Adding a new lifecycle phase (e.g., a `begin_run` or `physics_step` phase for a future CCPP protocol extension) currently requires:
1. Adding a row to `lifecycle_specs` — drives IR-based dispatcher generation
2. Adding a corresponding subroutine block in `_generate_cam_lifecycle_wrappers` — drives the CAM wrapper string

If step 2 is missed, the CAM host model gets no wrapper for the new phase and will silently not call it.

### Fix
Pass `lifecycle_specs` (or the already-generated `lifecycle_fns` dict) into `_generate_cam_lifecycle_wrappers` so it can derive phase presence from the canonical source instead of re-checking independently. The inner `_has_group_lifecycle` function can be replaced by a check against `lifecycle_fns`:

```python
# Instead of:
has_physics_init = _has_group_lifecycle("init")

# Use:
has_physics_init = "ccpp_physics_init" in lifecycle_fns
```

Since `lifecycle_fns` is already passed to `_generate_cam_lifecycle_wrappers`, this mapping is available. The remaining step is replacing the hardcoded `_has_group_lifecycle("init")` calls with lookups into `lifecycle_fns`. This is a small mechanical change, not a rewrite.

---

## Finding 2 (MEDIUM): String-based code generation inside an IR-based pipeline

### Location
- `ccpp_cap.py:_generate_cam_lifecycle_wrappers` (lines 842–1228): returns `ConstituentApiOp("\n".join(lines), public_names)` — a raw Fortran text blob
- All other lifecycle/run generators (`_generate_lifecycle_fn`, `_generate_run_fn`): return `func.FuncOp` (proper xDSL IR)

### The duplication
The codebase uses xDSL IR as the single code representation that `print_ftn.py` lowers to Fortran. This gives:
- Type safety at the IR level (MLIR verification passes)
- Automatic USE statement deduplication via `llvm.GlobalOp` stubs
- Extensibility (GPU passes can walk IR; string blobs are opaque)
- Ability to run analysis passes (e.g., `gpu_ccpp_cap_pass.py`) over generated code

`_generate_cam_lifecycle_wrappers` bypasses all of this and concatenates Fortran strings. It works because the CAM wrappers are thin (6 subroutines calling the IR-generated dispatchers with fixed argument mappings), but it is architecturally inconsistent and will not scale cleanly if the CAM adapter interface grows (e.g., GPU directives, additional host-model arguments, or new phases with richer signatures).

The specific issue is that `_generate_cam_lifecycle_wrappers` constructs Fortran USE statements by direct string formatting (`_format_use_stmts`), whereas the IR-based path achieves the same via `llvm.GlobalOp` stubs recognized by `print_ftn.py`. Two different mechanisms for the same concept.

### Risk
- If `print_ftn.py`'s USE statement emission logic changes, the IR-generated dispatchers update automatically; the string-based CAM wrappers do not
- GPU directive passes (`gpu_ccpp_cap_pass.py`, `gpu_data_pass.py`) can walk IR FuncOps but cannot instrument `ConstituentApiOp`'s raw text — CAM host GPU physics would require a parallel string-manipulation path or a special-case carve-out
- Any correctness checker that walks the IR (e.g., verify()) cannot validate the generated CAM wrapper code

### Fix (phased)
**Phase A** (low risk, targeted): Factor the `_build_dispatcher_call` + `_group_dispatch_block` + `_format_use_stmts` helpers out of `_generate_cam_lifecycle_wrappers` into module-level functions with documented interfaces, so future changes have clear seams.

**Phase B** (medium effort): Rewrite `_generate_cam_lifecycle_wrappers` to produce proper `func.FuncOp` IR using the same pattern as `_generate_lifecycle_fn`. Each `cam_ccpp_physics_*` wrapper would become an IR FuncOp whose body calls the existing IR-generated `ccpp_*` dispatcher FuncOps via `func.CallOp`. CAM-specific host variables (`lc_errmsg`, `lc_errcode`, etc.) become `HostVarRefOp`s referencing the `physics_types` / `physics_grid` modules. `_CAM_STD_EXPRS` becomes the mapping used to construct those `HostVarRefOp`s, exactly as `_CAM_STD_EXPRS` today drives the string construction.

This is the right long-term architecture. It unifies both paths, and `print_ftn.py`'s existing `HostVarRefOp` printer already handles the `use physics_types, only: errmsg => lc_errmsg` pattern via `GlobalOp` stubs. Phase B effort is medium — about the same scope as the `_generate_lifecycle_fn` extraction that already happened.

---

## Finding 3 (LOW): Near-identical `_synthesize_instance_number_arg` / `_synthesize_number_of_instances_arg` in `suite_cap.py`

### Location
- `suite_cap.py` lines 408–455: `_synthesize_instance_number_arg(meta_data, all_args)`
- `suite_cap.py` lines 458–488: `_synthesize_number_of_instances_arg(meta_data, all_args)`

### The duplication
These two functions are byte-for-byte identical in structure, differing only in which CCPP standard name constant they synthesize:

```python
# _synthesize_instance_number_arg (lines 441-455):
std_key = CCPP_INSTANCE_NUMBER_STD_NAME.lower()
if std_key in all_args: return
if not _is_multi_instance_host(meta_data): return
host_var = _resolve_host_only_std_name(meta_data, CCPP_INSTANCE_NUMBER_STD_NAME)
new_arg = CCPPArgument(host_var.name)
new_arg.setAttr("standard_name", CCPP_INSTANCE_NUMBER_STD_NAME)
...

# _synthesize_number_of_instances_arg (lines 473-488):
std_key = CCPP_NUMBER_OF_INSTANCES_STD_NAME.lower()
if std_key in all_args: return
if not _is_multi_instance_host(meta_data): return
host_var = _resolve_host_only_std_name(meta_data, CCPP_NUMBER_OF_INSTANCES_STD_NAME)
new_arg = CCPPArgument(host_var.name)
new_arg.setAttr("standard_name", CCPP_NUMBER_OF_INSTANCES_STD_NAME)
...
```

### Risk
If the `CCPPArgument` synthesis pattern needs to change (e.g., adding a new required attribute), both functions must be updated independently. They are already slightly out of sync on their docstrings.

### Fix
Extract to a single `_synthesize_host_scalar_arg(meta_data, all_args, std_name_const)` and call it twice:

```python
def _synthesize_host_scalar_arg(meta_data, all_args, std_name_const) -> None:
    std_key = std_name_const.lower()
    if std_key in all_args:
        return
    if not _is_multi_instance_host(meta_data):
        return
    host_var = _resolve_host_only_std_name(meta_data, std_name_const)
    if host_var is None:
        return
    new_arg = CCPPArgument(host_var.name)
    new_arg.setAttr("standard_name", std_name_const)
    new_arg.setAttr("type", host_var.getAttr("type"))
    new_arg.setAttr("intent", "in")
    if host_var.hasAttr("kind"):
        new_arg.setAttr("kind", host_var.getAttr("kind"))
    new_arg.setAttr("dimensions", 0)
    new_arg.setAttr("ownership_kind", ArgOwnershipKind.HostMatched)
    all_args[std_key] = new_arg
```

Low risk, straightforward mechanical extraction.

---

## Finding 4 (LOW): `_CCPP_DDT_MODS` dict defined inline in `_generate_lifecycle_fn`

### Location
- `lifecycle_cap.py` lines 570–574: `_CCPP_DDT_MODS = {"ccpp_constituent_properties_t": _CCPP_CONSTITUENT_MOD}` defined inside the else branch of the fallback-alloca path

### The duplication
`_CCPP_CONSTITUENT_MOD = "ccpp_constituent_prop_mod"` is already a module-level constant in `cap_shared.py` (line 89). The dict that maps DDT type names to modules is defined locally, hidden inside a conditional branch. If a new DDT type from another CCPP module were added (e.g., a second constituent type from a different module), this inline dict would be the only place needing update — and it is easy to miss.

### Risk
Low — currently only one DDT type is handled, and both `lifecycle_cap.py` and `run_dispatch.py` each have their own version (run_dispatch.py's version is built differently via `collect_ddt_source_modules`). The maintenance risk is contained.

### Fix
Extract `_CCPP_DDT_MODS` to module level in `cap_shared.py` alongside `_CCPP_CONSTITUENT_MOD`:

```python
# cap_shared.py
_CCPP_DDT_MODS: dict[str, str] = {
    "ccpp_constituent_properties_t": _CCPP_CONSTITUENT_MOD,
}
```

Import and use in `lifecycle_cap.py`. One-line change per file.

---

## Finding 5 (MINOR): `_CAM_STD_EXPRS` silently absorbs `FRAMEWORK_STD_NAME_TO_CAP_VAR`

### Location
- `ccpp_cap.py` lines 885–886 (inside `_generate_cam_lifecycle_wrappers`):
  ```python
  for _std, _expr in FRAMEWORK_STD_NAME_TO_CAP_VAR.items():
      _CAM_STD_EXPRS.setdefault(_std, (_expr, None, False))
  ```

### The issue
`FRAMEWORK_STD_NAME_TO_CAP_VAR` (cap_shared.py lines 83–87) has 3 entries; `_CAM_STD_EXPRS` has 6 CAM-specific entries, and the `setdefault` absorbs the framework ones automatically. The absorption assumes `(expr, None, False)` — no USE entry, no qmin preamble. This is correct for pure cap-var references (lc_constituent_array etc.), but the assumption is implicit.

### Risk
Very low. The current behavior is correct. If a new `FRAMEWORK_STD_NAME_TO_CAP_VAR` entry needed a USE statement in the CAM context, the silent absorption would be wrong — but the framework cap vars by definition live in the cap module itself (not an external module to USE), so this case cannot arise.

### Fix (optional)
Add an assertion after the `setdefault` loop:

```python
for _std, _expr in FRAMEWORK_STD_NAME_TO_CAP_VAR.items():
    assert _std not in _CAM_STD_EXPRS or _CAM_STD_EXPRS[_std][1] is None, (
        f"Framework std_name {_std!r} already in _CAM_STD_EXPRS with a USE entry "
        f"-- setdefault will silently lose it"
    )
    _CAM_STD_EXPRS.setdefault(_std, (_expr, None, False))
```

This documents the invariant and catches any future violation.

---

## Prioritized Action Plan

| Priority | Finding | Effort | Risk | Impact |
|----------|---------|--------|------|--------|
| 1 (HIGH) | Phase table coupling: use `lifecycle_fns` keys instead of `_has_group_lifecycle` in `_generate_cam_lifecycle_wrappers` | Small (< 1 day) | Low | Prevents phase-omission bugs when adding new lifecycle phases |
| 2 (MEDIUM) | Phase A: factor out `_build_dispatcher_call` / `_group_dispatch_block` / `_format_use_stmts` as module-level functions | Small (few hours) | Very low | Improves testability and readability; prerequisite for Phase B |
| 3 (MEDIUM) | Phase B: rewrite `_generate_cam_lifecycle_wrappers` to produce IR FuncOps instead of strings | Medium (2–3 days) | Medium | Unifies both paths; enables GPU pass coverage of CAM wrappers |
| 4 (LOW) | Extract `_synthesize_host_scalar_arg` from the two near-identical functions in `suite_cap.py` | Trivial (1 hour) | Very low | Eliminates maintenance-divergence risk for multi-instance support |
| 5 (LOW) | Promote `_CCPP_DDT_MODS` to module level in `cap_shared.py` | Trivial (30 min) | Very low | Single source of truth for DDT-module mapping |
| 6 (MINOR) | Add assertion after `FRAMEWORK_STD_NAME_TO_CAP_VAR` absorption in `_CAM_STD_EXPRS` | Trivial (5 min) | Zero | Documents and guards a silent assumption |

---

## Notes on What Is NOT Duplicated

Several things that look like duplication are actually intentional separation:

- **suite-name if/else dispatch**: `lifecycle_cap.py` builds it via xDSL IR (`scf.IfOp`); `_generate_cam_lifecycle_wrappers` builds it via string (`if (trim(suite_name) == ...)`). These operate at different levels (generic dispatcher vs CAM-specific thin wrapper calling that dispatcher) and serve different call sites.

- **Error variable handling**: `lifecycle_cap.py` uses `memref.AllocaOp` / `HostVarRefOp` members (for the generic/`ccpp_info_t` case); the CAM wrappers use `physics_types`-module references. These are different CCPP error-propagation conventions for different host models, not duplicate implementations of the same convention.

- **USE statement emission**: `lifecycle_cap.py` uses `llvm.GlobalOp` stubs (recognized by `print_ftn.py`); `_generate_cam_lifecycle_wrappers` uses `_format_use_stmts` strings. These are the same IR vs string generation split described in Finding 2 — a real structural inconsistency, but not accidental duplication of identical logic.
