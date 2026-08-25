<!--
Draft outline (2026-08-25) of the remaining D.4/D.5 files for every package
whose D.2 full-repo triage produced at least one pointwise/column-scan
candidate, beyond the three packages already fully drafted as real header
files in this directory (utilities_ccpp_native.hpp,
conservation_adjust_ccpp_native.hpp, kessler_ccpp_native.hpp) and
eamxx_xdsl_process_interface.{hpp,cpp} (the D.5 process-interface skeleton).

Why an outline instead of full .hpp files for these 13 packages: the three
files above were drafted from Fortran source read in full this session, so
their argument lists are verified. For the packages below, argument lists
come from fork reports that quoted the scheme's *math shape* precisely but
did not always transcribe every argument -- writing full header files with
invented-but-plausible-looking signatures would look more authoritative than
the underlying evidence supports. Every signature below is marked with a
confidence tag; treat [sketch] entries as "verify against the real .meta/.F90
before implementing," not as ready-to-compile declarations.

Naming convention: friendly `compute_*`/`apply_*`/`adjust_*` names, matching
utilities_ccpp_native.hpp -- not the literal CCPP `*_run` entry-point name.
Every signature takes whole-array Kokkos::View arguments and returns void, per
the same "no loop in the caller, one bare-line call site" contract as
utilities_ccpp_native.hpp and TMSFunctions::compute_tms -- no exceptions below.
`VT`/`Pack` are eamxx_ccpp_view_types.hpp's aliases throughout.
-->

# D.4/D.5 outline: remaining 13 packages

For each package: proposed D.4 header (device functions, empty bodies) and
D.5 note (which EAMxx `AtmosphereProcess` would include it -- for these
packages, unlike `utilities`/`conservation_adjust`, that's a real, dedicated
process, analogous to `KesslerMicrophysics`/`TurbulentMountainStress`, not a
shared cross-process utility).

## rayleigh_friction
**File:** `rayleigh_friction_ccpp_native.hpp` -- **D.5:** would-be `RayleighFriction` process (currently unused by any suite in this repo).
```cpp
KOKKOS_INLINE_FUNCTION
static void apply_rayleigh_friction(int ncol, int nz, Real ztodt,
                                     const VT::view_1d<Real>& otau,   // [sketch]
                                     const VT::view_2d<Pack>& u,
                                     const VT::view_2d<Pack>& v,
                                     VT::view_2d<Pack>& dudt,
                                     VT::view_2d<Pack>& dvdt,
                                     VT::view_2d<Pack>& dsdt);
```
`otau` moves from `rayleigh_friction_init`'s module state to an explicit argument (same pattern as Kessler's `gravit`).

## held_suarez
**File:** `held_suarez_ccpp_native.hpp` -- **D.5:** `HeldSuarez` process.
```cpp
KOKKOS_INLINE_FUNCTION
static void apply_held_suarez_1994(int ncol, int nz, Real dt,
                                    const VT::view_1d<Real>& clat,     // [sketch]
                                    const VT::view_1d<Real>& pref,     // module state -> arg
                                    const VT::view_2d<Pack>& pmid,
                                    const VT::view_2d<Pack>& u,
                                    const VT::view_2d<Pack>& v,
                                    const VT::view_2d<Pack>& temp,
                                    VT::view_2d<Pack>& ds,
                                    VT::view_2d<Pack>& du,
                                    VT::view_2d<Pack>& dv);
```

