// End-to-end test: Fortran host calling one Fortran scheme and one C++ scheme.
// Verifies that the suite cap:
//   - uses iso_c_binding (triggered by C++ scheme presence)
//   - imports the Fortran scheme via a normal USE statement
//   - does NOT emit a USE for the C++ scheme module
//   - emits a BIND(C) interface block for the C++ scheme
//   - declares C-interoperable types inside the interface block
//   - calls both schemes inside the physics subroutine
//
// RUN: python3 tests/filecheck/examples/language_suite.py | python3 -m xdsl_ccpp.tools.ccpp_opt -p generate-meta-cap,generate-meta-kinds,generate-arg-ownership,generate-suite-cap,generate-ccpp-cap,generate-cpp-cap,generate-kinds,strip-ccpp -t ftn | python3 -m filecheck %s

// Suite cap module header: iso_c_binding from C++ scheme; Fortran scheme imported normally.

// CHECK-LABEL: // FILE: tiny_suite_cap.F90
// CHECK-LABEL: module tiny_suite_cap
// CHECK:         use ccpp_kinds
// CHECK-NEXT:    use iso_c_binding
// CHECK-NEXT:    use tiny_fortran_scheme, only: tiny_fortran_scheme_run
// CHECK:         interface
// CHECK-NEXT:      subroutine tiny_cxx_scheme_run(ncol, temp, errmsg, errflg) &
// CHECK-NEXT:          BIND(C, name='tiny_cxx_scheme_run')
// CHECK-NEXT:          use iso_c_binding
// CHECK-NEXT:      integer(c_int), value, intent(in) :: ncol
// CHECK-NEXT:      real(c_double), intent(inout) :: temp(*)
// CHECK-NEXT:      character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK-NEXT:      integer(c_int), intent(out) :: errflg
// CHECK-NEXT:      end subroutine tiny_cxx_scheme_run
// CHECK-NEXT:    end interface
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         character(len=16) :: ccpp_suite_state = 'uninitialized'
// CHECK-NEXT:    character(len=16), parameter :: const_in_time_step = 'in_time_step'
// CHECK-NEXT:    character(len=16), parameter :: const_initialized = 'initialized'
// CHECK-NEXT:    character(len=16), parameter :: const_uninitialized = 'uninitialized'
// CHECK-NEXT:    public :: tiny_suite_register
// CHECK-NEXT:    public :: tiny_suite_initialize
// CHECK-NEXT:    public :: tiny_suite_finalize
// CHECK-NEXT:    public :: tiny_suite_init_physics
// CHECK-NEXT:    public :: tiny_suite_physics
// CHECK-NEXT:    public :: tiny_suite_timestep_init_physics
// CHECK-NEXT:    public :: tiny_suite_timestep_final_physics
// CHECK-NEXT:    public :: tiny_suite_final_physics
// CHECK:       CONTAINS
// CHECK-LABEL:   subroutine tiny_suite_register(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:    end subroutine tiny_suite_register
// CHECK-LABEL:   subroutine tiny_suite_initialize(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_uninitialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in tiny_suite_initialize"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_initialized
// CHECK-NEXT:    end subroutine tiny_suite_initialize
// CHECK-LABEL:   subroutine tiny_suite_finalize(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in tiny_suite_finalize"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_uninitialized
// CHECK-NEXT:    end subroutine tiny_suite_finalize
// CHECK-LABEL:   subroutine tiny_suite_init_physics(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in tiny_suite_init_physics"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine tiny_suite_init_physics
// CHECK-LABEL:   subroutine tiny_suite_physics(ncol, temp, errmsg, errflg)
// CHECK:           integer, intent(in) :: ncol
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: temp(:)
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_in_time_step .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in tiny_suite_physics"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call tiny_fortran_scheme_run(ncol=ncol, temp=temp, errmsg=errmsg, errflg=errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call tiny_cxx_scheme_run(ncol=ncol, temp=temp, errmsg=errmsg, errflg=errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine tiny_suite_physics
// CHECK-LABEL:   subroutine tiny_suite_timestep_init_physics(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      ccpp_suite_state = const_in_time_step
// CHECK-NEXT:    end subroutine tiny_suite_timestep_init_physics
// CHECK-LABEL:   subroutine tiny_suite_timestep_final_physics(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      ccpp_suite_state = const_initialized
// CHECK-NEXT:    end subroutine tiny_suite_timestep_final_physics
// CHECK-LABEL:   subroutine tiny_suite_final_physics(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in tiny_suite_final_physics"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine tiny_suite_final_physics
// CHECK-NEXT:  end module tiny_suite_cap
// CHECK:       // -----
// CHECK-LABEL: // FILE: Tiny_ccpp_cap.F90
// CHECK-LABEL: module Tiny_ccpp_cap
// CHECK:         use ccpp_kinds
// CHECK-NEXT:    use ccpp_constituent_prop_mod, only: ccpp_constituent_prop_ptr_t
// CHECK-NEXT:    use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t
// CHECK-NEXT:    use tiny_suite_cap, only: tiny_suite_final_physics
// CHECK-NEXT:    use tiny_suite_cap, only: tiny_suite_finalize
// CHECK-NEXT:    use tiny_suite_cap, only: tiny_suite_init_physics
// CHECK-NEXT:    use tiny_suite_cap, only: tiny_suite_initialize
// CHECK-NEXT:    use tiny_suite_cap, only: tiny_suite_physics
// CHECK-NEXT:    use tiny_suite_cap, only: tiny_suite_register
// CHECK-NEXT:    use tiny_suite_cap, only: tiny_suite_timestep_final_physics
// CHECK-NEXT:    use tiny_suite_cap, only: tiny_suite_timestep_init_physics
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         character(len=10), parameter :: str_tiny_suite = 'tiny_suite'
// CHECK-NEXT:    character(len=7), parameter :: str_physics = 'physics'
// CHECK-NEXT:    type(ccpp_constituent_properties_t), target, allocatable :: lc_all_constituents(:)
// CHECK-NEXT:    real(kind=kind_phys), target, allocatable :: lc_constituent_array(:, :, :)
// CHECK-NEXT:    real(kind=kind_phys), target, allocatable :: lc_const_tend(:, :, :)
// CHECK-NEXT:    type(ccpp_constituent_prop_ptr_t), target, allocatable :: lc_const_props(:)
// CHECK-NEXT:    real(kind=kind_phys) :: lc_ncol
// CHECK-NEXT:    real(kind=kind_phys), allocatable :: lc_temp(:)
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
// CHECK-NEXT:    public :: Tiny_ccpp_is_scheme_constituent
// CHECK-NEXT:    public :: Tiny_ccpp_deallocate_dynamic_constituents
// CHECK-NEXT:    public :: Tiny_ccpp_register_constituents
// CHECK-NEXT:    public :: Tiny_ccpp_number_constituents
// CHECK-NEXT:    public :: Tiny_ccpp_initialize_constituents
// CHECK-NEXT:    public :: Tiny_constituents_array
// CHECK-NEXT:    public :: Tiny_const_get_index
// CHECK-NEXT:    public :: Tiny_model_const_properties
// CHECK:       CONTAINS
// CHECK-LABEL:   subroutine ccpp_register(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'tiny_suite') then
// CHECK-NEXT:        call tiny_suite_register(errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_register
// CHECK-LABEL:   subroutine ccpp_init(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'tiny_suite') then
// CHECK-NEXT:        call tiny_suite_initialize(errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_init
// CHECK-LABEL:   subroutine ccpp_final(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'tiny_suite') then
// CHECK-NEXT:        call tiny_suite_finalize(errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_final
// CHECK-LABEL:   subroutine ccpp_physics_run(suite_name, suite_part, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), intent(in) :: suite_part
// CHECK-NEXT:      character(len=512), intent(inout) :: errmsg
// CHECK-NEXT:      integer, intent(inout) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'tiny_suite') then
// CHECK-NEXT:        if (trim(suite_part) .eq. 'physics') then
// CHECK-NEXT:          call tiny_suite_physics(lc_ncol, lc_temp, errmsg, errflg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg, '(3a)') "No suite part named ", trim(suite_part),                           &
// CHECK-NEXT:            " found in suite tiny_suite"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_physics_run
// CHECK-LABEL:   subroutine ccpp_physics_timestep_init(suite_name, suite_part, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), intent(in) :: suite_part
// CHECK-NEXT:      character(len=512), intent(inout) :: errmsg
// CHECK-NEXT:      integer, intent(inout) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'tiny_suite') then
// CHECK-NEXT:        if (trim(suite_part) .eq. 'physics') then
// CHECK-NEXT:          call tiny_suite_timestep_init_physics(errflg, errmsg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg, '(3a)') "No suite part named ", trim(suite_part),                           &
// CHECK-NEXT:            " found in suite tiny_suite"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_physics_timestep_init
// CHECK-LABEL:   subroutine ccpp_physics_timestep_final(suite_name, suite_part, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), intent(in) :: suite_part
// CHECK-NEXT:      character(len=512), intent(inout) :: errmsg
// CHECK-NEXT:      integer, intent(inout) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'tiny_suite') then
// CHECK-NEXT:        if (trim(suite_part) .eq. 'physics') then
// CHECK-NEXT:          call tiny_suite_timestep_final_physics(errflg, errmsg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg, '(3a)') "No suite part named ", trim(suite_part),                           &
// CHECK-NEXT:            " found in suite tiny_suite"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_physics_timestep_final
// CHECK-LABEL:   subroutine ccpp_physics_init(suite_name, suite_part, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), intent(in) :: suite_part
// CHECK-NEXT:      character(len=512), intent(inout) :: errmsg
// CHECK-NEXT:      integer, intent(inout) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'tiny_suite') then
// CHECK-NEXT:        if (trim(suite_part) .eq. 'physics') then
// CHECK-NEXT:          call tiny_suite_init_physics(errflg, errmsg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg, '(3a)') "No suite part named ", trim(suite_part),                           &
// CHECK-NEXT:            " found in suite tiny_suite"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_physics_init
// CHECK-LABEL:   subroutine ccpp_physics_final(suite_name, suite_part, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), intent(in) :: suite_part
// CHECK-NEXT:      character(len=512), intent(inout) :: errmsg
// CHECK-NEXT:      integer, intent(inout) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'tiny_suite') then
// CHECK-NEXT:        if (trim(suite_part) .eq. 'physics') then
// CHECK-NEXT:          call tiny_suite_final_physics(errflg, errmsg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg, '(3a)') "No suite part named ", trim(suite_part),                           &
// CHECK-NEXT:            " found in suite tiny_suite"
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
// CHECK-NEXT:      suites(1) = str_tiny_suite
// CHECK-NEXT:    end subroutine ccpp_physics_suite_list
// CHECK-LABEL:   subroutine ccpp_physics_suite_part_list(suite_name, part_list, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), allocatable, intent(out) :: part_list(:)
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'tiny_suite') then
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
// CHECK-NEXT:      if (trim(suite_name) .eq. 'tiny_suite') then
// CHECK-NEXT:        if (do_input .and. .not. do_output) then
// CHECK-NEXT:          allocate(var_list(2))
// CHECK-NEXT:          var_list(1) = 'air_temperature                     '
// CHECK-NEXT:          var_list(2) = 'horizontal_dimension                '
// CHECK-NEXT:        else if (.not. do_input .and. do_output) then
// CHECK-NEXT:          allocate(var_list(3))
// CHECK-NEXT:          var_list(1) = 'air_temperature                     '
// CHECK-NEXT:          var_list(2) = 'ccpp_error_code                     '
// CHECK-NEXT:          var_list(3) = 'ccpp_error_message                  '
// CHECK-NEXT:        else
// CHECK-NEXT:          allocate(var_list(4))
// CHECK-NEXT:          var_list(1) = 'air_temperature                     '
// CHECK-NEXT:          var_list(2) = 'ccpp_error_code                     '
// CHECK-NEXT:          var_list(3) = 'ccpp_error_message                  '
// CHECK-NEXT:          var_list(4) = 'horizontal_dimension                '
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_physics_suite_variables
// CHECK-LABEL:   subroutine Tiny_ccpp_is_scheme_constituent(std_name, is_const, errflg, errmsg)
// CHECK:           character(len=*), intent(in) :: std_name
// CHECK-NEXT:      logical, intent(out) :: is_const
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer :: lc_idx
// CHECK-NEXT:      character(len=256) :: lc_std_name
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      is_const = .false.
// CHECK-NEXT:      select case (trim(std_name))
// CHECK-NEXT:      case default
// CHECK-NEXT:      end select
// CHECK-NEXT:    end subroutine Tiny_ccpp_is_scheme_constituent
// CHECK-LABEL:   subroutine Tiny_ccpp_deallocate_dynamic_constituents()
// CHECK:           if (allocated(lc_all_constituents)) deallocate(lc_all_constituents)
// CHECK-NEXT:      if (allocated(lc_const_props)) deallocate(lc_const_props)
// CHECK-NEXT:      if (allocated(lc_constituent_array)) deallocate(lc_constituent_array)
// CHECK-NEXT:      if (allocated(lc_const_tend)) deallocate(lc_const_tend)
// CHECK-NEXT:      if (allocated(lc_ncol)) deallocate(lc_ncol)
// CHECK-NEXT:      if (allocated(lc_temp)) deallocate(lc_temp)
// CHECK-NEXT:    end subroutine Tiny_ccpp_deallocate_dynamic_constituents
// CHECK-LABEL:   subroutine Tiny_ccpp_register_constituents(host_constituents, errmsg, errcode)
// CHECK:           use ccpp_scheme_utils, only: ccpp_scheme_utils_set_constituents
// CHECK-NEXT:      type(ccpp_constituent_properties_t), intent(in) :: host_constituents(:)
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errcode
// CHECK-NEXT:      integer :: lc_max, lc_num, lc_i, lc_j
// CHECK-NEXT:      logical :: lc_found
// CHECK-NEXT:      type(ccpp_constituent_properties_t), allocatable :: lc_tmp(:)
// CHECK-NEXT:      character(len=256) :: lc_src_std_name
// CHECK-NEXT:      character(len=256) :: lc_dst_std_name
// CHECK-NEXT:      character(len=256) :: lc_src_units
// CHECK-NEXT:      character(len=256) :: lc_dst_units
// CHECK-NEXT:      type(ccpp_constituent_properties_t), pointer :: lc_tmp_ptr
// CHECK-NEXT:      errcode = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      lc_max = 0
// CHECK-NEXT:      lc_max = lc_max + 0
// CHECK-NEXT:      lc_max = lc_max + size(host_constituents)
// CHECK-NEXT:      allocate(lc_tmp(lc_max))
// CHECK-NEXT:      lc_num = 0
// CHECK-NEXT:      do lc_i = 1, size(host_constituents)
// CHECK-NEXT:        call host_constituents(lc_i)%standard_name(lc_src_std_name)
// CHECK-NEXT:        call host_constituents(lc_i)%units(lc_src_units)
// CHECK-NEXT:        lc_found = .false.
// CHECK-NEXT:        do lc_j = 1, lc_num
// CHECK-NEXT:          call lc_tmp(lc_j)%standard_name(lc_dst_std_name)
// CHECK-NEXT:          if (trim(lc_dst_std_name) == trim(lc_src_std_name)) then
// CHECK-NEXT:            lc_found = .true.
// CHECK-NEXT:            call lc_tmp(lc_j)%units(lc_dst_units)
// CHECK-NEXT:            if (trim(lc_dst_units) /= trim(lc_src_units)) then
// CHECK-NEXT:              write(errmsg,                                                                         &
// CHECK-NEXT:        '(3a)') 'ccp_model_const_add_metadata ERROR: Trying to add constituent ',                   &
// CHECK-NEXT:        trim(lc_src_std_name), &
// CHECK-NEXT:                ' but an incompatible constituent with this name already exists'
// CHECK-NEXT:              errcode = 1
// CHECK-NEXT:              return
// CHECK-NEXT:            end if
// CHECK-NEXT:            exit
// CHECK-NEXT:          end if
// CHECK-NEXT:        end do
// CHECK-NEXT:        if (.not. lc_found) then
// CHECK-NEXT:          lc_num = lc_num + 1
// CHECK-NEXT:          lc_tmp(lc_num) = host_constituents(lc_i)
// CHECK-NEXT:        end if
// CHECK-NEXT:      end do
// CHECK-NEXT:      if (allocated(lc_all_constituents)) deallocate(lc_all_constituents)
// CHECK-NEXT:      allocate(lc_all_constituents(lc_num))
// CHECK-NEXT:      lc_all_constituents(1:lc_num) = lc_tmp(1:lc_num)
// CHECK-NEXT:      deallocate(lc_tmp)
// CHECK-NEXT:      if (allocated(lc_const_props)) deallocate(lc_const_props)
// CHECK-NEXT:      allocate(lc_const_props(lc_num))
// CHECK-NEXT:      do lc_i = 1, lc_num
// CHECK-NEXT:        lc_tmp_ptr => lc_all_constituents(lc_i)
// CHECK-NEXT:        call lc_const_props(lc_i)%set(lc_tmp_ptr)
// CHECK-NEXT:      end do
// CHECK-NEXT:      call ccpp_scheme_utils_set_constituents(lc_all_constituents)
// CHECK-NEXT:    end subroutine Tiny_ccpp_register_constituents
// CHECK-LABEL:   subroutine Tiny_ccpp_number_constituents(num_advected, errmsg, errcode, advected)
// CHECK:           integer, intent(out) :: num_advected
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errcode
// CHECK-NEXT:      logical, optional, intent(in) :: advected
// CHECK-NEXT:      errcode = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (allocated(lc_all_constituents)) then
// CHECK-NEXT:        num_advected = size(lc_all_constituents)
// CHECK-NEXT:      else
// CHECK-NEXT:        num_advected = 0
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine Tiny_ccpp_number_constituents
// CHECK-LABEL:   subroutine Tiny_ccpp_initialize_constituents(ncols, pver, errflg, errmsg)
// CHECK:           integer, intent(in) :: ncols
// CHECK-NEXT:      integer, intent(in) :: pver
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer :: lc_num, lc_i
// CHECK-NEXT:      logical :: lc_has_def
// CHECK-NEXT:      real(kind=kind_phys) :: lc_def_val
// CHECK-NEXT:      character(len=256) :: lc_std_name
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.not. allocated(lc_all_constituents)) then
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:        errmsg = 'ccpp_initialize_constituents: register_constituents not called'
// CHECK-NEXT:        return
// CHECK-NEXT:      end if
// CHECK-NEXT:      lc_num = size(lc_all_constituents)
// CHECK-NEXT:      if (allocated(lc_constituent_array)) deallocate(lc_constituent_array)
// CHECK-NEXT:      allocate(lc_constituent_array(ncols, pver, lc_num))
// CHECK-NEXT:      lc_constituent_array = 0.0_kind_phys
// CHECK-NEXT:      do lc_i = 1, lc_num
// CHECK-NEXT:        call lc_all_constituents(lc_i)%has_default(lc_has_def, errflg, errmsg)
// CHECK-NEXT:        if (lc_has_def) then
// CHECK-NEXT:          call lc_all_constituents(lc_i)%default_value(lc_def_val, errflg, errmsg)
// CHECK-NEXT:          lc_constituent_array(:, :, lc_i) = lc_def_val
// CHECK-NEXT:        end if
// CHECK-NEXT:      end do
// CHECK-NEXT:      if (allocated(lc_const_tend)) deallocate(lc_const_tend)
// CHECK-NEXT:      allocate(lc_const_tend(ncols, pver, lc_num))
// CHECK-NEXT:      lc_const_tend = 0.0_kind_phys
// CHECK-NEXT:      if (allocated(lc_ncol)) deallocate(lc_ncol)
// CHECK-NEXT:      allocate(lc_ncol(ncols, pver))
// CHECK-NEXT:      lc_ncol = 0.0_kind_phys
// CHECK-NEXT:      if (allocated(lc_temp)) deallocate(lc_temp)
// CHECK-NEXT:      allocate(lc_temp(ncols))
// CHECK-NEXT:      lc_temp = 0.0_kind_phys
// CHECK-NEXT:    end subroutine Tiny_ccpp_initialize_constituents
// CHECK-NEXT:    function Tiny_constituents_array() result(ptr)
// CHECK-NEXT:      real(kind=kind_phys), pointer :: ptr(:, :, :)
// CHECK-NEXT:      ptr => lc_constituent_array
// CHECK-NEXT:    end function Tiny_constituents_array
// CHECK-LABEL:   subroutine Tiny_const_get_index(std_name, index, errflg, errmsg)
// CHECK:           character(len=*), intent(in) :: std_name
// CHECK-NEXT:      integer, intent(out) :: index
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer :: lc_i
// CHECK-NEXT:      character(len=256) :: lc_std_name
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      index = -1
// CHECK-NEXT:      if (.not. allocated(lc_all_constituents)) then
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:        errmsg = 'const_get_index: constituents not registered'
// CHECK-NEXT:        return
// CHECK-NEXT:      end if
// CHECK-NEXT:      do lc_i = 1, size(lc_all_constituents)
// CHECK-NEXT:        call lc_all_constituents(lc_i)%standard_name(lc_std_name)
// CHECK-NEXT:        if (trim(lc_std_name) == trim(std_name)) then
// CHECK-NEXT:          index = lc_i
// CHECK-NEXT:          return
// CHECK-NEXT:        end if
// CHECK-NEXT:      end do
// CHECK-NEXT:      errflg = 1
// CHECK-NEXT:      write(errmsg, '(3a)') 'const_get_index: constituent ', trim(std_name), ' not found'
// CHECK-NEXT:    end subroutine Tiny_const_get_index
// CHECK-NEXT:    function Tiny_model_const_properties() result(ptr)
// CHECK-NEXT:      type(ccpp_constituent_prop_ptr_t), pointer :: ptr(:)
// CHECK-NEXT:      ptr => lc_const_props
// CHECK-NEXT:    end function Tiny_model_const_properties
// CHECK-NEXT:  end module Tiny_ccpp_cap
// CHECK:       // -----
// CHECK-LABEL: // FILE: ccpp_kinds.F90
// CHECK-LABEL: module ccpp_kinds
// CHECK:         use ISO_FORTRAN_ENV, only: kind_phys => REAL64
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         public :: kind_phys
// CHECK-NEXT:  end module ccpp_kinds
