! Test collection of constituent indices
!
! dup-meta-shadow-elim (BACKLOG.md): this is the tag-based twin of
! examples/advection's own const_indices.F90 -- identical behavior, but
! standard_name/long_name/units/protected/dim_names live here as !$ccpp
! tags instead of a hand-maintained const_indices.meta. See
! examples/advection_nometa's own README.md and CMakeLists.txt for how
! .meta gets generated from this file at configure time instead of being
! committed.

MODULE const_indices

   USE ccpp_kinds, ONLY: kind_phys

   IMPLICIT NONE
   PRIVATE

   PUBLIC :: const_indices_init
   PUBLIC :: const_indices_run

CONTAINS

   !> \section arg_table_const_indices_run  Argument Table
   !! \htmlinclude arg_table_const_indices_run.html
   !!
   subroutine const_indices_run(const_std_name, num_consts, test_stdname_array,  &
        const_index, const_inds, errmsg, errflg)
      use ccpp_constituent_prop_mod, only: int_unassigned
      use ccpp_scheme_utils,         only: ccpp_constituent_index
      use ccpp_scheme_utils,         only: ccpp_constituent_indices

      character(len=*),   intent(in)  :: const_std_name
      !$ccpp [const_std_name] standard_name = test_banana_name &
      !$ccpp                  units = 1 &
      !$ccpp                  protected = true
      integer,            intent(in)  :: num_consts
      !$ccpp [num_consts] standard_name = banana_array_dim &
      !$ccpp              long_name = Size of test_banana_name_array &
      !$ccpp              units = 1
      character(len=*),   intent(in)  :: test_stdname_array(:)
      !$ccpp [test_stdname_array] standard_name = test_banana_name_array &
      !$ccpp                      units = count &
      !$ccpp                      dim_names = banana_array_dim
      integer,            intent(out) :: const_index
      !$ccpp [const_index] standard_name = test_banana_constituent_index &
      !$ccpp               long_name = Constituent index &
      !$ccpp               units = 1
      integer,            intent(out) :: const_inds(:)
      !$ccpp [const_inds] standard_name = test_banana_constituent_indices &
      !$ccpp              long_name = Array of constituent indices &
      !$ccpp              units = 1 &
      !$ccpp              dim_names = banana_array_dim
      character(len=512), intent(out) :: errmsg
      !$ccpp [errmsg] standard_name = ccpp_error_message &
      !$ccpp          long_name = Error message for error handling in CCPP &
      !$ccpp          units = none
      integer,            intent(out) :: errflg
      !$ccpp [errflg] standard_name = ccpp_error_code &
      !$ccpp          long_name = Error flag for error handling in CCPP &
      !$ccpp          units = 1
      !----------------------------------------------------------------

      integer                         :: indx
      integer                         :: test_indx

      errmsg = ''
      errflg = 0

      ! Find the constituent index for <const_std_name>
      call ccpp_constituent_index(const_std_name, const_index, errflg, errmsg)
      if (errflg == 0) then
         call ccpp_constituent_indices(test_stdname_array, const_inds, errflg, errmsg)
      end if
      ! Check that a non-registered constituent is detectable but
      !   does not cause an error
      if (errflg == 0) then
         call ccpp_constituent_index('unobtainium', test_indx, errflg, errmsg)
         if (test_indx /= int_unassigned) then
            if (errflg == 0) then
               ! Do not add an error if one is already reported
               errflg = 2
               write(errmsg, '(2a,i0,a,i0)') "ccpp_constituent_index called for ", &
                    "'unobtainium' returned an index of ", test_indx, ", not ",    &
                    int_unassigned
            end if
         end if
      end if

   end subroutine const_indices_run

   !> \section arg_table_const_indices_init  Argument Table
   !! \htmlinclude arg_table_const_indices_init.html
   !!
   subroutine const_indices_init(const_std_name, num_consts, test_stdname_array, &
        const_index, const_inds, errmsg, errflg)
      use ccpp_scheme_utils, only: ccpp_constituent_index, ccpp_constituent_indices

      character(len=*),   intent(in)  :: const_std_name
      !$ccpp [const_std_name] standard_name = test_banana_name &
      !$ccpp                  units = 1 &
      !$ccpp                  protected = true
      integer,            intent(in)  :: num_consts
      !$ccpp [num_consts] standard_name = banana_array_dim &
      !$ccpp              long_name = Size of test_banana_name_array &
      !$ccpp              units = 1
      character(len=*),   intent(in)  :: test_stdname_array(:)
      !$ccpp [test_stdname_array] standard_name = test_banana_name_array &
      !$ccpp                      units = count &
      !$ccpp                      dim_names = banana_array_dim
      integer,            intent(out) :: const_index
      !$ccpp [const_index] standard_name = test_banana_constituent_index &
      !$ccpp               long_name = Constituent index &
      !$ccpp               units = 1
      integer,            intent(out) :: const_inds(:)
      !$ccpp [const_inds] standard_name = test_banana_constituent_indices &
      !$ccpp              long_name = Array of constituent indices &
      !$ccpp              units = 1 &
      !$ccpp              dim_names = banana_array_dim
      character(len=512), intent(out) :: errmsg
      !$ccpp [errmsg] standard_name = ccpp_error_message &
      !$ccpp          long_name = Error message for error handling in CCPP &
      !$ccpp          units = none
      integer,            intent(out) :: errflg
      !$ccpp [errflg] standard_name = ccpp_error_code &
      !$ccpp          long_name = Error flag for error handling in CCPP &
      !$ccpp          units = 1
      !----------------------------------------------------------------

      integer         :: indx

      errmsg = ''
      errflg = 0

      ! Find the constituent index for <const_std_name>
      call ccpp_constituent_index(const_std_name, const_index, errflg, errmsg)
      if (errflg == 0) then
         call ccpp_constituent_indices(test_stdname_array, const_inds, errflg, errmsg)
      end if

   end subroutine const_indices_init

   !! @}
   !! @}

END MODULE const_indices
