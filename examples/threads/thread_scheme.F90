!>\file thread_scheme.F90
!! This file contains a thread_scheme CCPP scheme that does nothing
!! except verifying it was called with the correct per-thread data,
!! proving the thread_number/number_of_threads scalar-index substitution
!! correctly indexed the HOST-owned per-thread container DDT.

module thread_scheme

  use, intrinsic :: iso_fortran_env, only: error_unit
  use ccpp_kinds, only : kind_phys
  implicit none

  private
  public :: thread_scheme_run

  ! This is for unit testing only
  real(kind=kind_phys), parameter, dimension(1:2) :: target_values = (/-1.0_kind_phys, 1.0_kind_phys/)

contains

  !! \section arg_table_thread_scheme_run Argument Table
  !! \htmlinclude thread_scheme_run.html
  !!
  subroutine thread_scheme_run(thread, data_array, errmsg, errflg)
    character(len=*), intent(out) :: errmsg
    integer, intent(out) :: errflg
    integer, intent(in) :: thread
    real(kind=kind_phys), intent(inout) :: data_array(:)

    ! Initialize CCPP error handling variables
    errmsg = ''
    errflg = 0

    ! Check values in data array -- confirms thread_data(thread)%data_array
    ! was correctly indexed by this call's own thread_number argument, not
    ! some other thread's entry or an unindexed reference.
    write(error_unit, '(a,e12.4)') &
        'In thread_scheme_run: checking min/max values of data array to be approximately ', &
        target_values(thread)
    if (abs(minval(data_array) - target_values(thread)) > 0.01_kind_phys .or. &
        abs(maxval(data_array) - target_values(thread)) > 0.01_kind_phys) then
      write(errmsg, '(3(a,e12.4),a)') &
          "Error in thread_scheme_run, expected values for data_array of approximately ", &
          target_values(thread), "  but got [ ", minval(data_array), " : ", maxval(data_array), " ]"
      errflg = 1
      return
    end if

  end subroutine thread_scheme_run

end module thread_scheme
