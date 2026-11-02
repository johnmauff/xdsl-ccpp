! Standalone round-trip test for ccpp_capture_constituents_mod: writes two
! constituent properties (one with a default value, one without) the way
! a generated cap does, reads them back the way a generated driver does,
! and checks every property, plus an unset pointer left unset.
!
! Run from this directory (compiler and netcdf-fortran as for
! test_ccpp_capture_mod.F90, e.g. `module load gcc netcdf`):
!   S=../../xdsl_ccpp/framework_src
!   gfortran -ffree-line-length-none -o test_ccpp_capture_constituents $(nf-config --fflags) \
!       ccpp_kinds.F90 $S/ccpp_hashable.F90 $S/ccpp_hash_table.F90 \
!       $S/ccpp_constituent_prop_mod.F90 $S/ccpp_capture_mod.F90 \
!       $S/ccpp_capture_constituents_mod.F90 test_ccpp_capture_constituents.F90 \
!       $(nf-config --flibs)
!   ./test_ccpp_capture_constituents
!   ncdump -h const_table_1.nc     # optional: group in/cprops
!
! Exits 0 and prints "ALL TESTS PASSED" on success, 1 otherwise. Writes
! const_table_1.nc into the current directory and leaves it.
program test_ccpp_capture_constituents
  use ccpp_kinds, only: kind_phys
  use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t, &
                                       ccpp_constituent_prop_ptr_t
  use ccpp_capture_mod, only: ccpp_capture_begin, ccpp_capture_end, &
                              ccpp_capture_open_call, ccpp_capture_close
  use ccpp_capture_constituents_mod, only: ccpp_capture_constituents, &
                                           ccpp_capture_read_constituents

  implicit none

  type(ccpp_constituent_properties_t), target :: source(2)
  type(ccpp_constituent_prop_ptr_t) :: written(3)
  type(ccpp_constituent_prop_ptr_t), allocatable :: rebuilt(:)
  type(ccpp_constituent_properties_t), pointer :: prop
  integer :: n_failed, errcode, i
  character(len=512) :: errmsg
  logical :: found

  n_failed = 0

  ! Two properties set the way a host sets them; element 3 left unset.
  call source(1)%instantiate(std_name='water_vapor_mixing_ratio_wrt_moist_air_and_condensed_water', &
    long_name='Water vapor', diag_name='Q', units='kg kg-1', &
    vertical_dim='vertical_layer_dimension', advected=.true., min_value=1.0e-12_kind_phys, &
    molar_mass=18.0_kind_phys, water_species=.true., errcode=errcode, errmsg=errmsg)
  call check(errcode == 0, 'instantiate 1')
  call source(2)%instantiate(std_name='ozone_volume_mixing_ratio', &
    long_name='Ozone', diag_name='O3', units='mol mol-1', &
    vertical_dim='vertical_layer_dimension', advected=.false., default_value=3.0e-8_kind_phys, &
    mixing_ratio_type='dry', errcode=errcode, errmsg=errmsg)
  call check(errcode == 0, 'instantiate 2')
  do i = 1, 2
    prop => source(i)
    call written(i)%set(prop, errcode=errcode, errmsg=errmsg)
    call written(i)%set_const_index(10 + i, errcode=errcode, errmsg=errmsg)
  end do
  call written(1)%set_thermo_active(.true., errcode=errcode, errmsg=errmsg)

  call ccpp_capture_begin('const_table', 'before')
  call ccpp_capture_constituents('cprops', written)
  call ccpp_capture_end()

  call ccpp_capture_open_call('const_table', 1, found)
  call check(found, 'open call 1')
  call ccpp_capture_read_constituents('in', 'cprops', rebuilt)
  call ccpp_capture_close()

  call check(size(rebuilt) == 3, 'size')
  if (size(rebuilt) == 3) then
    do i = 1, 2
      call compare(written(i), rebuilt(i), i)
    end do
    call rebuilt(3)%standard_name(errmsg, errcode=errcode)
    call check(errcode /= 0, 'unset element stays unset')
  end if

  if (n_failed == 0) then
    write(*,*) 'ALL TESTS PASSED'
  else
    write(*,*) n_failed, ' TEST(S) FAILED'
    call exit(1)
  end if

contains

  subroutine check(ok, what)
    logical, intent(in) :: ok
    character(len=*), intent(in) :: what
    if (.not. ok) then
      write(*,*) 'FAIL: ', what
      n_failed = n_failed + 1
    end if
  end subroutine check

  subroutine compare(a, b, i)
    type(ccpp_constituent_prop_ptr_t), intent(in) :: a, b
    integer, intent(in) :: i
    character(len=256) :: sa, sb
    integer :: ia, ib, ec
    logical :: la, lb
    real(kind_phys) :: ra, rb
    character(len=512) :: em
    character(len=8) :: tag

    write(tag, '(I0)') i
    call a%standard_name(sa, ec, em)
    call b%standard_name(sb, ec, em)
    call check(sa == sb, 'standard_name ' // tag)
    call a%long_name(sa, ec, em)
    call b%long_name(sb, ec, em)
    call check(sa == sb, 'long_name ' // tag)
    call a%diagnostic_name(sa, ec, em)
    call b%diagnostic_name(sb, ec, em)
    call check(sa == sb, 'diagnostic_name ' // tag)
    call a%units(sa, ec, em)
    call b%units(sb, ec, em)
    call check(sa == sb, 'units ' // tag)
    call a%vertical_dimension(sa, ec, em)
    call b%vertical_dimension(sb, ec, em)
    call check(sa == sb, 'vertical_dimension ' // tag)
    call a%const_index(ia, ec, em)
    call b%const_index(ib, ec, em)
    call check(ia == ib, 'const_index ' // tag)
    call a%is_advected(la, ec, em)
    call b%is_advected(lb, ec, em)
    call check(la .eqv. lb, 'advected ' // tag)
    call a%is_thermo_active(la, ec, em)
    call b%is_thermo_active(lb, ec, em)
    call check(la .eqv. lb, 'thermo_active ' // tag)
    call a%is_water_species(la, ec, em)
    call b%is_water_species(lb, ec, em)
    call check(la .eqv. lb, 'water_species ' // tag)
    call a%is_dry(la, ec, em)
    call b%is_dry(lb, ec, em)
    call check(la .eqv. lb, 'dry ' // tag)
    call a%is_wet(la, ec, em)
    call b%is_wet(lb, ec, em)
    call check(la .eqv. lb, 'wet ' // tag)
    call a%has_default(la, ec, em)
    call b%has_default(lb, ec, em)
    call check(la .eqv. lb, 'has_default ' // tag)
    call a%default_value(ra, ec, em)
    call b%default_value(rb, ec, em)
    call check(ra == rb, 'default_value ' // tag)
    call a%minimum(ra, ec, em)
    call b%minimum(rb, ec, em)
    call check(ra == rb, 'minimum ' // tag)
    call a%molar_mass(ra, ec, em)
    call b%molar_mass(rb, ec, em)
    call check(ra == rb, 'molar_mass ' // tag)
  end subroutine compare

end program test_ccpp_capture_constituents
