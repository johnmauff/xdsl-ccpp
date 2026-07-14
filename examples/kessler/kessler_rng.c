#include <stdint.h>
#include <math.h>

#define KESSLER_PI 3.14159265358979323846

static uint64_t rng_state;

static uint64_t xorshift64_next(void) {
    rng_state ^= rng_state << 13;
    rng_state ^= rng_state >> 7;
    rng_state ^= rng_state << 17;
    return rng_state;
}

/* Returns a value in (0, 1) — LSB forced to 1 to avoid exactly zero */
static double rng_uniform(void) {
    return ((xorshift64_next() >> 11) | 1ULL) * (1.0 / (double)(1ULL << 53));
}

/*
 * Fill arr[0..ncol-1] with independent N(1, 0.1) samples via Box-Muller.
 * Fixed seed guarantees the same sequence across languages and compilers.
 */
void kessler_rng_fill(double* arr, int ncol)
{
    rng_state = 123456789ULL;
    for (int i = 0; i < ncol; i++) {
        double u1 = rng_uniform();
        double u2 = rng_uniform();
        double z  = sqrt(-2.0 * log(u1)) * cos(2.0 * KESSLER_PI * u2);
        arr[i] = 1.0 + 0.1 * z;
    }
}
