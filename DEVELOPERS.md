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
| `generate-kinds` | Emit `ccpp_kinds.F90` |
| `generate-gpu-ccpp-cap` | Insert OpenACC/OpenMP data directives at the ccpp_cap level |
| `generate-gpu-data` | Insert OpenACC/OpenMP directives at the suite_cap level for unmatched device variables |
| `strip-ccpp` | Remove CCPP dialect ops, leaving standard MLIR |

Pass options are set with `{key=value}` syntax, e.g. `generate-ccpp-cap{bind_c=true}`.

---

## Code Organization

### Transformation passes

The transformation pipeline lives under `xdsl_ccpp/transforms/`:

| Module | Pass name | Role |
|--------|-----------|------|
| `ccpp_cap.py` | `generate-ccpp-cap` | Host-facing cap (`ccpp_physics_initialize`, `ccpp_physics_run`, etc.) |
| `suite_cap.py` | `generate-suite-cap` | Per-suite subroutines (`*_suite_physics`, lifecycle init/finalize) |
| `host_var_match_pass.py` | `generate-host-match` | Annotates scheme arg ops with matching host variable names, kinds, and units |
| `gpu_ccpp_cap_pass.py` | `generate-gpu-ccpp-cap` | Inserts OpenACC/OpenMP data directives at the ccpp_cap level |
| `gpu_data_pass.py` | `generate-gpu-data` | Inserts OpenACC/OpenMP directives at the suite_cap level for unmatched device variables |

Shared utilities live in `xdsl_ccpp/transforms/util/`:

| Module | Contents |
|--------|----------|
| `ir_utils.py` | `find_ccpp_module(ops)` — locates the named `@ccpp` ModuleOp from an op list |
| `ccpp_descriptors.py` | `BuildMetaDataDescriptions` — walks CCPP metadata tables into Python descriptor objects |

When writing a new pass that needs the CCPP metadata module, import
`find_ccpp_module` from `xdsl_ccpp.transforms.util.ir_utils`.

### Dialects

Custom MLIR dialects are defined under `xdsl_ccpp/dialects/`:

| Module | Contents |
|--------|----------|
| `ccpp_utils.py` | Core CCPP ops: `ModuleVarOp`, `HostVarRefOp`, `UnitConvertOp`, `RowMajorConvertOp`, and related ops |
| `ccpp_cap_dialect.py` | Cap-level ops used by `generate-ccpp-cap` |

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
