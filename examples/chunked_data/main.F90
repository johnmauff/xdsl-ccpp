program test_chunked_data

  use, intrinsic :: iso_fortran_env, only: error_unit

  use data, only: nchunks, &
      chunk_begin, &
      chunk_end, &
      ncols, &
      nchunk
  use data, only: chunked_data_instance

  use test_host_ccpp_cap, only: test_host_ccpp_physics_register, &
      test_host_ccpp_physics_initialize, &
      test_host_ccpp_physics_timestep_initial, &
      test_host_ccpp_physics_run, &
      test_host_ccpp_physics_timestep_final, &
      test_host_ccpp_physics_finalize

  implicit none

  character(len=*), parameter :: ccpp_suite = 'chunked_data_suite'
  character(len=*), parameter :: ccpp_group = 'chunked_data_group'
  integer :: lb, ub
  integer :: errflg
  character(len=512) :: errmsg

  call chunked_data_instance%create(ncols)

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP register step                             !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  call test_host_ccpp_physics_register(ccpp_suite, errmsg, errflg)
  if (errflg/=0) then
    write(error_unit, '(a)') "An error occurred in ccpp_register:"
    write(error_unit, '(a)') trim(errmsg)
    stop 1
  end if

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP physics init step                         !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  call test_host_ccpp_physics_initialize(ccpp_suite, errmsg, errflg)
  if (errflg/=0) then
    write(error_unit, '(a)') "An error occurred in ccpp_physics_init:"
    write(error_unit, '(a)') trim(errmsg)
    stop 1
  end if

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP physics timestep init step                !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  call test_host_ccpp_physics_timestep_initial(ccpp_suite, errmsg, errflg)
  if (errflg/=0) then
    write(error_unit, '(a)') "An error occurred in ccpp_physics_timestep_init:"
    write(error_unit, '(a)') trim(errmsg)
    stop 1
  end if

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP physics run step                          !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  do nchunk = 1, nchunks
    lb=chunk_begin(nchunk)
    ub=chunk_end(nchunk)
    call test_host_ccpp_physics_run(ccpp_suite, ccpp_group, lb, ub, &
        chunked_data_instance%array_data(lb:ub), errmsg, errflg)
    if (errflg/=0) then
      write(error_unit, '(a,i3,a)') "An error occurred in ccpp_physics_run for chunk", nchunk, ":"
      write(error_unit, '(a)') trim(errmsg)
      stop 1
    end if
  end do

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP physics timestep finalize step            !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  call test_host_ccpp_physics_timestep_final(ccpp_suite, errmsg, errflg)
  if (errflg/=0) then
    write(error_unit, '(a)') "An error occurred in ccpp_physics_timestep_finalize:"
    write(error_unit, '(a)') trim(errmsg)
    stop 1
  end if

  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  ! CCPP physics finalize step                     !
  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!

  call test_host_ccpp_physics_finalize(ccpp_suite, errmsg, errflg)
  if (errflg/=0) then
    write(error_unit, '(a)') "An error occurred in ccpp_physics_finalize:"
    write(error_unit, '(a)') trim(errmsg)
    stop 1
  end if

  call chunked_data_instance%destroy()

  write(*, '(a)') 'chunked_data: TEST PASSED'

end program test_chunked_data
