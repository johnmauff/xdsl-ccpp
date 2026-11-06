! Capture test drivers only (scheme-io-capture-share-code): a stand-in for
! CESM share's shr_log_mod, which needs ESMF. It provides only what the
! physics schemes' sources use (to_be_ccppized/linear_1d_operators.F90:
! shr_log_errMsg), with the real interface. Never part of a model build.
module shr_log_mod

  implicit none
  private

  public :: shr_log_errMsg

contains

  ! The real message ("ERROR in <file> at line <line>"); 512 is
  ! shr_kind_mod's SHR_KIND_CX.
  pure function shr_log_errMsg(file, line)
    character(len=512) :: shr_log_errMsg
    character(len=*), intent(in) :: file
    integer, intent(in) :: line

    write(shr_log_errMsg, '(a, a, a, i0)') 'ERROR in ', trim(file), ' at line ', line
  end function shr_log_errMsg

end module shr_log_mod
