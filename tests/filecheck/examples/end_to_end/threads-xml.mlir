// Test the end-to-end generated Fortran for the threads example
// (task11-omp-thread item 3): confirms thread_data(thread)%data_array is
// emitted in the generated cap -- the decisive "did it actually work"
// proof, analogous to examples/instances' own instance_data(instance)
// output for the instance_number pair.

// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/threads/suite_thread_suite.xml --scheme-files examples/threads/thread_scheme.meta --host-files examples/threads/data.meta,examples/threads/test_host.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p generate-meta-cap,generate-meta-kinds,generate-host-match,generate-arg-ownership,generate-suite-cap,generate-ccpp-cap,generate-cpp-cap,generate-kinds,strip-ccpp -t ftn | python3 -m filecheck %s

// CHECK-LABEL: // FILE: thread_suite_cap.F90
// CHECK-LABEL: module thread_suite_cap
// CHECK:         use ccpp_kinds
// CHECK-NEXT:    use thread_scheme, only: thread_scheme_run
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         character(len=16) :: ccpp_suite_state = 'uninitialized'
// CHECK-NEXT:    character(len=16), parameter :: const_in_time_step = 'in_time_step'
// CHECK-NEXT:    character(len=16), parameter :: const_initialized = 'initialized'
// CHECK-NEXT:    character(len=16), parameter :: const_uninitialized = 'uninitialized'
// CHECK-NEXT:    public :: thread_suite_register
// CHECK-NEXT:    public :: thread_suite_initialize
// CHECK-NEXT:    public :: thread_suite_finalize
// CHECK-NEXT:    public :: thread_suite_init_thread_group
// CHECK-NEXT:    public :: thread_suite_thread_group
// CHECK-NEXT:    public :: thread_suite_timestep_init_thread_group
// CHECK-NEXT:    public :: thread_suite_timestep_final_thread_group
// CHECK-NEXT:    public :: thread_suite_final_thread_group
// CHECK:       CONTAINS
// CHECK-LABEL:   subroutine thread_suite_register(thread, nthreads, errflg, errmsg)
// CHECK:           integer, intent(in) :: thread
// CHECK-NEXT:      integer, intent(in) :: nthreads
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:    end subroutine thread_suite_register
// CHECK-LABEL:   subroutine thread_suite_initialize(thread, nthreads, errflg, errmsg)
// CHECK:           integer, intent(in) :: thread
// CHECK-NEXT:      integer, intent(in) :: nthreads
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_uninitialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in thread_suite_initialize"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_initialized
// CHECK-NEXT:    end subroutine thread_suite_initialize
// CHECK-LABEL:   subroutine thread_suite_finalize(thread, nthreads, errflg, errmsg)
// CHECK:           integer, intent(in) :: thread
// CHECK-NEXT:      integer, intent(in) :: nthreads
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in thread_suite_finalize"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_uninitialized
// CHECK-NEXT:    end subroutine thread_suite_finalize
// CHECK-LABEL:   subroutine thread_suite_init_thread_group(thread, nthreads, errflg, errmsg)
// CHECK:           integer, intent(in) :: thread
// CHECK-NEXT:      integer, intent(in) :: nthreads
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in thread_suite_init_thread_group"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine thread_suite_init_thread_group
// CHECK-LABEL:   subroutine thread_suite_thread_group(thread, data_array, nthreads, errmsg, errflg)
// CHECK:           integer, intent(in) :: thread
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: data_array(:)
// CHECK-NEXT:      integer, intent(in) :: nthreads
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_in_time_step .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in thread_suite_thread_group"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call thread_scheme_run(errmsg=errmsg, errflg=errflg, thread=thread, data_array=data_array)
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine thread_suite_thread_group
// CHECK-LABEL:   subroutine thread_suite_timestep_init_thread_group(thread, nthreads, errflg, errmsg)
// CHECK:           integer, intent(in) :: thread
// CHECK-NEXT:      integer, intent(in) :: nthreads
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      ccpp_suite_state = const_in_time_step
// CHECK-NEXT:    end subroutine thread_suite_timestep_init_thread_group
// CHECK-LABEL:   subroutine thread_suite_timestep_final_thread_group(thread, nthreads, errflg, errmsg)
// CHECK:           integer, intent(in) :: thread
// CHECK-NEXT:      integer, intent(in) :: nthreads
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      ccpp_suite_state = const_initialized
// CHECK-NEXT:    end subroutine thread_suite_timestep_final_thread_group
// CHECK-LABEL:   subroutine thread_suite_final_thread_group(thread, nthreads, errflg, errmsg)
// CHECK:           integer, intent(in) :: thread
// CHECK-NEXT:      integer, intent(in) :: nthreads
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in thread_suite_final_thread_group"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine thread_suite_final_thread_group
// CHECK-NEXT:  end module thread_suite_cap
// CHECK:       // -----
// CHECK-LABEL: // FILE: Thread_ccpp_cap.F90
// CHECK-LABEL: module Thread_ccpp_cap
// CHECK:         use ccpp_kinds
// CHECK-NEXT:    use data, only: thread_data
// CHECK-NEXT:    use data, only: thread_type
// CHECK-NEXT:    use thread_suite_cap, only: thread_suite_final_thread_group
// CHECK-NEXT:    use thread_suite_cap, only: thread_suite_finalize
// CHECK-NEXT:    use thread_suite_cap, only: thread_suite_init_thread_group
// CHECK-NEXT:    use thread_suite_cap, only: thread_suite_initialize
// CHECK-NEXT:    use thread_suite_cap, only: thread_suite_register
// CHECK-NEXT:    use thread_suite_cap, only: thread_suite_thread_group
// CHECK-NEXT:    use thread_suite_cap, only: thread_suite_timestep_final_thread_group
// CHECK-NEXT:    use thread_suite_cap, only: thread_suite_timestep_init_thread_group
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         character(len=12), parameter :: str_thread_suite = 'thread_suite'
// CHECK-NEXT:    character(len=12), parameter :: str_thread_group = 'thread_group'
// CHECK-NEXT:    public :: ccpp_register
// CHECK-NEXT:    public :: ccpp_init
// CHECK-NEXT:    public :: ccpp_final
// CHECK-NEXT:    public :: ccpp_physics_run
// CHECK-NEXT:    public :: ccpp_physics_timestep_init
// CHECK-NEXT:    public :: ccpp_physics_timestep_final
// CHECK-NEXT:    public :: ccpp_physics_init
// CHECK-NEXT:    public :: ccpp_physics_final
// CHECK-NEXT:    public :: ccpp_physics_suite_list
// CHECK-NEXT:    public :: ccpp_physics_suite_part_list
// CHECK-NEXT:    public :: ccpp_physics_suite_variables
// CHECK:       CONTAINS
// CHECK-LABEL:   subroutine ccpp_register(suite_name, thread, nthreads, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      integer, intent(in) :: thread
// CHECK-NEXT:      integer, intent(in) :: nthreads
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'thread_suite') then
// CHECK-NEXT:        call thread_suite_register(thread, nthreads, errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_register
// CHECK-LABEL:   subroutine ccpp_init(suite_name, thread, nthreads, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      integer, intent(in) :: thread
// CHECK-NEXT:      integer, intent(in) :: nthreads
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'thread_suite') then
// CHECK-NEXT:        call thread_suite_initialize(thread, nthreads, errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_init
// CHECK-LABEL:   subroutine ccpp_final(suite_name, thread, nthreads, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      integer, intent(in) :: thread
// CHECK-NEXT:      integer, intent(in) :: nthreads
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'thread_suite') then
// CHECK-NEXT:        call thread_suite_finalize(thread, nthreads, errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_final
// CHECK-LABEL:   subroutine ccpp_physics_run(suite_name, suite_part, lb, ub, thread, nthreads, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), intent(in) :: suite_part
// CHECK-NEXT:      integer, intent(in) :: lb
// CHECK-NEXT:      integer, intent(in) :: ub
// CHECK-NEXT:      integer, intent(in) :: thread
// CHECK-NEXT:      integer, intent(in) :: nthreads
// CHECK-NEXT:      character(len=512), intent(inout) :: errmsg
// CHECK-NEXT:      integer, intent(inout) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'thread_suite') then
// CHECK-NEXT:        if (trim(suite_part) .eq. 'thread_group') then
// CHECK-NEXT:          call thread_suite_thread_group(thread, thread_data(thread)%data_array(lb:ub), nthreads,   &
// CHECK-NEXT:            errmsg, errflg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg, '(3a)') "No suite part named ", trim(suite_part),                           &
// CHECK-NEXT:            " found in suite thread_suite"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_physics_run
// CHECK-LABEL:   subroutine ccpp_physics_timestep_init(suite_name, suite_part, lb, ub, thread, nthreads, errmsg, &
// CHECK:           errflg)
// CHECK-NEXT:      character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), intent(in) :: suite_part
// CHECK-NEXT:      integer, intent(in) :: lb
// CHECK-NEXT:      integer, intent(in) :: ub
// CHECK-NEXT:      integer, intent(in) :: thread
// CHECK-NEXT:      integer, intent(in) :: nthreads
// CHECK-NEXT:      character(len=512), intent(inout) :: errmsg
// CHECK-NEXT:      integer, intent(inout) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'thread_suite') then
// CHECK-NEXT:        if (trim(suite_part) .eq. 'thread_group') then
// CHECK-NEXT:          call thread_suite_timestep_init_thread_group(thread, nthreads, errflg, errmsg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg, '(3a)') "No suite part named ", trim(suite_part),                           &
// CHECK-NEXT:            " found in suite thread_suite"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_physics_timestep_init
// CHECK-LABEL:   subroutine ccpp_physics_timestep_final(suite_name, suite_part, lb, ub, thread, nthreads,        &
// CHECK:           errmsg, errflg)
// CHECK-NEXT:      character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), intent(in) :: suite_part
// CHECK-NEXT:      integer, intent(in) :: lb
// CHECK-NEXT:      integer, intent(in) :: ub
// CHECK-NEXT:      integer, intent(in) :: thread
// CHECK-NEXT:      integer, intent(in) :: nthreads
// CHECK-NEXT:      character(len=512), intent(inout) :: errmsg
// CHECK-NEXT:      integer, intent(inout) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'thread_suite') then
// CHECK-NEXT:        if (trim(suite_part) .eq. 'thread_group') then
// CHECK-NEXT:          call thread_suite_timestep_final_thread_group(thread, nthreads, errflg, errmsg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg, '(3a)') "No suite part named ", trim(suite_part),                           &
// CHECK-NEXT:            " found in suite thread_suite"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_physics_timestep_final
// CHECK-LABEL:   subroutine ccpp_physics_init(suite_name, suite_part, lb, ub, thread, nthreads, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), intent(in) :: suite_part
// CHECK-NEXT:      integer, intent(in) :: lb
// CHECK-NEXT:      integer, intent(in) :: ub
// CHECK-NEXT:      integer, intent(in) :: thread
// CHECK-NEXT:      integer, intent(in) :: nthreads
// CHECK-NEXT:      character(len=512), intent(inout) :: errmsg
// CHECK-NEXT:      integer, intent(inout) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'thread_suite') then
// CHECK-NEXT:        if (trim(suite_part) .eq. 'thread_group') then
// CHECK-NEXT:          call thread_suite_init_thread_group(thread, nthreads, errflg, errmsg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg, '(3a)') "No suite part named ", trim(suite_part),                           &
// CHECK-NEXT:            " found in suite thread_suite"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_physics_init
// CHECK-LABEL:   subroutine ccpp_physics_final(suite_name, suite_part, lb, ub, thread, nthreads, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), intent(in) :: suite_part
// CHECK-NEXT:      integer, intent(in) :: lb
// CHECK-NEXT:      integer, intent(in) :: ub
// CHECK-NEXT:      integer, intent(in) :: thread
// CHECK-NEXT:      integer, intent(in) :: nthreads
// CHECK-NEXT:      character(len=512), intent(inout) :: errmsg
// CHECK-NEXT:      integer, intent(inout) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'thread_suite') then
// CHECK-NEXT:        if (trim(suite_part) .eq. 'thread_group') then
// CHECK-NEXT:          call thread_suite_final_thread_group(thread, nthreads, errflg, errmsg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg, '(3a)') "No suite part named ", trim(suite_part),                           &
// CHECK-NEXT:            " found in suite thread_suite"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_physics_final
// CHECK-LABEL:   subroutine ccpp_physics_suite_list(suites)
// CHECK:           character(len=*), allocatable, intent(out) :: suites(:)
// CHECK:           allocate(suites(1))
// CHECK-NEXT:      suites(1) = str_thread_suite
// CHECK-NEXT:    end subroutine ccpp_physics_suite_list
// CHECK-LABEL:   subroutine ccpp_physics_suite_part_list(suite_name, part_list, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), allocatable, intent(out) :: part_list(:)
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'thread_suite') then
// CHECK-NEXT:        allocate(part_list(1))
// CHECK-NEXT:        part_list(1) = str_thread_group
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_physics_suite_part_list
// CHECK-LABEL:   subroutine ccpp_physics_suite_variables(suite_name, var_list, errmsg, errflg, input_vars,       &
// CHECK:           output_vars)
// CHECK-NEXT:      character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), allocatable, intent(out) :: var_list(:)
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      logical, optional, intent(in) :: input_vars
// CHECK-NEXT:      logical, optional, intent(in) :: output_vars
// CHECK-NEXT:      logical :: do_input
// CHECK-NEXT:      logical :: do_output
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      do_input = .true.
// CHECK-NEXT:      do_output = .true.
// CHECK-NEXT:      if (present(input_vars)) then
// CHECK-NEXT:        do_input = input_vars
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (present(output_vars)) then
// CHECK-NEXT:        do_output = output_vars
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (trim(suite_name) .eq. 'thread_suite') then
// CHECK-NEXT:        if (do_input .and. (.NOT. (do_output))) then
// CHECK-NEXT:          allocate(var_list(2))
// CHECK-NEXT:          var_list(1) = 'data_array                          '
// CHECK-NEXT:          var_list(2) = 'horizontal_dimension                '
// CHECK-NEXT:        else
// CHECK-NEXT:          if ((.NOT. (do_input)) .and. do_output) then
// CHECK-NEXT:            allocate(var_list(3))
// CHECK-NEXT:            var_list(1) = 'ccpp_error_code                     '
// CHECK-NEXT:            var_list(2) = 'ccpp_error_message                  '
// CHECK-NEXT:            var_list(3) = 'data_array                          '
// CHECK-NEXT:          else
// CHECK-NEXT:            allocate(var_list(4))
// CHECK-NEXT:            var_list(1) = 'ccpp_error_code                     '
// CHECK-NEXT:            var_list(2) = 'ccpp_error_message                  '
// CHECK-NEXT:            var_list(3) = 'data_array                          '
// CHECK-NEXT:            var_list(4) = 'horizontal_dimension                '
// CHECK-NEXT:          end if
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_physics_suite_variables
// CHECK-NEXT:  end module Thread_ccpp_cap
// CHECK:       // -----
// CHECK-LABEL: // FILE: ccpp_kinds.F90
// CHECK-LABEL: module ccpp_kinds
// CHECK:         use ISO_FORTRAN_ENV, only: kind_phys => REAL64
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         public :: kind_phys
// CHECK-NEXT:  end module ccpp_kinds
