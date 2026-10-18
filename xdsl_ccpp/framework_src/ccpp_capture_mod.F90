! Runtime support for xdsl_ccpp's opt-in --capture-scheme feature
! (scheme_io_capture_pass.py). Not part of any CCPP scheme's own interface
! -- linked in only when a build enables --capture-scheme at cap-generation
! time. Dumps scheme input/output arguments to disk (ccpp_capture*) for
! building data-driven, scheme-level regression tests, and reads/compares
! them back (ccpp_capture_read*/ccpp_capture_compare*) from a generated
! standalone test-driver program. Deliberately plain Fortran stream I/O,
! not PIO/NetCDF -- this is a dev/debug capability, not a production
! output path, and avoiding parallel-I/O coordination keeps it small.
!
! v1 scope matches scheme_io_capture_pass.py exactly: {integer, logical,
! real(kind_phys)} x {rank 0..3}. A real build with --capture-scheme only
! ever calls the write procedures (ccpp_capture_*); the read/compare
! families exist for the generated test-driver programs (PR 3), not for
! use inside a real simulation.
!
! File naming: <sanitized-tag>_<call-count>.ccppcap, where <call-count> is
! a per-tag counter that increments every time that tag is written (so a
! scheme called once per timestep produces one file per timestep, without
! xdsl_ccpp ever having to thread a call index through the generated IR
! itself). Multi-MPI-task file collisions are avoided one level up, not
! here: scheme_io_capture_pass.py guards every inserted capture call with
! the host's own mpi-root flag (CAM-SIMA's flag_for_mpi_root/masterproc,
! when the host declares it) so only one task ever writes a given tag at
! all -- this file has no MPI awareness of its own and stays that way.
!
! Every open() below passes convert='native' explicitly -- confirmed the
! hard way against a real CAM-SIMA/Derecho build: without it, unformatted
! stream I/O silently inherits whatever ambient byte-order convention the
! surrounding build environment happens to default to (a real CAM-SIMA
! build there writes big-endian; the gfortran used to verify this library
! standalone on the same login node defaults to little-endian), making a
! captured file's byte order depend on build environment, not content.
! convert='native' forces the true hardware-native order unconditionally,
! which is little-endian on every architecture this project targets (x86_64
! and ARM both default to little-endian universally in practice, despite
! ARM's ISA technically allowing either) -- so this is a safe, durable
! fix, not a narrow one.
module ccpp_capture_mod

  use ccpp_kinds, only: kind_phys

  implicit none
  private

  ! Only the three generic names are public. Every caller -- both the
  ! capture calls scheme_io_capture_pass.py inserts directly into a
  ! generated cap, and the generated test-driver programs' own read/
  ! compare calls -- addresses a scheme by its generic name only (e.g.
  ! `call ccpp_capture(tag, value)`), never a concrete one directly;
  ! Fortran's own overload resolution dispatches to the right concrete
  ! procedure from the argument's static type and rank. (An earlier
  ! version of the capture pass called a concrete write procedure by name
  ! directly, which real-build linking confirmed needs that name
  ! individually `public ::`'d too -- a module procedure reachable only
  ! through a generic interface cannot be named in a `use mod, only:
  ! <name>` statement from outside the module. Switching the pass to emit
  ! the generic name instead removed that requirement entirely.)
  public :: ccpp_capture
  public :: ccpp_capture_read
  public :: ccpp_capture_compare

  interface ccpp_capture
    module procedure ccpp_capture_int_0d
    module procedure ccpp_capture_int_1d
    module procedure ccpp_capture_int_2d
    module procedure ccpp_capture_int_3d
    module procedure ccpp_capture_log_0d
    module procedure ccpp_capture_log_1d
    module procedure ccpp_capture_log_2d
    module procedure ccpp_capture_log_3d
    module procedure ccpp_capture_r8_0d
    module procedure ccpp_capture_r8_1d
    module procedure ccpp_capture_r8_2d
    module procedure ccpp_capture_r8_3d
  end interface ccpp_capture

  interface ccpp_capture_read
    module procedure ccpp_capture_read_int_0d
    module procedure ccpp_capture_read_int_1d
    module procedure ccpp_capture_read_int_2d
    module procedure ccpp_capture_read_int_3d
    module procedure ccpp_capture_read_log_0d
    module procedure ccpp_capture_read_log_1d
    module procedure ccpp_capture_read_log_2d
    module procedure ccpp_capture_read_log_3d
    module procedure ccpp_capture_read_r8_0d
    module procedure ccpp_capture_read_r8_1d
    module procedure ccpp_capture_read_r8_2d
    module procedure ccpp_capture_read_r8_3d
  end interface ccpp_capture_read

  interface ccpp_capture_compare
    module procedure ccpp_capture_compare_int_0d
    module procedure ccpp_capture_compare_int_1d
    module procedure ccpp_capture_compare_int_2d
    module procedure ccpp_capture_compare_int_3d
    module procedure ccpp_capture_compare_log_0d
    module procedure ccpp_capture_compare_log_1d
    module procedure ccpp_capture_compare_log_2d
    module procedure ccpp_capture_compare_log_3d
    module procedure ccpp_capture_compare_r8_0d
    module procedure ccpp_capture_compare_r8_1d
    module procedure ccpp_capture_compare_r8_2d
    module procedure ccpp_capture_compare_r8_3d
  end interface ccpp_capture_compare

  ! Tag-keyed SAVE call counter -- fixed capacity, no dynamic (re)allocation,
  ! for certain portability across gnu/intel/nvhpc. A "dozen or so" distinct
  ! capture tags is the expected real scale (one per captured argument per
  ! scheme call site); 256 is a generous margin, not a tuned limit.
  integer, parameter :: ccpp_capture_max_tags = 256
  character(len=256), save :: lc_capture_tags(ccpp_capture_max_tags) = ''
  integer,             save :: lc_capture_counts(ccpp_capture_max_tags) = 0
  integer,             save :: lc_capture_ntags = 0

