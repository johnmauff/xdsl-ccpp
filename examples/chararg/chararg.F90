! chararg — minimal scheme with a character(len=32) intent(in) argument.
! Used to test gap 9: chost cap generation for fixed-length character args.
module chararg

  use ccpp_kinds, only: kind_phys
  implicit none
  private
  public :: chararg_run

contains

  ! Scale temp(:, :) by 3.0 everywhere.
  ! The label arg is a fixed-length string passed from the C++ host; its
  ! value is not used by the physics but exercises the C→Fortran copy path.
  subroutine chararg_run(ncol, nz, temp, label, errmsg, errflg)
    integer,            intent(in)    :: ncol, nz
    real(kind_phys),    intent(inout) :: temp(:, :)
    character(len=32),  intent(in)    :: label
    character(len=512), intent(out)   :: errmsg
    integer,            intent(out)   :: errflg

    errflg = 0
    errmsg = ''

    if (len_trim(label) == 0) then
      errmsg = 'chararg_run: label must not be empty'
      errflg = 1
      return
    end if

    temp(1:ncol, :) = temp(1:ncol, :) * 3.0_kind_phys
  end subroutine chararg_run

end module chararg
