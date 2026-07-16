// C++ host-model driver for the ddthost chost example.
// Exercises DDT flattening for intent=out (initialize) and intent=inout (run)
// DDT args. The generated chost cap reconstructs the vmr_type DDT on the
// Fortran side; C++ owns all arrays as flat buffers.
//
// make_ddt physics:
//   init:           allocates vmr%vmr_array(ncols, 2); sets vmr%nvmr = 2
//   run:            vmr_array(:,1) = O3(:); vmr_array(:,2) = HNO3(:)
//   timestep_final: validates vmr_array(i,1)==i*1e-6 and vmr_array(i,2)==i*1e-9
//                   (Fortran 1-indexed); returns errflg=0 on pass
//
// Build via:  make -f examples/ddthost/Makefile cxx_host
// Run via:    make -f examples/ddthost/Makefile run-cxx-host
// Check via:  make -f examples/ddthost/Makefile check-cxx-host

#include "Ddthost_chost.hpp"

#include <cstdio>
#include <cstdlib>
#include <cmath>

static constexpr int NCOL    = 5;
static constexpr int VMR_NVS = 2;   // hardcoded by make_ddt_init: vmr%nvmr = 2

static void check(const char* label, const Ddthost_chost::Status& s) {
    if (!s.ok()) {
        std::fprintf(stderr, "FAIL (%s): %s\n", label, s.message.c_str());
        std::exit(1);
    }
}

int main() {
    Ddthost_chost::State state(NCOL, VMR_NVS);
    state.allocate();

    // ccpp_info members forwarded to make_ddt_init (scheme only uses nbox/ncols)
    state.ccpp_info_col_start = 1;
    state.ccpp_info_col_end   = NCOL;
    state.ccpp_info_errflg    = 0;

    // Driving data: O3[i] = (i+1)*1e-6, HNO3[i] = (i+1)*1e-9  (0-indexed C++)
    for (int i = 0; i < NCOL; ++i) {
        state.O3[i]   = (i + 1) * 1.0e-6;
        state.HNO3[i] = (i + 1) * 1.0e-9;
    }

    // CCPP call sequence
    check("register",         Ddthost_chost::do_register());
    check("initialize",       Ddthost_chost::initialize(state));
    check("timestep_initial", Ddthost_chost::timestep_initial());
    check("run",              Ddthost_chost::run(state, 1, NCOL));
    // make_ddt_timestep_final validates vmr_array in Fortran; errflg!=0 == fail
    check("timestep_final",   Ddthost_chost::timestep_final(state));
    check("finalize",         Ddthost_chost::finalize());

    // Also verify vmr_vmr_array in C++ (column-major: first col = O3, second = HNO3)
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

    if (passed) {
        std::printf("PASS: %d columns, vmr_nvmr=%d\n", NCOL, VMR_NVS);
        std::printf("  O3   [0..%d]: %.3e .. %.3e\n",
                    NCOL - 1, state.vmr_vmr_array[0], state.vmr_vmr_array[NCOL - 1]);
        std::printf("  HNO3 [0..%d]: %.3e .. %.3e\n",
                    NCOL - 1, state.vmr_vmr_array[NCOL], state.vmr_vmr_array[2 * NCOL - 1]);
        return 0;
    }
    return 1;
}
