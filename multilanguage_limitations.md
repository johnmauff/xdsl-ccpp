# C++ Host → Fortran Scheme: Known Limitations

This document records known limitations of the chost cap generation mode
(activated via `language = c++` in host `.meta` files) as of the current
implementation.  See
[`multilanguage_plan.md`](multilanguage_plan.md) for design background and
[`README.md`](README.md) for usage instructions.

---

## 1. Array Layout — Column-Major Required

All array arguments passed through the chost interface must be laid out in
**column-major (Fortran) order**: the column index must vary fastest in memory.

A C++ `double theta[nz][ncol]` has the same in-memory layout as Fortran
`theta(ncol, nz)` and is correct.  The natural C++ layout `double
theta[ncol][nz]`, indexed as `theta[col][lev]`, gives the transposed layout and
produces silently wrong physics results.

**Correct layouts:**

```cpp
// Flat allocation — column-major indexing
std::vector<double> theta(ncol * nz);
double val = theta[col + ncol * lev];   // correct: col varies fastest

// Kokkos — LayoutLeft is column-major
Kokkos::View<double**, Kokkos::LayoutLeft> theta("theta", ncol, nz);
```

**Incorrect layout (silently wrong):**

```cpp
std::vector<double> theta(ncol * nz);
double val = theta[lev * ncol + col];   // wrong: lev varies fastest
```

**Potential resolution:** Generate a row-major variant of the cap header that
internally transposes arguments, or add an `array_layout = row_major` option on
the host `.meta` table (see `multilanguage_plan.md` for the existing design).
The Fortran RESHAPE approach is CPU-only; a GPU-resident transpose would require
device-side kernels.

---

## 2. GPU Memory Management

The chost cap is a CPU BIND(C) wrapper.  When physics schemes run on a GPU, the
C++ host is responsible for ensuring arrays are in the correct device memory
space before calling the cap.  The generated code provides no help with this.

Specific interoperability gaps:

- **Kokkos + Fortran OpenACC:** Kokkos device allocations (`CudaSpace`) are
  invisible to the OpenACC runtime.  The host must either use CUDA Unified
  Memory (`CudaUVMSpace`) or call `acc_map_data` to register already-placed
  device pointers with the OpenACC runtime before calling the cap.
- **OpenMP target host + Fortran OpenMP target scheme:** Each side maintains its
  own target-region mapper; there is no automatic sharing of device pointers
  across a BIND(C) call boundary.
- **CUDA Unified Memory:** Works transparently but at the cost of uncontrolled
  page-fault overhead on first access from each side.

**Potential resolution:** An optional `--directive` mode for the chost cap that
emits `!$acc host_data use_device(...)` (OpenACC) or `!$omp target data
use_device_ptr(...)` (OpenMP) directives to hand already-placed device pointers
through the BIND(C) boundary to the inner Fortran scheme.  The C++ caller would
remain responsible for placing data on the device before the call.

---

## 3. ~~Fixed Precision — Always `double`~~ *(Resolved)*

The chost cap now correctly maps real arguments to `float`/`float*` (C++ header)
and `real(c_float)` (Fortran wrapper) when the scheme's real kind resolves to
`REAL32`, and to `double`/`double*` / `real(c_double)` for `REAL64` (the default
for `kind_phys`).  The kind mapping is read from the `ccpp.kinds` IR ops
inserted by the `generate-meta-kinds` pass, so any `--kind-map` override (e.g.
`kind_phys:REAL32`) is honoured automatically.

---

## 4. ~~Partial DDT Support~~ *(Resolved)*

Basic DDT flattening is implemented and tested: scheme arguments whose type is a
DDT with scalar-integer and real-array members (e.g. `vmr_type` in the ddthost
and capgen examples) are automatically expanded into flat C-compatible arguments.
`intent=in`, `intent=inout`, and `intent=out` DDTs are all handled.

**What works:**
- DDT with `integer` scalar members (e.g. `nvmr`)
- DDT with `real(kind_phys)` 1-D and 2-D array members
- `intent=out` DDTs where the scheme allocates the array internally (initialize
  lifecycle)
