! Test parameterization with advected species
!

MODULE cld_liq

   USE ccpp_kinds, ONLY: kind_phys
   use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t

   IMPLICIT NONE
   PRIVATE

   PUBLIC :: cld_liq_register
   PUBLIC :: cld_liq_init
   PUBLIC :: cld_liq_run

CONTAINS

   !> \section arg_table_cld_liq_register  Argument Table
   !! \htmlinclude arg_table_cld_liq_register.html
   !!
   subroutine cld_liq_register(dyn_const, errmsg, errflg)
      type(ccpp_constituent_properties_t), allocatable, intent(out) :: dyn_const(:)
      !$ccpp [dyn_const] standard_name = dynamic_constituents_for_cld_liq &
      !$ccpp             dim_names = :
      character(len=512), intent(out) :: errmsg
      !$ccpp [errmsg] standard_name = ccpp_error_message &
      !$ccpp          long_name = Error message for error handling in CCPP &
      !$ccpp          units = none
      integer,            intent(out) :: errflg
      !$ccpp [errflg] standard_name = ccpp_error_code &
      !$ccpp          long_name = Error flag for error handling in CCPP &
      !$ccpp          units = 1

      errmsg = ''
      errflg = 0
      allocate(dyn_const(1), stat=errflg)
      if (errflg /= 0) then
         errmsg = 'Error allocating dyn_const in cld_liq_register'
         return
      end if
      call dyn_const(1)%instantiate(std_name="dyn_const3_wrt_moist_air_and_condensed_water", long_name='dyn const3', &
           diag_name='dyn_const3', units='kg kg-1', default_value=1._kind_phys,   &
           vertical_dim='vertical_layer_dimension', advected=.true.,               &
           water_species=.true., mixing_ratio_type='dry',                          &
           errcode=errflg, errmsg=errmsg)

   end subroutine cld_liq_register

   !> \section arg_table_cld_liq_run  Argument Table
   !! \htmlinclude arg_table_cld_liq_run.html
   !!
   subroutine cld_liq_run(ncol, timestep, tcld, temp, qv, ps, &
       cld_liq_tend, errmsg, errflg)

      integer,            intent(in)    :: ncol
      !$ccpp [ncol] standard_name = horizontal_dimension &
      !$ccpp        units = count
      real(kind_phys),    intent(in)    :: timestep
      !$ccpp [timestep] standard_name = time_step_for_physics &
      !$ccpp            long_name = time step &
      !$ccpp            units = s
      real(kind_phys),    intent(in)    :: tcld
      !$ccpp [tcld] standard_name = minimum_temperature_for_cloud_liquid &
      !$ccpp        units = K
      real(kind_phys),    intent(inout) :: temp(:,:)
      !$ccpp [temp] standard_name = temperature &
      !$ccpp        units = K &
      !$ccpp        dim_names = horizontal_dimension,vertical_layer_dimension
      real(kind_phys),    intent(inout) :: qv(:,:)
      !$ccpp [qv] standard_name = water_vapor_specific_humidity &
      !$ccpp      units = kg kg-1 &
      !$ccpp      dim_names = horizontal_dimension,vertical_layer_dimension
      real(kind_phys),    intent(in)    :: ps(:)
      !$ccpp [ps] standard_name = surface_air_pressure &
      !$ccpp      state_variable = true &
      !$ccpp      units = hPa &
      !$ccpp      dim_names = horizontal_dimension
      REAL(kind_phys),    intent(inout) :: cld_liq_tend(:,:)
      !$ccpp [cld_liq_tend] standard_name = tendency_of_cloud_liquid_dry_mixing_ratio &
      !$ccpp                units = kg kg-1 s-1 &
      !$ccpp                dim_names = horizontal_dimension,vertical_layer_dimension &
      !$ccpp                constituent = True
      character(len=512), intent(out)   :: errmsg
      !$ccpp [errmsg] standard_name = ccpp_error_message &
      !$ccpp          long_name = Error message for error handling in CCPP &
      !$ccpp          units = none
      integer,            intent(out)   :: errflg
      !$ccpp [errflg] standard_name = ccpp_error_code &
      !$ccpp          long_name = Error flag for error handling in CCPP &
      !$ccpp          units = 1
      !----------------------------------------------------------------

      integer         :: icol
      integer         :: ilev, nlev
      real(kind_phys) :: cond

      errmsg = ''
      errflg = 0

      nlev = size(temp, 2)
      ! Apply state-of-the-art thermodynamics :)
      !$acc parallel loop collapse(2) gang vector present(qv,temp,cld_liq_tend)
      do icol = 1, ncol
         do ilev = 1, nlev
            if ( (qv(icol, ilev) > 0.0_kind_phys) .and.                       &
                 (temp(icol, ilev) <= tcld)) then
               cond = MIN(qv(icol, ilev), 0.1_kind_phys)
               cld_liq_tend(icol, ilev) = cond
               qv(icol, ilev) = qv(icol, ilev) - cond
               if (cond > 0.0_kind_phys) then
                  temp(icol, ilev) = temp(icol, ilev) + (cond * 5.0_kind_phys)
               end if
            end if
         end do
      end do

   END SUBROUTINE cld_liq_run

   !> \section arg_table_cld_liq_init  Argument Table
   !! \htmlinclude arg_table_cld_liq_init.html
   !!
   subroutine cld_liq_init(tfreeze, cld_liq_array, tcld, errmsg, errflg)

      real(kind_phys),    intent(in)  :: tfreeze
      !$ccpp [tfreeze] standard_name = water_temperature_at_freezing &
      !$ccpp           long_name = Freezing temperature of water at sea level &
      !$ccpp           units = K
      real(kind_phys),    intent(out) :: cld_liq_array(:,:)
      !$ccpp [cld_liq_array] standard_name = cloud_liquid_dry_mixing_ratio &
      !$ccpp                 advected = .true. &
      !$ccpp                 units = kg kg-1 &
      !$ccpp                 dim_names = horizontal_dimension,vertical_layer_dimension
      real(kind_phys),    intent(out) :: tcld
      !$ccpp [tcld] standard_name = minimum_temperature_for_cloud_liquid &
      !$ccpp        units = K
      character(len=512), intent(out) :: errmsg
      !$ccpp [errmsg] standard_name = ccpp_error_message &
      !$ccpp          long_name = Error message for error handling in CCPP &
      !$ccpp          units = none
      integer,            intent(out) :: errflg
      !$ccpp [errflg] standard_name = ccpp_error_code &
      !$ccpp          long_name = Error flag for error handling in CCPP &
      !$ccpp          units = 1

      integer :: i, j, n1, n2
      ! This routine currently does nothing

      errmsg = ''
      errflg = 0
      tcld = tfreeze - 20.0_kind_phys
      n1 = size(cld_liq_array,1)
      n2 = size(cld_liq_array,2)
      !$acc parallel loop collapse(2) gang vector present(cld_liq_array)
      do i=1,n1
        do j=1,n2
          cld_liq_array(i,j) = 0.0_kind_phys
        enddo
      enddo

   end subroutine cld_liq_init

END MODULE cld_liq
