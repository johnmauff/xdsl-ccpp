# C++ Host → Fortran Scheme: Known Limitations

This document records known limitations of the `--explicit-args` chost cap
generation mode as of the current implementation.  See
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

## 4. No DDT (Derived Data Type) Support

Schemes whose argument lists include a Fortran derived data type (DDT) — such as
a physics state struct, a tracer container, or `ccpp_t` — cannot be expressed in
a C-compatible interface.  The chost generator will either skip those arguments
or produce an incorrect declaration.

**Potential resolution:** Restrict chost use to schemes that have no DDT
arguments, and emit a clear error at generation time if a DDT is encountered.
Full DDT support would require either (a) flattening the DDT members into
individual C arguments, or (b) generating a C `struct` that mirrors the Fortran
layout — both are non-trivial.

---

## 5. ~~Rank > 2 Arrays~~ *(Resolved)*

The chost cap now handles rank 3 and higher arrays.  The Fortran wrapper declares
them with the first two dimensions named (`ncol`, `nz`) and an assumed-size last
dimension (`*`), e.g.:

```fortran
real(c_double), target, intent(inout) :: flux(ncol, nz, *)
```

The C++ header always emits a flat pointer (`double*`) regardless of rank, which
is correct — C has no multi-dimensional pointer type for BIND(C) calls.  The
third-dimension size integer (e.g. `nbands`) is automatically included in the
chost signature as a `integer(c_int), value, intent(in)` argument so the caller
can communicate the size.

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

## 7. No C++ Ergonomics Layer

The generated interface is raw `extern "C"` with Fortran-style error reporting:
`char* errmsg` (null-terminated string buffer) and `int* errflg` (non-zero on
error).  C++ callers must manually check `errflg` after every lifecycle call.

There is no generated C++ wrapper class providing:
- RAII lifecycle management (constructor calls initialize; destructor calls
  finalize)
- Exception-on-error translation (`errflg != 0` → `std::runtime_error`)
- `std::string` errmsg extraction
- Named parameter / builder pattern for the many-argument `run` call

**Potential resolution:** Generate an optional `<HostName>_chost.hpp` thin C++
wrapper header that wraps the `extern "C"` calls in a class with the above
ergonomics.  The wrapper would be pure C++ with no additional Fortran code.

---

## 8. Column Chunking

The chost cap passes all `ncol` columns in a single call.  A C++ host that
wants to process columns in sub-chunks (e.g. GPU thread blocks, cache tiles) can
pass a smaller `ncol` and a base pointer into a larger allocation — but only if
the underlying buffer is contiguous for that slice.  There is no stride argument,
and non-contiguous sub-views are not supported.

**Potential resolution:** Accept an optional leading-dimension argument
(`ldim`) to allow strided column slices.  This would require changes to both the
Fortran wrapper (use explicit leading dimension in array declarations) and the
C++ header.

---

## Priority Summary

| # | Limitation | Blocks real use? | Effort to fix |
|---|-----------|-----------------|---------------|
| ~~3~~ | ~~Fixed `double` precision~~ | *(Resolved)* | *(Done)* |
| 4 | No DDT support | Yes, for DDT-heavy schemes | High |
| 2 | GPU memory management | Yes, for GPU builds | Medium–High |
| 1 | Column-major layout | Subtle bugs if overlooked | Medium |
| ~~5~~ | ~~Rank > 2 arrays~~ | *(Resolved)* | *(Done)* |
| 6 | Thread safety | Only for concurrent callers | Low–Medium |
| 7 | No C++ ergonomics | Usability only | Medium |
| 8 | Column chunking | Usability / performance | Medium |
