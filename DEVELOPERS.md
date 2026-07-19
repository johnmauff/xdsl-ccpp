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
| `generate-meta-cap` | Build cap metadata ops from descriptor tables |
| `generate-meta-kinds` | Propagate kind information across the IR |
| `generate-host-match` | Annotate scheme args with matching host variable names, kinds, and units |
| `generate-suite-cap` | Emit per-suite subroutines (`*_suite_physics`, lifecycle init/finalize) |
| `generate-ccpp-cap` | Emit the host-facing cap (`ccpp_physics_initialize`, `ccpp_physics_run`, etc.) |
| `generate-cpp-cap` | Emit a BIND(C) chost Fortran cap + C++ header/wrapper, for C++ host models. No-ops unless a host/module table declares `language = "c++"` |
| `generate-kinds` | Emit `ccpp_kinds.F90` |
| `generate-gpu-ccpp-cap` | Insert OpenACC/OpenMP data directives at the ccpp_cap level |
| `generate-gpu-data` | Insert OpenACC/OpenMP directives at the suite_cap level for unmatched device variables |
| `strip-ccpp` | Remove CCPP dialect ops, leaving standard MLIR |
| `fir-to-meta` | Generate CCPP metadata (`table_properties`/`arg_table`/`arg`) from Flang FIR MLIR — an alternative to parsing `.meta` files, used standalone by `xdsl_ccpp/tools/fir2meta.py` and the `ccpp_validate_fir.py`/`ccpp_validate_source.py` tools, not part of the `ccpp_xdsl` generation pipeline |
| `lower-ccpp-utils` | Lower remaining `ccpp_utils` dialect ops (`strcmp`, `set_string`, `write_errmsg`, `host_var_ref`, etc.) to plain `arith`/`memref`/`llvm`, for consumers needing fully-lowered standard MLIR rather than printed Fortran text |

Pass options are set with `{key=value}` syntax, e.g. `generate-ccpp-cap{bind_c=true}`.

`fir-to-meta` and `lower-ccpp-utils` are standalone, special-purpose passes — neither
appears in `ccpp_dsl.py`'s `_build_pipeline` or the example pass lists below, since they
serve separate tools/consumers rather than the main XML/Python-frontend → Fortran flow.

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
| `lifecycle_cap.py` | The `_ccpp_physics_initialize`/`_finalize`/`_timestep_initial`/`_timestep_final` lifecycle dispatcher subroutines |
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
isn't possible until that state actually becomes durable IR. That's tracked
as its own deferred sub-plan, Phase 7 ("full IR unification"), in the
refactor plan — not scheduled, but with a concrete 4-stage execution plan
recorded there if it's ever picked up.

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
| `ccpp.py` | Suite-structure ops (`SuiteOp`, `GroupOp`, `SchemeOp`, `SubcycleOp`), metadata table ops (`TablePropertiesOp`, `ArgumentTableOp`, `ArgumentOp`), kind ops (`KindOp`, `KindsOp`), `CcppHandleOp` (the host's `ccpp_t` variable, for multi-instance support), and `ResolvedArgOp`/`ArgSourceKind` (durable per-argument source resolution, built by `run_dispatch.py`) |

### ModuleVarOp type representation

`ModuleVarOp` represents a module-level variable declaration. Its type is stored
as four structured attributes rather than a pre-rendered Fortran string:

| Attribute | Required | Example |
|-----------|----------|---------|
| `base_type` | yes | `"real"`, `"integer"`, `"character"`, `"logical"`, `"type"` |
| `kind` | no | `"kind_phys"`, `"kind_dyn"`, `"512"` (char length) |
| `ddt_name` | no | `"vmr_type"` (when `base_type == "type"`) |
| `ftn_attrs` | no | `"target"`, `"pointer"` |

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

---

## Linting

```bash
ruff check xdsl_ccpp/
ruff format xdsl_ccpp/
```
