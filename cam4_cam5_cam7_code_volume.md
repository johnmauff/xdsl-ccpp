# CAM4 / CAM5 / CAM7 physics-suite code volume

Snapshot date: 2026-10-16/17. Pinned to commits: CAM-SIMA `xdsl-ccpp-adapter`
@ `b743726`, atmospheric_physics `xdsl-support` @ `15b844d`. Will drift as
schemes are added/changed — re-verify before trusting exact numbers if
either branch has moved significantly since.

## Where the suites live

In the atmospheric_physics checkout
(`CAM-SIMA.xdsl-ccpp/src/physics/ncar_ccpp/`), under `suites/`:
`suite_adiabatic.xml`, `suite_cam4.xml`, `suite_cam5.xml`, `suite_cam7.xml`,
`suite_held_suarez_1994.xml`, `suite_kessler.xml`, `suite_musica.xml`,
`suite_tj2016.xml`.

- `suite_cam4.xml` — ACTIVE: selected via `cime_config/config_component.xml`'s
  `_CAM40` rule (`--physics-suites cam4`), used by compsets `F1850_C4`/
  `F2000_C4`/`QPC4`.
- `suite_cam5.xml` — DORMANT: `_CAM50`'s compset mapping is commented out
  in `config_component.xml`; zero references to `suite_cam5.xml` anywhere
  else in either repo.
- `suite_cam7.xml` — ACTIVE: used by `F2000_C7`.
- `suite_musica.xml` — DORMANT, same situation as cam5 (schema-valid only,
  not wired into any compset or test).

## Method

For each suite's distinct `<scheme>` entries (dedupe): resolved each scheme
name to its real `.F90` file via its `arg_table_<scheme>_<phase>` comment
marker (schemes are NOT 1:1 with files — many share one file, e.g. several
`apply_*`/diagnostics schemes live together in a handful of files). Found
each file's sibling `.meta` and any `<basename>_namelist.xml`. Counted
**non-blank lines only** (`grep -cve '^[[:space:]]*$'` per file — blank/
whitespace-only lines excluded, comment lines kept).

## Results

| Suite | Schemes | Unique files | `.F90` lines | `.meta` lines | namelist `.xml` lines | Total (interface layer) | `.meta` % |
|---|---:|---:|---:|---:|---:|---:|---:|
| CAM4 | 147 | 111 | 24,146 | 19,284 | 3,855 | **47,285** | 40.8% |
| CAM5 | 130 | 112 | 22,876 | 20,874 | 4,284 | **48,034** | 43.5% |
| CAM7 | 125 | 120 | 25,299 | 21,244 | 4,469 | **51,012** | 41.7% |

"Interface layer" = the CCPP-exposed `.F90`/`.meta` pairs atmospheric_physics
itself maintains — excludes vendored libraries (see below).

## Vendored-library dilution (RRTMGP + PUMAS)

Both CAM5 and CAM7 include PUMAS (two-moment microphysics); all three
suites include RRTMGP (radiation). Both are separately git-submoduled,
externally-maintained physics libraries with **zero `.meta` files by
construction** (they're not CCPP-exposed at that layer) — folding their
line counts in dilutes the `.meta` percentage without reflecting anything
`dup-meta-shadow-elim`-style tagging could ever apply to:

| Suite | Interface-layer total | + vendored (RRTMGP ext, + PUMAS for cam5/cam7) | `.meta` % (combined) |
|---|---:|---:|---:|
| CAM4 | 47,285 | 68,429 (+21,144 RRTMGP `ext/`) | 28.2% |
| CAM5 | 48,034 | 81,653 (+21,144 RRTMGP + 12,475 PUMAS) | 25.6% |
| CAM7 | 51,012 | 84,631 (+21,144 RRTMGP + 12,475 PUMAS) | 25.1% |

RRTMGP alone: interface-layer-only = 8,564 total lines (4,390 F90 + 3,527
meta + 647 xml), 41.2% meta; + vendored `schemes/rrtmgp/ext/` (21,144
non-blank lines, 56 files, zero meta) = 29,708 total, 11.9% meta.

PUMAS alone (CAM5/CAM7 only — not in CAM4): interface-layer-only = 5,458
total (1,458 F90 + 3,458 meta + 542 xml), 63.4% meta; + vendored
`schemes/pumas/pumas/` (12,475 non-blank lines, 11 files, zero meta) =
17,933 total, 19.3% meta.

## What CAM5/CAM7 add beyond CAM4

CAM5 (130 schemes vs. CAM4's 147 — fewer but larger-footprint schemes)
adds 26 schemes CAM4 lacks: PUMAS microphysics
(`micro_pumas_ccpp*`/`pumas_pre_main`/`pumas_post_main`), a full aerosol
activation/ice-nucleation chain (`ndrop_bam_ccpp`, `nucleate_ice_ccpp`,
`hetfrz_classnuc_stub`, `dropmixnuc_apply_surface_fluxes`,
`clamp_number_concentrations`, `dust_default_radii`), two-moment cloud
fraction/water (`compute_cloud_fraction_two_moment`,
`cloud_water_paths`, `convective_cloud_water`), subgrid vertical velocity
for activation, and switches vertical diffusion from Holtslag-Boville to
Bretherton-Park plus adds Beljaars form drag. In exchange it drops 41 CAM4
schemes: the Hack shallow-convection diagnostics chain, the entire
Rasch-Kristjansson stratiform cloud block, Holtslag-Boville's own PBL
coefficient schemes, the old BAM `aerosol_optics` scheme, and the
`prescribed_ozone`/`prescribed_volcanic_aerosol`/
`prescribed_aerosol_deposition_flux` schemes.

CAM7 and CAM5 use the identical PUMAS and RRTMGP scheme sets (confirmed
directly); CAM7 additionally carries a larger gravity-wave-drag family
(ridge/ridge_beta/frontogenesis/moving_mountain/convection_deep) than
CAM4/CAM5, plus a `clubb_stub` placeholder (lives in
`test/test_schemes/clubb_stub.F90`, not under `schemes/`, until CLUBB
itself is ported).

## Known gap found alongside this (real, not an xdsl_ccpp bug)

`suite_cam7.xml` and `test/test_suites/suite_gw_cam7_se.xml` both gained a
new scheme, `compute_total_precipitation_rate`, in the atmospheric_physics
`main` merge pulled in 2026-10-16. It needs 3 host variables
(`lwe_precipitation_rate_at_surface_due_to_deep_convection`/
`..._shallow_convection`/`lwe_large_scale_precipitation_rate_at_surface`)
that CAM-SIMA's `src/data/registry.xml` does not define — confirmed via
direct grep; the closest existing name is the differently-scoped
`..._to_coupler` variant. Causes a real `MODEL_BUILD` host-var-match
failure for the `cam-outfrq_gw_cam7_derecho` FPHYStest case (confirmed via
a real regression run, test ID `xdsl54g`) and likely `F2000_C7` too — same
class of gap as the already-known, already-deferred
`F2000_C7`/`convective_cloud_water` issue. Would fail identically under
real capgen-v1 (missing host variable, not generator-specific).
