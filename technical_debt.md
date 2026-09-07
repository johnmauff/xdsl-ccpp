# xdsl_ccpp Technical Debt

## TDB-002: Constituent API generation uses raw Fortran string assembly

**Files**: `xdsl_ccpp/transforms/constituent_cap.py`, `xdsl_ccpp/transforms/ccpp_cap.py` (`_generate_cam_lifecycle_wrappers`)  
**Added**: 2026-09-06

### What was done

All constituent API subroutines — both the generic path (`_generate_constituent_api`) and
the cam_host path (`_generate_constituent_api_cam_host`) — are built as raw Python f-strings
that are stored in a `ConstituentApiOp(body=StringAttr(...))` and emitted verbatim by
`print_ftn.py`. The same pattern is used by `_generate_cam_lifecycle_wrappers` for the
`cam_ccpp_physics_*` wrappers.

### Why this is a problem

The rest of xdsl_ccpp represents Fortran semantics using typed MLIR IR (`func.FuncOp`,
`call.CallOp`, SSA values, block arguments) and derives the Fortran text from that IR
in `print_ftn.py`. The raw-string shortcut bypasses this abstraction, meaning:

- No IR-level analysis or transformation can touch these subroutines.
- Line-length limits, continuation lines, USE deduplication, and indentation are all
  managed manually in Python rather than by the emitter.
- Extending the generated API (new arguments, new subroutines) requires editing
  raw f-string templates instead of composing IR ops.

### What the right fix looks like

1. Replace `ConstituentApiOp`'s `body` field (a `StringAttr`) with proper child regions
   containing `func.FuncOp` ops for each generated subroutine.
2. Represent each call (`cam_constituents_obj%initialize_table(...)`, `new_field`, etc.)
   as a `call.CallOp` or a new `ccpp_utils` dialect op, with typed SSA values for
   arguments and results.
3. Update `print_ftn.py` to walk those child ops and emit Fortran rather than
   printing a raw text blob.
4. Migrate `_generate_cam_lifecycle_wrappers` to the same IR-based approach.

This is a broad refactor touching `ccpp_utils.py` (new op definitions), `constituent_cap.py`,
`ccpp_cap.py`, and `print_ftn.py`, so it should be done as a dedicated task, not
incrementally mixed with feature work.

### Risk of leaving as-is

Low short-term. The raw strings produce correct Fortran and pass all tests. The cost
accumulates as the constituent API grows — each new subroutine or argument is more
raw-string bookkeeping.

---


## TDB-001: Constituent API always generated for CAM host builds

**File**: `xdsl_ccpp/transforms/ccpp_cap.py`, line ~1591  
**Added**: 2026-09-06

### What was done

`_generate_constituent_api` is called unconditionally whenever `cam_host=True`,
even for suites that have no CCPP constituents (no dynamic arrays, no fixed-advected
constituents, no scratch vars, no `number_of_ccpp_constituents` references).

### Why this is a hack

`write_init_files.py` (in CAM-SIMA's `src/data/`) unconditionally imports
`cam_constituents_array` and `cam_model_const_properties` from `cam_ccpp_cap` and
calls them in the body of `physics_read_data` and `physics_check_data` — regardless
of whether the suite has any CCPP constituents. This was written to match capgen's
behavior, which always generates those symbols.

Rather than restructure `write_init_files.py` to be constituent-aware (non-trivial
surgery), xdsl_ccpp was patched to always emit the constituent API for CAM builds,
producing empty stubs when the suite has no constituents.

### What the right fix looks like

`write_init_files.py` should become constituent-aware:

1. Gate the `cam_constituents_array` / `cam_model_const_properties` `USE` imports on
   whether the suite has CCPP constituents (i.e., `bool(constituent_set)` or
   `bool(registry_constituents)`).
2. Gate the `const_props => cam_model_const_properties()` and
   `field_data_ptr => cam_constituents_array()` call sites on the same condition.
3. Conditionally declare and initialize `const_props` and `field_data_ptr` locals.

This would let xdsl_ccpp revert the `cam_host` guard addition and keep
`_generate_constituent_api` conditional on actual constituent presence — cleaner
generated code and correct semantics.

### Risk of leaving as-is

Low. The generated empty constituent API stubs are harmless at runtime (empty
arrays, no-op register calls). The only cost is a small amount of dead code in
`cam_ccpp_cap.F90` for constituent-free suites.
