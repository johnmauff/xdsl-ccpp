! Minimal stand-in for the real ccpp_kinds.F90 that xdsl_ccpp's own
! generate_kinds.py normally emits into a cap-generated build directory
! (see xdsl_ccpp/transforms/generate_kinds.py). This standalone Fortran
! test program is deliberately independent of any CCPP scheme or the
! Python pipeline (per the scheme-io-capture plan's PR 2 scope), so it
! provides its own copy here rather than running the generator -- content
! copied verbatim from a real generated instance
! (build_debug/examples/kessler/plain/ccpp_kinds.F90).
module ccpp_kinds
  use ISO_FORTRAN_ENV, only: kind_phys => REAL64

  implicit none
  private

  public :: kind_phys
end module ccpp_kinds
