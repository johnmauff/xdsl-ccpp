// C++ host-model driver for the nestedddt chost example.
// Exercises nested DDT flattening: outer_phys_t contains inner_phys_t.
// The generated chost cap reconstructs both DDTs on the Fortran side.
//
// nestedddt_run doubles all temperatures in the active column range, so
// after one call: state_inner_temp[*] == 2.0 (initialised to 1.0).
//
// Expected flat State fields (after gap-4b fix):
//   int     state_inner_nz        — inner_phys_t%nz
//   double* state_inner_temp      — inner_phys_t%temp(ncol, nz)
//
// Build via:  make -f examples/nestedddt/Makefile
// Run via:    make -f examples/nestedddt/Makefile run
// Check via:  make -f examples/nestedddt/Makefile check

#include "Nestedddt_chost.hpp"

#include <cstdio>
#include <cstdlib>

static constexpr int NCOL = 4;
static constexpr int NZ   = 3;

static void check(const char* label, const Nestedddt_chost::Status& s) {
    if (!s.ok()) {
        std::fprintf(stderr, "FAIL (%s): %s\n", label, s.message.c_str());
        std::exit(1);
    }
}

int main() {
    Nestedddt_chost::State state(NCOL, NZ);
    state.allocate();

    // Initialise all temperatures to 1.0 K.
    for (int i = 0; i < NCOL * NZ; ++i)
        state.state_inner_temp[i] = 1.0;

    // CCPP call sequence
    check("register",         Nestedddt_chost::do_register());
    check("initialize",       Nestedddt_chost::initialize());
    check("timestep_initial", Nestedddt_chost::timestep_initial());
    check("run",              Nestedddt_chost::run(state, 1, NCOL));
    check("timestep_final",   Nestedddt_chost::timestep_final());
    check("finalize",         Nestedddt_chost::finalize());

    // Verify: nestedddt_run doubles temp, so every element should be 2.0.
    bool passed = true;
    for (int i = 0; i < NCOL * NZ; ++i) {
        if (state.state_inner_temp[i] != 2.0) {
            std::fprintf(stderr,
                "FAIL: state_inner_temp[%d] = %.1f, expected 2.0\n",
                i, state.state_inner_temp[i]);
            passed = false;
        }
    }

    if (passed) {
        std::printf("PASS: %d columns x %d levels, state_inner_temp = %.1f\n",
                    NCOL, NZ, state.state_inner_temp[0]);
        return 0;
    }
    return 1;
}
