module hello_world_host

  use ccpp_kinds, only: kind_phys

  implicit none
  private

  public hello_world_sub

CONTAINS

  !> \section arg_table_hello_world_sub  Argument Table
  !! \htmlinclude arg_table_hello_world_sub.html
  !!
  subroutine hello_world_sub()

    use hello_world_mod,     only: ncols
    use HelloWorld_ccpp_cap, only: ccpp_init
    use HelloWorld_ccpp_cap, only: ccpp_physics_init
    use HelloWorld_ccpp_cap, only: ccpp_physics_timestep_init
    use HelloWorld_ccpp_cap, only: ccpp_physics_run
    use HelloWorld_ccpp_cap, only: ccpp_physics_timestep_final
    use HelloWorld_ccpp_cap, only: ccpp_physics_final
    use HelloWorld_ccpp_cap, only: ccpp_final
    use HelloWorld_ccpp_cap, only: ccpp_physics_suite_list
    use HelloWorld_ccpp_cap, only: ccpp_physics_suite_part_list
    use hello_world_mod,     only: init_temp, compare_temp

    integer                         :: col_start, col_end
    integer                         :: index
    character(len=128), allocatable :: part_names(:)
    character(len=512)              :: errmsg
    integer                         :: errflg

    ! Initialize our 'data'
    call init_temp()

    ! Use the suite information to setup the run
    call ccpp_init('hello_world_suite', errmsg, errflg)
    if (errflg /= 0) then
      write(6, *) trim(errmsg)
      stop
    end if

    ! Physics initialize (task #28, Stage 3): group-scoped, matching
    ! ccpp_physics_run's own signature -- owns the scheme-level _init
    ! calls ccpp_init no longer makes itself (see suite_cap.py's
    ! emit_scheme_calls).
    call ccpp_physics_init('hello_world_suite', 'physics', 1, ncols, &
        errmsg, errflg)
    if (errflg /= 0) then
      write(6, *) trim(errmsg)
      stop
    end if

    ! Initialize the timestep. ccpp_physics_timestep_init is now
    ! group-scoped (task #28, Stage 1), matching ccpp_physics_run's own
    ! signature -- full extent (1, ncols), not chunked.
    call ccpp_physics_timestep_init('hello_world_suite', 'physics', 1, ncols, &
        errmsg, errflg)
    if (errflg /= 0) then
      write(6, *) trim(errmsg)
      stop
    end if

    do col_start = 1, ncols, 5
      col_end = MIN(col_start + 4, ncols)

      call ccpp_physics_run('hello_world_suite', 'physics', col_start, col_end, errmsg, errflg)
      if (errflg /= 0) then
        write(6, *) trim(errmsg)
        call ccpp_physics_suite_part_list('hello_world_suite', part_names, errmsg, errflg)
        write(6, *) 'Available suite parts are:'
        do index = 1, size(part_names)
          write(6, *) trim(part_names(index))
        end do
        stop
      end if
    end do

    ! Finalize the timestep. ccpp_physics_timestep_final is now
    ! group-scoped (task #28, Stage 2), matching ccpp_physics_timestep_init's
    ! own signature -- full extent (1, ncols), not chunked.
    call ccpp_physics_timestep_final('hello_world_suite', 'physics', 1, ncols, &
        errmsg, errflg)

    ! Physics finalize (task #28, Stage 3): group-scoped, matching
    ! ccpp_physics_init's own signature above -- owns the scheme-level
    ! _finalize calls ccpp_final no longer makes itself.
    call ccpp_physics_final('hello_world_suite', 'physics', 1, ncols, &
        errmsg, errflg)
    if (errflg /= 0) then
      write(6, *) trim(errmsg)
      stop
    end if

    call ccpp_final('hello_world_suite', errmsg, errflg)
    if (errflg /= 0) then
      write(6, *) trim(errmsg)
      write(6,'(a)') 'An error occurred in ccpp_timestep_final, Exiting...'
      stop
    end if

    if (compare_temp()) then
      write(6, *) 'Answers are correct!'
    else
      write(6, *) 'Answers are not correct!'
    end if

  end subroutine hello_world_sub

end module hello_world_host

program hello_world
  use hello_world_host, only: hello_world_sub
  call hello_world_sub()
end program hello_world
