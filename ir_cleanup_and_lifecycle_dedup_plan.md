# IR String Cleanup and Lifecycle Deduplication Plan

**Goal**: Eliminate raw Fortran string manipulation from all transforms. All
language-specific syntax belongs exclusively in the backend printers
(`print_ftn.py`, `print_cpp_header.py`). Transforms construct IR ops; printers
emit text.

---

## Current State

### The Anti-Pattern

Three ops carry pre-built Fortran text as `StringAttr` blobs:

| Op | Dirty fields | Generated-string lines | Source files |
|---|---|---|---|
| `ConstituentApiOp` | `body`, `type_defs` | ~970 lines, ~400 f-strings | `constituent_cap.py`, `ccpp_cap.py` |
| `SuiteVariablesOp` | `body` | ~55 lines, ~9 f-strings | `ccpp_cap.py` |
| `CHostCapOp` | `ftn_text`, `cpp_text`, `wrapper_text` | ~734 lines, ~132 f-strings | `cpp_interop.py` |

`ModuleVarOp.ftn_attrs` is a lesser offender: a `StringAttr` carrying Fortran
attribute strings like `"target"` or `"pointer"` — not a body blob, but still
language-specific text in the IR definition.

**Total: ~2150 lines of string-built Fortran/C++ across 3 transform files.**

### What Is Already Clean

`lifecycle_cap.py`, `suite_cap.py`, `run_dispatch.py`, `gpu_ccpp_cap_pass.py`,
`suite_meta.py` — all produce proper XDSL IR ops. No string bodies.

The clean model for statement-level ops: `LazyAllocOp` and `SafeDeallocOp` —
single-purpose, typed properties, printer handles all Fortran syntax. New ops
should follow this pattern exactly.

---

## The Conversion Pattern

Every string-generation site follows the same three-step conversion:

### Step 1 — Define the op in `ccpp_utils.py`

```python
@irdl_op_definition
class NullifyPointerOp(IRDLOperation):
    """Null-initialize a pointer variable."""
    name = "ccpp_utils.nullify_pointer"
    var_name = prop_def(StringAttr)

    def __init__(self, var_name: str):
        super().__init__(properties={"var_name": StringAttr(var_name)})
```

Use typed properties (`BoolAttr`, `IntegerAttr`, existing op references) rather
than `StringAttr` whenever the value has structure. A `StringAttr` is acceptable
only for names/labels, never for code fragments.

### Step 2 — Add a printer case in `print_ftn.py`

```python
case NullifyPointerOp():
    printer.print(f"nullify({op.var_name.data})\n")
```

This is the **only** place where Fortran syntax for this concept ever appears.

### Step 3 — Update the caller in the transform

```python
# Before (string):
da_lines.append(f"    nullify({lc_name})")

# After (IR op):
body_ops.append(NullifyPointerOp(lc_name))
```

**Verification after each converted site**: run the full test suite and the
CAM-SIMA zm regression test.

---

## PR Sequence

### PR 1 — Quick wins: lifecycle dedup + `ModuleVarOp.ftn_attrs` (~1 day)

**Lifecycle dedup (from `lifecycle_duplication_report.md`):**

- **Finding 1 (HIGH)**: Replace `_has_group_lifecycle("init")` / `_has_group_lifecycle("final")` etc. in `_generate_cam_lifecycle_wrappers` with lookups into the already-computed `lifecycle_fns` dict. Eliminates the parallel phase table that silently diverges when new lifecycle phases are added.

- **Finding 3 (LOW)**: Extract `_synthesize_host_scalar_arg(meta_data, all_args, std_name_const)` from the two near-identical functions in `suite_cap.py` (lines 408–488).

- **Finding 4 (LOW)**: Promote `_CCPP_DDT_MODS` to module level in `cap_shared.py` alongside `_CCPP_CONSTITUENT_MOD`.

- **Finding 5/6 (MINOR)**: Add assertion after `FRAMEWORK_STD_NAME_TO_CAP_VAR` absorption in `_CAM_STD_EXPRS`. Document the invariant.

