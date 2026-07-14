module kessler_host_mod
  use ccpp_kinds, only: kind_phys
  implicit none

  ! Dimension scalars
  integer :: ncol
  integer :: nz
  real(kind_phys) :: dt
  integer :: lyr_surf
  integer :: lyr_toa

  ! Init constants (set before ccpp_physics_initialize)
  real(kind_phys) :: lv
  real(kind_phys) :: pref
  real(kind_phys) :: rhoqr
  real(kind_phys) :: gravit

  ! Scheme output scalar
  character(len=64) :: scheme_name

  ! 2D physics arrays (horizontal_dimension x vertical_layer_dimension)
  real(kind_phys), allocatable :: cpair(:,:)
  real(kind_phys), allocatable :: rair(:,:)
  real(kind_phys), allocatable :: rho(:,:)
  real(kind_phys), allocatable :: z(:,:)
  real(kind_phys), allocatable :: exner(:,:)
  real(kind_phys), allocatable :: theta(:,:)
  real(kind_phys), allocatable :: qv(:,:)
  real(kind_phys), allocatable :: qc(:,:)
  real(kind_phys), allocatable :: qr(:,:)
  real(kind_phys), allocatable :: relhum(:,:)
  real(kind_phys), allocatable :: temp(:,:)
  real(kind_phys), allocatable :: temp_prev(:,:)
  real(kind_phys), allocatable :: ttend_t(:,:)
  real(kind_phys), allocatable :: st_energy(:,:)

  ! 1D arrays (horizontal_dimension)
  real(kind_phys), allocatable :: precl(:)
  real(kind_phys), allocatable :: phis(:)

  public :: init_data
  public :: print_results

contains

  subroutine init_data()
    use iso_c_binding, only: c_double, c_int

    interface
      subroutine kessler_rng_fill(arr, ncol) bind(C, name='kessler_rng_fill')
        use iso_c_binding, only: c_double, c_int
        real(c_double),   intent(out) :: arr(*)
        integer(c_int),   intent(in), value :: ncol
      end subroutine
    end interface

    real(kind_phys), allocatable :: arr(:)
    integer :: i, k

    !------------------------------------------------------------------
    ! Grid size and time step
    !------------------------------------------------------------------
    ncol     = 1000
    nz       = 56
    dt       = 60.0_kind_phys
    lyr_surf = 1
    lyr_toa  = nz

    !------------------------------------------------------------------
    ! Physical constants (used by ccpp_physics_initialize)
    !------------------------------------------------------------------
    lv     = 2.5e6_kind_phys
    pref   = 100000.0_kind_phys
    rhoqr  = 1000.0_kind_phys
    gravit = 9.80616_kind_phys

    !------------------------------------------------------------------
    ! Allocate physics arrays
    !------------------------------------------------------------------
    allocate(cpair(ncol,nz), rair(ncol,nz), rho(ncol,nz))
    allocate(z(ncol,nz), exner(ncol,nz))
    allocate(theta(ncol,nz), qv(ncol,nz), qc(ncol,nz), qr(ncol,nz))
    allocate(relhum(ncol,nz))
    allocate(temp(ncol,nz), temp_prev(ncol,nz), ttend_t(ncol,nz))
    allocate(st_energy(ncol,nz))
    allocate(precl(ncol), phis(ncol))
    allocate(arr(ncol))

    !------------------------------------------------------------------
    ! Deterministic random perturbation via portable C RNG (xorshift64 + Box-Muller)
    !------------------------------------------------------------------
    call kessler_rng_fill(arr, int(ncol, c_int))

    !------------------------------------------------------------------
    ! Initialize physics arrays
    !------------------------------------------------------------------
    do i = 1, ncol
      do k = 1, nz
        cpair(i,k) = 1004.0_kind_phys
        rair(i,k)  = 287.0_kind_phys
        z(i,k)     = arr(i) * (100.0_kind_phys * real(k-1, kind_phys))
        rho(i,k)   = arr(i) * (1.2_kind_phys * exp(-z(i,k)/8000.0_kind_phys))
        exner(i,k) = arr(i) * 1.0_kind_phys
        theta(i,k) = arr(i) * (300.0_kind_phys - 0.006_kind_phys*z(i,k))
        qv(i,k)    = arr(i) * 0.010_kind_phys
        qc(i,k)    = arr(i) * 0.01_kind_phys
        qr(i,k)    = arr(i) * 0.01_kind_phys
        temp(i,k)  = arr(i) * 287.4_kind_phys
      end do
      phis(i) = arr(i) * 0.1_kind_phys
    end do

  end subroutine init_data

  subroutine print_results(etime)
    real(8), intent(in) :: etime

    print *, 'Scheme name: ',    trim(scheme_name)
    print *, 'theta: ',          SUM(theta)
    print *, 'qv: ',             SUM(qv)
    print *, 'qc: ',             SUM(qc)
    print *, 'qr: ',             SUM(qr)
    print *, 'Precip (m/s): ',   SUM(precl)
    print *, 'relnum: ',         SUM(relhum)
    print *, 'temp_prev: ',      SUM(temp_prev)
    print *, 'ttend_t: ',        SUM(ttend_t)
    print *, 'st_energy: ',      SUM(st_energy)
    print *, 'Elapsed time: (ms) ', etime/1.e-3_kind_phys

  end subroutine print_results

end module kessler_host_mod
