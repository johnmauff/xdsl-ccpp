! Capture test drivers only (scheme-io-capture-share-code): a stand-in for
! CESM share's shr_sys_mod, which needs ESMF (through shr_abort_mod). It
! provides only what the physics schemes' sources use
! (to_be_ccppized/linear_1d_operators.F90: shr_sys_abort), with the real
! interface. Reaching it ends the replay, which then fails. Never part of a
! model build.
module shr_sys_mod

  implicit none
  private

  public :: shr_sys_abort

contains

  subroutine shr_sys_abort(string, rc, line, file)
    character(len=*), intent(in), optional :: string
    integer, intent(in), optional :: rc
    integer, intent(in), optional :: line
    character(len=*), intent(in), optional :: file

    write(*, '(a)') 'shr_sys_abort called during a capture replay (xdsl_ccpp stub of shr_sys_mod)'
    if (present(string)) write(*, '(a)') trim(string)
    if (present(file) .and. present(line)) write(*, '(a, a, a, i0)') 'at ', trim(file), ':', line
    if (present(rc)) write(*, '(a, i0)') 'rc = ', rc
    error stop 1
  end subroutine shr_sys_abort

end module shr_sys_mod
