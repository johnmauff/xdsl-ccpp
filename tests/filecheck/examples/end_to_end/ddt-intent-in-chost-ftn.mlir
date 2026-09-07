// Test chost cap Fortran output for an intent=in DDT argument (Gap 2).
//
// Uses the ddthost make_ddt scheme whose timestep_final entry point has
// vmr (vmr_type, intent=in).  The generated timestep_final chost subroutine
// must:
//   - Declare vmr_vmr_array as intent(in)   (read-only pointer from C++)
//   - Allocate vmr_local%vmr_array and fill it from vmr_vmr_array (copy-in)
//   - Call the suite timestep_final subroutine
//   - NOT write vmr_vmr_array back from vmr_local%vmr_array (no writeback)
//   - NOT explicitly deallocate vmr_local%vmr_array -- vmr_local is a local,
//     non-SAVE derived-type variable, so Fortran deallocates its allocatable
//     component automatically when this subroutine returns; an explicit
//     deallocate immediately before that already-scheduled cleanup risked a
//     real double free (confirmed via a CI runtime failure on the capgen
//     chost example -- see cpp_interop.py's own comment on this fix)
//
// Contrast with the run/physics subroutine where vmr has intent=inout:
//   - vmr_vmr_array declared intent(inout)
//   - writeback IS emitted before dealloc
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites tests/filecheck/fixtures/ddt_intent_in/suite.xml --scheme-files examples/ddthost/scheme/make_ddt.meta --host-files tests/filecheck/fixtures/ddt_intent_in/host_mod.meta,tests/filecheck/fixtures/ddt_intent_in/host_sub.meta,examples/ddthost/scheme/host_ccpp_ddt.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p "generate-meta-cap,generate-meta-kinds,generate-arg-ownership,generate-suite-cap,generate-ccpp-cap{bind_c=true},generate-cpp-cap,generate-kinds,strip-ccpp" -t ftn | python3 -m filecheck %s

// ── run/physics: vmr is intent=inout → writeback present ─────────────────────
// (chost functions are generated in fixed lifecycle order -- register,
// initialize, finalize, run, timestep_initial, timestep_final -- so the
// run subroutine appears before timestep_final's in the real output; task
// #28 Stage 2 moved timestep_final later in that order, which is why this
// block now comes first.)

// The run subroutine declares vmr_vmr_array as intent(inout).

