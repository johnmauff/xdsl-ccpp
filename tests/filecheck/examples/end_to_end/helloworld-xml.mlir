// Test the full XML frontend → optimizer → Fortran pipeline for the helloworld
// example.  Checks that two schemes (hello_scheme, temp_adjust) are lowered to
// a suite cap with correct subroutine signatures, scheme calls guarded by
// errflg, and a ccpp_kinds module using ISO_FORTRAN_ENV.
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/helloworld/hello_world_suite.xml --scheme-files examples/helloworld/hello_scheme.meta,examples/helloworld/temp_adjust.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap,generate-cpp-cap,generate-kinds,strip-ccpp -t ftn | python3 -m filecheck %s

// CHECK-LABEL: // FILE: hello_world_suite_cap.F90
// CHECK-LABEL: module hello_world_suite_cap
// CHECK:         use ccpp_kinds
// CHECK-NEXT:    use hello_scheme, only: hello_scheme_finalize
// CHECK-NEXT:    use hello_scheme, only: hello_scheme_init
// CHECK-NEXT:    use hello_scheme, only: hello_scheme_run
// CHECK-NEXT:    use temp_adjust, only: temp_adjust_finalize
// CHECK-NEXT:    use temp_adjust, only: temp_adjust_init
// CHECK-NEXT:    use temp_adjust, only: temp_adjust_run
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         character(len=16) :: ccpp_suite_state = 'uninitialized'
// CHECK-NEXT:    character(len=16), parameter :: const_in_time_step = 'in_time_step'
// CHECK-NEXT:    character(len=16), parameter :: const_initialized = 'initialized'
// CHECK-NEXT:    character(len=16), parameter :: const_uninitialized = 'uninitialized'
// CHECK-NEXT:    real(kind=kind_phys), allocatable :: temp_layer(:, :)
// CHECK-NEXT:    public :: hello_world_suite_suite_register
// CHECK-NEXT:    public :: hello_world_suite_suite_initialize
// CHECK-NEXT:    public :: hello_world_suite_suite_finalize
// CHECK-NEXT:    public :: hello_world_suite_suite_timestep_initial
// CHECK-NEXT:    public :: hello_world_suite_suite_timestep_final
// CHECK-NEXT:    public :: hello_world_suite_suite_physics
// CHECK:       CONTAINS
// CHECK-LABEL:   subroutine hello_world_suite_suite_register(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:    end subroutine hello_world_suite_suite_register
// CHECK-LABEL:   subroutine hello_world_suite_suite_initialize(errmsg, errflg)
// CHECK:           character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_uninitialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in hello_world_suite_initialize"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call hello_scheme_init(errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call temp_adjust_init(errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_initialized
// CHECK-NEXT:    end subroutine hello_world_suite_suite_initialize
// CHECK-LABEL:   subroutine hello_world_suite_suite_finalize(errmsg, errflg)
// CHECK:           character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in hello_world_suite_finalize"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call hello_scheme_finalize(errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call temp_adjust_finalize(errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_uninitialized
// CHECK-NEXT:    end subroutine hello_world_suite_suite_finalize
// CHECK-LABEL:   subroutine hello_world_suite_suite_timestep_initial(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in hello_world_suite_timestep_initial"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_in_time_step
// CHECK-NEXT:    end subroutine hello_world_suite_suite_timestep_initial
// CHECK-LABEL:   subroutine hello_world_suite_suite_timestep_final(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_in_time_step .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in hello_world_suite_timestep_final"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_initialized
// CHECK-NEXT:    end subroutine hello_world_suite_suite_timestep_final
// CHECK-LABEL:   subroutine hello_world_suite_suite_physics(col_start, col_end, lev, ilev, timestep, temp_level, &
// CHECK:           temp_layer, errmsg, errflg)
// CHECK-NEXT:      integer, intent(in) :: col_start
// CHECK-NEXT:      integer, intent(in) :: col_end
// CHECK-NEXT:      integer, intent(in) :: lev
// CHECK-NEXT:      integer, intent(in) :: ilev
// CHECK-NEXT:      real(kind=kind_phys), intent(in) :: timestep
// CHECK-NEXT:      real(kind=kind_dyn), target, intent(inout) :: temp_level(:, :)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: temp_layer(:, :)
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      integer :: ncol
// CHECK-NEXT:      integer :: ccpp_lbound_one
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      ncol = col_end - col_start + 1
// CHECK-NEXT:      ccpp_lbound_one = 1
// CHECK-NEXT:      if (.NOT. (const_in_time_step .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in hello_world_suite_physics"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call hello_scheme_run(ncol, lev, ilev, timestep, temp_level, temp_layer, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call temp_adjust_run(ncol, lev, temp_layer, timestep, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine hello_world_suite_suite_physics
// CHECK-NEXT:  end module hello_world_suite_cap
// CHECK:       // -----
// CHECK-LABEL: // FILE: HelloWorld_ccpp_cap.F90
// CHECK-LABEL: module HelloWorld_ccpp_cap
// CHECK:         use ccpp_kinds
// CHECK-NEXT:    use ccpp_constituent_prop_mod, only: ccpp_constituent_prop_ptr_t
// CHECK-NEXT:    use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t
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
// CHECK-NEXT:    type(ccpp_constituent_properties_t), target, allocatable :: lc_all_constituents(:)
// CHECK-NEXT:    real(kind=kind_phys), target, allocatable :: lc_constituent_array(:, :, :)
// CHECK-NEXT:    real(kind=kind_phys), target, allocatable :: lc_const_tend(:, :, :)
// CHECK-NEXT:    type(ccpp_constituent_prop_ptr_t), target, allocatable :: lc_const_props(:)
// CHECK-NEXT:    real(kind=kind_phys) :: lc_lev
// CHECK-NEXT:    real(kind=kind_phys) :: lc_ilev
// CHECK-NEXT:    real(kind=kind_phys) :: lc_timestep
// CHECK-NEXT:    real(kind=kind_phys), allocatable :: lc_temp_level(:, :)
// CHECK-NEXT:    real(kind=kind_phys), allocatable :: lc_temp_layer(:, :)
// CHECK-NEXT:    public :: HelloWorld_ccpp_physics_register
// CHECK-NEXT:    public :: HelloWorld_ccpp_physics_initialize
// CHECK-NEXT:    public :: HelloWorld_ccpp_physics_finalize
// CHECK-NEXT:    public :: HelloWorld_ccpp_physics_timestep_initial
// CHECK-NEXT:    public :: HelloWorld_ccpp_physics_timestep_final
// CHECK-NEXT:    public :: HelloWorld_ccpp_physics_run
// CHECK-NEXT:    public :: ccpp_physics_suite_list
// CHECK-NEXT:    public :: ccpp_physics_suite_part_list
// CHECK-NEXT:    public :: ccpp_physics_suite_variables
// CHECK-NEXT:    public :: HelloWorld_ccpp_is_scheme_constituent
// CHECK-NEXT:    public :: HelloWorld_ccpp_deallocate_dynamic_constituents
// CHECK-NEXT:    public :: HelloWorld_ccpp_register_constituents
// CHECK-NEXT:    public :: HelloWorld_ccpp_number_constituents
// CHECK-NEXT:    public :: HelloWorld_ccpp_initialize_constituents
// CHECK-NEXT:    public :: HelloWorld_constituents_array
// CHECK-NEXT:    public :: HelloWorld_const_get_index
// CHECK-NEXT:    public :: HelloWorld_model_const_properties
// CHECK:       CONTAINS
// CHECK-LABEL:   subroutine HelloWorld_ccpp_physics_register(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'hello_world_suite') then
// CHECK-NEXT:        call hello_world_suite_suite_register(errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine HelloWorld_ccpp_physics_register
// CHECK-LABEL:   subroutine HelloWorld_ccpp_physics_initialize(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'hello_world_suite') then
// CHECK-NEXT:        call hello_world_suite_suite_initialize(errmsg, errflg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine HelloWorld_ccpp_physics_initialize
// CHECK-LABEL:   subroutine HelloWorld_ccpp_physics_finalize(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'hello_world_suite') then
// CHECK-NEXT:        call hello_world_suite_suite_finalize(errmsg, errflg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine HelloWorld_ccpp_physics_finalize
// CHECK-LABEL:   subroutine HelloWorld_ccpp_physics_timestep_initial(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'hello_world_suite') then
// CHECK-NEXT:        call hello_world_suite_suite_timestep_initial(errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine HelloWorld_ccpp_physics_timestep_initial
// CHECK-LABEL:   subroutine HelloWorld_ccpp_physics_timestep_final(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'hello_world_suite') then
// CHECK-NEXT:        call hello_world_suite_suite_timestep_final(errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine HelloWorld_ccpp_physics_timestep_final
// CHECK-LABEL:   subroutine HelloWorld_ccpp_physics_run(suite_name, suite_part, col_start, col_end, errmsg,      &
// CHECK:           errflg)
// CHECK-NEXT:      character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), intent(in) :: suite_part
// CHECK-NEXT:      integer, intent(in) :: col_start
// CHECK-NEXT:      integer, intent(in) :: col_end
// CHECK-NEXT:      character(len=512), intent(inout) :: errmsg
// CHECK-NEXT:      integer, intent(inout) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'hello_world_suite') then
// CHECK-NEXT:        if (trim(suite_part) .eq. 'physics') then
// CHECK-NEXT:          call hello_world_suite_suite_physics(col_start, col_end, lc_lev, lc_ilev, lc_timestep,    &
// CHECK-NEXT:            lc_temp_level(:, :), lc_temp_layer(:, :), errmsg, errflg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg, '(3a)') "No suite part named ", trim(suite_part),                           &
// CHECK-NEXT:            " found in suite hello_world_suite"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
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
// CHECK-NEXT:      subroutine HelloWorld_ccpp_is_scheme_constituent(std_name, is_const, errflg, errmsg)
// CHECK-NEXT:        character(len=*), intent(in) :: std_name
// CHECK-NEXT:        logical, intent(out) :: is_const
// CHECK-NEXT:        integer, intent(out) :: errflg
// CHECK-NEXT:        character(len=512), intent(out) :: errmsg
// CHECK-NEXT:        integer :: lc_idx
// CHECK-NEXT:        errflg = 0
// CHECK-NEXT:        errmsg = ''
// CHECK-NEXT:        is_const = .false.
// CHECK-NEXT:        select case (trim(std_name))
// CHECK-NEXT:        case default
// CHECK-NEXT:        end select
// CHECK-NEXT:      end subroutine HelloWorld_ccpp_is_scheme_constituent
// CHECK:           subroutine HelloWorld_ccpp_deallocate_dynamic_constituents()
// CHECK-NEXT:        if (allocated(lc_all_constituents)) deallocate(lc_all_constituents)
// CHECK-NEXT:        if (allocated(lc_const_props)) deallocate(lc_const_props)
// CHECK-NEXT:        if (allocated(lc_constituent_array)) deallocate(lc_constituent_array)
// CHECK-NEXT:        if (allocated(lc_const_tend)) deallocate(lc_const_tend)
// CHECK-NEXT:        if (allocated(lc_lev)) deallocate(lc_lev)
// CHECK-NEXT:        if (allocated(lc_ilev)) deallocate(lc_ilev)
// CHECK-NEXT:        if (allocated(lc_timestep)) deallocate(lc_timestep)
// CHECK-NEXT:        if (allocated(lc_temp_level)) deallocate(lc_temp_level)
// CHECK-NEXT:        if (allocated(lc_temp_layer)) deallocate(lc_temp_layer)
// CHECK-NEXT:      end subroutine HelloWorld_ccpp_deallocate_dynamic_constituents
// CHECK:           subroutine HelloWorld_ccpp_register_constituents(host_constituents, errmsg, errflg)
// CHECK-NEXT:        use ccpp_scheme_utils, only: ccpp_scheme_utils_set_constituents
// CHECK-NEXT:        type(ccpp_constituent_properties_t), intent(in) :: host_constituents(:)
// CHECK-NEXT:        character(len=512), intent(out) :: errmsg
// CHECK-NEXT:        integer, intent(out) :: errflg
// CHECK-NEXT:        integer :: lc_max, lc_num, lc_i, lc_j
// CHECK-NEXT:        logical :: lc_found
// CHECK-NEXT:        type(ccpp_constituent_properties_t), allocatable :: lc_tmp(:)
// CHECK-NEXT:        errflg = 0
// CHECK-NEXT:        errmsg = ''
// CHECK-NEXT:        lc_max = 0
// CHECK-NEXT:        lc_max = lc_max + 0
// CHECK-NEXT:        lc_max = lc_max + size(host_constituents)
// CHECK-NEXT:        allocate(lc_tmp(lc_max))
// CHECK-NEXT:        lc_num = 0
// CHECK-NEXT:        do lc_i = 1, size(host_constituents)
// CHECK-NEXT:          lc_found = .false.
// CHECK-NEXT:          do lc_j = 1, lc_num
// CHECK-NEXT:            if (trim(lc_tmp(lc_j)%std_name) == trim(host_constituents(lc_i)%std_name)) then
// CHECK-NEXT:              lc_found = .true.
// CHECK-NEXT:              if (trim(lc_tmp(lc_j)%units) /= trim(host_constituents(lc_i)%units)) then
// CHECK-NEXT:                write(errmsg,                                                                       &
// CHECK-NEXT:      '(3a)') 'ccp_model_const_add_metadata ERROR: Trying to add constituent ',                     &
// CHECK-NEXT:      trim(host_constituents(lc_i)%std_name), &
// CHECK-NEXT:                  ' but an incompatible constituent with this name already exists'
// CHECK-NEXT:                errflg = 1
// CHECK-NEXT:                return
// CHECK-NEXT:              end if
// CHECK-NEXT:              exit
// CHECK-NEXT:            end if
// CHECK-NEXT:          end do
// CHECK-NEXT:          if (.not. lc_found) then
// CHECK-NEXT:            lc_num = lc_num + 1
// CHECK-NEXT:            lc_tmp(lc_num) = host_constituents(lc_i)
// CHECK-NEXT:          end if
// CHECK-NEXT:        end do
// CHECK-NEXT:        if (allocated(lc_all_constituents)) deallocate(lc_all_constituents)
// CHECK-NEXT:        allocate(lc_all_constituents(lc_num))
// CHECK-NEXT:        lc_all_constituents(1:lc_num) = lc_tmp(1:lc_num)
// CHECK-NEXT:        deallocate(lc_tmp)
// CHECK-NEXT:        if (allocated(lc_const_props)) deallocate(lc_const_props)
// CHECK-NEXT:        allocate(lc_const_props(lc_num))
// CHECK-NEXT:        do lc_i = 1, lc_num
// CHECK-NEXT:          lc_const_props(lc_i)%ptr => lc_all_constituents(lc_i)
// CHECK-NEXT:        end do
// CHECK-NEXT:        call ccpp_scheme_utils_set_constituents(lc_all_constituents)
// CHECK-NEXT:      end subroutine HelloWorld_ccpp_register_constituents
// CHECK:           subroutine HelloWorld_ccpp_number_constituents(num_advected, errmsg, errflg)
// CHECK-NEXT:        integer, intent(out) :: num_advected
// CHECK-NEXT:        character(len=512), intent(out) :: errmsg
// CHECK-NEXT:        integer, intent(out) :: errflg
// CHECK-NEXT:        errflg = 0
// CHECK-NEXT:        errmsg = ''
// CHECK-NEXT:        if (allocated(lc_all_constituents)) then
// CHECK-NEXT:          num_advected = size(lc_all_constituents)
// CHECK-NEXT:        else
// CHECK-NEXT:          num_advected = 0
// CHECK-NEXT:        end if
// CHECK-NEXT:      end subroutine HelloWorld_ccpp_number_constituents
// CHECK:           subroutine HelloWorld_ccpp_initialize_constituents(ncols, pver, errflg, errmsg)
// CHECK-NEXT:        integer, intent(in) :: ncols
// CHECK-NEXT:        integer, intent(in) :: pver
// CHECK-NEXT:        integer, intent(out) :: errflg
// CHECK-NEXT:        character(len=512), intent(out) :: errmsg
// CHECK-NEXT:        integer :: lc_num, lc_i
// CHECK-NEXT:        errflg = 0
// CHECK-NEXT:        errmsg = ''
// CHECK-NEXT:        if (.not. allocated(lc_all_constituents)) then
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:          errmsg = 'ccpp_initialize_constituents: register_constituents not called'
// CHECK-NEXT:          return
// CHECK-NEXT:        end if
// CHECK-NEXT:        lc_num = size(lc_all_constituents)
// CHECK-NEXT:        if (allocated(lc_constituent_array)) deallocate(lc_constituent_array)
// CHECK-NEXT:        allocate(lc_constituent_array(ncols, pver, lc_num))
// CHECK-NEXT:        lc_constituent_array = 0.0_kind_phys
// CHECK-NEXT:        do lc_i = 1, lc_num
// CHECK-NEXT:          if (lc_all_constituents(lc_i)%default_val_set) then
// CHECK-NEXT:            lc_constituent_array(:, :, lc_i) = lc_all_constituents(lc_i)%default_val
// CHECK-NEXT:          end if
// CHECK-NEXT:        end do
// CHECK-NEXT:        if (allocated(lc_const_tend)) deallocate(lc_const_tend)
// CHECK-NEXT:        allocate(lc_const_tend(ncols, pver, lc_num))
// CHECK-NEXT:        lc_const_tend = 0.0_kind_phys
// CHECK-NEXT:        if (allocated(lc_lev)) deallocate(lc_lev)
// CHECK-NEXT:        allocate(lc_lev(ncols, pver))
// CHECK-NEXT:        lc_lev = 0.0_kind_phys
// CHECK-NEXT:        if (allocated(lc_ilev)) deallocate(lc_ilev)
// CHECK-NEXT:        allocate(lc_ilev(ncols, pver))
// CHECK-NEXT:        lc_ilev = 0.0_kind_phys
// CHECK-NEXT:        if (allocated(lc_timestep)) deallocate(lc_timestep)
// CHECK-NEXT:        allocate(lc_timestep(ncols, pver))
// CHECK-NEXT:        lc_timestep = 0.0_kind_phys
// CHECK-NEXT:        if (allocated(lc_temp_level)) deallocate(lc_temp_level)
// CHECK-NEXT:        allocate(lc_temp_level(ncols, 1))
// CHECK-NEXT:        lc_temp_level = 0.0_kind_phys
// CHECK-NEXT:        if (allocated(lc_temp_layer)) deallocate(lc_temp_layer)
// CHECK-NEXT:        allocate(lc_temp_layer(ncols, pver))
// CHECK-NEXT:        lc_temp_layer = 0.0_kind_phys
// CHECK-NEXT:      end subroutine HelloWorld_ccpp_initialize_constituents
// CHECK:           function HelloWorld_constituents_array() result(ptr)
// CHECK-NEXT:        real(kind=kind_phys), pointer :: ptr(:, :, :)
// CHECK-NEXT:        ptr => lc_constituent_array
// CHECK-NEXT:      end function HelloWorld_constituents_array
// CHECK:           subroutine HelloWorld_const_get_index(std_name, index, errflg, errmsg)
// CHECK-NEXT:        character(len=*), intent(in) :: std_name
// CHECK-NEXT:        integer, intent(out) :: index
// CHECK-NEXT:        integer, intent(out) :: errflg
// CHECK-NEXT:        character(len=512), intent(out) :: errmsg
// CHECK-NEXT:        integer :: lc_i
// CHECK-NEXT:        errflg = 0
// CHECK-NEXT:        errmsg = ''
// CHECK-NEXT:        index = -1
// CHECK-NEXT:        if (.not. allocated(lc_all_constituents)) then
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:          errmsg = 'const_get_index: constituents not registered'
// CHECK-NEXT:          return
// CHECK-NEXT:        end if
// CHECK-NEXT:        do lc_i = 1, size(lc_all_constituents)
// CHECK-NEXT:          if (trim(lc_all_constituents(lc_i)%std_name) == trim(std_name)) then
// CHECK-NEXT:            index = lc_i
// CHECK-NEXT:            return
// CHECK-NEXT:          end if
// CHECK-NEXT:        end do
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:        write(errmsg, '(3a)') 'const_get_index: constituent ', trim(std_name), ' not found'
// CHECK-NEXT:      end subroutine HelloWorld_const_get_index
// CHECK:           function HelloWorld_model_const_properties() result(ptr)
// CHECK-NEXT:        type(ccpp_constituent_prop_ptr_t), pointer :: ptr(:)
// CHECK-NEXT:        ptr => lc_const_props
// CHECK-NEXT:      end function HelloWorld_model_const_properties
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
