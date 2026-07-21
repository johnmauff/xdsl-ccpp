module flat_host_mod

   use ccpp_kinds, only: kind_phys

   implicit none
   public

   !> \section arg_table_flat_host_mod  Argument Table
   !! \htmlinclude arg_table_flat_host_mod.html
   !!
   integer,         parameter   :: ncols = 10
   integer,         parameter   :: pver = 5
   integer,         parameter   :: pverP = pver + 1
   real(kind_phys)              :: dt
   real(kind_phys), parameter   :: tfreeze = 273.15_kind_phys
   real(kind_phys), allocatable :: temp(:,:)
   real(kind_phys), allocatable :: qv(:,:)
   real(kind_phys), allocatable :: ps(:)

contains

   subroutine init_data()
      ! Level 1 is set well below tcld (tfreeze - 20, computed independently
      ! by cld_liq_init/cld_ice_init) so both schemes' trigger conditions
      ! fire there; every other level is set well above tcld so neither
      ! scheme touches them. This gives the verification driver a clean
      ! "changed where expected, untouched where not" check using only
      ! temp/qv -- the two arrays actually visible to the host.
      allocate(temp(ncols, pver))
      allocate(qv(ncols, pver))
      allocate(ps(ncols))

      temp(:, 1)      = tfreeze - 40.0_kind_phys
      temp(:, 2:pver) = tfreeze + 40.0_kind_phys
      qv(:,:)         = 1.0_kind_phys
      ps(:)           = 1.0e5_kind_phys

   end subroutine init_data

end module flat_host_mod
