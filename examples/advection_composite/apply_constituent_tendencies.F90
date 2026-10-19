module apply_constituent_tendencies

  use ccpp_kinds, only: kind_phys

  implicit none
  private

  public :: apply_constituent_tendencies_run

CONTAINS

   !> \section arg_table_apply_constituent_tendencies_run Argument Table
   !!! \htmlinclude apply_constituent_tendencies_run.html
   subroutine apply_constituent_tendencies_run(const_tend, const, errcode, errmsg)
      ! Dummy arguments
      real(kind_phys),    intent(inout) :: const_tend(:,:,:)  ! constituent tendency array
      !$ccpp [const_tend] standard_name = ccpp_constituent_tendencies &
      !$ccpp               long_name = ccpp constituent tendencies &
      !$ccpp               units = none &
      !$ccpp               dim_names = horizontal_dimension,vertical_layer_dimension,number_of_ccpp_constituents
      real(kind_phys),    intent(inout) :: const(:,:,:)       ! constituent state array
      !$ccpp [const] standard_name = ccpp_constituents &
      !$ccpp         long_name = ccpp constituents &
      !$ccpp         units = none &
      !$ccpp         dim_names = horizontal_dimension,vertical_layer_dimension,number_of_ccpp_constituents
      integer,            intent(out)   :: errcode
      !$ccpp [errcode] standard_name = ccpp_error_code &
      !$ccpp           long_name = Error flag for error handling in CCPP &
      !$ccpp           units = 1
      character(len=512), intent(out)   :: errmsg
      !$ccpp [errmsg] standard_name = ccpp_error_message &
      !$ccpp          long_name = Error message for error handling in CCPP &
      !$ccpp          units = none

      ! Local variables
      integer :: klev, jcnst, icol

      errcode = 0
      errmsg = ''

      do icol = 1, size(const_tend, 1)
         do klev = 1, size(const_tend, 2)
            do jcnst = 1, size(const_tend, 3)
               const(icol, klev, jcnst) = const(icol, klev, jcnst) + const_tend(icol, klev, jcnst)
            end do
         end do
      end do

      const_tend = 0._kind_phys

   end subroutine apply_constituent_tendencies_run

end module apply_constituent_tendencies
