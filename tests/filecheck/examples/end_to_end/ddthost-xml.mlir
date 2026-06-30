// Test the XML frontend → optimizer → Fortran pipeline for the ddthost example.
// Exercises Fortran derived data type (DDT) arguments: vmr_type appears as
// type(vmr_type) in subroutine signatures and scheme calls.
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/ddthost/ddt_suite.xml --scheme-files examples/ddthost/make_ddt.meta,examples/ddthost/environ_conditions.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap,generate-kinds,strip-ccpp -t ftn | python3 -m filecheck %s

// CHECK-LABEL: // FILE: ddt_suite_cap.F90
// CHECK-LABEL: module ddt_suite_cap
// CHECK:         use ccpp_kinds
// CHECK-NEXT:    use environ_conditions, only: environ_conditions_finalize
// CHECK-NEXT:    use environ_conditions, only: environ_conditions_init
// CHECK-NEXT:    use environ_conditions, only: environ_conditions_run
// CHECK-NEXT:    use make_ddt, only: make_ddt_init
// CHECK-NEXT:    use make_ddt, only: make_ddt_run
// CHECK-NEXT:    use make_ddt, only: make_ddt_timestep_final
// CHECK-NEXT:    use make_ddt, only: vmr_type
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         character(len=16) :: ccpp_suite_state = 'uninitialized'
// CHECK-NEXT:    character(len=16), parameter :: const_in_time_step = 'in_time_step'
// CHECK-NEXT:    character(len=16), parameter :: const_initialized = 'initialized'
// CHECK-NEXT:    character(len=16), parameter :: const_uninitialized = 'uninitialized'
// CHECK-NEXT:    type(vmr_type) :: vmr
// CHECK-NEXT:    real(kind=kind_phys), allocatable :: o3(:)
// CHECK-NEXT:    real(kind=kind_phys), allocatable :: hno3(:)
// CHECK-NEXT:    integer :: ntimes
// CHECK-NEXT:    integer, allocatable :: model_times(:)
// CHECK-NEXT:    public :: ddt_suite_suite_register
// CHECK-NEXT:    public :: ddt_suite_suite_initialize
// CHECK-NEXT:    public :: ddt_suite_suite_finalize
// CHECK-NEXT:    public :: ddt_suite_suite_timestep_initial
// CHECK-NEXT:    public :: ddt_suite_suite_timestep_final
// CHECK-NEXT:    public :: ddt_suite_suite_data_prep
// CHECK:       CONTAINS
// CHECK-LABEL:   subroutine ddt_suite_suite_register(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:    end subroutine ddt_suite_suite_register
// CHECK-LABEL:   subroutine ddt_suite_suite_initialize(nbox, ccpp_info, o3, hno3, model_times, vmr, errmsg,      &
// CHECK:           errflg, ntimes)
// CHECK-NEXT:      integer, intent(in) :: nbox
// CHECK-NEXT:      type(ccpp_info_t), intent(in) :: ccpp_info
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: o3(:)
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: hno3(:)
// CHECK-NEXT:      integer, allocatable, intent(inout) :: model_times(:)
// CHECK-NEXT:      type(vmr_type), intent(out) :: vmr
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      integer, intent(out) :: ntimes
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.not. allocated(o3)) then
// CHECK-NEXT:        allocate(o3(nbox))
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (.not. allocated(hno3)) then
// CHECK-NEXT:        allocate(hno3(nbox))
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (.not. allocated(model_times)) then
// CHECK-NEXT:        allocate(model_times(ntimes))
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (.NOT. (const_uninitialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in ddt_suite_initialize"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call make_ddt_init(nbox, ccpp_info, vmr, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call environ_conditions_init(nbox, o3, hno3, ntimes, model_times, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_initialized
// CHECK-NEXT:    end subroutine ddt_suite_suite_initialize
// CHECK-LABEL:   subroutine ddt_suite_suite_finalize(ntimes, model_times, errmsg, errflg)
// CHECK:           integer, intent(in) :: ntimes
// CHECK-NEXT:      integer, intent(in) :: model_times(:)
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in ddt_suite_finalize"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call environ_conditions_finalize(ntimes, model_times, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_uninitialized
// CHECK-NEXT:    end subroutine ddt_suite_suite_finalize
// CHECK-LABEL:   subroutine ddt_suite_suite_timestep_initial(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in ddt_suite_timestep_initial"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_in_time_step
// CHECK-NEXT:    end subroutine ddt_suite_suite_timestep_initial
// CHECK-LABEL:   subroutine ddt_suite_suite_timestep_final(ncols, vmr, errmsg, errflg)
// CHECK:           integer, intent(in) :: ncols
// CHECK-NEXT:      type(vmr_type), intent(in) :: vmr
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_in_time_step .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in ddt_suite_timestep_final"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call make_ddt_timestep_final(ncols, vmr, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_initialized
// CHECK-NEXT:    end subroutine ddt_suite_suite_timestep_final
// CHECK-LABEL:   subroutine ddt_suite_suite_data_prep(cols, cole, O3, HNO3, vmr, psurf, errmsg, errflg)
// CHECK:           integer, intent(in) :: cols
// CHECK-NEXT:      integer, intent(in) :: cole
// CHECK-NEXT:      real(kind=kind_phys), intent(in) :: O3(:)
// CHECK-NEXT:      real(kind=kind_phys), intent(in) :: HNO3(:)
// CHECK-NEXT:      type(vmr_type), intent(inout) :: vmr
// CHECK-NEXT:      real(kind=kind_phys), intent(in) :: psurf(:)
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_in_time_step .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in ddt_suite_data_prep"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call make_ddt_run(cols, cole, O3, HNO3, vmr, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call environ_conditions_run(psurf, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ddt_suite_suite_data_prep
// CHECK-NEXT:  end module ddt_suite_cap
// CHECK:       // -----
// CHECK-LABEL: // FILE: Ddt_ccpp_cap.F90
// CHECK-LABEL: module Ddt_ccpp_cap
// CHECK:         use ccpp_kinds
// CHECK-NEXT:    use ccpp_constituent_prop_mod, only: ccpp_constituent_prop_ptr_t
// CHECK-NEXT:    use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t
// CHECK-NEXT:    use ddt_suite_cap, only: ddt_suite_suite_data_prep
// CHECK-NEXT:    use ddt_suite_cap, only: ddt_suite_suite_finalize
// CHECK-NEXT:    use ddt_suite_cap, only: ddt_suite_suite_initialize
// CHECK-NEXT:    use ddt_suite_cap, only: ddt_suite_suite_register
// CHECK-NEXT:    use ddt_suite_cap, only: ddt_suite_suite_timestep_final
// CHECK-NEXT:    use ddt_suite_cap, only: ddt_suite_suite_timestep_initial
// CHECK-NEXT:    use make_ddt, only: vmr_type
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         character(len=9), parameter :: str_ddt_suite = 'ddt_suite'
// CHECK-NEXT:    character(len=9), parameter :: str_data_prep = 'data_prep'
// CHECK-NEXT:    type(ccpp_constituent_properties_t), target, allocatable :: lc_all_constituents(:)
// CHECK-NEXT:    real(kind=kind_phys), target, allocatable :: lc_constituent_array(:, :, :)
// CHECK-NEXT:    real(kind=kind_phys), target, allocatable :: lc_const_tend(:, :, :)
// CHECK-NEXT:    type(ccpp_constituent_prop_ptr_t), target, allocatable :: lc_const_props(:)
// CHECK-NEXT:    real(kind=kind_phys) :: lc_cols
// CHECK-NEXT:    real(kind=kind_phys) :: lc_cole
// CHECK-NEXT:    real(kind=kind_phys), allocatable :: lc_O3(:)
// CHECK-NEXT:    real(kind=kind_phys), allocatable :: lc_HNO3(:)
// CHECK-NEXT:    real(kind=kind_phys) :: lc_vmr
// CHECK-NEXT:    real(kind=kind_phys), allocatable :: lc_psurf(:)
// CHECK-NEXT:    public :: Ddt_ccpp_physics_register
// CHECK-NEXT:    public :: Ddt_ccpp_physics_initialize
// CHECK-NEXT:    public :: Ddt_ccpp_physics_finalize
// CHECK-NEXT:    public :: Ddt_ccpp_physics_timestep_initial
// CHECK-NEXT:    public :: Ddt_ccpp_physics_timestep_final
// CHECK-NEXT:    public :: Ddt_ccpp_physics_run
// CHECK-NEXT:    public :: ccpp_physics_suite_list
// CHECK-NEXT:    public :: ccpp_physics_suite_part_list
// CHECK-NEXT:    public :: ccpp_physics_suite_variables
// CHECK-NEXT:    public :: Ddt_ccpp_is_scheme_constituent
// CHECK-NEXT:    public :: Ddt_ccpp_deallocate_dynamic_constituents
// CHECK-NEXT:    public :: Ddt_ccpp_register_constituents
// CHECK-NEXT:    public :: Ddt_ccpp_number_constituents
// CHECK-NEXT:    public :: Ddt_ccpp_initialize_constituents
// CHECK-NEXT:    public :: Ddt_constituents_array
// CHECK-NEXT:    public :: Ddt_const_get_index
// CHECK-NEXT:    public :: Ddt_model_const_properties
// CHECK:       CONTAINS
// CHECK-LABEL:   subroutine Ddt_ccpp_physics_register(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'ddt_suite') then
// CHECK-NEXT:        call ddt_suite_suite_register(errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), "found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine Ddt_ccpp_physics_register
// CHECK-LABEL:   subroutine Ddt_ccpp_physics_initialize(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      integer :: lc_nbox
// CHECK-NEXT:      type(ccpp_info_t) :: lc_ccpp_info
// CHECK-NEXT:      real(kind=kind_phys), allocatable :: lc_o3(:)
// CHECK-NEXT:      real(kind=kind_phys), allocatable :: lc_hno3(:)
// CHECK-NEXT:      integer, allocatable :: lc_model_times(:)
// CHECK-NEXT:      integer :: ccpp_tmp_0
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'ddt_suite') then
// CHECK-NEXT:        call ddt_suite_suite_initialize(lc_nbox, lc_ccpp_info, lc_o3, lc_hno3, lc_model_times,      &
// CHECK-NEXT:          lc_vmr, errmsg, errflg, ccpp_tmp_0)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), "found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine Ddt_ccpp_physics_initialize
// CHECK-LABEL:   subroutine Ddt_ccpp_physics_finalize(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      integer :: lc_ntimes
// CHECK-NEXT:      integer, allocatable :: lc_model_times(:)
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'ddt_suite') then
// CHECK-NEXT:        call ddt_suite_suite_finalize(lc_ntimes, lc_model_times, errmsg, errflg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), "found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine Ddt_ccpp_physics_finalize
// CHECK-LABEL:   subroutine Ddt_ccpp_physics_timestep_initial(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'ddt_suite') then
// CHECK-NEXT:        call ddt_suite_suite_timestep_initial(errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), "found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine Ddt_ccpp_physics_timestep_initial
// CHECK-LABEL:   subroutine Ddt_ccpp_physics_timestep_final(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      integer :: lc_ncols
// CHECK-NEXT:      type(vmr_type) :: lc_vmr
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'ddt_suite') then
// CHECK-NEXT:        call ddt_suite_suite_timestep_final(lc_ncols, lc_vmr, errmsg, errflg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), "found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine Ddt_ccpp_physics_timestep_final
// CHECK-LABEL:   subroutine Ddt_ccpp_physics_run(suite_name, suite_part, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), intent(in) :: suite_part
// CHECK-NEXT:      character(len=512), intent(inout) :: errmsg
// CHECK-NEXT:      integer, intent(inout) :: errflg
// CHECK-NEXT:      type(vmr_type) :: ccpp_tmp_0
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'ddt_suite') then
// CHECK-NEXT:        if (trim(suite_part) .eq. 'data_prep') then
// CHECK-NEXT:          call ddt_suite_suite_data_prep(lc_cols, lc_cole, lc_O3(:), lc_HNO3(:), lc_vmr,            &
// CHECK-NEXT:            lc_psurf(:), ccpp_tmp_0, errmsg, errflg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg, '(3a)') "No suite part named ", trim(suite_part), " found in suite ddt_suite"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), "found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine Ddt_ccpp_physics_run
// CHECK-LABEL:   subroutine ccpp_physics_suite_list(suites)
// CHECK:           character(len=*), allocatable, intent(out) :: suites(:)
// CHECK:           allocate(suites(1))
// CHECK-NEXT:      suites(1) = str_ddt_suite
// CHECK-NEXT:    end subroutine ccpp_physics_suite_list
// CHECK-LABEL:   subroutine ccpp_physics_suite_part_list(suite_name, part_list, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), allocatable, intent(out) :: part_list(:)
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'ddt_suite') then
// CHECK-NEXT:        allocate(part_list(1))
// CHECK-NEXT:        part_list(1) = str_data_prep
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
// CHECK-NEXT:      if (trim(suite_name) .eq. 'ddt_suite') then
// CHECK-NEXT:        if (do_input .and. .not. do_output) then
// CHECK-NEXT:          allocate(var_list(10))
// CHECK-NEXT:          var_list(1) = 'horizontal_dimension                '
// CHECK-NEXT:          var_list(2) = 'horizontal_loop_begin               '
// CHECK-NEXT:          var_list(3) = 'horizontal_loop_end                 '
// CHECK-NEXT:          var_list(4) = 'host_standard_ccpp_type             '
// CHECK-NEXT:          var_list(5) = 'model_times                         '
// CHECK-NEXT:          var_list(6) = 'nitric_acid                         '
// CHECK-NEXT:          var_list(7) = 'number_of_model_times               '
// CHECK-NEXT:          var_list(8) = 'ozone                               '
// CHECK-NEXT:          var_list(9) = 'surface_air_pressure                '
// CHECK-NEXT:          var_list(10) = 'volume_mixing_ratio_ddt             '
// CHECK-NEXT:        else if (.not. do_input .and. do_output) then
// CHECK-NEXT:          allocate(var_list(8))
// CHECK-NEXT:          var_list(1) = 'ccpp_error_code                     '
// CHECK-NEXT:          var_list(2) = 'ccpp_error_message                  '
// CHECK-NEXT:          var_list(3) = 'model_times                         '
// CHECK-NEXT:          var_list(4) = 'nitric_acid                         '
// CHECK-NEXT:          var_list(5) = 'number_of_model_times               '
// CHECK-NEXT:          var_list(6) = 'ozone                               '
// CHECK-NEXT:          var_list(7) = 'surface_air_pressure                '
// CHECK-NEXT:          var_list(8) = 'volume_mixing_ratio_ddt             '
// CHECK-NEXT:        else
// CHECK-NEXT:          allocate(var_list(12))
// CHECK-NEXT:          var_list(1) = 'ccpp_error_code                     '
// CHECK-NEXT:          var_list(2) = 'ccpp_error_message                  '
// CHECK-NEXT:          var_list(3) = 'horizontal_dimension                '
// CHECK-NEXT:          var_list(4) = 'horizontal_loop_begin               '
// CHECK-NEXT:          var_list(5) = 'horizontal_loop_end                 '
// CHECK-NEXT:          var_list(6) = 'host_standard_ccpp_type             '
// CHECK-NEXT:          var_list(7) = 'model_times                         '
// CHECK-NEXT:          var_list(8) = 'nitric_acid                         '
// CHECK-NEXT:          var_list(9) = 'number_of_model_times               '
// CHECK-NEXT:          var_list(10) = 'ozone                               '
// CHECK-NEXT:          var_list(11) = 'surface_air_pressure                '
// CHECK-NEXT:          var_list(12) = 'volume_mixing_ratio_ddt             '
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_physics_suite_variables
// CHECK-NEXT:      subroutine Ddt_ccpp_is_scheme_constituent(std_name, is_const, errflg, errmsg)
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
// CHECK-NEXT:      end subroutine Ddt_ccpp_is_scheme_constituent
// CHECK:           subroutine Ddt_ccpp_deallocate_dynamic_constituents()
// CHECK-NEXT:        if (allocated(lc_all_constituents)) deallocate(lc_all_constituents)
// CHECK-NEXT:        if (allocated(lc_const_props)) deallocate(lc_const_props)
// CHECK-NEXT:        if (allocated(lc_constituent_array)) deallocate(lc_constituent_array)
// CHECK-NEXT:        if (allocated(lc_const_tend)) deallocate(lc_const_tend)
// CHECK-NEXT:        if (allocated(lc_cols)) deallocate(lc_cols)
// CHECK-NEXT:        if (allocated(lc_cole)) deallocate(lc_cole)
// CHECK-NEXT:        if (allocated(lc_O3)) deallocate(lc_O3)
// CHECK-NEXT:        if (allocated(lc_HNO3)) deallocate(lc_HNO3)
// CHECK-NEXT:        if (allocated(lc_vmr)) deallocate(lc_vmr)
// CHECK-NEXT:        if (allocated(lc_psurf)) deallocate(lc_psurf)
// CHECK-NEXT:      end subroutine Ddt_ccpp_deallocate_dynamic_constituents
// CHECK:           subroutine Ddt_ccpp_register_constituents(host_constituents, errmsg, errflg)
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
// CHECK-NEXT:      end subroutine Ddt_ccpp_register_constituents
// CHECK:           subroutine Ddt_ccpp_number_constituents(num_advected, errmsg, errflg)
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
// CHECK-NEXT:      end subroutine Ddt_ccpp_number_constituents
// CHECK:           subroutine Ddt_ccpp_initialize_constituents(ncols, pver, errflg, errmsg)
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
// CHECK-NEXT:        if (allocated(lc_cols)) deallocate(lc_cols)
// CHECK-NEXT:        allocate(lc_cols(ncols, pver))
// CHECK-NEXT:        lc_cols = 0.0_kind_phys
// CHECK-NEXT:        if (allocated(lc_cole)) deallocate(lc_cole)
// CHECK-NEXT:        allocate(lc_cole(ncols, pver))
// CHECK-NEXT:        lc_cole = 0.0_kind_phys
// CHECK-NEXT:        if (allocated(lc_O3)) deallocate(lc_O3)
// CHECK-NEXT:        allocate(lc_O3(ncols))
// CHECK-NEXT:        lc_O3 = 0.0_kind_phys
// CHECK-NEXT:        if (allocated(lc_HNO3)) deallocate(lc_HNO3)
// CHECK-NEXT:        allocate(lc_HNO3(ncols))
// CHECK-NEXT:        lc_HNO3 = 0.0_kind_phys
// CHECK-NEXT:        if (allocated(lc_vmr)) deallocate(lc_vmr)
// CHECK-NEXT:        allocate(lc_vmr(ncols, pver))
// CHECK-NEXT:        lc_vmr = 0.0_kind_phys
// CHECK-NEXT:        if (allocated(lc_psurf)) deallocate(lc_psurf)
// CHECK-NEXT:        allocate(lc_psurf(ncols))
// CHECK-NEXT:        lc_psurf = 0.0_kind_phys
// CHECK-NEXT:      end subroutine Ddt_ccpp_initialize_constituents
// CHECK:           function Ddt_constituents_array() result(ptr)
// CHECK-NEXT:        real(kind=kind_phys), pointer :: ptr(:, :, :)
// CHECK-NEXT:        ptr => lc_constituent_array
// CHECK-NEXT:      end function Ddt_constituents_array
// CHECK:           subroutine Ddt_const_get_index(std_name, index, errflg, errmsg)
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
// CHECK-NEXT:      end subroutine Ddt_const_get_index
// CHECK:           function Ddt_model_const_properties() result(ptr)
// CHECK-NEXT:        type(ccpp_constituent_prop_ptr_t), pointer :: ptr(:)
// CHECK-NEXT:        ptr => lc_const_props
// CHECK-NEXT:      end function Ddt_model_const_properties
// CHECK-NEXT:  end module Ddt_ccpp_cap
// CHECK:       // -----
// CHECK-LABEL: // FILE: ccpp_kinds.F90
// CHECK-LABEL: module ccpp_kinds
// CHECK:         use ISO_FORTRAN_ENV, only: kind_phys => REAL64
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         public :: kind_phys
// CHECK-NEXT:  end module ccpp_kinds
