# xdsl-ccpp Developer Guide

This document covers internal pipeline details not needed for day-to-day use of
the `ccpp_xdsl` driver. For user-facing documentation see [README.md](README.md).

---

## Running the Pipeline Manually

The `ccpp_xdsl` driver is a thin wrapper around two separate tools that can be
composed by hand:

| Tool | Module | Role |
|------|--------|------|
| Frontend (XML) | `xdsl_ccpp.frontend.ccpp_xml` | Parse XML + `.meta` → MLIR IR |
| Frontend (Python) | `xdsl_ccpp.frontend.py_api` | Python suite definition → MLIR IR |
| Optimizer | `xdsl_ccpp.tools.ccpp_opt` | Apply transformation passes → Fortran |

### Frontend only (parse → MLIR IR)

```bash
python3 -m xdsl_ccpp.frontend.ccpp_xml \
  --suites       examples/helloworld/hello_world_suite.xml \
  --scheme-files examples/helloworld/hello_scheme.meta,examples/helloworld/temp_adjust.meta
```

### Frontend → optimizer (MLIR IR after all passes, before Fortran output)

```bash
python3 -m xdsl_ccpp.frontend.ccpp_xml \
  --suites       examples/helloworld/hello_world_suite.xml \
  --scheme-files examples/helloworld/hello_scheme.meta,examples/helloworld/temp_adjust.meta \
| python3 -m xdsl_ccpp.tools.ccpp_opt \
  -p generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap,generate-kinds,strip-ccpp
```

### Full pipeline (frontend → optimizer → Fortran)

```bash
python3 -m xdsl_ccpp.frontend.ccpp_xml \
  --suites       examples/helloworld/hello_world_suite.xml \
  --scheme-files examples/helloworld/hello_scheme.meta,examples/helloworld/temp_adjust.meta \
| python3 -m xdsl_ccpp.tools.ccpp_opt \
  -p generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap,generate-kinds,strip-ccpp \
  -t ftn
```

### Python API frontend

```bash
python3 examples/helloworld/helloworld_py.py \
| python3 -m xdsl_ccpp.tools.ccpp_opt \
  -p generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap,generate-kinds,strip-ccpp \
  -t ftn
```

### Pass reference

| Pass name | Role |
|-----------|------|
| `scope-packages` | Check each package's declared `shared_state` against the inferred interface, then rename each package-private standard name to `<package>__<name>` and mark its arguments suite-owned (see `package_scope.py`); first in the driver's pipeline, before `flatten-composites` erases the package boundaries, a no-op without packages |
| `flatten-composites` | Inline `ccpp.composite` ops (from `@ccpp_composite` and package entry points in the Python frontend) into their callers and erase `ccpp.package` declarations; runs right after `scope-packages`, a no-op without composites |
| `generate-meta-cap` | Build cap metadata ops from descriptor tables |
| `generate-meta-kinds` | Propagate kind information across the IR |
| `generate-host-match` | Annotate scheme args with matching host variable names, kinds, and units |
| `generate-arg-ownership` | Annotate every scheme `ccpp.arg` op with its `ownership_kind` — durably, once, whether the cap owns this arg or its data comes from outside (Phase 7 IR unification) |
| `generate-suite-cap` | Emit per-suite subroutines (`*_suite_physics`, lifecycle init/finalize) |
| `generate-ccpp-cap` | Emit the host-facing cap (`ccpp_physics_initialize`, `ccpp_physics_run`, etc.) |
| `generate-cpp-cap` | Emit a BIND(C) chost Fortran cap + C++ header/wrapper, for C++ host models. No-ops unless a host/module table declares `language = "c++"` |
| `generate-kinds` | Emit `ccpp_kinds.F90` |
| `generate-gpu-ccpp-cap` | Insert OpenACC/OpenMP data directives at the ccpp_cap level |
| `generate-gpu-data` | Insert OpenACC/OpenMP directives at the suite_cap level for unmatched device variables |
| `generate-gpu-debug-prints` | Opt-in GPU-residency debug prints (only emitted with `--gpu-debug-prints`) — reports whether a variable/slice is actually present and correctly sized on the device at a given point in a run |
| `strip-ccpp` | Remove CCPP dialect ops, leaving standard MLIR |

Pass options are set with `{key=value}` syntax, e.g. `generate-ccpp-cap{bind_c=true}`.

The `ccpp_xdsl` driver builds its own pass list automatically (see
`_build_pipeline` in `xdsl_ccpp/tools/ccpp_dsl.py`) rather than using a fixed
string: `generate-host-match` is only inserted when `--host-files` is given,
and `generate-ccpp-cap`/`generate-cpp-cap` only run — always as a pair, right
after `generate-suite-cap` (and `generate-gpu-data`, if `--directive` was
given) — also gated on `--host-files` being present. The example pass lists
below are for manually composing `ccpp_opt` directly and don't reproduce that
conditional logic — they're a fixed, minimal pipeline without host-matching
or the C++ backend, not a stand-in for what the driver would build for the
same flags.

---

## Code Organization

### Transformation passes

