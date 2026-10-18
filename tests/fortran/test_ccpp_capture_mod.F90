! Standalone round-trip test for ccpp_capture_mod (PR 2 of the
! scheme-io-capture backlog item) -- compiled and run directly, independent
! of any CCPP scheme or the Python xdsl_ccpp pipeline. Exercises every
! (type, rank) combination the runtime library supports
! ({integer, logical, real(kind_phys)} x {rank 0..3}): write a known
! value, read it back, and confirm ccpp_capture_compare reports a match.
! Also confirms a deliberately-introduced mismatch is correctly flagged
! as a failure by the compare procedures, not silently accepted.
!
! Run from this directory:
!   gfortran -o test_ccpp_capture_mod ccpp_kinds.F90 \
!       ../../xdsl_ccpp/framework_src/ccpp_capture_mod.F90 \
!       test_ccpp_capture_mod.F90
!   ./test_ccpp_capture_mod
!
! Exits 0 and prints "ALL TESTS PASSED" on success; exits 1 and prints
! each failing case otherwise. Capture files are written into the current
! working directory and removed on a clean exit.
program test_ccpp_capture_mod
  use ccpp_kinds, only: kind_phys
  use ccpp_capture_mod, only: ccpp_capture, ccpp_capture_read, ccpp_capture_compare

  implicit none

  integer :: n_failed

  n_failed = 0

  call test_int_0d(n_failed)
  call test_int_1d(n_failed)
  call test_int_2d(n_failed)
  call test_int_3d(n_failed)
  call test_log_0d(n_failed)
  call test_log_1d(n_failed)
  call test_log_2d(n_failed)
  call test_log_3d(n_failed)
  call test_r8_0d(n_failed)
  call test_r8_1d(n_failed)
  call test_r8_2d(n_failed)
  call test_r8_3d(n_failed)
  call test_deliberate_mismatch_is_detected(n_failed)

  if (n_failed == 0) then
    write(*,*) 'ALL TESTS PASSED'
  else
    write(*,*) n_failed, ' TEST(S) FAILED'
    call exit(1)
  end if

