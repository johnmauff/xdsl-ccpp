program test_kessler_driver

  use iso_c_binding
  use kessler
  use kessler_update
  use kessler_host_mod

  implicit none

  character(len=512) :: errmsg
  integer            :: errflg

  integer(8) :: t1, t2, rate
  real(8)    :: etime

  integer :: dev, ierr
  integer(c_size_t) :: bytes1D, bytes2D
  type(c_ptr) :: cpair_raw, rair_raw, rho_raw, z_raw, theta_raw, &
                 qv_raw, qc_raw, qr_raw, precl_raw, relhum_raw
  type(c_ptr) :: temp_raw, exner_raw, phis_raw, temp_prev_raw, &
                 st_energy_raw, ttend_t_raw

  integer :: version

  !------------------------------------------------------
  ! Initialize host data (grid size, constants, arrays)
  !------------------------------------------------------
  call init_data()

  !------------------------------------------------------
  ! Initialize Kessler constants
  !------------------------------------------------------
  call kessler_init(lv, pref, rhoqr, errmsg, errflg)

  if (errflg /= 0) then
     print *, 'Initialization error: ', trim(errmsg)
     stop
  end if

  !------------------------------------------------------
  ! Initialize kessler_update constants (gravit)
  !------------------------------------------------------
  call kessler_update_init(gravit, errmsg, errflg)

  if (errflg /= 0) then
     print *, 'kessler_update_init error: ', trim(errmsg)
     stop
  end if

#ifdef USE_GPU
  dev = omp_get_default_device()

  bytes2D = ncol * nz * c_sizeof(z(1,1))
  bytes1D = ncol * c_sizeof(precl(1))

  cpair_raw  = omp_target_alloc(bytes2D, dev)
  rair_raw   = omp_target_alloc(bytes2D, dev)
  rho_raw    = omp_target_alloc(bytes2D, dev)
  z_raw      = omp_target_alloc(bytes2D, dev)
  theta_raw  = omp_target_alloc(bytes2D, dev)
  qv_raw     = omp_target_alloc(bytes2D, dev)
  qc_raw     = omp_target_alloc(bytes2D, dev)
  qr_raw     = omp_target_alloc(bytes2D, dev)
  relhum_raw = omp_target_alloc(bytes2D, dev)
  temp_raw       = omp_target_alloc(bytes2D, dev)
  exner_raw      = omp_target_alloc(bytes2D, dev)
  temp_prev_raw  = omp_target_alloc(bytes2D, dev)
  st_energy_raw  = omp_target_alloc(bytes2D, dev)
  ttend_t_raw    = omp_target_alloc(bytes2D, dev)

  ierr = omp_target_associate_ptr(c_loc(cpair(1,1)),    cpair_raw,    bytes2D, 0_c_size_t, dev)
  ierr = omp_target_associate_ptr(c_loc(rair(1,1)),     rair_raw,     bytes2D, 0_c_size_t, dev)
  ierr = omp_target_associate_ptr(c_loc(rho(1,1)),      rho_raw,      bytes2D, 0_c_size_t, dev)
  ierr = omp_target_associate_ptr(c_loc(z(1,1)),        z_raw,        bytes2D, 0_c_size_t, dev)
  ierr = omp_target_associate_ptr(c_loc(theta(1,1)),    theta_raw,    bytes2D, 0_c_size_t, dev)
  ierr = omp_target_associate_ptr(c_loc(qv(1,1)),       qv_raw,       bytes2D, 0_c_size_t, dev)
  ierr = omp_target_associate_ptr(c_loc(qc(1,1)),       qc_raw,       bytes2D, 0_c_size_t, dev)
  ierr = omp_target_associate_ptr(c_loc(qr(1,1)),       qr_raw,       bytes2D, 0_c_size_t, dev)
  ierr = omp_target_associate_ptr(c_loc(relhum(1,1)),   relhum_raw,   bytes2D, 0_c_size_t, dev)
  ierr = omp_target_associate_ptr(c_loc(temp(1,1)),     temp_raw,     bytes2D, 0_c_size_t, dev)
  ierr = omp_target_associate_ptr(c_loc(exner(1,1)),    exner_raw,    bytes2D, 0_c_size_t, dev)
  ierr = omp_target_associate_ptr(c_loc(temp_prev(1,1)),temp_prev_raw,bytes2D, 0_c_size_t, dev)
  ierr = omp_target_associate_ptr(c_loc(st_energy(1,1)),st_energy_raw,bytes2D, 0_c_size_t, dev)
  ierr = omp_target_associate_ptr(c_loc(ttend_t(1,1)),  ttend_t_raw,  bytes2D, 0_c_size_t, dev)

  precl_raw = omp_target_alloc(bytes1D, dev)
  phis_raw  = omp_target_alloc(bytes1D, dev)
  ierr = omp_target_associate_ptr(c_loc(precl(1)), precl_raw, bytes1D, 0_c_size_t, dev)
  ierr = omp_target_associate_ptr(c_loc(phis(1)),  phis_raw,  bytes1D, 0_c_size_t, dev)

  !$omp target update to(cpair(1:ncol,1:nz), rair(1:ncol,1:nz), rho(1:ncol,1:nz), &
  !$omp      z(1:ncol,1:nz), exner(1:ncol,1:nz), theta(1:ncol,1:nz), qv(1:ncol,1:nz), &
  !$omp      qc(1:ncol,1:nz), qr(1:ncol,1:nz), precl(1:ncol), relhum(1:ncol,1:nz))
