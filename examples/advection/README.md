# advection

A cloud advection example with five schemes, including one scheme (`apply_constituent_tendencies`) that appears twice in the suite to demonstrate repeated scheme calls.

## Schemes

| Scheme | Entry points | Description |
|--------|-------------|-------------|
| `const_indices` | `_run` | Sets constituent array indices |
| `cld_liq` | `_run`, `_init` | Liquid cloud scheme |
| `apply_constituent_tendencies` | `_run` | Applies constituent tendencies (called twice in the suite) |
| `cld_ice` | `_run`, `_init` | Ice cloud scheme |
| `cld_shadow` | `_run` | Ported from real capgen-v1 (GitHub issues #772/#774): its own local arg names (`cld_ice_array`, `ncols`) reuse names already used elsewhere in the group cap for unrelated standard_names, testing that the generated group cap renames each to avoid a module-scope collision |

Suite `cld_suite` runs all schemes in a single `physics` group, with `apply_constituent_tendencies` appearing after both `cld_liq` and `cld_ice`.

`dlc_liq.F90`/`.meta` and `cld_suite_error.xml` are a separate, deliberate negative-test fixture (also ported from real capgen-v1): `dlc_liq` declares a `ccpp_constituent_properties_t`-typed arg in its `_init` phase rather than `_register`, which must be rejected. Neither is part of the main `cld_suite` build above.

## Files

| File | Description |
|------|-------------|
| `cld_suite.xml` | Suite definition |
| `const_indices.meta` | Metadata for `const_indices` |
| `cld_liq.meta` | Metadata for `cld_liq` |
| `cld_ice.meta` | Metadata for `cld_ice` |
| `apply_constituent_tendencies.meta` | Metadata for `apply_constituent_tendencies` |
| `cld_shadow.meta` | Metadata for `cld_shadow` |
| `test_host_data.meta` | Host DDT metadata (`physics_state`) |
| `test_host.meta` | Host DDT metadata (`suite_info`) |
| `test_host_mod.meta` | Host module metadata |
| `dlc_liq.meta` | Metadata for the register-phase-violation negative test (not part of `cld_suite`) |
| `cld_suite_error.xml` | Suite definition for the negative test above |

## Running with ccpp_xdsl

```bash
ccpp_xdsl \
  --suites examples/advection/cld_suite.xml \
  --scheme-files examples/advection/const_indices.meta,examples/advection/cld_liq.meta,examples/advection/cld_ice.meta,examples/advection/apply_constituent_tendencies.meta,examples/advection/cld_shadow.meta \
  --host-files examples/advection/test_host_data.meta,examples/advection/test_host.meta,examples/advection/test_host_mod.meta \
  -o output/
```

## Generated output

| File | Description |
|------|-------------|
| `ccpp_kinds.F90` | Kind parameter definitions (`kind_phys` via ISO_FORTRAN_ENV) |
| `cld_suite_cap.F90` | Suite cap: `_initialize`, `_physics`, `_finalize` subroutines |
| `cld_ccpp_cap.F90` | Host-facing cap: `ccpp_physics_initialize`, `ccpp_physics_run`, etc. |
