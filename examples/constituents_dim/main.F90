program test_constituents_dim

  use, intrinsic :: iso_fortran_env, only: output_unit, &
      error_unit

  use ccpp_kinds, only: kind_phys
  use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t

  use host_data, only: ncols, &
      pver, &
      coupler_flux

  use test_host_ccpp_cap, only: ccpp_register, &
      ccpp_init, &
      ccpp_physics_timestep_init, &
      ccpp_physics_run, &
      ccpp_physics_timestep_final, &
      ccpp_final, &
      test_host_ccpp_register_constituents, &
      test_host_ccpp_number_constituents, &
      test_host_ccpp_initialize_constituents, &
      test_host_ccpp_deallocate_dynamic_constituents

  implicit none

  character(len=*), parameter :: ccpp_suite = 'constituents_dim_suite'
  character(len=*), parameter :: ccpp_group = 'const_group'
  character(len=512) :: errmsg
  integer :: errflg
  integer :: num_const
  integer :: m, i
  type(ccpp_constituent_properties_t), allocatable, target :: host_constituents(:)

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP register step                             !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  ! register_consts_register registers 3 dynamic constituents, which is what
  ! gives the suite a non-trivial number_of_ccpp_constituents.
  call ccpp_register(ccpp_suite, errmsg, errflg)
  if (errflg/=0) then
    write(error_unit, '(a)') "An error occurred in ccpp_register:"
    write(error_unit, '(a)') trim(errmsg)
    stop 1
  end if

  ! This test registers all constituents on the scheme side; the host adds none.
  allocate(host_constituents(0))
  call test_host_ccpp_register_constituents(host_constituents, errmsg, errflg)
  if (errflg/=0) then
    write(error_unit, '(a)') "An error occurred in ccpp_register_constituents:"
    write(error_unit, '(a)') trim(errmsg)
    stop 1
  end if

  call test_host_ccpp_number_constituents(num_const, errmsg, errflg)
  if (errflg/=0) then
    write(error_unit, '(a)') "An error occurred in ccpp_number_constituents:"
    write(error_unit, '(a)') trim(errmsg)
    stop 1
  end if
  if (num_const < 1) then
    write(error_unit, '(a,i0)') &
        'Error: expected at least one constituent, got ', num_const
    stop 1
  end if

  call test_host_ccpp_initialize_constituents(ncols, pver, errflg, errmsg)
  if (errflg/=0) then
    write(error_unit, '(a)') "An error occurred in ccpp_initialize_constituents:"
    write(error_unit, '(a)') trim(errmsg)
    stop 1
  end if

  ! Case 1: the host owns coupler_flux and sizes it to the constituent count.
  ! capgen passes the whole constituent axis (':') to const_dim_producer_run.
  allocate(coupler_flux(ncols, num_const))
  do m = 1, num_const
    do i = 1, ncols
      coupler_flux(i, m) = real(m, kind_phys)
    end do
  end do

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP physics init step                         !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  call ccpp_init(ccpp_suite, errmsg, errflg)
  if (errflg/=0) then
    write(error_unit, '(a)') "An error occurred in ccpp_physics_init:"
    write(error_unit, '(a)') trim(errmsg)
    stop 1
  end if

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP physics timestep init step                !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  call ccpp_physics_timestep_init(ccpp_suite, errmsg, errflg)
  if (errflg/=0) then
    write(error_unit, '(a)') "An error occurred in ccpp_physics_timestep_init:"
    write(error_unit, '(a)') trim(errmsg)
    stop 1
  end if

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP physics run step                          !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  ! Producer fills/allocates the workspaces and checks Case 1; consumer verifies
  ! Cases 2a/2b.  Any mismatch sets errflg inside the schemes.
  call ccpp_physics_run(ccpp_suite, ccpp_group, 1, ncols, coupler_flux, &
      errmsg, errflg)
  if (errflg/=0) then
    write(error_unit, '(a)') "An error occurred in ccpp_physics_run:"
    write(error_unit, '(a)') trim(errmsg)
    stop 1
  end if

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP physics timestep finalize step            !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  call ccpp_physics_timestep_final(ccpp_suite, errmsg, errflg)
  if (errflg/=0) then
    write(error_unit, '(a)') "An error occurred in ccpp_physics_timestep_finalize:"
    write(error_unit, '(a)') trim(errmsg)
    stop 1
  end if

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP physics finalize step                     !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  call ccpp_final(ccpp_suite, errmsg, errflg)
  if (errflg/=0) then
    write(error_unit, '(a)') "An error occurred in ccpp_physics_finalize:"
    write(error_unit, '(a)') trim(errmsg)
    stop 1
  end if

  call test_host_ccpp_deallocate_dynamic_constituents()
  deallocate(host_constituents)
  if (allocated(coupler_flux)) deallocate(coupler_flux)

  write(output_unit, '(a,i0,a)') &
      'PASS: constituents_dim (number_of_ccpp_constituents = ', num_const, ')'

end program test_constituents_dim
