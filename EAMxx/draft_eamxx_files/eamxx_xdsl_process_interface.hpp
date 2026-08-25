#ifndef SCREAM_XDSL_PROCESS_HPP
#define SCREAM_XDSL_PROCESS_HPP

#include "eamxx_ccpp_view_types.hpp"
#include "share/atm_process/atmosphere_process.hpp"
#include "share/atm_process/ATMBufferManager.hpp"

#include "share/physics/physics_constants.hpp"
#include "share/physics/eamxx_common_physics_functions.hpp"

// D.4 device-function headers: a real generated process includes only the
// ones its own suite actually calls into. utilities/conservation_adjust are
// shared across nearly every suite; add a per-package one
// (e.g. kessler_ccpp_native.hpp) alongside them as needed.
// #include "utilities_ccpp_native.hpp"
// #include "conservation_adjust_ccpp_native.hpp"

#include <ekat_parameter_list.hpp>

#include <string>

namespace scream
{

/*
 * Draft skeleton for an EAMxx AtmosphereProcess targeted by xdsl-ccpp's Phase C/D
 * pipeline (see EAMxx/EAMxx-bridge-automation.md). Modeled on the existing
 * TurbulentMountainStress process (physics/tms), since that process is EAMxx's
 * cleanest existing example of the Phase D target architecture: no Fortran bridge,
 * no params_helpers/params_computed transpose glue, just direct calls into shared
 * C++ device functions.
 *
 * This file is intentionally not a working process -- every method body is empty or
 * a TODO placeholder, it is not added to any CMakeLists.txt, and "Xdsl"/"xdsl_..."
 * naming is a placeholder for whatever a real generated suite/process is actually
 * called. It exists to pin down the includes, namespace, and base-class surface a
 * generated (or hand-written, Phase-D-style) process needs.
 *
 * The AD should store exactly ONE instance of this class in its list of
 * subcomponents (the AD should make sure of this).
 */
class XdslGeneratedProcess : public AtmosphereProcess
{
public:
  // Shared view/type aliases (Phase D.1) -- see eamxx_ccpp_view_types.hpp. A real
  // generated process should pull its Pack/view aliases from here rather than
  // re-declaring them locally, the way kessler_functions.hpp/zm_functions.hpp do today.
  using VT = ccpp::DefaultCCPPViewTypes;
  using PF = scream::PhysicsFunctions<DefaultDevice>;
  using PC = scream::physics::Constants<Real>;

  using Pack    = VT::Pack;
  using IntPack = VT::IntPack;

  // Constructors
  XdslGeneratedProcess (const ekat::Comm& comm, const ekat::ParameterList& params);

  // The type of subcomponent
  AtmosphereProcessType type () const override { return AtmosphereProcessType::Physics; }

  // The name of the subcomponent -- a generator should fill this in from the suite name.
  std::string name () const override { return "xdsl_generated_process"; }

  // Create grid-dependent field requests -- a generator should emit one
  // add_field<Required/Updated/Computed>() / add_tracer<>() call here per host-facing
  // CCPP variable in the target suite (see Phase C's field-classification gap).
  void create_requests() override;

#ifndef KOKKOS_ENABLE_CUDA
  // Cuda requires methods enclosing __device__ lambdas to be public.
  protected:
#endif
    void initialize_impl(const RunType run_type) override;
    void run_impl(const double dt) override;
  protected:
    void finalize_impl() override;

    // Computes bytes needed in buffers. Only relevant for schemes still requiring the
    // Fortran-bridge transpose apparatus (Phase A/B/C); a process built entirely on
    // Phase D.3 native device functions should not need any buffer at all.
    size_t requested_buffer_size_in_bytes() const;

    // Set the variables using memory provided by the ATMBufferManager.
    void init_buffers(const ATMBufferManager &buffer_manager);

    // Keep track of field dimensions
    std::shared_ptr<const AbstractGrid> m_grid;
    int m_num_cols;
    int m_num_levs;

}; // class XdslGeneratedProcess

} // namespace scream

#endif // SCREAM_XDSL_PROCESS_HPP
