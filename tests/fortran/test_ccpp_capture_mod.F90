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
  use ccpp_capture_mod, only: ccpp_capture, ccpp_capture_read, ccpp_capture_compare, &
                              ccpp_capture_tolerance_override

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
  call test_found_parameter_for_multi_call_replay(n_failed)
  call test_compare_diagnostics(n_failed)
  call test_tolerance_override_default_when_unset(n_failed)

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

  subroutine test_found_parameter_for_multi_call_replay(n_failed)
    ! The `found` status parameter (scheme-io-capture-multi-timestep) is
    ! what lets a generated test driver loop "replay call 1, 2, 3, ...
    ! until no more captured data exists" without needing to know ahead
    ! of time how many real calls a fixture actually contains. Confirms:
    ! found=.true. for a call_count that was actually written, and
    ! found=.false. (not a crash, not a stderr-noise false alarm) for one
    ! that wasn't -- exactly the "no more calls" signal a replay loop's
    ! own exit condition depends on.
    integer, intent(inout) :: n_failed
    integer :: written, readback
    logical :: found

    written = 7
    call ccpp_capture('test:found_param:in:before', written)

    call ccpp_capture_read('test:found_param:in:before', readback, call_count=1, found=found)
    call report('found=.true. for a real call_count', found, n_failed)
    call report('value read correctly alongside found=.true.', readback == written, n_failed)

    call ccpp_capture_read('test:found_param:in:before', readback, call_count=99, found=found)
    call report('found=.false. for a call_count that was never written', .not. found, n_failed)
  end subroutine test_found_parameter_for_multi_call_replay

  subroutine test_compare_diagnostics(n_failed)
    ! scheme-io-capture-compare-diagnostics: a bare pass/fail used to tell
    ! a generated driver *that* a GPU-port regression existed but never
    ! how badly or where. Confirms the optional first_mismatch_index/
    ! max_abs_diff/mean_abs_diff outputs report the exact, known location
    ! and magnitude of a deliberately-introduced mismatch -- not just
    ! that ok comes back .false.
    integer, intent(inout) :: n_failed
    real(kind=kind_phys) :: actual2d(3,2), expected2d(3,2)
    real(kind=kind_phys) :: max_abs_diff, mean_abs_diff
    integer :: first_mismatch_index
    integer :: actual1d(4), expected1d(4)
    logical :: ok

    ! Column-major linear index for (i=2, j=1) in a (3,2) array is
    ! 2 + (1-1)*3 = 2 -- deliberately perturb exactly that element by a
    ! known amount (5.0) so every diagnostic output has a known-correct
    ! answer to check against, not just "some nonzero value."
    expected2d = reshape( &
        [1._kind_phys, 2._kind_phys, 3._kind_phys, 4._kind_phys, 5._kind_phys, 6._kind_phys], [3,2])
    actual2d = expected2d
    actual2d(2,1) = actual2d(2,1) + 5._kind_phys

    ok = ccpp_capture_compare( &
        actual2d, expected2d, 1.0e-12_kind_phys, max_abs_diff, mean_abs_diff, first_mismatch_index)
    call report('real 2d diagnostics: ok is .false.', .not. ok, n_failed)
    call report('real 2d diagnostics: first_mismatch_index == 2', first_mismatch_index == 2, n_failed)
    call report('real 2d diagnostics: max_abs_diff == 5.0', &
        abs(max_abs_diff - 5._kind_phys) < 1.0e-12_kind_phys, n_failed)
    call report('real 2d diagnostics: mean_abs_diff == 5.0/6', &
        abs(mean_abs_diff - 5._kind_phys/6._kind_phys) < 1.0e-12_kind_phys, n_failed)

    ! A clean match must report first_mismatch_index=0, not a stale value
    ! from a previous call -- also confirms diagnostics are computed on a
    ! PASS too ("how close", not only "how far" on a FAIL).
    ok = ccpp_capture_compare( &
        expected2d, expected2d, 1.0e-12_kind_phys, max_abs_diff, mean_abs_diff, first_mismatch_index)
    call report('real 2d diagnostics: ok is .true. on an exact match', ok, n_failed)
    call report('real 2d diagnostics: first_mismatch_index == 0 on a match', &
        first_mismatch_index == 0, n_failed)
    call report('real 2d diagnostics: max_abs_diff == 0 on a match', &
        abs(max_abs_diff) < 1.0e-12_kind_phys, n_failed)

    ! Integer compares get first_mismatch_index only (no magnitude
    ! concept for an exact-match type) -- mismatch at index 3.
    expected1d = [1, 2, 3, 4]
    actual1d = expected1d
    actual1d(3) = 30
    ok = ccpp_capture_compare(actual1d, expected1d, first_mismatch_index)
    call report('integer 1d diagnostics: ok is .false.', .not. ok, n_failed)
    call report('integer 1d diagnostics: first_mismatch_index == 3', first_mismatch_index == 3, n_failed)
  end subroutine test_compare_diagnostics

  subroutine test_tolerance_override_default_when_unset(n_failed)
    ! scheme-io-capture-tolerance-config's runtime-override follow-on:
    ! with CCPP_CAPTURE_TOLERANCE unset (the normal case this test's own
    ! environment is assumed to be in -- setting/unsetting an environment
    ! variable mid-process has no portable standard Fortran mechanism, so
    ! the actual "variable IS set" override path is verified separately,
    ! via a real build run from the shell with CCPP_CAPTURE_TOLERANCE
    ! exported -- see scheme-io-capture's own CHANGELOG entry), the
    ! function must return the caller's own default unchanged.
    integer, intent(inout) :: n_failed
    real(kind=kind_phys) :: tolerance

    tolerance = ccpp_capture_tolerance_override(1.0e-10_kind_phys)
    call report('tolerance override: default returned when unset', &
        abs(tolerance - 1.0e-10_kind_phys) < 1.0e-20_kind_phys, n_failed)
  end subroutine test_tolerance_override_default_when_unset

end program test_ccpp_capture_mod
