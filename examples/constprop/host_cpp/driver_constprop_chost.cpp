// C++ host-model driver for the constprop chost example.
//
// Purpose: validate gap 4c — constituent DDT array support.
//
// The constprop scheme registers one constituent (water_vapor_specific_humidity)
// during do_register().  The driver queries it back via get_constituents() and
// verifies the fields match what the scheme set.  The run lifecycle scales
// temperatures by 2x so the array write-back path is also exercised.
//
// Build via:  make -f examples/constprop/Makefile
// Run  via:   make -f examples/constprop/Makefile run
// Check via:  make -f examples/constprop/Makefile check

#include "constprop_host_sub_chost.hpp"

#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace CP = constprop_host_sub_chost;

static constexpr int NCOL = 4;
static constexpr int NZ   = 3;

static void check(const char* label, const CP::Status& s) {
    if (!s.ok()) {
        std::fprintf(stderr, "%s error: %s\n", label, s.message.c_str());
        std::exit(1);
    }
}

int main() {
    bool passed = true;

    // ── 1. Register ────────────────────────────────────────────────────────────
    check("register", CP::do_register());

    // ── 2. Query constituent info ──────────────────────────────────────────────
    int n = CP::nconstituents();
    if (n != 1) {
        std::fprintf(stderr, "FAIL: nconstituents() = %d, expected 1\n", n);
        return 1;
    }

    auto props = CP::get_constituents();
    if (static_cast<int>(props.size()) != n) {
        std::fprintf(stderr, "FAIL: get_constituents() returned %zu entries, expected %d\n",
                     props.size(), n);
        return 1;
    }

    // Verify the one constituent registered by constprop_register().
    const CcppConstituentInfo& p = props[0];

    if (std::strcmp(p.std_name, "water_vapor_specific_humidity") != 0) {
        std::fprintf(stderr, "FAIL: std_name = '%s', expected 'water_vapor_specific_humidity'\n",
                     p.std_name);
        passed = false;
    }
    if (std::strcmp(p.long_name, "Water vapour specific humidity") != 0) {
        std::fprintf(stderr, "FAIL: long_name = '%s', expected 'Water vapour specific humidity'\n",
                     p.long_name);
        passed = false;
    }
    if (std::strcmp(p.units, "kg kg-1") != 0) {
        std::fprintf(stderr, "FAIL: units = '%s', expected 'kg kg-1'\n", p.units);
        passed = false;
    }
    if (!p.is_advected_flag) {
        std::fprintf(stderr, "FAIL: is_advected_flag = false, expected true\n");
        passed = false;
    }
    if (p.default_val != 0.0) {
        std::fprintf(stderr, "FAIL: default_val = %g, expected 0.0\n", p.default_val);
        passed = false;
    }

    // ── 3. Full physics lifecycle ──────────────────────────────────────────────
    check("initialize",       CP::initialize());
    check("timestep_initial", CP::timestep_initial());

    CP::State state(NCOL, NZ);
    state.allocate();
    for (int i = 0; i < NCOL * NZ; ++i)
        state.temp[i] = 1.0;

    // constprop_run multiplies temp by 2x in the active chunk.
    check("run", CP::run(state, 1, NCOL));

    for (int i = 0; i < NCOL * NZ; ++i) {
        if (state.temp[i] != 2.0) {
            std::fprintf(stderr, "FAIL: temp[%d] = %.1f, expected 2.0\n", i, state.temp[i]);
            passed = false;
        }
    }

    check("timestep_final", CP::timestep_final());
    check("finalize",       CP::finalize());

    // ── 4. Report ──────────────────────────────────────────────────────────────
    if (passed) {
        std::printf("PASS: nconstituents=%d, std_name='%s', is_advected=%s, "
                    "all %d temp = %.1f after 2x scale\n",
                    n, p.std_name, p.is_advected_flag ? "true" : "false",
                    NCOL * NZ, state.temp[0]);
        return 0;
    }
    return 1;
}
