# xdsl_ccpp Readiness: non-FPHYStest aux_sima Cases

Analysis date: 2026-09-06  
Context: `aux_sima` test suite has 24 cases on derecho/gnu. 15 are `FPHYStest/ne3pg3`
(stub/null dycore, already verified with xdsl_ccpp). The remaining 9 use real SE or MPAS
dycores and are assessed below.

---

## Key finding: host variables are dycore-agnostic

The CAM-SIMA registry (`src/data/registry.xml`) generates the **same CCPP host variables**
regardless of whether the dycore is SE, MPAS, or null. The dycore only affects initial
values of a few variables (via `dyn=` attributes), not the variable definitions themselves.
From xdsl_ccpp's perspective, the host `.meta` files passed to `ccpp_dsl` are identical
across dycores. "Real SE" vs. "null dycore" is **not** an xdsl_ccpp blocker.

No preprocessor `#if`/`#ifdef` directives were found in any scheme `.meta` file for any
of the six suites examined (`kessler`, `held_suarez_1994`, `tj2016`, `adiabatic`, `cam4`,
`cam7`). The existing xdsl_ccpp restriction on preprocessor defines does not apply here.

---

## Case-by-case assessment

### SE dycore cases — 5 cases, all ne3pg3_ne3pg3_mg37 grid

All use `CAM_DYCORE=se` with the real spectral element dycore. Host files are identical to
FPHYStest cases from xdsl_ccpp's perspective.

| Test name | Physics suite | Scheme count | Assessment |
|-----------|--------------|--------------|------------|
| `SMS_Ln9.ne3pg3_ne3pg3_mg37.FKESSLER.derecho_gnu.cam-outfrq_se_cslam` | `kessler` | 25 | **Ready** — superset of `kessler_test` (16 schemes) already proven. Extra schemes: `check_energy_*`, `dme_adjust`, `dycore_energy_consistency_adjust`, `thermo_water_update`, `sima_tend_diagnostics`. No new types. |
| `SMS_Ln9.ne3pg3_ne3pg3_mg37.FHS94.derecho_gnu.cam-outfrq_se_cslam` | `held_suarez_1994` | 7 | **Ready** — this exact suite already passes FPHYStest runs with xdsl_ccpp. |
| `SMS_Ln9.ne3pg3_ne3pg3_mg37.FTJ16.derecho_gnu.cam-outfrq_se_cslam` | `tj2016` | 18 | **Ready** — this exact suite already passes FPHYStest runs with xdsl_ccpp. |
| `SMS_Ln9.ne3pg3_ne3pg3_mg37.FADIAB.derecho_gnu.cam-outfrq_se_cslam` | `adiabatic` | 12 | **Ready** — simpler than kessler; no physics tendencies, just energy bookkeeping. |
| `SMS_Ln9.ne3pg3_ne3pg3_mg37.FCAM7.derecho_gnu.cam-outfrq_se_cslam_analy_ic` | `cam7` | 89 | **Likely ready** — 40 schemes not in simpler suites (gravity wave drag variants, cloud fraction, ZM convection, etc.). No DDT variables or preproc defs found in meta files. Larger surface area so edge cases possible, but no structural blocker identified. |

**Verdict for SE cases:** Minimal or no xdsl_ccpp code changes expected. These cases could
be added to a `CCPP_GENERATOR=xdsl_ccpp` test run immediately.

---

### MPAS dycore cases — 4 cases

MPAS uses its own upstream build infrastructure rather than CIME's standard Fortran
compilation path. This is the primary unknown — xdsl_ccpp has never been exercised with
the MPAS dycore build path.

| Test name | Physics suite | Scheme count | Assessment |
|-----------|--------------|--------------|------------|
| `SMS_Ln9.mpasa480_mpasa480.FKESSLER.derecho_gnu.cam-outfrq_kessler_mpas_derecho` | `kessler` | 25 | **Unknown** — physics suite is known-good but MPAS build path untested with xdsl_ccpp. Simplest MPAS case; good first target for investigation. |
| `SMS_Ln9.mpasa480_mpasa480.FKESSLER.derecho_gnu.cam-outfrq_kessler_mpas_derecho_history` | `kessler` | 25 | **Unknown** — same as above plus history output testmod. |
| `SMS_Ln9.mpasa120_mpasa120.QPC4.derecho_gnu.cam-outfrq_analy_ic_cam4` | `cam4` | 139 unique scheme names | **Unknown** — both unknowns combined: MPAS build path AND cam4's large scheme set. Lower priority until MPAS basic case works. |
| `SMS_D_Ln9.mpasa120_mpasa120.QPC4.derecho_gnu.cam-outfrq_analy_ic_cam4` | `cam4` | 139 unique scheme names | **Unknown** — same as QPC4 above plus restart/branch test (`SMS_D` test type). |

**Verdict for MPAS cases:** Physics content is not the blocker (kessler is proven). The
investigation needed is: does the MPAS build path correctly invoke `cam_autogen.py` with
`CCPP_GENERATOR=xdsl_ccpp`, and does xdsl_ccpp's generated code compile cleanly against
the MPAS interface layer? Start with `outfrq_kessler_mpas_derecho` since it isolates the
MPAS build path from suite complexity.

---

## Summary

| Category | Count | Status |
|----------|-------|--------|
| FPHYStest (null dycore) | 15 | In test (PBS job 7334893) |
| SE dycore, simple suites (kessler/hs94/tj2016/adiabatic) | 4 | Ready, no code changes needed |
| SE dycore, cam7 | 1 | Likely ready, needs test |
| MPAS dycore, kessler | 2 | Unknown — MPAS build path investigation needed |
| MPAS dycore, cam4 | 2 | Unknown — lower priority |

Of the 24 total aux_sima cases, **20 are likely xdsl_ccpp-ready** with no code changes.
The 4 MPAS cases are the remaining frontier.
