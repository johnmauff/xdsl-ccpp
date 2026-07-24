module ccpp_scheme_utils
  use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t, int_unassigned
  implicit none
  private
  public :: ccpp_constituent_index, ccpp_constituent_indices
  public :: ccpp_scheme_utils_set_constituents

  type(ccpp_constituent_properties_t), allocatable :: lc_constituents(:)

contains

  subroutine ccpp_scheme_utils_set_constituents(all_consts)
    type(ccpp_constituent_properties_t), intent(in) :: all_consts(:)
    if (allocated(lc_constituents)) deallocate(lc_constituents)
    allocate(lc_constituents(size(all_consts)))
    lc_constituents = all_consts
  end subroutine ccpp_scheme_utils_set_constituents

  subroutine ccpp_constituent_index(std_name, cindex, errcode, errmsg)
    character(len=*), intent(in)  :: std_name
    integer,          intent(out) :: cindex
    integer,          intent(out) :: errcode
    character(len=*), intent(out) :: errmsg
    integer :: i
    cindex  = int_unassigned
    errcode = 0
    errmsg  = ''
    if (.not. allocated(lc_constituents)) return
    do i = 1, size(lc_constituents)
      if (trim(lc_constituents(i)%std_name) == trim(std_name)) then
        cindex = i
        return
      end if
    end do
  end subroutine ccpp_constituent_index

  subroutine ccpp_constituent_indices(std_names, cindices, errcode, errmsg)
    character(len=*), intent(in)  :: std_names(:)
    integer,          intent(out) :: cindices(:)
    integer,          intent(out) :: errcode
    character(len=*), intent(out) :: errmsg
    integer :: k, i
    cindices = int_unassigned
    errcode  = 0
    errmsg   = ''
    if (.not. allocated(lc_constituents)) return
    do k = 1, size(std_names)
      do i = 1, size(lc_constituents)
        if (trim(lc_constituents(i)%std_name) == trim(std_names(k))) then
          cindices(k) = i
          exit
        end if
      end do
    end do
  end subroutine ccpp_constituent_indices

end module ccpp_scheme_utils
