// Test that chost C++ header emits float when kind_phys maps to REAL32.
// Verifies the precision fix: the generated header must use float/float*
// rather than always emitting double/double*.
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/kessler/scheme/kessler_suite.xml --scheme-files examples/kessler/scheme/kessler.meta,examples/kessler/scheme/kessler_update.meta --host-files examples/kessler/host_cpp/kessler_host_mod.meta,examples/kessler/host_cpp/kessler_host_sub.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p "generate-meta-cap,generate-meta-kinds{extra_kind=kind_phys extra_iso=REAL32},generate-arg-ownership,generate-suite-cap,generate-ccpp-cap{bind_c=true},generate-cpp-cap,generate-kinds,strip-ccpp" -t cpp_header | python3 -m filecheck %s

// typedef uses float for REAL32 kind.
// CHECK: typedef float     kind_phys_t;

// task #28 Stage 3: initialize's own scheme calls (and their float args)
// moved to the new, group-scoped physics_initial entry point below --
// initialize itself is now scheme-call-free (errmsg/errflg only).
// CHECK-LABEL: void Kessler_chost_physics_initialize(
// CHECK:           char*            errmsg,

// Run: scalar dt is float, intent(in) arrays are const float*, inout are float*.
// CHECK-LABEL: void Kessler_chost_physics_run(
// CHECK:           float            dt,
// CHECK:           const float*     cpair,
// CHECK:           float*           theta,
// CHECK:           float*           precl,
// CHECK-NOT:       double

// Timestep initial: intent(in) array is const float*, intent(inout) is float*.
// (task #28: timestep_init is now group-scoped, generated after run.)
// CHECK-LABEL: void Kessler_chost_physics_timestep_initial(
// CHECK:           const float*     temp,
// CHECK:           float*           temp_prev,
// CHECK-NOT:       double

// Scalar real args (rank 0) in physics_initial use float, not double
// (task #28 Stage 3: generated last, after run/timestep_*/timestep_final).
// CHECK-LABEL: void Kessler_chost_physics_physics_initial(
// CHECK:           float            lv,
// CHECK:           float            gravit,
// CHECK-NOT:       double
