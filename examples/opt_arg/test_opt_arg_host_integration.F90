program test_opt_arg

  use, intrinsic :: iso_fortran_env, only: output_unit, &
      error_unit

  use data, only: nx, &
      flag_for_opt_arg, &
      std_arg, &
      opt_arg, &
      opt_arg_2

  use test_host_ccpp_cap, only: test_host_ccpp_physics_register, &
      test_host_ccpp_physics_initialize, &
      test_host_ccpp_physics_timestep_initial, &
      test_host_ccpp_physics_run, &
      test_host_ccpp_physics_timestep_final, &
      test_host_ccpp_physics_finalize

  implicit none

  character(len=*), parameter :: ccpp_suite = 'opt_arg_suite'
  character(len=*), parameter :: ccpp_group = 'opt_arg_group'
  character(len=512) :: errmsg
  integer :: errflg

  std_arg = 1
  flag_for_opt_arg = .true.
  allocate(opt_arg(nx))
  allocate(opt_arg_2(nx))
  opt_arg = 0
  opt_arg_2 = 0

  call test_host_ccpp_physics_register(ccpp_suite, errmsg, errflg)
  if (errflg /= 0) then
    write(error_unit, '(a)') "An error occurred in register: "//trim(errmsg)
    stop 1
  end if

  call test_host_ccpp_physics_initialize(ccpp_suite, errmsg, errflg)
  if (errflg /= 0) then
    write(error_unit, '(a)') "An error occurred in initialize: "//trim(errmsg)
    stop 1
  end if

  call test_host_ccpp_physics_timestep_initial(ccpp_suite, nx, std_arg, opt_arg, opt_arg_2,       &
    errmsg, errflg)
  if (errflg /= 0) then
    write(error_unit, '(a)') "An error occurred in timestep_initial: "//trim(errmsg)
    stop 1
  end if

  write(output_unit, '(a)') "PASS: after timestep_initial: check std_arg(:)==1 and opt_arg(:)==2"
  if (.not. all(std_arg == 1)) write(error_unit, '(a,3i3)') "Error: std_arg=", std_arg
  if (.not. all(opt_arg == 2)) write(error_unit, '(a,3i3)') "Error: opt_arg=", opt_arg

  call test_host_ccpp_physics_run(ccpp_suite, ccpp_group, 1, nx, nx, std_arg, opt_arg, opt_arg_2, &
    errmsg, errflg)
  if (errflg /= 0) then
    write(error_unit, '(a)') "An error occurred in run: "//trim(errmsg)
    stop 1
  end if

  write(output_unit, '(a)') "PASS: after run: check std_arg(:)==1 and opt_arg(:)==3"
  if (.not. all(std_arg == 1)) write(error_unit, '(a,3i3)') "Error: std_arg=", std_arg
  if (.not. all(opt_arg == 3)) write(error_unit, '(a,3i3)') "Error: opt_arg=", opt_arg

  call test_host_ccpp_physics_timestep_final(ccpp_suite, nx, std_arg, opt_arg, opt_arg_2,         &
    errmsg, errflg)
  if (errflg /= 0) then
    write(error_unit, '(a)') "An error occurred in timestep_final: "//trim(errmsg)
    stop 1
  end if

  call test_host_ccpp_physics_finalize(ccpp_suite, errmsg, errflg)
  if (errflg /= 0) then
    write(error_unit, '(a)') "An error occurred in finalize: "//trim(errmsg)
    stop 1
  end if

  write(output_unit, '(a)') "opt_arg: TEST PASSED"

end program test_opt_arg
