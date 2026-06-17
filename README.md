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
```

## Examples

The `examples/` directory contains several complete examples:

| Directory | Description |
|-----------|-------------|
| `helloworld/` | Two schemes (`hello_scheme`, `temp_adjust`) with XML and Python frontends |
| `advection/` | Advection scheme example with XML frontend |
| `ddthost/` | Example using Fortran derived data types (DDTs) and optional entry points |

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
| **Metadata format** | | | | |
| Old embedded-comment format | ✅ | ❌ | ❌ | ❌ |
| New `.meta` file format | ❌ | ✅ | ✅ | ✅ |
| **Variable handling** | | | | |
| Host variable matching | ✅ | ✅ | ✅ | Partial† |
| Variable compatibility validation | ✅ | ✅ | ✅ | Partial‡ |
| Unit/kind conversion | ✅ | ✅ | ✅ | ✅ |
| Optional argument handling | ✅ | Partial | ✅ | ✅ |
| Chunked data layout | ✅ | ❌ | ✅ | ❌ |
| Constituent registration | ✅ | ✅ | ✅ | ❌ |
| **Code correctness** | | | | |
| Fortran source cross-validation | ❌ | ✅ | ✅ | ✅¶ |
| Multi-instance support | ❌ | ❌ | ✅ | ❌ |
| **Build & tooling** | | | | |
| Build system integration (CMake) | ✅ | ✅ | ✅ | ❌ |
| Documentation generation | ✅ HTML/LaTeX | ✅ datatable.xml | ✅ | ❌ |
| `ccpp_track_variables` utility | ✅ | ❌ | ✅ | ❌ |
| **Testing** | | | | |
| Compiled Fortran execution tests | ✅ | ✅ | ✅ | Partial§ |
| Unit test depth | Moderate | Moderate | 1300+ tests | 80 pytest + 3 Makefiles |
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
| Multi-language host model path | ❌ | ❌ | ❌ | ✅ (architecture ready) |

### Notes on Partial / Missing xdsl-ccpp Capabilities

† **Host variable matching — remaining gaps:**
- `allocatable` code generation for non-real types (`ccpp_constituent_properties_t`
  arrays) — the type is declared correctly but constituent registration infrastructure
  (`ccpp_register_constituents` etc.) is not generated. This is the same gap as
  "Constituent registration" in the capability table above.

‡ **Variable compatibility validation — remaining gaps:**
- Dimension name cross-validation beyond `horizontal_loop_extent` →
  `horizontal_dimension` (other substitutions are resolved but not checked)
- DDT member type/rank/kind validation (members matched by standard_name only)

¶ **Fortran source cross-validation — what is and isn't checked:**

The `ccpp_validate` tool (`pip install -e ".[validate]"`) validates each scheme's
`.F90` source against its `.meta` file using fparser2 (pure Python) or Flang (FIR):

| Check | Validated | Notes |
|---|---|---|
| Argument existence | ✅ | flags args in source but not in `.meta`, and vice versa |
| Type | ✅ | intrinsic types (`real`, `integer`, `character`) and derived types (`type(name)`) |
| Rank (dimension count) | ✅ | both assumed-shape `(:)` and explicit-shape `(n)` |
| Intent | ✅ | `in`, `out`, `inout` |
| Optional flag | ✅ | Fortran `OPTIONAL` attribute vs `.meta` `optional = True` |
| Kind names | ✅/❌ | fparser2 backend only; Flang/FIR lowers `kind_phys` to `f32`/`f64` |
| Dimension names | ✅/❌ | requires `--host-files`; names checked against host standard names |

§ **Compiled Fortran execution tests:**

| | helloworld | capgen | ddthost | advection | CCPP-SCM (GFS) |
|---|---|---|---|---|---|
| Suites | 1 | 2 | 2 | 1 | varies |
| Schemes | 2 | 6 | 6 | 4 (5 calls) | ~60 |
| Variables | ~12 | ~30 | ~30 | ~25 | ~800+ |
| Optional args | 0 | 1 | 0 | 0 | ~550 |
| Constituents | 0 | 0 | 0 | yes | many |
| Groups | 1 | 3 | 3 | 1 | ~10 |
| xdsl-ccpp status | ✅ passes | ✅ passes | ✅ passes | ⚠ blocked | ❌ not yet |

Notes:
- **helloworld**: exercises kind conversion (`kind_phys`↔`kind_dyn`) and unit conversion (K↔degC)
- **capgen**: two suites (`temp_suite` + `ddt_suite`), 3 groups, 1 optional arg in `temp_adjust`
- **ddthost**: same suites as capgen; primary purpose is testing DDT host variables and Python-defined host interface (`ddthost_py.py`)
- **advection**: caps generate and compile; full end-to-end test blocked on missing constituent registration infrastructure (`ccpp_register_constituents` etc.)
- **Variables**: unique standard names across all scheme `.meta` files in the example

### xdsl-ccpp Gaps vs capgen-ng

Ranked by impact on real-world use:

1. **Constituent registration infrastructure** — `ccpp_register_constituents`,
   `ccpp_number_constituents`, `ccpp_initialize_constituents` and related API not
   generated. Blocks the advection test case and any suite with advected species.

2. **Build system integration** — no CMake or Make integration. xdsl-ccpp runs as a
   standalone script and cannot be embedded in a host model build.

3. **Host model integration** — only the three example test cases (helloworld, capgen,
   ddthost). No integration with CCPP-SCM, CAM-SIMA, or UFS.

4. **Chunked data layout** — column-blocked physics loops not supported.

5. **Multi-instance support** — one suite instance per run only.

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
correctness is verified across helloworld, capgen, and ddthost.

### Recommended Use Today

| Use case | Recommended tool |
|---|---|
| Production CPU physics — old metadata format | ccpp_prebuild |
| Production CPU physics — new metadata format | ccpp_capgen |
| Next-gen CPU physics development | ccpp_capgen-ng |
| GPU-enabled physics development | xdsl-ccpp |
| Research into multi-language host models | xdsl-ccpp |
