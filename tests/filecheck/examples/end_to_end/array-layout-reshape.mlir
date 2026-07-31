// Test end-to-end RESHAPE generation for row_major host arrays.
//
// When a host table declares array_layout = row_major, the generated CCPP cap
// must transpose 2D+ arrays from row-major to column-major before forwarding
// them to the suite cap (using Fortran RESHAPE), and write them back after.
// 1D arrays from the same host (e.g. temperature) need no such transpose, but
// (like every horizontal_dimension-dimensioned host array) are still sliced
// by col_start:col_end at the call site -- confirmed necessary by a real
// gfortran-verified numerical bug in examples/var_compat, where the same
// slicing was previously missing entirely under a chunked driver.
//
// RUN: python3 tests/filecheck/examples/array_layout_suite.py | python3 -m xdsl_ccpp.tools.ccpp_opt -p generate-meta-cap,generate-meta-kinds,generate-host-match,generate-arg-ownership,generate-suite-cap,generate-ccpp-cap,generate-cpp-cap,generate-kinds,strip-ccpp -t ftn | python3 -m filecheck %s

// The host cap uses host module variables for theta and temperature.

// CHECK-LABEL: // FILE: tiny_suite_cap.F90
// CHECK-LABEL: module tiny_suite_cap
// CHECK:         use ccpp_kinds
// CHECK-NEXT:    use tiny_scheme, only: tiny_scheme_run
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         character(len=16) :: ccpp_suite_state = 'uninitialized'
// CHECK-NEXT:    character(len=16), parameter :: const_in_time_step = 'in_time_step'
// CHECK-NEXT:    character(len=16), parameter :: const_initialized = 'initialized'
// CHECK-NEXT:    character(len=16), parameter :: const_uninitialized = 'uninitialized'
// CHECK-NEXT:    public :: tiny_suite_suite_register
// CHECK-NEXT:    public :: tiny_suite_suite_initialize
// CHECK-NEXT:    public :: tiny_suite_suite_finalize
// CHECK-NEXT:    public :: tiny_suite_suite_timestep_initial
// CHECK-NEXT:    public :: tiny_suite_suite_timestep_final
// CHECK-NEXT:    public :: tiny_suite_suite_physics
// CHECK:       CONTAINS
// CHECK-LABEL:   subroutine tiny_suite_suite_register(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:    end subroutine tiny_suite_suite_register
// CHECK-LABEL:   subroutine tiny_suite_suite_initialize(errflg, errmsg)
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
// CHECK-NEXT:    end subroutine tiny_suite_suite_initialize
// CHECK-LABEL:   subroutine tiny_suite_suite_finalize(errflg, errmsg)
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
// CHECK-NEXT:    end subroutine tiny_suite_suite_finalize
// CHECK-LABEL:   subroutine tiny_suite_suite_timestep_initial(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in tiny_suite_timestep_initial"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_in_time_step
// CHECK-NEXT:    end subroutine tiny_suite_suite_timestep_initial
// CHECK-LABEL:   subroutine tiny_suite_suite_timestep_final(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_in_time_step .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in tiny_suite_timestep_final"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_initialized
// CHECK-NEXT:    end subroutine tiny_suite_suite_timestep_final
// CHECK-LABEL:   subroutine tiny_suite_suite_physics(col_start, col_end, nz, temp, theta, errmsg, errflg)
// CHECK:           integer, intent(in) :: col_start
// CHECK-NEXT:      integer, intent(in) :: col_end
// CHECK-NEXT:      integer, intent(in) :: nz
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: temp(:)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: theta(:, :)
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
// CHECK-NEXT:          "' in tiny_suite_physics"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call tiny_scheme_run(ncol=ncol, nz=nz, temp=temp, theta=theta, errmsg=errmsg, errflg=errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine tiny_suite_suite_physics
// CHECK-NEXT:  end module tiny_suite_cap
// CHECK:       // -----
// CHECK-LABEL: // FILE: Tiny_ccpp_cap.F90
// CHECK-LABEL: module Tiny_ccpp_cap
// CHECK:         use ccpp_kinds
// CHECK-NEXT:    use tiny_host_mod, only: nz_total
// CHECK-NEXT:    use tiny_host_mod, only: temperature
// CHECK-NEXT:    use tiny_host_mod, only: theta
// CHECK-NEXT:    use tiny_suite_cap, only: tiny_suite_suite_finalize
// CHECK-NEXT:    use tiny_suite_cap, only: tiny_suite_suite_initialize
// CHECK-NEXT:    use tiny_suite_cap, only: tiny_suite_suite_physics
// CHECK-NEXT:    use tiny_suite_cap, only: tiny_suite_suite_register
// CHECK-NEXT:    use tiny_suite_cap, only: tiny_suite_suite_timestep_final
// CHECK-NEXT:    use tiny_suite_cap, only: tiny_suite_suite_timestep_initial
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         character(len=10), parameter :: str_tiny_suite = 'tiny_suite'
// CHECK-NEXT:    character(len=7), parameter :: str_physics = 'physics'
// CHECK-NEXT:    public :: Tiny_ccpp_physics_register
// CHECK-NEXT:    public :: Tiny_ccpp_physics_initialize
// CHECK-NEXT:    public :: Tiny_ccpp_physics_finalize
// CHECK-NEXT:    public :: Tiny_ccpp_physics_timestep_initial
// CHECK-NEXT:    public :: Tiny_ccpp_physics_timestep_final
// CHECK-NEXT:    public :: Tiny_ccpp_physics_run
// CHECK-NEXT:    public :: ccpp_physics_suite_list
// CHECK-NEXT:    public :: ccpp_physics_suite_part_list
// CHECK-NEXT:    public :: ccpp_physics_suite_variables
// CHECK:       CONTAINS
// CHECK-LABEL:   subroutine Tiny_ccpp_physics_register(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'tiny_suite') then
// CHECK-NEXT:        call tiny_suite_suite_register(errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine Tiny_ccpp_physics_register
// CHECK-LABEL:   subroutine Tiny_ccpp_physics_initialize(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'tiny_suite') then
// CHECK-NEXT:        call tiny_suite_suite_initialize(errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine Tiny_ccpp_physics_initialize
// CHECK-LABEL:   subroutine Tiny_ccpp_physics_finalize(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'tiny_suite') then
// CHECK-NEXT:        call tiny_suite_suite_finalize(errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine Tiny_ccpp_physics_finalize
// CHECK-LABEL:   subroutine Tiny_ccpp_physics_timestep_initial(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'tiny_suite') then
// CHECK-NEXT:        call tiny_suite_suite_timestep_initial(errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine Tiny_ccpp_physics_timestep_initial
// CHECK-LABEL:   subroutine Tiny_ccpp_physics_timestep_final(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'tiny_suite') then
// CHECK-NEXT:        call tiny_suite_suite_timestep_final(errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine Tiny_ccpp_physics_timestep_final
// CHECK-LABEL:   subroutine Tiny_ccpp_physics_run(suite_name, suite_part, col_start, col_end, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), intent(in) :: suite_part
// CHECK-NEXT:      integer, intent(in) :: col_start
// CHECK-NEXT:      integer, intent(in) :: col_end
// CHECK-NEXT:      character(len=512), intent(inout) :: errmsg
// CHECK-NEXT:      integer, intent(inout) :: errflg
// CHECK-NEXT:      real(kind=kind_phys), allocatable :: theta_col(:, :)
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'tiny_suite') then
// CHECK-NEXT:        if (trim(suite_part) .eq. 'physics') then
// CHECK-NEXT:          if (allocated(theta_col)) deallocate(theta_col)
// CHECK-NEXT:          allocate(theta_col(col_end - col_start + 1, nz_total))
// CHECK-NEXT:          theta_col = reshape(theta, [col_end - col_start + 1, nz_total], order=[2, 1])
// CHECK-NEXT:          call tiny_suite_suite_physics(col_start, col_end, nz_total,                               &
// CHECK-NEXT:            temperature(col_start:col_end), theta_col, errmsg, errflg)
// CHECK-NEXT:          theta = reshape(theta_col, [nz_total, col_end - col_start + 1], order=[2, 1])
// CHECK-NEXT:          deallocate(theta_col)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg, '(3a)') "No suite part named ", trim(suite_part),                           &
// CHECK-NEXT:            " found in suite tiny_suite"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine Tiny_ccpp_physics_run
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
// CHECK-NEXT:          allocate(var_list(3))
// CHECK-NEXT:          var_list(1) = 'air_potential_temperature           '
// CHECK-NEXT:          var_list(2) = 'air_temperature                     '
// CHECK-NEXT:          var_list(3) = 'vertical_layer_dimension            '
// CHECK-NEXT:        else if (.not. do_input .and. do_output) then
// CHECK-NEXT:          allocate(var_list(4))
// CHECK-NEXT:          var_list(1) = 'air_potential_temperature           '
// CHECK-NEXT:          var_list(2) = 'air_temperature                     '
// CHECK-NEXT:          var_list(3) = 'ccpp_error_code                     '
// CHECK-NEXT:          var_list(4) = 'ccpp_error_message                  '
// CHECK-NEXT:        else
// CHECK-NEXT:          allocate(var_list(5))
// CHECK-NEXT:          var_list(1) = 'air_potential_temperature           '
// CHECK-NEXT:          var_list(2) = 'air_temperature                     '
// CHECK-NEXT:          var_list(3) = 'ccpp_error_code                     '
// CHECK-NEXT:          var_list(4) = 'ccpp_error_message                  '
// CHECK-NEXT:          var_list(5) = 'vertical_layer_dimension            '
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_physics_suite_variables
// CHECK-NEXT:  end module Tiny_ccpp_cap
// CHECK:       // -----
// CHECK-LABEL: // FILE: ccpp_kinds.F90
// CHECK-LABEL: module ccpp_kinds
// CHECK:         use ISO_FORTRAN_ENV, only: kind_phys => REAL64
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         public :: kind_phys
// CHECK-NEXT:  end module ccpp_kinds
