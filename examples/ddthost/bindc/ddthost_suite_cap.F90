module ddthost_suite_cap
  
  use ccpp_kinds
  use host_ccpp_ddt, only: ccpp_info_t
  use make_ddt, only: make_ddt_init
  use make_ddt, only: make_ddt_run
  use make_ddt, only: make_ddt_timestep_final
  use make_ddt, only: vmr_type
  
  implicit none
  private

  character(len=16) :: ccpp_suite_state = 'uninitialized'
  character(len=16), parameter :: const_in_time_step = 'in_time_step'
  character(len=16), parameter :: const_initialized = 'initialized'
  character(len=16), parameter :: const_uninitialized = 'uninitialized'
  public :: ddthost_suite_suite_register
  public :: ddthost_suite_suite_initialize
  public :: ddthost_suite_suite_finalize
  public :: ddthost_suite_suite_timestep_initial
  public :: ddthost_suite_suite_timestep_final
  public :: ddthost_suite_suite_physics

CONTAINS
  
  subroutine ddthost_suite_suite_register(errflg, errmsg) 
    integer, intent(out) :: errflg
    character(len=512), intent(out) :: errmsg
    
    errflg = 0    
    errmsg = ''
  end subroutine ddthost_suite_suite_register 
  
  subroutine ddthost_suite_suite_initialize(nbox, ccpp_info, vmr, errmsg, errflg) 
    integer, intent(in) :: nbox
    type(ccpp_info_t), intent(in) :: ccpp_info
    type(vmr_type), intent(out) :: vmr
    character(len=512), intent(out) :: errmsg
    integer, intent(out) :: errflg
    
    errflg = 0    
    errmsg = ''
    if (.NOT. (const_uninitialized .eq. ccpp_suite_state)) then
      write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
        "' in ddthost_suite_initialize"
      errflg = 1      
    end if
    if (errflg .eq. 0) then
      call make_ddt_init(nbox, ccpp_info, vmr, errmsg, errflg)
    end if
    ccpp_suite_state = const_initialized
  end subroutine ddthost_suite_suite_initialize 
  
  subroutine ddthost_suite_suite_finalize(errflg, errmsg) 
    integer, intent(out) :: errflg
    character(len=512), intent(out) :: errmsg
    
    errflg = 0    
    errmsg = ''
    if (.NOT. (const_initialized .eq. ccpp_suite_state)) then
      write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
        "' in ddthost_suite_finalize"
      errflg = 1      
    end if
    ccpp_suite_state = const_uninitialized
  end subroutine ddthost_suite_suite_finalize 
  
  subroutine ddthost_suite_suite_timestep_initial(errflg, errmsg) 
    integer, intent(out) :: errflg
    character(len=512), intent(out) :: errmsg
    
    errflg = 0    
    errmsg = ''
    if (.NOT. (const_initialized .eq. ccpp_suite_state)) then
      write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
        "' in ddthost_suite_timestep_initial"
      errflg = 1      
    end if
    ccpp_suite_state = const_in_time_step
  end subroutine ddthost_suite_suite_timestep_initial 
  
  subroutine ddthost_suite_suite_timestep_final(ncols, vmr, errmsg, errflg) 
    integer, intent(in) :: ncols
    type(vmr_type), intent(in) :: vmr
    character(len=512), intent(out) :: errmsg
    integer, intent(out) :: errflg
    
    errflg = 0    
    errmsg = ''
    if (.NOT. (const_in_time_step .eq. ccpp_suite_state)) then
      write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
        "' in ddthost_suite_timestep_final"
      errflg = 1      
    end if
    if (errflg .eq. 0) then
      call make_ddt_timestep_final(ncols, vmr, errmsg, errflg)
    end if
    ccpp_suite_state = const_initialized
  end subroutine ddthost_suite_suite_timestep_final 
  
  subroutine ddthost_suite_suite_physics(cols, cole, O3, HNO3, vmr, errmsg, errflg) 
    integer, intent(in) :: cols
    integer, intent(in) :: cole
    real(kind=kind_phys), target, intent(in) :: O3(:)
    real(kind=kind_phys), target, intent(in) :: HNO3(:)
    type(vmr_type), intent(inout) :: vmr
    character(len=512), intent(out) :: errmsg
    integer, intent(out) :: errflg
    
    errflg = 0    
    errmsg = ''
    if (.NOT. (const_in_time_step .eq. ccpp_suite_state)) then
      write(errmsg, '(3a)') "Invalid initial CCPP state, '", trim(ccpp_suite_state),              &
        "' in ddthost_suite_physics"
      errflg = 1      
    end if
    if (errflg .eq. 0) then
      call make_ddt_run(cols, cole, O3, HNO3, vmr, errmsg, errflg)
    end if
  end subroutine ddthost_suite_suite_physics 
end module ddthost_suite_cap
