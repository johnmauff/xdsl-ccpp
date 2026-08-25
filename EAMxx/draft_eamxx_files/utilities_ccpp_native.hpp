#ifndef SCREAM_CCPP_NATIVE_UTILITIES_HPP
#define SCREAM_CCPP_NATIVE_UTILITIES_HPP

// Draft of EAMxx-bridge-automation.md's Phase D.4 for the `utilities` package
// (atmospheric_physics/schemes/utilities/) -- shared across nearly every suite
// in the repo (kessler, cam4, cam7, adiabatic, tj2016; see D.2's full-repo
// results), which is why this lives in its own header rather than inside
// kessler_ccpp_native.hpp: any process that needs `compute_exner` should
// include this one header, not duplicate the declaration per-process.
//
// STATUS: draft/exploratory. Most bodies below are empty stubs -- the actual
// Kokkos::parallel_for each one needs is a one-time hand-port, not written
// here (per the request that produced this file) -- except
// compute_geopotential_temp, which already has a real body (see that
// function's own comment for why). Every signature takes whole-array
// Kokkos::View arguments and returns void -- there is no per-point form
// anywhere in this header, so nothing that calls these needs its own loop;
// the call site is always one bare line, matching TMSFunctions::compute_tms's
// shape, not PF::exner_function's pointwise one.
//
// Function names are the natural/friendly form (`compute_exner`, not the
// literal CCPP entry-point name `calc_exner_run`) -- see
// cpp_native_candidates.meta for the scheme <-> function-name mapping the
// Phase D.3 printer would need to encode.

#include "eamxx_ccpp_view_types.hpp"
#include "share/physics/eamxx_common_physics_functions.hpp"

#include <ekat_team_policy_utils.hpp>

