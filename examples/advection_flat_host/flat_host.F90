module flat_host

   implicit none
   public

   integer, parameter :: cs = 16
   integer, parameter :: cm = 41

   !> \section arg_table_suite_info  Argument Table
   !! \htmlinclude arg_table_suite_info.html
   !!
   type :: suite_info
      character(len=cs) :: suite_name = ''
      character(len=cs), pointer :: suite_parts(:) => NULL()
      character(len=cm), pointer :: suite_input_vars(:) => NULL()
      character(len=cm), pointer :: suite_output_vars(:) => NULL()
      character(len=cm), pointer :: suite_required_vars(:) => NULL()
   end type suite_info

   !> \section arg_table_flat_host  Argument Table
   !! \htmlinclude arg_table_flat_host.html
   !!
   integer            :: col_start
   integer            :: col_end
   character(len=512) :: errmsg
   integer            :: errflg

end module flat_host
