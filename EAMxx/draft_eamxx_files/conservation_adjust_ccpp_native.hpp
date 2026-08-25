#ifndef SCREAM_CCPP_NATIVE_CONSERVATION_ADJUST_HPP
#define SCREAM_CCPP_NATIVE_CONSERVATION_ADJUST_HPP

// Draft of EAMxx-bridge-automation.md's Phase D.4 for the `conservation_adjust`
// package (atmospheric_physics/schemes/conservation_adjust/check_energy/,
// dme_adjust/) -- shared across kessler, cam4, cam7, adiabatic, and tj2016.
//
// STATUS: draft/exploratory, empty-bodied. See utilities_ccpp_native.hpp's
// header comment for the shared conventions (whole-array Kokkos::View
// arguments, void return, bare-line call site, no per-point form).
//
// check_energy_zero_fluxes_run and check_energy_chng_run(+_timestep_init) are
// deliberately absent: both confirmed structurally superseded by EAMxx's
// energy fixer via HOMME, and check_energy_chng additionally could never be
// ported regardless (its own source: "non-portable due to dependencies on
// cam_thermo").

#include "eamxx_ccpp_view_types.hpp"

namespace scream {
namespace ccpp_native {

using VT = ccpp::DefaultCCPPViewTypes;
using Pack = VT::Pack;

// check_energy_fix_run. Argument list approximate (evidence: `ptend_s =
// heat_glob` scalar broadcast; `eshflx` from two fixed interface-pressure
// levels) -- verify against
// atmospheric_physics/schemes/conservation_adjust/check_energy/check_energy_fix.F90.
KOKKOS_INLINE_FUNCTION
static void apply_energy_fix(int ncol, int nz,
                              Real heat_glob,
                              const VT::view_2d<Pack>& pint,
                              Real gravit,
                              VT::view_2d<Pack>& ptend_s,
                              VT::view_1d<Real>& eshflx) {
  // TODO: one-time hand port. SIGNATURE SKETCH -- verify against source.
}

// check_energy_save_teout_run: teout(:ncol) = te_cur_dyn(:ncol), a bare
// per-column copy.
KOKKOS_INLINE_FUNCTION
static void save_teout(int ncol,
                        const VT::view_1d<Real>& te_cur_dyn,
                        VT::view_1d<Real>& teout) {
  // TODO: one-time hand port of check_energy_save_teout_run.
}

// check_energy_scaling_run (verified in full this session):
//   scaling_dycore(:ncol,:) = cpairv(:ncol,:) / cp_or_cv_dycore(:ncol,:)
// [confirmed superseded for its physics_before_coupler use in Kessler's
// suite ("taken care of by HOMME"); unconfirmed for its physics_after_coupler
// use in cam4/cam7/tj2016 -- same function either way, trivially portable
// regardless of which supersession claim turns out right].
KOKKOS_INLINE_FUNCTION
static void compute_dycore_energy_scaling(int ncol, int nz,
                                           const VT::view_2d<Pack>& cp_or_cv_dycore,
                                           const VT::view_2d<Pack>& cpairv,
                                           VT::view_2d<Pack>& scaling_dycore) {
  // TODO: one-time hand port of check_energy_scaling_run.
}

// dycore_energy_consistency_adjust_run (verified in full this session):
//   if (do_consistency_adjust) tend_dTdt_local(:ncol,:) =
//       (scaling_dycore(:ncol,:) - 1) * tend_dTdt(:ncol,:)
// [unconfirmed -- Kessler's bridge comment hedges "pretty sure eamxx does
// this with the energy fixer... TODO ?"].
KOKKOS_INLINE_FUNCTION
static void apply_dycore_energy_consistency_adjust(int ncol, int nz,
                                                     bool do_consistency_adjust,
                                                     const VT::view_2d<Pack>& scaling_dycore,
                                                     const VT::view_2d<Pack>& tend_dTdt,
                                                     VT::view_2d<Pack>& tend_dTdt_local) {
  // TODO: one-time hand port of dycore_energy_consistency_adjust_run.
}

// check_energy_zero_fluxes_run [confirmed superseded, "taken care of by
// HOMME"] -- kept here (unlike qneg/geopotential_temp in
// utilities_ccpp_native.hpp) only because it's the one member of the
// check_energy_* trio that ISN'T also independently non-portable on its own
// merits (check_energy_chng is). Trivial to implement if ever needed; not
// expected to actually be called.
KOKKOS_INLINE_FUNCTION
static void zero_energy_check_fluxes(int ncol,
                                      VT::view_1d<Real>& flx_vap,
                                      VT::view_1d<Real>& flx_cnd,
                                      VT::view_1d<Real>& flx_ice,
                                      VT::view_1d<Real>& flx_sen) {
  // TODO: one-time hand port of check_energy_zero_fluxes_run (only if the
  // "confirmed superseded" classification above turns out wrong for some
  // future suite).
}

// dme_adjust_run -- COLUMN-SCAN, not pointwise: pint(:,k+1) = pint(:,k) +
// pdel(:,k) inside a do k=1,pver loop (level k+1 depends on the just-updated
// pint at level k), plus a per-level, per-constituent mass-conservation
// adjustment. Early-returns entirely if not moist-dycore. Argument list
// approximate -- verify against
// atmospheric_physics/schemes/conservation_adjust/dme_adjust/dme_adjust.F90.
// Because this is a column-scan, the hand-ported body needs a *team* policy
// (one team per column), not the flat range-parallel form the pointwise
// functions above can use -- same team+scan signature family PF:: already
// has a template for (PF::calculate_z_int/calculate_z_mid).
KOKKOS_INLINE_FUNCTION
static void adjust_dry_mass_and_energy(const VT::MemberType& team,
                                        int ncol, int nz,
                                        bool is_dycore_moist,
                                        const VT::view_2d<Pack>& pdel,
                                        VT::view_2d<Pack>& pint,
                                        VT::view_2d<Pack>& lnpint /* , constituent args TBD */) {
  // TODO: one-time hand port. SIGNATURE SKETCH -- verify against source,
  // especially the per-constituent mass-adjustment arguments this omits.
}

} // namespace ccpp_native
} // namespace scream

#endif // SCREAM_CCPP_NATIVE_CONSERVATION_ADJUST_HPP
