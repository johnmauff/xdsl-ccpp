module Ddthost_ccpp_cap
  
  use ccpp_kinds
  use iso_c_binding
  use ddthost_host_mod, only: ncols
  use ddthost_host_mod, only: vmr
  use ddthost_suite_cap, only: ddthost_suite_suite_finalize
  use ddthost_suite_cap, only: ddthost_suite_suite_initialize
  use ddthost_suite_cap, only: ddthost_suite_suite_physics
  use ddthost_suite_cap, only: ddthost_suite_suite_register
  use ddthost_suite_cap, only: ddthost_suite_suite_timestep_final
  use ddthost_suite_cap, only: ddthost_suite_suite_timestep_initial
  use host_ccpp_ddt, only: ccpp_info_t
  use make_ddt, only: vmr_type
  
  implicit none
  private

  character(len=13), parameter :: str_ddthost_suite = 'ddthost_suite'
  character(len=7), parameter :: str_physics = 'physics'
  public :: Ddthost_ccpp_physics_register
  public :: Ddthost_ccpp_physics_initialize
  public :: Ddthost_ccpp_physics_finalize
  public :: Ddthost_ccpp_physics_timestep_initial
  public :: Ddthost_ccpp_physics_timestep_final
  public :: Ddthost_ccpp_physics_run
  public :: ccpp_physics_suite_list
  public :: ccpp_physics_suite_part_list
  public :: ccpp_physics_suite_variables

