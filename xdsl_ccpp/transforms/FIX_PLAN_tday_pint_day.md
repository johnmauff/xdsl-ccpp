# Plan: Fix t_day/pint_day SuiteOwned allocation bugs in xdsl_ccpp

## Context

The xdsl23 rrtmgp run fails with two distinct but related runtime errors:

1. **`t_day` (and `pmid_day`, `coszrs_day`, `toa_src_sw`, `sfac`, `alb_dir`, `alb_dif`)** —
   `Index '1' of dimension 1 of array 't_day.0' outside of expected range (1:0)`.
   These arrays are allocated at module level on the first `_run` call when `nday=0`
   (all-nighttime chunk). The `if (.not. allocated)` lazy guard prevents re-allocation
   on subsequent calls when `nday>0`. Arrays are permanently stuck at size 0.

2. **`pint_day`** — `Array bound mismatch for dimension 2 of array 'pint_day' (1/60)`.
   `pint_day` has second dimension `nlayp` (number_of_vertical_interfaces_in_RRTMGP).
   `nlayp` is produced only in `rrtmgp_inputs_setup._init`; `_resolve_alloc_dim_var_refs`
   searches only the current phase's `all_args` so it never finds `nlayp`, and silently
   drops the allocation.

**Capgen-v1 reference**: In `ccpp_rrtmgp_cap.F90` (capgen-baseline), ALL of these
variables are declared as **local allocatables** inside `rrtmgp_physics_after_coupler`,
allocated unconditionally with the current `nday` on every call, and deallocated at
subroutine end. No module-level, no lazy guard. That is the correct approach.

**Root causes confirmed by code exploration**:

- Bug 1: xdsl_ccpp's CCPP four-case rule (`suite_variable_model.py`) classifies these
  vars as `SUITE_OWNED` (intent=out + no host match) → `_build_module_vars` emits
  `ModuleVarOp` for them → `_maybe_schedule_framework_var_alloc` wraps the allocation in
  a `LazyAllocOp` (`if (.not. allocated)`). GPU residence is NOT a factor.
- Bug 2: `_resolve_alloc_dim_var_refs` only searches `all_args` for the current run phase.
  `nlayp` (init-phase SuiteOwned scalar) is in `data_ops` as a `HostVarRefOp` but is
  never consulted.
- Bug 3 (latent): `_inject_safe_deallocs` is completely broken — it excludes every
  SuiteOwned var because `interstitial_var_names` covers all of them. No module-level
  allocatable is ever deallocated.

---

## Fix Design

### Fix A — Run-local allocatable for `_run`-dimensioned SuiteOwned arrays (Bug 1)

**Discriminator**: A SuiteOwned array should be a LOCAL allocatable in the run subroutine
(not module-level) if any of its allocation dimensions is a scalar SuiteOwned variable
that is produced in the `_run` phase. This is checked via:

```python
def _is_run_local_var(entry: SuiteVarEntry, suite_model: SuiteVariableModel) -> bool:
    for dim_std_name in entry.alloc_dim_std_names:
        dim_entry = suite_model.get(dim_std_name.lower())
        if (dim_entry is not None
                and dim_entry.producing_phase == "_run"
                and dim_entry.rank == 0):
            return True
    return False
```

This correctly classifies:
- `t_day(nday, nlay)`: `nday` is `_run`-produced scalar → **run-local**
- `pint_day(nday, nlayp)`: `nday` is `_run`-produced scalar → **run-local**
- `sfac(nday, nswgpts)`: `nday` is `_run`-produced scalar → **run-local**
- `nlayp` itself: `_init`-produced scalar, rank=0 → stays **module-level** (correct)

**Changes needed** (all in `suite_cap.py`):

1. **`_build_module_vars` (~line 4112)**: Skip run-local vars from `allocatable_mod_vars`
   and `interstitial_var_names`. Collect them in a new `run_local_entries` list passed
   to `_assemble_func`.

2. **`_assemble_func` (~line 2464)**: For each run-local entry:
   - Emit a local allocatable declaration using `memref.AllocaOp(name_hint=name+"__alloc")`
     at the top of the run subroutine (the existing printer generates
     `real(kind_phys), allocatable :: t_day(:,:)` for these)
   - Emit `SafeDeallocOp` for each run-local var at the END of the run body, just before
     `ReturnOp`

