// C++ host-model driver for the tinyddt chost example.
// Demonstrates DDT flattening with two DDT arguments: tiny_state_t and tiny_tend_t.
// The generated chost cap reconstructs both DDTs internally on the Fortran side.
//
// tinyddt_run sets tend%dtemp = 1.0 and applies it to state%temp, so after one
// call: state_temp == 201.0 and tend_dtemp == 1.0.
//
// Build via:  make -f examples/tinyddt/Makefile
// Run via:    make -f examples/tinyddt/Makefile run
// Check via:  make -f examples/tinyddt/Makefile check

#include "Tinyddt_chost.hpp"

#include <cstdio>
#include <cstdlib>

static constexpr int NCOL     = 4;
static constexpr int STATE_NZ = 3;
static constexpr int TEND_NZ  = 3;

static void check(const char* label, const Tinyddt_chost::Status& s) {
    if (!s.ok()) {
        std::fprintf(stderr, "%s error: %s\n", label, s.message.c_str());
        std::exit(1);
    }
}

int main() {
    Tinyddt_chost::State state(NCOL, STATE_NZ, TEND_NZ);
    state.allocate();

    // Initialise temperatures to 200 K; tendencies to 0.
    for (int i = 0; i < NCOL * STATE_NZ; ++i)
        state.state_temp[i] = 200.0;
    for (int i = 0; i < NCOL * TEND_NZ; ++i)
        state.tend_dtemp[i] = 0.0;

    check("register",         Tinyddt_chost::do_register());
    check("initialize",       Tinyddt_chost::initialize());
    check("timestep_initial", Tinyddt_chost::timestep_initial());
    check("run",              Tinyddt_chost::run(state, 1, NCOL));
    check("timestep_final",   Tinyddt_chost::timestep_final());
    check("finalize",         Tinyddt_chost::finalize());

    // tinyddt_run sets tend%dtemp = 1.0 then adds it to state%temp.
    bool passed = true;

    for (int i = 0; i < NCOL * STATE_NZ; ++i) {
        if (state.state_temp[i] != 201.0) {
            std::fprintf(stderr, "FAIL: state_temp[%d] = %.1f, expected 201.0\n",
                         i, state.state_temp[i]);
            passed = false;
        }
    }

    for (int i = 0; i < NCOL * TEND_NZ; ++i) {
        if (state.tend_dtemp[i] != 1.0) {
            std::fprintf(stderr, "FAIL: tend_dtemp[%d] = %.1f, expected 1.0\n",
                         i, state.tend_dtemp[i]);
            passed = false;
        }
    }

    if (passed) {
        std::printf("PASS: all %d state_temp = %.1f, all %d tend_dtemp = %.1f\n",
                    NCOL * STATE_NZ, state.state_temp[0],
                    NCOL * TEND_NZ,  state.tend_dtemp[0]);
        return 0;
    }
    return 1;
}