CONTAINS
  
  subroutine Ddthost_ccpp_physics_register(suite_name, ccpp_info) BIND(C,                         &
    name='Ddthost_ccpp_physics_register') 
    character(kind=c_char, len=1), intent(in) :: suite_name(*)
    type(c_ptr), intent(inout) :: ccpp_info
    integer :: ccpp_c2f_i
    character(len=512) :: suite_name_f
    
    suite_name_f = ' '
    do ccpp_c2f_i = 1, len(suite_name_f) 
      if (suite_name(ccpp_c2f_i) == c_null_char) exit
      suite_name_f(ccpp_c2f_i:ccpp_c2f_i) = suite_name(ccpp_c2f_i)
    end do 
    ccpp_info%errflg = 0    
    if (trim(suite_name_f) .eq. 'ddthost_suite') then
      call ddthost_suite_suite_register(ccpp_info%errflg, ccpp_info%errmsg)
    else
      write(ccpp_info%errmsg, '(3a)') "No suite named ", trim(suite_name_f), "found"
      ccpp_info%errflg = 1      
    end if
  end subroutine Ddthost_ccpp_physics_register 
  
  subroutine Ddthost_ccpp_physics_initialize(suite_name, ccpp_info) BIND(C,                       &
    name='Ddthost_ccpp_physics_initialize') 
    character(kind=c_char, len=1), intent(in) :: suite_name(*)
    type(c_ptr), intent(inout) :: ccpp_info
    integer :: ccpp_c2f_i
    character(len=512) :: suite_name_f
    
    suite_name_f = ' '
    do ccpp_c2f_i = 1, len(suite_name_f) 
      if (suite_name(ccpp_c2f_i) == c_null_char) exit
      suite_name_f(ccpp_c2f_i:ccpp_c2f_i) = suite_name(ccpp_c2f_i)
    end do 
    ccpp_info%errflg = 0    
    if (trim(suite_name_f) .eq. 'ddthost_suite') then
      call ddthost_suite_suite_initialize(ncols, ccpp_info, vmr, ccpp_info%errmsg,                &
        ccpp_info%errflg)
    else
      write(ccpp_info%errmsg, '(3a)') "No suite named ", trim(suite_name_f), "found"
      ccpp_info%errflg = 1      
    end if
  end subroutine Ddthost_ccpp_physics_initialize 
  
  subroutine Ddthost_ccpp_physics_finalize(suite_name, ccpp_info) BIND(C,                         &
    name='Ddthost_ccpp_physics_finalize') 
    character(kind=c_char, len=1), intent(in) :: suite_name(*)
    type(c_ptr), intent(inout) :: ccpp_info
    integer :: ccpp_c2f_i
    character(len=512) :: suite_name_f
    
    suite_name_f = ' '
    do ccpp_c2f_i = 1, len(suite_name_f) 
      if (suite_name(ccpp_c2f_i) == c_null_char) exit
      suite_name_f(ccpp_c2f_i:ccpp_c2f_i) = suite_name(ccpp_c2f_i)
    end do 
    ccpp_info%errflg = 0    
    if (trim(suite_name_f) .eq. 'ddthost_suite') then
      call ddthost_suite_suite_finalize(ccpp_info%errflg, ccpp_info%errmsg)
    else
      write(ccpp_info%errmsg, '(3a)') "No suite named ", trim(suite_name_f), "found"
      ccpp_info%errflg = 1      
    end if
  end subroutine Ddthost_ccpp_physics_finalize 
  
  subroutine Ddthost_ccpp_physics_timestep_initial(suite_name, ccpp_info) BIND(C,                 &
    name='Ddthost_ccpp_physics_timestep_initial') 
    character(kind=c_char, len=1), intent(in) :: suite_name(*)
    type(c_ptr), intent(inout) :: ccpp_info
    integer :: ccpp_c2f_i
    character(len=512) :: suite_name_f
    
    suite_name_f = ' '
    do ccpp_c2f_i = 1, len(suite_name_f) 
      if (suite_name(ccpp_c2f_i) == c_null_char) exit
      suite_name_f(ccpp_c2f_i:ccpp_c2f_i) = suite_name(ccpp_c2f_i)
    end do 
    ccpp_info%errflg = 0    
    if (trim(suite_name_f) .eq. 'ddthost_suite') then
      call ddthost_suite_suite_timestep_initial(ccpp_info%errflg, ccpp_info%errmsg)
    else
      write(ccpp_info%errmsg, '(3a)') "No suite named ", trim(suite_name_f), "found"
      ccpp_info%errflg = 1      
    end if
  end subroutine Ddthost_ccpp_physics_timestep_initial 
  
  subroutine Ddthost_ccpp_physics_timestep_final(suite_name, ccpp_info) BIND(C,                   &
    name='Ddthost_ccpp_physics_timestep_final') 
    character(kind=c_char, len=1), intent(in) :: suite_name(*)
    type(c_ptr), intent(inout) :: ccpp_info
    integer :: ccpp_c2f_i
    character(len=512) :: suite_name_f
    
    suite_name_f = ' '
    do ccpp_c2f_i = 1, len(suite_name_f) 
      if (suite_name(ccpp_c2f_i) == c_null_char) exit
      suite_name_f(ccpp_c2f_i:ccpp_c2f_i) = suite_name(ccpp_c2f_i)
    end do 
    ccpp_info%errflg = 0    
    if (trim(suite_name_f) .eq. 'ddthost_suite') then
      call ddthost_suite_suite_timestep_final(ncols, vmr, ccpp_info%errmsg, ccpp_info%errflg)
    else
      write(ccpp_info%errmsg, '(3a)') "No suite named ", trim(suite_name_f), "found"
      ccpp_info%errflg = 1      
    end if
  end subroutine Ddthost_ccpp_physics_timestep_final 
  
  subroutine Ddthost_ccpp_physics_run(suite_name, suite_part, ccpp_info, O3, HNO3) BIND(C,        &
    name='Ddthost_ccpp_physics_run') 
    character(kind=c_char, len=1), intent(in) :: suite_name(*)
    character(kind=c_char, len=1), intent(in) :: suite_part(*)
    type(c_ptr), intent(inout) :: ccpp_info
    real(c_double), intent(in) :: O3(*)
    real(c_double), intent(in) :: HNO3(*)
    type(vmr_type) :: ccpp_tmp_0
    integer :: ccpp_c2f_i
    character(len=512) :: suite_name_f
    character(len=512) :: suite_part_f
    
    suite_name_f = ' '
    do ccpp_c2f_i = 1, len(suite_name_f) 
      if (suite_name(ccpp_c2f_i) == c_null_char) exit
      suite_name_f(ccpp_c2f_i:ccpp_c2f_i) = suite_name(ccpp_c2f_i)
    end do 
    suite_part_f = ' '
    do ccpp_c2f_i = 1, len(suite_part_f) 
      if (suite_part(ccpp_c2f_i) == c_null_char) exit
      suite_part_f(ccpp_c2f_i:ccpp_c2f_i) = suite_part(ccpp_c2f_i)
    end do 
    ccpp_info%errflg = 0    
    if (trim(suite_name_f) .eq. 'ddthost_suite') then
      if (trim(suite_part_f) .eq. 'physics') then
        call ddthost_suite_suite_physics(ccpp_info%col_start, ccpp_info%col_end, O3, HNO3, vmr,   &
          ccpp_tmp_0, ccpp_info%errmsg, ccpp_info%errflg)
      else
        write(ccpp_info%errmsg, '(3a)') "No suite part named ", trim(suite_part_f),               &
          " found in suite ddthost_suite"
        ccpp_info%errflg = 1        
      end if
    else
      write(ccpp_info%errmsg, '(3a)') "No suite named ", trim(suite_name_f), "found"
      ccpp_info%errflg = 1      
    end if
  end subroutine Ddthost_ccpp_physics_run 
  
  subroutine ccpp_physics_suite_list(suites) 
    character(len=*), allocatable, intent(out) :: suites(:)
    
    allocate(suites(1))
    suites(1) = str_ddthost_suite
  end subroutine ccpp_physics_suite_list 
  
  subroutine ccpp_physics_suite_part_list(suite_name, part_list, errmsg, errflg) 
    character(len=*), intent(in) :: suite_name
    character(len=*), allocatable, intent(out) :: part_list(:)
    character(len=512), intent(out) :: errmsg
    integer, intent(out) :: errflg
    
    errflg = 0    
    if (trim(suite_name) .eq. 'ddthost_suite') then
      allocate(part_list(1))
      part_list(1) = str_physics
    else
      write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
      errflg = 1      
    end if
  end subroutine ccpp_physics_suite_part_list 
  subroutine ccpp_physics_suite_variables(suite_name, var_list, errmsg, errflg, input_vars,       &
    output_vars)
    character(len=*), intent(in) :: suite_name
    character(len=*), allocatable, intent(out) :: var_list(:)
    character(len=512), intent(out) :: errmsg
    integer, intent(out) :: errflg
    logical, optional, intent(in) :: input_vars
    logical, optional, intent(in) :: output_vars
    logical :: do_input, do_output
    errmsg = ''
    errflg = 0
    do_input = .true.
    do_output = .true.
    if (present(input_vars)) do_input = input_vars
    if (present(output_vars)) do_output = output_vars
    if (trim(suite_name) .eq. 'ddthost_suite') then
      if (do_input .and. .not. do_output) then
        allocate(var_list(5))
        var_list(1) = 'horizontal_dimension                '
        var_list(2) = 'host_standard_ccpp_type             '
        var_list(3) = 'nitric_acid                         '
        var_list(4) = 'ozone                               '
        var_list(5) = 'volume_mixing_ratio_ddt             '
      else if (.not. do_input .and. do_output) then
        allocate(var_list(3))
        var_list(1) = 'ccpp_error_code                     '
        var_list(2) = 'ccpp_error_message                  '
        var_list(3) = 'volume_mixing_ratio_ddt             '
      else
        allocate(var_list(7))
        var_list(1) = 'ccpp_error_code                     '
        var_list(2) = 'ccpp_error_message                  '
        var_list(3) = 'horizontal_dimension                '
        var_list(4) = 'host_standard_ccpp_type             '
        var_list(5) = 'nitric_acid                         '
        var_list(6) = 'ozone                               '
        var_list(7) = 'volume_mixing_ratio_ddt             '
      end if
    else
      write(errmsg, '(3a)') "No suite named ", trim(suite_name), " found"
      errflg = 1
    end if
  end subroutine ccpp_physics_suite_variables
end module Ddthost_ccpp_cap
