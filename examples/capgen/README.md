# capgen

A two-suite example combining DDT-based schemes with temperature physics schemes, exercising a wider range of entry point types.

## Schemes

**Suite `ddt_suite`** — group `data_prep`:

| Scheme | Entry points | Description |
|--------|-------------|-------------|
| `make_ddt` | `_run`, `_init`, `_timestep_final` | Constructs a `vmr_type` DDT from constituent arrays |
| `environ_conditions` | `_run`, `_init`, `_finalize` | Sets environmental conditions (ozone, HNO3, model times) |

**Suite `temp_suite`** — groups `physics1`, `physics2`:

| Scheme | Entry points | Description |
|--------|-------------|-------------|
| `setup_coeffs` | `_timestep_init` | Sets up temperature coefficients |
| `temp_set` | `_run` | Sets initial temperatures |
| `temp_calc_adjust` | `_run`, `_init` | Calculates adjusted temperatures |
| `temp_adjust` | `_run`, `_init`, `_finalize` | Applies temperature adjustment |

## Files

| File | Description |
|------|-------------|
| `scheme/ddt_suite.xml` | Suite definition for `ddt_suite` |
| `scheme/temp_suite.xml` | Suite definition for `temp_suite` |
| `scheme/make_ddt.meta` | Metadata for `make_ddt` + `vmr_type` DDT definition |
| `scheme/environ_conditions.meta` | Metadata for `environ_conditions` |
| `scheme/setup_coeffs.meta` | Metadata for `setup_coeffs` |
| `scheme/temp_set.meta` | Metadata for `temp_set` |
| `scheme/temp_calc_adjust.meta` | Metadata for `temp_calc_adjust` |
| `scheme/temp_adjust.meta` | Metadata for `temp_adjust` |
| `host_ftn/test_host_data.meta` | Host DDT metadata (`physics_state`) |
| `host_ftn/test_host.meta` | Host DDT/host metadata |
| `host_ftn/test_host_mod.meta` | Host module metadata |

## Running with ccpp_xdsl

```bash
ccpp_xdsl \
  --suites examples/capgen/scheme/ddt_suite.xml,examples/capgen/scheme/temp_suite.xml \
  --scheme-files examples/capgen/scheme/make_ddt.meta,examples/capgen/scheme/environ_conditions.meta,examples/capgen/scheme/setup_coeffs.meta,examples/capgen/scheme/temp_set.meta,examples/capgen/scheme/temp_calc_adjust.meta,examples/capgen/scheme/temp_adjust.meta \
  --host-files examples/capgen/host_ftn/test_host_data.meta,examples/capgen/host_ftn/test_host_mod.meta,examples/capgen/host_ftn/test_host.meta \
  -o output/
```

## Generated output

| File | Description |
|------|-------------|
| `ccpp_kinds.F90` | Kind parameter definitions (`kind_phys` via ISO_FORTRAN_ENV) |
| `ddt_suite_cap.F90` | Suite cap for `ddt_suite`: `_initialize`, `_data_prep`, `_finalize` |
| `temp_suite_cap.F90` | Suite cap for `temp_suite`: `_initialize`, `_physics1`, `_physics2`, `_finalize` |
| `ddt_ccpp_cap.F90` | Host-facing cap: `ccpp_physics_initialize`, `ccpp_physics_run`, etc. |
