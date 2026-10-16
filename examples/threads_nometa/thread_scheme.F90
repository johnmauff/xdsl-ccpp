!>\file thread_scheme.F90
!! This file contains a thread_scheme CCPP scheme that does nothing
!! except verifying it was called with the correct per-thread data,
!! proving the thread_number/number_of_threads scalar-index substitution
!! correctly indexed the HOST-owned per-thread container DDT.
!!
!! dup-meta-shadow-elim (BACKLOG.md): this is the tag-based twin of
!! examples/threads' own thread_scheme.F90 -- identical behavior, but
!! standard_name/long_name/units live here as !$ccpp tags instead of in a
!! hand-maintained thread_scheme.meta. See examples/threads_nometa's own
!! README.md and CMakeLists.txt for how .meta gets generated from this
!! file at configure time instead of being committed.

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
    !$ccpp [errmsg] standard_name = ccpp_error_message  &
    !$ccpp          long_name = error message for error handling in CCPP &
    !$ccpp          units = none

    integer, intent(out) :: errflg
    !$ccpp [errflg] standard_name = ccpp_error_code
    !$ccpp [errflg] long_name = error code for error handling in CCPP
    !$ccpp [errflg] units = 1

    integer, intent(in) :: thread
    !$ccpp [thread] standard_name = thread_number
    !$ccpp [thread] long_name = thread number for testing multi-thread support
    !$ccpp [thread] units = index

    real(kind=kind_phys), intent(inout) :: data_array(:)
    !$ccpp [data_array] standard_name = data_array
    !$ccpp [data_array] long_name = per-thread data array
    !$ccpp [data_array] units = m
    !$ccpp [data_array] dim_names = horizontal_dimension

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
