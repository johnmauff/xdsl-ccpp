! Ported verbatim from capgen-v1's own
! end-to-end-tests/capgen/adjust/temp_kinds.F90 -- defines a real,
! non-kind_phys Fortran kind (temp_r8) that temp_set/temp_adjust's own
! kind_spec table property (temp_set.meta/temp_adjust.meta) declares as the
! source for their "to_promote" argument's kind (kind_temp).

module temp_kinds

  implicit none
  private

  integer, public, parameter :: temp_r8 = selected_real_kind(12) !8-byte real
  integer, public, parameter :: temp_i8 = selected_int_kind(13) !8-byte integer

end module temp_kinds
