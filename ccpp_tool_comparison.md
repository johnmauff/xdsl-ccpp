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
| Unit test depth | Moderate | Moderate | 1300+ tests | 19 pytest + 4 Makefiles |
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
- Allocation code generation for `advected` real arrays — suite cap declares
  module-level `allocatable`, lazily allocates in `_suite_physics` with
  correct dimensions and `default_value` initialization, safely deallocates
  in `_timestep_final`. Verified with Fortran compilation in Docker.
- Case-insensitive standard name and dimension name matching
- Interstitial variable detection: variables produced by `_init` and consumed
  by `_run`, or passed between `_run` calls, marked `is_interstitial`
- Module-level allocatable declarations for array interstitials; interstitial
  arrays allocated in `_init`, persisted across timesteps (not freed in
  `_timestep_final`), freed only at `_finalize`
- **Variable promotion** — scheme 1D, host 2D: suite cap generates a
  `do vertical_layer_index = 1, lev` loop with `RankReducingSliceOp`
- **DDT type imports** — `use make_ddt, only: vmr_type` etc. auto-generated
- **`ccpp_physics_suite_variables` full implementation** — per-suite variable
  lists (input, output, required) computed by direct IR scan
- HOST-type table variables correctly excluded from USE statement generation
  (they are caller-provided interfaces, not Fortran modules)
- DDT instances accessed through HOST-type tables treated as block args
- Standard_name aliases in suite cap — two scheme args with different local
  names but the same standard_name (e.g. `temp` and `temp_layer`) share a
  single block arg, preventing host aliasing with non-contiguous array sections
- DDT member subscript standard_name resolution (e.g. `index_of_water_vapor...`
  → local variable name `index_qv`)
- Framework arrays sectioned to `(col_start:col_end)` in physics calls
- `ccpp_info_t` pattern for ddthost: lifecycle/run functions accept a single
  `type(ccpp_info_t), intent(inout)` argument bundling errmsg/errflg/col_start/col_end
- timestep_initial/final correctly propagate errmsg/errflg to the top-level cap
- `physics_register` stub generated (required by some host drivers)
- `ccpp_physics_suite_part_list` returns actual XML group names

*Still missing / known gaps:*
- **Per-group physics dispatch** (see Architectural Gaps below) — currently all
  XML groups in a suite dispatch to the same combined `_suite_physics` function,
  which runs ALL schemes for every group call. This is semantically incorrect
  for multi-group suites and causes physics correctness failures.
- `allocatable` code generation for non-real types (`ccpp_constituent_properties_t`)
- Integer `is_interstitial` scalars handled incorrectly (would generate invalid
  allocatable declarations — currently no test case exercises this)
- DDT member `is_interstitial` not validated (potential latent bug if a DDT
  member is marked interstitial but the DDT instance is a block arg)

This is distinct from the "Variable compatibility validation" row, which covers
type/kind/dims/intent checking after a match is found.

§ **Compiled Fortran execution tests (Partial):**
- **helloworld**: compiles, runs, and verifies correct physics results ✅
- **capgen**: compiles, runs, and **passes all correctness checks** (`STOP 0`) ✅
- **ddthost**: compiles, runs, and **passes all correctness checks** ✅
- **advection**: suite caps compile; top-level cap not yet attempted
- Makefiles exist at `examples/helloworld/`, `examples/capgen/`, `examples/ddthost/`

‡ **Variable compatibility validation (Partial):** Four checks are implemented
in `HostVariableMatchPass`: type mismatch (hard error), dimension rank mismatch
(hard error), intent mismatch covering all four incompatible access combinations
(hard error with specific messages), and kind mismatch (warning + IR annotation
for the future unit conversion pass). Not yet covered: dimension name
compatibility beyond the `horizontal_loop_extent` → `horizontal_dimension`
framework substitution, unit compatibility checking, and DDT member matching.

---

## Architectural Gaps in xdsl-ccpp

The following are fundamental architectural issues, not individual bugs:

### 1. Per-group physics dispatch (HIGH PRIORITY)

**Problem:** For a suite with groups `physics1` (schemes A+B) and `physics2`
(schemes C+D), the current top-level cap dispatches BOTH group names to the
same combined `_suite_physics` function that runs ALL schemes (A+B+C+D).
This means each scheme runs twice per timestep, producing wrong physics values.

**Root cause of earlier fix:** We previously attempted per-group suite cap
functions (`_suite_physics1`, `_suite_physics2`) but hit an interstitial variable
problem — variables produced in one group and consumed in another (e.g. `O3`
allocated in `_init` and read in `_run`) are declared at module scope in the
combined suite cap. Splitting the physics function requires careful handling of
which interstitials are alive at each group boundary.

**Required fix:** Generate true per-group suite cap functions where interstitials
shared across group boundaries are accessed from module scope, and interstitials
private to a single group are handled locally.

### 2. MLIR layer debugging overhead

The MLIR IR is "post-hoc" — it faithfully represents the generated Fortran but
is not used for optimization or scheduling. Every correctness bug requires tracing
through MLIR ops (`HostVarRefOp`, `ArraySectionOp`, `CopyOp`, etc.) before the
Fortran output can be understood. The IR adds real debugging overhead. The
long-term benefit (composable passes, multi-language, GPU backends) justifies
this cost, but it means fixes are slower than direct string generation would be.

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
Key calling-convention and generation bugs found and fixed during Fortran
compilation and runtime testing:
1. **`inout` double-passing** — MLIR's SSA model was splitting `intent(inout)`
   arguments into separate in/out actual arguments.
2. **Module naming inconsistency** — generated dispatcher used wrong case.
3. **Missing scheme USE statements** — suite cap called schemes without `use`.
4. **errflg/ntimes routing** — type-based matching routed `ntimes` (integer) to
   `errflg` (also integer); fixed to use standard_name matching.
5. **timestep errmsg/errflg** — timestep functions had `std_name=None` in
   `ret_info`, causing errmsg/errflg to go to orphaned `ccpp_tmp_N` locals
   instead of the cap's output arguments.
6. **Standard_name aliasing** — two schemes using different local names for the
   same standard_name (e.g. `temp`/`temp_layer`) generated duplicate block args,
   causing Fortran aliasing with non-contiguous array sections.
7. **Array subscript double-application** — DDT member subscripts like
   `phys_state%q(:,:,index_qv)` had `(cols:cole,1:pver)` appended as a second
   set of parentheses (invalid Fortran) instead of merged into one subscript.

These were only caught by compiling and running real Fortran — not by FileCheck.

### xdsl-ccpp functional gap vs capgen-ng
The most significant missing capabilities are:
1. **Per-group physics dispatch** — architecturally broken, causing correctness failures
2. Unit conversion
3. Optional argument handling
4. Chunked data layout
5. Build system integration
6. Host model integration beyond helloworld

Variable compatibility validation is now Partial‡ — type, kind, dimension rank,
and intent checks are implemented.

**Revised rough estimate:**
Physics correctness parity is now **demonstrated** across helloworld, capgen,
and ddthost test cases. Remaining gap to full feature parity (unit conversion,
optional args, build integration, host model integration beyond helloworld) is
approximately 15–20 weeks.

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
