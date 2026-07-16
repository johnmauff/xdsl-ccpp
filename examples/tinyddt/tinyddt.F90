module tinyddt

  use ccpp_kinds, only: kind_phys

  implicit none
  private

  public :: tinyddt_run
  public :: tiny_state_t

  !> \section arg_table_tiny_state_t  Argument Table
  !! \htmlinclude arg_table_tiny_state_t.html
  !!
  type tiny_state_t
     integer                          :: nz
     real(kind_phys), allocatable :: temp(:,:)
  end type tiny_state_t

contains

  !> \section arg_table_tinyddt_run  Argument Table
  !! \htmlinclude arg_table_tinyddt_run.html
  !!
  subroutine tinyddt_run(cols, cole, state, errmsg, errflg)
    integer,            intent(in)    :: cols
    integer,            intent(in)    :: cole
    type(tiny_state_t), intent(inout) :: state
    character(len=512), intent(out)   :: errmsg
    integer,            intent(out)   :: errflg

    errmsg = ''
    errflg = 0

    ! Add 1 K to temperatures in the active column range (trivially verifiable).
    state%temp(cols:cole, :) = state%temp(cols:cole, :) + 1.0_kind_phys

  end subroutine tinyddt_run

end module tinyddt
