// Test end-to-end RESHAPE generation for row_major host arrays.
//
// When a host table declares array_layout = row_major, the generated CCPP cap
// must transpose 2D+ arrays from row-major to column-major before forwarding
// them to the suite cap (using Fortran RESHAPE), and write them back after.
// 1D arrays from the same host (e.g. temperature) are passed through directly.
//
// RUN: python3 tests/filecheck/examples/array_layout_suite.py | python3 -m xdsl_ccpp.tools.ccpp_opt -p generate-meta-cap,generate-meta-kinds,generate-host-match,generate-arg-ownership,generate-suite-cap,generate-ccpp-cap,generate-cpp-cap,generate-kinds,strip-ccpp -t ftn | python3 -m filecheck %s

// The host cap uses host module variables for theta and temperature.
// CHECK-LABEL: module Tiny_ccpp_cap
// CHECK:         use tiny_host_mod, only: nz_total
// CHECK-NEXT:    use tiny_host_mod, only: temperature
// CHECK-NEXT:    use tiny_host_mod, only: theta

// A column-major scratch buffer is declared in the run subroutine (local, not module-level).
// CHECK-LABEL:   subroutine Tiny_ccpp_physics_run(suite_name, suite_part, col_start, col_end, errmsg,
// CHECK:           real(kind=kind_phys), allocatable :: theta_col(:, :)

// Forward convert: allocate then reshape host theta → column-major theta_col.
// CHECK:           allocate(theta_col(col_end - col_start + 1, nz_total))
// CHECK-NEXT:      theta_col = reshape(theta, [col_end - col_start + 1, nz_total], order=[2, 1])

// The suite call receives theta_col (transposed) and temperature (unchanged, 1D).
// CHECK:           call tiny_suite_suite_physics(col_start, col_end, nz_total, temperature, theta_col,
// CHECK-NOT:       reshape(temperature

// Write-back: transpose theta_col back to row-major theta, then deallocate.
// CHECK:           theta = reshape(theta_col, [nz_total, col_end - col_start + 1], order=[2, 1])
// CHECK-NEXT:      deallocate(theta_col)
