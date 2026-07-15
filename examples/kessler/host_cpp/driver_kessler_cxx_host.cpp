// C++ host-model driver for the Kessler microphysics example.
// Unlike driver_kessler_cpp.cpp, this driver owns all physics arrays directly.
// Kessler_chost::State::allocate() handles array allocation and pointer wiring.
// init_data() wraps init_data_c() with a State& interface.
//
// Build via:  make -f examples/kessler/Makefile cxx_host
// Run via:    make -f examples/kessler/Makefile run-cxx-host

#include "Kessler_chost.hpp"

#include <chrono>
#include <cstdio>
#include <cstdlib>

extern "C" {
    void init_data_c(
        int     ncol, int     nz,
        double* dt,   int*    lyr_surf, int*    lyr_toa,
        double* lv,   double* pref,     double* rhoqr,   double* gravit,
        double* cpair, double* rair, double* rho, double* z, double* exner,
        double* theta, double* qv,  double* qc,  double* qr,
        double* temp,  double* phis
    );

    void Kessler_chost_print_results(
        int ncol, int nz, const char* scheme_name, double elapsed_s,
        const double* theta, const double* qv,  const double* qc,
        const double* qr,    const double* precl, const double* relhum,
        const double* temp_prev, const double* ttend_t, const double* st_energy
    );
}

static constexpr int NCOL = 1000;
static constexpr int NZ   = 56;

// Fill State scalars and arrays from the shared portable RNG.
static void init_data(Kessler_chost::State& s) {
    init_data_c(s.ncol, s.nz,
        &s.dt, &s.lyr_surf, &s.lyr_toa,
        &s.lv, &s.pref, &s.rhoqr, &s.gravit,
        s.cpair, s.rair, s.rho, s.z, s.exner,
        s.theta, s.qv, s.qc, s.qr,
        s.temp, s.phis);
}

static void check(const char* label, const Kessler_chost::Status& s) {
    if (!s.ok()) {
        std::fprintf(stderr, "%s error: %s\n", label, s.message.c_str());
        std::exit(1);
    }
}

int main() {
    Kessler_chost::State state(NCOL, NZ);
    state.allocate();   // allocates and wires all array pointers
    init_data(state);   // fills scalars and array data

    check("initialize",       Kessler_chost::initialize(state));
    check("timestep_initial", Kessler_chost::timestep_initial(state));

    auto t_start = std::chrono::high_resolution_clock::now();
    check("run", Kessler_chost::run(state, 1, NCOL));
    auto t_end = std::chrono::high_resolution_clock::now();

    check("timestep_final", Kessler_chost::timestep_final(state));
    check("finalize",       Kessler_chost::finalize());

    double elapsed_s = std::chrono::duration<double>(t_end - t_start).count();

    Kessler_chost_print_results(NCOL, NZ, "kessler", elapsed_s,
        state.theta, state.qv, state.qc, state.qr,
        state.precl, state.relhum,
        state.temp_prev, state.ttend_t, state.st_energy);

    return 0;
}
