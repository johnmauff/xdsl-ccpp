// Test chost cap Fortran output for the tinyddt example with two DDT args.
// Verifies that both tiny_state_t and tiny_tend_t are each expanded into
// individual scalar/array BIND(C) args in the generated chost subroutine.
//
// Canonical arg ordering: ncol (is_ncol) → state_nz, tend_nz (is_nz) → others → errmsg → errflg
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/tinyddt/tinyddt_suite.xml --scheme-files examples/tinyddt/tinyddt.meta --host-files examples/tinyddt/host_cpp/tinyddt_host_mod.meta,examples/tinyddt/host_cpp/tinyddt_host_sub.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p "generate-meta-cap,generate-meta-kinds,generate-arg-ownership,generate-suite-cap,generate-ccpp-cap{bind_c=true},generate-cpp-cap,generate-kinds,strip-ccpp" -t ftn | python3 -m filecheck %s

// Module header: uses both DDT types from tinyddt.

// CHECK-LABEL: // FILE: tinyddt_suite_cap.F90
// CHECK-LABEL: module tinyddt_suite_cap
// CHECK:         use ccpp_kinds
// CHECK-NEXT:    use tinyddt, only: tiny_state_t
// CHECK-NEXT:    use tinyddt, only: tiny_tend_t
// CHECK-NEXT:    use tinyddt, only: tinyddt_run
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         character(len=16) :: ccpp_suite_state = 'uninitialized'
// CHECK-NEXT:    character(len=16), parameter :: const_in_time_step = 'in_time_step'
// CHECK-NEXT:    character(len=16), parameter :: const_initialized = 'initialized'
// CHECK-NEXT:    character(len=16), parameter :: const_uninitialized = 'uninitialized'
// CHECK-NEXT:    public :: tinyddt_suite_register
// CHECK-NEXT:    public :: tinyddt_suite_initialize
// CHECK-NEXT:    public :: tinyddt_suite_finalize
// CHECK-NEXT:    public :: tinyddt_suite_init_physics
// CHECK-NEXT:    public :: tinyddt_suite_physics
// CHECK-NEXT:    public :: tinyddt_suite_timestep_init_physics
// CHECK-NEXT:    public :: tinyddt_suite_timestep_final_physics
// CHECK-NEXT:    public :: tinyddt_suite_final_physics
// CHECK:       CONTAINS
// CHECK-LABEL:   subroutine tinyddt_suite_register(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:    end subroutine tinyddt_suite_register
// CHECK-LABEL:   subroutine tinyddt_suite_initialize(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_uninitialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in tinyddt_suite_initialize"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_initialized
// CHECK-NEXT:    end subroutine tinyddt_suite_initialize
// CHECK-LABEL:   subroutine tinyddt_suite_finalize(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in tinyddt_suite_finalize"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_uninitialized
// CHECK-NEXT:    end subroutine tinyddt_suite_finalize
// CHECK-LABEL:   subroutine tinyddt_suite_init_physics(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in tinyddt_suite_init_physics"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine tinyddt_suite_init_physics
// CHECK-LABEL:   subroutine tinyddt_suite_physics(cols, cole, state, tend, errmsg, errflg)
// CHECK:           integer, intent(in) :: cols
// CHECK-NEXT:      integer, intent(in) :: cole
// CHECK-NEXT:      type(tiny_state_t), intent(inout) :: state
// CHECK-NEXT:      type(tiny_tend_t), intent(inout) :: tend
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_in_time_step .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in tinyddt_suite_physics"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call tinyddt_run(cols=cols, cole=cole, state=state, tend=tend, errmsg=errmsg, errflg=errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine tinyddt_suite_physics
// CHECK-LABEL:   subroutine tinyddt_suite_timestep_init_physics(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      ccpp_suite_state = const_in_time_step
// CHECK-NEXT:    end subroutine tinyddt_suite_timestep_init_physics
// CHECK-LABEL:   subroutine tinyddt_suite_timestep_final_physics(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      ccpp_suite_state = const_initialized
// CHECK-NEXT:    end subroutine tinyddt_suite_timestep_final_physics
// CHECK-LABEL:   subroutine tinyddt_suite_final_physics(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in tinyddt_suite_final_physics"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine tinyddt_suite_final_physics
// CHECK-NEXT:  end module tinyddt_suite_cap
// CHECK:       // -----
// CHECK-LABEL: // FILE: Tinyddt_ccpp_cap.F90
// CHECK-LABEL: module Tinyddt_ccpp_cap
// CHECK:         use ccpp_kinds
// CHECK-NEXT:    use iso_c_binding
// CHECK-NEXT:    use tinyddt, only: tiny_state_t
// CHECK-NEXT:    use tinyddt, only: tiny_tend_t
// CHECK-NEXT:    use tinyddt_suite_cap, only: tinyddt_suite_final_physics
// CHECK-NEXT:    use tinyddt_suite_cap, only: tinyddt_suite_finalize
// CHECK-NEXT:    use tinyddt_suite_cap, only: tinyddt_suite_init_physics
// CHECK-NEXT:    use tinyddt_suite_cap, only: tinyddt_suite_initialize
// CHECK-NEXT:    use tinyddt_suite_cap, only: tinyddt_suite_physics
// CHECK-NEXT:    use tinyddt_suite_cap, only: tinyddt_suite_register
// CHECK-NEXT:    use tinyddt_suite_cap, only: tinyddt_suite_timestep_final_physics
// CHECK-NEXT:    use tinyddt_suite_cap, only: tinyddt_suite_timestep_init_physics
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         character(len=13), parameter :: str_tinyddt_suite = 'tinyddt_suite'
// CHECK-NEXT:    character(len=7), parameter :: str_physics = 'physics'
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
// CHECK-NEXT:      if (trim(suite_name_f) .eq. 'tinyddt_suite') then
// CHECK-NEXT:        call tinyddt_suite_register(errflg, errmsg_f)
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
// CHECK-NEXT:      if (trim(suite_name_f) .eq. 'tinyddt_suite') then
// CHECK-NEXT:        call tinyddt_suite_initialize(errflg, errmsg_f)
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
// CHECK-NEXT:      if (trim(suite_name_f) .eq. 'tinyddt_suite') then
// CHECK-NEXT:        call tinyddt_suite_finalize(errflg, errmsg_f)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg_f, '(3a)') "No suite named ", trim(suite_name_f), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      do ccpp_c2f_i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(ccpp_c2f_i) = errmsg_f(ccpp_c2f_i:ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine ccpp_final
// CHECK-LABEL:   subroutine ccpp_physics_run(suite_name, suite_part, cols, cole, state, tend, errmsg,            &
// CHECK:           errflg) BIND(C, name='ccpp_physics_run')
// CHECK-NEXT:      character(kind=c_char, len=1), intent(in) :: suite_name(*)
// CHECK-NEXT:      character(kind=c_char, len=1), intent(in) :: suite_part(*)
// CHECK-NEXT:      integer(c_int), value, intent(in) :: cols
// CHECK-NEXT:      integer(c_int), value, intent(in) :: cole
// CHECK-NEXT:      type(c_ptr), intent(inout) :: state
// CHECK-NEXT:      type(c_ptr), intent(inout) :: tend
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
// CHECK-NEXT:      if (trim(suite_name_f) .eq. 'tinyddt_suite') then
// CHECK-NEXT:        if (trim(suite_part_f) .eq. 'physics') then
// CHECK-NEXT:          call tinyddt_suite_physics(cols, cole, state, tend, errmsg_f, errflg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg_f, '(3a)') "No suite part named ", trim(suite_part_f),                       &
// CHECK-NEXT:            " found in suite tinyddt_suite"
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
// CHECK-NEXT:      if (trim(suite_name_f) .eq. 'tinyddt_suite') then
// CHECK-NEXT:        if (trim(suite_part_f) .eq. 'physics') then
// CHECK-NEXT:          call tinyddt_suite_timestep_init_physics(errflg, errmsg_f)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg_f, '(3a)') "No suite part named ", trim(suite_part_f),                       &
// CHECK-NEXT:            " found in suite tinyddt_suite"
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
// CHECK-LABEL:   subroutine ccpp_physics_timestep_final(suite_name, suite_part, col_start, col_end, errmsg,      &
// CHECK:           errflg) BIND(C, name='ccpp_physics_timestep_final')
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
// CHECK-NEXT:      if (trim(suite_name_f) .eq. 'tinyddt_suite') then
// CHECK-NEXT:        if (trim(suite_part_f) .eq. 'physics') then
// CHECK-NEXT:          call tinyddt_suite_timestep_final_physics(errflg, errmsg_f)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg_f, '(3a)') "No suite part named ", trim(suite_part_f),                       &
// CHECK-NEXT:            " found in suite tinyddt_suite"
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
// CHECK-LABEL:   subroutine ccpp_physics_init(suite_name, suite_part, col_start, col_end, errmsg,                &
// CHECK:           errflg) BIND(C, name='ccpp_physics_init')
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
// CHECK-NEXT:      if (trim(suite_name_f) .eq. 'tinyddt_suite') then
// CHECK-NEXT:        if (trim(suite_part_f) .eq. 'physics') then
// CHECK-NEXT:          call tinyddt_suite_init_physics(errflg, errmsg_f)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg_f, '(3a)') "No suite part named ", trim(suite_part_f),                       &
// CHECK-NEXT:            " found in suite tinyddt_suite"
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
// CHECK-NEXT:      if (trim(suite_name_f) .eq. 'tinyddt_suite') then
// CHECK-NEXT:        if (trim(suite_part_f) .eq. 'physics') then
// CHECK-NEXT:          call tinyddt_suite_final_physics(errflg, errmsg_f)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg_f, '(3a)') "No suite part named ", trim(suite_part_f),                       &
// CHECK-NEXT:            " found in suite tinyddt_suite"
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
// CHECK-NEXT:      suites(1) = str_tinyddt_suite
// CHECK-NEXT:    end subroutine ccpp_physics_suite_list
// CHECK-LABEL:   subroutine ccpp_physics_suite_part_list(suite_name, part_list, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), allocatable, intent(out) :: part_list(:)
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'tinyddt_suite') then
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
// CHECK-NEXT:      if (trim(suite_name) .eq. 'tinyddt_suite') then
// CHECK-NEXT:        if (do_input .and. .not. do_output) then
// CHECK-NEXT:          allocate(var_list(4))
// CHECK-NEXT:          var_list(1) = 'horizontal_loop_begin               '
// CHECK-NEXT:          var_list(2) = 'horizontal_loop_end                 '
// CHECK-NEXT:          var_list(3) = 'tiny_physics_state                  '
// CHECK-NEXT:          var_list(4) = 'tiny_physics_tendency               '
// CHECK-NEXT:        else if (.not. do_input .and. do_output) then
// CHECK-NEXT:          allocate(var_list(4))
// CHECK-NEXT:          var_list(1) = 'ccpp_error_code                     '
// CHECK-NEXT:          var_list(2) = 'ccpp_error_message                  '
// CHECK-NEXT:          var_list(3) = 'tiny_physics_state                  '
// CHECK-NEXT:          var_list(4) = 'tiny_physics_tendency               '
// CHECK-NEXT:        else
// CHECK-NEXT:          allocate(var_list(6))
// CHECK-NEXT:          var_list(1) = 'ccpp_error_code                     '
// CHECK-NEXT:          var_list(2) = 'ccpp_error_message                  '
// CHECK-NEXT:          var_list(3) = 'horizontal_loop_begin               '
// CHECK-NEXT:          var_list(4) = 'horizontal_loop_end                 '
// CHECK-NEXT:          var_list(5) = 'tiny_physics_state                  '
// CHECK-NEXT:          var_list(6) = 'tiny_physics_tendency               '
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_physics_suite_variables
// CHECK:  end module Tinyddt_ccpp_cap
// CHECK:       // -----
// CHECK-LABEL: // FILE: Tinyddt_ccpp_chost_cap.F90
// CHECK-LABEL: module Tinyddt_ccpp_chost_cap
// CHECK:         use ccpp_kinds, only: kind_phys
// CHECK-NEXT:    use iso_c_binding
// CHECK-NEXT:    use tinyddt, only: tiny_state_t
// CHECK-NEXT:    use tinyddt, only: tiny_tend_t
// CHECK-NEXT:    use tinyddt_suite_cap, only: tinyddt_suite_register
// CHECK-NEXT:    use tinyddt_suite_cap, only: tinyddt_suite_initialize
// CHECK-NEXT:    use tinyddt_suite_cap, only: tinyddt_suite_finalize
// CHECK-NEXT:    use tinyddt_suite_cap, only: tinyddt_suite_physics
// CHECK-NEXT:    use tinyddt_suite_cap, only: tinyddt_suite_timestep_init_physics
// CHECK-NEXT:    use tinyddt_suite_cap, only: tinyddt_suite_timestep_final_physics
// CHECK-NEXT:    use tinyddt_suite_cap, only: tinyddt_suite_init_physics
// CHECK-NEXT:    use tinyddt_suite_cap, only: tinyddt_suite_final_physics
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         public :: Tinyddt_chost_physics_register
// CHECK-NEXT:    public :: Tinyddt_chost_physics_initialize
// CHECK-NEXT:    public :: Tinyddt_chost_physics_finalize
// CHECK-NEXT:    public :: Tinyddt_chost_physics_run
// CHECK-NEXT:    public :: Tinyddt_chost_physics_timestep_initial
// CHECK-NEXT:    public :: Tinyddt_chost_physics_timestep_final
// CHECK-NEXT:    public :: Tinyddt_chost_physics_physics_initial
// CHECK-NEXT:    public :: Tinyddt_chost_physics_physics_final
// CHECK:       contains
// CHECK-LABEL:   subroutine Tinyddt_chost_physics_register(errmsg, errflg) &
// CHECK:             bind(C, name='Tinyddt_chost_physics_register')
// CHECK-NEXT:      character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK-NEXT:      integer(c_int),               intent(out) :: errflg
// CHECK-NEXT:      integer :: i
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK:           errmsg_f = ' '
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      call tinyddt_suite_register(errflg, errmsg_f)
// CHECK-NEXT:      do i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(i) = errmsg_f(i:i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine Tinyddt_chost_physics_register
// CHECK-LABEL:   subroutine Tinyddt_chost_physics_initialize(errmsg, errflg) &
// CHECK:             bind(C, name='Tinyddt_chost_physics_initialize')
// CHECK-NEXT:      character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK-NEXT:      integer(c_int),               intent(out) :: errflg
// CHECK-NEXT:      integer :: i
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK:           errmsg_f = ' '
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      call tinyddt_suite_initialize(errflg, errmsg_f)
// CHECK-NEXT:      do i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(i) = errmsg_f(i:i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine Tinyddt_chost_physics_initialize
// CHECK-LABEL:   subroutine Tinyddt_chost_physics_finalize(errmsg, errflg) &
// CHECK:             bind(C, name='Tinyddt_chost_physics_finalize')
// CHECK-NEXT:      character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK-NEXT:      integer(c_int),               intent(out) :: errflg
// CHECK-NEXT:      integer :: i
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK:           errmsg_f = ' '
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      call tinyddt_suite_finalize(errflg, errmsg_f)
// CHECK-NEXT:      do i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(i) = errmsg_f(i:i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine Tinyddt_chost_physics_finalize
// CHECK-LABEL:   subroutine Tinyddt_chost_physics_run( &
// CHECK:             ncol, state_nz, tend_nz, col_start, col_end, state_temp, tend_dtemp, errmsg,  &
// CHECK-NEXT:        errflg) &
// CHECK-NEXT:        bind(C, name='Tinyddt_chost_physics_run')
// CHECK-NEXT:      integer(c_int), value, intent(in) :: ncol
// CHECK-NEXT:      integer(c_int), value, intent(in) :: state_nz
// CHECK-NEXT:      integer(c_int), value, intent(in) :: tend_nz
// CHECK-NEXT:      integer(c_int), value, intent(in) :: col_start
// CHECK-NEXT:      integer(c_int), value, intent(in) :: col_end
// CHECK-NEXT:      real(c_double), target, intent(inout) :: state_temp(ncol, state_nz)
// CHECK-NEXT:      real(c_double), target, intent(inout) :: tend_dtemp(ncol, tend_nz)
// CHECK-NEXT:      character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK-NEXT:      integer(c_int),               intent(out) :: errflg
// CHECK-NEXT:      integer :: i
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK-NEXT:      type(tiny_state_t) :: state_local
// CHECK-NEXT:      type(tiny_tend_t) :: tend_local
// CHECK:           errmsg_f = ' '
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      state_local%nz = state_nz
// CHECK-NEXT:      allocate(state_local%temp(ncol, state_nz))
// CHECK-NEXT:      state_local%temp = real(state_temp, kind_phys)
// CHECK-NEXT:      tend_local%nz = tend_nz
// CHECK-NEXT:      allocate(tend_local%dtemp(ncol, tend_nz))
// CHECK-NEXT:      tend_local%dtemp = real(tend_dtemp, kind_phys)
// CHECK-NEXT:      call tinyddt_suite_physics( &
// CHECK-NEXT:          col_start, col_end, state_local, tend_local, errmsg_f, errflg)
// CHECK-NEXT:      state_temp = real(state_local%temp, c_double)
// CHECK-NEXT:      tend_dtemp = real(tend_local%dtemp, c_double)
// CHECK-NEXT:      do i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(i) = errmsg_f(i:i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine Tinyddt_chost_physics_run
// CHECK-LABEL:   subroutine Tinyddt_chost_physics_timestep_initial(errmsg, errflg) &
// CHECK:             bind(C, name='Tinyddt_chost_physics_timestep_initial')
// CHECK-NEXT:      character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK-NEXT:      integer(c_int),               intent(out) :: errflg
// CHECK-NEXT:      integer :: i
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK:           errmsg_f = ' '
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      call tinyddt_suite_timestep_init_physics(errflg, errmsg_f)
// CHECK-NEXT:      do i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(i) = errmsg_f(i:i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine Tinyddt_chost_physics_timestep_initial
// CHECK-LABEL:   subroutine Tinyddt_chost_physics_timestep_final(errmsg, errflg) &
// CHECK:             bind(C, name='Tinyddt_chost_physics_timestep_final')
// CHECK-NEXT:      character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK-NEXT:      integer(c_int),               intent(out) :: errflg
// CHECK-NEXT:      integer :: i
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK:           errmsg_f = ' '
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      call tinyddt_suite_timestep_final_physics(errflg, errmsg_f)
// CHECK-NEXT:      do i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(i) = errmsg_f(i:i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine Tinyddt_chost_physics_timestep_final
// CHECK-LABEL:   subroutine Tinyddt_chost_physics_physics_initial(errmsg, errflg) &
// CHECK:             bind(C, name='Tinyddt_chost_physics_physics_initial')
// CHECK-NEXT:      character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK-NEXT:      integer(c_int),               intent(out) :: errflg
// CHECK-NEXT:      integer :: i
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK:           errmsg_f = ' '
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      call tinyddt_suite_init_physics(errflg, errmsg_f)
// CHECK-NEXT:      do i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(i) = errmsg_f(i:i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine Tinyddt_chost_physics_physics_initial
// CHECK-LABEL:   subroutine Tinyddt_chost_physics_physics_final(errmsg, errflg) &
// CHECK:             bind(C, name='Tinyddt_chost_physics_physics_final')
// CHECK-NEXT:      character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK-NEXT:      integer(c_int),               intent(out) :: errflg
// CHECK-NEXT:      integer :: i
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK:           errmsg_f = ' '
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      call tinyddt_suite_final_physics(errflg, errmsg_f)
// CHECK-NEXT:      do i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(i) = errmsg_f(i:i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine Tinyddt_chost_physics_physics_final
// CHECK:       end module Tinyddt_ccpp_chost_cap
// CHECK:       // -----
// CHECK-LABEL: // FILE: ccpp_kinds.F90
// CHECK-LABEL: module ccpp_kinds
// CHECK:         use ISO_FORTRAN_ENV, only: kind_phys => REAL64
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         public :: kind_phys
// CHECK-NEXT:  end module ccpp_kinds
