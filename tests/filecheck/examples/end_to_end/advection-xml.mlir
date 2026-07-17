// Test the XML frontend → optimizer → Fortran pipeline for the advection
// example.  Exercises: four distinct schemes in one suite, a scheme that
// appears twice in the suite XML (apply_constituent_tendencies), host/module
// metadata files, and 3-D array arguments.
//
// Note: duplicate scheme entries are deduplicated in the suite cap — only one
// call to apply_constituent_tendencies_run is emitted even though the scheme
// appears twice in the XML.
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/advection/cld_suite.xml --scheme-files examples/advection/const_indices.meta,examples/advection/cld_liq.meta,examples/advection/cld_ice.meta,examples/advection/apply_constituent_tendencies.meta --host-files examples/advection/test_host_data.meta,examples/advection/test_host.meta,examples/advection/test_host_mod.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap,generate-cpp-cap,generate-kinds,strip-ccpp -t ftn | python3 -m filecheck %s

// CHECK-LABEL: // FILE: cld_suite_cap.F90
// CHECK-LABEL: module cld_suite_cap
// CHECK:         use ccpp_kinds
// CHECK-NEXT:    use apply_constituent_tendencies, only: apply_constituent_tendencies_run
// CHECK-NEXT:    use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t
// CHECK-NEXT:    use cld_ice, only: cld_ice_init
// CHECK-NEXT:    use cld_ice, only: cld_ice_register
// CHECK-NEXT:    use cld_ice, only: cld_ice_run
// CHECK-NEXT:    use cld_liq, only: cld_liq_init
// CHECK-NEXT:    use cld_liq, only: cld_liq_register
// CHECK-NEXT:    use cld_liq, only: cld_liq_run
// CHECK-NEXT:    use const_indices, only: const_indices_init
// CHECK-NEXT:    use const_indices, only: const_indices_run
// CHECK-NEXT:    use test_host_data, only: num_consts
// CHECK-NEXT:    use test_host_mod, only: ncols
// CHECK-NEXT:    use test_host_mod, only: pver
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         character(len=16) :: ccpp_suite_state = 'uninitialized'
// CHECK-NEXT:    character(len=16), parameter :: const_in_time_step = 'in_time_step'
// CHECK-NEXT:    character(len=16), parameter :: const_initialized = 'initialized'
// CHECK-NEXT:    character(len=16), parameter :: const_uninitialized = 'uninitialized'
// CHECK-NEXT:    integer :: const_index
// CHECK-NEXT:    integer, allocatable :: const_inds(:)
// CHECK-NEXT:    real(kind=kind_phys), allocatable :: cld_liq_array(:, :)
// CHECK-NEXT:    real(kind=kind_phys) :: tcld
// CHECK-NEXT:    real(kind=kind_phys), allocatable :: cld_ice_array(:, :)
// CHECK-NEXT:    public :: cld_suite_suite_register
// CHECK-NEXT:    public :: cld_suite_suite_initialize
// CHECK-NEXT:    public :: cld_suite_suite_finalize
// CHECK-NEXT:    public :: cld_suite_suite_timestep_initial
// CHECK-NEXT:    public :: cld_suite_suite_timestep_final
// CHECK-NEXT:    public :: cld_suite_suite_physics
// CHECK:       CONTAINS
// CHECK-LABEL:   subroutine cld_suite_suite_register(dyn_const, dyn_const_ice, errmsg, errflg)
// CHECK:           type(ccpp_constituent_properties_t), allocatable, intent(inout) :: dyn_const(:)
// CHECK-NEXT:      type(ccpp_constituent_properties_t), allocatable, intent(inout) :: dyn_const_ice(:)
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.not. allocated(const_inds)) then
// CHECK-NEXT:        allocate(const_inds(num_consts))
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (.not. allocated(cld_liq_array)) then
// CHECK-NEXT:        allocate(cld_liq_array(ncols, pver))
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (.not. allocated(cld_ice_array)) then
// CHECK-NEXT:        allocate(cld_ice_array(ncols, pver))
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call cld_liq_register(dyn_const, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call cld_ice_register(dyn_const_ice, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine cld_suite_suite_register
// CHECK-LABEL:   subroutine cld_suite_suite_initialize(const_std_name, num_consts, test_stdname_array,           &
// CHECK:           const_inds, tfreeze, const_index, errmsg, errflg, tcld)
// CHECK-NEXT:      character(len=512), intent(in) :: const_std_name
// CHECK-NEXT:      integer, intent(in) :: num_consts
// CHECK-NEXT:      character(len=512), target, intent(in) :: test_stdname_array(:)
// CHECK-NEXT:      integer, target, intent(inout) :: const_inds(:)
// CHECK-NEXT:      real(kind=kind_phys), intent(in) :: tfreeze
// CHECK-NEXT:      integer, intent(out) :: const_index
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      real(kind=kind_phys), intent(out) :: tcld
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.not. allocated(cld_liq_array)) then
// CHECK-NEXT:        allocate(cld_liq_array(ncols, pver))
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (.not. allocated(cld_ice_array)) then
// CHECK-NEXT:        allocate(cld_ice_array(ncols, pver))
// CHECK-NEXT:        cld_ice_array = 0.0_kind_phys
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (.not. allocated(const_inds)) then
// CHECK-NEXT:        allocate(const_inds(num_consts))
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (.NOT. (const_uninitialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in cld_suite_initialize"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call const_indices_init(const_std_name, num_consts, test_stdname_array, const_index,        &
// CHECK-NEXT:          const_inds, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call cld_liq_init(tfreeze, cld_liq_array, tcld, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call cld_ice_init(tfreeze, cld_ice_array, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_initialized
// CHECK-NEXT:    end subroutine cld_suite_suite_initialize
// CHECK-LABEL:   subroutine cld_suite_suite_finalize(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in cld_suite_finalize"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_uninitialized
// CHECK-NEXT:    end subroutine cld_suite_suite_finalize
// CHECK-LABEL:   subroutine cld_suite_suite_timestep_initial(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in cld_suite_timestep_initial"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_in_time_step
// CHECK-NEXT:    end subroutine cld_suite_suite_timestep_initial
// CHECK-LABEL:   subroutine cld_suite_suite_timestep_final(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_in_time_step .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in cld_suite_timestep_final"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_initialized
// CHECK-NEXT:    end subroutine cld_suite_suite_timestep_final
// CHECK-LABEL:   subroutine cld_suite_suite_physics(const_std_name, num_consts, test_stdname_array, const_inds,  &
// CHECK:           col_start, col_end, timestep, tcld, temp, qv, ps, cld_liq_tend, const_tend, const,            &
// CHECK-NEXT:      const_index, errmsg, errflg)
// CHECK-NEXT:      character(len=512), intent(in) :: const_std_name
// CHECK-NEXT:      integer, intent(in) :: num_consts
// CHECK-NEXT:      character(len=512), target, intent(in) :: test_stdname_array(:)
// CHECK-NEXT:      integer, target, intent(inout) :: const_inds(:)
// CHECK-NEXT:      integer, intent(in) :: col_start
// CHECK-NEXT:      integer, intent(in) :: col_end
// CHECK-NEXT:      real(kind=kind_phys), intent(in) :: timestep
// CHECK-NEXT:      real(kind=kind_phys), intent(in) :: tcld
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: temp(:, :)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: qv(:, :)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(in) :: ps(:)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: cld_liq_tend(:, :)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: const_tend(:, :, :)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: const(:, :, :)
// CHECK-NEXT:      integer, intent(out) :: const_index
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
// CHECK-NEXT:          "' in cld_suite_physics"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call const_indices_run(const_std_name, num_consts, test_stdname_array, const_index,         &
// CHECK-NEXT:          const_inds, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call cld_liq_run(ncol, timestep, tcld, temp, qv, ps, cld_liq_tend, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call apply_constituent_tendencies_run(const_tend, const, errflg, errmsg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call cld_ice_run(ncol, timestep, temp, qv, ps, cld_ice_array, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call apply_constituent_tendencies_run(const_tend, const, errflg, errmsg)
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine cld_suite_suite_physics
// CHECK-NEXT:  end module cld_suite_cap
// CHECK:       // -----
// CHECK-LABEL: // FILE: Cld_ccpp_cap.F90
// CHECK-LABEL: module Cld_ccpp_cap
// CHECK:         use ccpp_kinds
// CHECK-NEXT:    use ccpp_constituent_prop_mod, only: ccpp_constituent_prop_ptr_t
// CHECK-NEXT:    use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t
// CHECK-NEXT:    use cld_suite_cap, only: cld_suite_suite_finalize
// CHECK-NEXT:    use cld_suite_cap, only: cld_suite_suite_initialize
// CHECK-NEXT:    use cld_suite_cap, only: cld_suite_suite_physics
// CHECK-NEXT:    use cld_suite_cap, only: cld_suite_suite_register
// CHECK-NEXT:    use cld_suite_cap, only: cld_suite_suite_timestep_final
// CHECK-NEXT:    use cld_suite_cap, only: cld_suite_suite_timestep_initial
// CHECK-NEXT:    use test_host_data, only: const_index
// CHECK-NEXT:    use test_host_data, only: const_inds
// CHECK-NEXT:    use test_host_data, only: const_std_name
// CHECK-NEXT:    use test_host_data, only: num_consts
// CHECK-NEXT:    use test_host_data, only: physics_state
// CHECK-NEXT:    use test_host_data, only: std_name_array
// CHECK-NEXT:    use test_host_mod, only: tfreeze
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         character(len=9), parameter :: str_cld_suite = 'cld_suite'
// CHECK-NEXT:    character(len=7), parameter :: str_physics = 'physics'
// CHECK-NEXT:    type(ccpp_constituent_properties_t), allocatable :: lc_dyn_const(:)
// CHECK-NEXT:    type(ccpp_constituent_properties_t), allocatable :: lc_dyn_const_ice(:)
// CHECK-NEXT:    type(ccpp_constituent_properties_t), target, allocatable :: lc_all_constituents(:)
// CHECK-NEXT:    real(kind=kind_phys), target, allocatable :: lc_constituent_array(:, :, :)
// CHECK-NEXT:    real(kind=kind_phys), target, allocatable :: lc_const_tend(:, :, :)
// CHECK-NEXT:    type(ccpp_constituent_prop_ptr_t), target, allocatable :: lc_const_props(:)
// CHECK-NEXT:    real(kind=kind_phys) :: lc_tcld
// CHECK-NEXT:    real(kind=kind_phys), allocatable :: lc_temp(:, :)
// CHECK-NEXT:    real(kind=kind_phys), allocatable :: lc_qv(:, :)
// CHECK-NEXT:    real(kind=kind_phys), allocatable :: lc_ps(:)
// CHECK-NEXT:    real(kind=kind_phys), pointer :: lc_cld_liq_tend(:, :) => null()
// CHECK-NEXT:    public :: Cld_ccpp_physics_register
// CHECK-NEXT:    public :: Cld_ccpp_physics_initialize
// CHECK-NEXT:    public :: Cld_ccpp_physics_finalize
// CHECK-NEXT:    public :: Cld_ccpp_physics_timestep_initial
// CHECK-NEXT:    public :: Cld_ccpp_physics_timestep_final
// CHECK-NEXT:    public :: Cld_ccpp_physics_run
// CHECK-NEXT:    public :: ccpp_physics_suite_list
// CHECK-NEXT:    public :: ccpp_physics_suite_part_list
// CHECK-NEXT:    public :: ccpp_physics_suite_variables
// CHECK-NEXT:    public :: Cld_ccpp_is_scheme_constituent
// CHECK-NEXT:    public :: Cld_ccpp_deallocate_dynamic_constituents
// CHECK-NEXT:    public :: Cld_ccpp_register_constituents
// CHECK-NEXT:    public :: Cld_ccpp_number_constituents
// CHECK-NEXT:    public :: Cld_ccpp_initialize_constituents
// CHECK-NEXT:    public :: Cld_constituents_array
// CHECK-NEXT:    public :: Cld_const_get_index
// CHECK-NEXT:    public :: Cld_model_const_properties
// CHECK:       CONTAINS
// CHECK-LABEL:   subroutine Cld_ccpp_physics_register(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'cld_suite') then
// CHECK-NEXT:        call cld_suite_suite_register(lc_dyn_const, lc_dyn_const_ice, errmsg, errflg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), "found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine Cld_ccpp_physics_register
// CHECK-LABEL:   subroutine Cld_ccpp_physics_initialize(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'cld_suite') then
// CHECK-NEXT:        call cld_suite_suite_initialize(const_std_name, num_consts, std_name_array, const_inds,     &
// CHECK-NEXT:          tfreeze, const_index, errmsg, errflg, lc_tcld)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), "found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine Cld_ccpp_physics_initialize
// CHECK-LABEL:   subroutine Cld_ccpp_physics_finalize(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'cld_suite') then
// CHECK-NEXT:        call cld_suite_suite_finalize(errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), "found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine Cld_ccpp_physics_finalize
// CHECK-LABEL:   subroutine Cld_ccpp_physics_timestep_initial(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'cld_suite') then
// CHECK-NEXT:        call cld_suite_suite_timestep_initial(errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), "found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine Cld_ccpp_physics_timestep_initial
// CHECK-LABEL:   subroutine Cld_ccpp_physics_timestep_final(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'cld_suite') then
// CHECK-NEXT:        call cld_suite_suite_timestep_final(errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), "found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine Cld_ccpp_physics_timestep_final
// CHECK-LABEL:   subroutine Cld_ccpp_physics_run(suite_name, suite_part, const_std_name, num_consts,             &
// CHECK:           test_stdname_array, const_inds, col_start, col_end, timestep, errmsg, errflg)
// CHECK-NEXT:      character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), intent(in) :: suite_part
// CHECK-NEXT:      character(len=512), intent(in) :: const_std_name
// CHECK-NEXT:      integer, intent(in) :: num_consts
// CHECK-NEXT:      character(len=512), target, intent(in) :: test_stdname_array(:)
// CHECK-NEXT:      integer, target, intent(inout) :: const_inds(:)
// CHECK-NEXT:      integer, intent(in) :: col_start
// CHECK-NEXT:      integer, intent(in) :: col_end
// CHECK-NEXT:      real(kind=kind_phys), intent(in) :: timestep
// CHECK-NEXT:      character(len=512), intent(inout) :: errmsg
// CHECK-NEXT:      integer, intent(inout) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'cld_suite') then
// CHECK-NEXT:        if (trim(suite_part) .eq. 'physics') then
// CHECK-NEXT:          call cld_suite_suite_physics(const_std_name, num_consts, test_stdname_array, const_inds,  &
// CHECK-NEXT:            col_start, col_end, timestep, lc_tcld, lc_temp(col_start:col_end, :),                   &
// CHECK-NEXT:            lc_qv(col_start:col_end, :), lc_ps(col_start:col_end),                                  &
// CHECK-NEXT:            lc_cld_liq_tend(col_start:col_end, :), lc_const_tend(col_start:col_end, :, :),          &
// CHECK-NEXT:            lc_constituent_array(col_start:col_end, :, :), const_index, errmsg, errflg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg, '(3a)') "No suite part named ", trim(suite_part), " found in suite cld_suite"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), "found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine Cld_ccpp_physics_run
// CHECK-LABEL:   subroutine ccpp_physics_suite_list(suites)
// CHECK:           character(len=*), allocatable, intent(out) :: suites(:)
// CHECK:           allocate(suites(1))
// CHECK-NEXT:      suites(1) = str_cld_suite
// CHECK-NEXT:    end subroutine ccpp_physics_suite_list
// CHECK-LABEL:   subroutine ccpp_physics_suite_part_list(suite_name, part_list, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), allocatable, intent(out) :: part_list(:)
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'cld_suite') then
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
// CHECK-NEXT:      if (trim(suite_name) .eq. 'cld_suite') then
// CHECK-NEXT:        if (do_input .and. .not. do_output) then
// CHECK-NEXT:          allocate(var_list(13))
// CHECK-NEXT:          var_list(1) = 'banana_array_dim                    '
// CHECK-NEXT:          var_list(2) = 'ccpp_constituent_tendencies         '
// CHECK-NEXT:          var_list(3) = 'ccpp_constituents                   '
// CHECK-NEXT:          var_list(4) = 'cloud_ice_dry_mixing_ratio          '
// CHECK-NEXT:          var_list(5) = 'cloud_liquid_dry_mixing_ratio       '
// CHECK-NEXT:          var_list(6) = 'minimum_temperature_for_cloud_liquid'
// CHECK-NEXT:          var_list(7) = 'number_of_ccpp_constituents         '
// CHECK-NEXT:          var_list(8) = 'surface_air_pressure                '
// CHECK-NEXT:          var_list(9) = 'temperature                         '
// CHECK-NEXT:          var_list(10) = 'tendency_of_cloud_liquid_dry_mixing_ratio'
// CHECK-NEXT:          var_list(11) = 'time_step_for_physics               '
// CHECK-NEXT:          var_list(12) = 'water_temperature_at_freezing       '
// CHECK-NEXT:          var_list(13) = 'water_vapor_specific_humidity       '
// CHECK-NEXT:        else if (.not. do_input .and. do_output) then
// CHECK-NEXT:          allocate(var_list(14))
// CHECK-NEXT:          var_list(1) = 'ccpp_constituent_tendencies         '
// CHECK-NEXT:          var_list(2) = 'ccpp_constituents                   '
// CHECK-NEXT:          var_list(3) = 'ccpp_error_code                     '
// CHECK-NEXT:          var_list(4) = 'ccpp_error_message                  '
// CHECK-NEXT:          var_list(5) = 'cloud_ice_dry_mixing_ratio          '
// CHECK-NEXT:          var_list(6) = 'cloud_liquid_dry_mixing_ratio       '
// CHECK-NEXT:          var_list(7) = 'dynamic_constituents_for_cld_ice    '
// CHECK-NEXT:          var_list(8) = 'dynamic_constituents_for_cld_liq    '
// CHECK-NEXT:          var_list(9) = 'minimum_temperature_for_cloud_liquid'
// CHECK-NEXT:          var_list(10) = 'temperature                         '
// CHECK-NEXT:          var_list(11) = 'tendency_of_cloud_liquid_dry_mixing_ratio'
// CHECK-NEXT:          var_list(12) = 'test_banana_constituent_index       '
// CHECK-NEXT:          var_list(13) = 'test_banana_constituent_indices     '
// CHECK-NEXT:          var_list(14) = 'water_vapor_specific_humidity       '
// CHECK-NEXT:        else
// CHECK-NEXT:          allocate(var_list(19))
// CHECK-NEXT:          var_list(1) = 'banana_array_dim                    '
// CHECK-NEXT:          var_list(2) = 'ccpp_constituent_tendencies         '
// CHECK-NEXT:          var_list(3) = 'ccpp_constituents                   '
// CHECK-NEXT:          var_list(4) = 'ccpp_error_code                     '
// CHECK-NEXT:          var_list(5) = 'ccpp_error_message                  '
// CHECK-NEXT:          var_list(6) = 'cloud_ice_dry_mixing_ratio          '
// CHECK-NEXT:          var_list(7) = 'cloud_liquid_dry_mixing_ratio       '
// CHECK-NEXT:          var_list(8) = 'dynamic_constituents_for_cld_ice    '
// CHECK-NEXT:          var_list(9) = 'dynamic_constituents_for_cld_liq    '
// CHECK-NEXT:          var_list(10) = 'minimum_temperature_for_cloud_liquid'
// CHECK-NEXT:          var_list(11) = 'number_of_ccpp_constituents         '
// CHECK-NEXT:          var_list(12) = 'surface_air_pressure                '
// CHECK-NEXT:          var_list(13) = 'temperature                         '
// CHECK-NEXT:          var_list(14) = 'tendency_of_cloud_liquid_dry_mixing_ratio'
// CHECK-NEXT:          var_list(15) = 'test_banana_constituent_index       '
// CHECK-NEXT:          var_list(16) = 'test_banana_constituent_indices     '
// CHECK-NEXT:          var_list(17) = 'time_step_for_physics               '
// CHECK-NEXT:          var_list(18) = 'water_temperature_at_freezing       '
// CHECK-NEXT:          var_list(19) = 'water_vapor_specific_humidity       '
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_physics_suite_variables
// CHECK-NEXT:      subroutine Cld_ccpp_is_scheme_constituent(std_name, is_const, errflg, errmsg)
// CHECK-NEXT:        character(len=*), intent(in) :: std_name
// CHECK-NEXT:        logical, intent(out) :: is_const
// CHECK-NEXT:        integer, intent(out) :: errflg
// CHECK-NEXT:        character(len=512), intent(out) :: errmsg
// CHECK-NEXT:        integer :: lc_idx
// CHECK-NEXT:        errflg = 0
// CHECK-NEXT:        errmsg = ''
// CHECK-NEXT:        is_const = .false.
// CHECK-NEXT:        select case (trim(std_name))
// CHECK-NEXT:        case ('cloud_liquid_dry_mixing_ratio', 'cloud_ice_dry_mixing_ratio')
// CHECK-NEXT:          is_const = .true.
// CHECK-NEXT:        case default
// CHECK-NEXT:          if (allocated(lc_dyn_const)) then
// CHECK-NEXT:            do lc_idx = 1, size(lc_dyn_const)
// CHECK-NEXT:              if (trim(lc_dyn_const(lc_idx)%std_name) == trim(std_name)) then
// CHECK-NEXT:                is_const = .true.
// CHECK-NEXT:                return
// CHECK-NEXT:              end if
// CHECK-NEXT:            end do
// CHECK-NEXT:          end if
// CHECK-NEXT:          if (allocated(lc_dyn_const_ice)) then
// CHECK-NEXT:            do lc_idx = 1, size(lc_dyn_const_ice)
// CHECK-NEXT:              if (trim(lc_dyn_const_ice(lc_idx)%std_name) == trim(std_name)) then
// CHECK-NEXT:                is_const = .true.
// CHECK-NEXT:                return
// CHECK-NEXT:              end if
// CHECK-NEXT:            end do
// CHECK-NEXT:          end if
// CHECK-NEXT:        end select
// CHECK-NEXT:      end subroutine Cld_ccpp_is_scheme_constituent
// CHECK:           subroutine Cld_ccpp_deallocate_dynamic_constituents()
// CHECK-NEXT:        if (allocated(lc_dyn_const)) deallocate(lc_dyn_const)
// CHECK-NEXT:        if (allocated(lc_dyn_const_ice)) deallocate(lc_dyn_const_ice)
// CHECK-NEXT:        if (allocated(lc_all_constituents)) deallocate(lc_all_constituents)
// CHECK-NEXT:        if (allocated(lc_const_props)) deallocate(lc_const_props)
// CHECK-NEXT:        if (allocated(lc_constituent_array)) deallocate(lc_constituent_array)
// CHECK-NEXT:        if (allocated(lc_const_tend)) deallocate(lc_const_tend)
// CHECK-NEXT:        if (allocated(lc_tcld)) deallocate(lc_tcld)
// CHECK-NEXT:        if (allocated(lc_temp)) deallocate(lc_temp)
// CHECK-NEXT:        if (allocated(lc_qv)) deallocate(lc_qv)
// CHECK-NEXT:        if (allocated(lc_ps)) deallocate(lc_ps)
// CHECK-NEXT:        nullify(lc_cld_liq_tend)
// CHECK-NEXT:      end subroutine Cld_ccpp_deallocate_dynamic_constituents
// CHECK:           subroutine Cld_ccpp_register_constituents(host_constituents, errmsg, errflg)
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
// CHECK-NEXT:        if (allocated(lc_dyn_const)) lc_max = lc_max + size(lc_dyn_const)
// CHECK-NEXT:        if (allocated(lc_dyn_const_ice)) lc_max = lc_max + size(lc_dyn_const_ice)
// CHECK-NEXT:        lc_max = lc_max + 2
// CHECK-NEXT:        lc_max = lc_max + size(host_constituents)
// CHECK-NEXT:        allocate(lc_tmp(lc_max))
// CHECK-NEXT:        lc_num = 0
// CHECK-NEXT:        if (allocated(lc_dyn_const)) then
// CHECK-NEXT:          do lc_i = 1, size(lc_dyn_const)
// CHECK-NEXT:            lc_found = .false.
// CHECK-NEXT:            do lc_j = 1, lc_num
// CHECK-NEXT:              if (trim(lc_tmp(lc_j)%std_name) == trim(lc_dyn_const(lc_i)%std_name)) then
// CHECK-NEXT:                lc_found = .true.
// CHECK-NEXT:                if (trim(lc_tmp(lc_j)%units) /= trim(lc_dyn_const(lc_i)%units)) then
// CHECK-NEXT:                  write(errmsg,                                                                     &
// CHECK-NEXT:      '(3a)') 'ccp_model_const_add_metadata ERROR: Trying to add constituent ',                     &
// CHECK-NEXT:      trim(lc_dyn_const(lc_i)%std_name), &
// CHECK-NEXT:                    ' but an incompatible constituent with this name already exists'
// CHECK-NEXT:                  errflg = 1
// CHECK-NEXT:                  return
// CHECK-NEXT:                end if
// CHECK-NEXT:                exit
// CHECK-NEXT:              end if
// CHECK-NEXT:            end do
// CHECK-NEXT:            if (.not. lc_found) then
// CHECK-NEXT:              lc_num = lc_num + 1
// CHECK-NEXT:              lc_tmp(lc_num) = lc_dyn_const(lc_i)
// CHECK-NEXT:            end if
// CHECK-NEXT:          end do
// CHECK-NEXT:        end if
// CHECK-NEXT:        if (allocated(lc_dyn_const_ice)) then
// CHECK-NEXT:          do lc_i = 1, size(lc_dyn_const_ice)
// CHECK-NEXT:            lc_found = .false.
// CHECK-NEXT:            do lc_j = 1, lc_num
// CHECK-NEXT:              if (trim(lc_tmp(lc_j)%std_name) == trim(lc_dyn_const_ice(lc_i)%std_name)) then
// CHECK-NEXT:                lc_found = .true.
// CHECK-NEXT:                if (trim(lc_tmp(lc_j)%units) /= trim(lc_dyn_const_ice(lc_i)%units)) then
// CHECK-NEXT:                  write(errmsg,                                                                     &
// CHECK-NEXT:      '(3a)') 'ccp_model_const_add_metadata ERROR: Trying to add constituent ',                     &
// CHECK-NEXT:      trim(lc_dyn_const_ice(lc_i)%std_name), &
// CHECK-NEXT:                    ' but an incompatible constituent with this name already exists'
// CHECK-NEXT:                  errflg = 1
// CHECK-NEXT:                  return
// CHECK-NEXT:                end if
// CHECK-NEXT:                exit
// CHECK-NEXT:              end if
// CHECK-NEXT:            end do
// CHECK-NEXT:            if (.not. lc_found) then
// CHECK-NEXT:              lc_num = lc_num + 1
// CHECK-NEXT:              lc_tmp(lc_num) = lc_dyn_const_ice(lc_i)
// CHECK-NEXT:            end if
// CHECK-NEXT:          end do
// CHECK-NEXT:        end if
// CHECK-NEXT:        lc_found = .false.
// CHECK-NEXT:        do lc_j = 1, lc_num
// CHECK-NEXT:          if (trim(lc_tmp(lc_j)%std_name) == 'cloud_liquid_dry_mixing_ratio') then
// CHECK-NEXT:            lc_found = .true.
// CHECK-NEXT:            if (trim(lc_tmp(lc_j)%units) /= 'kg kg-1') then
// CHECK-NEXT:              write(errmsg,                                                                         &
// CHECK-NEXT:      '(3a)') 'ccp_model_const_add_metadata ERROR: Trying to add constituent ',                     &
// CHECK-NEXT:      'cloud_liquid_dry_mixing_ratio', &
// CHECK-NEXT:                ' but an incompatible constituent with this name already exists'
// CHECK-NEXT:              errflg = 1
// CHECK-NEXT:              return
// CHECK-NEXT:            end if
// CHECK-NEXT:            exit
// CHECK-NEXT:          end if
// CHECK-NEXT:        end do
// CHECK-NEXT:        if (.not. lc_found) then
// CHECK-NEXT:          lc_num = lc_num + 1
// CHECK-NEXT:          call lc_tmp(lc_num)%instantiate(std_name='cloud_liquid_dry_mixing_ratio',                 &
// CHECK-NEXT:      long_name='Cloud liquid dry mixing ratio', units='kg kg-1', errcode=errflg, errmsg=errmsg,    &
// CHECK-NEXT:      advected=.true.)
// CHECK-NEXT:          if (errflg /= 0) return
// CHECK-NEXT:        end if
// CHECK-NEXT:        lc_found = .false.
// CHECK-NEXT:        do lc_j = 1, lc_num
// CHECK-NEXT:          if (trim(lc_tmp(lc_j)%std_name) == 'cloud_ice_dry_mixing_ratio') then
// CHECK-NEXT:            lc_found = .true.
// CHECK-NEXT:            if (trim(lc_tmp(lc_j)%units) /= 'kg kg-1') then
// CHECK-NEXT:              write(errmsg,                                                                         &
// CHECK-NEXT:      '(3a)') 'ccp_model_const_add_metadata ERROR: Trying to add constituent ',                     &
// CHECK-NEXT:      'cloud_ice_dry_mixing_ratio', &
// CHECK-NEXT:                ' but an incompatible constituent with this name already exists'
// CHECK-NEXT:              errflg = 1
// CHECK-NEXT:              return
// CHECK-NEXT:            end if
// CHECK-NEXT:            exit
// CHECK-NEXT:          end if
// CHECK-NEXT:        end do
// CHECK-NEXT:        if (.not. lc_found) then
// CHECK-NEXT:          lc_num = lc_num + 1
// CHECK-NEXT:          call lc_tmp(lc_num)%instantiate(std_name='cloud_ice_dry_mixing_ratio',                    &
// CHECK-NEXT:      long_name='Cloud ice dry mixing ratio', units='kg kg-1', errcode=errflg, errmsg=errmsg,       &
// CHECK-NEXT:      advected=.true., default_value=0.0_kind_phys)
// CHECK-NEXT:          if (errflg /= 0) return
// CHECK-NEXT:        end if
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
// CHECK-NEXT:      end subroutine Cld_ccpp_register_constituents
// CHECK:           subroutine Cld_ccpp_number_constituents(num_advected, errmsg, errflg)
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
// CHECK-NEXT:      end subroutine Cld_ccpp_number_constituents
// CHECK:           subroutine Cld_ccpp_initialize_constituents(ncols, pver, errflg, errmsg)
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
// CHECK-NEXT:        if (allocated(lc_tcld)) deallocate(lc_tcld)
// CHECK-NEXT:        allocate(lc_tcld(ncols, pver))
// CHECK-NEXT:        lc_tcld = 0.0_kind_phys
// CHECK-NEXT:        if (allocated(lc_temp)) deallocate(lc_temp)
// CHECK-NEXT:        allocate(lc_temp(ncols, pver))
// CHECK-NEXT:        lc_temp = 0.0_kind_phys
// CHECK-NEXT:        if (allocated(lc_qv)) deallocate(lc_qv)
// CHECK-NEXT:        allocate(lc_qv(ncols, pver))
// CHECK-NEXT:        lc_qv = 0.0_kind_phys
// CHECK-NEXT:        if (allocated(lc_ps)) deallocate(lc_ps)
// CHECK-NEXT:        allocate(lc_ps(ncols))
// CHECK-NEXT:        lc_ps = 0.0_kind_phys
// CHECK-NEXT:        nullify(lc_cld_liq_tend)
// CHECK-NEXT:        do lc_i = 1, lc_num
// CHECK-NEXT:          if (trim(lc_all_constituents(lc_i)%std_name) == 'cloud_liquid_dry_mixing_ratio') then
// CHECK-NEXT:            lc_cld_liq_tend => lc_const_tend(:, :, lc_i)
// CHECK-NEXT:            exit
// CHECK-NEXT:          end if
// CHECK-NEXT:        end do
// CHECK-NEXT:      end subroutine Cld_ccpp_initialize_constituents
// CHECK:           function Cld_constituents_array() result(ptr)
// CHECK-NEXT:        real(kind=kind_phys), pointer :: ptr(:, :, :)
// CHECK-NEXT:        ptr => lc_constituent_array
// CHECK-NEXT:      end function Cld_constituents_array
// CHECK:           subroutine Cld_const_get_index(std_name, index, errflg, errmsg)
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
// CHECK-NEXT:      end subroutine Cld_const_get_index
// CHECK:           function Cld_model_const_properties() result(ptr)
// CHECK-NEXT:        type(ccpp_constituent_prop_ptr_t), pointer :: ptr(:)
// CHECK-NEXT:        ptr => lc_const_props
// CHECK-NEXT:      end function Cld_model_const_properties
// CHECK-NEXT:  end module Cld_ccpp_cap
// CHECK:       // -----
// CHECK-LABEL: // FILE: ccpp_kinds.F90
// CHECK-LABEL: module ccpp_kinds
// CHECK:         use ISO_FORTRAN_ENV, only: kind_phys => REAL64
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         public :: kind_phys
// CHECK-NEXT:  end module ccpp_kinds
