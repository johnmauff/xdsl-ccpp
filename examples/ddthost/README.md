# ddthost

A two-suite example demonstrating Fortran derived data types (DDTs) and optional entry points (`_timestep_init`, `_timestep_final`).

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
| `temp_calc_adjust` | `_register`, `_run`, `_init` | Calculates adjusted temperatures; `_register` produces `dim_inter` (`dimension_for_interstitial_variable`), consumed by `temp_adjust`'s `interstitial_var` |
| `temp_adjust` | `_run`, `_init`, `_finalize` | Applies temperature adjustment |

## Files

| File | Description |
|------|-------------|
| `ddt_suite.xml` | Suite definition for `ddt_suite` |
| `temp_suite.xml` | Suite definition for `temp_suite` |
| `make_ddt.meta` | Metadata for `make_ddt` + `vmr_type` DDT definition |
| `environ_conditions.meta` | Metadata for `environ_conditions` |
| `setup_coeffs.meta` | Metadata for `setup_coeffs` |
| `temp_set.meta` | Metadata for `temp_set` |
| `temp_calc_adjust.meta` | Metadata for `temp_calc_adjust` |
| `temp_adjust.meta` | Metadata for `temp_adjust` |
| `host_ccpp_ddt.meta` | Host DDT metadata (`ccpp_info_t`) |
| `test_host_data.meta` | Host DDT metadata (`physics_state`) |
| `test_host.meta` | Host DDT metadata (`suite_info`) |
| `test_host_mod.meta` | Host module metadata |
| `ddthost_py.py` | `ddt_suite` definition using the Python API |

## Running with ccpp_xdsl

### XML frontend

```bash
ccpp_xdsl \
  --suites examples/ddthost/ddt_suite.xml,examples/ddthost/temp_suite.xml \
  --scheme-files examples/ddthost/make_ddt.meta,examples/ddthost/environ_conditions.meta,examples/ddthost/setup_coeffs.meta,examples/ddthost/temp_set.meta,examples/ddthost/temp_calc_adjust.meta,examples/ddthost/temp_adjust.meta \
  --host-files examples/ddthost/test_host_data.meta,examples/ddthost/test_host_mod.meta,examples/ddthost/host_ccpp_ddt.meta,examples/ddthost/test_host.meta \
  -o output/
```

### Python frontend (ddt_suite only)

```bash
python3 examples/ddthost/ddthost_py.py | \
  python3 -m xdsl_ccpp.tools.ccpp_opt \
  -p generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap,generate-kinds,strip-ccpp \
  -t ftn
```

## Generated output

| File | Description |
|------|-------------|
| `ccpp_kinds.F90` | Kind parameter definitions (`kind_phys` via ISO_FORTRAN_ENV) |
| `ddt_suite_cap.F90` | Suite cap for `ddt_suite`: `_initialize`, `_data_prep`, `_finalize` |
| `temp_suite_cap.F90` | Suite cap for `temp_suite`: `_initialize`, `_physics1`, `_physics2`, `_finalize` |
| `ddt_ccpp_cap.F90` | Host-facing cap: `ccpp_physics_initialize`, `ccpp_physics_run`, etc. |

## Notable features

- **DDT arguments**: `make_ddt_run` takes a `vmr_type` argument. The `vmr_type` DDT is defined in `make_ddt.meta` (as a second `[ccpp-table-properties]` block) and passed via `additional` in the Python API.
- **Optional entry points**: `make_ddt` has `_timestep_final` but no `_finalize`; `setup_coeffs` has only `_timestep_init`. The pipeline silently skips absent entry points.
- **Multiple suites**: Both suite caps share a single `ddt_ccpp_cap` host-facing module.
