# CCPP Tool Comparison: prebuild vs capgen vs capgen-ng vs xdsl-ccpp

---

## Tool Overview

| Tool | Status | Metadata format | Primary purpose |
|---|---|---|---|
| `ccpp_prebuild` | Production, legacy | Old embedded-comment format | Cap generation + build integration |
| `ccpp_capgen` | Production, current | New `.meta` file format | Cap generation + Fortran validation |
| `ccpp_capgen-ng` | In development | New `.meta` file format | Unified successor to both above |
| `xdsl-ccpp` | Prototype | New `.meta` file format | MLIR-based cap generation + GPU |

**Note:** `ccpp_prebuild` and `ccpp_capgen` are two separate tools in the same
repository serving overlapping purposes for different metadata formats.
`ccpp_capgen-ng` unifies them. Capabilities marked `prebuild only` or
`capgen only` exist in one tool but not yet the other — `ccpp_capgen-ng`
is designed to close these gaps.

---

## Capability Comparison

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
| Host variable matching | ✅ | ✅ | ✅ | ✅ (partial) |
| Variable compatibility validation | ✅ | ✅ | ✅ | ❌ |
| Unit conversion | ✅ | ✅ | ✅ | ❌ |
| Optional argument handling | ✅ | Partial | ✅ | ❌ |
| Chunked data layout | ✅ | ❌ | ✅ | ❌ |
| **Code correctness** | | | | |
| Fortran source cross-validation | ❌ | ✅ | ✅ | ❌ |
| Multi-instance support | ❌ | ❌ | ✅ | ❌ |
| **Build & tooling** | | | | |
| Build system integration (CMake) | ✅ | ✅ | ✅ | ❌ |
| Documentation generation | ✅ HTML/LaTeX | ✅ datatable.xml | ✅ | ❌ |
| `ccpp_track_variables` utility | ✅ | ❌ | ✅ | ❌ |
| **Testing** | | | | |
| Compiled Fortran execution tests | ✅ | ✅ | ✅ | ❌ FileCheck only |
| Unit test depth | Moderate | Moderate | 1300+ tests | FileCheck only |
| **Host model integration** | | | | |
| CCPP-SCM | ✅ | ✅ | ✅ | ❌ helloworld only |
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

---

## Key Observations

### ccpp_prebuild vs ccpp_capgen
These tools have complementary strengths. `ccpp_prebuild` handles unit conversion,
optional args, and chunked data well — all tested end-to-end. `ccpp_capgen` adds
Fortran source cross-validation and nested suites but does not yet cover chunked
data or optional args. Neither is a complete replacement for the other, which is
exactly why `ccpp_capgen-ng` exists.

### ccpp_capgen-ng
Closes all the gaps between prebuild and capgen by unifying them into a single
tool with the new metadata format. Adds multi-instance support. Has the deepest
test coverage (1300+). Does not add GPU support and cannot practically do so
without an architectural rethink — it is a text-templating Fortran generator
throughout.

### xdsl-ccpp functional gap vs capgen-ng
The most significant missing capabilities are:
1. Unit conversion
2. Variable compatibility validation (type/kind/dims/intent)
3. Optional argument handling
4. Chunked data layout
5. Build system integration
6. Host model integration beyond helloworld

Rough estimate to close parity: ~30–40 weeks of focused work.

### xdsl-ccpp unique advantages
No other CCPP tool has GPU support. xdsl-ccpp generates correct `!$acc data` and
`!$omp target data` directives at the right level (`ccpp_physics_run`) using
actual host module variable names and array section notation. The full 2×2
host/scheme memory space matrix is handled automatically from `.meta` annotations.

The MLIR architecture also enables future capabilities that none of the other
tools can reach: multi-language host models (C++, Python), additional GPU
backends, and composable transformation passes.

---

## Recommended Use Today

| Use case | Recommended tool |
|---|---|
| Production CPU physics — old metadata format | ccpp_prebuild |
| Production CPU physics — new metadata format | ccpp_capgen |
| Next-gen CPU physics development | ccpp_capgen-ng |
| GPU-enabled physics development | xdsl-ccpp |
| Research into multi-language host models | xdsl-ccpp |
