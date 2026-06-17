// Test the full XML frontend → optimizer → Fortran pipeline for the capgen
// example.  Two suites (ddt_suite, temp_suite) with DDT arguments and
// optional entry points.
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/capgen/ddt_suite.xml,examples/capgen/temp_suite.xml --scheme-files examples/capgen/make_ddt.meta,examples/capgen/environ_conditions.meta,examples/capgen/setup_coeffs.meta,examples/capgen/temp_set.meta,examples/capgen/temp_calc_adjust.meta,examples/capgen/temp_adjust.meta --host-files examples/capgen/test_host_data.meta,examples/capgen/test_host_mod.meta,examples/capgen/test_host.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap,generate-kinds,strip-ccpp -t ftn | python3 -m filecheck %s

// CHECK-LABEL: // FILE: temp_suite_cap.F90
// CHECK-LABEL: module temp_suite_cap
// CHECK:         use ccpp_kinds
// CHECK-NEXT:    use temp_adjust, only: temp_adjust_finalize
// CHECK-NEXT:    use temp_adjust, only: temp_adjust_init
// CHECK-NEXT:    use temp_adjust, only: temp_adjust_register
// CHECK-NEXT:    use temp_adjust, only: temp_adjust_run
// CHECK-NEXT:    use temp_calc_adjust, only: temp_calc_adjust_finalize
// CHECK-NEXT:    use temp_calc_adjust, only: temp_calc_adjust_init
// CHECK-NEXT:    use temp_calc_adjust, only: temp_calc_adjust_run
// CHECK-NEXT:    use temp_set, only: temp_set_finalize
// CHECK-NEXT:    use temp_set, only: temp_set_init
// CHECK-NEXT:    use temp_set, only: temp_set_run
// CHECK-NEXT:    use temp_set, only: temp_set_timestep_initialize
// CHECK-NEXT:    use test_host_mod, only: ncols
// CHECK-NEXT:    use test_host_mod, only: pcnst
// CHECK-NEXT:    use test_host_mod, only: pver
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         character(len=16) :: ccpp_suite_state = 'uninitialized'
// CHECK-NEXT:    character(len=16), parameter :: const_in_time_step = 'in_time_step'
// CHECK-NEXT:    character(len=16), parameter :: const_initialized = 'initialized'
// CHECK-NEXT:    character(len=16), parameter :: const_uninitialized = 'uninitialized'
// CHECK-NEXT:    real(kind=kind_phys) :: temp_inc_set
// CHECK-NEXT:    real(kind=kind_phys), allocatable :: temp(:, :)
// CHECK-NEXT:    real(kind=kind_phys), allocatable :: to_promote(:, :)
// CHECK-NEXT:    real(kind=kind_phys), allocatable :: promote_pcnst(:)
// CHECK-NEXT:    real(kind=kind_phys), allocatable :: temp_calc(:)
// CHECK-NEXT:    public :: temp_suite_suite_register
// CHECK-NEXT:    public :: temp_suite_suite_initialize
// CHECK-NEXT:    public :: temp_suite_suite_finalize
// CHECK-NEXT:    public :: temp_suite_suite_timestep_initial
// CHECK-NEXT:    public :: temp_suite_suite_timestep_final
// CHECK-NEXT:    public :: temp_suite_suite_physics1
// CHECK-NEXT:    public :: temp_suite_suite_physics2
// CHECK:       CONTAINS
// CHECK-LABEL:   subroutine temp_suite_suite_register(config_var, errmsg, errflg)
// CHECK:           logical, intent(in) :: config_var
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.not. allocated(temp)) then
// CHECK-NEXT:        allocate(temp(ncols, pver))
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (.not. allocated(to_promote)) then
// CHECK-NEXT:        allocate(to_promote(ncols, pver))
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (.not. allocated(promote_pcnst)) then
// CHECK-NEXT:        allocate(promote_pcnst(pcnst))
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (.not. allocated(temp_calc)) then
// CHECK-NEXT:        allocate(temp_calc(ncols))
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call temp_adjust_register(config_var, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine temp_suite_suite_register
// CHECK-LABEL:   subroutine temp_suite_suite_initialize(temp_inc_in, fudge, temp_inc_set, errmsg, errflg)
// CHECK:           real(kind=kind_phys), intent(in) :: temp_inc_in
// CHECK-NEXT:      real(kind=kind_phys), intent(in) :: fudge
// CHECK-NEXT:      real(kind=kind_phys), intent(out) :: temp_inc_set
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.not. allocated(temp)) then
// CHECK-NEXT:        allocate(temp(ncols, pver))
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (.not. allocated(to_promote)) then
// CHECK-NEXT:        allocate(to_promote(ncols, pver))
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (.not. allocated(promote_pcnst)) then
// CHECK-NEXT:        allocate(promote_pcnst(pcnst))
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (.not. allocated(temp_calc)) then
// CHECK-NEXT:        allocate(temp_calc(ncols))
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (.NOT. (const_uninitialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in temp_suite_initialize"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call temp_set_init(temp_inc_in, fudge, temp_inc_set, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call temp_calc_adjust_init(errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call temp_adjust_init(errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_initialized
// CHECK-NEXT:    end subroutine temp_suite_suite_initialize
// CHECK-LABEL:   subroutine temp_suite_suite_finalize(errmsg, errflg)
// CHECK:           character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in temp_suite_finalize"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call temp_set_finalize(errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call temp_calc_adjust_finalize(errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call temp_adjust_finalize(errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_uninitialized
// CHECK-NEXT:    end subroutine temp_suite_suite_finalize
// CHECK-LABEL:   subroutine temp_suite_suite_timestep_initial(ncol, temp_inc, temp_level, errmsg, errflg)
// CHECK:           integer, intent(in) :: ncol
// CHECK-NEXT:      real(kind=kind_phys), intent(in) :: temp_inc
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: temp_level(:, :)
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in temp_suite_timestep_initial"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call temp_set_timestep_initialize(ncol, temp_inc, temp_level, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_in_time_step
// CHECK-NEXT:    end subroutine temp_suite_suite_timestep_initial
// CHECK-LABEL:   subroutine temp_suite_suite_timestep_final(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_in_time_step .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in temp_suite_timestep_final"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_initialized
// CHECK-NEXT:    end subroutine temp_suite_suite_timestep_final
// CHECK-LABEL:   subroutine temp_suite_suite_physics1(col_start, col_end, lev, timestep, temp_level, temp_diag,  &
// CHECK:           temp, ps, to_promote, promote_pcnst, slev_lbound, soil_levs, var_array, errmsg, errflg)
// CHECK-NEXT:      integer, intent(in) :: col_start
// CHECK-NEXT:      integer, intent(in) :: col_end
// CHECK-NEXT:      integer, intent(in) :: lev
// CHECK-NEXT:      real(kind=kind_phys), intent(in) :: timestep
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: temp_level(:, :)
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: temp_diag(:, :)
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: temp(:, :)
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: ps(:)
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: to_promote(:, :)
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: promote_pcnst(:)
// CHECK-NEXT:      integer, intent(in) :: slev_lbound
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: soil_levs(:)
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: var_array(:, :, :, :)
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
// CHECK-NEXT:          "' in temp_suite_physics1"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call temp_set_run(ncol, lev, timestep, temp_level, temp_diag, temp, ps, to_promote,         &
// CHECK-NEXT:          promote_pcnst, slev_lbound, soil_levs, var_array, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine temp_suite_suite_physics1
// CHECK-LABEL:   subroutine temp_suite_suite_physics2(col_start, col_end, timestep, temp_level, temp_calc,       &
// CHECK:           temp_layer, qv, ps, to_promote, promote_pcnst, errmsg, errflg)
// CHECK-NEXT:      integer, intent(in) :: col_start
// CHECK-NEXT:      integer, intent(in) :: col_end
// CHECK-NEXT:      real(kind=kind_phys), intent(in) :: timestep
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: temp_level(:, :)
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: temp_calc(:)
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: temp_layer(:)
// CHECK-NEXT:      real(kind=kind_phys), optional, intent(inout) :: qv(:)
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: ps(:)
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: to_promote(:)
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: promote_pcnst(:)
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
// CHECK-NEXT:          "' in temp_suite_physics2"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call temp_calc_adjust_run(ncol, timestep, temp_level, temp_calc, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call temp_adjust_run(foo=ncol, timestep=timestep, temp_prev=temp_calc,                      &
// CHECK-NEXT:          temp_layer=temp_layer, qv=qv, ps=ps, to_promote=to_promote, promote_pcnst=promote_pcnst,  &
// CHECK-NEXT:          errmsg=errmsg, errflg=errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine temp_suite_suite_physics2
// CHECK-NEXT:  end module temp_suite_cap
// CHECK:       // -----
// CHECK-LABEL: // FILE: ddt_suite_cap.F90
// CHECK-LABEL: module ddt_suite_cap
// CHECK:         use ccpp_kinds
// CHECK-NEXT:    use environ_conditions, only: environ_conditions_finalize
// CHECK-NEXT:    use environ_conditions, only: environ_conditions_init
// CHECK-NEXT:    use environ_conditions, only: environ_conditions_run
// CHECK-NEXT:    use make_ddt, only: make_ddt_init
// CHECK-NEXT:    use make_ddt, only: make_ddt_run
// CHECK-NEXT:    use make_ddt, only: vmr_type
// CHECK-NEXT:    use test_host_mod, only: ncols
// CHECK-NEXT:    use test_host_mod, only: num_model_times
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
// CHECK-NEXT:      if (.not. allocated(o3)) then
// CHECK-NEXT:        allocate(o3(ncols))
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (.not. allocated(hno3)) then
// CHECK-NEXT:        allocate(hno3(ncols))
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (.not. allocated(model_times)) then
// CHECK-NEXT:        allocate(model_times(num_model_times))
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ddt_suite_suite_register
// CHECK-LABEL:   subroutine ddt_suite_suite_initialize(nbox, o3, hno3, model_times, vmr, errmsg, errflg, ntimes)
// CHECK:           integer, intent(in) :: nbox
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
// CHECK-NEXT:        call make_ddt_init(nbox, vmr, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call environ_conditions_init(nbox, o3, hno3, ntimes, model_times, errmsg, errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_initialized
// CHECK-NEXT:    end subroutine ddt_suite_suite_initialize
// CHECK-LABEL:   subroutine ddt_suite_suite_finalize(ntimes, model_times, errmsg, errflg)
// CHECK:           integer, intent(in) :: ntimes
// CHECK-NEXT:      integer, intent(inout) :: model_times(:)
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
// CHECK-LABEL:   subroutine ddt_suite_suite_timestep_final(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_in_time_step .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in ddt_suite_timestep_final"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_initialized
// CHECK-NEXT:    end subroutine ddt_suite_suite_timestep_final
// CHECK-LABEL:   subroutine ddt_suite_suite_data_prep(cols, cole, O3, HNO3, vmr, psurf, errmsg, errflg)
// CHECK:           integer, intent(in) :: cols
// CHECK-NEXT:      integer, intent(in) :: cole
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: O3(:)
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: HNO3(:)
// CHECK-NEXT:      type(vmr_type), intent(inout) :: vmr
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: psurf(:)
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
// CHECK-NEXT:    use ddt_suite_cap, only: ddt_suite_suite_data_prep
// CHECK-NEXT:    use ddt_suite_cap, only: ddt_suite_suite_finalize
// CHECK-NEXT:    use ddt_suite_cap, only: ddt_suite_suite_initialize
// CHECK-NEXT:    use ddt_suite_cap, only: ddt_suite_suite_register
// CHECK-NEXT:    use ddt_suite_cap, only: ddt_suite_suite_timestep_final
// CHECK-NEXT:    use ddt_suite_cap, only: ddt_suite_suite_timestep_initial
// CHECK-NEXT:    use make_ddt, only: vmr_type
// CHECK-NEXT:    use temp_suite_cap, only: temp_suite_suite_finalize
// CHECK-NEXT:    use temp_suite_cap, only: temp_suite_suite_initialize
// CHECK-NEXT:    use temp_suite_cap, only: temp_suite_suite_physics1
// CHECK-NEXT:    use temp_suite_cap, only: temp_suite_suite_physics2
// CHECK-NEXT:    use temp_suite_cap, only: temp_suite_suite_register
// CHECK-NEXT:    use temp_suite_cap, only: temp_suite_suite_timestep_final
// CHECK-NEXT:    use temp_suite_cap, only: temp_suite_suite_timestep_initial
// CHECK-NEXT:    use test_host_data, only: physics_state
// CHECK-NEXT:    use test_host_mod, only: config_var
// CHECK-NEXT:    use test_host_mod, only: model_times
// CHECK-NEXT:    use test_host_mod, only: ncols
// CHECK-NEXT:    use test_host_mod, only: num_model_times
// CHECK-NEXT:    use test_host_mod, only: temp_inc
// CHECK-NEXT:    use test_host_mod, only: temp_interfaces
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         character(len=9), parameter :: str_ddt_suite = 'ddt_suite'
// CHECK-NEXT:    character(len=10), parameter :: str_temp_suite = 'temp_suite'
// CHECK-NEXT:    character(len=9), parameter :: str_data_prep = 'data_prep'
// CHECK-NEXT:    character(len=8), parameter :: str_physics1 = 'physics1'
// CHECK-NEXT:    character(len=8), parameter :: str_physics2 = 'physics2'
// CHECK-NEXT:    public :: Ddt_ccpp_physics_register
// CHECK-NEXT:    public :: Ddt_ccpp_physics_initialize
// CHECK-NEXT:    public :: Ddt_ccpp_physics_finalize
// CHECK-NEXT:    public :: Ddt_ccpp_physics_timestep_initial
// CHECK-NEXT:    public :: Ddt_ccpp_physics_timestep_final
// CHECK-NEXT:    public :: Ddt_ccpp_physics_run
// CHECK-NEXT:    public :: ccpp_physics_suite_list
// CHECK-NEXT:    public :: ccpp_physics_suite_part_list
// CHECK-NEXT:    public :: ccpp_physics_suite_variables
// CHECK:       CONTAINS
// CHECK-LABEL:   subroutine Ddt_ccpp_physics_register(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'ddt_suite') then
// CHECK-NEXT:        call ddt_suite_suite_register(errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        if (trim(suite_name) .eq. 'temp_suite') then
// CHECK-NEXT:          call temp_suite_suite_register(config_var, errmsg, errflg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg, '(3a)') "No suite named ", trim(suite_name), "found"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine Ddt_ccpp_physics_register
// CHECK-LABEL:   subroutine Ddt_ccpp_physics_initialize(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      real(kind=kind_phys) :: lc_fudge
// CHECK-NEXT:      real(kind=kind_phys), allocatable :: lc_o3(:)
// CHECK-NEXT:      real(kind=kind_phys), allocatable :: lc_hno3(:)
// CHECK-NEXT:      type(vmr_type) :: ccpp_tmp_0
// CHECK-NEXT:      real(kind=kind_phys) :: ccpp_tmp_1
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'ddt_suite') then
// CHECK-NEXT:        call ddt_suite_suite_initialize(ncols, lc_o3, lc_hno3, model_times, ccpp_tmp_0, errmsg,     &
// CHECK-NEXT:          errflg, num_model_times)
// CHECK-NEXT:      else
// CHECK-NEXT:        if (trim(suite_name) .eq. 'temp_suite') then
// CHECK-NEXT:          call temp_suite_suite_initialize(temp_inc, lc_fudge, ccpp_tmp_1, errmsg, errflg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg, '(3a)') "No suite named ", trim(suite_name), "found"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine Ddt_ccpp_physics_initialize
// CHECK-LABEL:   subroutine Ddt_ccpp_physics_finalize(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'ddt_suite') then
// CHECK-NEXT:        call ddt_suite_suite_finalize(num_model_times, model_times, errmsg, errflg)
// CHECK-NEXT:      else
// CHECK-NEXT:        if (trim(suite_name) .eq. 'temp_suite') then
// CHECK-NEXT:          call temp_suite_suite_finalize(errmsg, errflg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg, '(3a)') "No suite named ", trim(suite_name), "found"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine Ddt_ccpp_physics_finalize
// CHECK-LABEL:   subroutine Ddt_ccpp_physics_timestep_initial(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK-NEXT:      real(kind=kind_phys) :: lc_temp_inc
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'ddt_suite') then
// CHECK-NEXT:        call ddt_suite_suite_timestep_initial(errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        if (trim(suite_name) .eq. 'temp_suite') then
// CHECK-NEXT:          call temp_suite_suite_timestep_initial(ncols, lc_temp_inc, temp_interfaces, errmsg, errflg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg, '(3a)') "No suite named ", trim(suite_name), "found"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine Ddt_ccpp_physics_timestep_initial
// CHECK-LABEL:   subroutine Ddt_ccpp_physics_timestep_final(suite_name, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'ddt_suite') then
// CHECK-NEXT:        call ddt_suite_suite_timestep_final(errflg, errmsg)
// CHECK-NEXT:      else
// CHECK-NEXT:        if (trim(suite_name) .eq. 'temp_suite') then
// CHECK-NEXT:          call temp_suite_suite_timestep_final(errflg, errmsg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg, '(3a)') "No suite named ", trim(suite_name), "found"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine Ddt_ccpp_physics_timestep_final
// CHECK-LABEL:   subroutine Ddt_ccpp_physics_run(suite_name, suite_part, cols, cole, O3, HNO3, vmr, psurf, lev,  &
// CHECK:           timestep, temp_level, temp_diag, temp, to_promote, promote_pcnst, slev_lbound, soil_levs,     &
// CHECK-NEXT:      var_array, temp_calc, qv, errmsg, errflg)
// CHECK-NEXT:      character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), intent(in) :: suite_part
// CHECK-NEXT:      integer, intent(in) :: cols
// CHECK-NEXT:      integer, intent(in) :: cole
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: O3(:)
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: HNO3(:)
// CHECK-NEXT:      type(vmr_type), intent(in) :: vmr
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: psurf(:)
// CHECK-NEXT:      integer, intent(in) :: lev
// CHECK-NEXT:      real(kind=kind_phys), intent(in) :: timestep
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: temp_level(:, :)
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: temp_diag(:, :)
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: temp(:, :)
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: to_promote(:, :)
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: promote_pcnst(:)
// CHECK-NEXT:      integer, intent(in) :: slev_lbound
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: soil_levs(:)
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: var_array(:, :, :, :)
// CHECK-NEXT:      real(kind=kind_phys), intent(inout) :: temp_calc(:)
// CHECK-NEXT:      real(kind=kind_phys), optional, intent(inout) :: qv(:)
// CHECK-NEXT:      character(len=512), intent(inout) :: errmsg
// CHECK-NEXT:      integer, intent(inout) :: errflg
// CHECK-NEXT:      type(vmr_type) :: ccpp_tmp_0
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'ddt_suite') then
// CHECK-NEXT:        if (trim(suite_part) .eq. 'data_prep') then
// CHECK-NEXT:          call ddt_suite_suite_data_prep(cols, cole, O3, HNO3, vmr, psurf, ccpp_tmp_0, errmsg,      &
// CHECK-NEXT:            errflg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg, '(3a)') "No suite part named ", trim(suite_part), " found in suite ddt_suite"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        if (trim(suite_name) .eq. 'temp_suite') then
// CHECK-NEXT:          if (trim(suite_part) .eq. 'physics1') then
// CHECK-NEXT:            call temp_suite_suite_physics1(cols, cole, lev, timestep, temp_level, temp_diag, temp,  &
// CHECK-NEXT:              psurf, to_promote, promote_pcnst, slev_lbound, soil_levs, var_array, errmsg, errflg)
// CHECK-NEXT:          else
// CHECK-NEXT:            if (trim(suite_part) .eq. 'physics2') then
// CHECK-NEXT:              call temp_suite_suite_physics2(col_start=cols, col_end=cole, timestep=timestep,       &
// CHECK-NEXT:                temp_level=temp_level, temp_calc=temp_calc, temp_layer=temp, qv=qv, ps=psurf,       &
// CHECK-NEXT:                to_promote=to_promote, promote_pcnst=promote_pcnst, errmsg=errmsg, errflg=errflg)
// CHECK-NEXT:            else
// CHECK-NEXT:              write(errmsg, '(3a)') "No suite part named ", trim(suite_part),                       &
// CHECK-NEXT:                " found in suite temp_suite"
// CHECK-NEXT:              errflg = 1
// CHECK-NEXT:            end if
// CHECK-NEXT:          end if
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg, '(3a)') "No suite named ", trim(suite_name), "found"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine Ddt_ccpp_physics_run
// CHECK-LABEL:   subroutine ccpp_physics_suite_list(suites)
// CHECK:           character(len=*), allocatable, intent(out) :: suites(:)
// CHECK:           allocate(suites(2))
// CHECK-NEXT:      suites(1) = str_ddt_suite
// CHECK-NEXT:      suites(2) = str_temp_suite
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
// CHECK-NEXT:        if (trim(suite_name) .eq. 'temp_suite') then
// CHECK-NEXT:          allocate(part_list(2))
// CHECK-NEXT:          part_list(1) = str_physics1
// CHECK-NEXT:          part_list(2) = str_physics2
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
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
// CHECK-NEXT:          allocate(var_list(3))
// CHECK-NEXT:          var_list(1) = 'model_times                         '
// CHECK-NEXT:          var_list(2) = 'number_of_model_times               '
// CHECK-NEXT:          var_list(3) = 'surface_air_pressure                '
// CHECK-NEXT:        else if (.not. do_input .and. do_output) then
// CHECK-NEXT:          allocate(var_list(5))
// CHECK-NEXT:          var_list(1) = 'ccpp_error_code                     '
// CHECK-NEXT:          var_list(2) = 'ccpp_error_message                  '
// CHECK-NEXT:          var_list(3) = 'model_times                         '
// CHECK-NEXT:          var_list(4) = 'number_of_model_times               '
// CHECK-NEXT:          var_list(5) = 'surface_air_pressure                '
// CHECK-NEXT:        else
// CHECK-NEXT:          allocate(var_list(5))
// CHECK-NEXT:          var_list(1) = 'ccpp_error_code                     '
// CHECK-NEXT:          var_list(2) = 'ccpp_error_message                  '
// CHECK-NEXT:          var_list(3) = 'model_times                         '
// CHECK-NEXT:          var_list(4) = 'number_of_model_times               '
// CHECK-NEXT:          var_list(5) = 'surface_air_pressure                '
// CHECK-NEXT:        end if
// CHECK-NEXT:      else if (trim(suite_name) .eq. 'temp_suite') then
// CHECK-NEXT:        if (do_input .and. .not. do_output) then
// CHECK-NEXT:          allocate(var_list(10))
// CHECK-NEXT:          var_list(1) = 'array_variable_for_testing          '
// CHECK-NEXT:          var_list(2) = 'coefficients_for_interpolation      '
// CHECK-NEXT:          var_list(3) = 'potential_temperature               '
// CHECK-NEXT:          var_list(4) = 'potential_temperature_at_interface  '
// CHECK-NEXT:          var_list(5) = 'potential_temperature_increment     '
// CHECK-NEXT:          var_list(6) = 'soil_levels                         '
// CHECK-NEXT:          var_list(7) = 'surface_air_pressure                '
// CHECK-NEXT:          var_list(8) = 'temperature_at_diagnostic_levels    '
// CHECK-NEXT:          var_list(9) = 'time_step_for_physics               '
// CHECK-NEXT:          var_list(10) = 'water_vapor_specific_humidity       '
// CHECK-NEXT:        else if (.not. do_input .and. do_output) then
// CHECK-NEXT:          allocate(var_list(10))
// CHECK-NEXT:          var_list(1) = 'array_variable_for_testing          '
// CHECK-NEXT:          var_list(2) = 'ccpp_error_code                     '
// CHECK-NEXT:          var_list(3) = 'ccpp_error_message                  '
// CHECK-NEXT:          var_list(4) = 'coefficients_for_interpolation      '
// CHECK-NEXT:          var_list(5) = 'potential_temperature               '
// CHECK-NEXT:          var_list(6) = 'potential_temperature_at_interface  '
// CHECK-NEXT:          var_list(7) = 'soil_levels                         '
// CHECK-NEXT:          var_list(8) = 'surface_air_pressure                '
// CHECK-NEXT:          var_list(9) = 'temperature_at_diagnostic_levels    '
// CHECK-NEXT:          var_list(10) = 'water_vapor_specific_humidity       '
// CHECK-NEXT:        else
// CHECK-NEXT:          allocate(var_list(12))
// CHECK-NEXT:          var_list(1) = 'array_variable_for_testing          '
// CHECK-NEXT:          var_list(2) = 'ccpp_error_code                     '
// CHECK-NEXT:          var_list(3) = 'ccpp_error_message                  '
// CHECK-NEXT:          var_list(4) = 'coefficients_for_interpolation      '
// CHECK-NEXT:          var_list(5) = 'potential_temperature               '
// CHECK-NEXT:          var_list(6) = 'potential_temperature_at_interface  '
// CHECK-NEXT:          var_list(7) = 'potential_temperature_increment     '
// CHECK-NEXT:          var_list(8) = 'soil_levels                         '
// CHECK-NEXT:          var_list(9) = 'surface_air_pressure                '
// CHECK-NEXT:          var_list(10) = 'temperature_at_diagnostic_levels    '
// CHECK-NEXT:          var_list(11) = 'time_step_for_physics               '
// CHECK-NEXT:          var_list(12) = 'water_vapor_specific_humidity       '
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_physics_suite_variables
// CHECK-NEXT:  end module Ddt_ccpp_cap
// CHECK:       // -----
// CHECK-LABEL: // FILE: ccpp_kinds.F90
// CHECK-LABEL: module ccpp_kinds
// CHECK:         use ISO_FORTRAN_ENV, only: kind_phys => REAL64
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         public :: kind_phys
// CHECK-NEXT:  end module ccpp_kinds