## cloud_fraction
**File:** `cloud_fraction_ccpp_native.hpp` -- **D.5:** `CloudFraction` process (`compute_cloud_fraction_run` itself stays Fortran -- genuinely needs Fortran, see D.2).
```cpp
KOKKOS_INLINE_FUNCTION  // cloud_fraction_fice_run
static void compute_cloud_fraction_fice(int ncol, int nz,
                                         const VT::view_2d<Pack>& temp,    // [sketch]
                                         VT::view_2d<Pack>& fice,
                                         VT::view_2d<Pack>& fsnow);

KOKKOS_INLINE_FUNCTION  // convective_cloud_cover_run
static void compute_convective_cloud_cover(int ncol, int nz,
                                            const VT::view_2d<Pack>& /* inputs at k, k+1 */, // [sketch]
                                            VT::view_2d<Pack>& conv_cld);
```
`set_cloud_fraction_top_init` is init-only (`top_lev = trop_cloud_top_lev`, a scalar copy) -- not worth its own device function; a process's own `initialize_impl` can just set the member directly.

## hack_shallow
**File:** `hack_shallow_ccpp_native.hpp` -- **D.5:** `HackShallowConvection` process (`hack_convect_shallow_run` itself stays Fortran; used by cam4 only, not cam7).
```cpp
KOKKOS_INLINE_FUNCTION  // set_general_conv_fluxes_to_shallow_run / set_shallow_conv_fluxes_to_general_run
static void route_shallow_conv_fluxes(int ncol, int nz,
                                       const VT::view_2d<Pack>& src, VT::view_2d<Pack>& dst); // [sketch, generic-reuse candidate: pure copy, same shape both directions]

KOKKOS_INLINE_FUNCTION  // convect_shallow_sum_to_deep_run
static void sum_shallow_into_deep_convection(int ncol, int nz,
                                              const VT::view_2d<Pack>& cmfmc_deep,
                                              const VT::view_2d<Pack>& cmfmc_sh,
                                              VT::view_2d<Pack>& cmfmc_total /* , per-column index merge args TBD */); // [sketch]
```

## tj2016
**File:** `tj2016_ccpp_native.hpp` -- **D.5:** `TJ2016` process. **The best-verified of this outline's 13** -- `tj2016_sfc_pbl_hs_run` was read in full this session, so its signature below is high-confidence; `tj2016_precip_run` was not read in full (only the fork's evidence), so it's marked [sketch] despite being the single best candidate in the whole repo.
```cpp
KOKKOS_INLINE_FUNCTION  // tj2016_precip_run -- best Phase D pilot in the repo
static void compute_tj2016_precip(int ncol, int nz, Real dt,
                                   const VT::view_2d<Pack>& pmid,    // [sketch]
                                   VT::view_2d<Pack>& temp,
                                   VT::view_2d<Pack>& qv,
                                   VT::view_1d<Real>& precl);

KOKKOS_INLINE_FUNCTION  // tj2016_sfc_pbl_hs_run -- verified in full this session
static void apply_tj2016_sfc_pbl_hs(const VT::MemberType& team, int ncol, int nz,
                                     int index_top_interface, int index_surface,
                                     int index_surface_interface,
                                     Real gravit, Real pi, Real latvap, Real rh2o,
                                     Real epsilo, Real rhoh2o, Real ps0, Real dtime,
                                     const VT::view_2d<Pack>& cappav,
                                     const VT::view_2d<Pack>& rairv,
                                     const VT::view_2d<Pack>& cpairv,
                                     const VT::view_2d<Pack>& zvirv,
                                     const VT::view_1d<Real>& etamid,
                                     const VT::view_1d<Real>& clat,
                                     const VT::view_1d<Real>& PS,
                                     const VT::view_2d<Pack>& pmid,
                                     const VT::view_2d<Pack>& pint,
                                     const VT::view_2d<Pack>& lnpint,
                                     const VT::view_2d<Pack>& rpdel,
                                     const VT::view_2d<Pack>& stateT,
                                     const VT::view_2d<Pack>& U,
                                     VT::view_2d<Pack>& dudt,
                                     const VT::view_2d<Pack>& V,
                                     VT::view_2d<Pack>& dvdt,
                                     VT::view_2d<Pack>& qv,
                                     VT::view_1d<Real>& shflx, VT::view_1d<Real>& lhflx,
                                     VT::view_1d<Real>& taux, VT::view_1d<Real>& tauy,
                                     VT::view_1d<Real>& evap,
                                     VT::view_2d<Pack>& dqdt_vdiff, VT::view_2d<Pack>& dtdt_vdiff,
                                     VT::view_2d<Pack>& dtdt_heating,
                                     VT::view_2d<Pack>& Km, VT::view_2d<Pack>& Ke,
                                     VT::view_1d<Real>& Tsurf,
                                     VT::view_2d<Pack>& tendency_of_air_enthalpy);
```
This one takes a `MemberType& team` (not a flat range) because its body is the two-pass inline Thomas-algorithm solve identified in D.2's cross-cutting finding #3 -- a team-per-column policy, same family as `dme_adjust`/`PF::calculate_z_int`, not the plain range-parallel form the pointwise functions elsewhere in this outline use. It has real argument *count* (25+) that a real implementation would likely want to pack into a small struct rather than a flat parameter list this long -- noted here rather than pretending a 25-argument C++ function is a clean design.

