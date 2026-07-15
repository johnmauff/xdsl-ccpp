! Thin BIND(C) bridges that let a C++ host drive kessler_host_mod without
! pulling in Fortran module interfaces on the C++ side.
!
! Three entry points:
!   kessler_host_init_data()         — calls kessler_host_mod::init_data()
!   kessler_host_print_results(s)    — calls kessler_host_mod::print_results(s)
!   kessler_host_setup(...)          — low-level scalar setter (bypasses init_data)
!
! All routines are standalone (not in a module) so they can be declared with
! plain extern "C" on the C++ side.

! ---------------------------------------------------------------------------
! Full initialisation: scalars + array allocation + Box-Muller fill.
! ---------------------------------------------------------------------------
subroutine kessler_host_init_data() bind(c, name='kessler_host_init_data')
  use kessler_host_mod, only: init_data
  implicit none
  call init_data()
end subroutine kessler_host_init_data

! ---------------------------------------------------------------------------
! Print sums of all output arrays plus wall-clock time.
! elapsed_s is in seconds; print_results internally converts to milliseconds.
! ---------------------------------------------------------------------------
subroutine kessler_host_print_results(elapsed_s) &
    bind(c, name='kessler_host_print_results')
  use iso_c_binding,    only: c_double
  use kessler_host_mod, only: print_results
  implicit none
  real(c_double), value, intent(in) :: elapsed_s
  call print_results(real(elapsed_s, kind=8))
end subroutine kessler_host_print_results

! ---------------------------------------------------------------------------
! Low-level scalar setter — populates kessler_host_mod module scalars
! individually. Useful when the caller supplies its own RNG and arrays but
! still needs the Fortran module scalars in place before physics_initialize.
! ---------------------------------------------------------------------------
subroutine kessler_host_setup(ncol_in, nz_in, dt_in,            &
                               lyr_surf_in, lyr_toa_in,         &
                               lv_in, pref_in, rhoqr_in, gravit_in) &
    bind(c, name='kessler_host_setup')

  use ccpp_kinds,       only: kind_phys
  use kessler_host_mod, only: ncol, nz, dt, lyr_surf, lyr_toa,  &
                               lv, pref, rhoqr, gravit
  implicit none

  integer,         value, intent(in) :: ncol_in, nz_in
  integer,         value, intent(in) :: lyr_surf_in, lyr_toa_in
  real(kind_phys), value, intent(in) :: dt_in
  real(kind_phys), value, intent(in) :: lv_in, pref_in, rhoqr_in, gravit_in

  ncol     = ncol_in
  nz       = nz_in
  dt       = dt_in
  lyr_surf = lyr_surf_in
  lyr_toa  = lyr_toa_in
  lv       = lv_in
  pref     = pref_in
  rhoqr    = rhoqr_in
  gravit   = gravit_in

end subroutine kessler_host_setup
