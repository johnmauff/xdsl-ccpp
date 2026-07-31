! Stub implementation of ccpp_constituent_prop_mod for standalone compilation.
! The real module is part of the CCPP framework library.
!
! Field order of ccpp_constituent_properties_t is kept identical to the original
! stub (std_name, long_name, units, ...) so that .mod files from earlier partial
! builds stay compatible.  New fields (default_val_set, molar_mass_val,
! thermo_active) are appended at the end.
!
! ccpp_constituent_properties_t does NOT bind a procedure named 'long_name'
! (that would conflict with the 'long_name' data component); ptr methods access
! the field directly via this%ptr%long_name.
module ccpp_constituent_prop_mod
  use ccpp_kinds, only: kind_phys
  implicit none
  private

  integer, parameter, public :: int_unassigned = -1

  type, public :: ccpp_constituent_properties_t
    ! Original field order — must not change (generated cap accesses std_name,
    ! units by name; gfortran mod compatibility requires stable layout order).
    character(len=128) :: std_name          = ''
    character(len=128) :: long_name         = ''
    character(len=32)  :: units             = ''
    real(kind_phys)    :: default_val       = 0.0_kind_phys
    real(kind_phys)    :: min_val           = 0.0_kind_phys
    logical            :: is_advected_flag  = .false.
    logical            :: is_water          = .false.
    character(len=32)  :: mix_ratio_type    = ''
    character(len=64)  :: vert_dim          = ''
    ! New fields appended at end.
    logical            :: default_val_set   = .false.
    real(kind_phys)    :: molar_mass_val    = 0.0_kind_phys
    logical            :: thermo_active     = .false.
  contains
    procedure :: instantiate
    procedure :: standard_name => cp_standard_name
    procedure :: default_value => cp_default_value
    procedure :: is_advected   => cp_is_advected
  end type ccpp_constituent_properties_t

  type, public :: ccpp_constituent_prop_ptr_t
    type(ccpp_constituent_properties_t), pointer :: ptr => null()
  contains
    procedure :: standard_name        => ptr_standard_name
    procedure :: long_name            => ptr_long_name
    procedure :: is_mass_mixing_ratio => ptr_is_mass_mixing_ratio
    procedure :: is_dry               => ptr_is_dry
    procedure :: is_wet               => ptr_is_wet
    procedure :: is_moist             => ptr_is_moist
    procedure :: minimum              => ptr_minimum
    procedure :: set_minimum          => ptr_set_minimum
    procedure :: molar_mass           => ptr_molar_mass
    procedure :: set_molar_mass       => ptr_set_molar_mass
    procedure :: is_thermo_active     => ptr_is_thermo_active
    procedure :: set_thermo_active    => ptr_set_thermo_active
    procedure :: is_water_species     => ptr_is_water_species
    procedure :: set_water_species    => ptr_set_water_species
    procedure :: has_default          => ptr_has_default
    procedure :: default_value        => ptr_default_value
  end type ccpp_constituent_prop_ptr_t