namespace scream {
namespace ccpp_native {

using VT = ccpp::DefaultCCPPViewTypes;
using Pack = VT::Pack;
using PF = scream::PhysicsFunctions<DefaultDevice>;

// calc_exner_run: exner(:,k) = (pmid/ref_pres)**(rair/cpair), per level.
// NOTE: EAMxx already has a hand-written analog, PF::exner_function, using
// fixed dry-air constants internally rather than these composition-dependent
// rair/cpair arguments (Category 1's open finding -- the two are not
// bit-identical). This function's body should either forward to
// PF::exner_function where the constants agree, or implement the
// composition-dependent formula directly where they don't -- re-derive and
// verify, don't copy-paste.
KOKKOS_INLINE_FUNCTION
static void compute_exner(int ncol, int nz,
                           const VT::view_2d<Pack>& cpair,
                           const VT::view_2d<Pack>& rair,
                           Real ref_pres,
                           const VT::view_2d<Pack>& pmid,
                           VT::view_2d<Pack>& exner) {
  // TODO: one-time hand port of calc_exner_run
  // (atmospheric_physics/schemes/utilities/state_converters.F90). Kokkos
  // loop goes here -- never at this function's call site.
}

// temp_to_potential_temp_run: theta = temp/exner, per level.
// NOTE: analog is PF::calculate_theta_from_T -- same re-derive-and-verify
// caveat as compute_exner above.
KOKKOS_INLINE_FUNCTION
static void compute_theta_from_temp(int ncol, int nz,
                                     const VT::view_2d<Pack>& temp,
                                     const VT::view_2d<Pack>& exner,
                                     VT::view_2d<Pack>& theta) {
  // TODO: one-time hand port of temp_to_potential_temp_run.
}

// potential_temp_to_temp_run: temp = theta*exner, per level. Inverse of the
// above; no existing PF:: analog.
KOKKOS_INLINE_FUNCTION
static void compute_temp_from_theta(int ncol, int nz,
                                     const VT::view_2d<Pack>& theta,
                                     const VT::view_2d<Pack>& exner,
                                     VT::view_2d<Pack>& temp) {
  // TODO: one-time hand port of potential_temp_to_temp_run.
}

// calc_dry_air_ideal_gas_density_run: rho = pmiddry/(rair*temp), per level.
// NOTE: Category 2's open physics question -- does this ideal-gas density
// agree closely enough with EAMxx's own mass-weighted
// rho = pseudo_density/(g*dz) to be interchangeable? That is a physics
// question to resolve before wiring this in, independent of the trivial
// portability of the shape itself.
KOKKOS_INLINE_FUNCTION
static void compute_dry_air_density(int ncol, int nz,
                                     const VT::view_2d<Pack>& rair,
                                     const VT::view_2d<Pack>& pmiddry,
                                     const VT::view_2d<Pack>& temp,
                                     VT::view_2d<Pack>& rho) {
  // TODO: one-time hand port of calc_dry_air_ideal_gas_density_run.
}

// Replaces wet_to_dry_water_vapor_run / wet_to_dry_cloud_liquid_water_run /
// wet_to_dry_cloud_ice_run / wet_to_dry_rain_run -- all four are the
// identical formula q_dry(:,k) = q(:,k)*(pdel(:,k)/pdeldry(:,k)) for
// different species; one generic device function replaces all four CCPP
// schemes, called once per species from the process interface, rather than
// four near-duplicate device functions. Not needed for Kessler itself
// (qv/qc/qr are already dry-basis on both sides there), but real for any
// suite/process that does need the conversion.
KOKKOS_INLINE_FUNCTION
static void convert_wet_to_dry_mixing_ratio(int ncol, int nz,
                                             const VT::view_2d<Pack>& pdel,
                                             const VT::view_2d<Pack>& pdeldry,
                                             const VT::view_2d<Pack>& q_wet,
                                             VT::view_2d<Pack>& q_dry) {
  // TODO: one-time hand port (shared by all 4 wet_to_dry_* schemes).
}

// Replaces dry_to_wet_water_vapor_run / dry_to_wet_cloud_liquid_water_run /
// dry_to_wet_cloud_ice_run / dry_to_wet_rain_run -- inverse of the above,
// same one-generic-function-for-four-schemes reasoning.
KOKKOS_INLINE_FUNCTION
static void convert_dry_to_wet_mixing_ratio(int ncol, int nz,
                                             const VT::view_2d<Pack>& pdel,
                                             const VT::view_2d<Pack>& pdeldry,
                                             const VT::view_2d<Pack>& q_dry,
                                             VT::view_2d<Pack>& q_wet) {
  // TODO: one-time hand port (shared by all 4 dry_to_wet_* schemes).
}

// convert_dry_constituent_tendencies_to_dry_air_basis_run.
// Argument list is approximate (evidence: `tend_q(i,k,m) *= pdel(i,k)/pdeldry(i,k)`
// gated by a per-constituent dry/wet flag) -- verify against
// atmospheric_physics/schemes/utilities/convert_dry_constituent_tendencies_to_dry_air_basis.F90
// before implementing; the constituent-dry-flag argument shape in particular
// needs re-derivation (it's a per-constituent property lookup in the real
// scheme, not a plain array).
KOKKOS_INLINE_FUNCTION
static void convert_constituent_tendencies_to_dry_basis(
    int ncol, int nz, int pcnst,
    const VT::view_2d<Pack>& pdel,
    const VT::view_2d<Pack>& pdeldry,
    /* per-constituent dry/wet flag -- shape TBD, see note above */
    VT::view_2d<Pack>& tend_q) {
  // TODO: one-time hand port. SIGNATURE SKETCH -- verify against source.
}

// apply_tendency_of_eastward_wind_run / apply_tendency_of_northward_wind_run /
// apply_heating_rate_run / apply_tendency_of_air_temperature_run /
// apply_constituent_tendencies_run all share this exact shape:
//   state(:,k) += tend(:,k)*dt; total(:,k) += tend(:,k); tend(:,k) = 0
// Declared as one generic function per state variable's rank/type below,
// rather than five near-identical device functions, mirroring the
// wet/dry-conversion consolidation above.
KOKKOS_INLINE_FUNCTION
static void apply_and_reset_tendency(int ncol, int nz,
                                      VT::view_2d<Pack>& state,
                                      VT::view_2d<Pack>& tend,
                                      VT::view_2d<Pack>& total_tend,
                                      Real dt) {
  // TODO: one-time hand port (shared by apply_tendency_of_eastward_wind_run,
  // apply_tendency_of_northward_wind_run, and apply_tendency_of_air_temperature_run
  // -- the latter is [unconfirmed] possibly superseded by EAMxx's energy
  // fixer; keep this available in case that hedge resolves "not superseded").
}

// apply_heating_rate_run divides by cpair on the way in, so it does not
// fit apply_and_reset_tendency's shape exactly -- kept separate rather than
// forcing a fourth "extra scaling argument" onto the shared function above.
KOKKOS_INLINE_FUNCTION
static void apply_and_reset_heating_rate(int ncol, int nz,
                                          VT::view_2d<Pack>& temp,
                                          VT::view_2d<Pack>& heating_rate,
                                          VT::view_2d<Pack>& dTdt_total,
                                          Real dt,
                                          const VT::view_2d<Pack>& cpair) {
  // TODO: one-time hand port of apply_heating_rate_run.
}

// apply_constituent_tendencies_run: same shape as apply_and_reset_tendency
// but rank-3 (per constituent) -- D.1's shared header has no view_3d alias
// yet (see eamxx_ccpp_view_types.hpp's own NotImplementedError for this
// exact gap), so this declaration is blocked on that header being extended
// first.
// KOKKOS_INLINE_FUNCTION
// static void apply_and_reset_constituent_tendencies(int ncol, int nz, int pcnst,
//                                                     VT::view_3d<Pack>& const_,
//                                                     VT::view_3d<Pack>& const_tend,
//                                                     Real dt);

// static_energy.F90's update_dry_static_energy_run:
//   st_energy(:,k) = temp(:,k)*cpair(:,k) + gravit*zm(:,k) + phis(:)
// Argument list approximate (not directly read this session) -- verify
// against atmospheric_physics/schemes/utilities/static_energy.F90.
KOKKOS_INLINE_FUNCTION
static void compute_dry_static_energy(int ncol, int nz,
                                       const VT::view_2d<Pack>& temp,
                                       const VT::view_2d<Pack>& cpair,
                                       const VT::view_2d<Pack>& zm,
                                       const VT::view_1d<Real>& phis,
                                       Real gravit,
                                       VT::view_2d<Pack>& st_energy) {
  // TODO: one-time hand port. SIGNATURE SKETCH -- verify against source.
}

// geopotential_temp_run: confirmed structurally superseded (EAMxx's own
// hand-written z_mid/z_int scan already does this -- see
// eamxx_kessler_process_interface.cpp's tracking comment, "-> done above
// when calculating z_mid"), so no *generated* call site will ever invoke a
// native replacement for it. Included below anyway, with a real body rather
// than a stub, because that "already does this" computation already exists
// as working EAMxx code -- extracted here verbatim (adapted from a
// class-member lambda to a free-function one) rather than re-derived, so it
// can be reused directly by any future process that doesn't already have its
// own copy of this z_mid/z_int logic, instead of every such process
// re-deriving the same team-scan by hand the way Kessler's own
// eamxx_kessler_process_interface.cpp had to.
//
// Source: eamxx_kessler_process_interface.cpp, lines 276-288 (run_impl's
// preprocess block, immediately before the Fortran bridge call). dz is an
// input here, not computed by this function -- in that source, it comes
// from an earlier call to PF::calculate_dz in the same preprocess loop.
KOKKOS_INLINE_FUNCTION
static void compute_geopotential_temp(int ncol, int nz,
                                       const VT::view_2d<Pack>& dz,
                                       VT::view_2d<Pack>& z_int,
                                       VT::view_2d<Pack>& z_mid) {
  // calculate_z_int() contains a team-level parallel_scan, which requires a
  // special policy -- verbatim from eamxx_kessler_process_interface.cpp.
  using TPF = ekat::TeamPolicyFactory<VT::KT::ExeSpace>;
  const int nlev_packs   = ekat::npack<Pack>(nz);
  const auto scan_policy = TPF::get_thread_range_parallel_scan_team_policy(ncol, nlev_packs);

  Kokkos::parallel_for(scan_policy, KOKKOS_LAMBDA (const VT::MemberType& team) {
    const int i = team.league_rank();

    auto z_mid_i = ekat::subview(z_mid, i);
    auto dz_i    = ekat::subview(dz, i);
    auto z_int_i = ekat::subview(z_int, i);
    Real z_surf  = 0.0;

    PF::calculate_z_int(team, nz, dz_i, z_surf, z_int_i);
    team.team_barrier();
    PF::calculate_z_mid(team, nz, z_int_i, z_mid_i);
    team.team_barrier();
  });
}

// qneg_run is deliberately absent from this header: confirmed structurally
// superseded (EAMxx's own postcondition checks) -- nothing will ever call a
// native replacement for it, and unlike geopotential_temp_run there is no
// existing hand-written EAMxx computation worth extracting here (the
// postcondition-check mechanism it's replaced by isn't a per-column
// numerical computation at all).

} // namespace ccpp_native
} // namespace scream

#endif // SCREAM_CCPP_NATIVE_UTILITIES_HPP
