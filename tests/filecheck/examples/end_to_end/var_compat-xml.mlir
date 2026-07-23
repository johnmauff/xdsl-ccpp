// Test the XML frontend -> optimizer -> Fortran pipeline for the var_compat
// example -- ported from NCAR ccpp-framework's feature/capgen-v1 branch,
// end-to-end-tests/var_compat. Exercises: nested <subcycle> Fortran codegen,
// three levels deep in one branch (var_compatibility_suite_suite_radiation's
// nested do ccpp_loop_cnt1 / do ccpp_loop_cnt0 / do ccpp_loop_cnt loops around
// effr_pre/effr_calc/effr_post), plus a second sibling dynamic-count do-loop
// (do ccpp_loop_cnt2, around effrs_calc) -- this is the primary end-to-end
// regression coverage for the nested-subcycle-support work. All four loop
// variables are declared exactly once each -- see
// ccpp_cap_refactor_plan.md's backlog for the duplicate/missing-declaration
// bugs this work found and fixed along the way. See examples/var_compat/
// README.md for what this example does and does not cover (the vertical
// array flipping attribute, top_at_one, is a separate, already-tracked,
// out-of-scope issue). The suite's four schemes all use the bare local name
// 'scalar_var' for four unrelated standard_names -- a dummy-argument-name
// collision the host's own metadata resolves by giving each standard_name a
// distinct name (scalar_var/scalar_varA/scalar_varB/scalar_varC); this
// requires the generate-host-match pass to run (as the production ccpp_xdsl
// tool always does whenever host files are given) so suite_cap.py has a
// model_var_name to disambiguate with.
//
// Two standard_names here are declared with genuinely different units or
// kind by different schemes (not just different from the host):
// effr_pre/effr_post declare the rain-particle radius in meters (matching
// the host) while effr_calc/effr_diag declare the same standard_name in
// micrometers, and effrs_calc declares the snow-particle radius in
// meters/kind_phys (matching the host) while effr_calc declares the same
// standard_name in micrometers/kind=8. Each scheme call below marshals to
// its own known kind/unit mismatch independently -- effrr_in_unit_conv gets
// freshly built (and, for effr_calc/effr_diag, torn down) around each
// individual call, effr_pre/effr_post/effrs_calc receive the shared value
// directly with no conversion at all -- rather than one suite-boundary
// conversion applied uniformly to every caller.
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/var_compat/var_compatibility_suite.xml --scheme-files examples/var_compat/effr_pre.meta,examples/var_compat/effr_calc.meta,examples/var_compat/effr_post.meta,examples/var_compat/effrs_calc.meta,examples/var_compat/effr_diag.meta,examples/var_compat/rad_lw.meta,examples/var_compat/rad_sw.meta --host-files examples/var_compat/test_host_data.meta,examples/var_compat/test_host_mod.meta,examples/var_compat/test_host.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p generate-meta-cap,generate-meta-kinds,generate-host-match,generate-arg-ownership,generate-suite-cap,generate-ccpp-cap,generate-cpp-cap,generate-kinds,strip-ccpp -t ftn | python3 -m filecheck %s