contains

  ! ── ccpp_constituent_properties_t ───────────────────────────────────────────

  subroutine instantiate(this, std_name, long_name, units, errcode, errmsg, &
                         default_value, min_value, molar_mass, advected,    &
                         vertical_dim, water_species, mixing_ratio_type)
    class(ccpp_constituent_properties_t), intent(inout) :: this
    character(len=*), intent(in)           :: std_name
    character(len=*), intent(in)           :: long_name
    character(len=*), intent(in)           :: units
    integer,          intent(out)          :: errcode
    character(len=*), intent(out)          :: errmsg
    real(kind_phys),  intent(in), optional :: default_value
    real(kind_phys),  intent(in), optional :: min_value
    real(kind_phys),  intent(in), optional :: molar_mass
    logical,          intent(in), optional :: advected
    character(len=*), intent(in), optional :: vertical_dim
    logical,          intent(in), optional :: water_species
    character(len=*), intent(in), optional :: mixing_ratio_type
    this%std_name      = std_name
    this%long_name     = long_name
    this%units         = units
    if (present(default_value)) then
      this%default_val     = default_value
      this%default_val_set = .true.
    end if
    if (present(min_value))        this%min_val          = min_value
    if (present(molar_mass))       this%molar_mass_val   = molar_mass
    if (present(advected))         this%is_advected_flag = advected
    if (present(vertical_dim))     this%vert_dim         = vertical_dim
    if (present(water_species))    this%is_water         = water_species
    if (present(mixing_ratio_type)) this%mix_ratio_type  = mixing_ratio_type
    errcode = 0
    errmsg  = ''
  end subroutine instantiate

  subroutine cp_standard_name(this, name, errcode, errmsg)
    class(ccpp_constituent_properties_t), intent(in)  :: this
    character(len=*), intent(out) :: name
    integer,          intent(out) :: errcode
    character(len=*), intent(out) :: errmsg
    name = trim(this%std_name); errcode = 0; errmsg = ''
  end subroutine cp_standard_name

  subroutine cp_default_value(this, val, errcode, errmsg)
    class(ccpp_constituent_properties_t), intent(in)  :: this
    real(kind_phys),  intent(out) :: val
    integer,          intent(out) :: errcode
    character(len=*), intent(out) :: errmsg
    val = this%default_val; errcode = 0; errmsg = ''
  end subroutine cp_default_value

  subroutine cp_is_advected(this, adv, errcode, errmsg)
    class(ccpp_constituent_properties_t), intent(in)  :: this
    logical,          intent(out) :: adv
    integer,          intent(out) :: errcode
    character(len=*), intent(out) :: errmsg
    adv = this%is_advected_flag; errcode = 0; errmsg = ''
  end subroutine cp_is_advected

  ! ── ccpp_constituent_prop_ptr_t — all methods access ptr fields directly ─────

  subroutine ptr_standard_name(this, name, errcode, errmsg)
    class(ccpp_constituent_prop_ptr_t), intent(in)  :: this
    character(len=*), intent(out) :: name
    integer,          intent(out) :: errcode
    character(len=*), intent(out) :: errmsg
    name = trim(this%ptr%std_name); errcode = 0; errmsg = ''
  end subroutine ptr_standard_name

  subroutine ptr_long_name(this, name, errcode, errmsg)
    class(ccpp_constituent_prop_ptr_t), intent(in)  :: this
    character(len=*), intent(out) :: name
    integer,          intent(out) :: errcode
    character(len=*), intent(out) :: errmsg
    name = trim(this%ptr%long_name); errcode = 0; errmsg = ''
  end subroutine ptr_long_name

  subroutine ptr_is_mass_mixing_ratio(this, val, errcode, errmsg)
    class(ccpp_constituent_prop_ptr_t), intent(in)  :: this
    logical,          intent(out) :: val
    integer,          intent(out) :: errcode
    character(len=*), intent(out) :: errmsg
    val = .true.; errcode = 0; errmsg = ''
  end subroutine ptr_is_mass_mixing_ratio

  subroutine ptr_is_dry(this, val, errcode, errmsg)
    class(ccpp_constituent_prop_ptr_t), intent(in)  :: this
    logical,          intent(out) :: val
    integer,          intent(out) :: errcode
    character(len=*), intent(out) :: errmsg
    ! Explicit 'dry' type, or infer from standard name containing '_dry_'
    val = (trim(this%ptr%mix_ratio_type) == 'dry') .or. &
          (trim(this%ptr%mix_ratio_type) == '' .and. &
           index(this%ptr%std_name, '_dry_') > 0)
    errcode = 0; errmsg = ''
  end subroutine ptr_is_dry

  subroutine ptr_is_wet(this, val, errcode, errmsg)
    class(ccpp_constituent_prop_ptr_t), intent(in)  :: this
    logical,          intent(out) :: val
    integer,          intent(out) :: errcode
    character(len=*), intent(out) :: errmsg
    val = (trim(this%ptr%mix_ratio_type) == 'wet'); errcode = 0; errmsg = ''
  end subroutine ptr_is_wet

  subroutine ptr_is_moist(this, val, errcode, errmsg)
    class(ccpp_constituent_prop_ptr_t), intent(in)  :: this
    logical,          intent(out) :: val
    integer,          intent(out) :: errcode
    character(len=*), intent(out) :: errmsg
    ! Moist when neither dry (explicit or name-inferred) nor wet
    val = .not. ((trim(this%ptr%mix_ratio_type) == 'dry') .or. &
                 (trim(this%ptr%mix_ratio_type) == '' .and. &
                  index(this%ptr%std_name, '_dry_') > 0)) .and. &
          .not. (trim(this%ptr%mix_ratio_type) == 'wet')
    errcode = 0; errmsg = ''
  end subroutine ptr_is_moist

  subroutine ptr_minimum(this, val, errcode, errmsg)
    class(ccpp_constituent_prop_ptr_t), intent(in)  :: this
    real(kind_phys),  intent(out) :: val
    integer,          intent(out) :: errcode
    character(len=*), intent(out) :: errmsg
    val = this%ptr%min_val; errcode = 0; errmsg = ''
  end subroutine ptr_minimum

  subroutine ptr_set_minimum(this, val, errcode, errmsg)
    class(ccpp_constituent_prop_ptr_t), intent(inout) :: this
    real(kind_phys),  intent(in)  :: val
    integer,          intent(out) :: errcode
    character(len=*), intent(out) :: errmsg
    this%ptr%min_val = val; errcode = 0; errmsg = ''
  end subroutine ptr_set_minimum

  subroutine ptr_molar_mass(this, val, errcode, errmsg)
    class(ccpp_constituent_prop_ptr_t), intent(in)  :: this
    real(kind_phys),  intent(out) :: val
    integer,          intent(out) :: errcode
    character(len=*), intent(out) :: errmsg
    val = this%ptr%molar_mass_val; errcode = 0; errmsg = ''
  end subroutine ptr_molar_mass

  subroutine ptr_set_molar_mass(this, val, errcode, errmsg)
    class(ccpp_constituent_prop_ptr_t), intent(inout) :: this
    real(kind_phys),  intent(in)  :: val
    integer,          intent(out) :: errcode
    character(len=*), intent(out) :: errmsg
    this%ptr%molar_mass_val = val; errcode = 0; errmsg = ''
  end subroutine ptr_set_molar_mass

  subroutine ptr_is_thermo_active(this, val, errcode, errmsg)
    class(ccpp_constituent_prop_ptr_t), intent(in)  :: this
    logical,          intent(out) :: val
    integer,          intent(out) :: errcode
    character(len=*), intent(out) :: errmsg
    val = this%ptr%thermo_active; errcode = 0; errmsg = ''
  end subroutine ptr_is_thermo_active

  subroutine ptr_set_thermo_active(this, val, errcode, errmsg)
    class(ccpp_constituent_prop_ptr_t), intent(inout) :: this
    logical,          intent(in)  :: val
    integer,          intent(out) :: errcode
    character(len=*), intent(out) :: errmsg
    this%ptr%thermo_active = val; errcode = 0; errmsg = ''
  end subroutine ptr_set_thermo_active

  subroutine ptr_is_water_species(this, val, errcode, errmsg)
    class(ccpp_constituent_prop_ptr_t), intent(in)  :: this
    logical,          intent(out) :: val
    integer,          intent(out) :: errcode
    character(len=*), intent(out) :: errmsg
    val = this%ptr%is_water; errcode = 0; errmsg = ''
  end subroutine ptr_is_water_species

  subroutine ptr_set_water_species(this, val, errcode, errmsg)
    class(ccpp_constituent_prop_ptr_t), intent(inout) :: this
    logical,          intent(in)  :: val
    integer,          intent(out) :: errcode
    character(len=*), intent(out) :: errmsg
    this%ptr%is_water = val; errcode = 0; errmsg = ''
  end subroutine ptr_set_water_species

  subroutine ptr_has_default(this, val, errcode, errmsg)
    class(ccpp_constituent_prop_ptr_t), intent(in)  :: this
    logical,          intent(out) :: val
    integer,          intent(out) :: errcode
    character(len=*), intent(out) :: errmsg
    val = this%ptr%default_val_set; errcode = 0; errmsg = ''
  end subroutine ptr_has_default

  subroutine ptr_default_value(this, val, errcode, errmsg)
    class(ccpp_constituent_prop_ptr_t), intent(in)  :: this
    real(kind_phys),  intent(out) :: val
    integer,          intent(out) :: errcode
    character(len=*), intent(out) :: errmsg
    val = this%ptr%default_val; errcode = 0; errmsg = ''
  end subroutine ptr_default_value

end module ccpp_constituent_prop_mod
