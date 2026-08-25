#include "eamxx_xdsl_process_interface.hpp"

#include <ekat_team_policy_utils.hpp>
#include <ekat_assert.hpp>
#include <ekat_units.hpp>

namespace scream
{

// =========================================================================================
XdslGeneratedProcess::XdslGeneratedProcess (const ekat::Comm& comm, const ekat::ParameterList& params)
  : AtmosphereProcess(comm, params)
{
  // Do nothing -- a generator would emit any suite-level constructor setup here.
}

// =========================================================================================
void XdslGeneratedProcess::create_requests()
{
  // TODO(xdsl-ccpp): emit one add_field<Required/Updated/Computed>() / add_tracer<>()
  // call per host-facing CCPP variable in the target suite (Phase C's field/tracer
  // classification gap -- see EAMxx-bridge-automation.md).
}

// =========================================================================================
void XdslGeneratedProcess::initialize_impl (const RunType /* run_type */)
{
  // TODO(xdsl-ccpp): emit calls into the suite's *_physics_initial entry point(s)
  // (eight-phase lifecycle, Phase A0), and/or into Phase D.3 native device functions.
}

// =========================================================================================
void XdslGeneratedProcess::run_impl (const double /* dt */)
{
  // TODO(xdsl-ccpp): emit the suite's per-timestep call sequence.
  //
  // HARD CONSTRAINT (2026-08-25): this function -- and every function this
  // generator ever emits into an EAMxx AtmosphereProcess -- must never contain
  // a Kokkos::parallel_for or a raw index loop of its own. Every D.3/D.4
  // native device function takes WHOLE-ARRAY Kokkos::View arguments and does
  // its own internal looping, exactly like TMSFunctions::compute_tms, not
  // like PF::exner_function's per-point form. So the generated call sequence
  // here is a flat list of bare-line, whole-array calls -- never a loop
  // wrapping a per-point call -- e.g., for a scheme D.2 classifies as
  // pointwise/elemental:
  //
  //   const auto p_mid = get_field_in("p_mid").get_view<const Pack**>();
  //   const auto exner = m_buffer.exner;
  //   ccpp_native::compute_exner(m_num_cols, m_num_levs, cpair, rair, ref_pres,
  //                              p_mid, exner);
  //
  // one call per scheme, in suite order, using this file's VT/Pack aliases and
  // the D.4 headers under EAMxx/draft_eamxx_files/ (utilities_ccpp_native.hpp,
  // conservation_adjust_ccpp_native.hpp, kessler_ccpp_native.hpp, ...) -- never
  // a Fortran bridge call plus params_helpers/params_computed transpose glue.
  // For a scheme that still needs the Fortran bridge (e.g. kessler_run
  // itself), this is instead a call into the generated
  // Kessler_chost_physics_*-style entry point (Phase A/B/C) -- also one bare
  // line, also no loop, since that call crosses into Fortran which owns its
  // own column loop internally, same principle as the native case.
}

// =========================================================================================
void XdslGeneratedProcess::finalize_impl()
{
  // TODO(xdsl-ccpp): emit calls into the suite's *_physics_final entry point(s), if any.
}

// =========================================================================================
size_t XdslGeneratedProcess::requested_buffer_size_in_bytes() const
{
  // TODO(xdsl-ccpp): only nonzero if this process still needs Fortran-bridge transpose
  // buffers (Phase A/B/C). A process built entirely on Phase D.3 native device
  // functions needs no buffer at all.
  return 0;
}

// =========================================================================================
void XdslGeneratedProcess::init_buffers(const ATMBufferManager &/* buffer_manager */)
{
  // TODO(xdsl-ccpp): see requested_buffer_size_in_bytes() above.
}

} // namespace scream
