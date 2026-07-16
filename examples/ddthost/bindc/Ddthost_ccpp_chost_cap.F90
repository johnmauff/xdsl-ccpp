module Ddthost_ccpp_chost_cap

  use ccpp_kinds, only: kind_phys
  use iso_c_binding
  use host_ccpp_ddt, only: ccpp_info_t
  use make_ddt, only: vmr_type
  use ddthost_suite_cap, only: ddthost_suite_suite_register
  use ddthost_suite_cap, only: ddthost_suite_suite_initialize
  use ddthost_suite_cap, only: ddthost_suite_suite_finalize
  use ddthost_suite_cap, only: ddthost_suite_suite_timestep_initial
  use ddthost_suite_cap, only: ddthost_suite_suite_timestep_final
  use ddthost_suite_cap, only: ddthost_suite_suite_physics

  implicit none
  private

  public :: Ddthost_chost_physics_register
  public :: Ddthost_chost_physics_initialize
  public :: Ddthost_chost_physics_finalize
  public :: Ddthost_chost_physics_timestep_initial
  public :: Ddthost_chost_physics_timestep_final
  public :: Ddthost_chost_physics_run

contains

  subroutine Ddthost_chost_physics_register(errmsg, errflg) &
      bind(C, name='Ddthost_chost_physics_register')
    character(kind=c_char, len=1), intent(out) :: errmsg(*)
    integer(c_int),               intent(out) :: errflg
    integer :: i
    character(len=512) :: errmsg_f

    errmsg_f = ' '
    errflg = 0
    call ddthost_suite_suite_register(errflg, errmsg_f)
    do i = 1, len_trim(errmsg_f)
      errmsg(i) = errmsg_f(i:i)
    end do
    errmsg(len_trim(errmsg_f)+1) = c_null_char
  end subroutine Ddthost_chost_physics_register

  subroutine Ddthost_chost_physics_initialize( &
      ncols, vmr_nvmr, ccpp_info_col_start, ccpp_info_col_end, ccpp_info_errflg,  &
      vmr_vmr_array, errmsg, errflg) &
      bind(C, name='Ddthost_chost_physics_initialize')
    integer(c_int), value, intent(in) :: ncols
    integer(c_int), value, intent(in) :: vmr_nvmr
    integer(c_int), value, intent(in) :: ccpp_info_col_start
    integer(c_int), value, intent(in) :: ccpp_info_col_end
    integer(c_int), value, intent(in) :: ccpp_info_errflg
    real(c_double), target, intent(out) :: vmr_vmr_array(ncols, vmr_nvmr)
    character(kind=c_char, len=1), intent(out) :: errmsg(*)
    integer(c_int),               intent(out) :: errflg
    integer :: i
    character(len=512) :: errmsg_f
    type(ccpp_info_t) :: ccpp_info_local
    type(vmr_type) :: vmr_local

    errmsg_f = ' '
    errflg = 0
    ccpp_info_local%errmsg = ' '
    ccpp_info_local%col_start = ccpp_info_col_start
    ccpp_info_local%col_end = ccpp_info_col_end
    ccpp_info_local%errflg = ccpp_info_errflg
    vmr_local%nvmr = vmr_nvmr
    call ddthost_suite_suite_initialize( &
        ncols, ccpp_info_local, vmr_local, errmsg_f, errflg)
    vmr_vmr_array = real(vmr_local%vmr_array, c_double)
    deallocate(vmr_local%vmr_array)
    do i = 1, len_trim(errmsg_f)
      errmsg(i) = errmsg_f(i:i)
    end do
    errmsg(len_trim(errmsg_f)+1) = c_null_char
  end subroutine Ddthost_chost_physics_initialize

  subroutine Ddthost_chost_physics_finalize(errmsg, errflg) &
      bind(C, name='Ddthost_chost_physics_finalize')
    character(kind=c_char, len=1), intent(out) :: errmsg(*)
    integer(c_int),               intent(out) :: errflg
    integer :: i
    character(len=512) :: errmsg_f

    errmsg_f = ' '
    errflg = 0
    call ddthost_suite_suite_finalize(errflg, errmsg_f)
    do i = 1, len_trim(errmsg_f)
      errmsg(i) = errmsg_f(i:i)
    end do
    errmsg(len_trim(errmsg_f)+1) = c_null_char
  end subroutine Ddthost_chost_physics_finalize

  subroutine Ddthost_chost_physics_timestep_initial(errmsg, errflg) &
      bind(C, name='Ddthost_chost_physics_timestep_initial')
    character(kind=c_char, len=1), intent(out) :: errmsg(*)
    integer(c_int),               intent(out) :: errflg
    integer :: i
    character(len=512) :: errmsg_f

    errmsg_f = ' '
    errflg = 0
    call ddthost_suite_suite_timestep_initial(errflg, errmsg_f)
    do i = 1, len_trim(errmsg_f)
      errmsg(i) = errmsg_f(i:i)
    end do
    errmsg(len_trim(errmsg_f)+1) = c_null_char
  end subroutine Ddthost_chost_physics_timestep_initial

  subroutine Ddthost_chost_physics_timestep_final( &
      ncols, vmr_nvmr, vmr_vmr_array, errmsg, errflg) &
      bind(C, name='Ddthost_chost_physics_timestep_final')
    integer(c_int), value, intent(in) :: ncols
    integer(c_int), value, intent(in) :: vmr_nvmr
    real(c_double), target, intent(in) :: vmr_vmr_array(ncols, vmr_nvmr)
    character(kind=c_char, len=1), intent(out) :: errmsg(*)
    integer(c_int),               intent(out) :: errflg
    integer :: i
    character(len=512) :: errmsg_f
    type(vmr_type) :: vmr_local

    errmsg_f = ' '
    errflg = 0
    vmr_local%nvmr = vmr_nvmr
    allocate(vmr_local%vmr_array(ncols, vmr_nvmr))
    vmr_local%vmr_array = real(vmr_vmr_array, kind_phys)
    call ddthost_suite_suite_timestep_final(ncols, vmr_local, errmsg_f, errflg)
    deallocate(vmr_local%vmr_array)
    do i = 1, len_trim(errmsg_f)
      errmsg(i) = errmsg_f(i:i)
    end do
    errmsg(len_trim(errmsg_f)+1) = c_null_char
  end subroutine Ddthost_chost_physics_timestep_final

  subroutine Ddthost_chost_physics_run( &
      ncols, vmr_nvmr, col_start, col_end, O3, HNO3, vmr_vmr_array, errmsg, errflg) &
      bind(C, name='Ddthost_chost_physics_run')
    integer(c_int), value, intent(in) :: ncols
    integer(c_int), value, intent(in) :: vmr_nvmr
    integer(c_int), value, intent(in) :: col_start
    integer(c_int), value, intent(in) :: col_end
    real(c_double), target, intent(in) :: O3(ncols)
    real(c_double), target, intent(in) :: HNO3(ncols)
    real(c_double), target, intent(inout) :: vmr_vmr_array(ncols, vmr_nvmr)
    character(kind=c_char, len=1), intent(out) :: errmsg(*)
    integer(c_int),               intent(out) :: errflg
    integer :: i
    character(len=512) :: errmsg_f
    type(vmr_type) :: vmr_local

    errmsg_f = ' '
    errflg = 0
    vmr_local%nvmr = vmr_nvmr
    allocate(vmr_local%vmr_array(ncols, vmr_nvmr))
    vmr_local%vmr_array = real(vmr_vmr_array, kind_phys)
    call ddthost_suite_suite_physics( &
        col_start, col_end, O3, HNO3, vmr_local, errmsg_f, errflg)
    vmr_vmr_array = real(vmr_local%vmr_array, c_double)
    deallocate(vmr_local%vmr_array)
    do i = 1, len_trim(errmsg_f)
      errmsg(i) = errmsg_f(i:i)
    end do
    errmsg(len_trim(errmsg_f)+1) = c_null_char
  end subroutine Ddthost_chost_physics_run

end module Ddthost_ccpp_chost_cap
