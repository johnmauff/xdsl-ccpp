# Multi-Instance Support Implementation Plan

## Background

capgen-ng supports up to 200 independent CCPP instances (ensemble members,
perturbation-parameter runs, thread-parallel physics) by passing a `ccpp_t`
Fortran derived type through every generated cap subroutine. The `ccpp_t`
carries a `ccpp_instance` integer that indexes into a 200-slot `initialized`
array, so each instance tracks its own initialization state independently.

xdsl-ccpp currently generates a scalar `initialized` flag and has no concept
of a `ccpp_t` variable.

## What capgen-ng generates (reference)

```fortran
! In the host cap module:
logical, dimension(200), save :: initialized = .false.

! Every group cap signature:
function ddt_suite_data_prep_run_cap(ccpp_data, ncol, ...) result(ierr)
   type(ccpp_t), intent(inout) :: ccpp_data
   ...
   if (.not.initialized(ccpp_data%ccpp_instance)) then
     errmsg = 'run called before init'; errflg = 1; return
   end if
```

The constant `CCPP_NUM_INSTANCES = 200` is defined in `scripts/common.py`.
The host model registers a `ccpp_t` variable in its own `.meta` file; the
standard-name matching machinery recognizes it by type and threads it through
automatically.

## Change inventory

### Trivial (< 1 hour total)

1. **`initialized` scalar → array** — in `suite_cap.py` (or wherever the guard
   is emitted), change:
   ```fortran
   logical, save :: initialized = .false.
   ```
   to:
   ```fortran
   logical, dimension(200), save :: initialized = .false.
   ```

2. **Guard indexing** — change `initialized` reads/writes to
   `initialized(ccpp_data%ccpp_instance)` once the variable is available.

3. **`ccpp_t` type definition** — emit a minimal `ccpp_t` type (or include
   the framework's `ccpp_types.F90`) in the generated kinds/types file.

### Medium (half a day)

4. **Host `.meta` recognition** — in `host_var_match_pass.py`, detect
   variables with `type = ccpp_t` and treat them as framework-managed
   (skip normal standard-name matching, similar to `CCPP_INTERNAL_STD_NAMES`).

5. **`ccpp_t` standard name** — decide on a standard name for the `ccpp_t`
   variable (capgen-ng uses something like `ccpp_state_ds`). Add it to
   `ccpp_conventions.py` as a framework-internal name.

### Hard (2–3 days)

6. **IR representation** — `ccpp_t` currently has no representation in the
   MLIR IR. Options:
   - Add a `ccpp.ccpp_t_arg` op or a flag on `ArgumentOp`
   - Or represent it as a special `ArgumentOp` with a reserved standard name
   The second option is less invasive.

7. **Thread through transform passes** — the variable must flow from the host
   `.meta` through:
   - `host_var_match_pass.py` — identify and tag the `ccpp_t` arg
   - `suite_cap.py` (`GenerateSuiteSubroutine`) — add it to every group cap
     signature and forward it to each scheme call
   - `ccpp_cap.py` (`GenerateCCPPCap`) — add it to the top-level
     `ccpp_physics_initialize`/`_run`/`_finalize` signatures
   - `print_ftn.py` — emit the `type(ccpp_t)` argument declaration

8. **Tests** — update existing filecheck tests that check cap signatures;
   add a new unit test for the multi-instance guard pattern.

## Suggested implementation order

1. Add `ccpp_t` type emission (trivial, no IR changes needed)
2. Add host-var-match recognition (medium, self-contained)
3. Add IR representation for the `ccpp_t` arg
4. Thread it through `suite_cap.py` and `ccpp_cap.py`
5. Update `print_ftn.py` to emit the declaration
6. Change scalar `initialized` → array + indexed guards
7. Update tests

## Open questions

- Should xdsl-ccpp define its own `ccpp_t` or depend on the framework's
  `ccpp_types.F90`? (capgen-ng ships the type in the framework source tree.)
- What standard name should the `ccpp_t` variable carry? Check capgen-ng's
  `src/ccpp_types.F90` and the host `.meta` files for the authoritative name.
- Is 200 the right cap, or should it be a CLI argument to `ccpp_xdsl`?

## Effort estimate

3–4 days total for a full implementation with tests.