// CHECK-LABEL: // FILE: ddt_in_suite_cap.F90
// CHECK-LABEL: module ddt_in_suite_cap
// CHECK:         use ccpp_kinds
// CHECK-NEXT:    use host_ccpp_ddt, only: ccpp_info_t
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
// CHECK-NEXT:    public :: ddt_in_suite_register
// CHECK-NEXT:    public :: ddt_in_suite_initialize
// CHECK-NEXT:    public :: ddt_in_suite_finalize
// CHECK-NEXT:    public :: ddt_in_suite_init_physics
// CHECK-NEXT:    public :: ddt_in_suite_physics
// CHECK-NEXT:    public :: ddt_in_suite_timestep_init_physics
// CHECK-NEXT:    public :: ddt_in_suite_timestep_final_physics
// CHECK-NEXT:    public :: ddt_in_suite_final_physics
// CHECK:       CONTAINS
// CHECK-LABEL:   subroutine ddt_in_suite_register(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:    end subroutine ddt_in_suite_register
// CHECK-LABEL:   subroutine ddt_in_suite_initialize(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_uninitialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in ddt_in_suite_initialize"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_initialized
// CHECK-NEXT:    end subroutine ddt_in_suite_initialize
// CHECK-LABEL:   subroutine ddt_in_suite_finalize(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in ddt_in_suite_finalize"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_uninitialized
// CHECK-NEXT:    end subroutine ddt_in_suite_finalize
// CHECK-LABEL:   subroutine ddt_in_suite_init_physics(nbox, ccpp_info, vmr, errmsg, errflg)
// CHECK:           integer, intent(in) :: nbox
// CHECK-NEXT:      type(ccpp_info_t), intent(in) :: ccpp_info
// CHECK-NEXT:      type(vmr_type), intent(out) :: vmr
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in ddt_in_suite_init_physics"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call make_ddt_init(nbox=nbox, ccpp_info=ccpp_info, vmr=vmr, errmsg=errmsg, errflg=errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ddt_in_suite_init_physics
// CHECK-LABEL:   subroutine ddt_in_suite_physics(cols, cole, O3, HNO3, vmr, errmsg, errflg)
// CHECK:           integer, intent(in) :: cols
// CHECK-NEXT:      integer, intent(in) :: cole
// CHECK-NEXT:      real(kind=kind_phys), target, intent(in) :: O3(:)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(in) :: HNO3(:)
// CHECK-NEXT:      type(vmr_type), intent(inout) :: vmr
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_in_time_step .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in ddt_in_suite_physics"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call make_ddt_run(cols=cols, cole=cole, O3=O3, HNO3=HNO3, vmr=vmr, errmsg=errmsg,           &
// CHECK-NEXT:          errflg=errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ddt_in_suite_physics
// CHECK-LABEL:   subroutine ddt_in_suite_timestep_init_physics(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      ccpp_suite_state = const_in_time_step
// CHECK-NEXT:    end subroutine ddt_in_suite_timestep_init_physics
// CHECK-LABEL:   subroutine ddt_in_suite_timestep_final_physics(ncols, vmr, errmsg, errflg)
// CHECK:           integer, intent(in) :: ncols
// CHECK-NEXT:      type(vmr_type), intent(in) :: vmr
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call make_ddt_timestep_final(ncols=ncols, vmr=vmr, errmsg=errmsg, errflg=errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_initialized
// CHECK-NEXT:    end subroutine ddt_in_suite_timestep_final_physics
// CHECK-LABEL:   subroutine ddt_in_suite_final_physics(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in ddt_in_suite_final_physics"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ddt_in_suite_final_physics
// CHECK-NEXT:  end module ddt_in_suite_cap
// CHECK:       // -----
// CHECK-LABEL: // FILE: DdtIn_ccpp_cap.F90
// CHECK-LABEL: module DdtIn_ccpp_cap
// CHECK:         use ccpp_kinds
// CHECK-NEXT:    use iso_c_binding
// CHECK-NEXT:    use ccpp_constituent_prop_mod, only: ccpp_constituent_prop_ptr_t
// CHECK-NEXT:    use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t
// CHECK-NEXT:    use ddt_in_host_mod, only: vmr
// CHECK-NEXT:    use ddt_in_suite_cap, only: ddt_in_suite_final_physics
// CHECK-NEXT:    use ddt_in_suite_cap, only: ddt_in_suite_finalize
// CHECK-NEXT:    use ddt_in_suite_cap, only: ddt_in_suite_init_physics
// CHECK-NEXT:    use ddt_in_suite_cap, only: ddt_in_suite_initialize
// CHECK-NEXT:    use ddt_in_suite_cap, only: ddt_in_suite_physics
// CHECK-NEXT:    use ddt_in_suite_cap, only: ddt_in_suite_register
// CHECK-NEXT:    use ddt_in_suite_cap, only: ddt_in_suite_timestep_final_physics
// CHECK-NEXT:    use ddt_in_suite_cap, only: ddt_in_suite_timestep_init_physics
// CHECK-NEXT:    use host_ccpp_ddt, only: ccpp_info_t
// CHECK-NEXT:    use make_ddt, only: vmr_type
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         character(len=12), parameter :: str_ddt_in_suite = 'ddt_in_suite'
// CHECK-NEXT:    character(len=7), parameter :: str_physics = 'physics'
// CHECK-NEXT:    type(ccpp_constituent_properties_t), target, allocatable :: lc_all_constituents(:)
// CHECK-NEXT:    real(kind=kind_phys), target, allocatable :: lc_constituent_array(:, :, :)
// CHECK-NEXT:    real(kind=kind_phys), target, allocatable :: lc_const_tend(:, :, :)
// CHECK-NEXT:    type(ccpp_constituent_prop_ptr_t), target, allocatable :: lc_const_props(:)
// CHECK-NEXT:    real(kind=kind_phys), allocatable :: lc_O3(:)
// CHECK-NEXT:    real(kind=kind_phys), allocatable :: lc_HNO3(:)
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
// CHECK-NEXT:    public :: DdtIn_ccpp_is_scheme_constituent
// CHECK-NEXT:    public :: DdtIn_ccpp_deallocate_dynamic_constituents
// CHECK-NEXT:    public :: DdtIn_ccpp_register_constituents
// CHECK-NEXT:    public :: DdtIn_ccpp_number_constituents
// CHECK-NEXT:    public :: DdtIn_ccpp_initialize_constituents
// CHECK-NEXT:    public :: DdtIn_constituents_array
// CHECK-NEXT:    public :: DdtIn_const_get_index
// CHECK-NEXT:    public :: DdtIn_model_const_properties
// CHECK:       CONTAINS
// CHECK-LABEL:   subroutine ccpp_register(suite_name, errmsg, errflg) BIND(C, name='ccpp_register')
// CHECK:           character(kind=c_char, len=1), intent(in) :: suite_name(*)
// CHECK-NEXT:      character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK-NEXT:      integer(c_int), intent(out) :: errflg
// CHECK-NEXT:      integer :: ccpp_c2f_i
// CHECK-NEXT:      character(len=512) :: suite_name_f
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK:           suite_name_f = ' '
// CHECK-NEXT:      do ccpp_c2f_i = 1, len(suite_name_f)
// CHECK-NEXT:        if (suite_name(ccpp_c2f_i) == c_null_char) exit
// CHECK-NEXT:        suite_name_f(ccpp_c2f_i:ccpp_c2f_i) = suite_name(ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg_f = ' '
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      if (trim(suite_name_f) .eq. 'ddt_in_suite') then
// CHECK-NEXT:        call ddt_in_suite_register(errflg, errmsg_f)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg_f, '(3a)') "No suite named ", trim(suite_name_f), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      do ccpp_c2f_i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(ccpp_c2f_i) = errmsg_f(ccpp_c2f_i:ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine ccpp_register
// CHECK-LABEL:   subroutine ccpp_init(suite_name, errmsg, errflg) BIND(C, name='ccpp_init')
// CHECK:           character(kind=c_char, len=1), intent(in) :: suite_name(*)
// CHECK-NEXT:      character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK-NEXT:      integer(c_int), intent(out) :: errflg
// CHECK-NEXT:      integer :: ccpp_c2f_i
// CHECK-NEXT:      character(len=512) :: suite_name_f
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK:           suite_name_f = ' '
// CHECK-NEXT:      do ccpp_c2f_i = 1, len(suite_name_f)
// CHECK-NEXT:        if (suite_name(ccpp_c2f_i) == c_null_char) exit
// CHECK-NEXT:        suite_name_f(ccpp_c2f_i:ccpp_c2f_i) = suite_name(ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg_f = ' '
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      if (trim(suite_name_f) .eq. 'ddt_in_suite') then
// CHECK-NEXT:        call ddt_in_suite_initialize(errflg, errmsg_f)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg_f, '(3a)') "No suite named ", trim(suite_name_f), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      do ccpp_c2f_i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(ccpp_c2f_i) = errmsg_f(ccpp_c2f_i:ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine ccpp_init
// CHECK-LABEL:   subroutine ccpp_final(suite_name, errmsg, errflg) BIND(C, name='ccpp_final')
// CHECK:           character(kind=c_char, len=1), intent(in) :: suite_name(*)
// CHECK-NEXT:      character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK-NEXT:      integer(c_int), intent(out) :: errflg
// CHECK-NEXT:      integer :: ccpp_c2f_i
// CHECK-NEXT:      character(len=512) :: suite_name_f
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK:           suite_name_f = ' '
// CHECK-NEXT:      do ccpp_c2f_i = 1, len(suite_name_f)
// CHECK-NEXT:        if (suite_name(ccpp_c2f_i) == c_null_char) exit
// CHECK-NEXT:        suite_name_f(ccpp_c2f_i:ccpp_c2f_i) = suite_name(ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg_f = ' '
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      if (trim(suite_name_f) .eq. 'ddt_in_suite') then
// CHECK-NEXT:        call ddt_in_suite_finalize(errflg, errmsg_f)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg_f, '(3a)') "No suite named ", trim(suite_name_f), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      do ccpp_c2f_i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(ccpp_c2f_i) = errmsg_f(ccpp_c2f_i:ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine ccpp_final
// CHECK-LABEL:   subroutine ccpp_physics_run(suite_name, suite_part, cols, cole, vmr, errmsg, errflg) BIND(C,    &
// CHECK:           name='ccpp_physics_run')
// CHECK-NEXT:      character(kind=c_char, len=1), intent(in) :: suite_name(*)
// CHECK-NEXT:      character(kind=c_char, len=1), intent(in) :: suite_part(*)
// CHECK-NEXT:      integer(c_int), value, intent(in) :: cols
// CHECK-NEXT:      integer(c_int), value, intent(in) :: cole
// CHECK-NEXT:      type(c_ptr), intent(inout) :: vmr
// CHECK-NEXT:      character(kind=c_char, len=1), intent(inout) :: errmsg(*)
// CHECK-NEXT:      integer(c_int), intent(inout) :: errflg
// CHECK-NEXT:      integer :: ccpp_c2f_i
// CHECK-NEXT:      character(len=512) :: suite_name_f
// CHECK-NEXT:      character(len=512) :: suite_part_f
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK:           suite_name_f = ' '
// CHECK-NEXT:      do ccpp_c2f_i = 1, len(suite_name_f)
// CHECK-NEXT:        if (suite_name(ccpp_c2f_i) == c_null_char) exit
// CHECK-NEXT:        suite_name_f(ccpp_c2f_i:ccpp_c2f_i) = suite_name(ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      suite_part_f = ' '
// CHECK-NEXT:      do ccpp_c2f_i = 1, len(suite_part_f)
// CHECK-NEXT:        if (suite_part(ccpp_c2f_i) == c_null_char) exit
// CHECK-NEXT:        suite_part_f(ccpp_c2f_i:ccpp_c2f_i) = suite_part(ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg_f = ' '
// CHECK-NEXT:      do ccpp_c2f_i = 1, len(errmsg_f)
// CHECK-NEXT:        if (errmsg(ccpp_c2f_i) == c_null_char) exit
// CHECK-NEXT:        errmsg_f(ccpp_c2f_i:ccpp_c2f_i) = errmsg(ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      if (trim(suite_name_f) .eq. 'ddt_in_suite') then
// CHECK-NEXT:        if (trim(suite_part_f) .eq. 'physics') then
// CHECK-NEXT:          call ddt_in_suite_physics(cols, cole, lc_O3(cols:cole), lc_HNO3(cols:cole), vmr,          &
// CHECK-NEXT:            errmsg_f, errflg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg_f, '(3a)') "No suite part named ", trim(suite_part_f),                       &
// CHECK-NEXT:            " found in suite ddt_in_suite"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg_f, '(3a)') "No suite named ", trim(suite_name_f), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      do ccpp_c2f_i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(ccpp_c2f_i) = errmsg_f(ccpp_c2f_i:ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine ccpp_physics_run
// CHECK-LABEL:   subroutine ccpp_physics_timestep_init(suite_name, suite_part, col_start, col_end, errmsg,       &
// CHECK:           errflg) BIND(C, name='ccpp_physics_timestep_init')
// CHECK-NEXT:      character(kind=c_char, len=1), intent(in) :: suite_name(*)
// CHECK-NEXT:      character(kind=c_char, len=1), intent(in) :: suite_part(*)
// CHECK-NEXT:      integer(c_int), value, intent(in) :: col_start
// CHECK-NEXT:      integer(c_int), value, intent(in) :: col_end
// CHECK-NEXT:      character(kind=c_char, len=1), intent(inout) :: errmsg(*)
// CHECK-NEXT:      integer(c_int), intent(inout) :: errflg
// CHECK-NEXT:      integer :: ccpp_c2f_i
// CHECK-NEXT:      character(len=512) :: suite_name_f
// CHECK-NEXT:      character(len=512) :: suite_part_f
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK:           suite_name_f = ' '
// CHECK-NEXT:      do ccpp_c2f_i = 1, len(suite_name_f)
// CHECK-NEXT:        if (suite_name(ccpp_c2f_i) == c_null_char) exit
// CHECK-NEXT:        suite_name_f(ccpp_c2f_i:ccpp_c2f_i) = suite_name(ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      suite_part_f = ' '
// CHECK-NEXT:      do ccpp_c2f_i = 1, len(suite_part_f)
// CHECK-NEXT:        if (suite_part(ccpp_c2f_i) == c_null_char) exit
// CHECK-NEXT:        suite_part_f(ccpp_c2f_i:ccpp_c2f_i) = suite_part(ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg_f = ' '
// CHECK-NEXT:      do ccpp_c2f_i = 1, len(errmsg_f)
// CHECK-NEXT:        if (errmsg(ccpp_c2f_i) == c_null_char) exit
// CHECK-NEXT:        errmsg_f(ccpp_c2f_i:ccpp_c2f_i) = errmsg(ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      if (trim(suite_name_f) .eq. 'ddt_in_suite') then
// CHECK-NEXT:        if (trim(suite_part_f) .eq. 'physics') then
// CHECK-NEXT:          call ddt_in_suite_timestep_init_physics(errflg, errmsg_f)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg_f, '(3a)') "No suite part named ", trim(suite_part_f),                       &
// CHECK-NEXT:            " found in suite ddt_in_suite"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg_f, '(3a)') "No suite named ", trim(suite_name_f), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      do ccpp_c2f_i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(ccpp_c2f_i) = errmsg_f(ccpp_c2f_i:ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine ccpp_physics_timestep_init
// CHECK-LABEL:   subroutine ccpp_physics_timestep_final(suite_name, suite_part, col_start, col_end, ncols, vmr,  &
// CHECK:           errmsg, errflg) BIND(C, name='ccpp_physics_timestep_final')
// CHECK-NEXT:      character(kind=c_char, len=1), intent(in) :: suite_name(*)
// CHECK-NEXT:      character(kind=c_char, len=1), intent(in) :: suite_part(*)
// CHECK-NEXT:      integer(c_int), value, intent(in) :: col_start
// CHECK-NEXT:      integer(c_int), value, intent(in) :: col_end
// CHECK-NEXT:      integer(c_int), value, intent(in) :: ncols
// CHECK-NEXT:      type(c_ptr), value, intent(in) :: vmr
// CHECK-NEXT:      character(kind=c_char, len=1), intent(inout) :: errmsg(*)
// CHECK-NEXT:      integer(c_int), intent(inout) :: errflg
// CHECK-NEXT:      integer :: ccpp_c2f_i
// CHECK-NEXT:      character(len=512) :: suite_name_f
// CHECK-NEXT:      character(len=512) :: suite_part_f
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK:           suite_name_f = ' '
// CHECK-NEXT:      do ccpp_c2f_i = 1, len(suite_name_f)
// CHECK-NEXT:        if (suite_name(ccpp_c2f_i) == c_null_char) exit
// CHECK-NEXT:        suite_name_f(ccpp_c2f_i:ccpp_c2f_i) = suite_name(ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      suite_part_f = ' '
// CHECK-NEXT:      do ccpp_c2f_i = 1, len(suite_part_f)
// CHECK-NEXT:        if (suite_part(ccpp_c2f_i) == c_null_char) exit
// CHECK-NEXT:        suite_part_f(ccpp_c2f_i:ccpp_c2f_i) = suite_part(ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg_f = ' '
// CHECK-NEXT:      do ccpp_c2f_i = 1, len(errmsg_f)
// CHECK-NEXT:        if (errmsg(ccpp_c2f_i) == c_null_char) exit
// CHECK-NEXT:        errmsg_f(ccpp_c2f_i:ccpp_c2f_i) = errmsg(ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      if (trim(suite_name_f) .eq. 'ddt_in_suite') then
// CHECK-NEXT:        if (trim(suite_part_f) .eq. 'physics') then
// CHECK-NEXT:          call ddt_in_suite_timestep_final_physics(ncols, vmr, errmsg_f, errflg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg_f, '(3a)') "No suite part named ", trim(suite_part_f),                       &
// CHECK-NEXT:            " found in suite ddt_in_suite"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg_f, '(3a)') "No suite named ", trim(suite_name_f), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      do ccpp_c2f_i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(ccpp_c2f_i) = errmsg_f(ccpp_c2f_i:ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine ccpp_physics_timestep_final
// CHECK-LABEL:   subroutine ccpp_physics_init(suite_name, suite_part, col_start, col_end, nbox, ccpp_info,       &
// CHECK:           errmsg, errflg) BIND(C, name='ccpp_physics_init')
// CHECK-NEXT:      character(kind=c_char, len=1), intent(in) :: suite_name(*)
// CHECK-NEXT:      character(kind=c_char, len=1), intent(in) :: suite_part(*)
// CHECK-NEXT:      integer(c_int), value, intent(in) :: col_start
// CHECK-NEXT:      integer(c_int), value, intent(in) :: col_end
// CHECK-NEXT:      integer(c_int), value, intent(in) :: nbox
// CHECK-NEXT:      type(c_ptr), value, intent(in) :: ccpp_info
// CHECK-NEXT:      character(kind=c_char, len=1), intent(inout) :: errmsg(*)
// CHECK-NEXT:      integer(c_int), intent(inout) :: errflg
// CHECK-NEXT:      integer :: ccpp_c2f_i
// CHECK-NEXT:      character(len=512) :: suite_name_f
// CHECK-NEXT:      character(len=512) :: suite_part_f
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK:           suite_name_f = ' '
// CHECK-NEXT:      do ccpp_c2f_i = 1, len(suite_name_f)
// CHECK-NEXT:        if (suite_name(ccpp_c2f_i) == c_null_char) exit
// CHECK-NEXT:        suite_name_f(ccpp_c2f_i:ccpp_c2f_i) = suite_name(ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      suite_part_f = ' '
// CHECK-NEXT:      do ccpp_c2f_i = 1, len(suite_part_f)
// CHECK-NEXT:        if (suite_part(ccpp_c2f_i) == c_null_char) exit
// CHECK-NEXT:        suite_part_f(ccpp_c2f_i:ccpp_c2f_i) = suite_part(ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg_f = ' '
// CHECK-NEXT:      do ccpp_c2f_i = 1, len(errmsg_f)
// CHECK-NEXT:        if (errmsg(ccpp_c2f_i) == c_null_char) exit
// CHECK-NEXT:        errmsg_f(ccpp_c2f_i:ccpp_c2f_i) = errmsg(ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      if (trim(suite_name_f) .eq. 'ddt_in_suite') then
// CHECK-NEXT:        if (trim(suite_part_f) .eq. 'physics') then
// CHECK-NEXT:          call ddt_in_suite_init_physics(nbox, ccpp_info, vmr, errmsg_f, errflg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg_f, '(3a)') "No suite part named ", trim(suite_part_f),                       &
// CHECK-NEXT:            " found in suite ddt_in_suite"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg_f, '(3a)') "No suite named ", trim(suite_name_f), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      do ccpp_c2f_i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(ccpp_c2f_i) = errmsg_f(ccpp_c2f_i:ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine ccpp_physics_init
// CHECK-LABEL:   subroutine ccpp_physics_final(suite_name, suite_part, col_start, col_end, errmsg,               &
// CHECK:           errflg) BIND(C, name='ccpp_physics_final')
// CHECK-NEXT:      character(kind=c_char, len=1), intent(in) :: suite_name(*)
// CHECK-NEXT:      character(kind=c_char, len=1), intent(in) :: suite_part(*)
// CHECK-NEXT:      integer(c_int), value, intent(in) :: col_start
// CHECK-NEXT:      integer(c_int), value, intent(in) :: col_end
// CHECK-NEXT:      character(kind=c_char, len=1), intent(inout) :: errmsg(*)
// CHECK-NEXT:      integer(c_int), intent(inout) :: errflg
// CHECK-NEXT:      integer :: ccpp_c2f_i
// CHECK-NEXT:      character(len=512) :: suite_name_f
// CHECK-NEXT:      character(len=512) :: suite_part_f
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK:           suite_name_f = ' '
// CHECK-NEXT:      do ccpp_c2f_i = 1, len(suite_name_f)
// CHECK-NEXT:        if (suite_name(ccpp_c2f_i) == c_null_char) exit
// CHECK-NEXT:        suite_name_f(ccpp_c2f_i:ccpp_c2f_i) = suite_name(ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      suite_part_f = ' '
// CHECK-NEXT:      do ccpp_c2f_i = 1, len(suite_part_f)
// CHECK-NEXT:        if (suite_part(ccpp_c2f_i) == c_null_char) exit
// CHECK-NEXT:        suite_part_f(ccpp_c2f_i:ccpp_c2f_i) = suite_part(ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg_f = ' '
// CHECK-NEXT:      do ccpp_c2f_i = 1, len(errmsg_f)
// CHECK-NEXT:        if (errmsg(ccpp_c2f_i) == c_null_char) exit
// CHECK-NEXT:        errmsg_f(ccpp_c2f_i:ccpp_c2f_i) = errmsg(ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      if (trim(suite_name_f) .eq. 'ddt_in_suite') then
// CHECK-NEXT:        if (trim(suite_part_f) .eq. 'physics') then
// CHECK-NEXT:          call ddt_in_suite_final_physics(errflg, errmsg_f)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg_f, '(3a)') "No suite part named ", trim(suite_part_f),                       &
// CHECK-NEXT:            " found in suite ddt_in_suite"
// CHECK-NEXT:          errflg = 1
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg_f, '(3a)') "No suite named ", trim(suite_name_f), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      do ccpp_c2f_i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(ccpp_c2f_i) = errmsg_f(ccpp_c2f_i:ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine ccpp_physics_final
// CHECK-LABEL:   subroutine ccpp_physics_suite_list(suites)
// CHECK:           character(len=*), allocatable, intent(out) :: suites(:)
// CHECK:           allocate(suites(1))
// CHECK-NEXT:      suites(1) = str_ddt_in_suite
// CHECK-NEXT:    end subroutine ccpp_physics_suite_list
// CHECK-LABEL:   subroutine ccpp_physics_suite_part_list(suite_name, part_list, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), allocatable, intent(out) :: part_list(:)
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'ddt_in_suite') then
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
// CHECK-NEXT:      if (trim(suite_name) .eq. 'ddt_in_suite') then
// CHECK-NEXT:        if (do_input .and. .not. do_output) then
// CHECK-NEXT:          allocate(var_list(5))
// CHECK-NEXT:          var_list(1) = 'horizontal_dimension                '
// CHECK-NEXT:          var_list(2) = 'host_standard_ccpp_type             '
// CHECK-NEXT:          var_list(3) = 'nitric_acid                         '
// CHECK-NEXT:          var_list(4) = 'ozone                               '
// CHECK-NEXT:          var_list(5) = 'volume_mixing_ratio_ddt             '
// CHECK-NEXT:        else if (.not. do_input .and. do_output) then
// CHECK-NEXT:          allocate(var_list(3))
// CHECK-NEXT:          var_list(1) = 'ccpp_error_code                     '
// CHECK-NEXT:          var_list(2) = 'ccpp_error_message                  '
// CHECK-NEXT:          var_list(3) = 'volume_mixing_ratio_ddt             '
// CHECK-NEXT:        else
// CHECK-NEXT:          allocate(var_list(7))
// CHECK-NEXT:          var_list(1) = 'ccpp_error_code                     '
// CHECK-NEXT:          var_list(2) = 'ccpp_error_message                  '
// CHECK-NEXT:          var_list(3) = 'horizontal_dimension                '
// CHECK-NEXT:          var_list(4) = 'host_standard_ccpp_type             '
// CHECK-NEXT:          var_list(5) = 'nitric_acid                         '
// CHECK-NEXT:          var_list(6) = 'ozone                               '
// CHECK-NEXT:          var_list(7) = 'volume_mixing_ratio_ddt             '
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_physics_suite_variables
// CHECK-LABEL:   subroutine DdtIn_ccpp_is_scheme_constituent(std_name, is_const, errflg, errmsg)
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
// CHECK-NEXT:    end subroutine DdtIn_ccpp_is_scheme_constituent
// CHECK-LABEL:   subroutine DdtIn_ccpp_deallocate_dynamic_constituents()
// CHECK:           if (allocated(lc_all_constituents)) deallocate(lc_all_constituents)
// CHECK-NEXT:      if (allocated(lc_const_props)) deallocate(lc_const_props)
// CHECK-NEXT:      if (allocated(lc_constituent_array)) deallocate(lc_constituent_array)
// CHECK-NEXT:      if (allocated(lc_const_tend)) deallocate(lc_const_tend)
// CHECK-NEXT:      if (allocated(lc_O3)) deallocate(lc_O3)
// CHECK-NEXT:      if (allocated(lc_HNO3)) deallocate(lc_HNO3)
// CHECK-NEXT:    end subroutine DdtIn_ccpp_deallocate_dynamic_constituents
// CHECK-LABEL:   subroutine DdtIn_ccpp_register_constituents(host_constituents, errmsg, errcode)
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
// CHECK-NEXT:    end subroutine DdtIn_ccpp_register_constituents
// CHECK-LABEL:   subroutine DdtIn_ccpp_number_constituents(num_advected, errmsg, errcode, advected)
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
// CHECK-NEXT:    end subroutine DdtIn_ccpp_number_constituents
// CHECK-LABEL:   subroutine DdtIn_ccpp_initialize_constituents(ncols, pver, errflg, errmsg)
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
// CHECK-NEXT:      if (allocated(lc_O3)) deallocate(lc_O3)
// CHECK-NEXT:      allocate(lc_O3(ncols))
// CHECK-NEXT:      lc_O3 = 0.0_kind_phys
// CHECK-NEXT:      if (allocated(lc_HNO3)) deallocate(lc_HNO3)
// CHECK-NEXT:      allocate(lc_HNO3(ncols))
// CHECK-NEXT:      lc_HNO3 = 0.0_kind_phys
// CHECK-NEXT:    end subroutine DdtIn_ccpp_initialize_constituents
// CHECK-NEXT:    function DdtIn_constituents_array() result(ptr)
// CHECK-NEXT:      real(kind=kind_phys), pointer :: ptr(:, :, :)
// CHECK-NEXT:      ptr => lc_constituent_array
// CHECK-NEXT:    end function DdtIn_constituents_array
// CHECK-LABEL:   subroutine DdtIn_const_get_index(std_name, index, errflg, errmsg)
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
// CHECK-NEXT:    end subroutine DdtIn_const_get_index
// CHECK-NEXT:    function DdtIn_model_const_properties() result(ptr)
// CHECK-NEXT:      type(ccpp_constituent_prop_ptr_t), pointer :: ptr(:)
// CHECK-NEXT:      ptr => lc_const_props
// CHECK-NEXT:    end function DdtIn_model_const_properties
// CHECK-NEXT:  end module DdtIn_ccpp_cap
// CHECK:       // -----
// CHECK-LABEL: // FILE: DdtIn_ccpp_chost_cap.F90
// CHECK-LABEL: module DdtIn_ccpp_chost_cap
// CHECK:         use ccpp_kinds, only: kind_phys
// CHECK-NEXT:    use iso_c_binding
// CHECK-NEXT:    use host_ccpp_ddt, only: ccpp_info_t
// CHECK-NEXT:    use make_ddt, only: vmr_type
// CHECK-NEXT:    use ddt_in_suite_cap, only: ddt_in_suite_register
// CHECK-NEXT:    use ddt_in_suite_cap, only: ddt_in_suite_initialize
// CHECK-NEXT:    use ddt_in_suite_cap, only: ddt_in_suite_finalize
// CHECK-NEXT:    use ddt_in_suite_cap, only: ddt_in_suite_physics
// CHECK-NEXT:    use ddt_in_suite_cap, only: ddt_in_suite_timestep_init_physics
// CHECK-NEXT:    use ddt_in_suite_cap, only: ddt_in_suite_timestep_final_physics
// CHECK-NEXT:    use ddt_in_suite_cap, only: ddt_in_suite_init_physics
// CHECK-NEXT:    use ddt_in_suite_cap, only: ddt_in_suite_final_physics
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         public :: DdtIn_chost_physics_register
// CHECK-NEXT:    public :: DdtIn_chost_physics_initialize
// CHECK-NEXT:    public :: DdtIn_chost_physics_finalize
// CHECK-NEXT:    public :: DdtIn_chost_physics_run
// CHECK-NEXT:    public :: DdtIn_chost_physics_timestep_initial
// CHECK-NEXT:    public :: DdtIn_chost_physics_timestep_final
// CHECK-NEXT:    public :: DdtIn_chost_physics_physics_initial
// CHECK-NEXT:    public :: DdtIn_chost_physics_physics_final
// CHECK:       contains
// CHECK-LABEL:   subroutine DdtIn_chost_physics_register(errmsg, errflg) &
// CHECK:             bind(C, name='DdtIn_chost_physics_register')
// CHECK-NEXT:      character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK-NEXT:      integer(c_int),               intent(out) :: errflg
// CHECK-NEXT:      integer :: i
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK:           errmsg_f = ' '
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      call ddt_in_suite_register(errflg, errmsg_f)
// CHECK-NEXT:      do i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(i) = errmsg_f(i:i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine DdtIn_chost_physics_register
// CHECK-LABEL:   subroutine DdtIn_chost_physics_initialize(errmsg, errflg) &
// CHECK:             bind(C, name='DdtIn_chost_physics_initialize')
// CHECK-NEXT:      character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK-NEXT:      integer(c_int),               intent(out) :: errflg
// CHECK-NEXT:      integer :: i
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK:           errmsg_f = ' '
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      call ddt_in_suite_initialize(errflg, errmsg_f)
// CHECK-NEXT:      do i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(i) = errmsg_f(i:i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine DdtIn_chost_physics_initialize
// CHECK-LABEL:   subroutine DdtIn_chost_physics_finalize(errmsg, errflg) &
// CHECK:             bind(C, name='DdtIn_chost_physics_finalize')
// CHECK-NEXT:      character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK-NEXT:      integer(c_int),               intent(out) :: errflg
// CHECK-NEXT:      integer :: i
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK:           errmsg_f = ' '
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      call ddt_in_suite_finalize(errflg, errmsg_f)
// CHECK-NEXT:      do i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(i) = errmsg_f(i:i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine DdtIn_chost_physics_finalize
// CHECK-LABEL:   subroutine DdtIn_chost_physics_run( &
// CHECK:             ncols, vmr_nvmr, col_start, col_end, O3, HNO3, vmr_vmr_array, errmsg, errflg) &
// CHECK-NEXT:        bind(C, name='DdtIn_chost_physics_run')
// CHECK-NEXT:      integer(c_int), value, intent(in) :: ncols
// CHECK-NEXT:      integer(c_int), value, intent(in) :: vmr_nvmr
// CHECK-NEXT:      integer(c_int), value, intent(in) :: col_start
// CHECK-NEXT:      integer(c_int), value, intent(in) :: col_end
// CHECK-NEXT:      real(c_double), target, intent(in) :: O3(ncols)
// CHECK-NEXT:      real(c_double), target, intent(in) :: HNO3(ncols)
// CHECK-NEXT:      real(c_double), target, intent(inout) :: vmr_vmr_array(ncols, vmr_nvmr)
// CHECK-NEXT:      character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK-NEXT:      integer(c_int),               intent(out) :: errflg
// CHECK-NEXT:      integer :: i
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK-NEXT:      type(vmr_type) :: vmr_local
// CHECK:           errmsg_f = ' '
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      vmr_local%nvmr = vmr_nvmr
// CHECK-NEXT:      allocate(vmr_local%vmr_array(ncols, vmr_nvmr))
// CHECK-NEXT:      vmr_local%vmr_array = real(vmr_vmr_array, kind_phys)
// CHECK-NEXT:      call ddt_in_suite_physics( &
// CHECK-NEXT:          col_start, col_end, O3, HNO3, vmr_local, errmsg_f, errflg)
// CHECK-NEXT:      vmr_vmr_array = real(vmr_local%vmr_array, c_double)
// CHECK-NEXT:      do i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(i) = errmsg_f(i:i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine DdtIn_chost_physics_run
// CHECK-LABEL:   subroutine DdtIn_chost_physics_timestep_initial(errmsg, errflg) &
// CHECK:             bind(C, name='DdtIn_chost_physics_timestep_initial')
// CHECK-NEXT:      character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK-NEXT:      integer(c_int),               intent(out) :: errflg
// CHECK-NEXT:      integer :: i
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK:           errmsg_f = ' '
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      call ddt_in_suite_timestep_init_physics(errflg, errmsg_f)
// CHECK-NEXT:      do i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(i) = errmsg_f(i:i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine DdtIn_chost_physics_timestep_initial
// CHECK-LABEL:   subroutine DdtIn_chost_physics_timestep_final( &
// CHECK:             ncols, vmr_nvmr, vmr_vmr_array, errmsg, errflg) &
// CHECK-NEXT:        bind(C, name='DdtIn_chost_physics_timestep_final')
// CHECK-NEXT:      integer(c_int), value, intent(in) :: ncols
// CHECK-NEXT:      integer(c_int), value, intent(in) :: vmr_nvmr
// CHECK-NEXT:      real(c_double), target, intent(in) :: vmr_vmr_array(ncols, vmr_nvmr)
// CHECK-NEXT:      character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK-NEXT:      integer(c_int),               intent(out) :: errflg
// CHECK-NEXT:      integer :: i
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK-NEXT:      type(vmr_type) :: vmr_local
// CHECK:           errmsg_f = ' '
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      vmr_local%nvmr = vmr_nvmr
// CHECK-NEXT:      allocate(vmr_local%vmr_array(ncols, vmr_nvmr))
// CHECK-NEXT:      vmr_local%vmr_array = real(vmr_vmr_array, kind_phys)
// CHECK-NEXT:      call ddt_in_suite_timestep_final_physics(ncols, vmr_local, errmsg_f, errflg)
// CHECK-NEXT:      do i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(i) = errmsg_f(i:i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine DdtIn_chost_physics_timestep_final
// CHECK-LABEL:   subroutine DdtIn_chost_physics_physics_initial( &
// CHECK:             ncols, vmr_nvmr, ccpp_info_col_start, ccpp_info_col_end, ccpp_info_errflg,  &
// CHECK-NEXT:        vmr_vmr_array, errmsg, errflg) &
// CHECK-NEXT:        bind(C, name='DdtIn_chost_physics_physics_initial')
// CHECK-NEXT:      integer(c_int), value, intent(in) :: ncols
// CHECK-NEXT:      integer(c_int), value, intent(in) :: vmr_nvmr
// CHECK-NEXT:      integer(c_int), value, intent(in) :: ccpp_info_col_start
// CHECK-NEXT:      integer(c_int), value, intent(in) :: ccpp_info_col_end
// CHECK-NEXT:      integer(c_int), value, intent(in) :: ccpp_info_errflg
// CHECK-NEXT:      real(c_double), target, intent(out) :: vmr_vmr_array(ncols, vmr_nvmr)
// CHECK-NEXT:      character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK-NEXT:      integer(c_int),               intent(out) :: errflg
// CHECK-NEXT:      integer :: i
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK-NEXT:      type(ccpp_info_t) :: ccpp_info_local
// CHECK-NEXT:      type(vmr_type) :: vmr_local
// CHECK:           errmsg_f = ' '
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      ccpp_info_local%errmsg = ' '
// CHECK-NEXT:      ccpp_info_local%col_start = ccpp_info_col_start
// CHECK-NEXT:      ccpp_info_local%col_end = ccpp_info_col_end
// CHECK-NEXT:      ccpp_info_local%errflg = ccpp_info_errflg
// CHECK-NEXT:      vmr_local%nvmr = vmr_nvmr
// CHECK-NEXT:      call ddt_in_suite_init_physics( &
// CHECK-NEXT:          ncols, ccpp_info_local, vmr_local, errmsg_f, errflg)
// CHECK-NEXT:      vmr_vmr_array = real(vmr_local%vmr_array, c_double)
// CHECK-NEXT:      do i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(i) = errmsg_f(i:i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine DdtIn_chost_physics_physics_initial
// CHECK-LABEL:   subroutine DdtIn_chost_physics_physics_final(errmsg, errflg) &
// CHECK:             bind(C, name='DdtIn_chost_physics_physics_final')
// CHECK-NEXT:      character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK-NEXT:      integer(c_int),               intent(out) :: errflg
// CHECK-NEXT:      integer :: i
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK:           errmsg_f = ' '
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      call ddt_in_suite_final_physics(errflg, errmsg_f)
// CHECK-NEXT:      do i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(i) = errmsg_f(i:i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine DdtIn_chost_physics_physics_final
// CHECK:       end module DdtIn_ccpp_chost_cap
// CHECK:       // -----
// CHECK-LABEL: // FILE: ccpp_kinds.F90
// CHECK-LABEL: module ccpp_kinds
// CHECK:         use ISO_FORTRAN_ENV, only: kind_phys => REAL64
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         public :: kind_phys
// CHECK-NEXT:  end module ccpp_kinds