The transformation pipeline lives under `xdsl_ccpp/transforms/`:

| Module | Pass name | Role |
|--------|-----------|------|
| `suitecap/package_cap.py` | — (called by `generate-suite-cap`) | Generates each `<package>_package_cap` module from the `ccpp.package_cap` op: one routine per segment, private names as module variables |
| `lower_packages.py` | `lower-packages` | Package caps (2f, `ccpp_dsl --package-caps`): replaces each segment's calls with one synthetic scheme whose metadata is the segment's interface, and moves the calls into a `ccpp.package_cap` op |
| `package_segments.py` | — (analysis; `ccpp_dsl --list-package-scope`) | How a per-package cap would cut each package's code into routines (segments at hooks, per phase); multi-instance check |
| `package_scope.py` | `scope-packages` | Package scope and interface: the analysis (`ccpp_dsl --list-package-scope`: private names, interface inputs/outputs, shared state) and the pass that checks shared state and scopes private names, before flattening |
| `flatten_composites.py` | `flatten-composites` | Inlines composite schemes into their callers before any other pass except `scope-packages` |
| `ccpp_cap.py` | `generate-ccpp-cap` | Host-facing cap (`ccpp_physics_initialize`, `ccpp_physics_run`, etc.) |
| `cpp_interop.py` | `generate-cpp-cap` | C++/BIND(C) host-interop cap ("chost") — runs immediately after `generate-ccpp-cap`, no-ops without a `language = "c++"` host/module table |
| `suite_cap.py` | `generate-suite-cap` | Per-suite subroutines (`*_suite_physics`, lifecycle init/finalize) |
| `host_var_match_pass.py` | `generate-host-match` | Annotates scheme arg ops with matching host variable names, kinds, and units |
| `gpu_ccpp_cap_pass.py` | `generate-gpu-ccpp-cap` | Inserts OpenACC/OpenMP data directives at the ccpp_cap level |
| `gpu_data_pass.py` | `generate-gpu-data` | Inserts OpenACC/OpenMP directives at the suite_cap level for unmatched device variables |

`ccpp_cap.py`'s `generate-ccpp-cap` pass isn't monolithic — it calls directly
into three plain (not separately pass-registered) modules to generate parts
of the combined cap module:

| Module | Called for |
|--------|------------|
| `run_dispatch.py` | The run-dispatch cluster: per-suite argument resolution (host var / DDT member / cap var / block arg) and the nested if/else dispatch chain for `ccpp_physics_run` |
| `lifecycle_cap.py` | The `ccpp_init`/`ccpp_final`/`ccpp_physics_timestep_init`/`ccpp_physics_timestep_final` lifecycle dispatcher subroutines |
| `constituent_cap.py` | The constituent API (`ccpp_physics_get_constituent_...`) and its supporting metadata collection |

All three were extracted from `ccpp_cap.py` itself (originally one ~4,700-line
file) and still depend on it for a handful of shared helpers — see
`cap_shared.py` below. All three stay plain modules rather than becoming
registered passes: unlike `cpp_interop.py`, which scans an already-complete
ccpp module built by a prior pass, these three are called *mid-construction*,
contributing functions into the *same* ModuleOp `ccpp_cap.py` is still
assembling, using shared Python state (`host_var_map`, `cap_var_map`, the
`ccpp_t` handle) that isn't durable IR. Promoting any of them would mean
re-deriving that state from the IR the way `cpp_interop.py` does — which
wasn't possible until that state became durable IR. That state's now
durable: Phase 7 ("full IR unification", Stages 1-4) is done — see
`CHANGELOG.md` for the full history — but promoting these three modules
into registered passes hasn't been revisited since, so they remain plain
modules called mid-construction for now.

Shared utilities live in `xdsl_ccpp/transforms/util/`:

| Module | Contents |
|--------|----------|
| `ir_utils.py` | `find_ccpp_module(ops)` — locates the named `@ccpp` ModuleOp from an op list |
| `ccpp_descriptors.py` | `BuildMetaDataDescriptions` — walks CCPP metadata tables into Python descriptor objects |
| `cap_shared.py` | Helpers shared by `ccpp_cap.py`, `cpp_interop.py`, `lifecycle_cap.py`, and `constituent_cap.py` — `_bare`, `_build_host_var_map`, `_get_suite_lifecycle_ret_info`, `_is_framework_managed`. A neutral leaf module (no dependency on any of those four), so they can all import from it without an import cycle |

When writing a new pass that needs the CCPP metadata module, import
`find_ccpp_module` from `xdsl_ccpp.transforms.util.ir_utils`.

### Dialects

Custom MLIR dialects are defined under `xdsl_ccpp/dialects/`:

| Module | Contents |
|--------|----------|
| `ccpp_utils.py` | Core CCPP ops: `ModuleVarOp`, `HostVarRefOp`, `UnitConvertOp`, `RowMajorConvertOp`, and related ops |
| `ccpp.py` | Suite-structure ops (`SuiteOp`, `GroupOp`, `SchemeOp`, `SubcycleOp`, `CompositeOp`, `PackageOp`), metadata table ops (`TablePropertiesOp`, `ArgumentTableOp`, `ArgumentOp`), kind ops (`KindOp`, `KindsOp`), and `ResolvedArgOp`/`ArgSourceKind` (durable per-argument source resolution, built by `run_dispatch.py`) |

