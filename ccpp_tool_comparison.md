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
| Host variable matching | ✅ | ✅ | ✅ | Partial† |
| Variable compatibility validation | ✅ | ✅ | ✅ | Partial‡ |
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
| Compiled Fortran execution tests | ✅ | ✅ | ✅ | Partial§ |
| Unit test depth | Moderate | Moderate | 1300+ tests | 19 pytest + 1 Fortran |
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

## Notes

† **Host variable matching (Partial):** The matching step — finding which host
model variable corresponds to each scheme argument by standard name — is
functionally working via `HostVariableMatchPass`. It is marked Partial because
of the following remaining gaps:

*What now works:*
- Flat module variables (helloworld, fully tested with Fortran compilation)
- DDT member variables (e.g. `physics_state%temperature`) — indexing implemented
- Nine CCPP metadata attributes parsed and stored in the IR: `allocatable`,
  `advected`, `constituent`, `protected`, `state_variable`, `default_value`,
  `diagnostic_name`, `diagnostic_name_fixed`, `active`
- Framework-managed variables (`allocatable`, `advected`, `constituent`) skip
  the host match requirement correctly
- Exercised against capgen, advection, and ddthost examples from ccpp-framework
  with all warnings eliminated

*Still missing:*
- Interstitial variables (produced by `_init`, consumed by `_run`) — requires
  new framework support for variables that flow between lifecycle phases
- DDT type instances (e.g. a scheme requesting a whole DDT as a single argument)
- CCPP promotion variables (`promote_this_variable_to_suite` etc.)
- Allocation code generation for `allocatable`/`advected`/`constituent` variables
  — the match is skipped but the framework doesn't yet allocate storage
- `ccpp_cap.py` contains a parallel independent matching implementation not yet
  unified with `HostVariableMatchPass`

This is distinct from the "Variable compatibility validation" row, which covers
type/kind/dims/intent checking after a match is found.

§ **Compiled Fortran execution tests (Partial):** One end-to-end test exists:
the HelloWorld example compiles with gfortran inside a Docker container, links
against real CCPP scheme implementations from ccpp-framework, runs, and verifies
correct physics results (`compare_temp()` passes). Three calling-convention bugs
were found and fixed during this process. No tests yet for capgen, advection,
var_compatibility, or ddthost scenarios. A Docker-based Makefile
(`examples/helloworld/Makefile`) and pytest unit test suite (`tests/unit/`)
provide the testing infrastructure for future expansion.

‡ **Variable compatibility validation (Partial):** Four checks are implemented
in `HostVariableMatchPass`: type mismatch (hard error), dimension rank mismatch
(hard error), intent mismatch covering all four incompatible access combinations
(hard error with specific messages), and kind mismatch (warning + IR annotation
for the future unit conversion pass). Not yet covered: dimension name
compatibility beyond the `horizontal_loop_extent` → `horizontal_dimension`
framework substitution, unit compatibility checking, and DDT member matching.

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

### xdsl-ccpp correctness fixes made during development
Three calling-convention bugs were found and fixed during Fortran compilation
testing — bugs that would have prevented any real CCPP physics from running:
1. **`inout` double-passing** — MLIR's SSA model was splitting `intent(inout)`
   arguments into separate in/out actual arguments. Fixed to pass once by
   reference, matching standard Fortran/CCPP convention.
2. **Module naming inconsistency** — the generated dispatcher module used
   snake_case (`hello_world_ccpp_cap`) while subroutine names used CamelCase
   (`HelloWorld_ccpp_physics_run`). Fixed to use CamelCase throughout.
3. **Missing scheme USE statements** — the suite cap called scheme subroutines
   as external procedures without `use scheme_module` statements, causing link
   failures against real CCPP scheme implementations. Fixed to generate correct
   USE statements for each scheme's module.

These were only caught by compiling and running real Fortran — not by FileCheck.

### xdsl-ccpp functional gap vs capgen-ng
The most significant missing capabilities are:
1. Unit conversion
2. Optional argument handling
3. Chunked data layout
4. Build system integration
5. Host model integration beyond helloworld

Variable compatibility validation is now Partial‡ — type, kind, dimension rank,
and intent checks are implemented.

Rough estimate to close parity: ~25–35 weeks of focused work.

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
