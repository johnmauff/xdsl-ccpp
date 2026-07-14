! BIND(C) cap for a C++ host model calling the Kessler physics suite.
! All physics arrays are owned by the C++ caller and passed as explicit
! pointer arguments — kessler_host_mod is not used or linked.
! The underlying suite-cap state machine is reused for correct lifecycle
! ordering.
module Kessler_ccpp_chost_cap

  use ccpp_kinds,       only: kind_phys
  use iso_c_binding
  use kessler_suite_cap, only: kessler_suite_suite_initialize
  use kessler_suite_cap, only: kessler_suite_suite_finalize
  use kessler_suite_cap, only: kessler_suite_suite_timestep_initial
  use kessler_suite_cap, only: kessler_suite_suite_timestep_final
  use kessler_suite_cap, only: kessler_suite_suite_physics

  implicit none
  private

  public :: Kessler_chost_physics_initialize
  public :: Kessler_chost_physics_finalize
  public :: Kessler_chost_physics_timestep_initial
  public :: Kessler_chost_physics_run
  public :: Kessler_chost_physics_timestep_final
  public :: Kessler_chost_print_results

contains

  ! ---------------------------------------------------------------------------
  ! Initialize physics constants (kessler_init, kessler_update_init).
  ! ---------------------------------------------------------------------------
  subroutine Kessler_chost_physics_initialize(lv, pref, rhoqr, gravit, &
      errmsg, errflg) bind(C, name='Kessler_chost_physics_initialize')
    real(c_double),                value, intent(in)  :: lv, pref, rhoqr, gravit
    character(kind=c_char, len=1),        intent(out) :: errmsg(*)
    integer(c_int),                       intent(out) :: errflg
    integer :: i
    character(len=512) :: errmsg_f

    errmsg_f = ' '
    errflg   = 0
    call kessler_suite_suite_initialize(real(lv,    kind_phys), &
                                        real(pref,   kind_phys), &
                                        real(rhoqr,  kind_phys), &
                                        real(gravit, kind_phys), &
                                        errmsg_f, errflg)
    do i = 1, len_trim(errmsg_f)
      errmsg(i) = errmsg_f(i:i)
    end do
    errmsg(len_trim(errmsg_f)+1) = c_null_char
  end subroutine Kessler_chost_physics_initialize

  ! ---------------------------------------------------------------------------
  ! Finalize the physics suite.
  ! ---------------------------------------------------------------------------
  subroutine Kessler_chost_physics_finalize(errmsg, errflg) &
      bind(C, name='Kessler_chost_physics_finalize')
    character(kind=c_char, len=1), intent(out) :: errmsg(*)
    integer(c_int),                intent(out) :: errflg
    integer :: i
    character(len=512) :: errmsg_f

    errmsg_f = ' '
    errflg   = 0
    call kessler_suite_suite_finalize(errflg, errmsg_f)
    do i = 1, len_trim(errmsg_f)
      errmsg(i) = errmsg_f(i:i)
    end do
    errmsg(len_trim(errmsg_f)+1) = c_null_char
  end subroutine Kessler_chost_physics_finalize

  ! ---------------------------------------------------------------------------
  ! Timestep initial: copies temp -> temp_prev, zeroes ttend_t.
  ! Arrays are [ncol x nz] column-major.
  ! ---------------------------------------------------------------------------
  subroutine Kessler_chost_physics_timestep_initial(ncol, nz, &
      temp, temp_prev, ttend_t, errmsg, errflg) &
      bind(C, name='Kessler_chost_physics_timestep_initial')
    integer(c_int), value,        intent(in)    :: ncol, nz
    real(c_double), target,       intent(in)    :: temp(ncol, nz)
    real(c_double), target,       intent(inout) :: temp_prev(ncol, nz)
    real(c_double), target,       intent(inout) :: ttend_t(ncol, nz)
    character(kind=c_char, len=1),intent(out)   :: errmsg(*)
    integer(c_int),               intent(out)   :: errflg
    integer :: i
    character(len=512) :: errmsg_f

    errmsg_f = ' '
    errflg   = 0
    call kessler_suite_suite_timestep_initial(ncol, nz, temp, temp_prev, &
                                              ttend_t, errmsg_f, errflg)
    do i = 1, len_trim(errmsg_f)
      errmsg(i) = errmsg_f(i:i)
    end do
    errmsg(len_trim(errmsg_f)+1) = c_null_char
  end subroutine Kessler_chost_physics_timestep_initial

  ! ---------------------------------------------------------------------------
  ! Run physics: kessler microphysics + kessler_update.
  ! Arrays are [ncol x nz] column-major; precl is [ncol].
  ! scheme_name is a null-terminated output string (caller must provide >= 65 bytes).
  ! ---------------------------------------------------------------------------
  subroutine Kessler_chost_physics_run(ncol, nz, dt, lyr_surf, lyr_toa, &
      cpair, rair, rho, z, exner, theta, qv, qc, qr, precl, relhum, &
      temp_prev, ttend_t, scheme_name, errmsg, errflg) &
      bind(C, name='Kessler_chost_physics_run')
    integer(c_int), value,        intent(in)    :: ncol, nz, lyr_surf, lyr_toa
    real(c_double), value,        intent(in)    :: dt
    real(c_double), target,       intent(in)    :: cpair(ncol, nz)
    real(c_double), target,       intent(in)    :: rair(ncol, nz)
    real(c_double), target,       intent(in)    :: rho(ncol, nz)
    real(c_double), target,       intent(in)    :: z(ncol, nz)
    real(c_double), target,       intent(in)    :: exner(ncol, nz)
    real(c_double), target,       intent(inout) :: theta(ncol, nz)
    real(c_double), target,       intent(inout) :: qv(ncol, nz)
    real(c_double), target,       intent(inout) :: qc(ncol, nz)
    real(c_double), target,       intent(inout) :: qr(ncol, nz)
    real(c_double), target,       intent(inout) :: precl(ncol)
    real(c_double), target,       intent(inout) :: relhum(ncol, nz)
    real(c_double), target,       intent(in)    :: temp_prev(ncol, nz)
    real(c_double), target,       intent(inout) :: ttend_t(ncol, nz)
    character(kind=c_char, len=1),intent(out)   :: scheme_name(*)
    character(kind=c_char, len=1),intent(out)   :: errmsg(*)
    integer(c_int),               intent(out)   :: errflg
    integer :: i
    character(len=64)  :: scheme_name_f
    character(len=512) :: errmsg_f

    errmsg_f      = ' '
    scheme_name_f = ' '
    errflg        = 0
    call kessler_suite_suite_physics(1, ncol, nz, real(dt, kind_phys), &
        lyr_surf, lyr_toa, cpair, rair, rho, z, exner, theta, qv, qc, qr, &
        precl, relhum, temp_prev, ttend_t, scheme_name_f, errmsg_f, errflg)
    do i = 1, len_trim(scheme_name_f)
      scheme_name(i) = scheme_name_f(i:i)
    end do
    scheme_name(len_trim(scheme_name_f)+1) = c_null_char
    do i = 1, len_trim(errmsg_f)
      errmsg(i) = errmsg_f(i:i)
    end do
    errmsg(len_trim(errmsg_f)+1) = c_null_char
  end subroutine Kessler_chost_physics_run

  ! ---------------------------------------------------------------------------
  ! Timestep final: computes dry static energy.
  ! ---------------------------------------------------------------------------
  subroutine Kessler_chost_physics_timestep_final(ncol, nz, &
      cpair, temp, z, phis, st_energy, errmsg, errflg) &
      bind(C, name='Kessler_chost_physics_timestep_final')
    integer(c_int), value,        intent(in)    :: ncol, nz
    real(c_double), target,       intent(in)    :: cpair(ncol, nz)
    real(c_double), target,       intent(in)    :: temp(ncol, nz)
    real(c_double), target,       intent(in)    :: z(ncol, nz)
    real(c_double), target,       intent(in)    :: phis(ncol)
    real(c_double), target,       intent(inout) :: st_energy(ncol, nz)
    character(kind=c_char, len=1),intent(out)   :: errmsg(*)
    integer(c_int),               intent(out)   :: errflg
    integer :: i
    character(len=512) :: errmsg_f

    errmsg_f = ' '
    errflg   = 0
    call kessler_suite_suite_timestep_final(nz, ncol, cpair, temp, z, phis, &
                                            st_energy, errmsg_f, errflg)
    do i = 1, len_trim(errmsg_f)
      errmsg(i) = errmsg_f(i:i)
    end do
    errmsg(len_trim(errmsg_f)+1) = c_null_char
  end subroutine Kessler_chost_physics_timestep_final

  ! ---------------------------------------------------------------------------
  ! Print results using Fortran SUM — matches the format and reduction order
  ! of kessler_host_mod::print_results so output is bit-for-bit comparable.
  ! ---------------------------------------------------------------------------
  subroutine Kessler_chost_print_results(ncol, nz, scheme_name, elapsed_s, &
      theta, qv, qc, qr, precl, relhum, temp_prev, ttend_t, st_energy) &
      bind(C, name='Kessler_chost_print_results')
    integer(c_int), value,        intent(in) :: ncol, nz
    character(kind=c_char, len=1),intent(in) :: scheme_name(*)
    real(c_double), value,        intent(in) :: elapsed_s
    real(c_double),               intent(in) :: theta(ncol, nz)
    real(c_double),               intent(in) :: qv(ncol, nz)
    real(c_double),               intent(in) :: qc(ncol, nz)
    real(c_double),               intent(in) :: qr(ncol, nz)
    real(c_double),               intent(in) :: precl(ncol)
    real(c_double),               intent(in) :: relhum(ncol, nz)
    real(c_double),               intent(in) :: temp_prev(ncol, nz)
    real(c_double),               intent(in) :: ttend_t(ncol, nz)
    real(c_double),               intent(in) :: st_energy(ncol, nz)
    integer :: i
    character(len=64) :: scheme_name_f

    scheme_name_f = ' '
    do i = 1, len(scheme_name_f)
      if (scheme_name(i) == c_null_char) exit
      scheme_name_f(i:i) = scheme_name(i)
    end do

    print *, 'Scheme name: ',    trim(scheme_name_f)
    print *, 'theta: ',          SUM(theta)
    print *, 'qv: ',             SUM(qv)
    print *, 'qc: ',             SUM(qc)
    print *, 'qr: ',             SUM(qr)
    print *, 'Precip (m/s): ',   SUM(precl)
    print *, 'relnum: ',         SUM(relhum)
    print *, 'temp_prev: ',      SUM(temp_prev)
    print *, 'ttend_t: ',        SUM(ttend_t)
    print *, 'st_energy: ',      SUM(st_energy)
    print *, 'Elapsed time: (ms) ', elapsed_s / 1.e-3_kind_phys
  end subroutine Kessler_chost_print_results

end module Kessler_ccpp_chost_cap
