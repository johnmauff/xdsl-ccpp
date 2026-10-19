!Hello demonstration parameterization
!

MODULE temp_adjust

  USE ccpp_kinds, ONLY: kind_phys

  IMPLICIT NONE
  PRIVATE

  PUBLIC :: temp_adjust_init
  PUBLIC :: temp_adjust_run
  PUBLIC :: temp_adjust_finalize

CONTAINS

!> \section arg_table_temp_adjust_run  Argument Table
!! \htmlinclude arg_table_temp_adjust_run.html
!!
  SUBROUTINE temp_adjust_run(nbox, lev, temp_layer,    &
    timestep, errmsg, errflg)
!----------------------------------------------------------------
   IMPLICIT NONE
!----------------------------------------------------------------

   integer,            intent(in)    :: nbox, lev
   !$ccpp [nbox] standard_name = horizontal_dimension &
   !$ccpp        units = count
   !$ccpp [lev] standard_name = vertical_layer_dimension &
   !$ccpp       units = count
   REAL(kind_phys),    intent(inout) :: temp_layer(:, :)
   !$ccpp [temp_layer] standard_name = potential_temperature &
   !$ccpp              units = K &
   !$ccpp              dim_names = horizontal_dimension,vertical_layer_dimension
   real(kind_phys),    intent(in)    :: timestep
   !$ccpp [timestep] standard_name = time_step_for_physics &
   !$ccpp            long_name = time step &
   !$ccpp            units = s
   character(len=512), intent(out)   :: errmsg
   !$ccpp [errmsg] standard_name = ccpp_error_message &
   !$ccpp          long_name = Error message for error handling in CCPP &
   !$ccpp          units = none
   integer,            intent(out)   :: errflg
   !$ccpp [errflg] standard_name = ccpp_error_code &
   !$ccpp          long_name = Error flag for error handling in CCPP &
   !$ccpp          units = 1
!----------------------------------------------------------------

   integer :: box_index
   integer :: lev_index

    errmsg = ''
    errflg = 0

    do box_index = 1, nbox
       do lev_index = 1, lev
          temp_layer(box_index, lev_index) = temp_layer(box_index, lev_index) &
               + 1.0_kind_phys
       end do
    end do

  END SUBROUTINE temp_adjust_run

!> \section arg_table_temp_adjust_init  Argument Table
!! \htmlinclude arg_table_temp_adjust_init.html
!!
  subroutine temp_adjust_init (errmsg, errflg)

    character(len=512),      intent(out)   :: errmsg
    !$ccpp [errmsg] standard_name = ccpp_error_message &
    !$ccpp          long_name = Error message for error handling in CCPP &
    !$ccpp          units = none
    integer,                 intent(out)   :: errflg
    !$ccpp [errflg] standard_name = ccpp_error_code &
    !$ccpp          long_name = Error flag for error handling in CCPP &
    !$ccpp          units = 1

    ! This routine currently does nothing

    errmsg = ''
    errflg = 0

  end subroutine temp_adjust_init

!> \section arg_table_temp_adjust_finalize  Argument Table
!! \htmlinclude arg_table_temp_adjust_finalize.html
!!
  subroutine temp_adjust_finalize (errmsg, errflg)

    character(len=512),      intent(out)   :: errmsg
    !$ccpp [errmsg] standard_name = ccpp_error_message &
    !$ccpp          long_name = Error message for error handling in CCPP &
    !$ccpp          units = none
    integer,                 intent(out)   :: errflg
    !$ccpp [errflg] standard_name = ccpp_error_code &
    !$ccpp          long_name = Error flag for error handling in CCPP &
    !$ccpp          units = 1

    ! This routine currently does nothing

    errmsg = ''
    errflg = 0

  end subroutine temp_adjust_finalize

END MODULE temp_adjust
