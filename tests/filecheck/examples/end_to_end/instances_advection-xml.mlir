// Test the XML frontend → optimizer → Fortran pipeline for the
// instances_advection example. Exercises: the instance_number/
// number_of_instances multi-instance dispatch pattern combined with host +
// scheme-registered constituents -- the only example in this repo that
// drives constituent_cap.py's multi-instance path, so the only golden
// pinning the actual generated Fortran for the per-instance bundle type
// (test_host_lc_instance_t) and its DdtComponentDeclOp-derived declaration
// lines. Added as part of tdb-002's Stage A completion (2026-09-30).
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/instances_advection/cld_suite.xml --scheme-files examples/instances_advection/cld_liq.meta,examples/instances_advection/apply_constituent_tendencies.meta --host-files examples/instances_advection/data.meta,examples/instances_advection/test_host.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p generate-meta-cap,generate-meta-kinds,generate-host-match,generate-arg-ownership,generate-suite-cap,generate-ccpp-cap,generate-cpp-cap,generate-kinds,strip-ccpp -t ftn | python3 -m filecheck %s

// CHECK-LABEL: // FILE: cld_suite_cap.F90
// CHECK-LABEL: module cld_suite_cap
// CHECK:         use ccpp_kinds
// CHECK-NEXT:    use apply_constituent_tendencies, only: apply_constituent_tendencies_run
// CHECK-NEXT:    use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t
// CHECK-NEXT:    use ccpp_scheme_utils, only: ccpp_constituent_indices
// CHECK-NEXT:    use cld_liq, only: cld_liq_init
// CHECK-NEXT:    use cld_liq, only: cld_liq_register
// CHECK-NEXT:    use cld_liq, only: cld_liq_run
// CHECK-NEXT:    use data, only: ncols
// CHECK-NEXT:    use data, only: pver
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         character(len=16), allocatable, dimension(:) :: ccpp_suite_state
// CHECK-NEXT:    character(len=16), parameter :: const_in_time_step = 'in_time_step'
// CHECK-NEXT:    character(len=16), parameter :: const_initialized = 'initialized'
// CHECK-NEXT:    character(len=16), parameter :: const_uninitialized = 'uninitialized'
// CHECK-NEXT:    real(kind=kind_phys) :: tcld
// CHECK-NEXT:    real(kind=kind_phys), pointer :: cld_liq_array(:, :) => null()
// CHECK-NEXT:    real(kind=kind_phys), allocatable :: cld_liq_tend(:, :)
// CHECK-NEXT:    integer :: lc_const_indices(1) = [1]
// CHECK-NEXT:    public :: cld_suite_register
// CHECK-NEXT:    public :: cld_suite_initialize
// CHECK-NEXT:    public :: cld_suite_finalize
// CHECK-NEXT:    public :: cld_suite_init_physics
// CHECK-NEXT:    public :: cld_suite_physics
// CHECK-NEXT:    public :: cld_suite_timestep_init_physics
// CHECK-NEXT:    public :: cld_suite_timestep_final_physics
// CHECK-NEXT:    public :: cld_suite_final_physics
// CHECK:       CONTAINS
// CHECK-LABEL:   subroutine cld_suite_register(dyn_const, instance, ninstances, errmsg, errcode)
// CHECK:           type(ccpp_constituent_properties_t), allocatable, intent(inout) :: dyn_const(:)
// CHECK-NEXT:      integer, intent(in) :: instance
// CHECK-NEXT:      integer, intent(in) :: ninstances
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errcode
// CHECK:           errcode = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (errcode .eq. 0) then
// CHECK-NEXT:        call cld_liq_register(dyn_const=dyn_const, errmsg=errmsg, errcode=errcode)
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine cld_suite_register
// CHECK-LABEL:   subroutine cld_suite_initialize(instance, ninstances, errflg, errmsg)
// CHECK:           integer, intent(in) :: instance
// CHECK-NEXT:      integer, intent(in) :: ninstances
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.not. allocated(cld_liq_tend)) then
// CHECK-NEXT:        allocate(cld_liq_tend(ncols, pver))
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (.not. allocated(ccpp_suite_state)) then
// CHECK-NEXT:        allocate(ccpp_suite_state(ninstances))
// CHECK-NEXT:        ccpp_suite_state = 'uninitialized'
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (.NOT. (const_uninitialized .eq. ccpp_suite_state(instance))) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state(instance)),    &
// CHECK-NEXT:          "' in cld_suite_initialize"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state(instance) = const_initialized
// CHECK-NEXT:    end subroutine cld_suite_initialize
// CHECK-LABEL:   subroutine cld_suite_finalize(instance, ninstances, errflg, errmsg)
// CHECK:           integer, intent(in) :: instance
// CHECK-NEXT:      integer, intent(in) :: ninstances
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.not. allocated(ccpp_suite_state)) then
// CHECK-NEXT:        allocate(ccpp_suite_state(ninstances))
// CHECK-NEXT:        ccpp_suite_state = 'uninitialized'
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state(instance))) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state(instance)),    &
// CHECK-NEXT:          "' in cld_suite_finalize"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state(instance) = const_uninitialized
// CHECK-NEXT:    end subroutine cld_suite_finalize
// CHECK-LABEL:   subroutine cld_suite_init_physics(tfreeze, instance, ninstances, errmsg, errcode)
// CHECK:           real(kind=kind_phys), intent(in) :: tfreeze
// CHECK-NEXT:      integer, intent(in) :: instance
// CHECK-NEXT:      integer, intent(in) :: ninstances
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errcode
// CHECK:           call ccpp_constituent_indices( &
// CHECK-NEXT:          [character(len=29) :: "cloud_liquid_dry_mixing_ratio"], &
// CHECK-NEXT:          lc_const_indices, errcode, errmsg)
// CHECK-NEXT:      if (errcode /= 0) return
// CHECK-NEXT:      errcode = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.not. allocated(cld_liq_tend)) then
// CHECK-NEXT:        allocate(cld_liq_tend(ncols, pver))
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (.not. allocated(ccpp_suite_state)) then
// CHECK-NEXT:        allocate(ccpp_suite_state(ninstances))
// CHECK-NEXT:        ccpp_suite_state = 'uninitialized'
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state(instance))) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state(instance)),    &
// CHECK-NEXT:          "' in cld_suite_init_physics"
// CHECK-NEXT:        errcode = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errcode .eq. 0) then
// CHECK-NEXT:        call cld_liq_init(tfreeze=tfreeze, tcld=tcld, errmsg=errmsg, errcode=errcode)
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine cld_suite_init_physics
// CHECK-LABEL:   subroutine cld_suite_physics(ncol, timestep, temp, qv, ps, cld_liq_tend, const_tend, const,     &
// CHECK:           instance, ninstances, errmsg, errcode)
// CHECK-NEXT:      integer, intent(in) :: ncol
// CHECK-NEXT:      real(kind=kind_phys), intent(in) :: timestep
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: temp(:, :)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: qv(:, :)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(in) :: ps(:)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: cld_liq_tend(:, :)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: const_tend(:, :, :)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: const(:, :, :)
// CHECK-NEXT:      integer, intent(in) :: instance
// CHECK-NEXT:      integer, intent(in) :: ninstances
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errcode
// CHECK:           errcode = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.not. allocated(ccpp_suite_state)) then
// CHECK-NEXT:        allocate(ccpp_suite_state(ninstances))
// CHECK-NEXT:        ccpp_suite_state = 'uninitialized'
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (.NOT. (const_in_time_step .eq. ccpp_suite_state(instance))) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state(instance)),    &
// CHECK-NEXT:          "' in cld_suite_physics"
// CHECK-NEXT:        errcode = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      cld_liq_array => const(:, :, lc_const_indices(1))
// CHECK-NEXT:      if (errcode .eq. 0) then
// CHECK-NEXT:        call cld_liq_run(ncol=ncol, timestep=timestep, tcld=tcld, temp=temp, qv=qv, ps=ps,          &
// CHECK-NEXT:          cld_liq_array=cld_liq_array, cld_liq_tend=cld_liq_tend, errmsg=errmsg, errcode=errcode)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errcode .eq. 0) then
// CHECK-NEXT:        call apply_constituent_tendencies_run(const_tend=const_tend, const=const, errcode=errcode,  &
// CHECK-NEXT:          errmsg=errmsg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      nullify(cld_liq_array)
// CHECK-NEXT:    end subroutine cld_suite_physics
// CHECK-LABEL:   subroutine cld_suite_timestep_init_physics(instance, ninstances, errflg, errmsg)
// CHECK:           integer, intent(in) :: instance
// CHECK-NEXT:      integer, intent(in) :: ninstances
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           call ccpp_constituent_indices( &
// CHECK-NEXT:          [character(len=29) :: "cloud_liquid_dry_mixing_ratio"], &
// CHECK-NEXT:          lc_const_indices, errflg, errmsg)
// CHECK-NEXT:      if (errflg /= 0) return
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.not. allocated(ccpp_suite_state)) then
// CHECK-NEXT:        allocate(ccpp_suite_state(ninstances))
// CHECK-NEXT:        ccpp_suite_state = 'uninitialized'
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state(instance) = const_in_time_step
// CHECK-NEXT:    end subroutine cld_suite_timestep_init_physics
// CHECK-LABEL:   subroutine cld_suite_timestep_final_physics(instance, ninstances, errflg, errmsg)
// CHECK:           integer, intent(in) :: instance
// CHECK-NEXT:      integer, intent(in) :: ninstances
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.not. allocated(ccpp_suite_state)) then
// CHECK-NEXT:        allocate(ccpp_suite_state(ninstances))
// CHECK-NEXT:        ccpp_suite_state = 'uninitialized'
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state(instance) = const_initialized
// CHECK-NEXT:    end subroutine cld_suite_timestep_final_physics
// CHECK-LABEL:   subroutine cld_suite_final_physics(instance, ninstances, errflg, errmsg)
// CHECK:           integer, intent(in) :: instance
// CHECK-NEXT:      integer, intent(in) :: ninstances
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.not. allocated(ccpp_suite_state)) then
// CHECK-NEXT:        allocate(ccpp_suite_state(ninstances))
// CHECK-NEXT:        ccpp_suite_state = 'uninitialized'
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state(instance))) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state(instance)),    &
// CHECK-NEXT:          "' in cld_suite_final_physics"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine cld_suite_final_physics
// CHECK-NEXT:  end module cld_suite_cap
// CHECK:       // -----
// CHECK-LABEL: // FILE: Cld_ccpp_cap.F90
// CHECK-LABEL: module Cld_ccpp_cap
// CHECK:         use ccpp_kinds
// CHECK-NEXT:    use ccpp_constituent_prop_mod, only: ccpp_constituent_prop_ptr_t
// CHECK-NEXT:    use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t
// CHECK-NEXT:    use ccpp_constituent_prop_mod, only: ccpp_model_constituents_t
// CHECK-NEXT:    use cld_suite_cap, only: cld_suite_final_physics
// CHECK-NEXT:    use cld_suite_cap, only: cld_suite_finalize
// CHECK-NEXT:    use cld_suite_cap, only: cld_suite_init_physics
// CHECK-NEXT:    use cld_suite_cap, only: cld_suite_initialize
// CHECK-NEXT:    use cld_suite_cap, only: cld_suite_physics
// CHECK-NEXT:    use cld_suite_cap, only: cld_suite_register
// CHECK-NEXT:    use cld_suite_cap, only: cld_suite_timestep_final_physics
// CHECK-NEXT:    use cld_suite_cap, only: cld_suite_timestep_init_physics
// CHECK-NEXT:    use data, only: dt
// CHECK-NEXT:    use data, only: index_qv
// CHECK-NEXT:    use data, only: ncols
// CHECK-NEXT:    use data, only: phys_state
// CHECK-NEXT:    use data, only: physics_state
// CHECK-NEXT:    use data, only: pver
// CHECK-NEXT:    use data, only: tfreeze
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         character(len=9), parameter :: str_cld_suite = 'cld_suite'
// CHECK-NEXT:    character(len=7), parameter :: str_physics = 'physics'
// CHECK-NEXT:    type :: Cld_lc_instance_t
// CHECK-NEXT:      type(ccpp_model_constituents_t) :: cam_constituents_obj
// CHECK-NEXT:      type(ccpp_constituent_properties_t), allocatable :: lc_dyn_const(:)
// CHECK-NEXT:      integer, allocatable :: lc_all_constituents(:)
// CHECK-NEXT:      real(kind=kind_phys), pointer :: lc_constituent_array(:, :, :) => null()
// CHECK-NEXT:      real(kind=kind_phys), allocatable :: lc_const_tend(:, :, :)
// CHECK-NEXT:      type(ccpp_constituent_prop_ptr_t), allocatable :: lc_const_props(:)
// CHECK-NEXT:      real(kind=kind_phys), pointer :: lc_cld_liq_tend(:, :) => null()
// CHECK-NEXT:      character(len=29) :: cam_model_const_stdnames(1) = [ character(len=29) :: 'cloud_liquid_dry_mixing_ratio' ]
// CHECK-NEXT:      integer :: cam_model_const_indices(1) = -1
// CHECK-NEXT:    end type Cld_lc_instance_t
// CHECK-NEXT:    type(Cld_lc_instance_t), target, allocatable :: lc_instances(:)
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
// CHECK-NEXT:    public :: Cld_ccpp_is_scheme_constituent
// CHECK-NEXT:    public :: Cld_ccpp_deallocate_dynamic_constituents
// CHECK-NEXT:    public :: Cld_ccpp_register_constituents
// CHECK-NEXT:    public :: Cld_ccpp_number_constituents
// CHECK-NEXT:    public :: Cld_ccpp_initialize_constituents
// CHECK-NEXT:    public :: Cld_constituents_array
// CHECK-NEXT:    public :: Cld_advected_constituents_array
// CHECK-NEXT:    public :: Cld_const_get_index
// CHECK-NEXT:    public :: Cld_model_const_properties
// CHECK:       CONTAINS
// CHECK-LABEL:   subroutine ccpp_register(suite_name, instance, ninstances, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      integer, intent(in) :: instance
// CHECK-NEXT:      integer, intent(in) :: ninstances
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           if (.not. allocated(lc_instances)) then
// CHECK-NEXT:        allocate(lc_instances(ninstances))
// CHECK-NEXT:      end if
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'cld_suite') then
// CHECK-NEXT:        call cld_suite_register(lc_instances(instance)%lc_dyn_const, instance, ninstances, errmsg,  &
// CHECK-NEXT:          errflg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_register
// CHECK-LABEL:   subroutine ccpp_init(suite_name, instance, ninstances, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      integer, intent(in) :: instance
// CHECK-NEXT:      integer, intent(in) :: ninstances
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'cld_suite') then
// CHECK-NEXT:        call cld_suite_initialize(instance, ninstances, errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_init
// CHECK-LABEL:   subroutine ccpp_final(suite_name, instance, ninstances, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      integer, intent(in) :: instance
// CHECK-NEXT:      integer, intent(in) :: ninstances
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'cld_suite') then
// CHECK-NEXT:        call cld_suite_finalize(instance, ninstances, errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_final
// CHECK-LABEL:   subroutine ccpp_physics_run(suite_name, suite_part, lb, ub, instance, ninstances, errmsg,       &
// CHECK:           errflg)
// CHECK-NEXT:      character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), intent(in) :: suite_part
// CHECK-NEXT:      integer, intent(in) :: lb
// CHECK-NEXT:      integer, intent(in) :: ub
// CHECK-NEXT:      integer, intent(in) :: instance
// CHECK-NEXT:      integer, intent(in) :: ninstances
// CHECK-NEXT:      character(len=512), intent(inout) :: errmsg
// CHECK-NEXT:      integer, intent(inout) :: errflg
// CHECK-NEXT:      integer :: ncol
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'cld_suite') then
// CHECK-NEXT:        ncol = ub - lb + 1
// CHECK-NEXT:        if (trim(suite_part) .eq. 'physics') then
// CHECK-NEXT:          call cld_suite_physics(ncol, dt, phys_state(instance)%temp(lb:ub, 1:pver),                &
// CHECK-NEXT:            phys_state(instance)%q(:, :, index_qv), phys_state(instance)%ps(lb:ub),                 &
// CHECK-NEXT:            lc_instances(instance)%lc_cld_liq_tend(lb:ub, 1:pver),                                  &
// CHECK-NEXT:            lc_instances(instance)%lc_const_tend, lc_instances(instance)%lc_constituent_array,      &
// CHECK-NEXT:            instance, ninstances, errmsg, errflg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg, '(3a)') "No suite part named ", trim(suite_part), " found in suite cld_suite"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_physics_run
// CHECK-LABEL:   subroutine ccpp_physics_timestep_init(suite_name, suite_part, lb, ub, instance, ninstances,     &
// CHECK:           errmsg, errflg)
// CHECK-NEXT:      character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), intent(in) :: suite_part
// CHECK-NEXT:      integer, intent(in) :: lb
// CHECK-NEXT:      integer, intent(in) :: ub
// CHECK-NEXT:      integer, intent(in) :: instance
// CHECK-NEXT:      integer, intent(in) :: ninstances
// CHECK-NEXT:      character(len=512), intent(inout) :: errmsg
// CHECK-NEXT:      integer, intent(inout) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'cld_suite') then
// CHECK-NEXT:        if (trim(suite_part) .eq. 'physics') then
// CHECK-NEXT:          call cld_suite_timestep_init_physics(instance, ninstances, errflg, errmsg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg, '(3a)') "No suite part named ", trim(suite_part), " found in suite cld_suite"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_physics_timestep_init
// CHECK-LABEL:   subroutine ccpp_physics_timestep_final(suite_name, suite_part, lb, ub, instance, ninstances,    &
// CHECK:           errmsg, errflg)
// CHECK-NEXT:      character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), intent(in) :: suite_part
// CHECK-NEXT:      integer, intent(in) :: lb
// CHECK-NEXT:      integer, intent(in) :: ub
// CHECK-NEXT:      integer, intent(in) :: instance
// CHECK-NEXT:      integer, intent(in) :: ninstances
// CHECK-NEXT:      character(len=512), intent(inout) :: errmsg
// CHECK-NEXT:      integer, intent(inout) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'cld_suite') then
// CHECK-NEXT:        if (trim(suite_part) .eq. 'physics') then
// CHECK-NEXT:          call cld_suite_timestep_final_physics(instance, ninstances, errflg, errmsg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg, '(3a)') "No suite part named ", trim(suite_part), " found in suite cld_suite"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_physics_timestep_final
// CHECK-LABEL:   subroutine ccpp_physics_init(suite_name, suite_part, lb, ub, instance, ninstances, errmsg,      &
// CHECK:           errflg)
// CHECK-NEXT:      character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), intent(in) :: suite_part
// CHECK-NEXT:      integer, intent(in) :: lb
// CHECK-NEXT:      integer, intent(in) :: ub
// CHECK-NEXT:      integer, intent(in) :: instance
// CHECK-NEXT:      integer, intent(in) :: ninstances
// CHECK-NEXT:      character(len=512), intent(inout) :: errmsg
// CHECK-NEXT:      integer, intent(inout) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'cld_suite') then
// CHECK-NEXT:        if (trim(suite_part) .eq. 'physics') then
// CHECK-NEXT:          call cld_suite_init_physics(tfreeze, instance, ninstances, errmsg, errflg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg, '(3a)') "No suite part named ", trim(suite_part), " found in suite cld_suite"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_physics_init
// CHECK-LABEL:   subroutine ccpp_physics_final(suite_name, suite_part, lb, ub, instance, ninstances, errmsg,     &
// CHECK:           errflg)
// CHECK-NEXT:      character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), intent(in) :: suite_part
// CHECK-NEXT:      integer, intent(in) :: lb
// CHECK-NEXT:      integer, intent(in) :: ub
// CHECK-NEXT:      integer, intent(in) :: instance
// CHECK-NEXT:      integer, intent(in) :: ninstances
// CHECK-NEXT:      character(len=512), intent(inout) :: errmsg
// CHECK-NEXT:      integer, intent(inout) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'cld_suite') then
// CHECK-NEXT:        if (trim(suite_part) .eq. 'physics') then
// CHECK-NEXT:          call cld_suite_final_physics(instance, ninstances, errflg, errmsg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg, '(3a)') "No suite part named ", trim(suite_part), " found in suite cld_suite"
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
// CHECK-NEXT:          allocate(var_list(7))
// CHECK-NEXT:          var_list(1) = 'ccpp_constituent_tendencies         '
// CHECK-NEXT:          var_list(2) = 'ccpp_constituents                   '
// CHECK-NEXT:          var_list(3) = 'cloud_liquid_dry_mixing_ratio       '
// CHECK-NEXT:          var_list(4) = 'number_of_ccpp_constituents         '
// CHECK-NEXT:          var_list(5) = 'surface_air_pressure                '
// CHECK-NEXT:          var_list(6) = 'temperature                         '
// CHECK-NEXT:          var_list(7) = 'water_vapor_specific_humidity       '
// CHECK-NEXT:        else if (.not. do_input .and. do_output) then
// CHECK-NEXT:          allocate(var_list(9))
// CHECK-NEXT:          var_list(1) = 'ccpp_constituent_tendencies         '
// CHECK-NEXT:          var_list(2) = 'ccpp_constituents                   '
// CHECK-NEXT:          var_list(3) = 'ccpp_error_code                     '
// CHECK-NEXT:          var_list(4) = 'ccpp_error_message                  '
// CHECK-NEXT:          var_list(5) = 'cloud_liquid_dry_mixing_ratio       '
// CHECK-NEXT:          var_list(6) = 'dynamic_constituents_for_cld_liq    '
// CHECK-NEXT:          var_list(7) = 'temperature                         '
// CHECK-NEXT:          var_list(8) = 'tendency_of_cloud_liquid_dry_mixing_ratio'
// CHECK-NEXT:          var_list(9) = 'water_vapor_specific_humidity       '
// CHECK-NEXT:        else
// CHECK-NEXT:          allocate(var_list(11))
// CHECK-NEXT:          var_list(1) = 'ccpp_constituent_tendencies         '
// CHECK-NEXT:          var_list(2) = 'ccpp_constituents                   '
// CHECK-NEXT:          var_list(3) = 'ccpp_error_code                     '
// CHECK-NEXT:          var_list(4) = 'ccpp_error_message                  '
// CHECK-NEXT:          var_list(5) = 'cloud_liquid_dry_mixing_ratio       '
// CHECK-NEXT:          var_list(6) = 'dynamic_constituents_for_cld_liq    '
// CHECK-NEXT:          var_list(7) = 'number_of_ccpp_constituents         '
// CHECK-NEXT:          var_list(8) = 'surface_air_pressure                '
// CHECK-NEXT:          var_list(9) = 'temperature                         '
// CHECK-NEXT:          var_list(10) = 'tendency_of_cloud_liquid_dry_mixing_ratio'
// CHECK-NEXT:          var_list(11) = 'water_vapor_specific_humidity       '
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_physics_suite_variables
// CHECK-LABEL:   subroutine Cld_ccpp_is_scheme_constituent(std_name, is_const, errflg, errmsg, instance)
// CHECK:           character(len=*), intent(in) :: std_name
// CHECK-NEXT:      logical, intent(out) :: is_const
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(in) :: instance
// CHECK-NEXT:      integer :: lc_idx
// CHECK-NEXT:      character(len=256) :: lc_std_name
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      is_const = .false.
// CHECK-NEXT:      if (allocated(lc_instances)) then
// CHECK-NEXT:        if (any(lc_instances(instance)%cam_model_const_stdnames .eq. std_name)) then
// CHECK-NEXT:          is_const = .true.
// CHECK-NEXT:          return
// CHECK-NEXT:        end if
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (allocated(lc_instances)) then
// CHECK-NEXT:        if (allocated(lc_instances(instance)%lc_dyn_const)) then
// CHECK-NEXT:          do lc_idx = 1, size(lc_instances(instance)%lc_dyn_const)
// CHECK-NEXT:            call lc_instances(instance)%lc_dyn_const(lc_idx)%standard_name(lc_std_name)
// CHECK-NEXT:            if (trim(lc_std_name) .eq. trim(std_name)) then
// CHECK-NEXT:              is_const = .true.
// CHECK-NEXT:              return
// CHECK-NEXT:            end if
// CHECK-NEXT:          end do
// CHECK-NEXT:        end if
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine Cld_ccpp_is_scheme_constituent
// CHECK-LABEL:   subroutine Cld_ccpp_deallocate_dynamic_constituents(instance)
// CHECK:           integer, intent(in) :: instance
// CHECK-NEXT:      if (.not. allocated(lc_instances)) return
// CHECK-NEXT:      if (allocated(lc_instances(instance)%lc_dyn_const)) deallocate(lc_instances(instance)%lc_dyn_const)
// CHECK-NEXT:      if (allocated(lc_instances(instance)%lc_all_constituents)) deallocate(lc_instances(instance)%lc_all_constituents)
// CHECK-NEXT:      if (allocated(lc_instances(instance)%lc_const_props)) deallocate(lc_instances(instance)%lc_const_props)
// CHECK-NEXT:      if (associated(lc_instances(instance)%lc_constituent_array)) nullify(lc_instances(instance)%lc_constituent_array)
// CHECK-NEXT:      if (allocated(lc_instances(instance)%lc_const_tend)) deallocate(lc_instances(instance)%lc_const_tend)
// CHECK-NEXT:      nullify(lc_instances(instance)%lc_cld_liq_tend)
// CHECK-NEXT:      call lc_instances(instance)%cam_constituents_obj%reset()
// CHECK-NEXT:    end subroutine Cld_ccpp_deallocate_dynamic_constituents
// CHECK-LABEL:   subroutine Cld_ccpp_register_constituents(host_constituents, errmsg, errcode, instance,         &
// CHECK:           ninstances)
// CHECK-NEXT:      use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t, ccpp_constituent_prop_ptr_t
// CHECK-NEXT:      use ccpp_scheme_utils, only: ccpp_scheme_utils_set_constituents
// CHECK-NEXT:      type(ccpp_constituent_properties_t), target, intent(in) :: host_constituents(:)
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errcode
// CHECK-NEXT:      integer, intent(in) :: instance
// CHECK-NEXT:      integer, intent(in) :: ninstances
// CHECK-NEXT:      integer :: lc_i, lc_num_consts, field_ind
// CHECK-NEXT:      type(ccpp_constituent_properties_t), pointer :: const_prop
// CHECK-NEXT:      type(ccpp_constituent_prop_ptr_t), pointer :: lc_props_ptr(:)
// CHECK-NEXT:      errcode = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (allocated(lc_instances))) then
// CHECK-NEXT:        allocate(lc_instances(ninstances))
// CHECK-NEXT:      end if
// CHECK-NEXT:      lc_num_consts = size(host_constituents)
// CHECK-NEXT:      if (allocated(lc_instances(instance)%lc_dyn_const)) lc_num_consts = lc_num_consts + size(lc_instances(instance)%lc_dyn_const)
// CHECK-NEXT:      lc_num_consts = lc_num_consts + 1
// CHECK-NEXT:      call lc_instances(instance)%cam_constituents_obj%initialize_table(lc_num_consts)
// CHECK-NEXT:      do lc_i = 1, size(host_constituents)
// CHECK-NEXT:        allocate(const_prop, stat=errcode)
// CHECK-NEXT:        if (errcode .ne. 0) then
// CHECK-NEXT:          errmsg = 'ERROR allocating const_prop'
// CHECK-NEXT:          return
// CHECK-NEXT:        end if
// CHECK-NEXT:        const_prop = host_constituents(lc_i)
// CHECK-NEXT:        call lc_instances(instance)%cam_constituents_obj%new_field(const_prop, errcode=errcode,     &
// CHECK-NEXT:          errmsg=errmsg)
// CHECK-NEXT:        nullify(const_prop)
// CHECK-NEXT:        if (errcode /= 0) return
// CHECK-NEXT:      end do
// CHECK-NEXT:      if (allocated(lc_instances(instance)%lc_dyn_const)) then
// CHECK-NEXT:        do lc_i = 1, size(lc_instances(instance)%lc_dyn_const)
// CHECK-NEXT:          allocate(const_prop, stat=errcode)
// CHECK-NEXT:          if (errcode .ne. 0) then
// CHECK-NEXT:            errmsg = 'ERROR allocating const_prop'
// CHECK-NEXT:            return
// CHECK-NEXT:          end if
// CHECK-NEXT:          const_prop = lc_instances(instance)%lc_dyn_const(lc_i)
// CHECK-NEXT:          call lc_instances(instance)%cam_constituents_obj%new_field(const_prop, errcode=errcode,   &
// CHECK-NEXT:            errmsg=errmsg)
// CHECK-NEXT:          nullify(const_prop)
// CHECK-NEXT:          if (errcode /= 0) return
// CHECK-NEXT:        end do
// CHECK-NEXT:      end if
// CHECK-NEXT:      allocate(const_prop, stat=errcode)
// CHECK-NEXT:      if (errcode .ne. 0) then
// CHECK-NEXT:        errmsg = 'ERROR allocating const_prop'
// CHECK-NEXT:        return
// CHECK-NEXT:      end if
// CHECK-NEXT:      call const_prop%instantiate(std_name='cloud_liquid_dry_mixing_ratio',                         &
// CHECK-NEXT:        long_name='Cloud liquid dry mixing ratio', diag_name='cld_liq_array', units='kg kg-1',      &
// CHECK-NEXT:        vertical_dim='vertical_layer_dimension', advected=.true., errcode=errcode, errmsg=errmsg)
// CHECK-NEXT:      if (errcode /= 0) return
// CHECK-NEXT:      call lc_instances(instance)%cam_constituents_obj%new_field(const_prop, errcode=errcode,       &
// CHECK-NEXT:        errmsg=errmsg)
// CHECK-NEXT:      nullify(const_prop)
// CHECK-NEXT:      if (errcode /= 0) return
// CHECK-NEXT:      call lc_instances(instance)%cam_constituents_obj%lock_table(errcode=errcode, errmsg=errmsg)
// CHECK-NEXT:      if (errcode /= 0) return
// CHECK-NEXT:      lc_props_ptr => lc_instances(instance)%cam_constituents_obj%constituent_props_ptr()
// CHECK-NEXT:      if (allocated(lc_instances(instance)%lc_const_props)) deallocate(lc_instances(instance)%lc_const_props)
// CHECK-NEXT:      allocate(lc_instances(instance)%lc_const_props(size(lc_props_ptr)))
// CHECK-NEXT:      lc_instances(instance)%lc_const_props = lc_props_ptr
// CHECK-NEXT:      nullify(lc_props_ptr)
// CHECK-NEXT:      call ccpp_scheme_utils_set_constituents(lc_instances(instance)%lc_const_props)
// CHECK-NEXT:      call lc_instances(instance)%cam_constituents_obj%num_constituents(lc_num_consts,              &
// CHECK-NEXT:        errcode=errcode, errmsg=errmsg)
// CHECK-NEXT:      if (errcode /= 0) return
// CHECK-NEXT:      if (allocated(lc_instances(instance)%lc_all_constituents)) deallocate(lc_instances(instance)%lc_all_constituents)
// CHECK-NEXT:      allocate(lc_instances(instance)%lc_all_constituents(lc_num_consts))
// CHECK-NEXT:      do lc_i = 1, size(lc_instances(instance)%cam_model_const_indices)
// CHECK-NEXT:        call lc_instances(instance)%cam_constituents_obj%const_index(field_ind,                     &
// CHECK-NEXT:          lc_instances(instance)%cam_model_const_stdnames(lc_i), errcode=errcode, errmsg=errmsg)
// CHECK-NEXT:        if (errcode /= 0) return
// CHECK-NEXT:        if (field_ind .gt. 0) then
// CHECK-NEXT:          lc_instances(instance)%cam_model_const_indices(lc_i) = field_ind
// CHECK-NEXT:        else
// CHECK-NEXT:          errcode = 1
// CHECK-NEXT:          errmsg = 'No field index for '//trim(lc_instances(instance)%cam_model_const_stdnames(lc_i))
// CHECK-NEXT:          return
// CHECK-NEXT:        end if
// CHECK-NEXT:      end do
// CHECK-NEXT:    end subroutine Cld_ccpp_register_constituents
// CHECK-LABEL:   subroutine Cld_ccpp_number_constituents(num_advected, errmsg, errcode, advected, instance)
// CHECK:           integer, intent(out) :: num_advected
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errcode
// CHECK-NEXT:      logical, optional, intent(in) :: advected
// CHECK-NEXT:      integer, intent(in) :: instance
// CHECK-NEXT:      errcode = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (allocated(lc_instances)) then
// CHECK-NEXT:        call lc_instances(instance)%cam_constituents_obj%num_constituents(num_advected,             &
// CHECK-NEXT:          advected=advected, errcode=errcode, errmsg=errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        num_advected = 0
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine Cld_ccpp_number_constituents
// CHECK-LABEL:   subroutine Cld_ccpp_initialize_constituents(ncols, pver, errflg, errmsg, instance)
// CHECK:           integer, intent(in) :: ncols
// CHECK-NEXT:      integer, intent(in) :: pver
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(in) :: instance
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.not. allocated(lc_instances)) then
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:        errmsg = 'ccpp_initialize_constituents: register_constituents not called'
// CHECK-NEXT:        return
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (.not. allocated(lc_instances(instance)%lc_all_constituents)) then
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:        errmsg = 'ccpp_initialize_constituents: register_constituents not called'
// CHECK-NEXT:        return
// CHECK-NEXT:      end if
// CHECK-NEXT:      call lc_instances(instance)%cam_constituents_obj%lock_data(ncols, pver, errcode=errflg,       &
// CHECK-NEXT:        errmsg=errmsg)
// CHECK-NEXT:      if (errflg /= 0) return
// CHECK-NEXT:      lc_instances(instance)%lc_constituent_array => lc_instances(instance)%cam_constituents_obj%field_data_ptr()
// CHECK-NEXT:      if (allocated(lc_instances(instance)%lc_const_tend)) deallocate(lc_instances(instance)%lc_const_tend)
// CHECK-NEXT:      allocate(lc_instances(instance)%lc_const_tend(ncols, pver, size(lc_instances(instance)%lc_all_constituents)))
// CHECK-NEXT:      lc_instances(instance)%lc_const_tend = 0.0_kind_phys
// CHECK-NEXT:      block
// CHECK-NEXT:        integer :: lc_tend_idx
// CHECK-NEXT:        character(len=512) :: lc_tend_errmsg
// CHECK-NEXT:        nullify(lc_instances(instance)%lc_cld_liq_tend)
// CHECK-NEXT:        call lc_instances(instance)%cam_constituents_obj%const_index(lc_tend_idx,                   &
// CHECK-NEXT:          'cloud_liquid_dry_mixing_ratio', errcode=errflg, errmsg=lc_tend_errmsg)
// CHECK-NEXT:        if (errflg .eq. 0 .and. lc_tend_idx .gt. 0) then
// CHECK-NEXT:          lc_instances(instance)%lc_cld_liq_tend => lc_instances(instance)%lc_const_tend(:, :,      &
// CHECK-NEXT:            lc_tend_idx)
// CHECK-NEXT:        else
// CHECK-NEXT:          errflg = 0
// CHECK-NEXT:        end if
// CHECK-NEXT:      end block
// CHECK-NEXT:    end subroutine Cld_ccpp_initialize_constituents
// CHECK-NEXT:    function Cld_constituents_array(instance) result(ptr)
// CHECK-NEXT:      real(kind=kind_phys), pointer :: ptr(:, :, :)
// CHECK-NEXT:      integer, intent(in) :: instance
// CHECK-NEXT:      ptr => lc_instances(instance)%lc_constituent_array
// CHECK-NEXT:    end function Cld_constituents_array
// CHECK-NEXT:    function Cld_advected_constituents_array(instance) result(ptr)
// CHECK-NEXT:      real(kind=kind_phys), pointer :: ptr(:, :, :)
// CHECK-NEXT:      integer, intent(in) :: instance
// CHECK-NEXT:      ptr => lc_instances(instance)%cam_constituents_obj%advected_constituents_ptr()
// CHECK-NEXT:    end function Cld_advected_constituents_array
// CHECK-LABEL:   subroutine Cld_const_get_index(std_name, index, errflg, errmsg, instance)
// CHECK:           use ccpp_constituent_prop_mod, only: to_lower
// CHECK-NEXT:      character(len=*), intent(in) :: std_name
// CHECK-NEXT:      integer, intent(out) :: index
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(in) :: instance
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      index = -1
// CHECK-NEXT:      if (.not. allocated(lc_instances)) then
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:        errmsg = 'const_get_index: constituents not registered'
// CHECK-NEXT:        return
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (.not. allocated(lc_instances(instance)%lc_all_constituents)) then
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:        errmsg = 'const_get_index: constituents not registered'
// CHECK-NEXT:        return
// CHECK-NEXT:      end if
// CHECK-NEXT:      call lc_instances(instance)%cam_constituents_obj%const_index(index, to_lower(std_name),       &
// CHECK-NEXT:        errcode=errflg, errmsg=errmsg)
// CHECK-NEXT:      if (errflg .ne. 0 .or. index .le. 0) then
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:        write(errmsg, '(3a)') 'const_get_index: constituent ', trim(std_name), ' not found'
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine Cld_const_get_index
// CHECK-NEXT:    function Cld_model_const_properties(instance) result(ptr)
// CHECK-NEXT:      type(ccpp_constituent_prop_ptr_t), pointer :: ptr(:)
// CHECK-NEXT:      integer, intent(in) :: instance
// CHECK-NEXT:      ptr => lc_instances(instance)%lc_const_props
// CHECK-NEXT:    end function Cld_model_const_properties
// CHECK-NEXT:  end module Cld_ccpp_cap
// CHECK:       // -----
// CHECK-LABEL: // FILE: ccpp_kinds.F90
// CHECK-LABEL: module ccpp_kinds
// CHECK:         use ISO_FORTRAN_ENV, only: kind_phys => REAL64
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         public :: kind_phys
// CHECK-NEXT:  end module ccpp_kinds
