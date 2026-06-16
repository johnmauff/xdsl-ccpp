# CCPP Tool Comparison: prebuild vs capgen vs capgen-ng vs xdsl-ccpp

---

## Tool Overview

| Tool | Status | Metadata format | Primary purpose |
|---|---|---|---|
| `ccpp_prebuild` | Production, legacy | Old embedded-comment format | Cap generation + build integration |
| `ccpp_capgen` | Production, current | New `.meta` file format | Cap generation + Fortran validation |
| `ccpp_capgen-ng` | In development | New `.meta` file format | Unified successor to both above |
| `xdsl-ccpp` | Prototype | New `.meta` file format | MLIR-based cap generation + GPU |

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
| Constituent registration | ✅ | ✅ | ✅ | ❌ |
| **Code correctness** | | | | |
| Fortran source cross-validation | ❌ | ✅ | ✅ | ❌ |
| Multi-instance support | ❌ | ❌ | ✅ | ❌ |
| **Build & tooling** | | | | |
| Build system integration (CMake) | ✅ | ✅ | ✅ | ❌ |
| Documentation generation | ✅ HTML/LaTeX | ✅ datatable.xml | ✅ | ❌ |
| `ccpp_track_variables` utility | ✅ | ❌ | ✅ | ❌ |
| **Testing** | | | | |
| Compiled Fortran execution tests | ✅ | ✅ | ✅ | Partial§ |
| Unit test depth | Moderate | Moderate | 1300+ tests | 19 pytest + 3 Makefiles |
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

---

## Notes on Partial / Missing xdsl-ccpp Capabilities

† **Host variable matching — remaining gaps:**
- `allocatable` code generation for non-real types (`ccpp_constituent_properties_t`
  arrays) — type compiles but constituent registration infrastructure is missing
- Integer `is_interstitial` scalars not handled (no test case; would produce invalid declarations)
- DDT interstitials (e.g. `vmr_type`) managed by the top-level cap instead of the
  suite cap module — architecturally the suite should own them
- DDT member `is_interstitial` not validated

‡ **Variable compatibility validation — remaining gaps:**
- Dimension name cross-validation beyond `horizontal_loop_extent` →
  `horizontal_dimension` (other substitutions are resolved but not checked)
- Unit compatibility checking (kind mismatches are annotated but not converted)
- DDT member type/rank/kind validation (members matched by standard_name only)
- Fortran source cross-validation against `.F90` files (metadata-only today)

§ **Compiled Fortran execution tests:**
- **helloworld**, **capgen**, **ddthost**: compile, run, and pass all correctness checks ✅
- **advection**: caps generate and compile; full end-to-end test blocked on missing
  constituent registration infrastructure (`ccpp_register_constituents` etc.)

---

## xdsl-ccpp Gaps vs capgen-ng

Ranked by impact on real-world use:

1. **Constituent registration infrastructure** — `ccpp_register_constituents`,
   `ccpp_number_constituents`, `ccpp_initialize_constituents` and related API not
   generated. Blocks the advection test case and any suite with advected species.

2. **Optional argument handling** — schemes with `optional` dummy arguments are not
   supported. Required for most real-world physics suites (~550 optional variables
   in CCPP-SCM).

3. **Unit / kind conversion** — kind mismatches between host and scheme are detected
   and annotated but no conversion code is emitted. Blocks integration with hosts
   that use different precision kinds.

4. **Build system integration** — no CMake or Make integration. xdsl-ccpp runs as a
   standalone script and cannot be embedded in a host model build.

5. **Host model integration** — only the three example test cases (helloworld, capgen,
   ddthost). No integration with CCPP-SCM, CAM-SIMA, or UFS.

6. **Chunked data layout** — column-blocked physics loops not supported.

7. **Fortran source cross-validation** — metadata is checked against metadata only;
   capgen-ng validates each scheme argument against the actual `.F90` source.

8. **Multi-instance support** — one suite instance per run only.

---

## Key Observations

### ccpp_prebuild vs ccpp_capgen
`ccpp_prebuild` handles unit conversion, optional args, and chunked data well.
`ccpp_capgen` adds Fortran source cross-validation and nested suites but lacks
chunked data and optional args. Neither replaces the other — that is why
`ccpp_capgen-ng` exists.

### ccpp_capgen-ng
Closes all gaps between prebuild and capgen, adds multi-instance support, and has
1300+ tests. Cannot add GPU support without an architectural rethink — it is a
text-templating generator throughout.

### xdsl-ccpp unique advantages
GPU support (OpenACC and OpenMP) is unique among CCPP tools. The MLIR architecture
enables future capabilities none of the other tools can reach: multi-language host
models, additional GPU backends, and composable transformation passes. Physics
correctness is verified across helloworld, capgen, and ddthost.

---

## Recommended Use Today

| Use case | Recommended tool |
|---|---|
| Production CPU physics — old metadata format | ccpp_prebuild |
| Production CPU physics — new metadata format | ccpp_capgen |
| Next-gen CPU physics development | ccpp_capgen-ng |
| GPU-enabled physics development | xdsl-ccpp |
| Research into multi-language host models | xdsl-ccpp |