- `intent=inout` DDTs where the C++ caller owns the flat buffers (run lifecycle)

**All three gaps originally tracked here are now resolved** (the heading above
used to read "Remaining Gaps" — stale, since every sub-item below was already
marked Resolved):

### ~~4a. `logical` DDT members silently dropped~~ *(Resolved)*

`_chost_expand_ddt_arg` now detects `vtype == "logical"` and emits
`logical(c_bool), value, intent(...)` on the Fortran side and `bool` on the
C++ side.  The `c_bool` kind is part of `iso_c_binding`, which is already
imported by the generated cap.

### ~~4b. Nested DDTs not supported~~ *(Resolved)*

`_chost_expand_ddt_arg` now detects when a member's `vtype` is not a primitive
and recursively expands it.  Nested members are accessed via the outer local
using direct path assignment (`outer_local%inner_member%leaf`) so no additional
Fortran local variable is needed.  Arbitrary nesting depth is supported.
Validated by the `examples/nestedddt` example.

### ~~4c. Array-of-DDTs raises a generation-time error~~ *(Resolved)*

Allocatable DDT-array arguments (e.g. `ccpp_constituent_properties_t(:)` from
a scheme's register lifecycle) are now handled automatically.  The chost cap
generator detects these by element type name and:

1. **Excludes them from the C++ function signature** — the C++ caller never
   sees them; they are entirely internal to the cap.
2. **Declares module-level allocatables** (`_chost_dyn_const`, etc.) so the
   data persists after register returns.
3. **Generates a BIND(C) query interface:**
   - `{host}_nconstituents()` returns the total count across all constituent
     arrays registered by all schemes in the suite.
   - `{host}_get_constituent_info(buf, n)` copies the full
     `ccpp_constituent_properties_t` data into a C-compatible
     `CcppConstituentInfo` struct array (fixed-length char fields with null
     termination, `double` reals, `bool` logicals).
4. **Exposes C++ wrappers** in the ergonomics `.hpp`:
   `nconstituents()` and `get_constituents() → std::vector<CcppConstituentInfo>`.

Validated by `examples/constprop/` — a minimal scheme that registers one
constituent property; the C++ driver queries it back and verifies all 12 fields.

---

## 5. Rank > 2 Arrays — Partially Resolved

**chost path (`language = c++` host, no Fortran host module): Resolved,
but the declaration style below was stale — corrected 2026-07-19.**
The chost cap handles rank 3 and higher arrays with an **explicit-shape**
Fortran wrapper declaration (all dimensions named), not the assumed-size form
this section used to describe:

```fortran
real(c_double), target, intent(inout) :: flux(ncol, nz, nbands)
```

(Regenerated the `tiny_r3` fixture under `tests/filecheck/examples/chost_r3/`
directly to confirm — this is the actual current output, not the old
`flux(ncol, nz, *)` form.) The
explicit-shape style was introduced in commit `2fe5473` specifically so the
wrapper's actual argument matches the rank/shape the suite cap's own
assumed-shape `(:,:,:)` dummy expects. The C++ header still emits a flat
pointer (`double*`) regardless of rank, which is correct — C has no
multi-dimensional pointer type for BIND(C) calls — with each higher
dimension's size (e.g. `nbands`) passed by value as
`integer(c_int), value, intent(in)`.

**Plain `--bind-c` path (no `language = c++`, i.e. `generate-ccpp-cap{bind_c=true}`
without the chost layer on top): likely still broken — do not mark Resolved.**
`TinyR3_ccpp_cap.F90`'s `TinyR3_ccpp_physics_run` declares `flux` as flat
assumed-size —

```fortran
real(c_double), intent(inout) :: flux(*)
```

— and forwards it directly as the actual argument to
`tiny_r3_suite_suite_physics`'s dummy, which is assumed-shape rank 3:

```fortran
real(kind=kind_phys), target, intent(inout) :: flux(:, :, :)
```

Under standard Fortran rules, an assumed-shape dummy requires the actual
argument to genuinely be an array of matching rank carrying a descriptor —
an assumed-size actual only participates in sequence association when the
callee's own dummy is itself explicit-shape or assumed-size, never
assumed-shape. Passing a rank-1 assumed-size actual to a rank-3 assumed-shape
dummy, under the explicit interface this generator always produces (via
`use <module>, only: <name>`), should be a compile-time rank-mismatch error in
any standards-conforming compiler. **Not verified against an actual compiler**
(none available in the environment this was investigated in, 2026-07-19) —
this is a probable bug based on the language rules, not a confirmed one; flag
for someone with a Fortran compiler to check before either fixing or
re-closing this.

The golden FileCheck test for this case
(`tests/filecheck/examples/end_to_end/chost-r3-ftn.mlir`) is currently
`XFAIL`ed for exactly this reason — see that file's own header comment for the
fuller history (the assumed-size→explicit-shape change in `2fe5473` landed
without updating either this test or this doc section, which is what left
both of the above out of sync until now).

---

## 6. Thread Safety — CCPP Suite State

The generated suite cap stores per-suite state in a Fortran module-level
variable (`ccpp_suite_state`).  Calling the chost cap concurrently from multiple
C++ threads will produce a data race on that module variable.

This is safe for single-threaded C++ drivers (the current kessler example) but
would be a correctness issue for threaded host models that call physics from
multiple threads simultaneously.

**Potential resolution:** Either (a) protect suite state with a Fortran critical
section, or (b) require the C++ caller to serialize physics calls, or (c) use
the existing `--num-instances N` multi-instance path to give each thread its own
state slot.

---

## 7. ~~No C++ Ergonomics Layer~~ *(Resolved)*

A `<HostName>_chost.hpp` header is now generated alongside
`<HostName>_ccpp_chost_cap.h`.  It provides:

- A `Status` struct with `int code`, `std::string message`, and `bool ok()`.
- Per-lifecycle named arg structs (e.g. `RunArgs`) using C++20 designated
  initializers for readable call sites.  `errmsg`, `errflg`, and `scheme_name`
  are excluded — allocated internally and never exposed.
- `inline` free functions inside `namespace <HostName>_chost`.

```cpp
#include "Kessler_chost.hpp"

auto s = Kessler_chost::run({
    .ncol=100, .col_start=1, .col_end=50, .nz=64,
    .dt=0.1, .lyr_surf=1, .lyr_toa=64,
    .cpair=cpair_ptr, .exner=exner_ptr,
    .theta=theta_ptr, .precl=precl_ptr
});
if (!s.ok()) { /* s.message */ }
```

The wrapper is pure C++ with no additional Fortran code and is emitted as
part of the `cpp_header` target output.

---

## 8. ~~Column Chunking~~ *(Resolved)*

The chost `run` subroutine now accepts `col_start` and `col_end` as explicit
`integer(c_int), value, intent(in)` parameters (mirroring the Fortran driver
interface).  The arrays remain dimensioned by `ncol` (the full column extent of
the allocation), and the Fortran wrapper passes `col_start` and `col_end`
directly to the suite cap so the scheme sees only the active column range.

```fortran
! C++ caller controls the active chunk:
call Kessler_chost_physics_run(ncol_full, col_start, col_end, nz, dt, ..., theta, ...)
```

Because array columns are non-contiguous in column-major memory, the C++ caller
must NOT pre-extract a chunk by pointer arithmetic; passing `col_start`/`col_end`
is the correct approach.

---

## ~~9. `character(len=N)` Fixed-Length Scalar Arguments~~ *(Resolved)*

Fixed-length character scalar arguments (`character(len=N)`) are now fully
supported in the chost cap.  The mapping is:

- **C++ side:** `const char*` (intent=in) or `char*` (intent=out/inout) — a
  null-terminated C string.
- **C header:** same pointer types, emitted into the BIND(C) prototype.
- **Fortran side:** `character(kind=c_char, len=1), intent(...) :: arg(*)` (the
  required BIND(C) form), plus a local `character(len=N) :: arg_f` buffer.
- **C→F copy-in** (intent=in/inout): scans the C string up to the first
  `c_null_char`, filling `arg_f` one character at a time.
- **F→C copy-out** (intent=out/inout): copies `len_trim(arg_f)` characters back
  and appends a null terminator.

The generator raises a clear `ValueError` for unsupported forms:
- `character(len=*)` assumed-length scalars — BIND(C) does not permit them;
  change the scheme to use a fixed `character(len=N)`.
- Character arrays (e.g. `character(len=N) :: arr(M)`) — not supported in the
  C-interoperable interface.

Validated by `examples/chararg/` — a minimal scheme with a `character(len=32),
intent(in)` label arg; the C++ driver passes a non-empty label and verifies the
3× temperature scaling, then verifies an empty label returns an error.

---

## ~~10. Runtime-Determined Dimensions~~ *(Resolved)*

Rank-3 array arguments whose third dimension is the constituent count (`ncnst`)
are now fully supported.  The generator:

1. **Extracts `dim_n3`** — for rank-3 real arrays, scans `local_to_dim_names` for
   a dimension that is neither horizontal nor vertical and looks up the
   corresponding host variable.  For `q(horizontal_loop_extent,
   vertical_layer_dimension, number_of_ccpp_constituents)` this resolves to the
   host variable with standard name `number_of_ccpp_constituents` (e.g. `ncnst`).

2. **Marks the scalar** — the integer argument that provides `dim_n3` is flagged
   `is_dim_scalar=True`, which places it in the `State` constructor parameter list
   alongside `ncol` and `nz`.

3. **Sizes the allocation** — `State::allocate()` assigns
   `ncol × nz × ncnst` elements for rank-3 arrays (vs. `ncol × nz` for rank-2).

4. **Passes `ncnst` automatically** — the `run(State&, col_start, col_end)`
   overload extracts `s.ncnst` and forwards it to the BIND(C) call.

The two-phase usage pattern in the C++ driver is:

```cpp
// Phase 1 — register; ncnst is unknown before this call
CA::do_register();
int ncnst = CA::nconstituents();   // query runtime value from gap-4c interface

// Phase 2 — allocate with runtime ncnst, then run
CA::initialize();
CA::State st{NCOL, NZ, ncnst};
st.allocate();                     // sizes _q as NCOL * NZ * ncnst
// ... fill st.q ...
CA::timestep_initial();
CA::run(st, 1, NCOL);              // passes st.ncnst automatically
CA::timestep_final();
CA::finalize();
```

Validated by `examples/constadv/` — a minimal scheme that registers 2 constituents
in `register` and scales `q(ncol, nz, ncnst)` by 2× in `run`.  The C++ driver
queries `ncnst=2` after register, constructs `State{NCOL, NZ, 2}`, and verifies
all 24 elements equal 2.0 after the run.

---

## Priority Summary

| # | Limitation | Blocks real use? | Effort to fix |
|---|-----------|-----------------|---------------|
| ~~3~~ | ~~Fixed `double` precision~~ | *(Resolved)* | *(Done)* |
| ~~4a~~ | ~~DDT — `logical` members silently dropped~~ | *(Resolved)* | *(Done)* |
| ~~4b~~ | ~~DDT — nested DDTs~~ | *(Resolved)* | *(Done)* |
| ~~4c~~ | ~~DDT — array-of-DDTs / allocatable DDT args~~ | *(Resolved)* | *(Done)* |
| ~~9~~ | ~~`character(len=N)` scalar args~~ | *(Resolved)* | *(Done)* |
| ~~10~~ | ~~Runtime-determined dimensions (`ncnst`)~~ | *(Resolved)* | *(Done)* |
| 2 | GPU memory management | Yes, for GPU builds | Medium–High |
| 1 | Column-major layout | Subtle bugs if overlooked | Medium |
| 5 | Rank > 2 arrays — plain `--bind-c` path only (chost path *is* resolved) | Likely, if the rank mismatch is real — unverified, no compiler available | Low (probably a declaration-style fix, once confirmed) |
| 6 | Thread safety | Only for concurrent callers | Low–Medium |
| ~~7~~ | ~~No C++ ergonomics~~ | *(Resolved)* | *(Done)* |
| ~~8~~ | ~~Column chunking~~ | *(Resolved)* | *(Done)* |
