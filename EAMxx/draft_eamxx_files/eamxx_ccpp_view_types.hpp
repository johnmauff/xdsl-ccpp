#ifndef SCREAM_CCPP_VIEW_TYPES_HPP
#define SCREAM_CCPP_VIEW_TYPES_HPP

// Draft of EAMxx-bridge-automation.md's Phase D.1: a single, shared set of Kokkos
// view/type aliases for CCPP-derived EAMxx processes to include, instead of every
// process (kessler_functions.hpp, zm_functions.hpp, ...) re-declaring the same
// Pack/IntPack/view_2d/fview_* aliases locally, verbatim, from the same underlying
// ekat::Pack<Scalar,SCREAM_PACK_SIZE>/ekat::KokkosTypes<Device>. Nothing here is a new
// convention -- it consolidates the one that's already consistent across processes.
//
// This is a draft only: not wired into any CMakeLists.txt, not yet used by a real
// process interface. See eamxx_xdsl_process_interface.hpp/.cpp in this same directory
// for how a process would consume it.

#include "share/core/eamxx_types.hpp"

#include <ekat_pack_kokkos.hpp>
#include <ekat_team_policy_utils.hpp>

namespace scream {
namespace ccpp {

// Most EAMxx physics packages instantiate this with <Real, DefaultDevice>; ScalarT/DeviceT
// stay template parameters (mirroring KesslerMicrophysicsFunctions's existing convention)
// so the same aliases still work for a host-mirror or alternate-precision instantiation.
template <typename ScalarT, typename DeviceT>
struct CCPPViewTypes
{
  using Scalar = ScalarT;
  using Device = DeviceT;

  using Pack    = ekat::Pack<Scalar, SCREAM_PACK_SIZE>;
  using IntPack = ekat::Pack<Int, SCREAM_PACK_SIZE>;

  using KT         = ekat::KokkosTypes<Device>;
  using MemberType = typename KT::MemberType;
  using TeamPolicy  = typename KT::TeamPolicy;

  // "Native" (device-preferred-layout) views -- what a Phase D.3 pure-C++ device
  // function and its caller should exchange.
  template <typename S> using view_1d = typename KT::template view_1d<S>;
  template <typename S> using view_2d = typename KT::template view_2d<S>;
  template <typename S> using view_3d = typename KT::template view_3d<S>;

  template <typename S> using uview_1d = typename ekat::template Unmanaged<view_1d<S>>;
  template <typename S> using uview_2d = typename ekat::template Unmanaged<view_2d<S>>;

  // Left ("Fortran"/column-major) layout views, needed only at the chost-cap boundary
  // for schemes still going through a Fortran bridge (see Phase A/B/C). A process built
  // entirely on Phase D.3 native device functions should never need these.
  template <typename S> using lview_2d = typename KT::template lview<S**>;

#if defined(EAMXX_ENABLE_GPU) && !defined(EAMXX_ENABLE_OPENACC)
  // Fortran itself has no OpenACC to keep it resident on device here, so the "f_*"
  // holders passed across the chost-cap boundary must live on the host, with a
  // device-side view plus a Kokkos::deep_copy on either side of the Fortran call
  // (see kessler_functions.hpp's params_helpers/params_computed::transpose()).
  template <typename S> using fview_1d  = uview_1d<S>;
  template <typename S> using fview_2d  = uview_2d<S>;
  template <typename S> using fview_2dl = typename ekat::template Unmanaged<lview_2d<S>>;
  template <typename S> using view_1dh  = typename view_1d<S>::HostMirror;
  template <typename S> using view_2dh  = typename lview_2d<S>::HostMirror;
#else
  // With OpenACC (or on CPU), the Fortran side can operate on the same device views
  // directly -- no host mirror, no deep_copy.
  template <typename S> using fview_1d  = view_1d<S>;
  template <typename S> using fview_2d  = view_2d<S>;
  template <typename S> using fview_2dl = lview_2d<S>;
#endif
};

// Convenience alias for the instantiation essentially every process actually uses.
using DefaultCCPPViewTypes = CCPPViewTypes<Real, DefaultDevice>;

} // namespace ccpp
} // namespace scream

#endif // SCREAM_CCPP_VIEW_TYPES_HPP
