program test_kessler_ccpp_driver

  use kessler_host_mod
  use Kessler_ccpp_cap, only: &
      Kessler_ccpp_physics_register,        &
      Kessler_ccpp_physics_initialize,      &
      Kessler_ccpp_physics_finalize,        &
      Kessler_ccpp_physics_timestep_initial, &
      Kessler_ccpp_physics_timestep_final,  &
      Kessler_ccpp_physics_run

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
  call Kessler_ccpp_physics_register('kessler_suite', errmsg, errflg)
  if (errflg /= 0) then
    print *, 'Register error: ', trim(errmsg)
    stop
  end if

  call Kessler_ccpp_physics_initialize('kessler_suite', errmsg, errflg)
  if (errflg /= 0) then
    print *, 'Initialize error: ', trim(errmsg)
    stop
  end if

  !------------------------------------------------------
  ! Timestep initial (saves temp into temp_prev, zeros ttend_t)
  !------------------------------------------------------
  call Kessler_ccpp_physics_timestep_initial('kessler_suite', errmsg, errflg)
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
  call Kessler_ccpp_physics_run('kessler_suite', 'physics', col_start, col_end, errmsg, errflg)
  call system_clock(t2)
  etime = real(t2 - t1, 8) / real(rate, 8)

  if (errflg /= 0) then
    print *, 'Run error: ', trim(errmsg)
    stop
  end if

  !------------------------------------------------------
  ! Timestep final (computes dry static energy)
  !------------------------------------------------------
  call Kessler_ccpp_physics_timestep_final('kessler_suite', errmsg, errflg)
  if (errflg /= 0) then
    print *, 'Timestep final error: ', trim(errmsg)
    stop
  end if

  !------------------------------------------------------
  ! CCPP lifecycle: finalize
  !------------------------------------------------------
  call Kessler_ccpp_physics_finalize('kessler_suite', errmsg, errflg)

  !------------------------------------------------------
  ! Print results
  !------------------------------------------------------
  call print_results(etime)

end program test_kessler_ccpp_driver
