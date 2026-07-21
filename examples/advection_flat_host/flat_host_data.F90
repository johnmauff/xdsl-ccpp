module flat_host_data

  use ccpp_kinds, only: kind_phys

  implicit none

  !> \section arg_table_flat_host_data  Argument Table
  !! \htmlinclude arg_table_flat_host_data.html
  integer, public, parameter :: num_consts = 3
  character(len=32), public, parameter :: std_name_array(num_consts) = (/    &
       'specific_humidity            ',                                     &
       'cloud_liquid_dry_mixing_ratio',                                     &
       'cloud_ice_dry_mixing_ratio   ' /)
  character(len=32), public, parameter :: const_std_name = std_name_array(1)

  integer :: const_inds(num_consts) = -1
  integer :: const_index = -1

end module flat_host_data
