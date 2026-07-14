#include <math.h>
#include <stdlib.h>

/* Declared in kessler_rng.c */
extern void kessler_rng_fill(double* arr, int ncol);

/*
 * C mirror of kessler_host_mod::init_data().  Fills scalar parameters and
 * physics arrays using the shared kessler_rng_fill RNG so results match the
 * Fortran initialisation bit-for-bit.
 *
 * Arrays cpair..temp are [ncol*nz] in column-major (Fortran) order:
 *   element (i, k) is at index  k * ncol + i  (0-based i and k).
 * phis is [ncol].
 */
void init_data_c(
    int     ncol,
    int     nz,
    double* dt,
    int*    lyr_surf,
    int*    lyr_toa,
    double* lv,
    double* pref,
    double* rhoqr,
    double* gravit,
    double* cpair,
    double* rair,
    double* rho,
    double* z,
    double* exner,
    double* theta,
    double* qv,
    double* qc,
    double* qr,
    double* temp,
    double* phis
) {
    *dt       = 60.0;
    *lyr_surf = 1;
    *lyr_toa  = nz;
    *lv       = 2.5e6;
    *pref     = 100000.0;
    *rhoqr    = 1000.0;
    *gravit   = 9.80616;

    double* arr = (double*)malloc((size_t)ncol * sizeof(double));
    kessler_rng_fill(arr, ncol);

    for (int i = 0; i < ncol; i++) {
        double a = arr[i];
        for (int k = 0; k < nz; k++) {
            int    idx  = k * ncol + i;
            double zval = a * (100.0 * (double)k);
            cpair[idx] = 1004.0;
            rair[idx]  = 287.0;
            z[idx]     = zval;
            rho[idx]   = a * (1.2 * exp(-zval / 8000.0));
            exner[idx] = a;
            theta[idx] = a * (300.0 - 0.006 * zval);
            qv[idx]    = a * 0.010;
            qc[idx]    = a * 0.01;
            qr[idx]    = a * 0.01;
            temp[idx]  = a * 287.4;
        }
        phis[i] = a * 0.1;
    }

    free(arr);
}
