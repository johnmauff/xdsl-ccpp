// C++ host-model driver for the tinyddt chost example.
// Demonstrates DDT flattening: the C++ host holds state_temp as a raw pointer;
// the generated chost cap reconstructs tiny_state_t internally on the Fortran side.
//
// Build via:  make -f examples/tinyddt/Makefile
// Run via:    make -f examples/tinyddt/Makefile run
// Check via:  make -f examples/tinyddt/Makefile check

#include "Tinyddt_chost.hpp"

#include <cstdio>
#include <cstdlib>
#include <vector>

static constexpr int NCOL     = 4;
static constexpr int STATE_NZ = 3;

static void check(const char* label, const Tinyddt_chost::Status& s) {
    if (!s.ok()) {
        std::fprintf(stderr, "%s error: %s\n", label, s.message.c_str());
        std::exit(1);
    }
}

int main() {
    Tinyddt_chost::State state(NCOL, STATE_NZ);

    // Allocate temperature array in column-major order: (ncol, state_nz).
    std::vector<double> temp(NCOL * STATE_NZ, 200.0);
    state.state_temp = temp.data();

    check("register",   Tinyddt_chost::do_register());
    check("initialize", Tinyddt_chost::initialize());
    check("run",        Tinyddt_chost::run(state, 1, NCOL));
    check("finalize",   Tinyddt_chost::finalize());

    // tinyddt_run adds 1.0 K to all temperatures, so each should be 201.0.
    bool passed = true;
    for (int i = 0; i < NCOL * STATE_NZ; ++i) {
        if (temp[i] != 201.0) {
            std::fprintf(stderr, "FAIL: temp[%d] = %.1f, expected 201.0\n", i, temp[i]);
            passed = false;
        }
    }

    if (passed) {
        std::printf("PASS: all %d temperatures = %.1f "
                    "(initial 200.0 + 1.0 from tinyddt_run)\n",
                    NCOL * STATE_NZ, temp[0]);
        return 0;
    }
    return 1;
}
