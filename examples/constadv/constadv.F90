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

    call dyn_const(1)%instantiate( &
        std_name='water_vapor_specific_humidity', &
        long_name='Water vapor specific humidity', &
        units='kg kg-1', &
        default_val=0.0_kind_phys, &
        min_val=0.0_kind_phys, &
        is_advected=.true., &
        errmsg=errmsg, errflg=errflg)
    if (errflg /= 0) return

    call dyn_const(2)%instantiate( &
        std_name='cloud_ice_dry_mixing_ratio', &
        long_name='Cloud ice dry mixing ratio', &
        units='kg kg-1', &
        default_val=0.0_kind_phys, &
        min_val=0.0_kind_phys, &
        is_advected=.true., &
        errmsg=errmsg, errflg=errflg)

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
