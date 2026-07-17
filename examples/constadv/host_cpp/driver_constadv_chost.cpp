#include <cassert>
#include <cstdio>
#include <cstring>
#include "constadv_host_sub_chost.hpp"

namespace CA = constadv_host_sub_chost;

int main() {
    // ── Phase 1: register ───────────────────────────────────────────────────
    // Constituents are registered here; ncnst is unknown before this call.
    {
        auto s = CA::do_register();
        if (!s.ok()) {
            std::fprintf(stderr, "do_register failed: %s\n", s.message.c_str());
            return 1;
        }
    }

    int ncnst = CA::nconstituents();
    if (ncnst != 2) {
        std::fprintf(stderr, "expected ncnst=2, got %d\n", ncnst);
        return 1;
    }

    // Verify constituent metadata
    auto consts = CA::get_constituents();
    if (std::strcmp(consts[0].std_name, "water_vapor_specific_humidity") != 0) {
        std::fprintf(stderr, "wrong constituent[0].std_name: %s\n", consts[0].std_name);
        return 1;
    }
    if (std::strcmp(consts[1].std_name, "cloud_ice_dry_mixing_ratio") != 0) {
        std::fprintf(stderr, "wrong constituent[1].std_name: %s\n", consts[1].std_name);
        return 1;
    }

    // ── Phase 2: initialize ─────────────────────────────────────────────────
    {
        auto s = CA::initialize();
        if (!s.ok()) {
            std::fprintf(stderr, "initialize failed: %s\n", s.message.c_str());
            return 1;
        }
    }

    // ── Allocate state with runtime ncnst ───────────────────────────────────
    // ncnst is now known; State constructor and allocate() use it.
    constexpr int NCOL = 4, NZ = 3;
    CA::State st{NCOL, NZ, ncnst};
    st.allocate();

    // Fill q with 1.0  (column-major: i varies fastest, then k, then n)
    for (int n = 0; n < ncnst; n++)
        for (int k = 0; k < NZ; k++)
            for (int i = 0; i < NCOL; i++)
                st.q[i + NCOL * (k + NZ * n)] = 1.0;

    // ── Timestep ────────────────────────────────────────────────────────────
    {
        auto s = CA::timestep_initial();
        if (!s.ok()) { std::fprintf(stderr, "timestep_initial failed\n"); return 1; }
    }
    {
        auto s = CA::run(st, 1, NCOL);
        if (!s.ok()) {
            std::fprintf(stderr, "run failed: %s\n", s.message.c_str());
            return 1;
        }
    }
    {
        auto s = CA::timestep_final();
        if (!s.ok()) { std::fprintf(stderr, "timestep_final failed\n"); return 1; }
    }

    // ── Verify q == 2.0 ─────────────────────────────────────────────────────
    for (int n = 0; n < ncnst; n++) {
        for (int k = 0; k < NZ; k++) {
            for (int i = 0; i < NCOL; i++) {
                double val = st.q[i + NCOL * (k + NZ * n)];
                if (val != 2.0) {
                    std::fprintf(stderr,
                        "q[%d,%d,%d] = %g, expected 2.0\n", i, k, n, val);
                    return 1;
                }
            }
        }
    }

    // ── Finalize ─────────────────────────────────────────────────────────────
    {
        auto s = CA::finalize();
        if (!s.ok()) { std::fprintf(stderr, "finalize failed\n"); return 1; }
    }

    std::puts("PASS");
    return 0;
}
