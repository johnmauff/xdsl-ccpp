! constprop — minimal scheme that registers one constituent property.
! Used to test gap 4c: chost cap generation for constituent DDT arrays.
module constprop

  use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t
  use ccpp_kinds, only: kind_phys
  implicit none
  private
  public :: constprop_register
  public :: constprop_run

contains

  subroutine constprop_register(dyn_const, errmsg, errflg)
    type(ccpp_constituent_properties_t), allocatable, intent(out) :: dyn_const(:)
    character(len=512), intent(out) :: errmsg
    integer,            intent(out) :: errflg

    errflg = 0
    errmsg = ''
    allocate(dyn_const(1))
    dyn_const(1)%std_name         = 'water_vapor_specific_humidity'
    dyn_const(1)%long_name        = 'Water vapour specific humidity'
    dyn_const(1)%units            = 'kg kg-1'
    dyn_const(1)%default_val      = 0.0_kind_phys
    dyn_const(1)%min_val          = 0.0_kind_phys
    dyn_const(1)%is_advected_flag = .true.
  end subroutine constprop_register

  ! Scale temperatures in the active chunk by 2x so the driver can verify.
  subroutine constprop_run(ncol, nz, temp, errmsg, errflg)
    integer,            intent(in)    :: ncol, nz
    real(kind_phys),    intent(inout) :: temp(:, :)
    character(len=512), intent(out)   :: errmsg
    integer,            intent(out)   :: errflg

    errflg = 0
    errmsg = ''
    temp(1:ncol, :) = temp(1:ncol, :) * 2.0_kind_phys
  end subroutine constprop_run

end module constprop
