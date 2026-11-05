! Replay-side support for the generated scheme I/O capture test drivers:
! state a driver restores from the capture before replaying a scheme.
! Built into the drivers' support library only, never into a model (it uses
! the bundled ccpp_scheme_utils, not a host's own).
!
! The run's constituent table (scheme-io-capture-constituent-index-table):
! the generated host cap captures its constituent-properties array once, as
! call 1 of table 'ccpp_constituents' (subgroup in/constituents), when it
! registers the constituents. ccpp_capture_restore_constituents() rebuilds
! it and hands it to ccpp_scheme_utils, so a replayed scheme's
! ccpp_constituent_index(es) lookups answer as in the run. A capture
! without the table leaves ccpp_scheme_utils empty (every lookup
! unassigned), as before.
module ccpp_capture_replay_mod

  use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t, &
                                       ccpp_constituent_prop_ptr_t
  use ccpp_scheme_utils, only: ccpp_scheme_utils_set_constituents
  use ccpp_capture_mod, only: ccpp_capture_open_call, ccpp_capture_close
  use ccpp_capture_constituents_mod, only: ccpp_capture_rebuild_constituents

  implicit none
  private

  public :: ccpp_capture_restore_constituents

  character(len=*), parameter :: table_name = 'ccpp_constituents'
  character(len=*), parameter :: table_arg = 'constituents'

  ! The table's properties: ccpp_scheme_utils points at them for the whole
  ! replay (kept apart from the properties each scheme-argument read
  ! rebuilds).
  type(ccpp_constituent_properties_t), allocatable, target, save :: table_props(:)

contains

  subroutine ccpp_capture_restore_constituents()
    type(ccpp_constituent_prop_ptr_t), allocatable :: props(:)
    logical :: found

    call ccpp_capture_open_call(table_name, 1, found)
    if (.not. found) return
    call ccpp_capture_rebuild_constituents('in', table_arg, table_props, props)
    call ccpp_capture_close()
    call ccpp_scheme_utils_set_constituents(props)
  end subroutine ccpp_capture_restore_constituents

end module ccpp_capture_replay_mod
