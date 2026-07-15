// Test --bind-c mode of generate-ccpp-cap for the kessler example.
// Verifies that the ccpp_cap module subroutines carry BIND(C) signatures,
// use iso_c_binding at module scope, and declare arguments with C-compatible
// types.  Also verifies the physics run subroutine maps scalar intent(in)
// arguments with VALUE and real arrays as c_double assumed-size.
// Utility subroutines (ccpp_physics_suite_list, ccpp_physics_suite_part_list)
// must NOT be marked BIND(C).
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/kessler/scheme/kessler_suite.xml --scheme-files examples/kessler/scheme/kessler.meta,examples/kessler/scheme/kessler_update.meta --host-files examples/kessler/host_ftn/kessler_host_mod.meta,examples/kessler/host_ftn/kessler_host_sub.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p "generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap{bind_c=true},generate-kinds,strip-ccpp" -t ftn | python3 -m filecheck %s

// The ccpp_cap module uses iso_c_binding for all BIND(C) subroutines.
// CHECK-LABEL: module Kessler_ccpp_cap
// CHECK:         use ccpp_kinds
// CHECK:         use iso_c_binding

// Register: BIND(C) clause present, c_char and c_int argument types.
// CHECK-LABEL:   subroutine Kessler_ccpp_physics_register(suite_name, errmsg, errflg) BIND(C,
// CHECK:           character(kind=c_char, len=1), intent(in) :: suite_name(*)
// CHECK-NEXT:      character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK-NEXT:      integer(c_int), intent(out) :: errflg

// Initialize: same character/integer pattern.
// CHECK-LABEL:   subroutine Kessler_ccpp_physics_initialize(suite_name, errmsg, errflg) BIND(C,
// CHECK:           character(kind=c_char, len=1), intent(in) :: suite_name(*)

// Finalize.
// CHECK-LABEL:   subroutine Kessler_ccpp_physics_finalize(suite_name, errmsg, errflg) BIND(C,
// CHECK:           character(kind=c_char, len=1), intent(in) :: suite_name(*)

// Timestep initial/final.
// CHECK-LABEL:   subroutine Kessler_ccpp_physics_timestep_initial(suite_name, errmsg, errflg) BIND(C,
// CHECK-LABEL:   subroutine Kessler_ccpp_physics_timestep_final(suite_name, errmsg, errflg) BIND(C,

// Run: scalar intent(in) values use VALUE; strings use c_char; real arrays use c_double.
// CHECK-LABEL:   subroutine Kessler_ccpp_physics_run(
// CHECK:           character(kind=c_char, len=1), intent(in) :: suite_name(*)
// CHECK:           character(kind=c_char, len=1), intent(in) :: suite_part(*)
// CHECK:           integer(c_int), value, intent(in) :: col_start
// CHECK:           integer(c_int), value, intent(in) :: col_end
// CHECK:           integer(c_int), value, intent(in) :: nz
// CHECK:           real(c_double), value, intent(in) :: dt
// CHECK:           real(c_double), intent(in) :: cpair(*)
// CHECK:           real(c_double), intent(inout) :: theta(*)
// CHECK:           real(c_double), intent(inout) :: precl(*)
// CHECK:           character(kind=c_char, len=1), intent(inout) :: errmsg(*)
// CHECK:           integer(c_int), intent(inout) :: errflg

// Utility subroutines must NOT carry BIND(C) — they use allocatable types.
// CHECK-LABEL:   subroutine ccpp_physics_suite_list(suites)
// CHECK:           character(len=*), allocatable, intent(out) :: suites(:)
// CHECK-LABEL:   subroutine ccpp_physics_suite_part_list(suite_name, part_list, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
