# Multi-Language Support Plan: C++/Kokkos Host + Fortran Schemes

## Goal

Enable a C++/Kokkos host model to drive CCPP Fortran physics schemes through
xdsl-ccpp-generated caps, without requiring the cap generator to know anything
about Kokkos internals.

## Design Decisions

**Interface contract.** The generated BIND(C) cap accepts raw pointers plus
explicit dimension arguments. The C++ host is responsible for satisfying the
calling convention before invoking the cap. CCPP defines the contract; the
host satisfies it.

**Array layout.** Declared in the host `.meta` file as `array_layout =
column_major | row_major` on the table-properties block. Defaults to
`column_major` (all current Fortran hosts). When `row_major` is declared, the
generated Fortran BIND(C) cap performs a RESHAPE using standard Fortran
intrinsics before passing arrays to schemes. The cap generator never imports
Kokkos-specific knowledge.

> **GPU limitation.** The Fortran RESHAPE intrinsic operates on host-resident
> (CPU) memory. For GPU-resident arrays, the C++ host should provide data in
> column-major order (e.g. `Kokkos::View<double**, Kokkos::LayoutLeft>`) to
> avoid the RESHAPE entirely — this is the approach used in the Kessler C++
> driver example. If a `row_major` host passes GPU-resident data, the host is
> responsible for performing a device-side transpose before calling the cap.

**GPU data movement.** Out of scope for this plan. If the host uses
GPU-resident Kokkos views, the host is responsible for ensuring data is on the
CPU before calling the BIND(C) interface, or for using the existing
`memory_space = device` + `--directive acc|omp` path for schemes that run on
GPU. The two mechanisms compose independently.

**`active` guard expressions.** The active-condition strings (e.g.
`flag_for_mynn .eq. 1`) are evaluated inside the Fortran cap, so they stay
Fortran for this use case. No change needed for Phase 1.

---

## Phase 1 — Structured `ModuleVarOp.fortran_type` (prerequisite)

**Effort: ~1 week**

### Problem

`ModuleVarOp.fortran_type` stores a pre-rendered Fortran string
(`"real(kind=kind_phys)"`, `"type(vmr_type)"`) as an opaque `StringAttr`. The
Fortran printer emits it verbatim. A C++ header printer has no usable
structure to work from.

### Change

Replace the single `fortran_type` string attribute with three structured
fields on `ModuleVarOp`:

| Field | Type | Example |
|-------|------|---------|
| `base_type` | StringAttr | `"real"`, `"integer"`, `"character"`, `"type"` |
| `kind` | StringAttr (optional) | `"kind_phys"`, `"len=512"` |
| `ddt_name` | StringAttr (optional) | `"vmr_type"` (when base_type = "type") |

**Touch points:**
- All `ModuleVarOp(...)` construction sites in `ccpp_cap.py`
- All `ModuleVarOp(...)` construction sites in `suite_cap.py`
- Fortran printer (`print_ftn.py`): reconstruct the existing string from the
  three fields — behaviour is identical for all existing tests

**Verification:** all 210 existing tests pass unchanged.

---

## Phase 2 — Array Layout Metadata (1–2 days)

### Change

Add `array_layout` as an optional property on host table-properties blocks in
`.meta` files:

```ini
[ccpp-table-properties]
  name = my_host_state
  type = module
  array_layout = row_major    # new; omit or set column_major for Fortran hosts
```

**Pipeline propagation:**

1. **Frontend** (`ccpp_xml.py`, `py_api.py`) — parse `array_layout`; emit as
   a `StringAttr` on the `TablePropertiesOp`.
2. **`host_var_match_pass.py`** — when a scheme arg is matched to a host
   variable whose table has `array_layout = row_major`, annotate the arg op
   with `model_var_array_layout = StringAttr("row_major")`.
3. **Default** — absence of the attribute means `column_major`; no annotation
   is added and no code change is generated.

---

## Phase 3 — BIND(C) Cap Generation (2–3 weeks)

### New CLI flag

```
ccpp_xdsl --interface bindC ...
```

Default is `fortran` (existing behaviour, no change). When `bindC` is set:

- `ccpp_cap.py`'s `_generate_lifecycle_fn` emits subroutines with
  `BIND(C, name='<sym>')` and `use iso_c_binding`.
- `ccpp_kinds.F90` gains ISO_C_BINDING kind aliases.

### Type mapping in the BIND(C) interface

| CCPP type + kind | BIND(C) Fortran type | C/C++ type |
|-----------------|---------------------|------------|
| `real / kind_phys` | `real(c_double)` | `double` |
| `real / kind_dyn` | `real(c_double)` | `double` |
| `integer` | `integer(c_int)` | `int` |
| `logical` | `logical(c_bool)` | `bool` |
| `character` | `character(kind=c_char,len=1), dimension(*)` | `const char*` |