contains

  ! ---------------------------------------------------------------------
  ! Internal helpers
  ! ---------------------------------------------------------------------

  ! Returns the next 1-based call count for `tag`, creating a new counter
  ! entry the first time `tag` is seen. Returns -1 (never a valid count)
  ! if the fixed tag table is full -- a real build should simply raise
  ! ccpp_capture_max_tags, not crash.
  function ccpp_capture_next_call_count(tag) result(n)
    character(len=*), intent(in) :: tag
    integer :: n, i

    do i = 1, lc_capture_ntags
      if (trim(lc_capture_tags(i)) == trim(tag)) then
        lc_capture_counts(i) = lc_capture_counts(i) + 1
        n = lc_capture_counts(i)
        return
      end if
    end do

    if (lc_capture_ntags >= ccpp_capture_max_tags) then
      write(0,*) 'ccpp_capture_mod: ccpp_capture_max_tags exceeded for tag ', trim(tag)
      n = -1
      return
    end if

    lc_capture_ntags = lc_capture_ntags + 1
    lc_capture_tags(lc_capture_ntags) = tag
    lc_capture_counts(lc_capture_ntags) = 1
    n = 1
  end function ccpp_capture_next_call_count

  ! Peeks the current call count for `tag` without incrementing -- used by
  ! the generated test-driver programs (PR 3), which read back the Nth
  ! write of a given tag by number rather than writing it themselves.
  function ccpp_capture_peek_call_count(tag) result(n)
    character(len=*), intent(in) :: tag
    integer :: n, i

    n = 0
    do i = 1, lc_capture_ntags
      if (trim(lc_capture_tags(i)) == trim(tag)) then
        n = lc_capture_counts(i)
        return
      end if
    end do
  end function ccpp_capture_peek_call_count

  ! Filesystem-safe rendering of a tag (":" is legal on Linux but is
  ! avoided here for portability -- colons are not valid in Windows/some
  ! archive-tool paths, and this costs nothing to sidestep).
  function ccpp_capture_sanitize(tag) result(safe)
    character(len=*), intent(in) :: tag
    character(len=len(tag)) :: safe
    integer :: i

    safe = tag
    do i = 1, len(safe)
      if (safe(i:i) == ':') safe(i:i) = '_'
    end do
  end function ccpp_capture_sanitize

  function ccpp_capture_itoa(n) result(s)
    integer, intent(in) :: n
    character(len=12) :: s

    write(s,'(I0)') n
  end function ccpp_capture_itoa

  function ccpp_capture_filename(tag, call_count) result(fname)
    character(len=*), intent(in) :: tag
    integer,          intent(in) :: call_count
    character(len=:), allocatable :: fname

    fname = trim(ccpp_capture_sanitize(tag)) // '_' // &
            trim(ccpp_capture_itoa(call_count)) // '.ccppcap'
  end function ccpp_capture_filename

  ! ---------------------------------------------------------------------
  ! Write procedures -- one per (type, rank). On-disk format: a leading
  ! integer giving the rank, then (for rank > 0) that many integers giving
  ! the shape, then the raw data in a single unformatted write. A failed
  ! open is reported to stderr and the write is silently skipped (not a
  ! hard stop) -- a real simulation run should not abort because a dev/
  ! debug capture file couldn't be written.
  ! ---------------------------------------------------------------------

  subroutine ccpp_capture_int_0d(tag, value)
    character(len=*), intent(in) :: tag
    integer,           intent(in) :: value
    integer :: unit, ios, call_count

    call_count = ccpp_capture_next_call_count(tag)
    if (call_count < 0) return
    open(newunit=unit, file=ccpp_capture_filename(tag, call_count), &
         form='unformatted', access='stream', status='replace', &
         action='write', convert='native', iostat=ios)
    if (ios /= 0) then
      write(0,*) 'ccpp_capture_mod: failed to open capture file for tag ', trim(tag)
      return
    end if
    write(unit) 0
    write(unit) value
    close(unit)
  end subroutine ccpp_capture_int_0d

  subroutine ccpp_capture_int_1d(tag, value)
    character(len=*), intent(in) :: tag
    integer,           intent(in) :: value(:)
    integer :: unit, ios, call_count

    call_count = ccpp_capture_next_call_count(tag)
    if (call_count < 0) return
    open(newunit=unit, file=ccpp_capture_filename(tag, call_count), &
         form='unformatted', access='stream', status='replace', &
         action='write', convert='native', iostat=ios)
    if (ios /= 0) then
      write(0,*) 'ccpp_capture_mod: failed to open capture file for tag ', trim(tag)
      return
    end if
    write(unit) 1
    write(unit) shape(value)
    write(unit) value
    close(unit)
  end subroutine ccpp_capture_int_1d

  subroutine ccpp_capture_int_2d(tag, value)
    character(len=*), intent(in) :: tag
    integer,           intent(in) :: value(:,:)
    integer :: unit, ios, call_count

    call_count = ccpp_capture_next_call_count(tag)
    if (call_count < 0) return
    open(newunit=unit, file=ccpp_capture_filename(tag, call_count), &
         form='unformatted', access='stream', status='replace', &
         action='write', convert='native', iostat=ios)
    if (ios /= 0) then
      write(0,*) 'ccpp_capture_mod: failed to open capture file for tag ', trim(tag)
      return
    end if
    write(unit) 2
    write(unit) shape(value)
    write(unit) value
    close(unit)
  end subroutine ccpp_capture_int_2d

  subroutine ccpp_capture_int_3d(tag, value)
    character(len=*), intent(in) :: tag
    integer,           intent(in) :: value(:,:,:)
    integer :: unit, ios, call_count

    call_count = ccpp_capture_next_call_count(tag)
    if (call_count < 0) return
    open(newunit=unit, file=ccpp_capture_filename(tag, call_count), &
         form='unformatted', access='stream', status='replace', &
         action='write', convert='native', iostat=ios)
    if (ios /= 0) then
      write(0,*) 'ccpp_capture_mod: failed to open capture file for tag ', trim(tag)
      return
    end if
    write(unit) 3
    write(unit) shape(value)
    write(unit) value
    close(unit)
  end subroutine ccpp_capture_int_3d

  subroutine ccpp_capture_log_0d(tag, value)
    character(len=*), intent(in) :: tag
    logical,           intent(in) :: value
    integer :: unit, ios, call_count

    call_count = ccpp_capture_next_call_count(tag)
    if (call_count < 0) return
    open(newunit=unit, file=ccpp_capture_filename(tag, call_count), &
         form='unformatted', access='stream', status='replace', &
         action='write', convert='native', iostat=ios)
    if (ios /= 0) then
      write(0,*) 'ccpp_capture_mod: failed to open capture file for tag ', trim(tag)
      return
    end if
    write(unit) 0
    write(unit) value
    close(unit)
  end subroutine ccpp_capture_log_0d

  subroutine ccpp_capture_log_1d(tag, value)
    character(len=*), intent(in) :: tag
    logical,           intent(in) :: value(:)
    integer :: unit, ios, call_count

    call_count = ccpp_capture_next_call_count(tag)
    if (call_count < 0) return
    open(newunit=unit, file=ccpp_capture_filename(tag, call_count), &
         form='unformatted', access='stream', status='replace', &
         action='write', convert='native', iostat=ios)
    if (ios /= 0) then
      write(0,*) 'ccpp_capture_mod: failed to open capture file for tag ', trim(tag)
      return
    end if
    write(unit) 1
    write(unit) shape(value)
    write(unit) value
    close(unit)
  end subroutine ccpp_capture_log_1d

  subroutine ccpp_capture_log_2d(tag, value)
    character(len=*), intent(in) :: tag
    logical,           intent(in) :: value(:,:)
    integer :: unit, ios, call_count

    call_count = ccpp_capture_next_call_count(tag)
    if (call_count < 0) return
    open(newunit=unit, file=ccpp_capture_filename(tag, call_count), &
         form='unformatted', access='stream', status='replace', &
         action='write', convert='native', iostat=ios)
    if (ios /= 0) then
      write(0,*) 'ccpp_capture_mod: failed to open capture file for tag ', trim(tag)
      return
    end if
    write(unit) 2
    write(unit) shape(value)
    write(unit) value
    close(unit)
  end subroutine ccpp_capture_log_2d

  subroutine ccpp_capture_log_3d(tag, value)
    character(len=*), intent(in) :: tag
    logical,           intent(in) :: value(:,:,:)
    integer :: unit, ios, call_count

    call_count = ccpp_capture_next_call_count(tag)
    if (call_count < 0) return
    open(newunit=unit, file=ccpp_capture_filename(tag, call_count), &
         form='unformatted', access='stream', status='replace', &
         action='write', convert='native', iostat=ios)
    if (ios /= 0) then
      write(0,*) 'ccpp_capture_mod: failed to open capture file for tag ', trim(tag)
      return
    end if
    write(unit) 3
    write(unit) shape(value)
    write(unit) value
    close(unit)
  end subroutine ccpp_capture_log_3d

  subroutine ccpp_capture_r8_0d(tag, value)
    character(len=*), intent(in) :: tag
    real(kind=kind_phys), intent(in) :: value
    integer :: unit, ios, call_count

    call_count = ccpp_capture_next_call_count(tag)
    if (call_count < 0) return
    open(newunit=unit, file=ccpp_capture_filename(tag, call_count), &
         form='unformatted', access='stream', status='replace', &
         action='write', convert='native', iostat=ios)
    if (ios /= 0) then
      write(0,*) 'ccpp_capture_mod: failed to open capture file for tag ', trim(tag)
      return
    end if
    write(unit) 0
    write(unit) value
    close(unit)
  end subroutine ccpp_capture_r8_0d

  subroutine ccpp_capture_r8_1d(tag, value)
    character(len=*), intent(in) :: tag
    real(kind=kind_phys), intent(in) :: value(:)
    integer :: unit, ios, call_count

    call_count = ccpp_capture_next_call_count(tag)
    if (call_count < 0) return
    open(newunit=unit, file=ccpp_capture_filename(tag, call_count), &
         form='unformatted', access='stream', status='replace', &
         action='write', convert='native', iostat=ios)
    if (ios /= 0) then
      write(0,*) 'ccpp_capture_mod: failed to open capture file for tag ', trim(tag)
      return
    end if
    write(unit) 1
    write(unit) shape(value)
    write(unit) value
    close(unit)
  end subroutine ccpp_capture_r8_1d

  subroutine ccpp_capture_r8_2d(tag, value)
    character(len=*), intent(in) :: tag
    real(kind=kind_phys), intent(in) :: value(:,:)
    integer :: unit, ios, call_count

    call_count = ccpp_capture_next_call_count(tag)
    if (call_count < 0) return
    open(newunit=unit, file=ccpp_capture_filename(tag, call_count), &
         form='unformatted', access='stream', status='replace', &
         action='write', convert='native', iostat=ios)
    if (ios /= 0) then
      write(0,*) 'ccpp_capture_mod: failed to open capture file for tag ', trim(tag)
      return
    end if
    write(unit) 2
    write(unit) shape(value)
    write(unit) value
    close(unit)
  end subroutine ccpp_capture_r8_2d

  subroutine ccpp_capture_r8_3d(tag, value)
    character(len=*), intent(in) :: tag
    real(kind=kind_phys), intent(in) :: value(:,:,:)
    integer :: unit, ios, call_count

    call_count = ccpp_capture_next_call_count(tag)
    if (call_count < 0) return
    open(newunit=unit, file=ccpp_capture_filename(tag, call_count), &
         form='unformatted', access='stream', status='replace', &
         action='write', convert='native', iostat=ios)
    if (ios /= 0) then
      write(0,*) 'ccpp_capture_mod: failed to open capture file for tag ', trim(tag)
      return
    end if
    write(unit) 3
    write(unit) shape(value)
    write(unit) value
    close(unit)
  end subroutine ccpp_capture_r8_3d

  ! ---------------------------------------------------------------------
  ! Read procedures -- one per (type, rank). For use only by generated
  ! test-driver programs (PR 3): reads back the call_count'th write of
  ! `tag` (1-based; defaults to the most recent write seen so far by this
  ! same process, via ccpp_capture_peek_call_count, which is the common
  ! case of "read the one fixture file this driver program is built to
  ! consume"). Reports a rank/shape mismatch to stderr and leaves `value`
  ! unmodified rather than reading mismatched data into it.
  ! ---------------------------------------------------------------------

  subroutine ccpp_capture_read_int_0d(tag, value, call_count)
    character(len=*), intent(in)  :: tag
    integer,           intent(out) :: value
    integer, optional, intent(in) :: call_count
    integer :: unit, ios, n, file_rank

    if (present(call_count)) then
      n = call_count
    else
      n = ccpp_capture_peek_call_count(tag)
    end if
    open(newunit=unit, file=ccpp_capture_filename(tag, n), &
         form='unformatted', access='stream', status='old', &
         action='read', convert='native', iostat=ios)
    if (ios /= 0) then
      write(0,*) 'ccpp_capture_mod: failed to open capture file for tag ', trim(tag)
      return
    end if
    read(unit) file_rank
    if (file_rank /= 0) then
      write(0,*) 'ccpp_capture_mod: rank mismatch reading tag ', trim(tag)
      close(unit)
      return
    end if
    read(unit) value
    close(unit)
  end subroutine ccpp_capture_read_int_0d

  subroutine ccpp_capture_read_int_1d(tag, value, call_count)
    character(len=*), intent(in)  :: tag
    integer,           intent(out) :: value(:)
    integer, optional, intent(in) :: call_count
    integer :: unit, ios, n, file_rank, file_shape(1)

    if (present(call_count)) then
      n = call_count
    else
      n = ccpp_capture_peek_call_count(tag)
    end if
    open(newunit=unit, file=ccpp_capture_filename(tag, n), &
         form='unformatted', access='stream', status='old', &
         action='read', convert='native', iostat=ios)
    if (ios /= 0) then
      write(0,*) 'ccpp_capture_mod: failed to open capture file for tag ', trim(tag)
      return
    end if
    read(unit) file_rank
    if (file_rank /= 1) then
      write(0,*) 'ccpp_capture_mod: rank mismatch reading tag ', trim(tag)
      close(unit)
      return
    end if
    read(unit) file_shape
    if (any(file_shape /= shape(value))) then
      write(0,*) 'ccpp_capture_mod: shape mismatch reading tag ', trim(tag)
      close(unit)
      return
    end if
    read(unit) value
    close(unit)
  end subroutine ccpp_capture_read_int_1d

  subroutine ccpp_capture_read_int_2d(tag, value, call_count)
    character(len=*), intent(in)  :: tag
    integer,           intent(out) :: value(:,:)
    integer, optional, intent(in) :: call_count
    integer :: unit, ios, n, file_rank, file_shape(2)

    if (present(call_count)) then
      n = call_count
    else
      n = ccpp_capture_peek_call_count(tag)
    end if
    open(newunit=unit, file=ccpp_capture_filename(tag, n), &
         form='unformatted', access='stream', status='old', &
         action='read', convert='native', iostat=ios)
    if (ios /= 0) then
      write(0,*) 'ccpp_capture_mod: failed to open capture file for tag ', trim(tag)
      return
    end if
    read(unit) file_rank
    if (file_rank /= 2) then
      write(0,*) 'ccpp_capture_mod: rank mismatch reading tag ', trim(tag)
      close(unit)
      return
    end if
    read(unit) file_shape
    if (any(file_shape /= shape(value))) then
      write(0,*) 'ccpp_capture_mod: shape mismatch reading tag ', trim(tag)
      close(unit)
      return
    end if
    read(unit) value
    close(unit)
  end subroutine ccpp_capture_read_int_2d

  subroutine ccpp_capture_read_int_3d(tag, value, call_count)
    character(len=*), intent(in)  :: tag
    integer,           intent(out) :: value(:,:,:)
    integer, optional, intent(in) :: call_count
    integer :: unit, ios, n, file_rank, file_shape(3)

    if (present(call_count)) then
      n = call_count
    else
      n = ccpp_capture_peek_call_count(tag)
    end if
    open(newunit=unit, file=ccpp_capture_filename(tag, n), &
         form='unformatted', access='stream', status='old', &
         action='read', convert='native', iostat=ios)
    if (ios /= 0) then
      write(0,*) 'ccpp_capture_mod: failed to open capture file for tag ', trim(tag)
      return
    end if
    read(unit) file_rank
    if (file_rank /= 3) then
      write(0,*) 'ccpp_capture_mod: rank mismatch reading tag ', trim(tag)
      close(unit)
      return
    end if
    read(unit) file_shape
    if (any(file_shape /= shape(value))) then
      write(0,*) 'ccpp_capture_mod: shape mismatch reading tag ', trim(tag)
      close(unit)
      return
    end if
    read(unit) value
    close(unit)
  end subroutine ccpp_capture_read_int_3d

  subroutine ccpp_capture_read_log_0d(tag, value, call_count)
    character(len=*), intent(in)  :: tag
    logical,           intent(out) :: value
    integer, optional, intent(in) :: call_count
    integer :: unit, ios, n, file_rank

    if (present(call_count)) then
      n = call_count
    else
      n = ccpp_capture_peek_call_count(tag)
    end if
    open(newunit=unit, file=ccpp_capture_filename(tag, n), &
         form='unformatted', access='stream', status='old', &
         action='read', convert='native', iostat=ios)
    if (ios /= 0) then
      write(0,*) 'ccpp_capture_mod: failed to open capture file for tag ', trim(tag)
      return
    end if
    read(unit) file_rank
    if (file_rank /= 0) then
      write(0,*) 'ccpp_capture_mod: rank mismatch reading tag ', trim(tag)
      close(unit)
      return
    end if
    read(unit) value
    close(unit)
  end subroutine ccpp_capture_read_log_0d

  subroutine ccpp_capture_read_log_1d(tag, value, call_count)
    character(len=*), intent(in)  :: tag
    logical,           intent(out) :: value(:)
    integer, optional, intent(in) :: call_count
    integer :: unit, ios, n, file_rank, file_shape(1)

    if (present(call_count)) then
      n = call_count
    else
      n = ccpp_capture_peek_call_count(tag)
    end if
    open(newunit=unit, file=ccpp_capture_filename(tag, n), &
         form='unformatted', access='stream', status='old', &
         action='read', convert='native', iostat=ios)
    if (ios /= 0) then
      write(0,*) 'ccpp_capture_mod: failed to open capture file for tag ', trim(tag)
      return
    end if
    read(unit) file_rank
    if (file_rank /= 1) then
      write(0,*) 'ccpp_capture_mod: rank mismatch reading tag ', trim(tag)
      close(unit)
      return
    end if
    read(unit) file_shape
    if (any(file_shape /= shape(value))) then
      write(0,*) 'ccpp_capture_mod: shape mismatch reading tag ', trim(tag)
      close(unit)
      return
    end if
    read(unit) value
    close(unit)
  end subroutine ccpp_capture_read_log_1d

  subroutine ccpp_capture_read_log_2d(tag, value, call_count)
    character(len=*), intent(in)  :: tag
    logical,           intent(out) :: value(:,:)
    integer, optional, intent(in) :: call_count
    integer :: unit, ios, n, file_rank, file_shape(2)

    if (present(call_count)) then
      n = call_count
    else
      n = ccpp_capture_peek_call_count(tag)
    end if
    open(newunit=unit, file=ccpp_capture_filename(tag, n), &
         form='unformatted', access='stream', status='old', &
         action='read', convert='native', iostat=ios)
    if (ios /= 0) then
      write(0,*) 'ccpp_capture_mod: failed to open capture file for tag ', trim(tag)
      return
    end if
    read(unit) file_rank
    if (file_rank /= 2) then
      write(0,*) 'ccpp_capture_mod: rank mismatch reading tag ', trim(tag)
      close(unit)
      return
    end if
    read(unit) file_shape
    if (any(file_shape /= shape(value))) then
      write(0,*) 'ccpp_capture_mod: shape mismatch reading tag ', trim(tag)
      close(unit)
      return
    end if
    read(unit) value
    close(unit)
  end subroutine ccpp_capture_read_log_2d

  subroutine ccpp_capture_read_log_3d(tag, value, call_count)
    character(len=*), intent(in)  :: tag
    logical,           intent(out) :: value(:,:,:)
    integer, optional, intent(in) :: call_count
    integer :: unit, ios, n, file_rank, file_shape(3)

    if (present(call_count)) then
      n = call_count
    else
      n = ccpp_capture_peek_call_count(tag)
    end if
    open(newunit=unit, file=ccpp_capture_filename(tag, n), &
         form='unformatted', access='stream', status='old', &
         action='read', convert='native', iostat=ios)
    if (ios /= 0) then
      write(0,*) 'ccpp_capture_mod: failed to open capture file for tag ', trim(tag)
      return
    end if
    read(unit) file_rank
    if (file_rank /= 3) then
      write(0,*) 'ccpp_capture_mod: rank mismatch reading tag ', trim(tag)
      close(unit)
      return
    end if
    read(unit) file_shape
    if (any(file_shape /= shape(value))) then
      write(0,*) 'ccpp_capture_mod: shape mismatch reading tag ', trim(tag)
      close(unit)
      return
    end if
    read(unit) value
    close(unit)
  end subroutine ccpp_capture_read_log_3d

  subroutine ccpp_capture_read_r8_0d(tag, value, call_count)
    character(len=*), intent(in)  :: tag
    real(kind=kind_phys), intent(out) :: value
    integer, optional, intent(in) :: call_count
    integer :: unit, ios, n, file_rank

    if (present(call_count)) then
      n = call_count
    else
      n = ccpp_capture_peek_call_count(tag)
    end if
    open(newunit=unit, file=ccpp_capture_filename(tag, n), &
         form='unformatted', access='stream', status='old', &
         action='read', convert='native', iostat=ios)
    if (ios /= 0) then
      write(0,*) 'ccpp_capture_mod: failed to open capture file for tag ', trim(tag)
      return
    end if
    read(unit) file_rank
    if (file_rank /= 0) then
      write(0,*) 'ccpp_capture_mod: rank mismatch reading tag ', trim(tag)
      close(unit)
      return
    end if
    read(unit) value
    close(unit)
  end subroutine ccpp_capture_read_r8_0d

  subroutine ccpp_capture_read_r8_1d(tag, value, call_count)
    character(len=*), intent(in)  :: tag
    real(kind=kind_phys), intent(out) :: value(:)
    integer, optional, intent(in) :: call_count
    integer :: unit, ios, n, file_rank, file_shape(1)

    if (present(call_count)) then
      n = call_count
    else
      n = ccpp_capture_peek_call_count(tag)
    end if
    open(newunit=unit, file=ccpp_capture_filename(tag, n), &
         form='unformatted', access='stream', status='old', &
         action='read', convert='native', iostat=ios)
    if (ios /= 0) then
      write(0,*) 'ccpp_capture_mod: failed to open capture file for tag ', trim(tag)
      return
    end if
    read(unit) file_rank
    if (file_rank /= 1) then
      write(0,*) 'ccpp_capture_mod: rank mismatch reading tag ', trim(tag)
      close(unit)
      return
    end if
    read(unit) file_shape
    if (any(file_shape /= shape(value))) then
      write(0,*) 'ccpp_capture_mod: shape mismatch reading tag ', trim(tag)
      close(unit)
      return
    end if
    read(unit) value
    close(unit)
  end subroutine ccpp_capture_read_r8_1d

  subroutine ccpp_capture_read_r8_2d(tag, value, call_count)
    character(len=*), intent(in)  :: tag
    real(kind=kind_phys), intent(out) :: value(:,:)
    integer, optional, intent(in) :: call_count
    integer :: unit, ios, n, file_rank, file_shape(2)

    if (present(call_count)) then
      n = call_count
    else
      n = ccpp_capture_peek_call_count(tag)
    end if
    open(newunit=unit, file=ccpp_capture_filename(tag, n), &
         form='unformatted', access='stream', status='old', &
         action='read', convert='native', iostat=ios)
    if (ios /= 0) then
      write(0,*) 'ccpp_capture_mod: failed to open capture file for tag ', trim(tag)
      return
    end if
    read(unit) file_rank
    if (file_rank /= 2) then
      write(0,*) 'ccpp_capture_mod: rank mismatch reading tag ', trim(tag)
      close(unit)
      return
    end if
    read(unit) file_shape
    if (any(file_shape /= shape(value))) then
      write(0,*) 'ccpp_capture_mod: shape mismatch reading tag ', trim(tag)
      close(unit)
      return
    end if
    read(unit) value
    close(unit)
  end subroutine ccpp_capture_read_r8_2d

  subroutine ccpp_capture_read_r8_3d(tag, value, call_count)
    character(len=*), intent(in)  :: tag
    real(kind=kind_phys), intent(out) :: value(:,:,:)
    integer, optional, intent(in) :: call_count
    integer :: unit, ios, n, file_rank, file_shape(3)

    if (present(call_count)) then
      n = call_count
    else
      n = ccpp_capture_peek_call_count(tag)
    end if
    open(newunit=unit, file=ccpp_capture_filename(tag, n), &
         form='unformatted', access='stream', status='old', &
         action='read', convert='native', iostat=ios)
    if (ios /= 0) then
      write(0,*) 'ccpp_capture_mod: failed to open capture file for tag ', trim(tag)
      return
    end if
    read(unit) file_rank
    if (file_rank /= 3) then
      write(0,*) 'ccpp_capture_mod: rank mismatch reading tag ', trim(tag)
      close(unit)
      return
    end if
    read(unit) file_shape
    if (any(file_shape /= shape(value))) then
      write(0,*) 'ccpp_capture_mod: shape mismatch reading tag ', trim(tag)
      close(unit)
      return
    end if
    read(unit) value
    close(unit)
  end subroutine ccpp_capture_read_r8_3d

  ! ---------------------------------------------------------------------
  ! Compare procedures -- one per (type, rank). Integer/logical compares
  ! are always exact (no tolerance concept applies to counts, indices, or
  ! flags); real compares take an absolute tolerance. All return .true.
  ! when every element matches.
  ! ---------------------------------------------------------------------

  function ccpp_capture_compare_int_0d(actual, expected) result(ok)
    integer, intent(in) :: actual, expected
    logical :: ok
    ok = (actual == expected)
  end function ccpp_capture_compare_int_0d

  function ccpp_capture_compare_int_1d(actual, expected) result(ok)
    integer, intent(in) :: actual(:), expected(:)
    logical :: ok
    ok = all(actual == expected)
  end function ccpp_capture_compare_int_1d

  function ccpp_capture_compare_int_2d(actual, expected) result(ok)
    integer, intent(in) :: actual(:,:), expected(:,:)
    logical :: ok
    ok = all(actual == expected)
  end function ccpp_capture_compare_int_2d

  function ccpp_capture_compare_int_3d(actual, expected) result(ok)
    integer, intent(in) :: actual(:,:,:), expected(:,:,:)
    logical :: ok
    ok = all(actual == expected)
  end function ccpp_capture_compare_int_3d

  function ccpp_capture_compare_log_0d(actual, expected) result(ok)
    logical, intent(in) :: actual, expected
    logical :: ok
    ok = (actual .eqv. expected)
  end function ccpp_capture_compare_log_0d

  function ccpp_capture_compare_log_1d(actual, expected) result(ok)
    logical, intent(in) :: actual(:), expected(:)
    logical :: ok
    ok = all(actual .eqv. expected)
  end function ccpp_capture_compare_log_1d

  function ccpp_capture_compare_log_2d(actual, expected) result(ok)
    logical, intent(in) :: actual(:,:), expected(:,:)
    logical :: ok
    ok = all(actual .eqv. expected)
  end function ccpp_capture_compare_log_2d

  function ccpp_capture_compare_log_3d(actual, expected) result(ok)
    logical, intent(in) :: actual(:,:,:), expected(:,:,:)
    logical :: ok
    ok = all(actual .eqv. expected)
  end function ccpp_capture_compare_log_3d

  function ccpp_capture_compare_r8_0d(actual, expected, tolerance) result(ok)
    real(kind=kind_phys), intent(in) :: actual, expected, tolerance
    logical :: ok
    ok = (abs(actual - expected) <= tolerance)
  end function ccpp_capture_compare_r8_0d

  function ccpp_capture_compare_r8_1d(actual, expected, tolerance) result(ok)
    real(kind=kind_phys), intent(in) :: actual(:), expected(:), tolerance
    logical :: ok
    ok = all(abs(actual - expected) <= tolerance)
  end function ccpp_capture_compare_r8_1d

  function ccpp_capture_compare_r8_2d(actual, expected, tolerance) result(ok)
    real(kind=kind_phys), intent(in) :: actual(:,:), expected(:,:), tolerance
    logical :: ok
    ok = all(abs(actual - expected) <= tolerance)
  end function ccpp_capture_compare_r8_2d

  function ccpp_capture_compare_r8_3d(actual, expected, tolerance) result(ok)
    real(kind=kind_phys), intent(in) :: actual(:,:,:), expected(:,:,:), tolerance
    logical :: ok
    ok = all(abs(actual - expected) <= tolerance)
  end function ccpp_capture_compare_r8_3d

end module ccpp_capture_mod
