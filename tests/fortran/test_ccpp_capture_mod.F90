! Standalone round-trip test for ccpp_capture_mod (NetCDF format,
! scheme-io-capture-netcdf) -- compiled and run directly, independent of
! any CCPP scheme or the Python xdsl_ccpp pipeline. Writes one simulated
! scheme call (an `in` and an `out` group) holding every supported
! (type, rank), reads it back and compares; also checks the call counter,
! the `found` signal for a call that was never captured, missing
! variables, a shape mismatch, mismatch detection and diagnostics, and the
! tolerance override default.
!
! Run from this directory (netcdf-fortran on the paths, e.g. on Derecho
! `module load netcdf`):
!   gfortran -o test_ccpp_capture_mod $(nf-config --fflags) ccpp_kinds.F90 \
!       ../../xdsl_ccpp/framework_src/ccpp_capture_mod.F90 \
!       test_ccpp_capture_mod.F90 $(nf-config --flibs)
!   ./test_ccpp_capture_mod
!   ncdump -h test_table_1.nc     # optional: look at the layout
!
! Exits 0 and prints "ALL TESTS PASSED" on success; exits 1 and prints
! each failing case otherwise. Writes test_table_1.nc and test_table_2.nc
! into the current directory (CCPP_CAPTURE_DIR unset) and leaves them.
program test_ccpp_capture_mod
  use ccpp_kinds, only: kind_phys
  use ccpp_capture_mod, only: ccpp_capture_begin, ccpp_capture_end, ccpp_capture, &
                              ccpp_capture_open_call, ccpp_capture_close, &
                              ccpp_capture_read, ccpp_capture_compare, &
                              ccpp_capture_tolerance_override

  implicit none

  integer :: n_failed

  ! The values written to call 1 (in) and call 1 (out).
  integer :: i0, i1(4), i2(2,3), i3(2,2,2)
  logical :: l0, l1(3), l2(2,2), l3(2,1,2)
  real(kind=kind_phys) :: r0, r1(5), r2(3,2), r3(2,3,2)
  character(len=16) :: c0
  character(len=8) :: c1(3)
  real(kind=kind_phys) :: r2_out(3,2)

  n_failed = 0

  call write_call_1()
  call write_call_2()
  call test_round_trip(n_failed)
  call test_out_group(n_failed)
  call test_second_call(n_failed)
  call test_missing_call_and_variable(n_failed)
  call test_shape_mismatch_is_rejected(n_failed)
  call test_deliberate_mismatch_is_detected(n_failed)
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

  ! Call 1 of test_table: every (type, rank) in `in`, one result in `out`.
  subroutine write_call_1()
    i0 = 42
    i1 = [1, 2, 3, 4]
    i2 = reshape([1, 2, 3, 4, 5, 6], [2, 3])
    i3 = reshape([1, 2, 3, 4, 5, 6, 7, 8], [2, 2, 2])
    l0 = .true.
    l1 = [.true., .false., .true.]
    l2 = reshape([.false., .true., .true., .false.], [2, 2])
    l3 = reshape([.true., .true., .false., .true.], [2, 1, 2])
    r0 = 3.25_kind_phys
    r1 = [1.5_kind_phys, -2.0_kind_phys, 0.0_kind_phys, 1.0e-30_kind_phys, 7.0_kind_phys]
    r2 = reshape([1._kind_phys, 2._kind_phys, 3._kind_phys, 4._kind_phys, 5._kind_phys, &
                  6._kind_phys], [3, 2])
    r3 = 0.5_kind_phys
    r3(2, 3, 2) = -9.75_kind_phys
    c0 = 'kessler'
    c1 = [character(len=8) :: 'q', 'cldliq', 'rainqm']
    r2_out = 2.0_kind_phys * r2

    call ccpp_capture_begin('test_table', 'before')
    call ccpp_capture('i0', i0, standard_name='an_integer', units='1')
    call ccpp_capture('i1', i1, dim_names='four')
    call ccpp_capture('i2', i2, dim_names='horizontal_loop_extent,three')
    call ccpp_capture('i3', i3)
    call ccpp_capture('l0', l0)
    call ccpp_capture('l1', l1)
    call ccpp_capture('l2', l2)
    call ccpp_capture('l3', l3)
    call ccpp_capture('r0', r0, units='K')
    call ccpp_capture('r1', r1)
    ! horizontal_loop_extent again, with another length: a suffixed dimension.
    call ccpp_capture('r2', r2, dim_names='horizontal_loop_extent,vertical_layer_dimension')
    call ccpp_capture('r3', r3)
    call ccpp_capture('c0', c0)
    call ccpp_capture('c1', c1, dim_names='number_of_constituents')
    call ccpp_capture_end()

    call ccpp_capture_begin('test_table', 'after')
    call ccpp_capture('r2', r2_out, dim_names='horizontal_loop_extent,vertical_layer_dimension')
    call ccpp_capture_end()
  end subroutine write_call_1

  ! Call 2 of test_table: a second file, numbered by the per-table counter.
  subroutine write_call_2()
    call ccpp_capture_begin('test_table', 'before')
    call ccpp_capture('i0', 7)
    call ccpp_capture_end()
    call ccpp_capture_begin('test_table', 'after')
    call ccpp_capture_end()
  end subroutine write_call_2

  subroutine test_round_trip(n_failed)
    integer, intent(inout) :: n_failed
    integer :: ri0, ri1(4), ri2(2,3), ri3(2,2,2)
    logical :: rl0, rl1(3), rl2(2,2), rl3(2,1,2)
    real(kind=kind_phys) :: rr0, rr1(5), rr2(3,2), rr3(2,3,2)
    character(len=16) :: rc0
    character(len=8) :: rc1(3)
    logical :: found

    call ccpp_capture_open_call('test_table', 1, found)
    call report('call 1 file found', found, n_failed)
    call ccpp_capture_read('in', 'i0', ri0)
    call ccpp_capture_read('in', 'i1', ri1)
    call ccpp_capture_read('in', 'i2', ri2)
    call ccpp_capture_read('in', 'i3', ri3)
    call ccpp_capture_read('in', 'l0', rl0)
    call ccpp_capture_read('in', 'l1', rl1)
    call ccpp_capture_read('in', 'l2', rl2)
    call ccpp_capture_read('in', 'l3', rl3)
    call ccpp_capture_read('in', 'r0', rr0)
    call ccpp_capture_read('in', 'r1', rr1)
    call ccpp_capture_read('in', 'r2', rr2)
    call ccpp_capture_read('in', 'r3', rr3)
    call ccpp_capture_read('in', 'c0', rc0)
    call ccpp_capture_read('in', 'c1', rc1)
    call ccpp_capture_close()

    call report('int_0d round-trip', ccpp_capture_compare(ri0, i0), n_failed)
    call report('int_1d round-trip', ccpp_capture_compare(ri1, i1), n_failed)
    call report('int_2d round-trip', ccpp_capture_compare(ri2, i2), n_failed)
    call report('int_3d round-trip', ccpp_capture_compare(ri3, i3), n_failed)
    call report('log_0d round-trip', ccpp_capture_compare(rl0, l0), n_failed)
    call report('log_1d round-trip', ccpp_capture_compare(rl1, l1), n_failed)
    call report('log_2d round-trip', ccpp_capture_compare(rl2, l2), n_failed)
    call report('log_3d round-trip', ccpp_capture_compare(rl3, l3), n_failed)
    call report('r8_0d round-trip', ccpp_capture_compare(rr0, r0, 0.0_kind_phys), n_failed)
    call report('r8_1d round-trip', ccpp_capture_compare(rr1, r1, 0.0_kind_phys), n_failed)
    call report('r8_2d round-trip', ccpp_capture_compare(rr2, r2, 0.0_kind_phys), n_failed)
    call report('r8_3d round-trip', ccpp_capture_compare(rr3, r3, 0.0_kind_phys), n_failed)
    call report('char_0d round-trip', ccpp_capture_compare(rc0, c0), n_failed)
    call report('char_1d round-trip', ccpp_capture_compare(rc1, c1), n_failed)
  end subroutine test_round_trip

  subroutine test_out_group(n_failed)
    integer, intent(inout) :: n_failed
    real(kind=kind_phys) :: rr2(3,2)
    logical :: found

    call ccpp_capture_open_call('test_table', 1, found)
    call ccpp_capture_read('out', 'r2', rr2, found)
    call ccpp_capture_close()
    call report('out group written after reopening', found, n_failed)
    call report('out group value', ccpp_capture_compare(rr2, r2_out, 0.0_kind_phys), n_failed)
  end subroutine test_out_group

  subroutine test_second_call(n_failed)
    integer, intent(inout) :: n_failed
    integer :: ri0
    logical :: found

    call ccpp_capture_open_call('test_table', 2, found)
    call report('call 2 file found', found, n_failed)
    call ccpp_capture_read('in', 'i0', ri0)
    call ccpp_capture_close()
    call report('call 2 holds its own value', ri0 == 7, n_failed)
  end subroutine test_second_call

  subroutine test_missing_call_and_variable(n_failed)
    integer, intent(inout) :: n_failed
    integer :: ri0
    logical :: found

    call ccpp_capture_open_call('test_table', 99, found)
    call report('found=.false. for a call never captured', .not. found, n_failed)

    call ccpp_capture_open_call('test_table', 1, found)
    ri0 = -1
    call ccpp_capture_read('out', 'i0', ri0, found)
    call ccpp_capture_close()
    call report('found=.false. for a variable not in the group', .not. found, n_failed)
    call report('value unchanged when nothing is read', ri0 == -1, n_failed)
  end subroutine test_missing_call_and_variable

  subroutine test_shape_mismatch_is_rejected(n_failed)
    integer, intent(inout) :: n_failed
    real(kind=kind_phys) :: wrong(2,3)
    logical :: found

    write(*,*) '(expect one shape-mismatch message on stderr)'
    wrong = -1.0_kind_phys
    call ccpp_capture_open_call('test_table', 1, found)
    call ccpp_capture_read('in', 'r2', wrong, found)
    call ccpp_capture_close()
    call report('shape mismatch: not found', .not. found, n_failed)
    call report('shape mismatch: value unchanged', all(wrong == -1.0_kind_phys), n_failed)
  end subroutine test_shape_mismatch_is_rejected

  subroutine test_deliberate_mismatch_is_detected(n_failed)
    integer, intent(inout) :: n_failed
    real(kind=kind_phys) :: corrupted(3,2)
    logical :: ok

    corrupted = r2
    corrupted(2,1) = -corrupted(2,1)
    ok = ccpp_capture_compare(corrupted, r2, 1.0e-12_kind_phys)
    call report('deliberate mismatch correctly flagged as FAIL', .not. ok, n_failed)
    call report('character mismatch flagged', .not. ccpp_capture_compare('kessler', 'qneg'), n_failed)
  end subroutine test_deliberate_mismatch_is_detected

  subroutine test_compare_diagnostics(n_failed)
    integer, intent(inout) :: n_failed
    real(kind=kind_phys) :: actual2d(3,2), expected2d(3,2)
    real(kind=kind_phys) :: max_abs_diff, mean_abs_diff
    integer :: first_mismatch_index
    integer :: actual1d(4), expected1d(4)
    logical :: ok

    ! (2,1) of a (3,2) array is column-major linear index 2.
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

    ok = ccpp_capture_compare( &
        expected2d, expected2d, 1.0e-12_kind_phys, max_abs_diff, mean_abs_diff, first_mismatch_index)
    call report('real 2d diagnostics: ok on an exact match', ok, n_failed)
    call report('real 2d diagnostics: first_mismatch_index == 0 on a match', &
        first_mismatch_index == 0, n_failed)

    expected1d = [1, 2, 3, 4]
    actual1d = expected1d
    actual1d(3) = 30
    ok = ccpp_capture_compare(actual1d, expected1d, first_mismatch_index)
    call report('integer 1d diagnostics: ok is .false.', .not. ok, n_failed)
    call report('integer 1d diagnostics: first_mismatch_index == 3', first_mismatch_index == 3, n_failed)
  end subroutine test_compare_diagnostics

  subroutine test_tolerance_override_default_when_unset(n_failed)
    ! With CCPP_CAPTURE_TOLERANCE unset the caller's default comes back
    ! (the set case is checked from the shell; Fortran cannot set it).
    integer, intent(inout) :: n_failed
    real(kind=kind_phys) :: tolerance

    tolerance = ccpp_capture_tolerance_override(1.0e-10_kind_phys)
    call report('tolerance override: default returned when unset', &
        abs(tolerance - 1.0e-10_kind_phys) < 1.0e-20_kind_phys, n_failed)
  end subroutine test_tolerance_override_default_when_unset

end program test_ccpp_capture_mod
