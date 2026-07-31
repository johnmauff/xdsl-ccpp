// Test chost cap generation for the kessler example (host_cpp/ meta files carry language = c++).
// Verifies that the generated chost cap module:
//   - uses iso_c_binding and delegates to the suite cap
//   - injects ncol and passes col_start/col_end through for the run subroutine
//   - emits bind(C) subroutines with correct Fortran types for every lifecycle
//   - passes col_start and col_end directly in suite cap calls
//   - converts Fortran character buffers to C strings via copy loops
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/kessler/scheme/kessler_suite.xml --scheme-files examples/kessler/scheme/kessler.meta,examples/kessler/scheme/kessler_update.meta --host-files examples/kessler/host_cpp/kessler_host_mod.meta,examples/kessler/host_cpp/kessler_host_sub.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p "generate-meta-cap,generate-meta-kinds,generate-host-match,generate-arg-ownership,generate-suite-cap,generate-ccpp-cap{bind_c=true},generate-cpp-cap,generate-kinds,strip-ccpp" -t ftn | python3 -m filecheck %s

// Module header: uses iso_c_binding and imports only suite cap entry points.

// CHECK-LABEL: // FILE: kessler_suite_cap.F90
// CHECK-LABEL: module kessler_suite_cap
// CHECK:         use ccpp_kinds
// CHECK-NEXT:    use kessler, only: kessler_init
// CHECK-NEXT:    use kessler, only: kessler_run
// CHECK-NEXT:    use kessler_update, only: kessler_update_init
// CHECK-NEXT:    use kessler_update, only: kessler_update_run
// CHECK-NEXT:    use kessler_update, only: kessler_update_timestep_final
// CHECK-NEXT:    use kessler_update, only: kessler_update_timestep_init
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         character(len=16) :: ccpp_suite_state = 'uninitialized'
// CHECK-NEXT:    character(len=16), parameter :: const_in_time_step = 'in_time_step'
// CHECK-NEXT:    character(len=16), parameter :: const_initialized = 'initialized'
// CHECK-NEXT:    character(len=16), parameter :: const_uninitialized = 'uninitialized'
// CHECK-NEXT:    public :: kessler_suite_suite_register
// CHECK-NEXT:    public :: kessler_suite_suite_initialize
// CHECK-NEXT:    public :: kessler_suite_suite_finalize
// CHECK-NEXT:    public :: kessler_suite_suite_timestep_initial
// CHECK-NEXT:    public :: kessler_suite_suite_timestep_final
// CHECK-NEXT:    public :: kessler_suite_suite_physics
// CHECK:       CONTAINS
// CHECK-LABEL:   subroutine kessler_suite_suite_register(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:    end subroutine kessler_suite_suite_register
// CHECK-LABEL:   subroutine kessler_suite_suite_initialize(lv_in, pref_in, rhoqr_in, gravit_in, errmsg, errflg)
// CHECK:           real(kind=kind_phys), intent(in) :: lv_in
// CHECK-NEXT:      real(kind=kind_phys), intent(in) :: pref_in
// CHECK-NEXT:      real(kind=kind_phys), intent(in) :: rhoqr_in
// CHECK-NEXT:      real(kind=kind_phys), intent(in) :: gravit_in
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_uninitialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in kessler_suite_initialize"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call kessler_init(lv_in=lv_in, pref_in=pref_in, rhoqr_in=rhoqr_in, errmsg=errmsg,           &
// CHECK-NEXT:          errflg=errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call kessler_update_init(gravit_in=gravit_in, errmsg=errmsg, errflg=errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_initialized
// CHECK-NEXT:    end subroutine kessler_suite_suite_initialize
// CHECK-LABEL:   subroutine kessler_suite_suite_finalize(errflg, errmsg)
// CHECK:           integer, intent(out) :: errflg
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in kessler_suite_finalize"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_uninitialized
// CHECK-NEXT:    end subroutine kessler_suite_suite_finalize
// CHECK-LABEL:   subroutine kessler_suite_suite_timestep_initial(ncol, nz, temp, temp_prev, ttend_t, errmsg,     &
// CHECK:           errflg)
// CHECK-NEXT:      integer, intent(in) :: ncol
// CHECK-NEXT:      integer, intent(in) :: nz
// CHECK-NEXT:      real(kind=kind_phys), target, intent(in) :: temp(:, :)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: temp_prev(:, :)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: ttend_t(:, :)
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_initialized .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in kessler_suite_timestep_initial"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call kessler_update_timestep_init(ncol=ncol, nz=nz, temp=temp, temp_prev=temp_prev,         &
// CHECK-NEXT:          ttend_t=ttend_t, errmsg=errmsg, errflg=errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_in_time_step
// CHECK-NEXT:    end subroutine kessler_suite_suite_timestep_initial
// CHECK-LABEL:   subroutine kessler_suite_suite_timestep_final(nz, ncol, cpair, temp, zm, phis, st_energy,       &
// CHECK:           errmsg, errflg)
// CHECK-NEXT:      integer, intent(in) :: nz
// CHECK-NEXT:      integer, intent(in) :: ncol
// CHECK-NEXT:      real(kind=kind_phys), target, intent(in) :: cpair(:, :)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(in) :: temp(:, :)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(in) :: zm(:, :)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(in) :: phis(:)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: st_energy(:, :)
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_in_time_step .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in kessler_suite_timestep_final"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call kessler_update_timestep_final(nz=nz, ncol=ncol, cpair=cpair, temp=temp, zm=zm,         &
// CHECK-NEXT:          phis=phis, st_energy=st_energy, errmsg=errmsg, errflg=errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      ccpp_suite_state = const_initialized
// CHECK-NEXT:    end subroutine kessler_suite_suite_timestep_final
// CHECK-LABEL:   subroutine kessler_suite_suite_physics(ncol, nz, dt, lyr_surf, lyr_toa, cpair, rair, rho, z,    &
// CHECK:           pk, theta, qv, qc, qr, precl, relhum, temp_prev, ttend_t, scheme_name, errmsg, errflg)
// CHECK-NEXT:      integer, intent(in) :: ncol
// CHECK-NEXT:      integer, intent(in) :: nz
// CHECK-NEXT:      real(kind=kind_phys), intent(in) :: dt
// CHECK-NEXT:      integer, intent(in) :: lyr_surf
// CHECK-NEXT:      integer, intent(in) :: lyr_toa
// CHECK-NEXT:      real(kind=kind_phys), target, intent(in) :: cpair(:, :)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(in) :: rair(:, :)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(in) :: rho(:, :)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(in) :: z(:, :)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(in) :: pk(:, :)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: theta(:, :)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: qv(:, :)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: qc(:, :)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: qr(:, :)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: precl(:)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: relhum(:, :)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(in) :: temp_prev(:, :)
// CHECK-NEXT:      real(kind=kind_phys), target, intent(inout) :: ttend_t(:, :)
// CHECK-NEXT:      character(len=64), intent(out) :: scheme_name
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      errmsg = ''
// CHECK-NEXT:      if (.NOT. (const_in_time_step .eq. ccpp_suite_state)) then
// CHECK-NEXT:        write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
// CHECK-NEXT:          "' in kessler_suite_physics"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call kessler_run(ncol=ncol, nz=nz, dt=dt, lyr_surf=lyr_surf, lyr_toa=lyr_toa, cpair=cpair,  &
// CHECK-NEXT:          rair=rair, rho=rho, z=z, pk=pk, theta=theta, qv=qv, qc=qc, qr=qr, precl=precl,            &
// CHECK-NEXT:          relhum=relhum, scheme_name=scheme_name, errmsg=errmsg, errflg=errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:      if (errflg .eq. 0) then
// CHECK-NEXT:        call kessler_update_run(nz=nz, ncol=ncol, dt=dt, theta=theta, exner=pk,                     &
// CHECK-NEXT:          temp_prev=temp_prev, ttend_t=ttend_t, errmsg=errmsg, errflg=errflg)
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine kessler_suite_suite_physics
// CHECK-NEXT:  end module kessler_suite_cap
// CHECK:       // -----
// CHECK-LABEL: // FILE: Kessler_ccpp_cap.F90
// CHECK-LABEL: module Kessler_ccpp_cap
// CHECK:         use ccpp_kinds
// CHECK-NEXT:    use iso_c_binding
// CHECK-NEXT:    use kessler_host_mod, only: cpair
// CHECK-NEXT:    use kessler_host_mod, only: dt
// CHECK-NEXT:    use kessler_host_mod, only: exner
// CHECK-NEXT:    use kessler_host_mod, only: gravit
// CHECK-NEXT:    use kessler_host_mod, only: lv
// CHECK-NEXT:    use kessler_host_mod, only: lyr_surf
// CHECK-NEXT:    use kessler_host_mod, only: lyr_toa
// CHECK-NEXT:    use kessler_host_mod, only: ncol
// CHECK-NEXT:    use kessler_host_mod, only: nz
// CHECK-NEXT:    use kessler_host_mod, only: phis
// CHECK-NEXT:    use kessler_host_mod, only: precl
// CHECK-NEXT:    use kessler_host_mod, only: pref
// CHECK-NEXT:    use kessler_host_mod, only: qc
// CHECK-NEXT:    use kessler_host_mod, only: qr
// CHECK-NEXT:    use kessler_host_mod, only: qv
// CHECK-NEXT:    use kessler_host_mod, only: rair
// CHECK-NEXT:    use kessler_host_mod, only: relhum
// CHECK-NEXT:    use kessler_host_mod, only: rho
// CHECK-NEXT:    use kessler_host_mod, only: rhoqr
// CHECK-NEXT:    use kessler_host_mod, only: scheme_name
// CHECK-NEXT:    use kessler_host_mod, only: st_energy
// CHECK-NEXT:    use kessler_host_mod, only: temp
// CHECK-NEXT:    use kessler_host_mod, only: temp_prev
// CHECK-NEXT:    use kessler_host_mod, only: theta
// CHECK-NEXT:    use kessler_host_mod, only: ttend_t
// CHECK-NEXT:    use kessler_host_mod, only: z
// CHECK-NEXT:    use kessler_suite_cap, only: kessler_suite_suite_finalize
// CHECK-NEXT:    use kessler_suite_cap, only: kessler_suite_suite_initialize
// CHECK-NEXT:    use kessler_suite_cap, only: kessler_suite_suite_physics
// CHECK-NEXT:    use kessler_suite_cap, only: kessler_suite_suite_register
// CHECK-NEXT:    use kessler_suite_cap, only: kessler_suite_suite_timestep_final
// CHECK-NEXT:    use kessler_suite_cap, only: kessler_suite_suite_timestep_initial
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         character(len=13), parameter :: str_kessler_suite = 'kessler_suite'
// CHECK-NEXT:    character(len=7), parameter :: str_physics = 'physics'
// CHECK-NEXT:    public :: Kessler_ccpp_physics_register
// CHECK-NEXT:    public :: Kessler_ccpp_physics_initialize
// CHECK-NEXT:    public :: Kessler_ccpp_physics_finalize
// CHECK-NEXT:    public :: Kessler_ccpp_physics_timestep_initial
// CHECK-NEXT:    public :: Kessler_ccpp_physics_timestep_final
// CHECK-NEXT:    public :: Kessler_ccpp_physics_run
// CHECK-NEXT:    public :: ccpp_physics_suite_list
// CHECK-NEXT:    public :: ccpp_physics_suite_part_list
// CHECK-NEXT:    public :: ccpp_physics_suite_variables
// CHECK:       CONTAINS
// CHECK-LABEL:   subroutine Kessler_ccpp_physics_register(suite_name, errmsg, errflg) BIND(C,                    &
// CHECK:           name='Kessler_ccpp_physics_register')
// CHECK-NEXT:      character(kind=c_char, len=1), intent(in) :: suite_name(*)
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
// CHECK-NEXT:      if (trim(suite_name_f) .eq. 'kessler_suite') then
// CHECK-NEXT:        call kessler_suite_suite_register(errflg, errmsg_f)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg_f, '(3a)') "No suite named ", trim(suite_name_f), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      do ccpp_c2f_i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(ccpp_c2f_i) = errmsg_f(ccpp_c2f_i:ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine Kessler_ccpp_physics_register
// CHECK-LABEL:   subroutine Kessler_ccpp_physics_initialize(suite_name, errmsg, errflg) BIND(C,                  &
// CHECK:           name='Kessler_ccpp_physics_initialize')
// CHECK-NEXT:      character(kind=c_char, len=1), intent(in) :: suite_name(*)
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
// CHECK-NEXT:      if (trim(suite_name_f) .eq. 'kessler_suite') then
// CHECK-NEXT:        call kessler_suite_suite_initialize(lv, pref, rhoqr, gravit, errmsg_f, errflg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg_f, '(3a)') "No suite named ", trim(suite_name_f), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      do ccpp_c2f_i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(ccpp_c2f_i) = errmsg_f(ccpp_c2f_i:ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine Kessler_ccpp_physics_initialize
// CHECK-LABEL:   subroutine Kessler_ccpp_physics_finalize(suite_name, errmsg, errflg) BIND(C,                    &
// CHECK:           name='Kessler_ccpp_physics_finalize')
// CHECK-NEXT:      character(kind=c_char, len=1), intent(in) :: suite_name(*)
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
// CHECK-NEXT:      if (trim(suite_name_f) .eq. 'kessler_suite') then
// CHECK-NEXT:        call kessler_suite_suite_finalize(errflg, errmsg_f)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg_f, '(3a)') "No suite named ", trim(suite_name_f), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      do ccpp_c2f_i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(ccpp_c2f_i) = errmsg_f(ccpp_c2f_i:ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine Kessler_ccpp_physics_finalize
// CHECK-LABEL:   subroutine Kessler_ccpp_physics_timestep_initial(suite_name, errmsg, errflg) BIND(C,            &
// CHECK:           name='Kessler_ccpp_physics_timestep_initial')
// CHECK-NEXT:      character(kind=c_char, len=1), intent(in) :: suite_name(*)
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
// CHECK-NEXT:      if (trim(suite_name_f) .eq. 'kessler_suite') then
// CHECK-NEXT:        call kessler_suite_suite_timestep_initial(ncol, nz, temp, temp_prev, ttend_t, errmsg_f,     &
// CHECK-NEXT:          errflg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg_f, '(3a)') "No suite named ", trim(suite_name_f), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      do ccpp_c2f_i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(ccpp_c2f_i) = errmsg_f(ccpp_c2f_i:ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine Kessler_ccpp_physics_timestep_initial
// CHECK-LABEL:   subroutine Kessler_ccpp_physics_timestep_final(suite_name, errmsg, errflg) BIND(C,              &
// CHECK:           name='Kessler_ccpp_physics_timestep_final')
// CHECK-NEXT:      character(kind=c_char, len=1), intent(in) :: suite_name(*)
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
// CHECK-NEXT:      if (trim(suite_name_f) .eq. 'kessler_suite') then
// CHECK-NEXT:        call kessler_suite_suite_timestep_final(nz, ncol, cpair, temp, z, phis, st_energy,          &
// CHECK-NEXT:          errmsg_f, errflg)
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg_f, '(3a)') "No suite named ", trim(suite_name_f), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:      do ccpp_c2f_i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(ccpp_c2f_i) = errmsg_f(ccpp_c2f_i:ccpp_c2f_i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine Kessler_ccpp_physics_timestep_final
// CHECK-LABEL:   subroutine Kessler_ccpp_physics_run(suite_name, suite_part, col_start, col_end, errmsg,         &
// CHECK:           errflg) BIND(C, name='Kessler_ccpp_physics_run')
// CHECK-NEXT:      character(kind=c_char, len=1), intent(in) :: suite_name(*)
// CHECK-NEXT:      character(kind=c_char, len=1), intent(in) :: suite_part(*)
// CHECK-NEXT:      integer(c_int), value, intent(in) :: col_start
// CHECK-NEXT:      integer(c_int), value, intent(in) :: col_end
// CHECK-NEXT:      character(kind=c_char, len=1), intent(inout) :: errmsg(*)
// CHECK-NEXT:      integer(c_int), intent(inout) :: errflg
// CHECK-NEXT:      integer :: ncol
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
// CHECK-NEXT:      if (trim(suite_name_f) .eq. 'kessler_suite') then
// CHECK-NEXT:        ncol = col_end - col_start + 1
// CHECK-NEXT:        if (trim(suite_part_f) .eq. 'physics') then
// CHECK-NEXT:          call kessler_suite_suite_physics(ncol, nz, dt, lyr_surf, lyr_toa,                         &
// CHECK-NEXT:            cpair(col_start:col_end, 1:nz), rair(col_start:col_end, 1:nz), rho(col_start:col_end,   &
// CHECK-NEXT:            1:nz), z(col_start:col_end, 1:nz), exner(col_start:col_end, 1:nz),                      &
// CHECK-NEXT:            theta(col_start:col_end, 1:nz), qv(col_start:col_end, 1:nz), qc(col_start:col_end,      &
// CHECK-NEXT:            1:nz), qr(col_start:col_end, 1:nz), precl(col_start:col_end), relhum(col_start:col_end, &
// CHECK-NEXT:            1:nz), temp_prev(col_start:col_end, 1:nz), ttend_t(col_start:col_end, 1:nz),            &
// CHECK-NEXT:            scheme_name, errmsg_f, errflg)
// CHECK-NEXT:        else
// CHECK-NEXT:          write(errmsg_f, '(3a)') "No suite part named ", trim(suite_part_f),                       &
// CHECK-NEXT:            " found in suite kessler_suite"
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
// CHECK-NEXT:    end subroutine Kessler_ccpp_physics_run
// CHECK-LABEL:   subroutine ccpp_physics_suite_list(suites)
// CHECK:           character(len=*), allocatable, intent(out) :: suites(:)
// CHECK:           allocate(suites(1))
// CHECK-NEXT:      suites(1) = str_kessler_suite
// CHECK-NEXT:    end subroutine ccpp_physics_suite_list
// CHECK-LABEL:   subroutine ccpp_physics_suite_part_list(suite_name, part_list, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
// CHECK-NEXT:      character(len=*), allocatable, intent(out) :: part_list(:)
// CHECK-NEXT:      character(len=512), intent(out) :: errmsg
// CHECK-NEXT:      integer, intent(out) :: errflg
// CHECK:           errflg = 0
// CHECK-NEXT:      if (trim(suite_name) .eq. 'kessler_suite') then
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
// CHECK-NEXT:      if (trim(suite_name) .eq. 'kessler_suite') then
// CHECK-NEXT:        if (do_input .and. .not. do_output) then
// CHECK-NEXT:          allocate(var_list(22))
// CHECK-NEXT:          var_list(1) = 'air_potential_temperature           '
// CHECK-NEXT:          var_list(2) = 'air_temperature                     '
// CHECK-NEXT:          var_list(3) = 'air_temperature_on_previous_timestep'
// CHECK-NEXT:          var_list(4) = 'cloud_liquid_water_mixing_ratio_wrt_dry_air'
// CHECK-NEXT:          var_list(5) = 'composition_dependent_gas_constant_of_dry_air'
// CHECK-NEXT:          var_list(6) = 'composition_dependent_specific_heat_of_dry_air_at_constant_pressure'
// CHECK-NEXT:          var_list(7) = 'dimensionless_exner_function        '
// CHECK-NEXT:          var_list(8) = 'dry_air_density                     '
// CHECK-NEXT:          var_list(9) = 'fresh_liquid_water_density_at_0c    '
// CHECK-NEXT:          var_list(10) = 'geopotential_height_wrt_surface     '
// CHECK-NEXT:          var_list(11) = 'horizontal_dimension                '
// CHECK-NEXT:          var_list(12) = 'latent_heat_of_vaporization_of_water_at_0c'
// CHECK-NEXT:          var_list(13) = 'rain_mixing_ratio_wrt_dry_air       '
// CHECK-NEXT:          var_list(14) = 'standard_gravitational_acceleration '
// CHECK-NEXT:          var_list(15) = 'surface_geopotential                '
// CHECK-NEXT:          var_list(16) = 'surface_reference_pressure          '
// CHECK-NEXT:          var_list(17) = 'tendency_of_air_temperature_due_to_model_physics'
// CHECK-NEXT:          var_list(18) = 'timestep_for_physics                '
// CHECK-NEXT:          var_list(19) = 'vertical_index_at_surface_adjacent_layer'
// CHECK-NEXT:          var_list(20) = 'vertical_index_at_top_adjacent_layer'
// CHECK-NEXT:          var_list(21) = 'vertical_layer_dimension            '
// CHECK-NEXT:          var_list(22) = 'water_vapor_mixing_ratio_wrt_dry_air'
// CHECK-NEXT:        else if (.not. do_input .and. do_output) then
// CHECK-NEXT:          allocate(var_list(12))
// CHECK-NEXT:          var_list(1) = 'air_potential_temperature           '
// CHECK-NEXT:          var_list(2) = 'air_temperature_on_previous_timestep'
// CHECK-NEXT:          var_list(3) = 'ccpp_error_code                     '
// CHECK-NEXT:          var_list(4) = 'ccpp_error_message                  '
// CHECK-NEXT:          var_list(5) = 'cloud_liquid_water_mixing_ratio_wrt_dry_air'
// CHECK-NEXT:          var_list(6) = 'dry_static_energy                   '
// CHECK-NEXT:          var_list(7) = 'rain_mixing_ratio_wrt_dry_air       '
// CHECK-NEXT:          var_list(8) = 'relative_humidity                   '
// CHECK-NEXT:          var_list(9) = 'scheme_name                         '
// CHECK-NEXT:          var_list(10) = 'tendency_of_air_temperature_due_to_model_physics'
// CHECK-NEXT:          var_list(11) = 'total_precipitation_rate_at_surface '
// CHECK-NEXT:          var_list(12) = 'water_vapor_mixing_ratio_wrt_dry_air'
// CHECK-NEXT:        else
// CHECK-NEXT:          allocate(var_list(28))
// CHECK-NEXT:          var_list(1) = 'air_potential_temperature           '
// CHECK-NEXT:          var_list(2) = 'air_temperature                     '
// CHECK-NEXT:          var_list(3) = 'air_temperature_on_previous_timestep'
// CHECK-NEXT:          var_list(4) = 'ccpp_error_code                     '
// CHECK-NEXT:          var_list(5) = 'ccpp_error_message                  '
// CHECK-NEXT:          var_list(6) = 'cloud_liquid_water_mixing_ratio_wrt_dry_air'
// CHECK-NEXT:          var_list(7) = 'composition_dependent_gas_constant_of_dry_air'
// CHECK-NEXT:          var_list(8) = 'composition_dependent_specific_heat_of_dry_air_at_constant_pressure'
// CHECK-NEXT:          var_list(9) = 'dimensionless_exner_function        '
// CHECK-NEXT:          var_list(10) = 'dry_air_density                     '
// CHECK-NEXT:          var_list(11) = 'dry_static_energy                   '
// CHECK-NEXT:          var_list(12) = 'fresh_liquid_water_density_at_0c    '
// CHECK-NEXT:          var_list(13) = 'geopotential_height_wrt_surface     '
// CHECK-NEXT:          var_list(14) = 'horizontal_dimension                '
// CHECK-NEXT:          var_list(15) = 'latent_heat_of_vaporization_of_water_at_0c'
// CHECK-NEXT:          var_list(16) = 'rain_mixing_ratio_wrt_dry_air       '
// CHECK-NEXT:          var_list(17) = 'relative_humidity                   '
// CHECK-NEXT:          var_list(18) = 'scheme_name                         '
// CHECK-NEXT:          var_list(19) = 'standard_gravitational_acceleration '
// CHECK-NEXT:          var_list(20) = 'surface_geopotential                '
// CHECK-NEXT:          var_list(21) = 'surface_reference_pressure          '
// CHECK-NEXT:          var_list(22) = 'tendency_of_air_temperature_due_to_model_physics'
// CHECK-NEXT:          var_list(23) = 'timestep_for_physics                '
// CHECK-NEXT:          var_list(24) = 'total_precipitation_rate_at_surface '
// CHECK-NEXT:          var_list(25) = 'vertical_index_at_surface_adjacent_layer'
// CHECK-NEXT:          var_list(26) = 'vertical_index_at_top_adjacent_layer'
// CHECK-NEXT:          var_list(27) = 'vertical_layer_dimension            '
// CHECK-NEXT:          var_list(28) = 'water_vapor_mixing_ratio_wrt_dry_air'
// CHECK-NEXT:        end if
// CHECK-NEXT:      else
// CHECK-NEXT:        write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
// CHECK-NEXT:        errflg = 1
// CHECK-NEXT:      end if
// CHECK-NEXT:    end subroutine ccpp_physics_suite_variables
// CHECK-NEXT:  end module Kessler_ccpp_cap
// CHECK:       // -----
// CHECK-LABEL: // FILE: Kessler_ccpp_chost_cap.F90
// CHECK-LABEL: module Kessler_ccpp_chost_cap
// CHECK:         use ccpp_kinds, only: kind_phys
// CHECK-NEXT:    use iso_c_binding
// CHECK-NEXT:    use kessler_suite_cap, only: kessler_suite_suite_register
// CHECK-NEXT:    use kessler_suite_cap, only: kessler_suite_suite_initialize
// CHECK-NEXT:    use kessler_suite_cap, only: kessler_suite_suite_finalize
// CHECK-NEXT:    use kessler_suite_cap, only: kessler_suite_suite_timestep_initial
// CHECK-NEXT:    use kessler_suite_cap, only: kessler_suite_suite_timestep_final
// CHECK-NEXT:    use kessler_suite_cap, only: kessler_suite_suite_physics
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         public :: Kessler_chost_physics_register
// CHECK-NEXT:    public :: Kessler_chost_physics_initialize
// CHECK-NEXT:    public :: Kessler_chost_physics_finalize
// CHECK-NEXT:    public :: Kessler_chost_physics_timestep_initial
// CHECK-NEXT:    public :: Kessler_chost_physics_timestep_final
// CHECK-NEXT:    public :: Kessler_chost_physics_run
// CHECK:       contains
// CHECK-LABEL:   subroutine Kessler_chost_physics_register(errmsg, errflg) &
// CHECK:             bind(C, name='Kessler_chost_physics_register')
// CHECK-NEXT:      character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK-NEXT:      integer(c_int),               intent(out) :: errflg
// CHECK-NEXT:      integer :: i
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK:           errmsg_f = ' '
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      call kessler_suite_suite_register(errflg, errmsg_f)
// CHECK-NEXT:      do i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(i) = errmsg_f(i:i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine Kessler_chost_physics_register
// CHECK-LABEL:   subroutine Kessler_chost_physics_initialize(lv, pref, rhoqr, gravit, errmsg, errflg) &
// CHECK:             bind(C, name='Kessler_chost_physics_initialize')
// CHECK-NEXT:      real(c_double), value, intent(in) :: lv
// CHECK-NEXT:      real(c_double), value, intent(in) :: pref
// CHECK-NEXT:      real(c_double), value, intent(in) :: rhoqr
// CHECK-NEXT:      real(c_double), value, intent(in) :: gravit
// CHECK-NEXT:      character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK-NEXT:      integer(c_int),               intent(out) :: errflg
// CHECK-NEXT:      integer :: i
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK:           errmsg_f = ' '
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      call kessler_suite_suite_initialize( &
// CHECK-NEXT:          real(lv, kind_phys), real(pref, kind_phys), real(rhoqr, kind_phys),  &
// CHECK-NEXT:          real(gravit, kind_phys), errmsg_f, errflg)
// CHECK-NEXT:      do i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(i) = errmsg_f(i:i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine Kessler_chost_physics_initialize
// CHECK-LABEL:   subroutine Kessler_chost_physics_finalize(errmsg, errflg) &
// CHECK:             bind(C, name='Kessler_chost_physics_finalize')
// CHECK-NEXT:      character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK-NEXT:      integer(c_int),               intent(out) :: errflg
// CHECK-NEXT:      integer :: i
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK:           errmsg_f = ' '
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      call kessler_suite_suite_finalize(errflg, errmsg_f)
// CHECK-NEXT:      do i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(i) = errmsg_f(i:i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine Kessler_chost_physics_finalize
// CHECK-LABEL:   subroutine Kessler_chost_physics_timestep_initial( &
// CHECK:             ncol, nz, temp, temp_prev, ttend_t, errmsg, errflg) &
// CHECK-NEXT:        bind(C, name='Kessler_chost_physics_timestep_initial')
// CHECK-NEXT:      integer(c_int), value, intent(in) :: ncol
// CHECK-NEXT:      integer(c_int), value, intent(in) :: nz
// CHECK-NEXT:      real(c_double), target, intent(in) :: temp(ncol, nz)
// CHECK-NEXT:      real(c_double), target, intent(inout) :: temp_prev(ncol, nz)
// CHECK-NEXT:      real(c_double), target, intent(inout) :: ttend_t(ncol, nz)
// CHECK-NEXT:      character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK-NEXT:      integer(c_int),               intent(out) :: errflg
// CHECK-NEXT:      integer :: i
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK:           errmsg_f = ' '
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      call kessler_suite_suite_timestep_initial( &
// CHECK-NEXT:          ncol, nz, temp, temp_prev, ttend_t, errmsg_f, errflg)
// CHECK-NEXT:      do i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(i) = errmsg_f(i:i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine Kessler_chost_physics_timestep_initial
// CHECK-LABEL:   subroutine Kessler_chost_physics_timestep_final( &
// CHECK:             ncol, nz, cpair, temp, z, phis, st_energy, errmsg, errflg) &
// CHECK-NEXT:        bind(C, name='Kessler_chost_physics_timestep_final')
// CHECK-NEXT:      integer(c_int), value, intent(in) :: ncol
// CHECK-NEXT:      integer(c_int), value, intent(in) :: nz
// CHECK-NEXT:      real(c_double), target, intent(in) :: cpair(ncol, nz)
// CHECK-NEXT:      real(c_double), target, intent(in) :: temp(ncol, nz)
// CHECK-NEXT:      real(c_double), target, intent(in) :: z(ncol, nz)
// CHECK-NEXT:      real(c_double), target, intent(in) :: phis(ncol)
// CHECK-NEXT:      real(c_double), target, intent(inout) :: st_energy(ncol, nz)
// CHECK-NEXT:      character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK-NEXT:      integer(c_int),               intent(out) :: errflg
// CHECK-NEXT:      integer :: i
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK:           errmsg_f = ' '
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      call kessler_suite_suite_timestep_final( &
// CHECK-NEXT:          nz, ncol, cpair, temp, z, phis, st_energy, errmsg_f, errflg)
// CHECK-NEXT:      do i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(i) = errmsg_f(i:i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine Kessler_chost_physics_timestep_final
// CHECK-LABEL:   subroutine Kessler_chost_physics_run( &
// CHECK:             ncol, nz, dt, lyr_surf, lyr_toa, cpair, rair, rho, z, exner, theta, qv, qc, qr,  &
// CHECK-NEXT:        precl, relhum, temp_prev, ttend_t, scheme_name, errmsg, errflg) &
// CHECK-NEXT:        bind(C, name='Kessler_chost_physics_run')
// CHECK-NEXT:      integer(c_int), value, intent(in) :: ncol
// CHECK-NEXT:      integer(c_int), value, intent(in) :: nz
// CHECK-NEXT:      real(c_double), value, intent(in) :: dt
// CHECK-NEXT:      integer(c_int), value, intent(in) :: lyr_surf
// CHECK-NEXT:      integer(c_int), value, intent(in) :: lyr_toa
// CHECK-NEXT:      real(c_double), target, intent(in) :: cpair(ncol, nz)
// CHECK-NEXT:      real(c_double), target, intent(in) :: rair(ncol, nz)
// CHECK-NEXT:      real(c_double), target, intent(in) :: rho(ncol, nz)
// CHECK-NEXT:      real(c_double), target, intent(in) :: z(ncol, nz)
// CHECK-NEXT:      real(c_double), target, intent(in) :: exner(ncol, nz)
// CHECK-NEXT:      real(c_double), target, intent(inout) :: theta(ncol, nz)
// CHECK-NEXT:      real(c_double), target, intent(inout) :: qv(ncol, nz)
// CHECK-NEXT:      real(c_double), target, intent(inout) :: qc(ncol, nz)
// CHECK-NEXT:      real(c_double), target, intent(inout) :: qr(ncol, nz)
// CHECK-NEXT:      real(c_double), target, intent(inout) :: precl(ncol)
// CHECK-NEXT:      real(c_double), target, intent(inout) :: relhum(ncol, nz)
// CHECK-NEXT:      real(c_double), target, intent(in) :: temp_prev(ncol, nz)
// CHECK-NEXT:      real(c_double), target, intent(inout) :: ttend_t(ncol, nz)
// CHECK-NEXT:      character(kind=c_char, len=1), intent(out) :: scheme_name(*)
// CHECK-NEXT:      character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK-NEXT:      integer(c_int),               intent(out) :: errflg
// CHECK-NEXT:      integer :: i
// CHECK-NEXT:      character(len=64)  :: scheme_name_f
// CHECK-NEXT:      character(len=512) :: errmsg_f
// CHECK:           errmsg_f = ' '
// CHECK-NEXT:      scheme_name_f = ' '
// CHECK-NEXT:      errflg = 0
// CHECK-NEXT:      call kessler_suite_suite_physics( &
// CHECK-NEXT:          ncol, nz, real(dt, kind_phys), lyr_surf, lyr_toa, cpair, rair, rho,  &
// CHECK-NEXT:          z, exner, theta, qv, qc, qr, precl, relhum, temp_prev, ttend_t,  &
// CHECK-NEXT:          scheme_name_f, errmsg_f, errflg)
// CHECK-NEXT:      do i = 1, len_trim(scheme_name_f)
// CHECK-NEXT:        scheme_name(i) = scheme_name_f(i:i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      scheme_name(len_trim(scheme_name_f)+1) = c_null_char
// CHECK-NEXT:      do i = 1, len_trim(errmsg_f)
// CHECK-NEXT:        errmsg(i) = errmsg_f(i:i)
// CHECK-NEXT:      end do
// CHECK-NEXT:      errmsg(len_trim(errmsg_f)+1) = c_null_char
// CHECK-NEXT:    end subroutine Kessler_chost_physics_run
// CHECK:       end module Kessler_ccpp_chost_cap
// CHECK:       // -----
// CHECK-LABEL: // FILE: ccpp_kinds.F90
// CHECK-LABEL: module ccpp_kinds
// CHECK:         use ISO_FORTRAN_ENV, only: kind_phys => REAL64
// CHECK:         implicit none
// CHECK-NEXT:    private
// CHECK:         public :: kind_phys
// CHECK-NEXT:  end module ccpp_kinds
