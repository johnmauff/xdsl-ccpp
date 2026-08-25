#ifndef SCREAM_CCPP_NATIVE_KESSLER_HPP
#define SCREAM_CCPP_NATIVE_KESSLER_HPP

// Draft of EAMxx-bridge-automation.md's Phase D.4 for the `kessler` package's
// own Kessler-specific candidates -- kessler_run itself stays on the Fortran
// chost-cap path (Phase A/B/C: genuinely needs Fortran, CFL-adaptive
// subcycling), so this header is much smaller than utilities/
// conservation_adjust's -- only kessler_update's three lifecycle functions
// qualify, everything else Kessler's own suite needs
// (compute_exner/compute_theta_from_temp/check_energy_*/dycore_energy_consistency_adjust)
// lives in the shared utilities_ccpp_native.hpp / conservation_adjust_ccpp_native.hpp
// headers instead, since those schemes are reused by cam4/cam7/adiabatic/tj2016 too.
//
// STATUS: draft/exploratory, empty-bodied. See utilities_ccpp_native.hpp's
// header comment for the shared conventions.

#include "eamxx_ccpp_view_types.hpp"

namespace scream {
namespace ccpp_native {

using VT = ccpp::DefaultCCPPViewTypes;
using Pack = VT::Pack;

// kessler_update_timestep_init (verified in full this session):
//   temp_prev(:,:) = temp(:,:); ttend_t(:,:) = 0
KOKKOS_INLINE_FUNCTION
static void kessler_update_timestep_init(int ncol, int nz,
                                          const VT::view_2d<Pack>& temp,
                                          VT::view_2d<Pack>& temp_prev,
                                          VT::view_2d<Pack>& ttend_t) {
  // TODO: one-time hand port of kessler_update_timestep_init.
}

// kessler_update_run (verified in full this session):
//   new_temp = theta*exner
//   ttend_t += (new_temp - temp_prev) / dt
KOKKOS_INLINE_FUNCTION
static void kessler_update_back_out_tendency(int ncol, int nz,
                                              Real dt,
                                              const VT::view_2d<Pack>& theta,
                                              const VT::view_2d<Pack>& exner,
                                              const VT::view_2d<Pack>& temp_prev,
                                              VT::view_2d<Pack>& ttend_t) {
  // TODO: one-time hand port of kessler_update_run.
}

// kessler_update_timestep_final (verified in full this session):
//   st_energy(:,k) = temp(:,k)*cpair(:,k) + gravit*zm(:,k) + phis(:)
// NOTE: the real Fortran reads `gravit` from kessler_update's own private
// module state (set once by kessler_update_init), not as an argument --
// porting to a device function means passing it explicitly instead, a
// trivial signature change with no semantic difference.
KOKKOS_INLINE_FUNCTION
static void kessler_update_static_energy(int ncol, int nz,
                                          const VT::view_2d<Pack>& cpair,
                                          const VT::view_2d<Pack>& temp,
                                          const VT::view_2d<Pack>& zm,
                                          const VT::view_1d<Real>& phis,
                                          Real gravit,
                                          VT::view_2d<Pack>& st_energy) {
  // TODO: one-time hand port of kessler_update_timestep_final.
}

// kessler_run itself is deliberately absent: genuinely needs Fortran (Phase
// A/B/C's whole reason for existing -- adaptive CFL-driven subcycling,
// sedimentation flux dependent on neighboring levels, terminal velocity
// re-evaluated every subcycle). Stays on the chost-cap bridge path.

} // namespace ccpp_native
} // namespace scream

#endif // SCREAM_CCPP_NATIVE_KESSLER_HPP