### Array argument convention

Arrays are received as a typed pointer plus explicit dimension arguments:

```fortran
subroutine ccpp_physics_run(suite_name, ncol, nlev, theta, ...) BIND(C)
  use iso_c_binding
  character(kind=c_char, len=1), intent(in) :: suite_name(*)
  integer(c_int), value,         intent(in) :: ncol, nlev
  real(c_double), intent(inout)             :: theta(ncol, nlev)   ! column_major
  ...
```

### Layout conversion (row_major host)

When any matched variable carries `model_var_array_layout = row_major`, the
BIND(C) subroutine receives the array with transposed dimension order and
emits a Fortran RESHAPE before calling the suite subroutine:

```fortran
! received from C++ as row-major (nlev, ncol)
real(c_double), intent(inout) :: theta_c(nlev, ncol)
! local column-major temporary for Fortran schemes
real(kind_phys) :: theta(ncol, nlev)

theta = reshape(theta_c, [ncol, nlev], order=[2,1])
call kessler_suite_suite_physics(..., theta=theta, ...)
! write back for intent=inout or intent=out
theta_c = reshape(theta, [nlev, ncol], order=[2,1])
```

The `model_var_array_layout` annotation on each arg op drives whether the
reshape is emitted — same pattern as unit conversion temporaries today.

### Scalar suite_name / suite_part

The existing `StrCmpOp` and `SetStringOp` IR ops already model the string
logic. The BIND(C) printer maps them to `c_char` arrays with a
null-terminator check.

---

## Phase 4 — C++ Header Generation (1–2 weeks)

### New printer: `xdsl_ccpp/printers/print_cpp_header.py`

Emits two files when `--interface bindC` is set:

**`<host_name>_ccpp_cap.h`**

```cpp
// Generated by xdsl-ccpp. Array arguments are column-major (Fortran order).
// Pass Kokkos::View with LayoutLeft, or transpose before calling.
#pragma once
#include "ccpp_kinds.h"
#ifdef __cplusplus
extern "C" {
#endif

void HelloWorld_ccpp_physics_initialize(
    const char* suite_name,
    int         ncol,
    int         nlev,
    char*       errmsg,
    int*        errflg);

void HelloWorld_ccpp_physics_run(
    const char* suite_name,
    const char* suite_part,
    int         ncol,
    int         nlev,
    double*     theta,       // (ncol, nlev) column-major
    char*       errmsg,
    int*        errflg);

#ifdef __cplusplus
}
#endif
```

**`ccpp_kinds.h`**

```cpp
// Kind aliases — kept consistent with ccpp_kinds.F90
#pragma once
typedef double  kind_phys_t;
typedef double  kind_dyn_t;
typedef int     kind_int_t;
```

### Type mapping (same table as Phase 3, C++ column)

The printer walks the same typed `base_type` + `kind` attributes introduced in
Phase 1 to generate the C++ type strings.

---

## Phase 5 — CMake Integration (a few days)

`xdsl_ccpp_generate()` gains an optional `INTERFACE` keyword:

```cmake
xdsl_ccpp_generate(
    HOST_NAME   "Kessler"
    OUTPUT_ROOT "${CMAKE_CURRENT_BINARY_DIR}/caps"
    TARGET_VAR  KESSLER_CAPS
    INTERFACE   bindC           # new; emits BIND(C) Fortran + C++ header
    SUITES      kessler_suite.xml
    ...
)
```

When `INTERFACE bindC` is set, `TARGET_VAR` includes the `.h` files alongside
the `.F90` files.

---

## Phase 6 — Kessler C++ Driver Example (1–2 weeks)

### New file: `examples/kessler/driver_kessler_kokkos.cpp`

- Uses `Kokkos::View<double**, Kokkos::LayoutLeft>` (column-major — satisfies
  the cap contract without RESHAPE overhead)
- Calls `Kessler_ccpp_physics_initialize` / `_run` via the generated header
- Prints the same output columns as `driver_kessler.F90`
- CMake target in `examples/kessler/CMakeLists.txt` (Kokkos optional;
  guarded by `find_package(Kokkos)`)

### Numerical validation

Compare output against `driver_kessler.F90` results bit-for-bit. Validates
that the BIND(C) interface and any RESHAPE logic produce identical results.

---

## Phase 7 — Testing (1 week)