## mmm
**File:** `mmm_ccpp_native.hpp` -- **D.5:** none -- not referenced by any suite in this repo; drafting a process for it would have no suite to attach to. Included only if someone later wires an `mmm`-based suite in. Signatures omitted from this outline entirely (would be pure invention with zero suite context to verify against).

## holtslag_boville
**File:** `holtslag_boville_ccpp_native.hpp` -- **D.5:** `HoltslagBovillePBL` process.
```cpp
KOKKOS_INLINE_FUNCTION  // hb_diff_exchange_coefficients_run / hb_diff_free_atm_exchange_coefficients_run
static void compute_hb_exchange_coefficients(int ncol, int nz,
                                              const VT::view_2d<Pack>& ri,     // [sketch]
                                              const VT::view_2d<Pack>& s2,
                                              VT::view_2d<Pack>& kvf);

KOKKOS_INLINE_FUNCTION  // hb_pbl_independent_coefficients_run
static void compute_hb_pbl_independent_coefficients(int ncol, int nz,
                                                      const VT::view_2d<Pack>& temp,   // [sketch]
                                                      const VT::view_2d<Pack>& exner,
                                                      VT::view_2d<Pack>& th /* , shear/N2/Ri outputs TBD */);

KOKKOS_INLINE_FUNCTION  // hb_pbl_dependent_coefficients_run -- COLUMN-SCAN
static void compute_hb_pbl_height(const VT::MemberType& team, int ncol, int npbl,
                                   const VT::view_2d<Pack>& /* scan inputs TBD */, // [sketch]
                                   VT::view_1d<Real>& pblh);
```

## vertical_diffusion
**File:** `vertical_diffusion_ccpp_native.hpp` -- **D.5:** `VerticalDiffusion` process. Most of this package's 14 pointwise candidates are small setup/bookkeeping pieces (TOA defaults, interface interpolation, sponge-layer damping, the `diffusion_stubs.F90` TMS/Beljaars placeholders) -- listing one representative shape rather than all 14:
```cpp
KOKKOS_INLINE_FUNCTION  // vertical_diffusion_interpolate_to_interfaces_run
static void interpolate_to_interfaces(int ncol, int nz,
                                       const VT::view_2d<Pack>& t_mid,   // [sketch]
                                       VT::view_2d<Pack>& t_int);

KOKKOS_INLINE_FUNCTION  // vertical_diffusion_sponge_layer_run
static void apply_sponge_layer_damping(int ncol,
                                        const VT::view_1d<Real>& sponge_coeffs, // [sketch, fixed 4-6 element const array]
                                        VT::view_2d<Pack>& kvm);
```
**Deliberately excluded from this outline** (genuinely needs Fortran, per D.2): `vertical_diffusion_diffuse_horizontal_momentum_run`, `vertical_diffusion_diffuse_dry_static_energy_run`, `vertical_diffusion_diffuse_tracers_run` -- each calls an implicit tridiagonal/LU solve in `to_be_ccppized/`. **Also excluded**: the mixed-portability schemes flagged in `cpp_native_candidates.meta`'s header note (`vertical_diffusion_diffuse_horizontal_momentum`/`_diffuse_tracers`'s own trivial `_init`/`_timestep_init` phases) -- same reasoning, don't tag half a scheme.

