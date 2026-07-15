module kessler_chost_print_mod
  use ccpp_kinds, only: kind_phys
  use iso_c_binding
  implicit none
  private
  public :: Kessler_chost_print_results

contains

  ! Print physics results using Fortran SUM — output format matches
  ! kessler_host_mod::print_results so output is bit-for-bit comparable.
  subroutine Kessler_chost_print_results(ncol, nz, scheme_name, elapsed_s, &
      theta, qv, qc, qr, precl, relhum, temp_prev, ttend_t, st_energy) &
      bind(C, name='Kessler_chost_print_results')
    integer(c_int), value,         intent(in) :: ncol, nz
    character(kind=c_char, len=1), intent(in) :: scheme_name(*)
    real(c_double), value,         intent(in) :: elapsed_s
    real(c_double),                intent(in) :: theta(ncol, nz)
    real(c_double),                intent(in) :: qv(ncol, nz)
    real(c_double),                intent(in) :: qc(ncol, nz)
    real(c_double),                intent(in) :: qr(ncol, nz)
    real(c_double),                intent(in) :: precl(ncol)
    real(c_double),                intent(in) :: relhum(ncol, nz)
    real(c_double),                intent(in) :: temp_prev(ncol, nz)
    real(c_double),                intent(in) :: ttend_t(ncol, nz)
    real(c_double),                intent(in) :: st_energy(ncol, nz)
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

end module kessler_chost_print_mod
