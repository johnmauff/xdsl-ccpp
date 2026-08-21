program test_suite_allocate

  use, intrinsic :: iso_fortran_env, only: output_unit, &
      error_unit

  use ccpp_kinds, only: kind_phys

  use data, only: checksum

  use test_host_ccpp_cap, only: ccpp_register, &
      ccpp_init, &
      ccpp_physics_init, &
      ccpp_physics_timestep_init, &
      ccpp_physics_run, &
      ccpp_physics_timestep_final, &
      ccpp_physics_final, &
      ccpp_final

  implicit none

  character(len=*), parameter :: ccpp_suite = 'suite_allocate_suite'
  character(len=*), parameter :: ccpp_group = 'workspace_group'
  character(len=512) :: errmsg
  integer :: errflg
  integer, parameter :: expected_size = 4
  real(kind=kind_phys) :: expected
  real(kind=kind_phys), parameter :: tol = 1.0e-6_kind_phys

  expected = real(expected_size * (expected_size + 1) / 2, kind_phys)
  checksum = -1.0_kind_phys

  call ccpp_register(ccpp_suite, errmsg, errflg)
  call check_err('register', errflg, errmsg)

  call ccpp_init(ccpp_suite, errmsg, errflg)
  call check_err('initialize', errflg, errmsg)

  ! Physics initialize (task #28, Stage 3): group-scoped, matching
  ! ccpp_physics_run's own signature -- owns the scheme-level _init calls
  ! ccpp_init no longer makes itself (see suite_cap.py's emit_scheme_calls).
  call ccpp_physics_init(ccpp_suite, ccpp_group, 1, 1, errmsg, errflg)
  call check_err('physics_init', errflg, errmsg)

  ! ccpp_physics_timestep_init is now group-scoped (task #28, Stage 1),
  ! matching ccpp_physics_run's own signature/extent below exactly.
  call ccpp_physics_timestep_init(ccpp_suite, ccpp_group, 1, 1, errmsg, errflg)
  call check_err('timestep_initial', errflg, errmsg)

  call ccpp_physics_run(ccpp_suite, ccpp_group, 1, 1, errmsg, errflg)
  call check_err('run', errflg, errmsg)

  if (abs(checksum - expected) > tol) then
    write(error_unit, '(a,f0.6,a,f0.6)') &
        "Error after physics_run: workspace_checksum=", checksum, &
        " expected ", expected
    stop 1
  end if
  write(output_unit, '(a,f0.6)') &
      "PASS: After physics_run: suite-owned allocatable workspace summed to ", checksum

  ! ccpp_physics_timestep_final is now group-scoped (task #28, Stage 2),
  ! matching ccpp_physics_timestep_init's own signature/extent above exactly.
  call ccpp_physics_timestep_final(ccpp_suite, ccpp_group, 1, 1, errmsg, errflg)
  call check_err('timestep_final', errflg, errmsg)

  ! Physics finalize (task #28, Stage 3): group-scoped, matching
  ! ccpp_physics_init's own signature above -- owns the scheme-level
  ! _finalize calls ccpp_final no longer makes itself.
  call ccpp_physics_final(ccpp_suite, ccpp_group, 1, 1, errmsg, errflg)
  call check_err('physics_final', errflg, errmsg)

  call ccpp_final(ccpp_suite, errmsg, errflg)
  call check_err('finalize', errflg, errmsg)

  write(output_unit, '(a)') "PASS: suite_allocate test completed"

contains

  subroutine check_err(phase, errflg, errmsg)
    character(len=*), intent(in) :: phase
    integer,          intent(in) :: errflg
    character(len=*), intent(in) :: errmsg
    if (errflg /= 0) then
      write(error_unit, '(a)') "An error occurred in " // trim(phase) // ":"
      write(error_unit, '(a)') trim(errmsg)
      stop 1
    end if
  end subroutine check_err

end program test_suite_allocate
