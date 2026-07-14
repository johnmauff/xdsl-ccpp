// Hand-written BIND(C) cap for a C++ host model.
// All physics arrays are owned by the C++ caller and passed as column-major
// (Fortran-order) pointers.  kessler_host_mod is not involved.
#pragma once
#ifdef __cplusplus
extern "C" {
#endif

// Initialize physics constants (kessler_init + kessler_update_init).
void Kessler_chost_physics_initialize(
    double  lv,
    double  pref,
    double  rhoqr,
    double  gravit,
    char*   errmsg,
    int*    errflg
);

// Finalize the physics suite.
void Kessler_chost_physics_finalize(
    char*   errmsg,
    int*    errflg
);

// Timestep initial: copies temp -> temp_prev, zeroes ttend_t.
// Arrays are [ncol*nz] column-major.
void Kessler_chost_physics_timestep_initial(
    int           ncol,
    int           nz,
    const double* temp,
    double*       temp_prev,
    double*       ttend_t,
    char*         errmsg,
    int*          errflg
);

// Run kessler microphysics + kessler_update.
// 2D arrays are [ncol*nz] column-major; precl/relhum_1d is [ncol].
// scheme_name is a null-terminated output string (caller supplies >= 65 bytes).
void Kessler_chost_physics_run(
    int           ncol,
    int           nz,
    double        dt,
    int           lyr_surf,
    int           lyr_toa,
    const double* cpair,
    const double* rair,
    const double* rho,
    const double* z,
    const double* exner,
    double*       theta,
    double*       qv,
    double*       qc,
    double*       qr,
    double*       precl,
    double*       relhum,
    const double* temp_prev,
    double*       ttend_t,
    char*         scheme_name,
    char*         errmsg,
    int*          errflg
);

// Timestep final: computes dry static energy.
void Kessler_chost_physics_timestep_final(
    int           ncol,
    int           nz,
    const double* cpair,
    const double* temp,
    const double* z,
    const double* phis,
    double*       st_energy,
    char*         errmsg,
    int*          errflg
);

// Print sums via Fortran SUM — output format matches kessler_host_mod::print_results.
void Kessler_chost_print_results(
    int           ncol,
    int           nz,
    const char*   scheme_name,
    double        elapsed_s,
    const double* theta,
    const double* qv,
    const double* qc,
    const double* qr,
    const double* precl,
    const double* relhum,
    const double* temp_prev,
    const double* ttend_t,
    const double* st_energy
);

#ifdef __cplusplus
}
#endif
