# threads

**Not a capgen-v1 port.** Unlike most examples in this repo, this one is
new test coverage, not restored from real capgen-v1's own
`end-to-end-tests/`. Confirmed during scoping (`task11-omp-thread` item 3):
real capgen-v1 declares `thread_number`/`number_of_threads` as unused
control-table boilerplate in several of its own end-to-end fixtures, but
none of them actually dimensions a container DDT by `number_of_threads` or
has a scheme reach into one — real capgen-v1's own coverage of this
mechanism lives entirely at the unit-test level
(`unit-tests/test_variable_resolver.py`/`test_suite_resolver.py`/
`test_control_validation.py`).

This example is modeled structurally on `examples/instances/` — the real
capgen-v1 analog for the symmetric `instance_number`/`number_of_instances`
pair — swapping `instance`/`ninstances` for `thread`/`nthreads`, with a
single scheme/group in place of `instances`' two-scheme subcycle (this
fixture's only job is exercising the `thread_number` substitution
mechanism itself; `examples/instances` already covers subcycle/optional-
arg/array-section interactions for the instance pair, and those aren't
specific to which pair is used).

## Mechanism under test

`data.meta` declares `thread_data`, a HOST-owned array of `thread_type`
DDT instances, dimensioned by `number_of_threads`. `thread_scheme_run`
declares an ordinary `thread_number`-standard-name scalar arg
(`thread`) and a plain `data_array` member of that DDT. The generated
suite cap resolves `data_array` to `thread_data(thread)%data_array` —
indexed by this call's own `thread` argument — via the same generic
`CCPP_SCALAR_INDEX_DIMS` table-driven mechanism `examples/instances` uses
for `instance_number`/`number_of_instances` (see `CHANGELOG.md`'s
`task11-omp-thread` resolution entry for the full mechanism design).

## Files

| File | Description |
|------|-------------|
| `test_host.meta` | Control table (`lb`/`ub`/`errmsg`/`errflg`) + host table declaring `thread`/`nthreads` |
| `data.meta`/`data.F90` | `thread_type` DDT + the `thread_data(1:nthreads)` host array |
| `thread_scheme.meta`/`.F90` | Scheme verifying it was called with the correct per-thread data |
| `suite_thread_suite.xml` | Suite definition, one group (`thread_group`), one scheme |
| `main.F90` | Driver looping `do thr = 1, nthreads` around every lifecycle phase |
