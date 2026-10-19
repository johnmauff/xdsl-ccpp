!Hello demonstration parameterization
!

MODULE hello_scheme

  USE ccpp_kinds, ONLY: kind_phys, kind_dyn

  IMPLICIT NONE
  PRIVATE

  PUBLIC :: hello_scheme_init
  PUBLIC :: hello_scheme_run
  PUBLIC :: hello_scheme_finalize

CONTAINS

!> \section arg_table_hello_scheme_run  Argument Table
!! \htmlinclude arg_table_hello_scheme_run.html
!!
  SUBROUTINE hello_scheme_run(ncol, lev, ilev, timestep, temp_level,          &
       temp_layer, errmsg, errflg)
!----------------------------------------------------------------
   IMPLICIT NONE
!----------------------------------------------------------------

   integer,            intent(in)    :: ncol, lev, ilev
   !$ccpp [ncol] standard_name = horizontal_dimension &
   !$ccpp        units = count
   !$ccpp [lev] standard_name = vertical_layer_dimension &
   !$ccpp       units = count
   !$ccpp [ilev] standard_name = vertical_interface_dimension &
   !$ccpp        units = count
   REAL(kind_dyn),     intent(inout) :: temp_level(:, :)
   !$ccpp [temp_level] standard_name = potential_temperature_at_interface &
   !$ccpp              units = K &
   !$ccpp              dim_names = ccpp_constant_one:horizontal_dimension,vertical_interface_dimension
   real(kind_phys),    intent(in)    :: timestep
   !$ccpp [timestep] standard_name = time_step_for_physics &
   !$ccpp            long_name = time step &
   !$ccpp            units = s
   REAL(kind_phys),    INTENT(out)   :: temp_layer(:, :)
   !$ccpp [temp_layer] standard_name = potential_temperature &
   !$ccpp              units = K &
   !$ccpp              dim_names = horizontal_dimension,vertical_layer_dimension
   character(len=512), intent(out)   :: errmsg
   !$ccpp [errmsg] standard_name = ccpp_error_message &
   !$ccpp          long_name = Error message for error handling in CCPP &
   !$ccpp          units = none
   integer,            intent(out)   :: errflg
   !$ccpp [errflg] standard_name = ccpp_error_code &
   !$ccpp          long_name = Error flag for error handling in CCPP &
   !$ccpp          units = 1
!----------------------------------------------------------------

   integer :: col_index
   integer :: lev_index

    errmsg = ''
    errflg = 0

    if (ilev /= (lev + 1)) then
       errflg = 1
       errmsg = 'Invalid value for ilev, must be lev+1'
       return
    end if

    do col_index = 1, ncol
       do lev_index = 1, lev
          temp_layer(col_index, lev_index) = (temp_level(col_index, lev_index) &
               + temp_level(col_index, lev_index + 1)) / 2.0_kind_dyn
       end do
    end do

  END SUBROUTINE hello_scheme_run

!> \section arg_table_hello_scheme_init  Argument Table
!! \htmlinclude arg_table_hello_scheme_init.html
!!
  subroutine hello_scheme_init (errmsg, errflg)

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

  end subroutine hello_scheme_init

!> \section arg_table_hello_scheme_finalize  Argument Table
!! \htmlinclude arg_table_hello_scheme_finalize.html
!!
  subroutine hello_scheme_finalize (errmsg, errflg)

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

  end subroutine hello_scheme_finalize

END MODULE hello_scheme
