module constadv

  use ccpp_kinds, only: kind_phys
  use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t

  implicit none
  private

  public :: constadv_register
  public :: constadv_run

contains

  subroutine constadv_register(dyn_const, errmsg, errflg)
    type(ccpp_constituent_properties_t), allocatable, intent(out) :: dyn_const(:)
    character(len=512), intent(out) :: errmsg
    integer,            intent(out) :: errflg

    errmsg = ''
    errflg = 0
    allocate(dyn_const(2), stat=errflg)
    if (errflg /= 0) then
      errmsg = 'constadv_register: allocate failed'
      return
    end if

    dyn_const(1)%std_name         = 'water_vapor_specific_humidity'
    dyn_const(1)%long_name        = 'Water vapor specific humidity'
    dyn_const(1)%units            = 'kg kg-1'
    dyn_const(1)%default_val      = 0.0_kind_phys
    dyn_const(1)%min_val          = 0.0_kind_phys
    dyn_const(1)%is_advected_flag = .true.

    dyn_const(2)%std_name         = 'cloud_ice_dry_mixing_ratio'
    dyn_const(2)%long_name        = 'Cloud ice dry mixing ratio'
    dyn_const(2)%units            = 'kg kg-1'
    dyn_const(2)%default_val      = 0.0_kind_phys
    dyn_const(2)%min_val          = 0.0_kind_phys
    dyn_const(2)%is_advected_flag = .true.

  end subroutine constadv_register

  subroutine constadv_run(ncol, nz, ncnst, q, errmsg, errflg)
    integer,            intent(in)    :: ncol
    integer,            intent(in)    :: nz
    integer,            intent(in)    :: ncnst
    real(kind_phys),    intent(inout) :: q(:, :, :)
    character(len=512), intent(out)   :: errmsg
    integer,            intent(out)   :: errflg
    integer :: k, n

    errmsg = ''
    errflg = 0
    do n = 1, ncnst
      do k = 1, nz
        q(1:ncol, k, n) = q(1:ncol, k, n) * 2.0_kind_phys
      end do
    end do

  end subroutine constadv_run

end module constadv
