! New test fixture (task11-omp-thread item 3) -- NOT ported from real
! capgen-v1: confirmed during scoping that real capgen-v1's own
! end-to-end-tests/ has no fixture exercising thread_number/
! number_of_threads as a container-DDT scalar index (only unused
! control-table boilerplate declarations of the pair). Modeled directly
! on this repo's own examples/instances/main.F90 -- the real capgen-v1
! analog for the symmetric instance_number/number_of_instances pair --
! with instance/ninstances swapped for thread/nthreads and a single
! scheme/group in place of that example's two-scheme subcycle (this
! fixture's only job is to exercise the thread_number substitution
! mechanism itself, not re-test subcycle/optional-arg/array-section
! behavior examples/instances already covers for the instance pair).
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
  ! CCPP register step                             !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  do thr=1,nthreads
    call ccpp_register(suite_name=ccpp_suite, thread=thr, &
        nthreads=nthreads, errmsg=errmsg, errflg=errflg)
    if (errflg/=0) then
      write(error_unit, '(a)') "An error occurred in ccpp_register:"
      write(error_unit, '(a)') trim(errmsg)
      stop 1
    end if
  end do

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP init step                                 !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  do thr=1,nthreads
    call ccpp_init(suite_name=ccpp_suite, thread=thr, &
        nthreads=nthreads, errmsg=errmsg, errflg=errflg)
    if (errflg/=0) then
      write(error_unit, '(a)') "An error occurred in ccpp_init:"
      write(error_unit, '(a)') trim(errmsg)
      write(error_unit, '(a,i0)') "thread: ", thr
      stop 1
    end if
  end do

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP physics init step                         !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  do thr=1,nthreads
    call ccpp_physics_init(suite_name=ccpp_suite, suite_part=ccpp_group, &
        lb=1, ub=ncols, thread=thr, &
        nthreads=nthreads, errmsg=errmsg, errflg=errflg)
    if (errflg/=0) then
      write(error_unit, '(a)') "An error occurred in ccpp_physics_init:"
      write(error_unit, '(a)') trim(errmsg)
      write(error_unit, '(a,i0)') "thread: ", thr
      stop 1
    end if
  end do

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP physics timestep init step                !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  do thr=1,nthreads
    call ccpp_physics_timestep_init(suite_name=ccpp_suite, suite_part=ccpp_group, &
        lb=1, ub=ncols, thread=thr, &
        nthreads=nthreads, errmsg=errmsg, errflg=errflg)
    if (errflg/=0) then
      write(error_unit, '(a)') "An error occurred in ccpp_physics_timestep_init:"
      write(error_unit, '(a)') trim(errmsg)
      write(error_unit, '(a,i0)') "thread: ", thr
      stop 1
    end if
  end do

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP physics run step                          !
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
  ! CCPP physics timestep final step               !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  do thr=1,nthreads
    call ccpp_physics_timestep_final(suite_name=ccpp_suite, suite_part=ccpp_group, &
        lb=1, ub=ncols, thread=thr, &
        nthreads=nthreads, errmsg=errmsg, errflg=errflg)
    if (errflg/=0) then
      write(error_unit, '(a)') "An error occurred in ccpp_physics_timestep_final:"
      write(error_unit, '(a)') trim(errmsg)
      write(error_unit, '(a,i0)') "thread: ", thr
      stop 1
    end if
  end do

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP physics final step                        !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  do thr=1,nthreads
    call ccpp_physics_final(suite_name=ccpp_suite, suite_part=ccpp_group, &
        lb=1, ub=ncols, thread=thr, &
        nthreads=nthreads, errmsg=errmsg, errflg=errflg)
    if (errflg/=0) then
      write(error_unit, '(a)') "An error occurred in ccpp_physics_final:"
      write(error_unit, '(a)') trim(errmsg)
      write(error_unit, '(a,i0)') "thread: ", thr
      stop 1
    end if
  end do

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP final step                                !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  do thr=1,nthreads
    call ccpp_final(suite_name=ccpp_suite, thread=thr, &
        nthreads=nthreads, errmsg=errmsg, errflg=errflg)
    if (errflg/=0) then
      write(error_unit, '(a)') "An error occurred in ccpp_final:"
      write(error_unit, '(a)') trim(errmsg)
      write(error_unit, '(a,i0)') "thread: ", thr
      stop 1
    end if
  end do

  write(error_unit, '(a)') "test_thread_scheme: all checks passed"

end program test_thread_scheme