contains

  subroutine report(name, ok, n_failed)
    character(len=*), intent(in) :: name
    logical, intent(in) :: ok
    integer, intent(inout) :: n_failed

    if (ok) then
      write(*,*) 'PASS: ', trim(name)
    else
      write(*,*) 'FAIL: ', trim(name)
      n_failed = n_failed + 1
    end if
  end subroutine report

  subroutine test_int_0d(n_failed)
    integer, intent(inout) :: n_failed
    integer :: written, readback

    written = 42
    call ccpp_capture('test:int_0d:in:before', written)
    call ccpp_capture_read('test:int_0d:in:before', readback, call_count=1)
    call report('int_0d round-trip', ccpp_capture_compare(readback, written), n_failed)
  end subroutine test_int_0d

  subroutine test_int_1d(n_failed)
    integer, intent(inout) :: n_failed
    integer :: written(4), readback(4)

    written = [1, 2, 3, 4]
    call ccpp_capture('test:int_1d:in:before', written)
    call ccpp_capture_read('test:int_1d:in:before', readback, call_count=1)
    call report('int_1d round-trip', ccpp_capture_compare(readback, written), n_failed)
  end subroutine test_int_1d

  subroutine test_int_2d(n_failed)
    integer, intent(inout) :: n_failed
    integer :: written(2,3), readback(2,3)

    written = reshape([1,2,3,4,5,6], [2,3])
    call ccpp_capture('test:int_2d:in:before', written)
    call ccpp_capture_read('test:int_2d:in:before', readback, call_count=1)
    call report('int_2d round-trip', ccpp_capture_compare(readback, written), n_failed)
  end subroutine test_int_2d

  subroutine test_int_3d(n_failed)
    integer, intent(inout) :: n_failed
    integer :: written(2,2,2), readback(2,2,2)

    written = reshape([1,2,3,4,5,6,7,8], [2,2,2])
    call ccpp_capture('test:int_3d:in:before', written)
    call ccpp_capture_read('test:int_3d:in:before', readback, call_count=1)
    call report('int_3d round-trip', ccpp_capture_compare(readback, written), n_failed)
  end subroutine test_int_3d

  subroutine test_log_0d(n_failed)
    integer, intent(inout) :: n_failed
    logical :: written, readback

    written = .true.
    call ccpp_capture('test:log_0d:in:before', written)
    call ccpp_capture_read('test:log_0d:in:before', readback, call_count=1)
    call report('log_0d round-trip', ccpp_capture_compare(readback, written), n_failed)
  end subroutine test_log_0d

  subroutine test_log_1d(n_failed)
    integer, intent(inout) :: n_failed
    logical :: written(3), readback(3)

    written = [.true., .false., .true.]
    call ccpp_capture('test:log_1d:in:before', written)
    call ccpp_capture_read('test:log_1d:in:before', readback, call_count=1)
    call report('log_1d round-trip', ccpp_capture_compare(readback, written), n_failed)
  end subroutine test_log_1d

  subroutine test_log_2d(n_failed)
    integer, intent(inout) :: n_failed
    logical :: written(2,2), readback(2,2)

    written = reshape([.true., .false., .false., .true.], [2,2])
    call ccpp_capture('test:log_2d:in:before', written)
    call ccpp_capture_read('test:log_2d:in:before', readback, call_count=1)
    call report('log_2d round-trip', ccpp_capture_compare(readback, written), n_failed)
  end subroutine test_log_2d

  subroutine test_log_3d(n_failed)
    integer, intent(inout) :: n_failed
    logical :: written(2,1,2), readback(2,1,2)

    written = reshape([.true., .false., .true., .false.], [2,1,2])
    call ccpp_capture('test:log_3d:in:before', written)
    call ccpp_capture_read('test:log_3d:in:before', readback, call_count=1)
    call report('log_3d round-trip', ccpp_capture_compare(readback, written), n_failed)
  end subroutine test_log_3d

  subroutine test_r8_0d(n_failed)
    integer, intent(inout) :: n_failed
    real(kind=kind_phys) :: written, readback

    written = 3.14159265358979_kind_phys
    call ccpp_capture('test:r8_0d:in:before', written)
    call ccpp_capture_read('test:r8_0d:in:before', readback, call_count=1)
    call report('r8_0d round-trip', &
                ccpp_capture_compare(readback, written, 1.0e-12_kind_phys), n_failed)
  end subroutine test_r8_0d

  subroutine test_r8_1d(n_failed)
    integer, intent(inout) :: n_failed
    real(kind=kind_phys) :: written(4), readback(4)

    written = [1.1_kind_phys, 2.2_kind_phys, 3.3_kind_phys, 4.4_kind_phys]
    call ccpp_capture('test:r8_1d:in:before', written)
    call ccpp_capture_read('test:r8_1d:in:before', readback, call_count=1)
    call report('r8_1d round-trip', &
                ccpp_capture_compare(readback, written, 1.0e-12_kind_phys), n_failed)
  end subroutine test_r8_1d

  subroutine test_r8_2d(n_failed)
    integer, intent(inout) :: n_failed
    real(kind=kind_phys) :: written(3,2), readback(3,2)

    written = reshape([1.0_kind_phys, 2.0_kind_phys, 3.0_kind_phys, &
                        4.0_kind_phys, 5.0_kind_phys, 6.0_kind_phys], [3,2])
    call ccpp_capture('test:r8_2d:inout:before', written)
    call ccpp_capture_read('test:r8_2d:inout:before', readback, call_count=1)
    call report('r8_2d round-trip', &
                ccpp_capture_compare(readback, written, 1.0e-12_kind_phys), n_failed)
  end subroutine test_r8_2d

  subroutine test_r8_3d(n_failed)
    integer, intent(inout) :: n_failed
    real(kind=kind_phys) :: written(2,2,2), readback(2,2,2)
    integer :: i

    written = reshape([(real(i, kind_phys), i = 1, 8)], [2,2,2])
    call ccpp_capture('test:r8_3d:in:before', written)
    call ccpp_capture_read('test:r8_3d:in:before', readback, call_count=1)
    call report('r8_3d round-trip', &
                ccpp_capture_compare(readback, written, 1.0e-12_kind_phys), n_failed)
  end subroutine test_r8_3d

  subroutine test_deliberate_mismatch_is_detected(n_failed)
    integer, intent(inout) :: n_failed
    real(kind=kind_phys) :: written(3,2), readback(3,2), corrupted(3,2)
    logical :: ok

    ! Reuses the r8_2d fixture tag from test_r8_2d above -- this is the
    ! second write under that tag, so it lands in call_count=2's own file,
    ! independent of the first.
    written = reshape([1.0_kind_phys, 2.0_kind_phys, 3.0_kind_phys, &
                        4.0_kind_phys, 5.0_kind_phys, 6.0_kind_phys], [3,2])
    call ccpp_capture('test:r8_2d:inout:before', written)
    call ccpp_capture_read('test:r8_2d:inout:before', readback, call_count=2)

    ! A real captured-vs-regenerated divergence, not a round-trip check:
    ! corrupt one element the way a real scheme regression would (e.g. a
    ! sign flip from a bad CPU->GPU port) and confirm compare correctly
    ! reports FAIL, not a false PASS.
    corrupted = readback
    corrupted(2,1) = -corrupted(2,1)
    ok = ccpp_capture_compare(corrupted, written, 1.0e-12_kind_phys)
    call report('deliberate mismatch correctly flagged as FAIL', .not. ok, n_failed)

    ! And the unmodified readback must still compare equal, confirming
    ! the corruption above -- not some other bug -- is what triggered FAIL.
    ok = ccpp_capture_compare(readback, written, 1.0e-12_kind_phys)
    call report('uncorrupted readback still compares equal', ok, n_failed)
  end subroutine test_deliberate_mismatch_is_detected

end program test_ccpp_capture_mod
