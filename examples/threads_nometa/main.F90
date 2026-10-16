! New test fixture (task11-omp-thread item 3) -- NOT ported from real
! capgen-v1: confirmed during scoping that real capgen-v1's own
! end-to-end-tests/ has no fixture exercising thread_number/
! number_of_threads as a container-DDT scalar index (only unused
! control-table boilerplate declarations of the pair).
!
! Deliberately NOT structured like examples/instances/main.F90's own
! per-index loop over the WHOLE lifecycle (register/init/.../final) --
! that shape is correct for instance_number because each model instance
! genuinely gets its own independent lifecycle and its own entry in the
! framework's per-instance ccpp_suite_state array. thread_number has no
! such framework-side state: confirmed during scoping that real
! capgen-v1 builds no per-thread equivalent of that array (OpenMP
! threads parallelize only the RUN phase within one already-initialized
! model instance, never separate register/init/finalize calls). A first
! version of this driver copied examples/instances' per-index-loops-
! everything shape directly and hit exactly the bug that shape is meant
! to prevent for instances: thread 2's ccpp_init call saw thread 1's
! call having already flipped the single shared ccpp_suite_state to
! 'initialized' and errored ("Invalid initial CCPP state, 'initialized'
! in thread_suite_initialize, thread: 2") -- a real CI failure, not a
! hypothetical. Fixed by calling register/init/finalize ONCE and only
! looping the RUN-phase call per thread, matching how OpenMP threads
! actually parallelize physics work in a real host model.
program test_thread_scheme

  use, intrinsic :: iso_fortran_env, only: error_unit

  use data, only: ncols, nthreads
  use data, only: thread_data

  use test_host_ccpp_cap, only: ccpp_register, &
      ccpp_init, &
      ccpp_physics_init, &
      ccpp_physics_timestep_init, &
      ccpp_physics_run, &
      ccpp_physics_timestep_final, &
      ccpp_physics_final, &
      ccpp_final

  implicit none

  character(len=*), parameter :: ccpp_suite = 'thread_suite'
  character(len=*), parameter :: ccpp_group = 'thread_group'
  character(len=512) :: errmsg
  integer :: errflg
  integer :: thr

  thread_data(1)%data_array = -1.0_8
  thread_data(2)%data_array = +1.0_8

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP register step -- once, not per thread.    !
  ! thread_scheme declares thread_number only on    !
  ! its own _run entry point, so the value passed   !
  ! here is never consumed by anything; 1 is as     !
  ! good as any.                                    !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  call ccpp_register(suite_name=ccpp_suite, thread=1, &
      nthreads=nthreads, errmsg=errmsg, errflg=errflg)
  if (errflg/=0) then
    write(error_unit, '(a)') "An error occurred in ccpp_register:"
    write(error_unit, '(a)') trim(errmsg)
    stop 1
  end if

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP init step -- once.                        !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  call ccpp_init(suite_name=ccpp_suite, thread=1, &
      nthreads=nthreads, errmsg=errmsg, errflg=errflg)
  if (errflg/=0) then
    write(error_unit, '(a)') "An error occurred in ccpp_init:"
    write(error_unit, '(a)') trim(errmsg)
    stop 1
  end if

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP physics init step -- once.                !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  call ccpp_physics_init(suite_name=ccpp_suite, suite_part=ccpp_group, &
      lb=1, ub=ncols, thread=1, &
      nthreads=nthreads, errmsg=errmsg, errflg=errflg)
  if (errflg/=0) then
    write(error_unit, '(a)') "An error occurred in ccpp_physics_init:"
    write(error_unit, '(a)') trim(errmsg)
    stop 1
  end if

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP physics timestep init step -- once.       !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  call ccpp_physics_timestep_init(suite_name=ccpp_suite, suite_part=ccpp_group, &
      lb=1, ub=ncols, thread=1, &
      nthreads=nthreads, errmsg=errmsg, errflg=errflg)
  if (errflg/=0) then
    write(error_unit, '(a)') "An error occurred in ccpp_physics_timestep_init:"
    write(error_unit, '(a)') trim(errmsg)
    stop 1
  end if

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP physics run step -- once PER THREAD. This !
  ! is the actual mechanism under test: each call   !
  ! indexes thread_data(thread) independently.      !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  do thr=1,nthreads
    call ccpp_physics_run( &
        suite_name=ccpp_suite, suite_part=ccpp_group, &
        lb=1, ub=ncols, thread=thr, nthreads=nthreads, &
        errmsg=errmsg, errflg=errflg)
    if (errflg/=0) then
      write(error_unit, '(a)') "An error occurred in ccpp_physics_run:"
      write(error_unit, '(a)') trim(errmsg)
      write(error_unit, '(a,i0)') "thread: ", thr
      stop 1
    end if
  end do

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP physics timestep final step -- once.      !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  call ccpp_physics_timestep_final(suite_name=ccpp_suite, suite_part=ccpp_group, &
      lb=1, ub=ncols, thread=1, &
      nthreads=nthreads, errmsg=errmsg, errflg=errflg)
  if (errflg/=0) then
    write(error_unit, '(a)') "An error occurred in ccpp_physics_timestep_final:"
    write(error_unit, '(a)') trim(errmsg)
    stop 1
  end if

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP physics final step -- once.               !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  call ccpp_physics_final(suite_name=ccpp_suite, suite_part=ccpp_group, &
      lb=1, ub=ncols, thread=1, &
      nthreads=nthreads, errmsg=errmsg, errflg=errflg)
  if (errflg/=0) then
    write(error_unit, '(a)') "An error occurred in ccpp_physics_final:"
    write(error_unit, '(a)') trim(errmsg)
    stop 1
  end if

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP final step -- once.                       !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  call ccpp_final(suite_name=ccpp_suite, thread=1, &
      nthreads=nthreads, errmsg=errmsg, errflg=errflg)
  if (errflg/=0) then
    write(error_unit, '(a)') "An error occurred in ccpp_final:"
    write(error_unit, '(a)') trim(errmsg)
    stop 1
  end if

  write(error_unit, '(a)') "test_thread_scheme: all checks passed"

end program test_thread_scheme
