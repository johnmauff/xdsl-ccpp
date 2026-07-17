module nestedddt

  use ccpp_kinds, only: kind_phys

  implicit none
  private

  public :: nestedddt_run
  public :: inner_phys_t
  public :: outer_phys_t

  !> \section arg_table_inner_phys_t  Argument Table
  !! \htmlinclude arg_table_inner_phys_t.html
  !!
  type inner_phys_t
     integer                       :: nz
     real(kind_phys), allocatable :: temp(:,:)
  end type inner_phys_t

  !> \section arg_table_outer_phys_t  Argument Table
  !! \htmlinclude arg_table_outer_phys_t.html
  !!
  type outer_phys_t
     type(inner_phys_t) :: inner
  end type outer_phys_t

contains

  !> \section arg_table_nestedddt_run  Argument Table
  !! \htmlinclude arg_table_nestedddt_run.html
  !!
  subroutine nestedddt_run(cols, cole, state, errmsg, errflg)
    integer,            intent(in)    :: cols
    integer,            intent(in)    :: cole
    type(outer_phys_t), intent(inout) :: state
    character(len=512), intent(out)   :: errmsg
    integer,            intent(out)   :: errflg

    errmsg = ''
    errflg = 0

    ! Double all temperatures in the active column range.
    state%inner%temp(cols:cole, :) = state%inner%temp(cols:cole, :) * 2.0_kind_phys

  end subroutine nestedddt_run

end module nestedddt
