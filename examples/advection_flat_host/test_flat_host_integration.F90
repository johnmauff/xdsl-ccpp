! Minimal verification driver for advection_flat_host.
!
! Calls the generated cap's full lifecycle (register -> initialize ->
! timestep_initial -> run -> timestep_final -> finalize) once, then checks
! two things using only the data the host itself owns (temp/qv in
! flat_host_mod -- the generated cap's own lc_* scratch/tendency arrays are
! private to it and not observable from here):
!
!   1. errflg stays 0 after every lifecycle call.
!   2. Level 1 (initialized well below tcld) shows the expected physical
!      change (qv decreases, temp increases -- condensation/freezing with
!      latent heat release), while every other level (initialized well
!      above tcld) is untouched. This proves data actually flows from the
!      host arrays into the schemes and back, not just that nothing crashed.
program test_flat_host_integration

   use ccpp_kinds,        only: kind_phys
   use flat_host_mod,     only: init_data, temp, qv, ncols, pver
   use flat_host_ccpp_cap, only:                                             &
        flat_host_ccpp_physics_register,                                    &
        flat_host_ccpp_physics_initialize,                                  &
        flat_host_ccpp_physics_timestep_initial,                            &
        flat_host_ccpp_physics_run,                                         &
        flat_host_ccpp_physics_timestep_final,                              &
        flat_host_ccpp_physics_finalize,                                    &
        ccpp_physics_suite_part_list

   implicit none

   character(len=*), parameter :: suite_name = 'flat_cld_suite'
   character(len=512)          :: errmsg
   integer                     :: errflg
   character(len=:), allocatable :: part_list(:)
   integer                     :: ipart
   integer                     :: col_start, col_end
   real(kind_phys)             :: qv1_before, temp1_before
   real(kind_phys)             :: qv2_before, temp2_before
   logical                     :: passed

   passed = .true.
   col_start = 1
   col_end   = ncols

   call init_data()

   qv1_before   = qv(1, 1)
   temp1_before = temp(1, 1)
   qv2_before   = qv(1, 2)
   temp2_before = temp(1, 2)

   call check('register', flat_host_ccpp_physics_register_wrap())
   call check('initialize', flat_host_ccpp_physics_initialize_wrap())
   call check('timestep_initial', flat_host_ccpp_physics_timestep_initial_wrap())

   call ccpp_physics_suite_part_list(suite_name, part_list, errmsg, errflg)
   call check('suite_part_list', errflg == 0)
   if (errflg /= 0) then
      write(6, '(a)') trim(errmsg)
   end if

   do ipart = 1, size(part_list)
      call flat_host_ccpp_physics_run(suite_name, trim(part_list(ipart)),    &
           col_start, col_end, errmsg, errflg)
      call check('run(' // trim(part_list(ipart)) // ')', errflg == 0)
      if (errflg /= 0) then
         write(6, '(a)') trim(errmsg)
      end if
   end do

   call check('timestep_final', flat_host_ccpp_physics_timestep_final_wrap())
   call check('finalize', flat_host_ccpp_physics_finalize_wrap())

   ! Level 1 (below tcld): expect condensation/freezing to have fired.
   if (.not. (qv(1, 1) < qv1_before)) then
      write(6, '(a,es15.7,a,es15.7)') 'FAIL: qv(1,1) did not decrease: ',    &
           qv1_before, ' -> ', qv(1, 1)
      passed = .false.
   end if
   if (.not. (temp(1, 1) > temp1_before)) then
      write(6, '(a,es15.7,a,es15.7)') 'FAIL: temp(1,1) did not increase: ',  &
           temp1_before, ' -> ', temp(1, 1)
      passed = .false.
   end if

   ! Level 2 (above tcld): expect no change at all.
   if (qv(1, 2) /= qv2_before) then
      write(6, '(a,es15.7,a,es15.7)') 'FAIL: qv(1,2) changed unexpectedly: ',&
           qv2_before, ' -> ', qv(1, 2)
      passed = .false.
   end if
   if (temp(1, 2) /= temp2_before) then
      write(6, '(a,es15.7,a,es15.7)') 'FAIL: temp(1,2) changed unexpectedly: ', &
           temp2_before, ' -> ', temp(1, 2)
      passed = .false.
   end if

   if (passed) then
      write(6, '(a)') 'advection_flat_host: TEST PASSED'
      STOP 0
   else
      write(6, '(a)') 'advection_flat_host: TEST FAILED'
      STOP 1
   end if

contains

   subroutine check(step_name, ok)
      character(len=*), intent(in) :: step_name
      logical,          intent(in) :: ok

      if (.not. ok) then
         write(6, '(3a)') 'FAIL: lifecycle step "', trim(step_name), '" reported errflg /= 0'
         passed = .false.
      end if
   end subroutine check

   ! Small wrappers so each lifecycle call site can be passed to check() as
   ! a single boolean expression instead of repeating the errmsg/errflg
   ! boilerplate at every call site.
   logical function flat_host_ccpp_physics_register_wrap()
      call flat_host_ccpp_physics_register(suite_name, errmsg, errflg)
      flat_host_ccpp_physics_register_wrap = (errflg == 0)
      if (errflg /= 0) write(6, '(a)') trim(errmsg)
   end function flat_host_ccpp_physics_register_wrap

   logical function flat_host_ccpp_physics_initialize_wrap()
      call flat_host_ccpp_physics_initialize(suite_name, errmsg, errflg)
      flat_host_ccpp_physics_initialize_wrap = (errflg == 0)
      if (errflg /= 0) write(6, '(a)') trim(errmsg)
   end function flat_host_ccpp_physics_initialize_wrap

   logical function flat_host_ccpp_physics_timestep_initial_wrap()
      call flat_host_ccpp_physics_timestep_initial(suite_name, errmsg, errflg)
      flat_host_ccpp_physics_timestep_initial_wrap = (errflg == 0)
      if (errflg /= 0) write(6, '(a)') trim(errmsg)
   end function flat_host_ccpp_physics_timestep_initial_wrap

   logical function flat_host_ccpp_physics_timestep_final_wrap()
      call flat_host_ccpp_physics_timestep_final(suite_name, errmsg, errflg)
      flat_host_ccpp_physics_timestep_final_wrap = (errflg == 0)
      if (errflg /= 0) write(6, '(a)') trim(errmsg)
   end function flat_host_ccpp_physics_timestep_final_wrap

   logical function flat_host_ccpp_physics_finalize_wrap()
      call flat_host_ccpp_physics_finalize(suite_name, errmsg, errflg)
      flat_host_ccpp_physics_finalize_wrap = (errflg == 0)
      if (errflg /= 0) write(6, '(a)') trim(errmsg)
   end function flat_host_ccpp_physics_finalize_wrap

end program test_flat_host_integration