**`ModuleVarOp.ftn_attrs` (Stage 1 of string cleanup):**

Replace the Fortran-string attribute with typed boolean properties:
```python
# Before:
ftn_attrs = opt_prop_def(StringAttr)  # "target", "pointer", etc.

# After:
is_pointer = opt_prop_def(BoolAttr)
is_target  = opt_prop_def(BoolAttr)
```

Update `print_ftn.py` to emit `pointer` / `target` / `allocatable` from these
booleans. Update the 9 call sites in `constituent_cap.py` that currently pass
`ftn_attrs="target"` or `ftn_attrs="pointer"`.

**Tests**: full CI suite + zm CAM-SIMA regression.

---

### PR 2 — `_generate_cam_lifecycle_wrappers` → IR FuncOps (~3–5 days)

This is the intersection of lifecycle dedup Finding 2 (Phase A + Phase B) and
the string cleanup for `ccpp_cap.py`. Both say the same thing from different
angles.

**Phase A — factor helpers** (prerequisite, low risk):

Extract these as module-level functions with documented signatures:
- `_build_dispatcher_call(suite_name, fn_name, arg_exprs) → list[Op]`
- `_group_dispatch_block(lifecycle_fns, phase, cam_std_exprs) → list[Op]`

These become the building blocks for Phase B.

**Phase B — IR rewrite**:

`_generate_cam_lifecycle_wrappers` currently returns
`ConstituentApiOp("\n".join(lines), public_names)` — a Fortran text blob stored
in an op designed for constituent registration.

Rewrite it to return a list of `func.FuncOp` IR objects, one per
`cam_ccpp_physics_*` wrapper subroutine. Each body uses:
- `HostVarRefOp` for `physics_types` / `physics_grid` module references
  (replacing direct `use physics_types, only: ...` string construction)
- `func.CallOp` to call the IR-generated `ccpp_*` dispatchers
- Existing IR ops for error propagation

`ConstituentApiOp` is no longer used for lifecycle wrappers. The
`_format_use_stmts` string helper is retired — USE statements fall out of
`HostVarRefOp` / `GlobalOp` stubs as they do everywhere else.

**New statement ops introduced here** (follow `LazyAllocOp` / `SafeDeallocOp`
pattern; each needs Step 1 + Step 2 + Step 3 above):
- `ErrorPropagateOp` — `if (errflg /= 0) return`
- `StringCompareOp` (if not already covered by existing IR)

**Tests**: full CI suite + zm + any lifecycle-exercising CAM-SIMA cases.

---

### PR 3 — `constituent_cap.py`: declarations → IR, body blocks → ops (~2–3 weeks)

`constituent_cap.py` has two parallel string-generation paths
(`_generate_constituent_api_cam_host` and `_generate_constituent_api`), each
producing ~9 subroutine bodies across ~970 f-string lines.

**Stage A — move `type_defs_lines` to `ModuleVarOp`**:

All 7 declaration types currently in `type_defs_lines` become `ModuleVarOp`
instances (using the `is_pointer`/`is_target` booleans from PR 1):

| Current string | Replacement op |
|---|---|
| `real(kind=kind_phys), allocatable, target :: lc_const_tend(:,:,:)` | `ModuleVarOp("lc_const_tend", "real", kind="kind_phys", is_target=True, rank=3)` |
| `real(kind=kind_phys), pointer :: lc_qtnd(:,:) => null()` | `ModuleVarOp(lc_name, "real", kind="kind_phys", is_pointer=True, rank=rank)` |
| `integer, allocatable :: lc_all_constituents(:)` | `ModuleVarOp("lc_all_constituents", "integer", rank=1)` |
| `character(len=N) :: cam_model_const_stdnames(N) = [...]` | `ModuleVarOp(..., kind=str(N), fixed_dim=n_fixed, init_value="...")` |

Delete `type_defs_lines`, `type_defs_text`, and the `type_defs=` argument to
`ConstituentApiOp`.

**Stage B — new statement ops for subroutine bodies**:

Define these ops (all follow the Step 1/2/3 pattern; all emit Fortran in the
printer only):