## tropopause_find
**File:** `tropopause_find_ccpp_native.hpp` -- **D.5:** would be consumed by whichever process needs tropopause diagnostics (cam4/cam7 both use it; not necessarily its own process).
```cpp
KOKKOS_INLINE_FUNCTION  // tropopause_find_run -- COLUMN-SCAN, dispatches to ~6 algorithm variants
static void find_tropopause(const VT::MemberType& team, int ncol, int nz,
                             int algorithm_id,  // [sketch] selects among WMO/climate/hybrid-Stobie/cold-point/chemical
                             const VT::view_2d<Pack>& temp,
                             const VT::view_2d<Pack>& pmid,
                             VT::view_1d<int>& trop_level,
                             VT::view_1d<Real>& trop_pressure);
```
The real scheme's ~6 internal algorithms (only some of which run per call, selected by namelist option) are collapsed into one `algorithm_id` dispatch here rather than 6 separate device functions -- verify this is the right granularity against the real `tropopause_find.F90` before implementing; it may be cleaner as 6 small functions plus a thin dispatcher, mirroring the real Fortran's own structure more closely.

## rasch_kristjansson
**File:** `rasch_kristjansson_ccpp_native.hpp` -- **D.5:** `RaschKristjanssonStratiform` process (`prognostic_cloud_water_run` stays Fortran -- genuinely needs Fortran).
```cpp
KOKKOS_INLINE_FUNCTION  // rk_stratiform_detrain_convective_condensate_run / _external_forcings_run / _condensate_repartioning_run / _prognostic_cloud_water_tendencies_run / _save_qtlcwat_run / _check_qtlcwat_run / _sedimentation_run
static void compute_rk_stratiform_tendency_piece(int ncol, int nz,
                                                  const VT::view_2d<Pack>& /* varies per scheme */, // [sketch]
                                                  VT::view_2d<Pack>& tend);  // representative shape only -- these 7 are NOT one generic function in reality, each combines different already-computed rate terms; listed as one block here purely to keep this outline's length reasonable

KOKKOS_INLINE_FUNCTION  // cloud_particle_sedimentation_run -- COLUMN-SCAN, more sophisticated than PF::calculate_z_int
static void compute_cloud_particle_sedimentation(const VT::MemberType& team, int ncol, int nz,
                                                  const VT::view_2d<Pack>& /* getflx/cfint2 inputs TBD */, // [sketch]
                                                  VT::view_2d<Pack>& sedimentation_flux);
```
Budget more D.4 effort for `compute_cloud_particle_sedimentation` than the pointwise pieces above -- its interval-search/cubic-interpolation numerics (`cfint2`) are real, not a one-line port.

