// C++ host-model driver for the capgen chost example.
// Exercises three schemes in one group:
//   make_ddt:       O3/HNO3 → vmr DDT (validated by timestep_final)
//   setup_coeffs:   coeffs[:] = 1.0  (set during timestep_initial)
//   temp_calc_adjust: temp_calc[:] = 1.0 (ignores temp_level, sets output)
//
// make_ddt physics:
//   initialize:     allocates vmr%vmr_array(ncols, 2); sets vmr%nvmr = 2
//   run:            vmr_array(:,1) = O3(:); vmr_array(:,2) = HNO3(:)
//   timestep_final: validates vmr_array(i,1)==i*1e-6 and vmr_array(i,2)==i*1e-9
//                   (Fortran 1-indexed); returns errflg=0 on pass
//
// Build via:  make -f examples/capgen/Makefile cxx_host
// Run via:    make -f examples/capgen/Makefile run-cxx-host
// Check via:  make -f examples/capgen/Makefile check

#include "CapgenChost_chost.hpp"

#include <cstdio>
#include <cstdlib>

static constexpr int NCOL    = 5;
static constexpr int VMR_NVS = 2;   // hardcoded by make_ddt_init: vmr%nvmr = 2
static constexpr int PVERP   = 4;   // number of vertical interfaces

static void check(const char* label, const CapgenChost_chost::Status& s) {
    if (!s.ok()) {
        std::fprintf(stderr, "FAIL (%s): %s\n", label, s.message.c_str());
        std::exit(1);
    }
}

int main() {
    CapgenChost_chost::State state(NCOL, VMR_NVS, PVERP);
    state.allocate();

    // Driving data: O3[i] = (i+1)*1e-6, HNO3[i] = (i+1)*1e-9  (0-indexed C++)
    for (int i = 0; i < NCOL; ++i) {
        state.O3[i]   = (i + 1) * 1.0e-6;
        state.HNO3[i] = (i + 1) * 1.0e-9;
    }

    // temp_level: arbitrary input values (temp_calc_adjust_run ignores them)
    for (int col = 0; col < NCOL; ++col)
        for (int lev = 0; lev < PVERP; ++lev)
            state.temp_interfaces[col + NCOL * lev] = 200.0 + lev * 5.0;

    state.dt = 1800.0;

    // CCPP call sequence
    check("register",         CapgenChost_chost::do_register());
    check("initialize",       CapgenChost_chost::initialize(state));
    check("timestep_initial", CapgenChost_chost::timestep_initial(state));
    check("run",              CapgenChost_chost::run(state, 1, NCOL));
    // make_ddt_timestep_final validates vmr_array in Fortran; errflg!=0 == fail
    check("timestep_final",   CapgenChost_chost::timestep_final(state));
    check("finalize",         CapgenChost_chost::finalize());

    // Verify vmr_vmr_array in C++ (column-major: first col = O3, second = HNO3)
    bool passed = true;
    for (int i = 0; i < NCOL; ++i) {
        double expected_O3   = (i + 1) * 1.0e-6;
        double expected_HNO3 = (i + 1) * 1.0e-9;
        double got_O3        = state.vmr_vmr_array[i];
        double got_HNO3      = state.vmr_vmr_array[NCOL + i];
        if (got_O3 != expected_O3) {
            std::fprintf(stderr,
                "FAIL: vmr_vmr_array[%d] (O3)   = %.3e, expected %.3e\n",
                i, got_O3, expected_O3);
            passed = false;
        }
        if (got_HNO3 != expected_HNO3) {
            std::fprintf(stderr,
                "FAIL: vmr_vmr_array[%d] (HNO3) = %.3e, expected %.3e\n",
                NCOL + i, got_HNO3, expected_HNO3);
            passed = false;
        }
    }

    // Verify coeffs (setup_coeffs_timestep_init sets all to 1.0)
    for (int i = 0; i < NCOL; ++i) {
        if (state.coeffs[i] != 1.0) {
            std::fprintf(stderr, "FAIL: coeffs[%d] = %.3e, expected 1.0\n",
                i, state.coeffs[i]);
            passed = false;
        }
    }

    // Verify temp_calc (temp_calc_adjust_run sets all to 1.0)
    for (int i = 0; i < NCOL; ++i) {
        if (state.temp_calc[i] != 1.0) {
            std::fprintf(stderr, "FAIL: temp_calc[%d] = %.3e, expected 1.0\n",
                i, state.temp_calc[i]);
            passed = false;
        }
    }

    if (passed) {
        std::printf("PASS: %d columns, vmr_nvmr=%d, pverP=%d\n",
                    NCOL, VMR_NVS, PVERP);
        std::printf("  O3   [0..%d]: %.3e .. %.3e\n",
                    NCOL - 1, state.vmr_vmr_array[0], state.vmr_vmr_array[NCOL - 1]);
        std::printf("  HNO3 [0..%d]: %.3e .. %.3e\n",
                    NCOL - 1, state.vmr_vmr_array[NCOL], state.vmr_vmr_array[2 * NCOL - 1]);
        std::printf("  coeffs[0..%d]: %.3e .. %.3e\n",
                    NCOL - 1, state.coeffs[0], state.coeffs[NCOL - 1]);
        std::printf("  temp_calc[0..%d]: %.3e .. %.3e\n",
                    NCOL - 1, state.temp_calc[0], state.temp_calc[NCOL - 1]);
        return 0;
    }
    return 1;
}
