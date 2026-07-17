// C++ host-model driver for the chararg chost example.
//
// Purpose: validate gap 9 — character(len=N) scalar arg support.
//
// The chararg scheme takes a fixed-length character(len=32) label arg (intent=in).
// The driver passes a non-empty label and verifies:
//   1. The cap accepts a const char* label without crashing.
//   2. The scheme rejects an empty label (errflg != 0).
//   3. With a valid label the scheme scales temperature by 3x.
//
// Build via:  make -f examples/chararg/Makefile
// Check via:  make -f examples/chararg/Makefile check

#include "chararg_host_sub_chost.hpp"

#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace CA = chararg_host_sub_chost;

static constexpr int NCOL = 4;
static constexpr int NZ   = 3;

static void check(const char* label, const CA::Status& s) {
    if (!s.ok()) {
        std::fprintf(stderr, "%s error: %s\n", label, s.message.c_str());
        std::exit(1);
    }
}

int main() {
    bool passed = true;

    // ── 1. Full lifecycle with a valid label ──────────────────────────────────
    check("register",         CA::do_register());
    check("initialize",       CA::initialize());
    check("timestep_initial", CA::timestep_initial());

    CA::State state(NCOL, NZ);
    state.allocate();
    for (int i = 0; i < NCOL * NZ; ++i)
        state.temp[i] = 1.0;

    // chararg_run multiplies temp by 3x when label is non-empty.
    check("run", CA::run({
        .ncol      = NCOL,
        .nz        = NZ,
        .col_start = 1,
        .col_end   = NCOL,
        .temp      = state.temp,
        .label     = "physics_pass_1",
    }));

    for (int i = 0; i < NCOL * NZ; ++i) {
        if (state.temp[i] != 3.0) {
            std::fprintf(stderr, "FAIL: temp[%d] = %.1f, expected 3.0\n", i, state.temp[i]);
            passed = false;
        }
    }

    // ── 2. Empty label must return errflg != 0 ────────────────────────────────
    {
        CA::Status s = CA::run({
            .ncol      = NCOL,
            .nz        = NZ,
            .col_start = 1,
            .col_end   = NCOL,
            .temp      = state.temp,
            .label     = "",
        });
        if (s.ok()) {
            std::fprintf(stderr, "FAIL: expected error for empty label, got ok\n");
            passed = false;
        }
    }

    check("timestep_final", CA::timestep_final());
    check("finalize",       CA::finalize());

    // ── 3. Report ──────────────────────────────────────────────────────────────
    if (passed) {
        std::printf("PASS: label='physics_pass_1' correctly transmitted to scheme; "
                    "all %d temp = %.1f after 3x scale\n",
                    NCOL * NZ, state.temp[0]);
        return 0;
    }
    return 1;
}