## zhang_mcfarlane
**File:** `zhang_mcfarlane_ccpp_native.hpp` -- **D.5:** `ZhangMcFarlaneDeepConvection` process. Only the small bookkeeping pieces qualify; `zm_convr_run`/`zm_conv_convtran_run`/`zm_conv_momtran_run` are excluded (genuinely needs Fortran **and** column gather/scatter, D.2's cross-cutting finding #1 -- porting these would need a new gather/scatter design this outline does not attempt).
```cpp
KOKKOS_INLINE_FUNCTION  // save_ttend_from_convect_deep_timestep_init / _run
static void accumulate_deep_convection_ttend(int ncol, int nz,
                                              const VT::view_2d<Pack>& tend_s,   // [sketch]
                                              const VT::view_2d<Pack>& cpair,
                                              VT::view_2d<Pack>& ttend_dp);

KOKKOS_INLINE_FUNCTION  // set_deep_conv_fluxes_to_general_run / set_general_conv_fluxes_to_deep_run
static void route_deep_conv_fluxes(int ncol, int nz,
                                    const VT::view_2d<Pack>& src, VT::view_2d<Pack>& dst); // [sketch, pure copy, generic-reuse candidate like hack_shallow's routing pair above]
```

## gravity_wave_drag
**File:** `gravity_wave_drag_ccpp_native.hpp` -- **D.5:** would be consumed by whichever process needs GWD preprocessing; the package's real driver schemes all stay Fortran (`gw_drag_prof`'s shared engine, genuinely needs Fortran).
```cpp
KOKKOS_INLINE_FUNCTION  // gravity_wave_drag_prepare_profiles_run
static void prepare_gw_profiles(int ncol, int nz,
                                 const VT::view_2d<Pack>& t_mid,   // [sketch, fixed 2-point neighbor stencil]
                                 VT::view_2d<Pack>& nm, VT::view_2d<Pack>& ni, VT::view_2d<Pack>& rhoi);

KOKKOS_INLINE_FUNCTION  // gravity_wave_drag_top_taper_init -- COLUMN-SCAN, init-only (fixed reference grid, no _run)
static void compute_gw_top_taper(const VT::MemberType& team, int nz,
                                  const VT::view_1d<Real>& pref_edge,  // [sketch]
                                  VT::view_1d<Real>& vramp);
```

## rrtmgp
**File:** `rrtmgp_ccpp_native.hpp` -- **D.5:** N/A as a standalone process -- see `EAMxx-bridge-automation.md`'s cross-cutting finding #2. If EAMxx already links a native C++ RTE+RRTMGP (very likely, per that finding), the right move is almost certainly bridging to that directly rather than writing this header at all. Included only for the ~9 pre/post-processing glue functions `cpp_native_candidates.meta` tagged, in case that investigation concludes otherwise for some of them:
```cpp
KOKKOS_INLINE_FUNCTION  // rrtmgp_lw_calculate_heating_rate_run / rrtmgp_sw_calculate_heating_rate_run
static void compute_rrtmgp_heating_rate(int ncol, int nz, Real gravit,
                                         const VT::view_2d<Pack>& flux_net,   // [sketch, 2-point stencil]
                                         const VT::view_2d<Pack>& rpdel,
                                         VT::view_2d<Pack>& hrate);
```
The other ~8 tagged functions (`calculate_net_heating`, `rrtmgp_dry_static_energy_tendency`, the `*_calculate_fluxes`/`*_gas_optics_pre` pairs, `rrtmgp_lw_aerosols`) are omitted from this outline rather than sketched -- several of them read from or write into the RTE-RRTMGP library's own DDT objects (`ty_fluxes_byband_ccpp`, gas-concentration objects), so their "whole-array Kokkos::View" signature depends on a design decision (what replaces those DDTs on the C++ side) this outline hasn't made and shouldn't guess at.

---

## Cross-package pattern: some CCPP schemes share one device function

Repeated across this outline and the fully-drafted headers: several distinct
CCPP schemes reduce to the *same* device function called with different
arguments (`convert_wet_to_dry_mixing_ratio` replaces 4 schemes;
`apply_and_reset_tendency` replaces 3; `route_shallow_conv_fluxes` and
`route_deep_conv_fluxes` are both "pure copy between two field-naming
schemes"). A generator (D.3) that assumes one `cpp_native` scheme maps to
exactly one emitted declaration would produce 4 near-duplicate declarations
where a human would write 1 function called 4 times -- worth deciding
deliberately (either the generator recognizes identical-shape schemes and
consolidates, or it over-generates and a human consolidates by hand
afterward) rather than discovering this by accident once D.3 is implemented
for real.
