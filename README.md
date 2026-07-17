# xdsl-ccpp

An [MLIR](https://mlir.llvm.org)-based implementation of the
[CCPP](https://github.com/NCAR/ccpp-framework) (Common Community Physics Package)
cap generator, built on the [xDSL](https://github.com/xdslproject/xdsl) Python
framework. It reads CCPP suite XML and scheme metadata files and generates Fortran
cap subroutines, with optional GPU data-movement directives and C++/BIND(C)
interoperability support.

For internal pipeline and pass details see [`DEVELOPERS.md`](DEVELOPERS.md).

---

## Installation

### Clone the repository

```bash
git clone https://github.com/johnmauff/xdsl-ccpp.git
cd xdsl-ccpp
```

### Laptop

```bash
pip install .
```

This installs the `ccpp_xdsl` command-line driver and the `xdsl_ccpp` Python
package. Requires Python 3.11+ and installs xDSL 0.56.1 as a dependency.

For development (linting, testing):

```bash
pip install -e ".[dev]"
```

For Fortran source cross-validation (`ccpp_validate`):

```bash
pip install -e ".[validate]"
```

### Derecho (NCAR)

Derecho runs inside a system-managed virtual environment. Create your own conda
environment to get a writable Python installation:

```bash
module load conda
conda create -n xdsl-ccpp python=3.11
conda activate xdsl-ccpp
pip install -e ".[dev]"
pip install -e ".[validate]"
```

Run `conda activate xdsl-ccpp` at the start of each session, or add it to your
`~/.bashrc`.

For Fortran source cross-validation (uses fparser2, pure Python — no compiler
required):

```bash
pip install -e ".[validate]"
```

---

## Quick Start

The `examples/helloworld/` directory contains a complete example with two physics
schemes and a host model. Run the full compilation flow:

```bash
ccpp_xdsl \
  --suites       examples/helloworld/hello_world_suite.xml \
  --scheme-files examples/helloworld/hello_scheme.meta,examples/helloworld/temp_adjust.meta \
  --host-files   examples/helloworld/hello_world_mod.meta \
  -o output/
```

This generates three Fortran files in `output/`:

| File | Description |
|------|-------------|
| `ccpp_kinds.F90` | Kind parameter definitions (`kind_phys`, etc.) |
| `hello_world_suite_cap.F90` | Suite cap subroutines for `hello_world_suite` |
| `hello_world_ccpp_cap.F90` | Host-facing cap (`ccpp_physics_initialize`, `ccpp_physics_run`, etc.) |

---

## XML API

The XML frontend reads a standard CCPP suite definition file (SDF) plus
`.meta` files for schemes and host variables.

### ccpp_xdsl driver options

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
                        generated regardless of memory_space attributes.
  --no-memory-space-warning
                        Suppress the warning emitted when memory_space attributes
                        are present but --directive is not set.
  --emit-datatable      Write datatable.xml to this path after generating caps
  --emit-html           Write per-entry-point HTML variable tables to this directory
                        (requires --emit-datatable)
  --num-instances N     Maximum number of simultaneous CCPP instances (ensemble
                        members). When set, ccpp_suite_state is a per-instance array
                        of length N instead of the default (200).
  --bind-c              Generate BIND(C) Fortran cap subroutines and matching C++
                        headers (<HostName>_ccpp_cap.h and ccpp_kinds.h).
                        Requires --host-files.
```

---

## Python API

xdsl-ccpp provides a Python frontend (`xdsl_ccpp.frontend.py_api`) for defining
suites programmatically. It replaces the suite XML file and, optionally, the
per-scheme `.meta` argument lists.

### Two modes

**Inline** — define scheme arguments directly in Python (useful when no `.meta`
file exists yet):

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

**From `.meta` files** — load existing `.meta` files and write only the suite
orchestration in Python. This is the preferred approach when `.meta` files already
exist, as it keeps them as the single source of truth:

```python
from xdsl_ccpp.frontend.py_api import ccpp_scheme_from_meta, ccpp_suite, emit_ir

kessler        = ccpp_scheme_from_meta("examples/kessler/scheme/kessler.meta")
kessler_update = ccpp_scheme_from_meta("examples/kessler/scheme/kessler_update.meta")

@ccpp_suite("kessler_suite", version="1.0")
class kessler_suite:
    physics = [kessler, kessler_update]

if __name__ == "__main__":
    emit_ir(kessler_suite)
```

### Loader functions

| Function | Loads | Returns |
|----------|-------|---------|
| `ccpp_scheme_from_meta(file)` | First `type=scheme` block | `SchemeDescriptor` |
| `ccpp_scheme_from_meta(file, name="foo")` | Named scheme block | `SchemeDescriptor` |
| `ccpp_host_from_meta(file)` | All host/module blocks | `list[TableDescriptor]` |
| `ccpp_ddt_from_meta(file)` | First `type=ddt` block | `TableDescriptor` |

### Subcycles with `forLoop`

Use `forLoop` when the loop count is a CCPP standard name resolved at runtime
(matching `<subcycle loop="name">` in the suite XML):

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

For a fixed integer count known at code-generation time, a plain Python `for`
loop inside `def run():` is simpler:

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

Passing a CCPP standard name string to `range()` raises a clear error directing
you to `forLoop` instead.

### Compile-time parameters

`ccpp_param(name, default)` reads a `name=value` token from the command line at
IR-generation time, falling back to `default`:

```python
top = ccpp_param("top", default=19)   # override: python3 suite.py top=53
```

### Multiple suites

Pass a list to `emit_ir` to include multiple suites in one IR output:

```python
emit_ir([ddt_suite, temp_suite], additional=[vmr_type, *host])
```

---

## Functionality

### Cap Generation

`ccpp_xdsl` generates three Fortran files per run:

| File | Description |
|------|-------------|
| `ccpp_kinds.F90` | Kind parameter definitions (`kind_phys`, `kind_dyn`, etc.) |
| `<suite_name>_cap.F90` | Suite cap: per-suite `_physics`, `_initialize`, `_finalize`, etc. |
| `<HostName>_ccpp_cap.F90` | Host-facing cap: `ccpp_physics_run`, `ccpp_physics_initialize`, etc. |

When `--host-files` is supplied, the host-facing cap resolves host module variables,
performs unit and kind conversion, slices column arrays, and handles DDT member access.
Without `--host-files`, scheme calls and suite lifecycle subroutines are still
generated correctly.

### GPU Directives

Pass `--directive acc` or `--directive omp` to emit OpenACC or OpenMP target-offload
data directives around scheme physics calls. The directives are driven entirely by
`memory_space` metadata — no changes to scheme Fortran sources are required.

Mark an argument as GPU-resident in a scheme `.meta` file:

```ini
[ qv ]
  standard_name = water_vapor_mixing_ratio_wrt_moist_air_and_condensed_water
  ...
  memory_space = device
```

The clause used for each device-resident argument is chosen from its `intent`:

| Intent | OpenACC clause | OpenMP clause |
|--------|---------------|---------------|
| `in` | `copyin()` | `map(to:)` |
| `inout` | `copy()` | `map(tofrom:)` |
| `out` | `copyout()` | `map(from:)` |
| already device (host declares `model_var_memory_space = device`) | `present()` | `map(alloc:)` |

Example output (OpenACC):

```fortran
!$acc data copy(theta(col_start:col_end, 1:nz), qv(col_start:col_end, 1:nz)) &
!$acc      copyin(cpair(col_start:col_end, 1:nz))
call kessler_suite_suite_physics(...)
!$acc end data
```

### Metadata Skeleton Generation

`ccpp_generate_meta` generates a `.meta` skeleton from a Fortran source file. It
extracts argument names, types, kinds, intents, rank, and optional flags from
subroutine signatures, and fills in stubs for fields that cannot be inferred
(`standard_name`, `units`, dimension standard names).

```bash
ccpp_generate_meta scheme.F90
```

Only subroutines following CCPP entry-point naming conventions are included
(`_run`, `_init`, `_finalize`, `_final`, `_timestep_init`, `_timestep_final`).

```
Options:
  FILE.F90 [...]     One or more Fortran source files
  --output-dir DIR   Write .meta files here (default: same dir as .F90)
  --stdout           Print to stdout instead of writing files
  -v, --verbose      Print the output path for each generated file
```

Requires fparser: `pip install fparser` (or `pip install -e ".[validate]"`).

### Fortran Source Cross-Validation

`ccpp_validate` checks each scheme's `.meta` file against its `.F90` source,
flagging mismatches in argument existence, type, rank, intent, and optional status.

```bash
ccpp_validate examples/capgen/*.F90
```

Pass `--host-files` to enable dimension name validation against the host model registry.

The tool auto-detects the best available parsing backend:

| Backend | Install | Notes |
|---------|---------|-------|
| `fparser2` | `pip install fparser` | Pure Python, no external tools required |
| `flang` | system LLVM or conda | Production Fortran compiler, more robust |

| Check | fparser2 | Flang/FIR |
|-------|----------|-----------|
| Argument existence | ✅ | ✅ |
| Type | ✅ | ✅ |
| Rank | ✅ | ✅ |
| Intent | ✅ | ✅ |
| Optional flag | ✅ | ✅ |
| Kind names | ✅ | ❌ (lowered to `f32`/`f64`) |
| Dimension names | ✅ | ❌ (requires `--host-files`) |

### Variable Tracking

`ccpp_track_variables` traces a CCPP standard-name variable through a suite's call
tree and reports which scheme entry points use it, with intent, units, and whether
a unit conversion will be applied.

```bash
ccpp_track_variables \
  --suites       examples/advection/cld_suite.xml \
  --scheme-files examples/advection/const_indices.meta,... \
  --host-files   examples/advection/test_host_data.meta \
  --variable     surface_air_pressure
```

Example output:

```
Suite: cld_suite
Variable: surface_air_pressure

  Group: physics
    cld_liq_run  local=ps  intent=in  units=hpa  host=pa  [unit-converted]
    cld_ice_run  local=ps  intent=in  units=pa   host=pa
```

| Option | Description |
|--------|-------------|
| `--suites` | Comma-separated suite XML files (required) |
| `--scheme-files` | Comma-separated scheme `.meta` files (required) |
| `--host-files` | Host `.meta` files (optional; needed for unit mismatch detection) |
| `--variable` | Standard name to trace, case-insensitive (required) |
| `--suite` | Restrict output to a single named suite |
| `--entry-points` | Entry-point suffixes to check (default: `run`) |

Exit code is 0 when the variable is found in at least one scheme, 1 otherwise.

### CMake Integration

xdsl-ccpp provides a CMake module (`cmake/xdsl_ccpp.cmake`) that runs `ccpp_xdsl`
at configure time and returns the list of generated `.F90` cap files. Requires
CMake 3.20+ and `ccpp_xdsl` on `PATH`.

```cmake
include(path/to/cmake/xdsl_ccpp.cmake)

xdsl_ccpp_generate(
    HOST_NAME   "MyHost"
    OUTPUT_ROOT "${CMAKE_CURRENT_BINARY_DIR}/ccpp_caps"
    TARGET_VAR  MY_CAPS
    SUITES      "${CMAKE_CURRENT_SOURCE_DIR}/my_suite.xml"
    SCHEMEFILES "${CMAKE_CURRENT_SOURCE_DIR}/scheme_a.meta"
                "${CMAKE_CURRENT_SOURCE_DIR}/scheme_b.meta"
    HOSTFILES   "${CMAKE_CURRENT_SOURCE_DIR}/host_data.meta"
)

add_executable(my_host ${MY_SRCS} ${MY_CAPS})
```

| Argument | Required | Description |
|----------|----------|-------------|
| `HOST_NAME` | yes | CamelCase prefix for generated subroutine names |
| `OUTPUT_ROOT` | yes | Directory where `.F90` files are written |
| `TARGET_VAR` | yes | CMake variable receiving the list of generated `.F90` paths |
| `SUITES` | yes | One or more suite XML files |
| `SCHEMEFILES` | yes | One or more scheme `.meta` files |
| `HOSTFILES` | no | Host model `.meta` files |
| `EMIT_DATATABLE` | no | Path to write `datatable.xml`; enables precise file discovery |

A working example is in `examples/capgen/CMakeLists.txt`:

```bash
cmake -S examples/capgen -B examples/capgen/build
cmake --build examples/capgen/build
ctest --test-dir examples/capgen/build
```

### Documentation Generation

`ccpp_datatable` produces a machine-readable `datatable.xml` and optionally
per-entry-point HTML variable tables. It serves two purposes:

1. **CMake file discovery** — `<ccpp_files>` lists every `.F90` cap file written,
   giving the CMake module a precise source list without globbing.
2. **Variable documentation** — `<var_dictionaries>` records full variable metadata
   (standard name, units, dimensions, type, intent) for every scheme entry point.

Integrated use (recommended):

```bash
ccpp_xdsl \
  --suites examples/capgen/scheme/ddt_suite.xml,examples/capgen/scheme/temp_suite.xml \
  --scheme-files examples/capgen/scheme/make_ddt.meta,examples/capgen/scheme/temp_set.meta \
  --host-files   examples/capgen/host_ftn/test_host.meta \
  --host-name    test_host \
  -o             caps/ \
  --emit-datatable caps/datatable.xml \
  --emit-html    caps/docs/
```

```
ccpp_datatable options:
  --mlir FILE       Frontend MLIR file (required)
  --caps-dir DIR    Directory containing generated .F90 cap files (required)
  -o FILE           Output path for datatable.xml (default: datatable.xml)
  --html-dir DIR    Write one HTML variable table per entry point here
  --host-name NAME  Host model name in the <datatable> root element
```

### Multi-Language Support

xdsl-ccpp provides two modes for C++ host models calling Fortran physics schemes,
plus a path for Fortran hosts calling C++ schemes.

#### `--bind-c` — C++ host with Fortran host module

Pass `--bind-c` to generate a BIND(C) Fortran physics cap plus a C++ header.
The Fortran host module still owns the physics arrays; the C++ caller drives the
CCPP lifecycle through generated `extern "C"` functions.

```bash
ccpp_xdsl --suites ... --scheme-files ... --host-files ... --bind-c -o bindc/
```

Generated files:

| File | Description |
|------|-------------|
| `ccpp_kinds.F90` | Kind parameter definitions |
| `<suite>_cap.F90` | Suite cap (same as standard Fortran build) |
| `<HostName>_ccpp_cap.F90` | BIND(C) physics cap |
| `<HostName>_ccpp_cap.h` | C++ `extern "C"` lifecycle declarations |
| `ccpp_kinds.h` | C++ `typedef` aliases for `kind_phys`, `kind_dyn`, etc. |

The C++ lifecycle functions follow the naming convention
`<HostName>_ccpp_physics_run`, `_ccpp_physics_initialize`, etc.:

```cpp
#include "Kessler_ccpp_cap.h"
Kessler_ccpp_physics_initialize(...);
Kessler_ccpp_physics_run(...);
```

The kessler example includes a working C++ BIND(C) driver (`driver_kessler_cpp.cpp`)
that builds with `make cxx` and produces bit-for-bit identical results to the Fortran
drivers (`make check`).

#### C++ host model (no Fortran host module)

To generate a *chost* ("C++ host") cap — a thin BIND(C) Fortran wrapper that takes
all physics arrays as explicit C-compatible arguments — add `language = c++` to the
host `.meta` `[ccpp-table-properties]` block:

```ini
[ccpp-table-properties]
  name = kessler_host_sub
  type = host
  language = c++
```

`ccpp_xdsl` then auto-detects the C++ host and no extra flags are needed:

```bash
ccpp_xdsl --suites ... --scheme-files ... --host-files host_cpp/... -o bindc/
```

No Fortran host module is required. This is the mode for C++ host models
(e.g. Kokkos-based) that own all physics data directly in C++.

Additional generated files:

| File | Description |
|------|-------------|
| `<HostName>_ccpp_chost_cap.F90` | Chost BIND(C) Fortran wrapper module |
| `<HostName>_ccpp_chost_cap.h` | C++ `extern "C"` declarations with C-compatible types |

Key differences from the plain BIND(C) cap:

- `col_start`/`col_end` loop bounds are removed; `ncol` (total column count) is passed directly
- Scalar reals and integers are passed by value; 2D arrays carry explicit `(ncol, nz)` dimensions
- C++ type mapping: `int` for integer scalars, `double` for real scalars, `const double*` for `intent(in)` arrays, `double*` for `intent(inout/out)` arrays, `char*` for character outputs, `int*` for error flag
- Lifecycle functions are renamed `<HostName>_chost_physics_run`, `_chost_physics_initialize`, etc.

```cpp
#include "Kessler_ccpp_chost_cap.h"
Kessler_chost_physics_initialize(lv, pref, rhoqr, gravit, errmsg, &errflg);
Kessler_chost_physics_run(ncol, nz, dt, lyr_surf, lyr_toa,
                           cpair, exner, theta, ..., scheme_name, errmsg, &errflg);
```

The kessler example includes a working C++ host driver (`driver_kessler_cxx_host.cpp`)
that builds with `make cxx_host` and is verified bit-for-bit against all three Fortran
drivers by `make check`.

#### Array layout

All array arguments in both modes are **column-major (Fortran order)**: the column
index varies fastest in memory. A C++ host must allocate and pass arrays accordingly:

```cpp
// ncol × nz array in Fortran column-major layout
std::vector<double> theta(ncol * nz);    // access: theta[col + ncol * lev]

// Kokkos equivalent (LayoutLeft = column-major):
Kokkos::View<double**, Kokkos::LayoutLeft> theta("theta", ncol, nz);
```

#### Known limitations

The current chost implementation has several known constraints — fixed `double`
precision (no REAL32), no DDT argument support, rank > 2 arrays, GPU memory
management, and others. See
[`multilanguage_limitations.md`](multilanguage_limitations.md) for the full list
with priority ordering and resolution notes.

#### Fortran host → C++ schemes

When a scheme's `.meta` table carries `language = c++`, the generated suite cap
emits a `BIND(C)` interface block instead of a `use <module>` statement, allowing
a C++ scheme to be called directly from a Fortran host. The cap generator emits
correct interface blocks; a compiled end-to-end example has not yet been written.

---

## Examples

| Directory | Description |
|-----------|-------------|
| `helloworld/` | Two schemes (`hello_scheme`, `temp_adjust`); exercises kind conversion (kind_phys↔kind_dyn) and unit conversion (K↔degC) |
| `capgen/` | Two suites (`temp_suite`, `ddt_suite`) with DDT host variables, optional arguments, and CMake build integration |
| `ddthost/` | DDT host variables and optional entry points; Python-defined host interface |
| `advection/` | Columnar-chunked physics with constituent registration; column-sliced arrays |
| `kessler/` | Kessler warm-rain microphysics; OpenACC GPU directives; four drivers: CCPP Fortran cap, hand-written Fortran, C++ BIND(C) (`--bind-c`), and C++ host model (`language = c++` in `host_cpp/*.meta`) |
| `atmospheric_physics/` | Python suite definitions for 9 suites from [ESCOMP/atmospheric_physics](https://github.com/ESCOMP/atmospheric_physics) (CAM-SIMA's scheme library) |

Each example can be driven via the XML frontend, the Python API, or both.

---

## Testing

Tests use [pytest](https://pytest.org) with
[LLVM-style FileCheck](https://llvm.org/docs/CommandGuide/FileCheck.html)
via the Python `filecheck` package.

```bash
pip install -e ".[dev]"   # install test dependencies
pytest tests/             # run all tests
pytest tests/filecheck/examples/end_to_end/helloworld-xml.mlir  # single test
```

### FileCheck tests

FileCheck tests live under `tests/filecheck/examples/` in three subdirectories:

```
tests/filecheck/examples/
├── end_to_end/    ← full pipeline: frontend + optimizer + Fortran backend
├── frontend/      ← frontend only: raw MLIR IR emitted by the parser
└── completed_ir/  ← frontend + optimizer passes, before Fortran backend
```

Each `.mlir` file contains a `// RUN:` directive and `// CHECK:` patterns that
the output must match. `conftest.py` discovers and runs all `.mlir` files
automatically.

To regenerate CHECK directives after an output change:

```bash
python3 tests/filecheck/examples/update-filecheck-test.py \
  tests/filecheck/examples/end_to_end/helloworld-xml.mlir
```

### Parsing non-trivial suite definition files

The 8 main suites from
[ESCOMP/atmospheric_physics](https://github.com/ESCOMP/atmospheric_physics)
(used by CAM-SIMA) are exercised as scheme-only cap generation tests — no host
files. This validates the pipeline at real-world scale: 146 `.meta` files,
173 `.F90` scheme sources.

| Suite | Schemes | Subcycles |
|-------|---------|-----------|
| `adiabatic` | 1 | none |
| `held_suarez_1994` | 6 | none |
| `tj2016` | 8 | none |
| `cam7` | 25 | none |
| `kessler` | 14 | none |
| `musica` | 7 | none |
| `cam4` | 65 | 2 (`number_of_diagnostic_subcycles`) |
| `cam5` | 65 | 2 (`number_of_diagnostic_subcycles`) |

### Compiled examples

| Example | Suites | Schemes | Variables | xdsl-ccpp status |
|---------|--------|---------|-----------|-----------------|
| `helloworld` | 1 | 2 | ~12 | ✅ passes |
| `capgen` | 2 | 6 | ~30 | ✅ passes |
| `ddthost` | 2 | 6 | ~30 | ✅ passes |
| `advection` | 1 | 4 | ~25 | ✅ passes |
| `kessler` | 1 | 2 | ~15 | ✅ bit-for-bit across all four drivers†‡ |
| CCPP-SCM (GFS) | varies | ~60 | ~800+ | ❌ not yet integrated |

† Bit-for-bit agreement verified on CPU; GPU execution not yet tested.

‡ All four drivers produce identical numerical output: the CCPP Fortran cap
(`kessler_ccpp`), hand-written Fortran cap (`kessler_hand`), C++ BIND(C) driver
(`kessler_cxx`, built with `--bind-c`), and C++ host model driver
(`kessler_cxx_host`, built with `language = c++` in `host_cpp/*.meta`). Verified by `make check` in
`examples/kessler/`.

---

## CCPP Tool Comparison

### Tool overview

| Tool | Status | Metadata format | Primary purpose |
|------|--------|-----------------|-----------------|
| `ccpp_prebuild` | Production, legacy | Old embedded-comment format | Cap generation + build integration |
| `ccpp_capgen` | Production, current | New `.meta` file format | Cap generation + Fortran validation |
| `ccpp_capgen-ng` | In development | New `.meta` file format | Unified successor to both above |
| `xdsl-ccpp` | Prototype | New `.meta` file format | MLIR-based cap generation + GPU |

### Capability comparison

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
| Unit test depth | Moderate | Moderate | 1300+ tests | 220 pytest + 3 Makefiles |
| **Host model integration** | | | | |
| CCPP-SCM | ✅ | ✅ | ✅ | ❌ |
| CAM-SIMA / UFS | ✅ | ✅ | In progress | ❌ |
| **GPU support** | | | | |
| OpenACC data directives | ❌ | ❌ | ❌ | ✅ |
| OpenMP target offload | ❌ | ❌ | ❌ | ✅ |
| Array sections in GPU directives | ❌ | ❌ | ❌ | ✅ |
| `present()` / `map(alloc:)` optimisation | ❌ | ❌ | ❌ | ✅ |
| All four host/scheme memory combos | ❌ | ❌ | ❌ | ✅ |
| `--directive acc\|omp` CLI option | ❌ | ❌ | ❌ | ✅ |
| **Architecture** | | | | |
| MLIR IR (inspectable, composable) | ❌ | ❌ | ❌ | ✅ |
| Multi-language host model path | ❌ | ❌ | ❌ | ✅ |

### Notes

∥ **Unit conversion:** xdsl-ccpp allocates a local temporary for each
unit-converted argument, matching capgen's approach. The host array is never
modified in-place. For `intent=inout`/`intent=out` a write-back converts the
result back to host units. `ccpp_physics_suite_variables` correctly classifies
input/output including constituent and state-variable handling.

¶ **Fortran source cross-validation:** see the
[Fortran Source Cross-Validation](#fortran-source-cross-validation) section for
what each backend checks.

§ **Compiled Fortran execution tests:** see the
[Compiled examples](#compiled-examples) table above.

### Key observations

**ccpp_prebuild vs ccpp_capgen:** Each handles some capabilities the other lacks
— prebuild has chunked data and optional args; capgen adds Fortran source
cross-validation and nested suites. Neither replaces the other, which is why
`ccpp_capgen-ng` exists.

**ccpp_capgen-ng:** Closes all gaps between prebuild and capgen, adds
multi-instance support, and has 1300+ tests. Cannot add GPU support without an
architectural rethink — it is a text-templating generator throughout.

**xdsl-ccpp unique advantages:** GPU support (OpenACC and OpenMP) is unique among
CCPP tools. The MLIR architecture enables future capabilities none of the other
tools can reach: multi-language host models, additional GPU backends, and composable
transformation passes. Physics correctness is verified across all five example test
cases including a C++ BIND(C) driver that produces bit-for-bit identical results
alongside the Fortran drivers.
