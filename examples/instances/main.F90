! Adapted from real capgen-v1's own upstream driver (end-to-end-tests/
! instances/main.F90, feature/capgen-v1 branch) to xdsl-ccpp's actual
! generated calling convention -- see examples/instances/CMakeLists.txt's
! own header comment for the full port history. Two adaptations from the
! literal upstream driver, both because xdsl-ccpp's suite-level lifecycle
! is currently 6-phase, not real capgen-v1's own 8-phase split
! (ccpp_cap_refactor_plan.md's "Full 6-phase to 8-phase lifecycle match"
! backlog entry, still open) -- xdsl-ccpp's ccpp_init/ccpp_final already
! cover what real capgen-v1 splits further into a separate per-group
! ccpp_physics_init/ccpp_physics_final call, so those two calls are
! dropped entirely rather than calling subroutines that don't exist:
!   1) ccpp_physics_init/ccpp_physics_final calls removed.
!   2) group_name/thread_num/nthreads/nphys_threads dropped from every
!      call -- xdsl-ccpp's generated signatures don't carry them (matching
!      examples/opt_arg's own driver, which needed the identical
!      adaptation for the same reason). suite_part='unit_conv_group'
!      (the physics group's real name, from suite_unit_conv_suite.xml)
!      replaces group_name='all' on the one call that still needs a group.
! The loop-over-instances structure itself -- the actual mechanism this
! example exists to exercise -- is otherwise unchanged from upstream.
program test_unit_conv

  use, intrinsic :: iso_fortran_env, only: error_unit

  use data, only: ncols, &
      nspecies, ninstances
  use data, only: instance_data

  use test_host_ccpp_cap, only: ccpp_register, &
      ccpp_init, &
      ccpp_physics_timestep_init, &
      ccpp_physics_run, &
      ccpp_physics_timestep_final, &
      ccpp_final

  implicit none

  character(len=*), parameter :: ccpp_suite = 'unit_conv_suite'
  character(len=*), parameter :: ccpp_group = 'unit_conv_group'
  ! An updated ccpp_validator.py should detect this - metadata has len=512
  character(len=256) :: errmsg
  integer :: errflg
  integer :: ins

  instance_data(1)%data_array = -1.0_8
  instance_data(1)%data_array2 = -42.0_8
  instance_data(1)%opt_array_flag = .true.

  instance_data(2)%data_array = +1.0_8
  instance_data(2)%data_array2 = +42.0_8
  instance_data(2)%opt_array_flag = .false.

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP register step                             !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  do ins=1,ninstances
    call ccpp_register(suite_name=ccpp_suite, errmsg=errmsg, errflg=errflg)
    if (errflg/=0) then
      write(error_unit, '(a)') "An error occurred in ccpp_register:"
      write(error_unit, '(a)') trim(errmsg)
      stop 1
    end if
  end do

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP init step                                 !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  do ins=1,ninstances
    call ccpp_init(suite_name=ccpp_suite, errmsg=errmsg, errflg=errflg)
    if (errflg/=0) then
      write(error_unit, '(a)') "An error occurred in ccpp_init:"
      write(error_unit, '(a)') trim(errmsg)
      write(error_unit, '(a,i0)') "instance: ", ins
      stop 1
    end if
  end do

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP physics timestep init step                !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  do ins=1,ninstances
    call ccpp_physics_timestep_init(suite_name=ccpp_suite, errmsg=errmsg, errflg=errflg)
    if (errflg/=0) then
      write(error_unit, '(a)') "An error occurred in ccpp_physics_timestep_init:"
      write(error_unit, '(a)') trim(errmsg)
      write(error_unit, '(a,i0)') "instance: ", ins
      stop 1
    end if
  end do
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP physics run step                          !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  do ins=1,ninstances
    call ccpp_physics_run( &
        suite_name=ccpp_suite, suite_part=ccpp_group, &
        lb=1, ub=ncols, instance=ins, errmsg=errmsg, errflg=errflg)
    if (errflg/=0) then
      write(error_unit, '(a)') "An error occurred in ccpp_physics_run:"
      write(error_unit, '(a)') trim(errmsg)
      write(error_unit, '(a,i0)') "instance: ", ins
      stop 1
    end if
  end do

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP physics timestep final step               !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  do ins=1,ninstances
    call ccpp_physics_timestep_final(suite_name=ccpp_suite, errmsg=errmsg, errflg=errflg)
    if (errflg/=0) then
      write(error_unit, '(a)') "An error occurred in ccpp_physics_timestep_final:"
      write(error_unit, '(a)') trim(errmsg)
      write(error_unit, '(a,i0)') "instance: ", ins
      stop 1
    end if
  end do

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP final step                                !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  do ins=1,ninstances
    call ccpp_final(suite_name=ccpp_suite, errmsg=errmsg, errflg=errflg)
    if (errflg/=0) then
      write(error_unit, '(a)') "An error occurred in ccpp_final:"
      write(error_unit, '(a)') trim(errmsg)
      write(error_unit, '(a,i0)') "instance: ", ins
      stop 1
    end if
  end do

end program test_unit_conv