| Test | Type | Location | Status |
|------|------|----------|--------|
| BIND(C) Fortran output | FileCheck | `tests/filecheck/examples/end_to_end/kessler-bindC.mlir` | ✅ Done |
| C++ header output | FileCheck | `tests/filecheck/examples/end_to_end/kessler-cpp-header.mlir` | ✅ Done |
| `array_layout` round-trip through IR | FileCheck | `tests/filecheck/examples/frontend/array-layout-py.mlir`, `tests/filecheck/examples/completed_ir/array-layout-py.mlir` | ✅ Done |
| RESHAPE generation for row_major | FileCheck | `tests/filecheck/examples/end_to_end/array-layout-reshape.mlir` | ✅ Done |
| Numerical parity | Makefile / CTest | `examples/kessler/` | ❌ Not started |

---

## Effort Summary

| Phase | Description | Estimate |
|-------|-------------|----------|
| 1 | Structured `ModuleVarOp` type attributes | 1 week |
| 2 | `array_layout` metadata + propagation | 1–2 days |
| 3 | BIND(C) cap generation | 2–3 weeks |
| 4 | C++ header printer | 1–2 weeks |
| 5 | CMake integration | 2–3 days |
| 6 | Kessler C++ driver example | 1–2 weeks |
| 7 | Testing | 1 week |
| **Total** | | **6–9 weeks** |

---

## Fortran Host → C++ Scheme Implementations

This direction is orthogonal to the phases above (which cover C++ host → Fortran schemes). It allows a standard Fortran host model to call C++ scheme implementations through a CCPP-generated suite cap.

**Status: cap generator implemented; no compiled end-to-end test yet.**

### Metadata

A scheme's `.meta` table-properties block carries an optional `language` key:

```ini
[ccpp-table-properties]
  name = my_cxx_scheme
  type = scheme
  language = c++
```

Valid values: `fortran` (default, attribute omitted from IR) and `c++`.

### IR propagation

The `language = "c++"` attribute flows through the pipeline:

1. **Frontend** (`ccpp_xml.py`, `py_api.py`) — emits `{language = "c++"}` on the scheme `TablePropertiesOp`; Fortran schemes carry no attribute.
2. **`generate-suite-cap`** (`suite_cap.py`) — stamps `language`, `arg_names`, and `arg_intents` onto the external `func.FuncOp` declaration for the C++ entry point.
3. **Fortran printer** (`print_ftn.py`) — C++ FuncOps are excluded from `use <module>` statements; instead, a `BIND(C)` interface block is emitted.

### Generated suite cap output

```fortran
module tiny_suite_cap
  use ccpp_kinds
  use iso_c_binding
  use tiny_fortran_scheme, only: tiny_fortran_scheme_run   ! Fortran scheme: normal USE

  interface                                                 ! C++ scheme: interface block
    subroutine tiny_cxx_scheme_run(ncol, temp, errmsg, errflg) &
        BIND(C, name='tiny_cxx_scheme_run')
      use iso_c_binding
      integer(c_int), value, intent(in)      :: ncol
      real(c_double), intent(inout)          :: temp(*)
      character(kind=c_char, len=1), intent(out) :: errmsg(*)
      integer(c_int), intent(out)            :: errflg
    end subroutine tiny_cxx_scheme_run
  end interface
  ...
  call tiny_fortran_scheme_run(ncol, temp, errmsg, errflg)
  call tiny_cxx_scheme_run(ncol, temp, errmsg, errflg)     ! called like any Fortran sub
```

### FileCheck tests

| Test | What it verifies |
|------|-----------------|
| `tests/filecheck/examples/frontend/language-py.mlir` | `language = "c++"` on `TablePropertiesOp` in raw IR |
| `tests/filecheck/examples/completed_ir/language-py.mlir` | `module`, `language`, `arg_names`, `arg_intents` on `func.FuncOp` after `generate-suite-cap` |
| `tests/filecheck/examples/end_to_end/language-cxx-interface-py.mlir` | Full Fortran output: `use iso_c_binding`, no `use tiny_cxx_scheme`, correct `BIND(C)` interface block, calls to both schemes |

### What remains

- A C++ scheme implementation with `extern "C"` entry points to compile and link against.
- A compiled end-to-end test (Makefile or CTest) verifying ABI correctness and numerical results.

---

## What This Plan Deliberately Excludes

- **Kokkos-specific code in the cap generator** — the cap is pure Fortran +
  standard ISO_C_BINDING. The host uses whatever Kokkos version and layout
  it chooses.
- **GPU data movement at the BIND(C) boundary** — if schemes run on GPU, the
  existing `memory_space` + `--directive acc|omp` path handles it. The two
  features compose without coupling.
- **C++ host with C++ Kokkos schemes** — a separate effort; requires a full
  C++ cap printer and is not addressed here.
- **Fortran host with C++ schemes (compiled test)** — the cap generator now
  emits correct `BIND(C)` interface blocks (see section above), but a compiled
  end-to-end test with an actual C++ scheme implementation has not been written.
- **`active` guard expression translation** — active conditions are evaluated
  inside the Fortran cap and stay Fortran for this use case.
