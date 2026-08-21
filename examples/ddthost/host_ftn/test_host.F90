module test_prog

   use ccpp_kinds, only: kind_phys

   implicit none
   private

   public test_host

   ! Public data and interfaces
   integer, public, parameter :: cs = 16
   integer, public, parameter :: cm = 36

   !> \section arg_table_suite_info  Argument Table
   !! \htmlinclude arg_table_suite_info.html
   !!
   type, public :: suite_info
      character(len=cs) :: suite_name = ''
      character(len=cs), pointer :: suite_parts(:) => NULL()
      character(len=cm), pointer :: suite_input_vars(:) => NULL()
      character(len=cm), pointer :: suite_output_vars(:) => NULL()
      character(len=cm), pointer :: suite_required_vars(:) => NULL()
   end type suite_info

contains

    logical function check_suite(test_suite)
       use test_host_ccpp_cap, only: ccpp_physics_suite_part_list
       use test_host_ccpp_cap, only: ccpp_physics_suite_variables
       use test_utils,         only: check_list

       ! Dummy argument
       type(suite_info), intent(in)    :: test_suite
       ! Local variables
       integer                         :: sind
       logical                         :: check
       integer                         :: errflg
       character(len=512)              :: errmsg
       character(len=128), allocatable :: test_list(:)

       check_suite = .true.
       write(6, *) "Checking suite ", trim(test_suite%suite_name)
       ! First, check the suite parts
       call ccpp_physics_suite_part_list(test_suite%suite_name, test_list,    &
            errmsg, errflg)
       if (errflg == 0) then
          check = check_list(test_list, test_suite%suite_parts, 'part names', &
               suite_name=test_suite%suite_name)
       else
          check = .false.
          write(6, '(a,i0,2a)') 'ERROR ', errflg, ': ', trim(errmsg)
       end if
       check_suite = check_suite .and. check
       if (allocated(test_list)) then
          deallocate(test_list)
       end if
       ! Check the input variables
       call ccpp_physics_suite_variables(test_suite%suite_name, test_list,    &
            errmsg, errflg, input_vars=.true., output_vars=.false.)
       if (errflg == 0) then
          check = check_list(test_list, test_suite%suite_input_vars,          &
               'input variable names', suite_name=test_suite%suite_name)
       else
          check = .false.
          write(6, '(a,i0,2a)') 'ERROR ', errflg, ': ', trim(errmsg)
       end if
       check_suite = check_suite .and. check
       if (allocated(test_list)) then
          deallocate(test_list)
       end if
       ! Check the output variables
       call ccpp_physics_suite_variables(test_suite%suite_name, test_list,    &
            errmsg, errflg, input_vars=.false., output_vars=.true.)
       if (errflg == 0) then
          check = check_list(test_list, test_suite%suite_output_vars,         &
               'output variable names', suite_name=test_suite%suite_name)
       else
          check = .false.
          write(6, '(a,i0,2a)') 'ERROR ', errflg, ': ', trim(errmsg)
       end if
       check_suite = check_suite .and. check
       if (allocated(test_list)) then
          deallocate(test_list)
       end if
       ! Check all required variables
       call ccpp_physics_suite_variables(test_suite%suite_name, test_list,    &
            errmsg, errflg)
       if (errflg == 0) then
          check = check_list(test_list, test_suite%suite_required_vars,       &
               'required variable names', suite_name=test_suite%suite_name)
       else
          check = .false.
          write(6, '(a,i0,2a)') 'ERROR ', errflg, ': ', trim(errmsg)
       end if
       check_suite = check_suite .and. check
       if (allocated(test_list)) then
          deallocate(test_list)
       end if
    end function check_suite


    !> \section arg_table_test_host  Argument Table
    !! \htmlinclude arg_table_test_host.html
    !!
    subroutine test_host(retval, test_suites)

       use host_ccpp_ddt,      only: ccpp_info_t
       use test_host_mod,      only: ncols, num_time_steps
       ! model_times (module var, allocatable): ccpp_physics_init's own
       ! "_init" call needs it threaded explicitly -- its scheme arg is
       ! intent=out/allocatable, which xdsl-ccpp deliberately never
       ! host-matches (the scheme allocates a FRESH array; it can't just
       ! claim an existing host one), unlike the intent=in "_final" call,
       ! which DOES get host-matched and resolved via a module-level use
       ! inside ccpp_physics_final's own dispatcher module -- no explicit
       ! arg needed there.
       use test_host_mod,      only: model_times
       use test_host_ccpp_cap, only: ccpp_init
       use test_host_ccpp_cap, only: ccpp_physics_init
       use test_host_ccpp_cap, only: ccpp_physics_timestep_init
       use test_host_ccpp_cap, only: ccpp_physics_run
       use test_host_ccpp_cap, only: ccpp_physics_timestep_final
       use test_host_ccpp_cap, only: ccpp_physics_final
       use test_host_ccpp_cap, only: ccpp_final
       use test_host_ccpp_cap, only: ccpp_physics_suite_list
       use test_host_mod,      only: init_data, compare_data, check_model_times
       use test_utils,         only: check_list

       type(suite_info), intent(in)  :: test_suites(:)
       logical,          intent(out) :: retval

       logical                         :: check
       integer                         :: col_start
       integer                         :: index, sind
       integer                         :: time_step
       integer                         :: num_suites
       character(len=128), allocatable :: suite_names(:)
       type(ccpp_info_t)               :: ccpp_info
       ! random_fudge_factor has no host variable match (temp_set.meta's
       ! own metadata documents 1.0_kind_phys as its intended default) --
       ! ccpp_physics_init's real signature (task #28, Stage 3) surfaces it
       ! as a genuine caller-supplied argument now, matching how
       ! ccpp_physics_run already treats any similarly host-unmatched arg.
       real(kind=kind_phys)            :: fudge = 1.0_kind_phys

       ! Initialize our 'data'
       call init_data()

       ! Gather and test the inspection routines
       num_suites = size(test_suites)
       call ccpp_physics_suite_list(suite_names)
       retval = check_list(suite_names, test_suites(:)%suite_name,            &
            'suite names')
       write(6, *) 'Available suites are:'
       do index = 1, size(suite_names)
          do sind = 1, num_suites
             if (trim(test_suites(sind)%suite_name) ==                        &
                  trim(suite_names(index))) then
                exit
             end if
          end do
          write(6, '(i0,3a,i0,a)') index, ') ', trim(suite_names(index)),     &
               ' = test_suites(', sind, ')'
       end do
       if (retval) then
          do sind = 1, num_suites
             check = check_suite(test_suites(sind))
             retval = retval .and. check
          end do
       end if
       !!! Return here if any check failed
       if (.not. retval) then
          return
       end if

       ! Use the suite information to setup the run
       do sind = 1, num_suites
          call ccpp_init(test_suites(sind)%suite_name, &
               ccpp_info)
          if (ccpp_info%errflg /= 0) then
             write(6, '(4a)') 'ERROR in initialize of ',                      &
                  trim(test_suites(sind)%suite_name), ': ', trim(ccpp_info%errmsg)
          end if
       end do

       ! Physics initialize (task #28, Stage 3): group-scoped, matching
       ! ccpp_physics_run's own per-part call below -- owns the
       ! scheme-level _init calls ccpp_init no longer makes itself (see
       ! suite_cap.py's emit_scheme_calls). Full extent (not chunked) via
       ! ccpp_info%col_start/col_end, same convention as timestep_init below.
       ccpp_info%col_start = 1
       ccpp_info%col_end = ncols
       do sind = 1, num_suites
          if (ccpp_info%errflg /= 0) then
             exit
          end if
          do index = 1, size(test_suites(sind)%suite_parts)
             if (ccpp_info%errflg /= 0) then
                exit
             end if
             if (ccpp_info%errflg == 0) then
                call ccpp_physics_init(                              &
                     test_suites(sind)%suite_name,                      &
                     test_suites(sind)%suite_parts(index),              &
                     ccpp_info, model_times, fudge)
             end if
             if (ccpp_info%errflg /= 0) then
                write(6, '(5a)') trim(test_suites(sind)%suite_name),    &
                     '/', trim(test_suites(sind)%suite_parts(index)),   &
                     ': ', trim(ccpp_info%errmsg)
                exit
             end if
          end do
       end do

       ! Loop over time steps
       do time_step = 1, num_time_steps
          ! Initialize the timestep. ccpp_physics_timestep_init is now
          ! group-scoped (task #28, Stage 1), matching ccpp_physics_run's
          ! own per-part call below -- full extent (not chunked) via
          ! ccpp_info%col_start/col_end, same as this file's own convention
          ! for passing column bounds through the bundled ccpp_info_t.
          ccpp_info%col_start = 1
          ccpp_info%col_end = ncols
          do sind = 1, num_suites
             if (ccpp_info%errflg /= 0) then
                exit
             end if
             do index = 1, size(test_suites(sind)%suite_parts)
                if (ccpp_info%errflg /= 0) then
                   exit
                end if
                if (ccpp_info%errflg == 0) then
                   call ccpp_physics_timestep_init(                 &
                        test_suites(sind)%suite_name,                      &
                        test_suites(sind)%suite_parts(index),              &
                        ccpp_info)
                end if
                if (ccpp_info%errflg /= 0) then
                   write(6, '(5a)') trim(test_suites(sind)%suite_name),    &
                        '/', trim(test_suites(sind)%suite_parts(index)),   &
                        ': ', trim(ccpp_info%errmsg)
                   exit
                end if
             end do
          end do

          do col_start = 1, ncols, 5
             if (ccpp_info%errflg /= 0) then
                exit
             end if
             ccpp_info%col_start = col_start
             ccpp_info%col_end = MIN(col_start + 4, ncols)

             do sind = 1, num_suites
                if (ccpp_info%errflg /= 0) then
                   exit
                end if
                do index = 1, size(test_suites(sind)%suite_parts)
                   if (ccpp_info%errflg /= 0) then
                      exit
                   end if
                   if (ccpp_info%errflg == 0) then
                      call ccpp_physics_run(                        &
                           test_suites(sind)%suite_name,                      &
                           test_suites(sind)%suite_parts(index),              &
                           ccpp_info)
                   end if
                   if (ccpp_info%errflg /= 0) then
                      write(6, '(5a)') trim(test_suites(sind)%suite_name),    &
                           '/', trim(test_suites(sind)%suite_parts(index)),   &
                           ': ', trim(ccpp_info%errmsg)
                      exit
                   end if
                end do
             end do
          end do

          ! Finalize the timestep. ccpp_physics_timestep_final is now
          ! group-scoped (task #28, Stage 2), matching
          ! ccpp_physics_timestep_init's own per-part call above -- full
          ! extent (not chunked) via ccpp_info%col_start/col_end.
          ccpp_info%col_start = 1
          ccpp_info%col_end = ncols
          do sind = 1, num_suites
             if (ccpp_info%errflg /= 0) then
                exit
             end if
             do index = 1, size(test_suites(sind)%suite_parts)
                if (ccpp_info%errflg /= 0) then
                   exit
                end if
                if (ccpp_info%errflg == 0) then
                   call ccpp_physics_timestep_final(                &
                        test_suites(sind)%suite_name,                      &
                        test_suites(sind)%suite_parts(index),              &
                        ccpp_info)
                end if
                if (ccpp_info%errflg /= 0) then
                   write(6, '(5a)') trim(test_suites(sind)%suite_name),    &
                        '/', trim(test_suites(sind)%suite_parts(index)),   &
                        ': ', trim(ccpp_info%errmsg)
                   exit
                end if
             end do
          end do
       end do ! End time step loop

       ! Physics finalize (task #28, Stage 3): group-scoped, matching
       ! ccpp_physics_init's own per-part call above -- owns the
       ! scheme-level _finalize calls ccpp_final no longer makes itself.
       ccpp_info%col_start = 1
       ccpp_info%col_end = ncols
       do sind = 1, num_suites
          if (ccpp_info%errflg /= 0) then
             exit
          end if
          do index = 1, size(test_suites(sind)%suite_parts)
             if (ccpp_info%errflg /= 0) then
                exit
             end if
             if (ccpp_info%errflg == 0) then
                call ccpp_physics_final(                             &
                     test_suites(sind)%suite_name,                      &
                     test_suites(sind)%suite_parts(index),              &
                     ccpp_info)
             end if
             if (ccpp_info%errflg /= 0) then
                write(6, '(5a)') trim(test_suites(sind)%suite_name),    &
                     '/', trim(test_suites(sind)%suite_parts(index)),   &
                     ': ', trim(ccpp_info%errmsg)
                exit
             end if
          end do
       end do

       do sind = 1, num_suites
          if (ccpp_info%errflg /= 0) then
             exit
          end if
          if (ccpp_info%errflg == 0) then
             call ccpp_final(                            &
                  test_suites(sind)%suite_name,ccpp_info)
          end if
          if (ccpp_info%errflg /= 0) then
             write(6, '(3a)') test_suites(sind)%suite_parts(index), ': ',     &
                  trim(ccpp_info%errmsg)
             write(6,'(2a)') 'An error occurred in ccpp_timestep_final, ',    &
                  'Exiting...'
             exit
          end if
       end do

       if (ccpp_info%errflg == 0) then
          ! Run finished without error, check answers
          if (.not. check_model_times()) then
             write(6, *) 'Model times error!'
             ccpp_info%errflg = -1
          else if (compare_data()) then
             write(6, *) 'Answers are correct!'
             ccpp_info%errflg = 0
          else
             write(6, *) 'Answers are not correct!'
             ccpp_info%errflg = -1
          end if
       end if

       retval = ccpp_info%errflg == 0

    end subroutine test_host

 end module test_prog
