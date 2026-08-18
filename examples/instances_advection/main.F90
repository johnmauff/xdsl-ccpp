! Adapted from real capgen-v1's own upstream driver (end-to-end-tests/
! instances_advection/main.F90, feature/capgen-v1 branch) to xdsl-ccpp's
! actual generated calling convention -- see examples/instances_advection/
! CMakeLists.txt's own header comment for the full port history, and
! ccpp_cap_refactor_plan.md's "instances/instances_advection" backlog entry
! (task #35) for the constituent-API instance-awareness fix this adaptation
! depends on. Adaptations from the literal upstream driver, matching
! examples/instances' own precedent for the identical reasons:
!   1) ccpp_physics_init/ccpp_physics_final calls removed -- xdsl-ccpp's
!      lifecycle is still 6-phase, not real capgen-v1's 8-phase split
!      (ccpp_cap_refactor_plan.md's "Full 6-phase to 8-phase lifecycle
!      match" backlog entry, still open); ccpp_init/ccpp_final already
!      cover what those two calls would have done.
!   2) group_name/thread_num/nthreads/nphys_threads dropped from every
!      call -- xdsl-ccpp's generated signatures don't carry them.
!      suite_part='physics' (the physics group's real name, from
!      cld_suite.xml) replaces group_name='physics' on the calls that
!      still need a group/part.
!   3) errcode -> errflg: xdsl-ccpp's own generated signatures always use
!      errflg, never errcode (the local variable here is renamed to match,
!      not just the keyword-argument text, for consistency with every
!      other example's driver).
!   4) Constituent-API subroutines referenced by their real generated
!      names (test_host_ccpp_register_constituents, etc.) -- xdsl-ccpp
!      does not alias these to bare ccpp_-prefixed names the way the
!      lifecycle subroutines are (matches examples/constituents_dim's own
!      driver, which needed the identical adaptation).
! The loop-over-instances structure itself, and the per-instance
! constituent-registration calls (instance=/ninstances= on every one of
! them) -- the actual mechanism this example exists to exercise -- are
! otherwise unchanged from upstream; they only work now because
! constituent_cap.py's own instance-awareness fix (task #35) gives each
! model instance its own constituent storage.
program test_instances_advection

  use, intrinsic :: iso_fortran_env, only: error_unit

  use ccpp_kinds, only: kind_phys
  use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t

  use data, only: ncols, pver, ninstances, dt, tfreeze, num_time_steps
  use data, only: phys_state, qv_init, index_qv
  use data, only: allocate_physics_state, init_qv, set_index_qv, &
      verify_results

  use test_host_ccpp_cap, only: ccpp_register, ccpp_init, ccpp_final
  use test_host_ccpp_cap, only: ccpp_physics_run, &
      ccpp_physics_timestep_init, ccpp_physics_timestep_final
  use test_host_ccpp_cap, only: test_host_ccpp_register_constituents, &
      test_host_ccpp_initialize_constituents, &
      test_host_ccpp_deallocate_dynamic_constituents
  use test_host_ccpp_cap, only: test_host_const_get_index, &
      test_host_constituents_array
  use test_host_ccpp_cap, only: test_host_ccpp_number_constituents

  implicit none

  character(len=*), parameter :: ccpp_suite = 'cld_suite'
  character(len=*), parameter :: ccpp_group = 'physics'
  character(len=512) :: errmsg
  integer :: errflg
  integer :: ins
  integer :: tstep
  integer :: num_consts
  integer :: idx
  type(ccpp_constituent_properties_t), target, allocatable :: host_consts(:)
  real(kind=kind_phys), pointer :: constituents_ptr(:, :, :)

  !-----------------------------------------------------------------
  ! 1. CCPP register: per-instance, populates per-suite dynamic
  !    constituent buffer on first instance, idempotent thereafter.
  !-----------------------------------------------------------------
  do ins = 1, ninstances
    call ccpp_register(suite_name=ccpp_suite, &
        instance=ins, ninstances=ninstances, &
        errmsg=errmsg, errflg=errflg)
    if (errflg /= 0) then
      write(error_unit, '(2a)') 'ccpp_register failed: ', trim(errmsg)
      stop 1
    end if
  end do

  !-----------------------------------------------------------------
  ! 2. Build the host-registered constituent list (specific_humidity)
  !    and call test_host_ccpp_register_constituents per instance.
  !    Each call consumes the host_consts array (new_field sets
  !    const_index on the input objects), so we re-instantiate per
  !    instance.
  !-----------------------------------------------------------------
  do ins = 1, ninstances
    if (allocated(host_consts)) deallocate(host_consts)
    allocate(host_consts(1))
    call host_consts(1)%instantiate( &
        std_name='water_vapor_specific_humidity', &
        long_name='Water vapor specific humidity', &
        diag_name='QV', units='kg kg-1', &
        vertical_dim='vertical_layer_dimension', advected=.true., &
        default_value=0.0_kind_phys, mixing_ratio_type='wet', &
        errcode=errflg, errmsg=errmsg)
    if (errflg /= 0) then
      write(error_unit, '(2a)') 'instantiate failed: ', trim(errmsg)
      stop 1
    end if
    call test_host_ccpp_register_constituents(host_constituents=host_consts, &
        instance=ins, ninstances=ninstances, &
        errmsg=errmsg, errflg=errflg)
    if (errflg /= 0) then
      write(error_unit, '(a,i0,2a)') &
          'ccpp_register_constituents failed for instance ', ins, &
          ': ', trim(errmsg)
      stop 1
    end if
  end do

  !-----------------------------------------------------------------
  ! 3. ccpp_initialize_constituents per instance — allocates the
  !    per-instance constituent storage.
  !-----------------------------------------------------------------
  do ins = 1, ninstances
    call test_host_ccpp_initialize_constituents(ncols=ncols, pver=pver, &
        instance=ins, errmsg=errmsg, errflg=errflg)
    if (errflg /= 0) then
      write(error_unit, '(a,i0,2a)') &
          'ccpp_initialize_constituents failed for instance ', ins, &
          ': ', trim(errmsg)
      stop 1
    end if
  end do

  !-----------------------------------------------------------------
  ! 4. Resolve the qv constituent index and number of constituents
  !    (identical across instances).
  !-----------------------------------------------------------------

  call test_host_const_get_index(std_name='water_vapor_specific_humidity', &
      index=idx, instance=1, errflg=errflg, errmsg=errmsg)
  if (errflg /= 0) then
    write(error_unit, '(2a)') 'ccpp_const_get_index(qv) failed: ', &
        trim(errmsg)
    stop 1
  end if
  call set_index_qv(idx)

  call test_host_ccpp_number_constituents(num_advected=num_consts, &
      instance=1, errmsg=errmsg, errflg=errflg)
  if (errflg /= 0) then
    write(error_unit, '(2a)') 'ccpp_number_constituents failed: ', &
        trim(errmsg)
    stop 1
  end if

  !-----------------------------------------------------------------
  ! 5. For each instance, wire phys_state(ins) to its constituent
  !    storage and seed distinct initial qv values.
  !-----------------------------------------------------------------

  do ins = 1, ninstances
    constituents_ptr => test_host_constituents_array(ins)
    call allocate_physics_state(ins, constituents_ptr)
    call init_qv(ins)
  end do

  !-----------------------------------------------------------------
  ! 6. ccpp_init per instance.
  !-----------------------------------------------------------------
  do ins = 1, ninstances
    call ccpp_init(suite_name=ccpp_suite, tfreeze=tfreeze, &
        instance=ins, ninstances=ninstances, &
        errmsg=errmsg, errflg=errflg)
    if (errflg /= 0) then
      write(error_unit, '(a,i0,2a)') 'ccpp_init failed for instance ', &
          ins, ': ', trim(errmsg)
      stop 1
    end if
  end do

  !-----------------------------------------------------------------
  ! 7. Timestep loop.
  !-----------------------------------------------------------------
  do tstep = 1, num_time_steps
    do ins = 1, ninstances
      call ccpp_physics_timestep_init(suite_name=ccpp_suite, &
          instance=ins, ninstances=ninstances, &
          errmsg=errmsg, errflg=errflg)
      if (errflg /= 0) then
        write(error_unit, '(a,i0,2a)') &
            'ccpp_physics_timestep_init failed for instance ', ins, &
            ': ', trim(errmsg)
        stop 1
      end if
    end do
    do ins = 1, ninstances
      call ccpp_physics_run(suite_name=ccpp_suite, suite_part=ccpp_group, &
          lb=1, ub=ncols, ncol=ncols, timestep=dt, &
          instance=ins, ninstances=ninstances, &
          errmsg=errmsg, errflg=errflg)
      if (errflg /= 0) then
        write(error_unit, '(a,i0,2a)') &
            'ccpp_physics_run failed for instance ', ins, ': ', trim(errmsg)
        stop 1
      end if
    end do
    do ins = 1, ninstances
      call ccpp_physics_timestep_final(suite_name=ccpp_suite, &
          instance=ins, ninstances=ninstances, &
          errmsg=errmsg, errflg=errflg)
      if (errflg /= 0) then
        write(error_unit, '(a,i0,2a)') &
            'ccpp_physics_timestep_final failed for instance ', ins, &
            ': ', trim(errmsg)
        stop 1
      end if
    end do
  end do

  !-----------------------------------------------------------------
  ! 8. Verify per-instance results BEFORE constituent teardown.
  !    phys_state(:)%q points into the framework's per-instance
  !    constituent storage; ccpp_deallocate_dynamic_constituents
  !    frees that storage, so any verification must run first.
  !-----------------------------------------------------------------
  if (.not. verify_results(num_consts)) then
    write(6, '(a)') 'FAIL: per-instance + constituents test'
    stop 1
  end if

  !-----------------------------------------------------------------
  ! 9. Teardown.
  !-----------------------------------------------------------------
  do ins = 1, ninstances
    call ccpp_final(suite_name=ccpp_suite, &
        instance=ins, ninstances=ninstances, &
        errmsg=errmsg, errflg=errflg)
    if (errflg /= 0) then
      write(error_unit, '(a,i0,2a)') 'ccpp_final failed for instance ', &
          ins, ': ', trim(errmsg)
      stop 1
    end if
  end do
  do ins = 1, ninstances
    call test_host_ccpp_deallocate_dynamic_constituents(instance=ins)
  end do
  deallocate(host_consts)

  write(6, '(a)') 'PASS: per-instance + constituents test'
  stop 0

end program test_instances_advection