3. **`_maybe_schedule_framework_var_alloc` (~line 3019)**: When the var being allocated
   is run-local, use plain `AllocateOp` (unconditional, no lazy guard) instead of
   `LazyAllocOp`. The existing pending-alloc mechanism already handles the timing (defers
   until after the producer scheme's call ops are emitted), so only the op type changes.

4. **`_build_framework_var_ref` (~line 2916)**: The `HostVarRefOp(name, "", var_type)`
   emitted for SuiteOwned vars already uses empty module name (same-module reference).
   When the var is declared locally instead of at module scope, the reference still works.
   No change needed here.

### Fix B — `data_ops` fallback in `_resolve_alloc_dim_var_refs` (Bug 2)

**Location**: `_resolve_alloc_dim_var_refs` (~line 1477–1543) in `suite_cap.py`.

After the current-phase `all_args` search fails and before returning `([], None)`, add:

```python
# Fallback: init-phase SuiteOwned scalar in data_ops (e.g. nlayp from _init)
fw_ref = data_ops.get(("std_name", alloc_dim.lower()))
if fw_ref is not None and _is_scalar_integer_ref(fw_ref):
    return ([fw_ref], None)
```

The key lookup form `("std_name", ...)` matches how `data_ops` is populated in
`_build_framework_refs`. The scalar-integer check mirrors the guard already applied to
loop-bound scalars elsewhere in the function. This makes `nlayp` resolvable for
`pint_day`'s local allocation.

Note: With Fix A in place, `pint_day` becomes run-local, so `AllocateOp` is used (not
`LazyAllocOp`). The allocation becomes `allocate(pint_day(nday, nlayp))` where:
- `nday`: pending-alloc resolved after the filter scheme (existing mechanism)
- `nlayp`: now resolvable via `data_ops` fallback

---

## Files to Modify

| File | Sections Changed |
|---|---|
| `xdsl_ccpp/transforms/suite_cap.py` | `_is_run_local_var` (new helper), `_build_module_vars`, `_maybe_schedule_framework_var_alloc`, `_assemble_func`, `_resolve_alloc_dim_var_refs` |

No changes to `suite_variable_model.py`, CAM-SIMA scheme `.F90`/`.meta` files, or
`ccpp_conventions.py`.

**Reusable ops** (already exist in `xdsl_ccpp/dialects/ccpp_utils.py`):
- `AllocateOp` (~line 980): plain `allocate(var(dims))`
- `SafeDeallocOp` (~line 728): `if (allocated(var)) deallocate(var)`
- `memref.AllocaOp` with `__alloc` suffix: local `allocatable` declaration (printer at
  `print_ftn.py` ~line 2042)

---

## Implementation Order

1. Add `_is_run_local_var` helper in `suite_cap.py`
2. Fix `_resolve_alloc_dim_var_refs` — data_ops fallback (Fix B, self-contained)
3. Fix `_build_module_vars` — skip run-local vars
4. Fix `_maybe_schedule_framework_var_alloc` — use `AllocateOp` for run-local
5. Fix `_assemble_func` — local decls + end-of-run deallocs
6. Locally regenerate cap and verify

---

## Verification

1. Locally regenerate `rrtmgp_cap.F90` using the same script as the lw_Ds verification.
2. Confirm the following NO LONGER appear as module-level declarations:
   `t_day`, `pmid_day`, `pint_day`, `coszrs_day`, `toa_src_sw`, `sfac`, `alb_dir`, `alb_dif`
3. Confirm `rrtmgp_physics_after_coupler` contains:
   - Local `real(kind_phys), allocatable :: t_day(:,:)` etc.
   - Unconditional `allocate(t_day(nday, nlay))` AFTER the rrtmgp_pre call (no `if .not. allocated`)
   - `allocate(pint_day(nday, nlayp))` after rrtmgp_pre call
   - `if (allocated(t_day)) deallocate(t_day)` etc. at end of subroutine
4. Full unit + FileCheck test suite passes (628/1/0 baseline).
5. Do NOT submit the job — check in with user after step 4.
