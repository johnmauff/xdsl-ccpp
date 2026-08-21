! Adapted from real capgen-v1's own upstream driver (end-to-end-tests/
! instances/main.F90, feature/capgen-v1 branch) to xdsl-ccpp's actual
! generated calling convention -- see examples/instances/CMakeLists.txt's
! own header comment for the full port history. Two adaptations from the
! literal upstream driver:
!   1) ccpp_physics_init/ccpp_physics_final calls: task #28's "Full
!      6-phase to 8-phase lifecycle match" (ccpp_cap_refactor_plan.md)
!      originally left these out entirely, since xdsl-ccpp's own
!      ccpp_init/ccpp_final covered everything real capgen-v1 splits into
!      a separate per-group ccpp_physics_init/ccpp_physics_final call.
!      Stage 3 of that same task added the real, group-scoped
!      ccpp_physics_init/ccpp_physics_final entry points (matching
!      upstream), so both calls are back, using the same instance=/
!      ninstances= keyword-arg convention already used below.
!   2) group_name/thread_num/nthreads/nphys_threads dropped from every
!      call -- xdsl-ccpp's generated signatures don't carry them (matching
!      examples/opt_arg's own driver, which needed the identical
!      adaptation for the same reason). suite_part='unit_conv_group'
!      (the physics group's real name, from suite_unit_conv_suite.xml)
!      replaces group_name='all' on every call that needs a group.
! The loop-over-instances structure itself -- the actual mechanism this
! example exists to exercise -- is otherwise unchanged from upstream.
program test_unit_conv

  use, intrinsic :: iso_fortran_env, only: error_unit

  use data, only: ncols, &
      nspecies, ninstances
  use data, only: instance_data

  use test_host_ccpp_cap, only: ccpp_register, &
      ccpp_init, &
      ccpp_physics_init, &
      ccpp_physics_timestep_init, &
      ccpp_physics_run, &
      ccpp_physics_timestep_final, &
      ccpp_physics_final, &
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
    call ccpp_register(suite_name=ccpp_suite, instance=ins, &
        ninstances=ninstances, errmsg=errmsg, errflg=errflg)
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
    call ccpp_init(suite_name=ccpp_suite, instance=ins, &
        ninstances=ninstances, errmsg=errmsg, errflg=errflg)
    if (errflg/=0) then
      write(error_unit, '(a)') "An error occurred in ccpp_init:"
      write(error_unit, '(a)') trim(errmsg)
      write(error_unit, '(a,i0)') "instance: ", ins
      stop 1
    end if
  end do

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP physics init step                         !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  do ins=1,ninstances
    ! Physics initialize (task #28, Stage 3): group-scoped, matching
    ! ccpp_physics_run's own signature -- owns the scheme-level _init
    ! calls ccpp_init no longer makes itself (see suite_cap.py's
    ! emit_scheme_calls).
    call ccpp_physics_init(suite_name=ccpp_suite, suite_part=ccpp_group, &
        lb=1, ub=ncols, instance=ins, &
        ninstances=ninstances, errmsg=errmsg, errflg=errflg)
    if (errflg/=0) then
      write(error_unit, '(a)') "An error occurred in ccpp_physics_init:"
      write(error_unit, '(a)') trim(errmsg)
      write(error_unit, '(a,i0)') "instance: ", ins
      stop 1
    end if
  end do

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP physics timestep init step                !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  do ins=1,ninstances
    ! ccpp_physics_timestep_init is now group-scoped (task #28, Stage 1),
    ! matching ccpp_physics_run's own signature (same lb/ub full-extent
    ! convention this driver already uses for run).
    call ccpp_physics_timestep_init(suite_name=ccpp_suite, suite_part=ccpp_group, &
        lb=1, ub=ncols, instance=ins, &
        ninstances=ninstances, errmsg=errmsg, errflg=errflg)
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
        lb=1, ub=ncols, instance=ins, ninstances=ninstances, &
        errmsg=errmsg, errflg=errflg)
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
    ! ccpp_physics_timestep_final is now group-scoped (task #28, Stage 2),
    ! matching ccpp_physics_timestep_init's own signature above.
    call ccpp_physics_timestep_final(suite_name=ccpp_suite, suite_part=ccpp_group, &
        lb=1, ub=ncols, instance=ins, &
        ninstances=ninstances, errmsg=errmsg, errflg=errflg)
    if (errflg/=0) then
      write(error_unit, '(a)') "An error occurred in ccpp_physics_timestep_final:"
      write(error_unit, '(a)') trim(errmsg)
      write(error_unit, '(a,i0)') "instance: ", ins
      stop 1
    end if
  end do

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP physics final step                        !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  do ins=1,ninstances
    ! Physics finalize (task #28, Stage 3): group-scoped, matching
    ! ccpp_physics_init's own signature above -- owns the scheme-level
    ! _finalize calls ccpp_final no longer makes itself.
    call ccpp_physics_final(suite_name=ccpp_suite, suite_part=ccpp_group, &
        lb=1, ub=ncols, instance=ins, &
        ninstances=ninstances, errmsg=errmsg, errflg=errflg)
    if (errflg/=0) then
      write(error_unit, '(a)') "An error occurred in ccpp_physics_final:"
      write(error_unit, '(a)') trim(errmsg)
      write(error_unit, '(a,i0)') "instance: ", ins
      stop 1
    end if
  end do

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP final step                                !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  do ins=1,ninstances
    call ccpp_final(suite_name=ccpp_suite, instance=ins, &
        ninstances=ninstances, errmsg=errmsg, errflg=errflg)
    if (errflg/=0) then
      write(error_unit, '(a)') "An error occurred in ccpp_final:"
      write(error_unit, '(a)') trim(errmsg)
      write(error_unit, '(a,i0)') "instance: ", ins
      stop 1
    end if
  end do

end program test_unit_conv