#endif

  version = 2

  !------------------------------
  ! kessler_update_timestep_init  (before timer — matches CCPP timestep_initial)
  !------------------------------
#ifdef USE_GPU
  !$omp target update to(temp(1:ncol,1:nz))
#endif

  call kessler_update_timestep_init(ncol, nz, temp, temp_prev, ttend_t, errmsg, errflg)

#ifdef USE_GPU
  !$omp target update from(temp_prev(1:ncol,1:nz), ttend_t(1:ncol,1:nz))
#endif

  call system_clock(t1, rate)
  !------------------------------------------------------
  ! Run microphysics + update  (matches CCPP physics run scope)
  !------------------------------------------------------
  if (version .eq. 1) then
     call kessler_runv1(ncol, nz, dt, lyr_surf, lyr_toa, &
                          cpair, rair, rho, z, exner, &
                          theta, qv, qc, qr, &
                          precl, relhum, scheme_name, errmsg, errflg)
  elseif (version .eq. 2) then
     call kessler_runv2(ncol, nz, dt, lyr_surf, lyr_toa, &
                          cpair, rair, rho, z, exner, &
                          theta, qv, qc, qr, &
                          precl, relhum, scheme_name, errmsg, errflg)
  endif

#ifdef USE_GPU
  !$omp target update from(theta(1:ncol,1:nz), qv(1:ncol,1:nz), &
  !$omp      qc(1:ncol,1:nz), qr(1:ncol,1:nz), precl(1:ncol), relhum(1:ncol,1:nz))
#endif

  !-------------------
  ! kessler_update_run
  !-------------------
#ifdef USE_GPU
  !$omp target update to(theta(1:ncol,1:nz), exner(1:ncol,1:nz), &
  !$omp      temp_prev(1:ncol,1:nz), ttend_t(1:ncol,1:nz))
#endif

  call kessler_update_run(nz, ncol, dt, theta, exner, temp_prev, &
             ttend_t, errmsg, errflg)

  call system_clock(t2)
  etime = real(t2 - t1, 8) / real(rate, 8)

#ifdef USE_GPU
  !$omp target update from(ttend_t(1:ncol,1:nz))
#endif

  !------------------------------
  ! kessler_update_timestep_final
  !------------------------------
#ifdef USE_GPU
  !$omp target update to(cpair(1:ncol,1:nz), temp(1:ncol,1:nz), &
  !$omp      z(1:ncol,1:nz), phis(1:ncol))
#endif

  call kessler_update_timestep_final(nz, ncol, cpair, temp, z, phis, &
             st_energy, errmsg, errflg)

#ifdef USE_GPU
  !$omp target update from(st_energy(1:ncol,1:nz))
#endif

  if (errflg /= 0) then
     print *, 'Run error: ', trim(errmsg)
  else
     call print_results(etime)
  end if

end program test_kessler_driver
