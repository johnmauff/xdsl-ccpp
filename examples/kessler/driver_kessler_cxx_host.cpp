// C++ host-model driver for the Kessler microphysics example.
// Unlike driver_kessler_cpp.cpp, this driver owns all physics arrays directly
// as std::vector<double>.  Data is initialized by init_data_c() (same C RNG
// as the Fortran init_data), then passed as column-major pointers to the
// BIND(C) chost cap (Kessler_ccpp_chost_cap.F90).  kessler_host_mod is not
// linked.
//
// Build via:  make -f examples/kessler/Makefile cxx_host
// Run via:    make -f examples/kessler/Makefile run-cxx-host

#include "Kessler_ccpp_chost_cap.h"

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

// Declared in init_data_c.c
extern "C" {
    void init_data_c(
        int     ncol,
        int     nz,
        double* dt,
        int*    lyr_surf,
        int*    lyr_toa,
        double* lv,
        double* pref,
        double* rhoqr,
        double* gravit,
        double* cpair,
        double* rair,
        double* rho,
        double* z,
        double* exner,
        double* theta,
        double* qv,
        double* qc,
        double* qr,
        double* temp,
        double* phis
    );
}

static constexpr int NCOL           = 1000;
static constexpr int NZ             = 56;
static constexpr int ERRMSG_LEN     = 512;
static constexpr int SCHEME_LEN     = 65;

static void check(const char* label, const char* errmsg, int errflg) {
    if (errflg != 0) {
        std::fprintf(stderr, "%s error: %s\n", label, errmsg);
        std::exit(1);
    }
}

int main() {
    char errmsg[ERRMSG_LEN];
    char scheme_name[SCHEME_LEN];
    int  errflg = 0;

    // Scalars returned by init_data_c
    double dt, lv, pref, rhoqr, gravit;
    int    lyr_surf, lyr_toa;

    // Physics arrays owned by C++ host (column-major: element (i,k) at k*NCOL+i)
    std::vector<double> cpair    (NCOL * NZ);
    std::vector<double> rair     (NCOL * NZ);
    std::vector<double> rho      (NCOL * NZ);
    std::vector<double> z        (NCOL * NZ);
    std::vector<double> exner    (NCOL * NZ);
    std::vector<double> theta    (NCOL * NZ);
    std::vector<double> qv       (NCOL * NZ);
    std::vector<double> qc       (NCOL * NZ);
    std::vector<double> qr       (NCOL * NZ);
    std::vector<double> temp     (NCOL * NZ);
    std::vector<double> temp_prev(NCOL * NZ, 0.0);
    std::vector<double> ttend_t  (NCOL * NZ, 0.0);
    std::vector<double> st_energy(NCOL * NZ, 0.0);
    std::vector<double> precl    (NCOL,      0.0);
    std::vector<double> relhum   (NCOL * NZ, 0.0);
    std::vector<double> phis     (NCOL);

    // Initialize arrays from C++ using the shared portable RNG
    init_data_c(NCOL, NZ,
        &dt, &lyr_surf, &lyr_toa, &lv, &pref, &rhoqr, &gravit,
        cpair.data(), rair.data(), rho.data(), z.data(), exner.data(),
        theta.data(), qv.data(), qc.data(), qr.data(),
        temp.data(), phis.data());

    // Initialize physics constants (kessler_init, kessler_update_init)
    std::memset(errmsg, 0, sizeof(errmsg));
    Kessler_chost_physics_initialize(lv, pref, rhoqr, gravit, errmsg, &errflg);
    check("initialize", errmsg, errflg);

    // Timestep initial: copies temp -> temp_prev, zeroes ttend_t
    std::memset(errmsg, 0, sizeof(errmsg));
    Kessler_chost_physics_timestep_initial(NCOL, NZ,
        temp.data(), temp_prev.data(), ttend_t.data(), errmsg, &errflg);
    check("timestep_initial", errmsg, errflg);

    // Run physics (timed)
    std::memset(errmsg, 0, sizeof(errmsg));
    std::memset(scheme_name, 0, sizeof(scheme_name));
    auto t_start = std::chrono::high_resolution_clock::now();
    Kessler_chost_physics_run(NCOL, NZ, dt, lyr_surf, lyr_toa,
        cpair.data(), rair.data(), rho.data(), z.data(), exner.data(),
        theta.data(), qv.data(), qc.data(), qr.data(),
        precl.data(), relhum.data(),
        temp_prev.data(), ttend_t.data(),
        scheme_name, errmsg, &errflg);
    auto t_end = std::chrono::high_resolution_clock::now();
    check("run", errmsg, errflg);

    double elapsed_s = std::chrono::duration<double>(t_end - t_start).count();

    // Timestep final: computes dry static energy
    std::memset(errmsg, 0, sizeof(errmsg));
    Kessler_chost_physics_timestep_final(NCOL, NZ,
        cpair.data(), temp.data(), z.data(), phis.data(), st_energy.data(),
        errmsg, &errflg);
    check("timestep_final", errmsg, errflg);

    // Finalize
    std::memset(errmsg, 0, sizeof(errmsg));
    Kessler_chost_physics_finalize(errmsg, &errflg);
    check("finalize", errmsg, errflg);

    // Print sums via Fortran for identical reduction order and output format
    Kessler_chost_print_results(NCOL, NZ, scheme_name, elapsed_s,
        theta.data(), qv.data(), qc.data(), qr.data(),
        precl.data(), relhum.data(),
        temp_prev.data(), ttend_t.data(), st_energy.data());

    return 0;
}
