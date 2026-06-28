// Test the full XML frontend → optimizer → Fortran pipeline for the helloworld
// example when the host model declares a ccpp_t variable.  Verifies that:
//   - ccpp_suite_state is declared as dimension(200) (per-instance array)
//   - All suite cap subroutines receive ccpp_data as an intent(inout) argument
//   - State guards and assignments are indexed by ccpp_data%ccpp_instance
//   - All ccpp cap lifecycle/run subroutines thread ccpp_data through
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/helloworld/hello_world_suite.xml --scheme-files examples/helloworld/hello_scheme.meta,examples/helloworld/temp_adjust.meta --host-files examples/helloworld/hello_world_host_ccpp_t.meta,examples/helloworld/hello_world_mod.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p generate-meta-cap,generate-meta-kinds,generate-host-match,generate-suite-cap,generate-ccpp-cap,generate-kinds,strip-ccpp -t ftn | python3 -m filecheck %s

// CHECK-LABEL: // FILE: hello_world_suite_cap.F90
// CHECK-LABEL: module hello_world_suite_cap
// CHECK:         use ccpp_kinds
// CHECK-NEXT:    use ccpp_types, only: ccpp_t
// CHECK-NEXT:    use hello_scheme, only: hello_scheme_finalize
// CHECK-NEXT:    use hello_scheme, only: hello_scheme_init
// CHECK-NEXT:    use hello_scheme, only: hello_scheme_run
// CHECK-NEXT:    use temp_adjust, only: temp_adjust_finalize
// CHECK-NEXT:    use temp_adjust, only: temp_adjust_init
// CHECK-NEXT:    use temp_adjust, only: temp_adjust_run
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         character(len=16), dimension(200) :: ccpp_suite_state = 'uninitialized'
// CHECK-NEXT:    character(len=16), parameter :: const_in_time_step = 'in_time_step'
// CHECK-NEXT:    character(len=16), parameter :: const_initialized = 'initialized'
// CHECK-NEXT:    character(len=16), parameter :: const_uninitialized = 'uninitialized'
// CHECK-NEXT:    public :: hello_world_suite_suite_register
// CHECK-NEXT:    public :: hello_world_suite_suite_initialize
// CHECK-NEXT:    public :: hello_world_suite_suite_finalize
// CHECK-NEXT:    public :: hello_world_suite_suite_timestep_initial
// CHECK-NEXT:    public :: hello_world_suite_suite_timestep_final
// CHECK-NEXT:    public :: hello_world_suite_suite_physics
// CHECK:       CONTAINS
// CHECK-LABEL:   subroutine hello_world_suite_suite_register(ccpp_data, errflg, errmsg)
// CHECK:           type(ccpp_t), intent(inout) :: ccpp_data
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:    end subroutine hello_world_suite_suite_register
// CHECK-LABEL:   subroutine hello_world_suite_suite_initialize(ccpp_data, errmsg, errflg)
// CHECK:           type(ccpp_t), intent(inout) :: ccpp_data
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_uninitialized .eq. ccpp_suite_state(ccpp_data%ccpp_instance))) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '",                                      &
// CHECK-NEXT:          trim(ccpp_suite_state(ccpp_data%ccpp_instance)), "' in hello_world_suite_initialize"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call hello_scheme_init(errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call temp_adjust_init(errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state(ccpp_data%ccpp_instance) = const_initialized
// CHECK-NEXT:    end subroutine hello_world_suite_suite_initialize
// CHECK-LABEL:   subroutine hello_world_suite_suite_finalize(ccpp_data, errmsg, errflg)
// CHECK:           type(ccpp_t), intent(inout) :: ccpp_data
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state(ccpp_data%ccpp_instance))) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '",                                      &
// CHECK-NEXT:          trim(ccpp_suite_state(ccpp_data%ccpp_instance)), "' in hello_world_suite_finalize"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call hello_scheme_finalize(errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call temp_adjust_finalize(errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state(ccpp_data%ccpp_instance) = const_uninitialized
// CHECK-NEXT:    end subroutine hello_world_suite_suite_finalize
// CHECK-LABEL:   subroutine hello_world_suite_suite_timestep_initial(ccpp_data, errflg, errmsg)
// CHECK:           type(ccpp_t), intent(inout) :: ccpp_data
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state(ccpp_data%ccpp_instance))) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '",                                      &
// CHECK-NEXT:          trim(ccpp_suite_state(ccpp_data%ccpp_instance)), "' in hello_world_suite_timestep_initial"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state(ccpp_data%ccpp_instance) = const_in_time_step
// CHECK-NEXT:    end subroutine hello_world_suite_suite_timestep_initial
// CHECK-LABEL:   subroutine hello_world_suite_suite_timestep_final(ccpp_data, errflg, errmsg)
// CHECK:           type(ccpp_t), intent(inout) :: ccpp_data
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_in_time_step .eq. ccpp_suite_state(ccpp_data%ccpp_instance))) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '",                                      &
// CHECK-NEXT:          trim(ccpp_suite_state(ccpp_data%ccpp_instance)), "' in hello_world_suite_timestep_final"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state(ccpp_data%ccpp_instance) = const_initialized
// CHECK-NEXT:    end subroutine hello_world_suite_suite_timestep_final
// CHECK-LABEL:   subroutine hello_world_suite_suite_physics(col_start, col_end, lev, ilev, timestep, temp_level, &
// CHECK:           temp_layer, ccpp_data, errmsg, errflg)
// CHECK-NEXT:      integer, intent(in) :: col_start
// CHECK-NEXT:      integer, intent(in) :: col_end
// CHECK-NEXT:      integer, intent(in) :: lev
// CHECK-NEXT:      integer, intent(in) :: ilev
// CHECK-NEXT:      real(kind=kind_phys), intent(in) :: timestep
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: temp_level(:, :)
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: temp_layer(:, :)
// CHECK-NEXT:      type(ccpp_t), intent(inout) :: ccpp_data
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      integer :: ncol
// CHECK-NEXT:      integer :: ccpp_lbound_one
// CHECK-NEXT:      real(kind=kind_dyn), allocatable :: temp_level_kind_cast(:, :)
// CHECK-NEXT:      real(kind=kind_phys), allocatable :: temp_layer_unit_conv(:, :)
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      ncol = col_end - col_start + 1
// CHECK-NEXT:      ccpp_lbound_one = 1
// CHECK-NEXT:      allocate(temp_level_kind_cast(size(temp_level, 1), size(temp_level, 2)))
// CHECK-NEXT:      temp_level_kind_cast = real(temp_level, kind=kind_dyn)
// CHECK-NEXT:      allocate(temp_layer_unit_conv(size(temp_layer, 1), size(temp_layer, 2)))
// CHECK-NEXT:      if (.NOT. (const_in_time_step .eq. ccpp_suite_state(ccpp_data%ccpp_instance))) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '",                                      &
// CHECK-NEXT:          trim(ccpp_suite_state(ccpp_data%ccpp_instance)), "' in hello_world_suite_physics"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call hello_scheme_run(ncol, lev, ilev, timestep, temp_level_kind_cast,                      &
// CHECK-NEXT:          temp_layer_unit_conv, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call temp_adjust_run(ncol, lev, temp_layer_unit_conv, timestep, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      temp_level = real(temp_level_kind_cast, kind=kind_phys)
// CHECK-NEXT:      deallocate(temp_level_kind_cast)
// CHECK-NEXT:      temp_layer = temp_layer_unit_conv - 273.15_kind_phys
// CHECK-NEXT:      deallocate(temp_layer_unit_conv)
// CHECK-NEXT:    end subroutine hello_world_suite_suite_physics
// CHECK-NEXT:  end module hello_world_suite_cap
// CHECK:       // -----
// CHECK-LABEL: // FILE: HelloWorld_ccpp_cap.F90
// CHECK-LABEL: module HelloWorld_ccpp_cap
// CHECK:         use ccpp_kinds
// CHECK-NEXT:    use ccpp_types, only: ccpp_t
// CHECK-NEXT:    use hello_world_mod, only: dt
// CHECK-NEXT:    use hello_world_mod, only: pver
// CHECK-NEXT:    use hello_world_mod, only: pverp
// CHECK-NEXT:    use hello_world_mod, only: temp_interfaces
// CHECK-NEXT:    use hello_world_mod, only: temp_midpoints
// CHECK-NEXT:    use hello_world_suite_cap, only: hello_world_suite_suite_finalize
// CHECK-NEXT:    use hello_world_suite_cap, only: hello_world_suite_suite_initialize
// CHECK-NEXT:    use hello_world_suite_cap, only: hello_world_suite_suite_physics
// CHECK-NEXT:    use hello_world_suite_cap, only: hello_world_suite_suite_register
// CHECK-NEXT:    use hello_world_suite_cap, only: hello_world_suite_suite_timestep_final
// CHECK-NEXT:    use hello_world_suite_cap, only: hello_world_suite_suite_timestep_initial
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         character(len=17), parameter :: str_hello_world_suite = 'hello_world_suite'
// CHECK-NEXT:    character(len=7), parameter :: str_physics = 'physics'
// CHECK-NEXT:    public :: HelloWorld_ccpp_physics_register
// CHECK-NEXT:    public :: HelloWorld_ccpp_physics_initialize
// CHECK-NEXT:    public :: HelloWorld_ccpp_physics_finalize
// CHECK-NEXT:    public :: HelloWorld_ccpp_physics_timestep_initial
// CHECK-NEXT:    public :: HelloWorld_ccpp_physics_timestep_final
// CHECK-NEXT:    public :: HelloWorld_ccpp_physics_run
// CHECK-NEXT:    public :: ccpp_physics_suite_list
// CHECK-NEXT:    public :: ccpp_physics_suite_part_list
// CHECK-NEXT:    public :: ccpp_physics_suite_variables
// CHECK:       CONTAINS
// CHECK-LABEL:   subroutine HelloWorld_ccpp_physics_register(suite_name, ccpp_data, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      type(ccpp_t), intent(inout) :: ccpp_data
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'hello_world_suite') then
// CHECK-NEXT:        call hello_world_suite_suite_register(ccpp_data, errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), "found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine HelloWorld_ccpp_physics_register
// CHECK-LABEL:   subroutine HelloWorld_ccpp_physics_initialize(suite_name, ccpp_data, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      type(ccpp_t), intent(inout) :: ccpp_data
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'hello_world_suite') then
// CHECK-NEXT:        call hello_world_suite_suite_initialize(ccpp_data, errmsg, errflg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), "found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine HelloWorld_ccpp_physics_initialize
// CHECK-LABEL:   subroutine HelloWorld_ccpp_physics_finalize(suite_name, ccpp_data, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      type(ccpp_t), intent(inout) :: ccpp_data
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'hello_world_suite') then
// CHECK-NEXT:        call hello_world_suite_suite_finalize(ccpp_data, errmsg, errflg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), "found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine HelloWorld_ccpp_physics_finalize
// CHECK-LABEL:   subroutine HelloWorld_ccpp_physics_timestep_initial(suite_name, ccpp_data, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      type(ccpp_t), intent(inout) :: ccpp_data
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'hello_world_suite') then
// CHECK-NEXT:        call hello_world_suite_suite_timestep_initial(ccpp_data, errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), "found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine HelloWorld_ccpp_physics_timestep_initial
// CHECK-LABEL:   subroutine HelloWorld_ccpp_physics_timestep_final(suite_name, ccpp_data, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      type(ccpp_t), intent(inout) :: ccpp_data
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'hello_world_suite') then
// CHECK-NEXT:        call hello_world_suite_suite_timestep_final(ccpp_data, errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), "found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine HelloWorld_ccpp_physics_timestep_final
// CHECK-LABEL:   subroutine HelloWorld_ccpp_physics_run(suite_name, suite_part, ccpp_data, col_start, col_end,   &
// CHECK:           errmsg, errflg)
// CHECK-NEXT:      character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), intent(in) :: suite_part
// CHECK-NEXT:      type(ccpp_t), intent(inout) :: ccpp_data
// CHECK-NEXT:      integer, intent(in) :: col_start
// CHECK-NEXT:      integer, intent(in) :: col_end
// CHECK-NEXT:      character(len=512), intent(inout) :: errmsg
// CHECK-NEXT:      integer, intent(inout) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'hello_world_suite') then
// CHECK-NEXT:        if (trim(suite_part) .eq. 'physics') then
// CHECK-NEXT:          call hello_world_suite_suite_physics(col_start, col_end, pver, pverp, dt,                 &
// CHECK-NEXT:            temp_interfaces(col_start:col_end, 1:pverp), temp_midpoints(col_start:col_end, 1:pver), &
// CHECK-NEXT:            ccpp_data, errmsg, errflg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg, '(3a)') "No suite part named ", trim(suite_part),                           &
// CHECK-NEXT:            " found in suite hello_world_suite"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), "found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine HelloWorld_ccpp_physics_run
// CHECK-LABEL:   subroutine ccpp_physics_suite_list(suites)
// CHECK:           character(len=*), allocatable, intent(out) :: suites(:)
// CHECK:           allocate(suites(1))
// CHECK-NEXT:      suites(1) = str_hello_world_suite
// CHECK-NEXT:    end subroutine ccpp_physics_suite_list
// CHECK-LABEL:   subroutine ccpp_physics_suite_part_list(suite_name, part_list, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), allocatable, intent(out) :: part_list(:)
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'hello_world_suite') then
// CHECK-NEXT:        allocate(part_list(1))
// CHECK-NEXT:        part_list(1) = str_physics
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
// CHECK-NEXT:      logical :: do_input, do_output
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      do_input = .true.
// CHECK-NEXT:      do_output = .true.
// CHECK-NEXT:      if (present(input_vars)) do_input = input_vars
// CHECK-NEXT:      if (present(output_vars)) do_output = output_vars
// CHECK-NEXT:      if (trim(suite_name) .eq. 'hello_world_suite') then
// CHECK-NEXT:        if (do_input .and. .not. do_output) then
// CHECK-NEXT:          allocate(var_list(5))
// CHECK-NEXT:          var_list(1) = 'potential_temperature               '
// CHECK-NEXT:          var_list(2) = 'potential_temperature_at_interface  '
// CHECK-NEXT:          var_list(3) = 'time_step_for_physics               '
// CHECK-NEXT:          var_list(4) = 'vertical_interface_dimension        '
// CHECK-NEXT:          var_list(5) = 'vertical_layer_dimension            '
// CHECK-NEXT:        else if (.not. do_input .and. do_output) then
// CHECK-NEXT:          allocate(var_list(4))
// CHECK-NEXT:          var_list(1) = 'ccpp_error_code                     '
// CHECK-NEXT:          var_list(2) = 'ccpp_error_message                  '
// CHECK-NEXT:          var_list(3) = 'potential_temperature               '
// CHECK-NEXT:          var_list(4) = 'potential_temperature_at_interface  '
// CHECK-NEXT:        else
// CHECK-NEXT:          allocate(var_list(7))
// CHECK-NEXT:          var_list(1) = 'ccpp_error_code                     '
// CHECK-NEXT:          var_list(2) = 'ccpp_error_message                  '
// CHECK-NEXT:          var_list(3) = 'potential_temperature               '
// CHECK-NEXT:          var_list(4) = 'potential_temperature_at_interface  '
// CHECK-NEXT:          var_list(5) = 'time_step_for_physics               '
// CHECK-NEXT:          var_list(6) = 'vertical_interface_dimension        '
// CHECK-NEXT:          var_list(7) = 'vertical_layer_dimension            '
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_physics_suite_variables
// CHECK-NEXT:  end module HelloWorld_ccpp_cap
// CHECK:       // -----
// CHECK-LABEL: // FILE: ccpp_kinds.F90
// CHECK-LABEL: module ccpp_kinds
// CHECK:         use ISO_FORTRAN_ENV, only: kind_phys => REAL64
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         public :: kind_phys
// CHECK-NEXT:    public :: kind_dyn
// CHECK-NEXT:  end module ccpp_kinds