| Op | Semantics | Fortran emitted |
|---|---|---|
| `DeallocateIfOwnedOp(var)` | free if allocated | `if (allocated(x)) deallocate(x)` |
| `NullifyPointerOp(ptr)` | null a pointer | `nullify(x)` |
| `AllocateOp(var, shape_ops)` | allocate to shape | `allocate(x(n, m, k))` |
| `ZeroFillOp(var)` | fill with zero | `x = 0.0_kind_phys` |
| `PointerSliceAssignOp(ptr, array, index_var)` | slice pointer into 3D array | `ptr => arr(:, :, idx)` |
| `ConstituentIndexLookupOp(obj, std_name, idx_var, errflg)` | query index by standard name | `call obj%const_index(idx, 'std_name', & errcode=...)` |
| `ScopedBlockOp(locals, body: Region)` | introduce a local scope | `block; ...; end block` |

**Stage C — convert `ConstituentApiOp.body` from `StringAttr` to a `Region`**:

`ConstituentApiOp` gains a `body` Region containing one `ConstituentFunctionOp`
per subroutine. Each `ConstituentFunctionOp` has its own body Region of Stage B
ops. `print_ftn.py` walks the Region emitting `subroutine ... end subroutine`
for each child.

Do both parallel paths (`_generate_constituent_api_cam_host` and
`_generate_constituent_api`) together — they share the same op definitions.

**Tests after each Stage**: full CI suite + zm + kessler CAM-SIMA regressions.
Stage C in particular should be gated on Stage A and B passing cleanly first.

---

### PR 4 — `SuiteVariablesOp` and `ccpp_cap.py` remainder (~1–2 days)

`SuiteVariablesOp.body` carries ~55 lines for one subroutine
(`_render_suite_variables_subroutine`). Convert it to a Region using the ops
already defined in PR 2 and PR 3. This is the smallest of the string bodies
and is a natural cleanup once the larger ops exist.

**Tests**: full CI suite.

---

### PR 5 — `CHostCapOp` / `cpp_interop.py` (future; separate design)

`CHostCapOp` carries ~734 lines across three `StringAttr` fields (`ftn_text`,
`cpp_text`, `wrapper_text`). Converting it requires defining abstract ops that
both the Fortran and C++ printers can handle — a larger design discussion.
Deferred until PRs 1–4 establish the patterns. Tracked in a separate design
document when ready.

---

## Clean Examples to Follow

When implementing any new op, use these as templates:

**Single-statement op** (`ccpp_utils.py` lines ~700–740):
`LazyAllocOp`, `SafeDeallocOp` — typed properties, no Region, printer handles
all Fortran syntax.

**Region-body op** (`ccpp_utils.py` lines ~809–880):
`PromotionLoopOp`, `SubcycleLoopOp` — `body = region_def("single_block")`,
builder takes `body_ops` list, printer walks children.

**Conditional-body op** (`ccpp_utils.py` lines ~886–950):
`PresentCheckOp`, `ActiveCheckOp` — two named Regions (`with_body`,
`without_body`), printer emits `if (...) then ... else ... end if`.

---

## Testing Commands

After each PR, run both the unit test suite and a full CAM-SIMA regression.

**Unit + filecheck suite (xdsl_ccpp):**
```bash
cd /glade/derecho/scratch/dennis/Claude.CAM-SIMA/xdsl-ccpp.cam-sima
python -m pytest tests/ -x -q
```

**Full CAM-SIMA aux_sima regression:**
Use the `/cam-sima-regression` skill with a fresh test ID (e.g. xdsl04, xdsl05, ...).
The skill handles case creation, CCPP_GENERATOR wiring, submission, monitoring,
and results summary. Invoke it via:
```
/cam-sima-regression xdsl04
```
All aux_sima cases must show PASS. Any new FAIL relative to a known-good baseline
is a blocker for the PR.

---

## What This Plan Does NOT Cover

- `CHostCapOp` string bodies (PR 5 — deferred)
- `multilanguage_plan.md` BIND(C) interop phases — orthogonal effort
- Any new lifecycle phases or host-model features — this plan is cleanup only