### ModuleVarOp type representation

`ModuleVarOp` represents a module-level variable declaration. Its type is stored
as four structured attributes rather than a pre-rendered Fortran string:

| Attribute | Required | Example |
|-----------|----------|---------|
| `base_type` | yes | `"real"`, `"integer"`, `"character"`, `"logical"`, `"type"` |
| `kind` | no | `"kind_phys"`, `"kind_dyn"`, `"512"` (char length) |
| `ddt_name` | no | `"vmr_type"` (when `base_type == "type"`) |
| `is_pointer` | no | `True` → Fortran `POINTER` attribute |
| `is_target` | no | `True` → Fortran `TARGET` attribute |

The Fortran printer reconstructs the declaration from these fields; a C++ header
printer can interpret the type without parsing Fortran syntax.

### Backends

| Module | `-t` flag | Output |
|--------|-----------|--------|
| `xdsl_ccpp/backend/print_ftn.py` | `ftn` | Fortran source files |
| `xdsl_ccpp/backend/print_cpp_header.py` | `cpp_header` | C++ `extern "C"` header + `ccpp_kinds.h` |

---

## Adding a New Pass

1. Create a module under `xdsl_ccpp/transforms/`.
2. Define a class inheriting from `ModulePass` (see existing passes for the pattern).
3. Register the pass in `xdsl_ccpp/tools/ccpp_opt.py`.
4. Add FileCheck tests under `tests/filecheck/examples/` covering the new pass.

A pass builds language-neutral IR: no Fortran or C++ syntax in transforms, as raw-text
ops or inside typed ops' string fields -- compose existing ops, or add a reusable op
and its printer case. The full rule is in [`CLAUDE.md`](CLAUDE.md) (read by coding
agents too).

---

## Checking generated caps against real CAM-SIMA cases

The FileCheck goldens cover `examples/` only. For a change to the cap
generators, also check the caps of real CAM-SIMA suites with
`xdsl_ccpp/tools/cap_oracle.py`. It needs built CAM-SIMA case directories,
whose build cache records the generator inputs. It only generates caps and
compiles nothing.

```bash
# Old vs new: generate each case with a base revision (default main) and with
# the working tree, and diff the generated files. A refactor should report
# IDENTICAL everywhere.
python -m xdsl_ccpp.tools.cap_oracle diff [--base REV] CASE_DIR...

# The same for examples/: every xdsl_ccpp_capgen() call of a configured build
# tree of this repository (cmake -S . -B build; no build needed).
python -m xdsl_ccpp.tools.cap_oracle diff [--base REV] --examples build

# Against original capgen (CAM-SIMA's bundled ccpp_framework): compare what
# the code does (scheme calls per phase, and what each argument receives).
python -m xdsl_ccpp.tools.cap_oracle capgen CASE_DIR...
```

- Cases with the same inputs (e.g. the gnu, intel and nvhpc copies of an
  FPHYStest case) are generated once. Distinct cases run in parallel
  (`-j N`). The default is half the CPUs available to you: 4 on a Derecho
  login node, whose per-user quota is 8.
- `capgen` skips Python-suite and package-cap cases, and compares GPU cases
  without `--directive`. Suites capgen rejects (Kessler's `memory_space`)
  are reported as `NO CAPGEN`, not as failures.
- Differences are written to `diff.txt` / `differences.txt` under `--out`
  (default: a new temporary directory). The exit status is 1 if anything
  differs.
- `--examples` reads the command each `xdsl_ccpp_capgen()` call records at
  configure time (`<output dir>/xdsl_ccpp_command.txt`, written by
  `cmake/xdsl_ccpp_capgen.cmake`), so it covers exactly what CMake would
  run; reconfigure after changing an example's `CMakeLists.txt`. Both
  revisions read the example inputs from the working tree.
- A full aux_sima set (about 90 built cases, 29 distinct) takes about 2
  minutes for `diff` and 1 minute for `capgen` on a login node.

## Finding code nothing runs

`xdsl_ccpp/tools/code_coverage.py` measures, with coverage.py, which code
the generator runs for the same inputs as `cap_oracle` and which code only
the tests run. It uses `coverage` and, for `--vulture`, `vulture`, both in
the `dev` extra.

```bash
python -m xdsl_ccpp.tools.code_coverage run --out DIR [--examples build] [--no-tests] CASE_DIR...
python -m xdsl_ccpp.tools.code_coverage report DIR [--vulture]
```

`DIR/report.md` lists each file's coverage, the functions only the tests
run, the functions nothing runs, and blocks of generator-run functions that
no case reaches. These are candidates, not verdicts: error paths and unused
options are legitimate, so read each one before removing it.

---

## Linting

```bash
ruff check xdsl_ccpp/
ruff format xdsl_ccpp/
```
