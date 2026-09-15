# Session Status — t_day/pint_day run-local fix (2026-09-09)

## What We Are Doing

Fixing two related xdsl_ccpp bugs that cause the rrtmgp physics cap to fail at runtime:

**Bug 1 (t_day, pmid_day, coszrs_day, toa_src_sw, sfac, alb_dir, alb_dif)**:
- Symptom: `Index '1' of dimension 1 of array 't_day.0' outside of expected range (1:0)`
- Root cause: xdsl_ccpp generates these as module-level SuiteOwned allocatables with
  `if (.not. allocated)` lazy guard. On first call when nday=0 (all-nighttime chunk),
  `allocate(t_day(0, nlay))` fires. On subsequent calls with nday>0, the lazy guard
  prevents re-allocation — arrays permanently stuck at size 0.
- Correct behavior (capgen-v1 reference in `ccpp_rrtmgp_cap.F90`): these are LOCAL
  allocatables inside `rrtmgp_physics_after_coupler`, allocated unconditionally with
  current nday on every call, deallocated at subroutine end.

**Bug 2 (pint_day — never allocated)**:
- Symptom: `Array bound mismatch for dimension 2 of array 'pint_day' (1/60)`
- Root cause: `pint_day(nday, nlayp)` where nlayp is produced in `_init` phase only.
  `_resolve_alloc_dim_var_refs` searches only current phase's `all_args` → nlayp not found
  → allocation silently dropped.
- Status: The `data_ops` fallback for this was ALREADY in the code at lines 1540-1548
  of suite_cap.py BEFORE our changes. But if we make pint_day run-local (Bug 1 fix),
  the pending-alloc for pint_day fires AFTER rrtmgp_pre_run and uses the data_ops
  fallback to find nlayp. This should fix Bug 2 as a side effect.

## The Fix Strategy

**Discriminator**: A SuiteOwned array is "run-local" (should be local allocatable in
run subroutine, NOT module-level) if any of its allocation dimensions is a SuiteOwned
scalar produced in the `_run` phase. Examples: `nday` (daytime_columns_dimension) is
produced by `rrtmgp_pre._run` → any array dimensioned by nday should be run-local.

```python
@staticmethod
def _is_run_local_var(entry, suite_model):
    for dim_std_name in entry.alloc_dim_std_names:
        dim_entry = suite_model.get(dim_std_name.lower())
        if (dim_entry is not None
                and dim_entry.producing_phase == "_run"
                and dim_entry.rank == 0):
            return True
    return False
```

## Changes Made So Far

### 1. `xdsl_ccpp/dialects/ccpp_utils.py`
- Added `is_run_local = opt_prop_def(BoolAttr)` property to `LazyAllocOp`
- Added `is_run_local: bool = False` parameter to `LazyAllocOp.__init__`
- When `is_run_local=True`, sets `props["is_run_local"] = BoolAttr.from_bool(True)`

### 2. `xdsl_ccpp/backend/print_ftn.py`
- Modified `CCPPLazyAllocOp` printer case
- When `is_run_local` is True: emits plain `allocate(t_day(nday, nlay))` (no lazy guard)
- When `is_run_local` is False: existing `if (.not. allocated(...)) then ... end if` behavior

### 3. `xdsl_ccpp/transforms/suite_cap.py` — multiple changes:

**a) `_PendingAlloc` dataclass** (line ~1166):
- Added `is_run_local: bool = False` field

**b) `_is_run_local_var` static method** (added before `_maybe_schedule_framework_var_alloc`):
- New helper implementing the discriminator logic above

**c) `_maybe_schedule_framework_var_alloc`**:
- Computes `_is_run_local = (suite_entry is not None and suite_model is not None
  and self._is_run_local_var(suite_entry, suite_model))`
- Passes `is_run_local=_is_run_local` to both `_PendingAlloc` and `LazyAllocOp`

**d) `_resolve_and_splice_pending_allocs`**:
- Passes `is_run_local=_pending.is_run_local` when creating `LazyAllocOp`

**e) `_build_module_vars`**:
- Now returns 3-tuple: `(allocatable_mod_vars, interstitial_var_names, run_local_entries)`
- Skips run-local vars (rank>0, non-DDT, `_is_run_local_var` returns True) from
  `ModuleVarOp` — they don't go into the module spec section
- Collects them in `run_local_entries` list

**f) `_inject_run_local_var_handling` (new static method)**:
- Iterates `generated_fns` looking for `_run` FuncOps
- For each run-local var, inserts:
  - `memref.AllocaOp(name_hint=entry.local_name + "__alloc")` at start of block
    (picked up by printer's `local_allocas` scan → generates local allocatable decl)
  - `SafeDeallocOp(entry.local_name)` before `ReturnOp` (end-of-run dealloc)

**g) Call site at line ~4363**:
- Updated to unpack 3-tuple from `_build_module_vars`
- Added call to `_inject_run_local_var_handling(generated_fns, run_local_entries)`

## Test Results So Far

- **Unit tests (598 tests)**: ALL PASS ✓
- **FileCheck tests**: ONE FAILURE — `advection-xml.mlir`

## The FileCheck Failure

The `advection-xml.mlir` FileCheck test now fails. The failure is at line 91 of the
test file, which expects `%1 = "llvm.mlir.addressof"() <{global_name = @const_initialized}>`.

The generated IR now has `%tcld = "ccpp_utils.host_var_ref"()` at position 73, before
the `@const_initialized` line the test expects at that position.

