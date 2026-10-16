! Test parameterization whose local names collide with other identifiers
! in the group cap: <cld_ice_array> is also the local name of the cloud
! ice constituent (see cld_ice) and <ncols> is also the local name of the
! host model horizontal dimension. Both name a scheme-supplied
! interstitial here, so capgen must rename the group-cap locals.
!
! dup-meta-shadow-elim (BACKLOG.md): this is the tag-based twin of
! examples/advection's own cld_shadow.F90 -- identical behavior, but
! standard_name/long_name/units/dim_names live here as !$ccpp tags
! instead of a hand-maintained cld_shadow.meta. See
! examples/advection_nometa's own README.md and CMakeLists.txt for how
! .meta gets generated from this file at configure time instead of being
! committed.

module cld_shadow

  use ccpp_kinds, only: kind_phys

  implicit none
  private

  public :: cld_shadow_run

contains

  !> \section arg_table_cld_shadow_run  Argument Table
  !! \htmlinclude arg_table_cld_shadow_run.html
  !!
  subroutine cld_shadow_run(ncol, timestep, cld_ice_array, ncols,       &
       errmsg, errflg)

    integer,            intent(in)  :: ncol
    !$ccpp [ncol] standard_name = horizontal_dimension &
    !$ccpp        units = count
    real(kind_phys),    intent(in)  :: timestep
    !$ccpp [timestep] standard_name = time_step_for_physics &
    !$ccpp            long_name = time step &
    !$ccpp            units = s
    real(kind_phys),    intent(out) :: cld_ice_array(:,:)
    !$ccpp [cld_ice_array] standard_name = cld_shadow_scratch_array &
    !$ccpp                 units = s &
    !$ccpp                 dim_names = horizontal_dimension,vertical_layer_dimension
    real(kind_phys),    intent(out) :: ncols(:)
    !$ccpp [ncols] standard_name = cld_shadow_column_scratch &
    !$ccpp         units = count &
    !$ccpp         dim_names = horizontal_dimension
    character(len=512), intent(out) :: errmsg
    !$ccpp [errmsg] standard_name = ccpp_error_message &
    !$ccpp          long_name = Error message for error handling in CCPP &
    !$ccpp          units = none
    integer,            intent(out) :: errflg
    !$ccpp [errflg] standard_name = ccpp_error_code &
    !$ccpp          long_name = Error flag for error handling in CCPP &
    !$ccpp          units = 1
    !----------------------------------------------------------------

    errmsg = ''
    errflg = 0

    cld_ice_array(:ncol,:) = timestep
    ncols(:ncol) = real(ncol, kind_phys)

  end subroutine cld_shadow_run

end module cld_shadow
