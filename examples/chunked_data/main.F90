program test_chunked_data

  use, intrinsic :: iso_fortran_env, only: error_unit

  use data, only: nchunks, &
      chunk_begin, &
      chunk_end, &
      ncols, &
      nchunk
  use data, only: chunked_data_instance

  use test_host_ccpp_cap, only: ccpp_register, &
      ccpp_init, &
      ccpp_physics_timestep_init, &
      ccpp_physics_run, &
      ccpp_physics_timestep_final, &
      ccpp_final

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

  call ccpp_register(ccpp_suite, errmsg, errflg)
  if (errflg/=0) then
    write(error_unit, '(a)') "An error occurred in ccpp_register:"
    write(error_unit, '(a)') trim(errmsg)
    stop 1
  end if

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

  do nchunk = 1, nchunks
    lb=chunk_begin(nchunk)
    ub=chunk_end(nchunk)
    call ccpp_physics_run(ccpp_suite, ccpp_group, lb, ub, &
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

  call chunked_data_instance%destroy()

  write(*, '(a)') 'chunked_data: TEST PASSED'

end program test_chunked_data
