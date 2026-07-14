// Driver-facing chost cap header.  Includes the generated CCPP lifecycle
// declarations and adds the hand-written print-results utility.
#pragma once
#include "bindc/Kessler_ccpp_chost_cap.h"

#ifdef __cplusplus
extern "C" {
#endif

// Print sums via Fortran SUM — output format matches kessler_host_mod::print_results.
void Kessler_chost_print_results(
    int           ncol,
    int           nz,
    const char*   scheme_name,
    double        elapsed_s,
    const double* theta,
    const double* qv,
    const double* qc,
    const double* qr,
    const double* precl,
    const double* relhum,
    const double* temp_prev,
    const double* ttend_t,
    const double* st_energy
);

#ifdef __cplusplus
}
#endif
