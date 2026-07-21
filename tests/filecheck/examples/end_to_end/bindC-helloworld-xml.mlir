// Test --bind-c mode of generate-ccpp-cap for the helloworld example.
// Verifies that the ccpp_cap module subroutines carry BIND(C) signatures,
// use iso_c_binding at module scope, and declare arguments with C-compatible
// types (c_char arrays, c_int scalars).  Also verifies that utility subroutines
// (ccpp_physics_suite_list, ccpp_physics_suite_part_list) are NOT marked BIND(C).
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/helloworld/hello_world_suite.xml --scheme-files examples/helloworld/hello_scheme.meta,examples/helloworld/temp_adjust.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p "generate-meta-cap,generate-meta-kinds,generate-arg-ownership,generate-suite-cap,generate-ccpp-cap{bind_c=true},generate-cpp-cap,generate-kinds,strip-ccpp" -t ftn | python3 -m filecheck %s

// The ccpp_cap module uses iso_c_binding for all BIND(C) subroutines.
// CHECK-LABEL: module HelloWorld_ccpp_cap
// CHECK:         use ccpp_kinds
// CHECK:         use iso_c_binding
// CHECK:       CONTAINS

// Register: BIND(C) clause present, c_char and c_int argument types.
// CHECK-LABEL:   subroutine HelloWorld_ccpp_physics_register(suite_name, errmsg, errflg) BIND(C,
// CHECK:           character(kind=c_char, len=1), intent(in) :: suite_name(*)
// CHECK-NEXT:      character(kind=c_char, len=1), intent(out) :: errmsg(*)
// CHECK-NEXT:      integer(c_int), intent(out) :: errflg

// Initialize: same pattern.
// CHECK-LABEL:   subroutine HelloWorld_ccpp_physics_initialize(suite_name, errmsg, errflg) BIND(C,
// CHECK:           character(kind=c_char, len=1), intent(in) :: suite_name(*)

// Finalize: same pattern.
// CHECK-LABEL:   subroutine HelloWorld_ccpp_physics_finalize(suite_name, errmsg, errflg) BIND(C,
// CHECK:           character(kind=c_char, len=1), intent(in) :: suite_name(*)

// Timestep initial/final.
// CHECK-LABEL:   subroutine HelloWorld_ccpp_physics_timestep_initial(suite_name, errmsg, errflg) BIND(C,
// CHECK-LABEL:   subroutine HelloWorld_ccpp_physics_timestep_final(suite_name, errmsg, errflg) BIND(C,

// Run: integer intent(in) scalars (col_start, col_end) use VALUE; strings use c_char.
// CHECK-LABEL:   subroutine HelloWorld_ccpp_physics_run
// CHECK:           character(kind=c_char, len=1), intent(in) :: suite_name(*)
// CHECK:           character(kind=c_char, len=1), intent(in) :: suite_part(*)
// CHECK:           integer(c_int), value, intent(in) :: col_start
// CHECK:           integer(c_int), value, intent(in) :: col_end
// CHECK:           character(kind=c_char, len=1), intent(inout) :: errmsg(*)
// CHECK:           integer(c_int), intent(inout) :: errflg

// Utility subroutines must NOT carry BIND(C) — they use allocatable types
// that are not C-interoperable.
// CHECK-LABEL:   subroutine ccpp_physics_suite_list(suites)
// CHECK:           character(len=*), allocatable, intent(out) :: suites(:)
// CHECK-LABEL:   subroutine ccpp_physics_suite_part_list(suite_name, part_list, errmsg, errflg)
// CHECK:           character(len=*), intent(in) :: suite_name