// CHECK-LABEL: // FILE: var_compatibility_suite_cap.F90
// CHECK-LABEL: module var_compatibility_suite_cap
// CHECK:         use ccpp_kinds
// CHECK-NEXT:    use effr_calc, only: effr_calc_init
// CHECK-NEXT:    use effr_calc, only: effr_calc_run
// CHECK-NEXT:    use effr_diag, only: effr_diag_init
// CHECK-NEXT:    use effr_diag, only: effr_diag_run
// CHECK-NEXT:    use effr_post, only: effr_post_init
// CHECK-NEXT:    use effr_post, only: effr_post_run
// CHECK-NEXT:    use effr_pre, only: effr_pre_init
// CHECK-NEXT:    use effr_pre, only: effr_pre_run
// CHECK-NEXT:    use effrs_calc, only: effrs_calc_run
// CHECK-NEXT:    use rad_lw, only: rad_lw_run
// CHECK-NEXT:    use rad_sw, only: rad_sw_run
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         character(len=16) :: ccpp_suite_state = 'uninitialized'
// CHECK-NEXT:    character(len=16), parameter :: const_in_time_step = 'in_time_step'
// CHECK-NEXT:    character(len=16), parameter :: const_initialized = 'initialized'
// CHECK-NEXT:    character(len=16), parameter :: const_uninitialized = 'uninitialized'
// CHECK-NEXT:    real(kind=kind_phys), allocatable :: ncl_out(:, :)
// CHECK-NEXT:    public :: var_compatibility_suite_suite_register
// CHECK-NEXT:    public :: var_compatibility_suite_suite_initialize
// CHECK-NEXT:    public :: var_compatibility_suite_suite_finalize
// CHECK-NEXT:    public :: var_compatibility_suite_suite_timestep_initial
// CHECK-NEXT:    public :: var_compatibility_suite_suite_timestep_final
// CHECK-NEXT:    public :: var_compatibility_suite_suite_radiation
// CHECK:       CONTAINS
// CHECK-LABEL:   subroutine var_compatibility_suite_suite_register(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:    end subroutine var_compatibility_suite_suite_register
// CHECK-LABEL:   subroutine var_compatibility_suite_suite_initialize(scheme_order, errmsg, errflg)
// CHECK:           integer, intent(inout) :: scheme_order
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_uninitialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in var_compatibility_suite_initialize"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call effr_pre_init(scheme_order, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call effr_calc_init(scheme_order, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call effr_post_init(scheme_order, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call effr_diag_init(scheme_order, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_initialized
// CHECK-NEXT:    end subroutine var_compatibility_suite_suite_initialize
// CHECK-LABEL:   subroutine var_compatibility_suite_suite_finalize(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in var_compatibility_suite_finalize"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_uninitialized
// CHECK-NEXT:    end subroutine var_compatibility_suite_suite_finalize
// CHECK-LABEL:   subroutine var_compatibility_suite_suite_timestep_initial(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in var_compatibility_suite_timestep_initial"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_in_time_step
// CHECK-NEXT:    end subroutine var_compatibility_suite_suite_timestep_initial
// CHECK-LABEL:   subroutine var_compatibility_suite_suite_timestep_final(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_in_time_step .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in var_compatibility_suite_timestep_final"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_initialized
// CHECK-NEXT:    end subroutine var_compatibility_suite_suite_timestep_final
// CHECK-LABEL:   subroutine var_compatibility_suite_suite_radiation(effrr_inout, scalar_varA, ncol, nlev,        &
// CHECK:           effrg_in, ncg_in, nci_out, effrl_inout, effri_out, effrs_inout, ncl_out, has_graupel,         &
// CHECK-NEXT:      scalar_var, tke_inout, tke2_inout, scalar_varB, scalar_varC, fluxLW, errmsg, errflg)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: effrr_inout(:, :)
// CHECK-NEXT:      real(kind=kind_phys), intent(in) :: scalar_varA
// CHECK-NEXT:      integer, intent(in) :: ncol
// CHECK-NEXT:      integer, intent(in) :: nlev
// CHECK-NEXT:      real(kind=kind_phys), optional, target, intent(inout) :: effrg_in(:, :)
// CHECK-NEXT:      real(kind=kind_phys), optional, target, intent(inout) :: ncg_in(:, :)
// CHECK-NEXT:      real(kind=kind_phys), optional, target, intent(inout) :: nci_out(:, :)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: effrl_inout(:, :)
// CHECK-NEXT:      real(kind=kind_phys), optional, target, intent(inout) :: effri_out(:, :)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: effrs_inout(:, :)
// CHECK-NEXT:      real(kind=kind_phys), optional, target, intent(inout) :: ncl_out(:, :)
// CHECK-NEXT:      logical, intent(in) :: has_graupel
// CHECK-NEXT:      real(kind=kind_phys), intent(in) :: scalar_var
// CHECK-NEXT:      real(kind=kind_phys), intent(in) :: tke_inout
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: tke2_inout
// CHECK-NEXT:      real(kind=kind_phys), intent(in) :: scalar_varB
// CHECK-NEXT:      integer, intent(in) :: scalar_varC
// CHECK-NEXT:      type(ty_rad_lw), target, intent(inout) :: fluxLW(:)
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      integer :: ccpp_loop_cnt
// CHECK-NEXT:      integer :: ccpp_loop_cnt0
// CHECK-NEXT:      integer :: ccpp_loop_cnt1
// CHECK-NEXT:      integer :: ccpp_loop_cnt2
// CHECK-NEXT:      real(kind=kind_phys), allocatable :: effrg_in_unit_conv(:, :)
// CHECK-NEXT:      real(kind=kind_phys), allocatable :: effrl_inout_unit_conv(:, :)
// CHECK-NEXT:      real(kind=kind_phys), allocatable :: effri_out_unit_conv(:, :)
// CHECK-NEXT:      real(kind=kind_phys) :: scalar_var_unit_conv
// CHECK-NEXT:      real(kind=kind_phys) :: tke_inout_unit_conv
// CHECK-NEXT:      real(kind=kind_phys), allocatable :: effrr_in_unit_conv(:, :)
// CHECK-NEXT:      real(kind=8), allocatable :: effrs_inout_kind_cast(:, :)
// CHECK-NEXT:      real(kind=8), allocatable :: effrs_inout_unit_conv(:, :)
// CHECK-NEXT:      real(kind=kind_phys), allocatable :: effrr_in_unit_conv3(:, :)
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      allocate(effrg_in_unit_conv(size(effrg_in, 1), size(effrg_in, 2)))
// CHECK-NEXT:      effrg_in_unit_conv = effrg_in * 1.0E6_kind_phys
// CHECK-NEXT:      allocate(effrl_inout_unit_conv(size(effrl_inout, 1), size(effrl_inout, 2)))
// CHECK-NEXT:      effrl_inout_unit_conv = effrl_inout * 1.0E6_kind_phys
// CHECK-NEXT:      allocate(effri_out_unit_conv(size(effri_out, 1), size(effri_out, 2)))
// CHECK-NEXT:      scalar_var_unit_conv = scalar_var * 0.001_kind_phys
// CHECK-NEXT:      tke_inout_unit_conv = tke_inout * 1.0_kind_phys
// CHECK-NEXT:      if (.NOT. (const_in_time_step .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in var_compatibility_suite_radiation"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      do ccpp_loop_cnt1 = 1, num_subcycles_for_effr
// CHECK-NEXT:        if (errflg .eq. 0) then
// CHECK-NEXT:          call effr_pre_run(effrr_inout, scalar_varA, errmsg, errflg)
// CHECK-NEXT:        end if
// CHECK-NEXT:        do ccpp_loop_cnt0 = 1, 2
// CHECK-NEXT:          do ccpp_loop_cnt = 1, 2
// CHECK-NEXT:            if (errflg .eq. 0) then
// CHECK-NEXT:              allocate(effrr_in_unit_conv(size(effrr_inout, 1), size(effrr_inout, 2)))
// CHECK-NEXT:              effrr_in_unit_conv = effrr_inout * 1.0E6_kind_phys
// CHECK-NEXT:              allocate(effrs_inout_kind_cast(size(effrs_inout, 1), size(effrs_inout, 2)))
// CHECK-NEXT:              effrs_inout_kind_cast = real(effrs_inout, kind=8)
// CHECK-NEXT:              allocate(effrs_inout_unit_conv(size(effrs_inout_kind_cast, 1), size(effrs_inout_kind_cast, 2)))
// CHECK-NEXT:              effrs_inout_unit_conv = effrs_inout_kind_cast * 1.0E6_8
// CHECK-NEXT:              call effr_calc_run(ncol=ncol, nlev=nlev, effrr_in=effrr_in_unit_conv,                 &
// CHECK-NEXT:                effrg_in=effrg_in_unit_conv, ncg_in=ncg_in, nci_out=nci_out,                        &
// CHECK-NEXT:                effrl_inout=effrl_inout_unit_conv, effri_out=effri_out_unit_conv,                   &
// CHECK-NEXT:                effrs_inout=effrs_inout_unit_conv, ncl_out=ncl_out, has_graupel=has_graupel,        &
// CHECK-NEXT:                scalar_var=scalar_var_unit_conv, tke_inout=tke_inout_unit_conv,                     &
// CHECK-NEXT:                tke2_inout=tke2_inout, errmsg=errmsg, errflg=errflg)
// CHECK-NEXT:              effrs_inout_kind_cast = effrs_inout_unit_conv * 1.0E-6_8
// CHECK-NEXT:              deallocate(effrs_inout_unit_conv)
// CHECK-NEXT:              effrs_inout = real(effrs_inout_kind_cast, kind=kind_phys)
// CHECK-NEXT:              deallocate(effrs_inout_kind_cast)
// CHECK-NEXT:            end if
// CHECK-NEXT:          end do
// CHECK-NEXT:        end do
// CHECK-NEXT:        if (errflg .eq. 0) then
// CHECK-NEXT:          call effr_post_run(effrr_inout, scalar_varB, errmsg, errflg)
// CHECK-NEXT:        end if
// CHECK-NEXT:      end do
// CHECK-NEXT:      do ccpp_loop_cnt2 = 1, num_subcycles_for_effr
// CHECK-NEXT:        if (errflg .eq. 0) then
// CHECK-NEXT:          call effrs_calc_run(effrs_inout, errmsg, errflg)
// CHECK-NEXT:        end if
// CHECK-NEXT:      end do
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        allocate(effrr_in_unit_conv3(size(effrr_inout, 1), size(effrr_inout, 2)))
// CHECK-NEXT:        effrr_in_unit_conv3 = effrr_inout * 1.0E6_kind_phys
// CHECK-NEXT:        call effr_diag_run(effrr_in_unit_conv3, scalar_varC, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call rad_lw_run(ncol, fluxLW, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call rad_sw_run(ncol, sfc_up_sw, sfc_down_sw, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      effrl_inout = effrl_inout_unit_conv * 1.0E-6_kind_phys
// CHECK-NEXT:      deallocate(effrl_inout_unit_conv)
// CHECK-NEXT:      effri_out = effri_out_unit_conv * 1.0E-6_kind_phys
// CHECK-NEXT:      deallocate(effri_out_unit_conv)
// CHECK-NEXT:      scalar_var = scalar_var_unit_conv * 1000.0_kind_phys
// CHECK-NEXT:      tke_inout = tke_inout_unit_conv * 1.0_kind_phys
// CHECK-NEXT:    end subroutine var_compatibility_suite_suite_radiation
// CHECK-NEXT:  end module var_compatibility_suite_cap
// CHECK:       // -----
// CHECK-LABEL: // FILE: VarCompatibility_ccpp_cap.F90
// CHECK-LABEL: module VarCompatibility_ccpp_cap
// CHECK:         use ccpp_kinds
// CHECK-NEXT:    use ccpp_constituent_prop_mod, only: ccpp_constituent_prop_ptr_t
// CHECK-NEXT:    use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t
// CHECK-NEXT:    use test_host_data, only: physics_state
// CHECK-NEXT:    use var_compatibility_suite_cap, only: var_compatibility_suite_suite_finalize
// CHECK-NEXT:    use var_compatibility_suite_cap, only: var_compatibility_suite_suite_initialize
// CHECK-NEXT:    use var_compatibility_suite_cap, only: var_compatibility_suite_suite_radiation
// CHECK-NEXT:    use var_compatibility_suite_cap, only: var_compatibility_suite_suite_register
// CHECK-NEXT:    use var_compatibility_suite_cap, only: var_compatibility_suite_suite_timestep_final
// CHECK-NEXT:    use var_compatibility_suite_cap, only: var_compatibility_suite_suite_timestep_initial
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         character(len=23), parameter :: str_var_compatibility_suite = 'var_compatibility_suite'
// CHECK-NEXT:    character(len=9), parameter :: str_radiation = 'radiation'
// CHECK-NEXT:    type(ccpp_constituent_properties_t), target, allocatable :: lc_all_constituents(:)
// CHECK-NEXT:    real(kind=kind_phys), target, allocatable :: lc_constituent_array(:, :, :)
// CHECK-NEXT:    real(kind=kind_phys), target, allocatable :: lc_const_tend(:, :, :)
// CHECK-NEXT:    type(ccpp_constituent_prop_ptr_t), target, allocatable :: lc_const_props(:)
// CHECK-NEXT:    real(kind=kind_phys), allocatable :: lc_ncl_out(:, :)
// CHECK-NEXT:    public :: VarCompatibility_ccpp_physics_register
// CHECK-NEXT:    public :: VarCompatibility_ccpp_physics_initialize
// CHECK-NEXT:    public :: VarCompatibility_ccpp_physics_finalize
// CHECK-NEXT:    public :: VarCompatibility_ccpp_physics_timestep_initial
// CHECK-NEXT:    public :: VarCompatibility_ccpp_physics_timestep_final
// CHECK-NEXT:    public :: VarCompatibility_ccpp_physics_run
// CHECK-NEXT:    public :: ccpp_physics_suite_list
// CHECK-NEXT:    public :: ccpp_physics_suite_part_list
// CHECK-NEXT:    public :: ccpp_physics_suite_variables
// CHECK-NEXT:    public :: VarCompatibility_ccpp_is_scheme_constituent
// CHECK-NEXT:    public :: VarCompatibility_ccpp_deallocate_dynamic_constituents
// CHECK-NEXT:    public :: VarCompatibility_ccpp_register_constituents
// CHECK-NEXT:    public :: VarCompatibility_ccpp_number_constituents
// CHECK-NEXT:    public :: VarCompatibility_ccpp_initialize_constituents
// CHECK-NEXT:    public :: VarCompatibility_constituents_array
// CHECK-NEXT:    public :: VarCompatibility_const_get_index
// CHECK-NEXT:    public :: VarCompatibility_model_const_properties
// CHECK:       CONTAINS
// CHECK-LABEL:   subroutine VarCompatibility_ccpp_physics_register(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'var_compatibility_suite') then
// CHECK-NEXT:        call var_compatibility_suite_suite_register(errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine VarCompatibility_ccpp_physics_register
// CHECK-LABEL:   subroutine VarCompatibility_ccpp_physics_initialize(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      integer :: lc_scheme_order
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'var_compatibility_suite') then
// CHECK-NEXT:        call var_compatibility_suite_suite_initialize(lc_scheme_order, errmsg, errflg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine VarCompatibility_ccpp_physics_initialize
// CHECK-LABEL:   subroutine VarCompatibility_ccpp_physics_finalize(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'var_compatibility_suite') then
// CHECK-NEXT:        call var_compatibility_suite_suite_finalize(errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine VarCompatibility_ccpp_physics_finalize
// CHECK-LABEL:   subroutine VarCompatibility_ccpp_physics_timestep_initial(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'var_compatibility_suite') then
// CHECK-NEXT:        call var_compatibility_suite_suite_timestep_initial(errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine VarCompatibility_ccpp_physics_timestep_initial
// CHECK-LABEL:   subroutine VarCompatibility_ccpp_physics_timestep_final(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'var_compatibility_suite') then
// CHECK-NEXT:        call var_compatibility_suite_suite_timestep_final(errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine VarCompatibility_ccpp_physics_timestep_final
// CHECK-LABEL:   subroutine VarCompatibility_ccpp_physics_run(suite_name, suite_part, effrr_inout, scalar_varA,  &
// CHECK:           ncol, nlev, effrg_in, ncg_in, nci_out, effrl_inout, effri_out, effrs_inout, has_graupel,      &
// CHECK-NEXT:      scalar_var, tke_inout, tke2_inout, scalar_varB, scalar_varC, fluxLW, errmsg, errflg)
// CHECK-NEXT:      character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), intent(in) :: suite_part
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: effrr_inout(:, :)
// CHECK-NEXT:      real(kind=kind_phys), intent(in) :: scalar_varA
// CHECK-NEXT:      integer, intent(in) :: ncol
// CHECK-NEXT:      integer, intent(in) :: nlev
// CHECK-NEXT:      real(kind=kind_phys), optional, target, intent(inout) :: effrg_in(:, :)
// CHECK-NEXT:      real(kind=kind_phys), optional, target, intent(inout) :: ncg_in(:, :)
// CHECK-NEXT:      real(kind=kind_phys), optional, target, intent(inout) :: nci_out(:, :)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: effrl_inout(:, :)
// CHECK-NEXT:      real(kind=kind_phys), optional, target, intent(inout) :: effri_out(:, :)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: effrs_inout(:, :)
// CHECK-NEXT:      logical, intent(in) :: has_graupel
// CHECK-NEXT:      real(kind=kind_phys), intent(in) :: scalar_var
// CHECK-NEXT:      real(kind=kind_phys), intent(in) :: tke_inout
// CHECK-NEXT:      real(kind=kind_phys), intent(in) :: tke2_inout
// CHECK-NEXT:      real(kind=kind_phys), intent(in) :: scalar_varB
// CHECK-NEXT:      integer, intent(in) :: scalar_varC
// CHECK-NEXT:      type(ty_rad_lw), target, intent(inout) :: fluxLW(:)
// CHECK-NEXT:      character(len=512), intent(inout) :: errmsg
// CHECK-NEXT:      integer, intent(inout) :: errflg
// CHECK-NEXT:      real(kind=kind_phys) :: ccpp_tmp_0
// CHECK-NEXT:      real(kind=kind_phys) :: ccpp_tmp_1
// CHECK-NEXT:      real(kind=kind_phys) :: ccpp_tmp_2
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'var_compatibility_suite') then
// CHECK-NEXT:        if (trim(suite_part) .eq. 'radiation') then
// CHECK-NEXT:          call var_compatibility_suite_suite_radiation(effrr_inout=effrr_inout,                     &
// CHECK-NEXT:            scalar_varA=scalar_varA, ncol=ncol, nlev=nlev, effrg_in=effrg_in, ncg_in=ncg_in,        &
// CHECK-NEXT:            nci_out=nci_out, effrl_inout=effrl_inout, effri_out=effri_out, effrs_inout=effrs_inout, &
// CHECK-NEXT:            ncl_out=lc_ncl_out, has_graupel=has_graupel, scalar_var=scalar_var,                     &
// CHECK-NEXT:            tke_inout=tke_inout, tke2_inout=tke2_inout, scalar_varB=scalar_varB,                    &
// CHECK-NEXT:            scalar_varC=scalar_varC, fluxLW=fluxLW, _out_0=ccpp_tmp_0, _out_1=ccpp_tmp_1,           &
// CHECK-NEXT:            _out_2=ccpp_tmp_2, errmsg=errmsg, errflg=errflg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg, '(3a)') "No suite part named ", trim(suite_part),                           &
// CHECK-NEXT:            " found in suite var_compatibility_suite"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine VarCompatibility_ccpp_physics_run
// CHECK-LABEL:   subroutine ccpp_physics_suite_list(suites)
// CHECK:           character(len=*), allocatable, intent(out) :: suites(:)
// CHECK:           allocate(suites(1))
// CHECK-NEXT:      suites(1) = str_var_compatibility_suite
// CHECK-NEXT:    end subroutine ccpp_physics_suite_list
// CHECK-LABEL:   subroutine ccpp_physics_suite_part_list(suite_name, part_list, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), allocatable, intent(out) :: part_list(:)
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'var_compatibility_suite') then
// CHECK-NEXT:        allocate(part_list(1))
// CHECK-NEXT:        part_list(1) = str_radiation
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
// CHECK-NEXT:      if (trim(suite_name) .eq. 'var_compatibility_suite') then
// CHECK-NEXT:        if (do_input .and. .not. do_output) then
// CHECK-NEXT:          allocate(var_list(14))
// CHECK-NEXT:          var_list(1) = 'cloud_graupel_number_concentration  '
// CHECK-NEXT:          var_list(2) = 'effective_radius_of_stratiform_cloud_graupel'
// CHECK-NEXT:          var_list(3) = 'effective_radius_of_stratiform_cloud_liquid_water_particle'
// CHECK-NEXT:          var_list(4) = 'effective_radius_of_stratiform_cloud_rain_particle'
// CHECK-NEXT:          var_list(5) = 'effective_radius_of_stratiform_cloud_snow_particle'
// CHECK-NEXT:          var_list(6) = 'flag_indicating_cloud_microphysics_has_graupel'
// CHECK-NEXT:          var_list(7) = 'longwave_radiation_fluxes           '
// CHECK-NEXT:          var_list(8) = 'scalar_variable_for_testing         '
// CHECK-NEXT:          var_list(9) = 'scalar_variable_for_testing_a       '
// CHECK-NEXT:          var_list(10) = 'scalar_variable_for_testing_b       '
// CHECK-NEXT:          var_list(11) = 'scalar_variable_for_testing_c       '
// CHECK-NEXT:          var_list(12) = 'scheme_order_in_suite               '
// CHECK-NEXT:          var_list(13) = 'turbulent_kinetic_energy            '
// CHECK-NEXT:          var_list(14) = 'turbulent_kinetic_energy2           '
// CHECK-NEXT:        else if (.not. do_input .and. do_output) then
// CHECK-NEXT:          allocate(var_list(13))
// CHECK-NEXT:          var_list(1) = 'ccpp_error_code                     '
// CHECK-NEXT:          var_list(2) = 'ccpp_error_message                  '
// CHECK-NEXT:          var_list(3) = 'cloud_ice_number_concentration      '
// CHECK-NEXT:          var_list(4) = 'cloud_liquid_number_concentration   '
// CHECK-NEXT:          var_list(5) = 'effective_radius_of_stratiform_cloud_ice_particle'
// CHECK-NEXT:          var_list(6) = 'effective_radius_of_stratiform_cloud_liquid_water_particle'
// CHECK-NEXT:          var_list(7) = 'effective_radius_of_stratiform_cloud_rain_particle'
// CHECK-NEXT:          var_list(8) = 'effective_radius_of_stratiform_cloud_snow_particle'
// CHECK-NEXT:          var_list(9) = 'longwave_radiation_fluxes           '
// CHECK-NEXT:          var_list(10) = 'scalar_variable_for_testing         '
// CHECK-NEXT:          var_list(11) = 'scheme_order_in_suite               '
// CHECK-NEXT:          var_list(12) = 'turbulent_kinetic_energy            '
// CHECK-NEXT:          var_list(13) = 'turbulent_kinetic_energy2           '
// CHECK-NEXT:        else
// CHECK-NEXT:          allocate(var_list(19))
// CHECK-NEXT:          var_list(1) = 'ccpp_error_code                     '
// CHECK-NEXT:          var_list(2) = 'ccpp_error_message                  '
// CHECK-NEXT:          var_list(3) = 'cloud_graupel_number_concentration  '
// CHECK-NEXT:          var_list(4) = 'cloud_ice_number_concentration      '
// CHECK-NEXT:          var_list(5) = 'cloud_liquid_number_concentration   '
// CHECK-NEXT:          var_list(6) = 'effective_radius_of_stratiform_cloud_graupel'
// CHECK-NEXT:          var_list(7) = 'effective_radius_of_stratiform_cloud_ice_particle'
// CHECK-NEXT:          var_list(8) = 'effective_radius_of_stratiform_cloud_liquid_water_particle'
// CHECK-NEXT:          var_list(9) = 'effective_radius_of_stratiform_cloud_rain_particle'
// CHECK-NEXT:          var_list(10) = 'effective_radius_of_stratiform_cloud_snow_particle'
// CHECK-NEXT:          var_list(11) = 'flag_indicating_cloud_microphysics_has_graupel'
// CHECK-NEXT:          var_list(12) = 'longwave_radiation_fluxes           '
// CHECK-NEXT:          var_list(13) = 'scalar_variable_for_testing         '
// CHECK-NEXT:          var_list(14) = 'scalar_variable_for_testing_a       '
// CHECK-NEXT:          var_list(15) = 'scalar_variable_for_testing_b       '
// CHECK-NEXT:          var_list(16) = 'scalar_variable_for_testing_c       '
// CHECK-NEXT:          var_list(17) = 'scheme_order_in_suite               '
// CHECK-NEXT:          var_list(18) = 'turbulent_kinetic_energy            '
// CHECK-NEXT:          var_list(19) = 'turbulent_kinetic_energy2           '
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_physics_suite_variables
// CHECK-NEXT:      subroutine VarCompatibility_ccpp_is_scheme_constituent(std_name, is_const, errflg, errmsg)
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
// CHECK-NEXT:      end subroutine VarCompatibility_ccpp_is_scheme_constituent
// CHECK:           subroutine VarCompatibility_ccpp_deallocate_dynamic_constituents()
// CHECK-NEXT:        if (allocated(lc_all_constituents)) deallocate(lc_all_constituents)
// CHECK-NEXT:        if (allocated(lc_const_props)) deallocate(lc_const_props)
// CHECK-NEXT:        if (allocated(lc_constituent_array)) deallocate(lc_constituent_array)
// CHECK-NEXT:        if (allocated(lc_const_tend)) deallocate(lc_const_tend)
// CHECK-NEXT:        if (allocated(lc_ncl_out)) deallocate(lc_ncl_out)
// CHECK-NEXT:      end subroutine VarCompatibility_ccpp_deallocate_dynamic_constituents
// CHECK:           subroutine VarCompatibility_ccpp_register_constituents(host_constituents, errmsg, errflg)
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
// CHECK-NEXT:      end subroutine VarCompatibility_ccpp_register_constituents
// CHECK:           subroutine VarCompatibility_ccpp_number_constituents(num_advected, errmsg, errflg)
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
// CHECK-NEXT:      end subroutine VarCompatibility_ccpp_number_constituents
// CHECK:           subroutine VarCompatibility_ccpp_initialize_constituents(ncols, pver, errflg, errmsg)
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
// CHECK-NEXT:        if (allocated(lc_ncl_out)) deallocate(lc_ncl_out)
// CHECK-NEXT:        allocate(lc_ncl_out(ncols, pver))
// CHECK-NEXT:        lc_ncl_out = 0.0_kind_phys
// CHECK-NEXT:      end subroutine VarCompatibility_ccpp_initialize_constituents
// CHECK:           function VarCompatibility_constituents_array() result(ptr)
// CHECK-NEXT:        real(kind=kind_phys), pointer :: ptr(:, :, :)
// CHECK-NEXT:        ptr => lc_constituent_array
// CHECK-NEXT:      end function VarCompatibility_constituents_array
// CHECK:           subroutine VarCompatibility_const_get_index(std_name, index, errflg, errmsg)
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
// CHECK-NEXT:      end subroutine VarCompatibility_const_get_index
// CHECK:           function VarCompatibility_model_const_properties() result(ptr)
// CHECK-NEXT:        type(ccpp_constituent_prop_ptr_t), pointer :: ptr(:)
// CHECK-NEXT:        ptr => lc_const_props
// CHECK-NEXT:      end function VarCompatibility_model_const_properties
// CHECK-NEXT:  end module VarCompatibility_ccpp_cap
// CHECK:       // -----
// CHECK-LABEL: // FILE: ccpp_kinds.F90
// CHECK-LABEL: module ccpp_kinds
// CHECK:         use ISO_FORTRAN_ENV, only: kind_phys => REAL64
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         public :: kind_phys
// CHECK-NEXT:  end module ccpp_kinds