**`tcld` is a SuiteOwned SCALAR** (rank 0) in the advection example — it's NOT a
run-local array (since rank=0, the `_is_run_local_var` check in `_build_module_vars`
won't apply). The `tcld` scalar is still in `allocatable_mod_vars` and
`interstitial_var_names` as before.

However, looking at the generated IR output, `tcld` appears in `_finalize` with:
`%tcld = "ccpp_utils.host_var_ref"() <{var_name = "tcld", module_name = ""}>`.
This HostVarRefOp is in the FINALIZE subroutine at a position BEFORE the state-check.

**Why might this be different?** This needs investigation. The `tcld` HostVarRefOp
appearing in `_finalize` shouldn't be affected by our changes — we only changed
behavior for run-local ARRAYS (rank>0). Yet the IR ordering changed.

**Possible cause**: The `_inject_run_local_var_handling` inserts `memref.AllocaOp`
ops using `Rewriter.insert_op(..., InsertPoint.at_start(block))`. For suites that
have NO run-local vars (like the advection suite), `run_local_entries` is empty so
`_inject_run_local_var_handling` is a no-op. This should NOT affect advection.

**More likely cause**: The order of ops in `framework_ref_ops` changed subtly because
`_build_module_vars` now skips run-local entries. In the advection case, there are no
run-local entries, so `_build_module_vars` behavior is identical. This is puzzling.

**Next step**: Run the advection FileCheck test with verbose output to see exactly which
IR line is at position 73 vs 91, to understand what changed.

## What Still Needs To Be Done

1. **Investigate and fix the FileCheck failure** before checking the rrtmgp cap
2. **Regenerate rrtmgp cap** and verify the allocation structure is correct:
   - `t_day`, `pmid_day`, etc. NOT in module spec section
   - `real(kind=kind_phys), allocatable :: t_day(:,:)` in run subroutine spec
   - `allocate(t_day(nday, nlay))` AFTER rrtmgp_pre call (no lazy guard)
   - `allocate(pint_day(nday, nlayp))` AFTER rrtmgp_pre call
   - `if (allocated(t_day)) deallocate(t_day)` at end of run subroutine
3. **Run full FileCheck suite** after fixing the FileCheck failure
4. **Check in with user** before asking them to submit a build job

## Regenerating the rrtmgp Cap

The cap is generated by `cam_autogen.py` which calls `ccpp_dsl.py`. The command is:
```
$VENV_PYTHON -m xdsl_ccpp.tools.ccpp_dsl \
  --host-files <comma-joined host .meta files> \
  --scheme-files <comma-joined scheme .meta files> \
  --suites <comma-joined SDF .xml paths> \
  --host-name cam \
  -o <output_dir> \
  --tempdir <output_dir>/tmp \
  --emit-datatable <output_dir>/ccpp_datatable.xml \
  --emit-resolved-vars <output_dir>/resolved_vars.json \
  --legacy-mode \
  --cam-host \
  --framework-src-dir /glade/derecho/scratch/dennis/Claude.CAM-SIMA/CAM-SIMA.xdsl-ccpp/ccpp_framework/src \
  --kind-map r8:REAL64
```

The scheme/host file lists can be extracted from the `cam_build_cache.xml` in the
xdsl21 test case:
```
/glade/derecho/scratch/dennis/fphys_xdsl_test/SMS_Ln2.ne3pg3_ne3pg3_mg37.FPHYStest.derecho_gnu.cam-outfrq_rrtmgp_derecho.xdsl21/bld/atm/obj/cam_build_cache.xml
```

The previous successful cap generation was at:
```
/glade/derecho/scratch/dennis/tmp/.../scratchpad/rrtmgp_cap_verify_v3/
```

## Key Files

- Plan: `/glade/derecho/scratch/dennis/Claude.CAM-SIMA/xdsl-ccpp.cam-sima/xdsl_ccpp/transforms/FIX_PLAN_tday_pint_day.md`
- suite_cap.py: `/glade/derecho/scratch/dennis/Claude.CAM-SIMA/xdsl-ccpp.cam-sima/xdsl_ccpp/transforms/suite_cap.py`
- ccpp_utils.py: `/glade/derecho/scratch/dennis/Claude.CAM-SIMA/xdsl-ccpp.cam-sima/xdsl_ccpp/dialects/ccpp_utils.py`
- print_ftn.py: `/glade/derecho/scratch/dennis/Claude.CAM-SIMA/xdsl-ccpp.cam-sima/xdsl_ccpp/backend/print_ftn.py`
- capgen-v1 reference: `/glade/derecho/scratch/dennis/fphys_xdsl_test/SMS_Ln2.ne3pg3_ne3pg3_mg37.FPHYStest.derecho_gnu.cam-outfrq_rrtmgp_derecho.capgen-baseline/bld/atm/obj/ccpp/ccpp_rrtmgp_cap.F90`
  - t_day declared LOCAL at line 774-810
  - allocated at lines 827-870: `allocate(t_day(1:nday, 1:nlay))`
  - deallocated at lines 1436-1451: `if (allocated(t_day)) deallocate(t_day)`

## Git Status

Modified files (all intentional):
- `xdsl_ccpp/backend/print_ftn.py`
- `xdsl_ccpp/dialects/ccpp_utils.py`
- `xdsl_ccpp/transforms/suite_cap.py`
- `ccpp_cap_refactor_plan.md` (pre-existing modification, unrelated)

Untracked (created this session):
- `xdsl_ccpp/transforms/FIX_PLAN_tday_pint_day.md`
- `xdsl_ccpp/transforms/SESSION_STATUS.md` (this file)
