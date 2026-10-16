module data

  !! \section arg_table_data Argument Table
  !! \htmlinclude data.html
  !!
  use ccpp_kinds, only : kind_phys

  implicit none

  private

  public ncols, nthreads
  public thread_type, thread_data

  integer, parameter :: ncols = 4
  integer, parameter :: nthreads = 2

  !! \section arg_table_thread_type Argument Table
  !! \htmlinclude thread_type.html
  !!
  type thread_type
    real(kind=kind_phys), dimension(1:ncols) :: data_array
  end type thread_type

  type(thread_type), dimension(1:nthreads), target :: thread_data

end module data
