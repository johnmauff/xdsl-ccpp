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
// CHECK-NEXT:    use ccpp_constituent_prop_mod, only: ccpp_model_constituents_t
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
// CHECK-NEXT:    type(ccpp_model_constituents_t), target :: cam_constituents_obj
// CHECK-NEXT:    integer, allocatable :: lc_all_constituents(:)
// CHECK-NEXT:    real(kind=kind_phys), pointer :: lc_constituent_array(:, :, :) => null()
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
// CHECK-NEXT:    end subroutine Tiny_ccpp_is_scheme_constituent
// CHECK-LABEL:   subroutine Tiny_ccpp_deallocate_dynamic_constituents()
// CHECK:           if (allocated(lc_all_constituents)) deallocate(lc_all_constituents)
// CHECK-NEXT:      if (allocated(lc_const_props)) deallocate(lc_const_props)
// CHECK-NEXT:      if (associated(lc_constituent_array)) nullify(lc_constituent_array)
// CHECK-NEXT:      if (allocated(lc_ncol)) deallocate(lc_ncol)
// CHECK-NEXT:      if (allocated(lc_temp)) deallocate(lc_temp)
// CHECK-NEXT:      call cam_constituents_obj%reset()
// CHECK-NEXT:    end subroutine Tiny_ccpp_deallocate_dynamic_constituents
// CHECK-LABEL:   subroutine Tiny_ccpp_register_constituents(host_constituents, errmsg, errcode)
// CHECK:           use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t, ccpp_constituent_prop_ptr_t
// CHECK-NEXT:      use ccpp_scheme_utils, only: ccpp_scheme_utils_set_constituents
// CHECK-NEXT:      type(ccpp_constituent_properties_t), target, intent(in) :: host_constituents(:)
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errcode
// CHECK-NEXT:      integer :: lc_i, lc_num_consts
// CHECK-NEXT:      type(ccpp_constituent_properties_t), pointer :: const_prop
// CHECK-NEXT:      type(ccpp_constituent_prop_ptr_t), pointer :: lc_props_ptr(:)
// CHECK-NEXT:      errcode = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      lc_num_consts = size(host_constituents)
// CHECK-NEXT:      lc_num_consts = lc_num_consts + 0
// CHECK-NEXT:      call cam_constituents_obj%initialize_table(lc_num_consts)
// CHECK-NEXT:      do lc_i = 1, size(host_constituents)
// CHECK-NEXT:        allocate(const_prop, stat=errcode)
// CHECK-NEXT:        if (errcode /= 0) then
// CHECK-NEXT:          errmsg = 'ERROR allocating const_prop'
// CHECK-NEXT:          return
// CHECK-NEXT:        end if
// CHECK-NEXT:        const_prop = host_constituents(lc_i)
// CHECK-NEXT:        call cam_constituents_obj%new_field(const_prop, errcode=errcode, errmsg=errmsg)
// CHECK-NEXT:        nullify(const_prop)
// CHECK-NEXT:        if (errcode /= 0) return
// CHECK-NEXT:      end do
// CHECK-NEXT:      call cam_constituents_obj%lock_table(errcode=errcode, errmsg=errmsg)
// CHECK-NEXT:      if (errcode /= 0) return
// CHECK-NEXT:      lc_props_ptr => cam_constituents_obj%constituent_props_ptr()
// CHECK-NEXT:      if (allocated(lc_const_props)) deallocate(lc_const_props)
// CHECK-NEXT:      allocate(lc_const_props(size(lc_props_ptr)))
// CHECK-NEXT:      lc_const_props = lc_props_ptr
// CHECK-NEXT:      nullify(lc_props_ptr)
// CHECK-NEXT:      call ccpp_scheme_utils_set_constituents(lc_const_props)
// CHECK-NEXT:      call cam_constituents_obj%num_constituents(lc_num_consts, errcode=errcode, errmsg=errmsg)
// CHECK-NEXT:      if (errcode /= 0) return
// CHECK-NEXT:      if (allocated(lc_all_constituents)) deallocate(lc_all_constituents)
// CHECK-NEXT:      allocate(lc_all_constituents(lc_num_consts))
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
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.not. allocated(lc_all_constituents)) then
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:        errmsg = 'ccpp_initialize_constituents: register_constituents not called'
// CHECK-NEXT:        return
// CHECK-NEXT:      end if
// CHECK-NEXT:      call cam_constituents_obj%lock_data(ncols, pver, errcode=errflg, errmsg=errmsg)
// CHECK-NEXT:      if (errflg /= 0) return
// CHECK-NEXT:      lc_constituent_array => cam_constituents_obj%field_data_ptr()
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
// CHECK:           use ccpp_constituent_prop_mod, only: to_lower
// CHECK-NEXT:      character(len=*), intent(in) :: std_name
// CHECK-NEXT:      integer, intent(out) :: index
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      index = -1
// CHECK-NEXT:      if (.not. allocated(lc_all_constituents)) then
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:        errmsg = 'const_get_index: constituents not registered'
// CHECK-NEXT:        return
// CHECK-NEXT:      end if
// CHECK-NEXT:      call cam_constituents_obj%const_index(index, to_lower(std_name), &
// CHECK-NEXT:          errcode=errflg, errmsg=errmsg)
// CHECK-NEXT:      if (errflg /= 0 .or. index <= 0) then
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:        write(errmsg, '(3a)') 'const_get_index: constituent ', trim(std_name), ' not found'
// CHECK-NEXT:      end if
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
