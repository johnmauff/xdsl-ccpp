# xdsl-ccpp

An implementation of the [CCPP](https://github.com/NCAR/ccpp-framework) (Common Community Physics Package) framework using [xDSL](https://github.com/xdslproject/xdsl), a Python-based MLIR framework. It reads CCPP suite XML and scheme metadata files and compiles them to Fortran cap subroutines.

## Installation

```bash
pip install .
```

This installs the `ccpp_xdsl` command-line driver and the `xdsl-ccpp` Python package. Requires Python 3.12+ and installs xDSL 0.56.1 as a dependency.

For development (linting, testing):

```bash
pip install -e ".[dev]"
```

For Fortran source cross-validation (`ccpp_validate`):

```bash
pip install -e ".[validate]"
```

## Hello World Example

The `examples/helloworld/` directory contains a complete example with two physics schemes (`hello_scheme` and `temp_adjust`) and a host model.

Run the full compilation flow with the driver script:

```bash
ccpp_xdsl \
  --suites examples/helloworld/hello_world_suite.xml \
  --scheme-files examples/helloworld/hello_scheme.meta,examples/helloworld/temp_adjust.meta \
  --host-files examples/helloworld/hello_world_mod.meta \
  -o output/
```

This generates three Fortran files in `output/`:

| File | Description |
|------|-------------|
| `ccpp_kinds.F90` | Kind parameter definitions (`kind_phys`, etc.) |
| `hello_world_suite_cap.F90` | Suite cap subroutines for `hello_world_suite` |
| `hello_world_ccpp_cap.F90` | Host-facing cap (`ccpp_physics_initialize`, `ccpp_physics_run`, etc.) |

### Driver Options

```
ccpp_xdsl --suites <xml,...> --scheme-files <meta,...> [options]

Required:
  --suites              Comma-separated suite XML files
  --scheme-files        Comma-separated scheme .meta files

Optional:
  --host-files          Comma-separated host model .meta files
  -o, --out             Output directory for .F90 files (default: .)
  --stdout              Print generated Fortran to stdout instead of files
  --host-name           Override the CamelCase host name prefix (e.g. HelloWorld);
                        derived from the suite name when not set
  -t, --tempdir         Temporary directory for intermediate files (default: tmp)
  -v, --verbose         Verbosity level: 0=quiet, 1=normal, 2=detailed (default: 1)
  --directive acc|omp   GPU directive style: acc for OpenACC, omp for OpenMP target
                        offload. When omitted, no GPU data movement directives are
                        generated regardless of memory_space attributes. A warning
                        is emitted if any memory_space attributes are found without
                        this flag set (suppress with --no-memory-space-warning).
  --no-memory-space-warning
                        Suppress the warning emitted when memory_space attributes
                        are present but --directive is not set.
  --emit-datatable      Write datatable.xml to this path after generating caps
  --emit-html           Write per-entry-point HTML variable tables to this directory
                        (requires --emit-datatable)
  --num-instances N     Maximum number of simultaneous CCPP instances (ensemble members).
                        When set, ccpp_suite_state is generated as a per-instance array
                        of length N instead of the default (200). Also settable per-pass
                        via ccpp_opt: -p "generate-suite-cap{num_instances=N}"
```

## Examples

The `examples/` directory contains several complete examples:

| Directory | Description |
|-----------|-------------|
| `helloworld/` | Two schemes (`hello_scheme`, `temp_adjust`) with XML and Python frontends |
| `capgen/` | Two suites (`temp_suite`, `ddt_suite`) with DDT host variables, optional arguments, and CMake build integration |
| `advection/` | Advection scheme example with XML frontend |
| `ddthost/` | Example using Fortran derived data types (DDTs) and optional entry points |
| `kessler/` | Kessler microphysics scheme with OpenACC GPU directives (`memory_space = device`) |
| `atmospheric_physics/` | Python suite definitions for 9 suites from [ESCOMP/atmospheric_physics](https://github.com/ESCOMP/atmospheric_physics) (adiabatic, held_suarez_1994, tj2016, cam7, kessler, musica, cam4, and two test suites) |

Each example can be driven via the XML frontend, the Python API (`@ccpp_suite`), or both.

### Running the Pipeline Manually

**Frontend only** (parse → MLIR IR):

```bash
python3 -m xdsl_ccpp.frontend.ccpp_xml \
  --suites examples/helloworld/hello_world_suite.xml \
  --scheme-files examples/helloworld/hello_scheme.meta,examples/helloworld/temp_adjust.meta
```

**Frontend → optimizer** (MLIR IR after all passes, before Fortran):

```bash
python3 -m xdsl_ccpp.frontend.ccpp_xml \
  --suites examples/helloworld/hello_world_suite.xml \
  --scheme-files examples/helloworld/hello_scheme.meta,examples/helloworld/temp_adjust.meta | \
  python3 -m xdsl_ccpp.tools.ccpp_opt \
  -p generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap,generate-kinds,strip-ccpp
```

**Full pipeline** (frontend → optimizer → Fortran):

```bash
python3 -m xdsl_ccpp.frontend.ccpp_xml \
  --suites examples/helloworld/hello_world_suite.xml \
  --scheme-files examples/helloworld/hello_scheme.meta,examples/helloworld/temp_adjust.meta | \
  python3 -m xdsl_ccpp.tools.ccpp_opt \
  -p generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap,generate-kinds,strip-ccpp \
  -t ftn
```

**Python API frontend** (using `@ccpp_suite`):

```bash
python3 examples/helloworld/helloworld_py.py | \
  python3 -m xdsl_ccpp.tools.ccpp_opt \
  -p generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap,generate-kinds,strip-ccpp \
  -t ftn
```

## Python API

xdsl-ccpp provides a Python frontend (`xdsl_ccpp.frontend.py_api`) for defining suites programmatically. It replaces the suite XML file and, optionally, duplicating `.meta` argument lists in Python code.

### Two Modes

**Inline** — define scheme arguments directly in Python (useful when no `.meta` file exists yet):

```python
from xdsl_ccpp.frontend.py_api import Arg, ccpp_scheme, ccpp_suite, emit_ir

@ccpp_scheme
class my_scheme:
    run = [Arg("ncol", standard_name="horizontal_loop_extent",
               type="integer", units="count", intent="in"), ...]

@ccpp_suite("my_suite", version="1.0")
class my_suite:
    physics = [my_scheme]

if __name__ == "__main__":
    emit_ir(my_suite)
```

**From `.meta` files** — load existing `.meta` files and write only the suite orchestration in Python. This is the preferred approach when `.meta` files already exist, as it keeps them as the single source of truth:

```python
from xdsl_ccpp.frontend.py_api import ccpp_scheme_from_meta, ccpp_suite, emit_ir

kessler        = ccpp_scheme_from_meta("examples/kessler/kessler.meta")
kessler_update = ccpp_scheme_from_meta("examples/kessler/kessler_update.meta")

@ccpp_suite("kessler_suite", version="1.0")
class kessler_suite:
    physics = [kessler, kessler_update]

if __name__ == "__main__":
    emit_ir(kessler_suite)
```

Three loader functions cover the three metadata block types:

| Function | Loads | Returns |
|----------|-------|---------|
| `ccpp_scheme_from_meta(file)` | First `type=scheme` block | `SchemeDescriptor` |
| `ccpp_scheme_from_meta(file, name="foo")` | Named scheme block (for files with multiple schemes) | `SchemeDescriptor` |
| `ccpp_host_from_meta(file)` | All host/module blocks | `list[TableDescriptor]` |
| `ccpp_ddt_from_meta(file)` | First `type=ddt` block | `TableDescriptor` |

### Subcycles with `forLoop`

Use `forLoop` when the loop count is a CCPP standard name resolved at runtime by the host model (matching `<subcycle loop="name">` in the suite XML):

```python
from xdsl_ccpp.frontend.py_api import forLoop, ccpp_scheme_from_meta, ccpp_suite, emit_ir

@ccpp_suite("rrtmgp", version="1.0")
class rrtmgp:
    physics_after_coupler = [
        rrtmgp_pre,
        forLoop("number_of_diagnostic_subcycles", [
            rrtmgp_constituents,
            rrtmgp_sw_gas_optics,
            rrtmgp_sw_rte,
        ]),
        rrtmgp_post,
    ]
```

For a fixed integer count known at IR-generation time, a plain Python `for` loop inside `def run():` is simpler:

```python
repeats = ccpp_param("repeats", default=3)  # overridable: python3 suite.py repeats=5

@ccpp_suite("my_suite", version="1.0")
class my_suite:
    physics = [scheme_a, scheme_b]
    def run():
        for i in range(repeats):
            scheme_a()
        scheme_b()
```

Passing a CCPP standard name string to `range()` raises a clear error directing you to `forLoop` instead.

### Compile-Time Parameters

`ccpp_param(name, default)` reads a `name=value` token from the command line at IR-generation time, falling back to `default`:

```python
top = ccpp_param("top", default=19)   # override: python3 suite.py top=53
```

### Multiple Suites

Pass a list to `emit_ir` to include multiple suites in one IR output, matching `ccpp_xdsl --suites a.xml,b.xml`:

```python
emit_ir([ddt_suite, temp_suite], additional=[vmr_type, *host])
```

## GPU Support

xdsl-ccpp can generate OpenACC or OpenMP target-offload data directives around scheme physics calls. The directives are driven entirely by metadata — no changes to the scheme Fortran sources are required.

### Marking Arguments as Device-Resident

In a scheme `.meta` file, add `memory_space = device` to any argument that lives in GPU memory at the point of the physics call:

```ini
[ qv ]
  standard_name = water_vapor_mixing_ratio_wrt_moist_air_and_condensed_water
  units = kg kg-1
  type = real
  kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  intent = inout
  memory_space = device
```

Arguments without `memory_space = device` default to `memory_space = host` and are unaffected.

### OpenACC Clause Selection

The clause used for each device-resident argument is chosen from its `intent`:

| Intent | Clause | Effect |
|--------|--------|--------|
| `in` | `copyin()` | Copy host → device before the call; no copy back |
| `inout` | `copy()` | Copy host → device before the call, device → host after |
| `out` | `copyout()` | No copy in; copy device → host after the call |

When the same argument appears in multiple scheme entry points within a suite with different intents, the most permissive intent is used — for example, if an argument is `intent(inout)` in `kessler_run` and `intent(in)` in `kessler_update_run`, it is placed in `copy()`.

If the host model also declares the variable as device-resident (`model_var_memory_space = device` in the host `.meta` file), the variable goes into `present()` instead — no data transfer is needed because the host already manages the device copy across timesteps.

### Memory-Space Mismatch Warning

When `memory_space` attributes are present in scheme or host `.meta` files but `--directive` is not set, `ccpp_xdsl` emits a warning to stderr listing the affected variables:

```
Warning: memory_space attributes are set but --directive is not; GPU data movement directives will not be generated.
  Scheme variables with memory_space: theta (device), qv (device), ...
  Pass --directive acc or --directive omp to generate GPU data movement directives.
```

To suppress this warning (e.g. when intentionally omitting GPU directives for a CPU-only build):

```bash
ccpp_xdsl --no-memory-space-warning ...
```

### Generating a Cap with GPU Directives

Pass `--directive acc` or `--directive omp`:

```bash
ccpp_xdsl \
  --suites      examples/kessler/kessler_suite.xml \
  --scheme-files examples/kessler/kessler.meta,examples/kessler/kessler_update.meta \
  --host-files  examples/kessler/kessler_host_mod.meta,examples/kessler/kessler_host_sub.meta \
  --directive   acc \
  -o            output/
```

### Example Output

For the kessler example, the generated `Kessler_ccpp_physics_run` looks like:

```fortran
if (trim(suite_name) .eq. 'kessler_suite') then
  if (trim(suite_part) .eq. 'physics') then
    !$acc data copy(theta(col_start:col_end, 1:nz), qv(col_start:col_end, 1:nz), &
    !$acc      qc(col_start:col_end, 1:nz), qr(col_start:col_end, 1:nz), &
    !$acc      temp_prev(col_start:col_end, 1:nz), ttend_t(col_start:col_end, 1:nz)) &
    !$acc      copyin(cpair(col_start:col_end, 1:nz), rair(col_start:col_end, 1:nz), &
    !$acc      rho(col_start:col_end, 1:nz), z(col_start:col_end, 1:nz), &
    !$acc      exner(col_start:col_end, 1:nz)) copyout(precl, relhum(col_start:col_end, 1:nz))
    call kessler_suite_suite_physics(...)
    !$acc end data
  end if
end if
```

The `!$acc data` region opens only after the suite-part comparison is already known to be true, so no data movement occurs for unmatched suite parts. Array arguments use column-sliced sections (`col_start:col_end, 1:nz`) rather than the full host array, matching the active physics columns.

### OpenMP Target Offload

Pass `--directive omp` to emit OpenMP target data directives instead:

```fortran
!$omp target data map(tofrom: theta(...), qv(...), ...) map(to: cpair(...), ...) map(from: precl, ...)
call kessler_suite_suite_physics(...)
!$omp end target data
```

The intent-based clause mapping is the same: `inout` → `map(tofrom:)`, `in` → `map(to:)`, `out` → `map(from:)`, already-device → `map(alloc:)`.

## Metadata Skeleton Generation

`ccpp_generate_meta` generates a `.meta` skeleton file from a Fortran source file. It extracts argument names, types, kinds, intents, array rank, and optional flags from subroutine signatures and fills in stub values for fields that cannot be inferred from source (`standard_name`, `units`, dimension standard names). The stubs must be replaced by the developer before the `.meta` file is used with `ccpp_xdsl`.

This matches the functionality of `ccpp_fortran_to_metadata.py` from capgen-ng.

```bash
ccpp_generate_meta scheme.F90
```

Only subroutines following the CCPP entry-point naming convention are included (`_run`, `_init`, `_finalize`, `_final`, `_timestep_init`, `_timestep_final`). Other subroutines in the module are silently skipped.

Example output for a scheme with a `_run` entry point:

```ini
[ccpp-table-properties]
  name = temp_adjust
  type = scheme

[ccpp-arg-table]
  name = temp_adjust_run
  type = scheme
[ ncol ]
  standard_name = std_name_001
  units = enter_units
  type = integer
  dimensions = ()
  intent = in
[ temp ]
  standard_name = std_name_002
  units = enter_units
  type = real
  kind = kind_phys
  dimensions = (dim1)
  intent = inout
```

The developer then replaces each `std_name_NNN` with the correct CCPP standard name, `enter_units` with the physical units, and `dim1`/`dim2` with the appropriate CCPP dimension standard names (e.g. `horizontal_loop_extent`, `vertical_layer_dimension`).

### ccpp_generate_meta Options

```
Required:
  FILE.F90 [...]          One or more Fortran source files to process

Optional:
  --output-dir DIR        Write .meta files here (default: same directory as each .F90)
  --stdout                Print all output to stdout instead of writing files
  -v, --verbose           Print the output path for each generated file
```

Requires fparser: `pip install fparser` (or `pip install -e ".[validate]"`).

## Fortran Source Cross-Validation

`ccpp_validate` checks each scheme's `.meta` file against its `.F90` source, flagging mismatches in argument existence, type, rank, intent, and optional status.

```bash
ccpp_validate examples/capgen/*.F90
```

The tool auto-detects the best available Fortran parsing backend:

| Backend | Install | Notes |
|---------|---------|-------|
| `fparser2` | `pip install fparser` | Pure Python, no external tools required |
| `flang` | `brew install llvm` or `conda install -c conda-forge flang` | Production Fortran compiler, more robust |

Pass `--host-files` to enable dimension name validation against the host model registry:

```bash
ccpp_validate --host-files examples/capgen/test_host.meta,examples/capgen/test_host_mod.meta \
  examples/capgen/*.F90
```

Use `--backend flang` or `--backend fparser2` to select explicitly. Run with `-v` to see which backend was chosen and which files were skipped.

## Variable Tracking

`ccpp_track_variables` traces a CCPP standard-name variable through a suite's call tree and reports which scheme entry points use it, with intent, units, and whether a unit conversion will be applied.

```bash
ccpp_track_variables \
  --suites      examples/advection/cld_suite.xml \
  --scheme-files examples/advection/const_indices.meta,\
examples/advection/cld_liq.meta,\
examples/advection/apply_constituent_tendencies.meta,\
examples/advection/cld_ice.meta \
  --host-files  examples/advection/test_host_data.meta \
  --variable    surface_air_pressure
```

Example output:

```
Suite: cld_suite
Variable: surface_air_pressure

  Group: physics
    cld_liq_run  local=ps  intent=in  units=hpa  host=pa  [unit-converted]
    cld_ice_run  local=ps  intent=in  units=pa   host=pa
```

The `[unit-converted]` flag means the suite cap will allocate a local copy and convert units before calling the scheme.

Options:

| Option | Description |
|--------|-------------|
| `--suites` | Comma-separated suite XML files (required) |
| `--scheme-files` | Comma-separated scheme `.meta` files (required) |
| `--host-files` | Comma-separated host `.meta` files (optional; needed for unit mismatch detection) |
| `--variable` | Standard name to trace, case-insensitive (required) |
| `--suite` | Restrict output to a single named suite |
| `--entry-points` | Comma-separated entry-point suffixes to check (default: `run`; also accepts `init`, `finalize`) |

Exit code is 0 when the variable is found in at least one scheme, 1 otherwise. Partial matches (standard names that contain the query as a substring) are listed as suggestions when no exact match is found.

## CMake Integration

xdsl-ccpp provides a CMake module (`cmake/xdsl_ccpp.cmake`) that runs `ccpp_xdsl`
at configure time and returns the list of generated `.F90` cap files for use in
`add_library` or `add_executable` targets. This mirrors the approach used by
`ccpp_capgen-ng`.

### Requirements

- CMake 3.20 or later
- `ccpp_xdsl` on `PATH` (installed via `pip install -e .`)

### Quick Start

```cmake
cmake_minimum_required(VERSION 3.20)
project(my_host Fortran)

include(path/to/cmake/xdsl_ccpp.cmake)

xdsl_ccpp_generate(
    HOST_NAME   "MyHost"
    OUTPUT_ROOT "${CMAKE_CURRENT_BINARY_DIR}/ccpp_caps"
    TARGET_VAR  MY_CAPS
    SUITES
        "${CMAKE_CURRENT_SOURCE_DIR}/my_suite.xml"
    SCHEMEFILES
        "${CMAKE_CURRENT_SOURCE_DIR}/scheme_a.meta"
        "${CMAKE_CURRENT_SOURCE_DIR}/scheme_b.meta"
    HOSTFILES
        "${CMAKE_CURRENT_SOURCE_DIR}/host_data.meta"
)

add_executable(my_host ${MY_SRCS} ${MY_CAPS})
target_include_directories(my_host PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/ccpp_caps")
```

After `xdsl_ccpp_generate()` returns, `MY_CAPS` contains the absolute paths of
every `.F90` file written to `OUTPUT_ROOT`.

### Function Reference

```
xdsl_ccpp_generate(
    HOST_NAME   <name>            # CamelCase host name prefix (required)
    OUTPUT_ROOT <dir>             # Directory to write generated .F90 files (required)
    TARGET_VAR  <variable>        # CMake variable to populate with output paths (required)
    SUITES      <file> [<file>…]  # Suite XML files (required)
    SCHEMEFILES <file> [<file>…]  # Scheme .meta files (required)
    [HOSTFILES  <file> [<file>…]] # Host model .meta files (optional)
)
```

| Argument | Required | Description |
|----------|----------|-------------|
| `HOST_NAME` | yes | CamelCase prefix for generated subroutine names (e.g. `TestHost`) |
| `OUTPUT_ROOT` | yes | Directory where `.F90` files are written; created if it does not exist |
| `TARGET_VAR` | yes | CMake variable that receives the list of generated `.F90` paths |
| `SUITES` | yes | One or more suite XML files (space-separated in CMake list syntax) |
| `SCHEMEFILES` | yes | One or more scheme `.meta` files |
| `HOSTFILES` | no | Host model `.meta` files; required for unit conversion and host variable matching |

### How It Works

The function runs `ccpp_xdsl` via `execute_process()` at CMake configure time,
the same approach used by `ccpp_capgen-ng`. This means:

- Cap files are available immediately for `add_library` / `add_executable`
- Re-running `cmake` (or deleting the build directory) regenerates the caps
- Incremental rebuilds will not automatically re-run cap generation when only
  `.meta` or `.xml` files change — re-run `cmake` after editing those inputs

### Working Example

A complete working example is in `examples/capgen/CMakeLists.txt`:

```bash
cmake -S examples/capgen -B examples/capgen/build
cmake --build examples/capgen/build
ctest --test-dir examples/capgen/build
```

This configures the capgen example, generates all CCPP cap files into
`examples/capgen/build/caps/`, compiles them alongside the pre-existing Fortran
scheme sources, and runs the integration test.

## Documentation Generation

`ccpp_datatable` produces a machine-readable `datatable.xml` and optionally a set of human-readable HTML variable tables from a completed CCPP cap generation run. It serves two distinct purposes:

1. **CMake file discovery** — the `<ccpp_files>` section lists every `.F90` cap file written, giving the CMake module a precise source list without relying on a glob.
2. **Variable documentation** — the `<var_dictionaries>` section records full variable metadata (standard name, units, dimensions, type, intent) for every scheme entry point and host argument table, suitable for browsing as HTML.

The tool can be run standalone (after `ccpp_xdsl` with `--debug`) or integrated directly into the `ccpp_xdsl` pipeline.

### Integrated with ccpp_xdsl (recommended)

Pass `--emit-datatable` to generate the datatable as part of a normal cap generation run. The MLIR intermediate is read before the temp directory is cleaned up, so no `--debug` flag is required:

```bash
ccpp_xdsl \
  --suites       examples/capgen/ddt_suite.xml,examples/capgen/temp_suite.xml \
  --scheme-files examples/capgen/make_ddt.meta,examples/capgen/temp_set.meta \
  --host-files   examples/capgen/test_host.meta \
  --host-name    test_host \
  -o             caps/ \
  --emit-datatable caps/datatable.xml \
  --emit-html    caps/docs/
```

### Standalone Usage

Run `ccpp_datatable` separately against an existing caps directory. The MLIR intermediate file is normally removed after `ccpp_xdsl` finishes; pass `--debug` to keep it:

```bash
# Step 1: generate caps and keep the MLIR intermediate
ccpp_xdsl \
  --suites       examples/capgen/ddt_suite.xml \
  --scheme-files examples/capgen/make_ddt.meta \
  --host-name    test_host \
  -o             caps/ \
  --debug

# Step 2: generate datatable from the retained MLIR
ccpp_datatable \
  --mlir      tmp/ccpp.mlir \
  --caps-dir  caps/ \
  -o          caps/datatable.xml \
  --html-dir  caps/docs/ \
  --host-name test_host
```

### ccpp_datatable Options

```
Required:
  --mlir FILE         Frontend MLIR file (ccpp.mlir in the --tempdir from ccpp_xdsl)
  --caps-dir DIR      Directory containing the generated .F90 cap files

Optional:
  -o, --output FILE   Output path for datatable.xml (default: datatable.xml)
  --html-dir DIR      Write one HTML variable table per entry point to this directory
  --host-name NAME    Host model name written into the <datatable> root element
```

### datatable.xml Structure

The output file has four top-level sections:

| Section | Contents |
|---------|----------|
| `<ccpp_files>` | Absolute paths to every generated `.F90` cap file |
| `<schemes>` | Each scheme with its lifecycle entry points (`init`, `run`, `finalize`, etc.) |
| `<api>` | Suite → group → scheme call structure, matching the suite XML |
| `<var_dictionaries>` | Full variable metadata per argument-table entry point (one `<var_dictionary>` per scheme entry point and host table) |

```xml
<?xml version="1.0" encoding="UTF-8"?>
<datatable host_name="test_host">
  <ccpp_files>
    <file path="caps/ccpp_kinds.F90"/>
    <file path="caps/ddt_suite_cap.F90"/>
    <file path="caps/test_host_ccpp_cap.F90"/>
  </ccpp_files>
  <schemes>
    <scheme name="make_ddt">
      <entry_point name="make_ddt_init" phase="init"/>
      <entry_point name="make_ddt_run" phase="run"/>
    </scheme>
  </schemes>
  <api>
    <suite name="ddt_suite" version="1.0">
      <group name="data_prep">
        <scheme name="make_ddt"/>
      </group>
    </suite>
  </api>
  <var_dictionaries>
    <var_dictionary source="make_ddt_run" table_type="scheme">
      <variable local_name="O3" standard_name="ozone" long_name="Ozone mixing ratio"
                units="ppmv" type="real" dimensions="(horizontal_loop_extent)"
                kind="kind_phys" intent="in"/>
    </var_dictionary>
  </var_dictionaries>
</datatable>
```

### HTML Variable Tables

When `--html-dir` is provided, one self-contained HTML file is written per argument-table entry point. The filename matches the entry-point name (e.g. `make_ddt_run.html`, `temp_adjust_init.html`). Each page renders an 8-column table:

| Column | Description |
|--------|-------------|
| Local name | Fortran variable name used inside the scheme |
| Standard name | CCPP standard name (globally unique identifier) |
| Long name | Human-readable description |
| Units | Physical units string |
| Type | Fortran base type (`real`, `integer`, etc.) |
| Dimensions | Dimension list, e.g. `(horizontal_loop_extent, vertical_layer_dimension)` |
| Kind | Fortran kind parameter (e.g. `kind_phys`) |
| Intent | `in`, `out`, or `inout` |

### CMake Integration with Datatable

Pass `EMIT_DATATABLE` to `xdsl_ccpp_generate()` to enable precise file discovery. When the datatable exists, the CMake module reads the `<ccpp_files>` section instead of globbing — ensuring `TARGET_VAR` contains exactly the files that were generated, with no risk of picking up stale outputs:

```cmake
xdsl_ccpp_generate(
    HOST_NAME      "MyHost"
    OUTPUT_ROOT    "${CMAKE_CURRENT_BINARY_DIR}/caps"
    TARGET_VAR     MY_CAPS
    SUITES         "${CMAKE_CURRENT_SOURCE_DIR}/suite.xml"
    SCHEMEFILES    "${CMAKE_CURRENT_SOURCE_DIR}/scheme.meta"
    EMIT_DATATABLE "${CMAKE_CURRENT_BINARY_DIR}/caps/datatable.xml"
)
```

See [CMake Integration](#cmake-integration) for the full `xdsl_ccpp_generate()` function reference.

## Testing

Tests use [pytest](https://pytest.org) with [LLVM-style FileCheck](https://llvm.org/docs/CommandGuide/FileCheck.html) via the Python `filecheck` package.

Install test dependencies:

```bash
pip install -e ".[dev]"
```

Run all tests:

```bash
pytest tests/
```

Run a specific test file:

```bash
pytest tests/filecheck/examples/end_to_end/helloworld-xml.mlir
```

### Test Structure

FileCheck tests live under `tests/filecheck/examples/` in three subdirectories:

```
tests/filecheck/examples/
├── end_to_end/    ← full pipeline: frontend + optimizer + Fortran backend
├── frontend/      ← frontend only: raw MLIR IR emitted by the parser
└── completed_ir/  ← frontend + optimizer passes, before Fortran backend
```

Each `.mlir` file contains a `// RUN:` directive specifying the command to execute, followed by `// CHECK:` / `// CHECK-NEXT:` / `// CHECK-LABEL:` directives that the output must match. The `conftest.py` in `tests/` discovers and runs all `.mlir` files automatically.

### Updating Tests

If the compiler output changes, regenerate the CHECK directives for a test file using:

```bash
python3 tests/filecheck/examples/update-filecheck-test.py \
  tests/filecheck/examples/end_to_end/helloworld-xml.mlir
```

This runs the pipeline from the file's `// RUN:` line, converts the output to CHECK directives, and rewrites the file in place.

### Linting

```bash
ruff check xdsl_ccpp/
ruff format xdsl_ccpp/
```

## Code Organization

The transformation pipeline lives entirely under `xdsl_ccpp/transforms/`:

| Module | Pass name | Role |
|--------|-----------|------|
| `ccpp_cap.py` | `generate-ccpp-cap` | Emits the host-facing cap (`ccpp_physics_initialize`, `ccpp_physics_run`, etc.) |
| `suite_cap.py` | `generate-suite-cap` | Emits per-suite subroutines (`*_suite_physics`, lifecycle init/finalize) |
| `host_var_match_pass.py` | `generate-host-match` | Annotates scheme arg ops with matching host variable names, kinds, and units |
| `gpu_ccpp_cap_pass.py` | `generate-gpu-ccpp-cap` | Inserts OpenACC/OpenMP data directives at the ccpp_cap level |
| `gpu_data_pass.py` | `generate-gpu-data` | Inserts OpenACC/OpenMP directives at the suite_cap level for unmatched device variables |

Shared utilities used by multiple passes live in `xdsl_ccpp/transforms/util/`:

| Module | Contents |
|--------|----------|
| `ir_utils.py` | `find_ccpp_module(ops)` — locates the named `@ccpp` ModuleOp from an op list |
| `ccpp_descriptors.py` | `BuildMetaDataDescriptions` — walks CCPP metadata tables into Python descriptor objects |

When writing a new pass that needs the CCPP metadata module, import `find_ccpp_module` from `xdsl_ccpp.transforms.util.ir_utils` rather than re-implementing the search.

### ModuleVarOp type representation

`ModuleVarOp` (in `xdsl_ccpp/dialects/ccpp_utils.py`) represents a module-level variable declaration. Its type is stored as four structured attributes rather than a pre-rendered Fortran string:

| Attribute | Type | Example |
|-----------|------|---------|
| `base_type` | required | `"real"`, `"integer"`, `"character"`, `"logical"`, `"type"` |
| `kind` | optional | `"kind_phys"`, `"kind_dyn"`, `"512"` (char length) |
| `ddt_name` | optional | `"vmr_type"` (when `base_type == "type"`) |
| `ftn_attrs` | optional | `"target"`, `"pointer"` |

The Fortran printer reconstructs the declaration string from these fields. Other language backends (e.g. a C++ header printer) can interpret the type without parsing Fortran syntax.

---

## CCPP Tool Comparison

### Tool Overview

| Tool | Status | Metadata format | Primary purpose |
|---|---|---|---|
| `ccpp_prebuild` | Production, legacy | Old embedded-comment format | Cap generation + build integration |
| `ccpp_capgen` | Production, current | New `.meta` file format | Cap generation + Fortran validation |
| `ccpp_capgen-ng` | In development | New `.meta` file format | Unified successor to both above |
| `xdsl-ccpp` | Prototype | New `.meta` file format | MLIR-based cap generation + GPU |

### Capability Comparison

| Capability | ccpp_prebuild | ccpp_capgen | ccpp_capgen-ng | xdsl-ccpp |
|---|---|---|---|---|
| **Core cap generation** | | | | |
| Basic cap generation | ✅ | ✅ | ✅ | ✅ |
| DDT host model support | ✅ | ✅ | ✅ | ✅ |
| Nested suites | ❌ | ✅ | ✅ | ✅ |
| Python API for suite definition | ❌ | ❌ | ❌ | ✅ |
| Subcycle support (`loop="N"` in SDF) | ✅ | ❌ | ✅ | ✅ |
| **Metadata format** | | | | |
| Old embedded-comment format | ✅ | ❌ | ❌ | ❌ |
| New `.meta` file format | ❌ | ✅ | ✅ | ✅ |
| **Variable handling** | | | | |
| Host variable matching | ✅ | ✅ | ✅ | ✅ |
| Variable compatibility validation | ✅ | ✅ | ✅ | ✅ |
| Unit/kind conversion | ✅ | ✅ | ✅ | ✅∥ |
| Optional argument handling | ✅ | Partial | ✅ | ✅ |
| Chunked data layout | ✅ | ❌ | ✅ | ✅ |
| Constituent registration | ✅ | ✅ | ✅ | ✅ |
| `ccpp_physics_suite_variables` | ✅ | ✅ | ✅ | ✅ |
| **Code correctness** | | | | |
| Fortran source cross-validation | ❌ | ✅ | ✅ | ✅¶ |
| Multi-instance support | ❌ | ❌ | ✅ | ✅ |
| **Build & tooling** | | | | |
| Build system integration (CMake) | ✅ | ✅ | ✅ | ✅ |
| Documentation generation | ✅ HTML/LaTeX | ✅ datatable.xml | ✅ | ✅ |
| `ccpp_track_variables` utility | ✅ | ❌ | ✅ | ✅ |
| Metadata from Fortran source | ❌ | ❌ | ✅ | ✅ |
| **Testing** | | | | |
| Compiled Fortran execution tests | ✅ | ✅ | ✅ | ✅§ |
| Unit test depth | Moderate | Moderate | 1300+ tests | 210 pytest + 3 Makefiles |
| **Host model integration** | | | | |
| CCPP-SCM | ✅ | ✅ | ✅ | ❌ |
| CAM-SIMA / UFS | ✅ | ✅ | In progress | ❌ |
| **GPU support** | | | | |
| OpenACC data directives | ❌ | ❌ | ❌ | ✅ |
| OpenMP target offload | ❌ | ❌ | ❌ | ✅ |
| Array sections in GPU directives | ❌ | ❌ | ❌ | ✅ |
| present() / map(alloc:) optimisation | ❌ | ❌ | ❌ | ✅ |
| All four host/scheme memory combos | ❌ | ❌ | ❌ | ✅ |
| `--directive acc\|omp` CLI option | ❌ | ❌ | ❌ | ✅ |
| **Architecture** | | | | |
| MLIR IR (inspectable, composable) | ❌ | ❌ | ❌ | ✅ |
| Multi-language host model path | ❌ | ❌ | ❌ | In progress (see below) |

### Capability Notes

∥ **Unit conversion — implementation note:**
xdsl-ccpp allocates a local temporary for each unit-converted argument (e.g.
`ps_unit_conv = ps * 0.01_kind_phys`), matching capgen's approach.  The host's
array is never modified in-place.  For `intent=in` arguments the temporary is
discarded after the scheme call; for `intent=inout`/`intent=out` a write-back
converts the result back to host units before returning.

xdsl-ccpp also generates `ccpp_physics_suite_variables` with correct
input/output classification. A `state_variable=true` variable is listed as
output only when all schemes in the suite use the same units as the host (no
unit conversion); when a mismatch exists the variable is input-only, consistent
with the fact that the host array is never written.

¶ **Fortran source cross-validation — what is and isn't checked:**

The `ccpp_validate` tool (`pip install -e ".[validate]"`) validates each scheme's
`.F90` source against its `.meta` file using either fparser2 (pure Python, no
compiler required) or Flang/FIR (higher fidelity, requires a Flang build).  The
two backends differ in what they can check:

| Check | fparser2 | Flang/FIR | Notes |
|---|---|---|---|
| Argument existence | ✅ | ✅ | flags args in source but not in `.meta`, and vice versa |
| Type | ✅ | ✅ | intrinsic types (`real`, `integer`, `character`) and derived types (`type(name)`) |
| Rank (dimension count) | ✅ | ✅ | both assumed-shape `(:)` and explicit-shape `(n)` |
| Intent | ✅ | ✅ | `in`, `out`, `inout` |
| Optional flag | ✅ | ✅ | Fortran `OPTIONAL` attribute vs `.meta` `optional = True` |
| Kind names | ✅ | ❌ | Flang/FIR lowers `kind_phys` to `f32`/`f64`; kind names not preserved in FIR |
| Dimension names | ✅ | ❌ | requires `--host-files`; Flang/FIR does not preserve dimension standard names |

§ **Compiled Fortran execution tests:**

| | helloworld | capgen | ddthost | advection | kessler | CCPP-SCM (GFS) |
|---|---|---|---|---|---|---|
| Suites | 1 | 2 | 2 | 1 | 1 | varies |
| Schemes | 2 | 6 | 6 | 4 (5 calls) | 2 | ~60 |
| Variables | ~12 | ~30 | ~30 | ~25 | ~15 | ~800+ |
| Optional args | 0 | 1 | 0 | 0 | 0 | ~550 |
| Constituents | 0 | 0 | 0 | yes | 0 | many |
| Groups | 1 | 3 | 3 | 1 | 1 | ~10 |
| xdsl-ccpp status | ✅ passes | ✅ passes | ✅ passes | ✅ passes | ✅ B4B vs original† | ❌ not yet |

Notes:
- **helloworld**: exercises kind conversion (`kind_phys`↔`kind_dyn`) and unit conversion (K↔degC)
- **capgen**: two suites (`temp_suite` + `ddt_suite`), 3 groups, 1 optional arg in `temp_adjust`
- **ddthost**: same suites as capgen; primary purpose is testing DDT host variables and Python-defined host interface (`ddthost_py.py`)
- **advection**: columnar-chunked physics with constituent registration (`ccpp_register_constituents`, `ccpp_number_constituents`, `ccpp_initialize_constituents`); column-sliced arrays passed correctly to schemes
- **kessler**: Kessler warm-rain microphysics scheme with OpenACC GPU directives generated by xdsl-ccpp; CPU execution verified bit-for-bit against the hand-written original cap using gfortran; GPU execution not yet tested
- **Variables**: unique standard names across all scheme `.meta` files in the example

† Bit-for-bit agreement with the hand-written Kessler cap compiled with gfortran; compiled and executed on CPU only — GPU execution pending.

#### atmospheric_physics suite cap generation

The 8 main suites from the [ESCOMP/atmospheric_physics](https://github.com/ESCOMP/atmospheric_physics) repository (used by CAM-SIMA) are exercised as a scheme-only cap generation test — no host files. This validates the pipeline against the real-world scale of that library: 146 `.meta` files, 173 `.F90` scheme sources, scheme counts ranging from 1 (adiabatic) to 65+ (cam4/cam5).

| Suite | Schemes | Subcycles | xdsl-ccpp status |
|---|---|---|---|
| `adiabatic` | 1 | none | ✅ cap generated |
| `held_suarez_1994` | 6 | none | ✅ cap generated |
| `tj2016` | 8 | none | ✅ cap generated |
| `cam7` | 25 | none | ✅ cap generated |
| `kessler` | 14 | none | ✅ cap generated |
| `musica` | 7 | none | ✅ cap generated |
| `cam4` | 65 | 2 (`number_of_diagnostic_subcycles`) | ✅ cap generated |
| `cam5` | 65 | 2 (`number_of_diagnostic_subcycles`) | ✅ cap generated |

These tests run without host files, so the generated caps contain scheme calls and suite lifecycle subroutines but no host-variable resolution or unit conversion.

### xdsl-ccpp Gaps vs capgen-ng

Ranked by impact on real-world use:

1. **Host model integration** — only the four example test cases (helloworld, capgen,
   ddthost, advection). No integration with CCPP-SCM, CAM-SIMA, or UFS.

### Next Steps to Further Match capgen-ng

The following work items are ordered by impact on closing the gap with production
capgen-ng use cases.

#### 1. Host model integration (CAM-SIMA / CCPP-SCM)
The xdsl-ccpp pipeline has been validated against all 8 main suites from the
`atmospheric_physics` repository (CAM-SIMA's scheme library) for scheme-only cap
generation — no host files required.  The next step is to supply the host `.meta`
files so that host-variable resolution, dimension validation, and unit conversion
are exercised at real-world scale (~800 variables).  After that, linking the
generated caps into a running host model (CCPP-SCM or CAM-SIMA) will confirm
end-to-end correctness.

### Multi-Language Support

The full plan for C++/Kokkos host + Fortran schemes support is in
[`multilanguage_plan.md`](multilanguage_plan.md). It describes a 7-phase,
6–9 week effort to enable a C++/Kokkos host model to call Fortran physics
schemes through a CCPP-generated BIND(C) cap, without requiring the cap
generator to know anything about Kokkos internals.

**Current status:**

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Structured `ModuleVarOp` type attributes | ✅ Done |
| 2 | `array_layout` metadata in host `.meta` files | ✅ Done |
| 3 | BIND(C) cap generation (`--interface bindC`) | Not started |
| 4 | C++ header printer | Not started |
| 5 | CMake `INTERFACE bindC` option | Not started |
| 6 | Kessler C++ driver example | Not started |
| 7 | Testing | Not started |

### Key Observations

#### ccpp_prebuild vs ccpp_capgen
`ccpp_prebuild` handles unit conversion, optional args, and chunked data well.
`ccpp_capgen` adds Fortran source cross-validation and nested suites but lacks
chunked data and optional args. Neither replaces the other — that is why
`ccpp_capgen-ng` exists.

#### ccpp_capgen-ng
Closes all gaps between prebuild and capgen, adds multi-instance support, and has
1300+ tests. Cannot add GPU support without an architectural rethink — it is a
text-templating generator throughout.

#### xdsl-ccpp unique advantages
GPU support (OpenACC and OpenMP) is unique among CCPP tools. The MLIR architecture
enables future capabilities none of the other tools can reach: multi-language host
models, additional GPU backends, and composable transformation passes. Physics
correctness is verified across all four example test cases — helloworld, capgen,
ddthost, and advection. Unit conversion uses local temporaries (consistent with
capgen), `ccpp_physics_suite_variables` correctly classifies input and output
variables including constituent and state-variable handling, and column-chunked
physics with constituent registration is fully supported.

Multi-instance support (ensemble / perturbation-parameter runs) is now implemented
via a `ccpp_t` derived-type handle threaded as `intent(inout)` through every
generated subroutine. When the host provides a variable with
`standard_name = ccpp_t_instance`, the generated `ccpp_suite_state` flag is
declared as `dimension(N)` and indexed by `ccpp_data%ccpp_instance`. The instance
count defaults to 200 and is configurable via `--num-instances N` on the
`ccpp_xml` frontend or `generate-suite-cap{num_instances=N}` as a pass parameter.

### Recommended Use Today

| Use case | Recommended tool |
|---|---|
| Production CPU physics — old metadata format | ccpp_prebuild |
| Production CPU physics — new metadata format | ccpp_capgen |
| Next-gen CPU physics development | ccpp_capgen-ng |
| GPU-enabled physics development | xdsl-ccpp |
| Research into multi-language host models | xdsl-ccpp |
