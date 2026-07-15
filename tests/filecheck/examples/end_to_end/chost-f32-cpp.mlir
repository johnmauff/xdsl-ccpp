// Test that chost C++ header emits float when kind_phys maps to REAL32.
// Verifies the precision fix: the generated header must use float/float*
// rather than always emitting double/double*.
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/kessler/kessler_suite.xml --scheme-files examples/kessler/kessler.meta,examples/kessler/kessler_update.meta --host-files examples/kessler/kessler_host_mod.meta,examples/kessler/kessler_host_sub.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p "generate-meta-cap,generate-meta-kinds{extra_kind=kind_phys extra_iso=REAL32},generate-suite-cap,generate-ccpp-cap{bind_c=true explicit_args=true},generate-kinds,strip-ccpp" -t cpp_header | python3 -m filecheck %s

// typedef uses float for REAL32 kind.
// CHECK: typedef float     kind_phys_t;

// Initialize: scalar real args are float, not double.
// CHECK-LABEL: void Kessler_chost_physics_initialize(
// CHECK:           float            lv,
// CHECK:           float            gravit,
// CHECK-NOT:       double

// Timestep initial: intent(in) array is const float*, intent(inout) is float*.
// CHECK-LABEL: void Kessler_chost_physics_timestep_initial(
// CHECK:           const float*     temp,
// CHECK:           float*           temp_prev,
// CHECK-NOT:       double

// Run: scalar dt is float, intent(in) arrays are const float*, inout are float*.
// CHECK-LABEL: void Kessler_chost_physics_run(
// CHECK:           float            dt,
// CHECK:           const float*     cpair,
// CHECK:           float*           theta,
// CHECK:           float*           precl,
// CHECK-NOT:       double
