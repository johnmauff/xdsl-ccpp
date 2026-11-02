! Scheme I/O capture of the CCPP constituent properties
! (ccpp_constituent_prop_ptr_t arrays, e.g. geopotential_temp's cprops),
! on top of ccpp_capture_mod -- kept apart so that module needs no
! framework types.
!
! Writing (generated caps, between ccpp_capture_begin(table, 'before') and
! ccpp_capture_end): ccpp_capture_constituents(name, props) writes subgroup
! in/<name> with one variable per property along dimension
! number_of_ccpp_constituents: standard_name, long_name, diagnostic_name,
! units, vertical_dimension, mixing_ratio_type ('dry', 'moist' or 'wet'),
! const_index, advected, thermo_active, water_species, has_default,
! default_value, minimum, molar_mass. A property its getter cannot return
! is written as blank / zero / .false. (a capture never aborts the model).
!
! Reading (generated test drivers): ccpp_capture_read_constituents(group,
! name, props) rebuilds the array from <group>/<name> of the open call:
! each element is instantiated from the captured properties and its
! constituent index and thermo-active flag set, as the host does. The
! properties live in this module (props points at them) until the next
! read. Constituent properties are intent(in) only, so there is nothing
! to compare.
module ccpp_capture_constituents_mod

  use ccpp_kinds, only: kind_phys
  use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t, &
                                       ccpp_constituent_prop_ptr_t
  use ccpp_capture_mod, only: ccpp_capture, ccpp_capture_read, ccpp_capture_extents, &
                              ccpp_capture_begin_ddt, ccpp_capture_end_ddt

  implicit none
  private

  public :: ccpp_capture_constituents
  public :: ccpp_capture_read_constituents

  integer, parameter :: name_len = 256
  character(len=*), parameter :: dim_name = 'number_of_ccpp_constituents'

  ! The properties a read rebuilt; the returned pointers point at them.
  type(ccpp_constituent_properties_t), allocatable, target, save :: lc_props(:)

contains

  subroutine ccpp_capture_constituents(name, props)
    character(len=*), intent(in) :: name
    type(ccpp_constituent_prop_ptr_t), intent(in) :: props(:)
    character(len=name_len) :: std_name(size(props)), long_name(size(props))
    character(len=name_len) :: diag_name(size(props)), units(size(props))
    character(len=name_len) :: vert_dim(size(props))
    character(len=8) :: mixing_ratio_type(size(props))
    integer :: const_index(size(props))
    logical :: advected(size(props)), thermo_active(size(props))
    logical :: water_species(size(props)), has_default(size(props))
    real(kind_phys) :: default_value(size(props)), minimum(size(props))
    real(kind_phys) :: molar_mass(size(props))
    logical :: flag
    integer :: i, errcode
    character(len=512) :: errmsg

    std_name = ''
    long_name = ''
    diag_name = ''
    units = ''
    vert_dim = ''
    mixing_ratio_type = ''
    const_index = 0
    advected = .false.
    thermo_active = .false.
    water_species = .false.
    has_default = .false.
    default_value = 0.0_kind_phys
    minimum = 0.0_kind_phys
    molar_mass = 0.0_kind_phys
    do i = 1, size(props)
      call props(i)%standard_name(std_name(i), errcode, errmsg)
      if (errcode /= 0) cycle  ! no properties behind this pointer
      call props(i)%long_name(long_name(i), errcode, errmsg)
      call props(i)%diagnostic_name(diag_name(i), errcode, errmsg)
      call props(i)%units(units(i), errcode, errmsg)
      call props(i)%vertical_dimension(vert_dim(i), errcode, errmsg)
      call props(i)%const_index(const_index(i), errcode, errmsg)
      call props(i)%is_advected(advected(i), errcode, errmsg)
      call props(i)%is_thermo_active(thermo_active(i), errcode, errmsg)
      call props(i)%is_water_species(water_species(i), errcode, errmsg)
      call props(i)%has_default(has_default(i), errcode, errmsg)
      call props(i)%default_value(default_value(i), errcode, errmsg)
      call props(i)%minimum(minimum(i), errcode, errmsg)
      call props(i)%molar_mass(molar_mass(i), errcode, errmsg)
      call props(i)%is_dry(flag, errcode, errmsg)
      if (flag) mixing_ratio_type(i) = 'dry'
      call props(i)%is_moist(flag, errcode, errmsg)
      if (flag) mixing_ratio_type(i) = 'moist'
      call props(i)%is_wet(flag, errcode, errmsg)
      if (flag) mixing_ratio_type(i) = 'wet'
    end do

    call ccpp_capture_begin_ddt(name)
    call ccpp_capture('standard_name', std_name, dim_names=dim_name)
    call ccpp_capture('long_name', long_name, dim_names=dim_name)
    call ccpp_capture('diagnostic_name', diag_name, dim_names=dim_name)
    call ccpp_capture('units', units, dim_names=dim_name)
    call ccpp_capture('vertical_dimension', vert_dim, dim_names=dim_name)
    call ccpp_capture('mixing_ratio_type', mixing_ratio_type, dim_names=dim_name)
    call ccpp_capture('const_index', const_index, dim_names=dim_name)
    call ccpp_capture('advected', advected, dim_names=dim_name)
    call ccpp_capture('thermo_active', thermo_active, dim_names=dim_name)
    call ccpp_capture('water_species', water_species, dim_names=dim_name)
    call ccpp_capture('has_default', has_default, dim_names=dim_name)
    call ccpp_capture('default_value', default_value, dim_names=dim_name)
    call ccpp_capture('minimum', minimum, dim_names=dim_name)
    call ccpp_capture('molar_mass', molar_mass, dim_names=dim_name)
    call ccpp_capture_end_ddt()
  end subroutine ccpp_capture_constituents

  subroutine ccpp_capture_read_constituents(group, name, props)
    character(len=*), intent(in) :: group, name
    type(ccpp_constituent_prop_ptr_t), allocatable, intent(out) :: props(:)
    character(len=:), allocatable :: path
    character(len=name_len), allocatable :: std_name(:), long_name(:), diag_name(:)
    character(len=name_len), allocatable :: units(:), vert_dim(:)
    character(len=8), allocatable :: mixing_ratio_type(:)
    integer, allocatable :: const_index(:)
    logical, allocatable :: advected(:), thermo_active(:), water_species(:), has_default(:)
    real(kind_phys), allocatable :: default_value(:), minimum(:), molar_mass(:)
    type(ccpp_constituent_properties_t), pointer :: prop
    integer :: extents(1), n, i, errcode
    character(len=512) :: errmsg
    logical :: found

    path = trim(group) // '/' // trim(name)
    call ccpp_capture_extents(path, 'standard_name', extents, found)
    if (.not. found) then
      write(0,*) 'ccpp_capture_constituents_mod: no constituent properties ', path
      allocate(props(0))
      return
    end if
    n = extents(1)
    allocate(std_name(n), long_name(n), diag_name(n), units(n), vert_dim(n))
    allocate(mixing_ratio_type(n), const_index(n), advected(n), thermo_active(n))
    allocate(water_species(n), has_default(n), default_value(n), minimum(n), molar_mass(n))
    call ccpp_capture_read(path, 'standard_name', std_name)
    call ccpp_capture_read(path, 'long_name', long_name)
    call ccpp_capture_read(path, 'diagnostic_name', diag_name)
    call ccpp_capture_read(path, 'units', units)
    call ccpp_capture_read(path, 'vertical_dimension', vert_dim)
    call ccpp_capture_read(path, 'mixing_ratio_type', mixing_ratio_type)
    call ccpp_capture_read(path, 'const_index', const_index)
    call ccpp_capture_read(path, 'advected', advected)
    call ccpp_capture_read(path, 'thermo_active', thermo_active)
    call ccpp_capture_read(path, 'water_species', water_species)
    call ccpp_capture_read(path, 'has_default', has_default)
    call ccpp_capture_read(path, 'default_value', default_value)
    call ccpp_capture_read(path, 'minimum', minimum)
    call ccpp_capture_read(path, 'molar_mass', molar_mass)

    if (allocated(lc_props)) then
      do i = 1, size(lc_props)
        call lc_props(i)%deallocate()
      end do
      deallocate(lc_props)
    end if
    allocate(lc_props(n))
    allocate(props(n))
    do i = 1, n
      if (len_trim(std_name(i)) == 0) cycle  ! not captured: left unset
      if (has_default(i)) then
        call lc_props(i)%instantiate(std_name=trim(std_name(i)), long_name=trim(long_name(i)), &
          diag_name=trim(diag_name(i)), units=trim(units(i)), vertical_dim=trim(vert_dim(i)), &
          advected=advected(i), default_value=default_value(i), min_value=minimum(i), &
          molar_mass=molar_mass(i), water_species=water_species(i), &
          mixing_ratio_type=trim(mixing_ratio_type(i)), errcode=errcode, errmsg=errmsg)
      else
        call lc_props(i)%instantiate(std_name=trim(std_name(i)), long_name=trim(long_name(i)), &
          diag_name=trim(diag_name(i)), units=trim(units(i)), vertical_dim=trim(vert_dim(i)), &
          advected=advected(i), min_value=minimum(i), &
          molar_mass=molar_mass(i), water_species=water_species(i), &
          mixing_ratio_type=trim(mixing_ratio_type(i)), errcode=errcode, errmsg=errmsg)
      end if
      if (errcode == 0) then
        prop => lc_props(i)
        call props(i)%set(prop, errcode=errcode, errmsg=errmsg)
      end if
      if (errcode == 0) call props(i)%set_const_index(const_index(i), errcode=errcode, errmsg=errmsg)
      if (errcode == 0) call props(i)%set_thermo_active(thermo_active(i), errcode=errcode, errmsg=errmsg)
      if (errcode /= 0) then
        write(0,*) 'ccpp_capture_constituents_mod: constituent ', i, ' (', trim(std_name(i)), &
                   '): ', trim(errmsg)
      end if
    end do
  end subroutine ccpp_capture_read_constituents

end module ccpp_capture_constituents_mod
