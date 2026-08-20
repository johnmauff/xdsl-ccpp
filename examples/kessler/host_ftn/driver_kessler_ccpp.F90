program test_kessler_ccpp_driver

  use kessler_host_mod
  use Kessler_ccpp_cap, only: &
      ccpp_register,        &
      ccpp_init,      &
      ccpp_final,        &
      ccpp_physics_timestep_init, &
      ccpp_physics_timestep_final,  &
      ccpp_physics_run

  implicit none

  character(len=512) :: errmsg
  integer :: errflg
  integer :: col_start, col_end

  integer(8) :: t1, t2, rate
  real(8)    :: etime

  !------------------------------------------------------
  ! Initialize all host module data
  !------------------------------------------------------
  call init_data()

  !------------------------------------------------------
  ! CCPP lifecycle: register + initialize
  !------------------------------------------------------
  call ccpp_register('kessler_suite', errmsg, errflg)
  if (errflg /= 0) then
    print *, 'Register error: ', trim(errmsg)
    stop
  end if

  call ccpp_init('kessler_suite', errmsg, errflg)
  if (errflg /= 0) then
    print *, 'Initialize error: ', trim(errmsg)
    stop
  end if

  !------------------------------------------------------
  ! Timestep initial (saves temp into temp_prev, zeros ttend_t)
  !------------------------------------------------------
  ! ccpp_physics_timestep_init is now group-scoped (task #28, Stage 1),
  ! matching ccpp_physics_run's own signature -- full extent (1, ncol),
  ! not chunked (this driver never chunks columns for run either).
  call ccpp_physics_timestep_init('kessler_suite', 'physics', 1, ncol, errmsg, errflg)
  if (errflg /= 0) then
    print *, 'Timestep initial error: ', trim(errmsg)
    stop
  end if

  !------------------------------------------------------
  ! Run physics
  !------------------------------------------------------
  col_start = 1
  col_end   = ncol

  call system_clock(t1, rate)
  call ccpp_physics_run('kessler_suite', 'physics', col_start, col_end, errmsg, errflg)
  call system_clock(t2)
  etime = real(t2 - t1, 8) / real(rate, 8)

  if (errflg /= 0) then
    print *, 'Run error: ', trim(errmsg)
    stop
  end if

  !------------------------------------------------------
  ! Timestep final (computes dry static energy)
  !------------------------------------------------------
  call ccpp_physics_timestep_final('kessler_suite', errmsg, errflg)
  if (errflg /= 0) then
    print *, 'Timestep final error: ', trim(errmsg)
    stop
  end if

  !------------------------------------------------------
  ! CCPP lifecycle: finalize
  !------------------------------------------------------
  call ccpp_final('kessler_suite', errmsg, errflg)

  !------------------------------------------------------
  ! Print results
  !------------------------------------------------------
  call print_results(etime)

end program test_kessler_ccpp_driver
