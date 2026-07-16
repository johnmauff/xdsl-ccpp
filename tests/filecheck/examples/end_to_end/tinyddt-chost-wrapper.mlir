// Test C++ ergonomics wrapper generation for the tinyddt chost cap.
// Verifies that DDT flattening produces sensible wrapper types:
//   - RunArgs struct has state_nz (int) and state_temp (double*) instead of a DDT
//   - State struct has state_nz and state_temp as members with defaults
//   - State constructor initialises the dimension scalars ncol and state_nz
//   - inline run() calls Tinyddt_chost_physics_run with the flattened args
//
// Canonical arg ordering: ncol (is_ncol) → state_nz (is_nz) → others → errmsg → errflg
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/tinyddt/tinyddt_suite.xml --scheme-files examples/tinyddt/tinyddt.meta --host-files examples/tinyddt/host_cpp/tinyddt_host_mod.meta,examples/tinyddt/host_cpp/tinyddt_host_sub.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p "generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap{bind_c=true},generate-kinds,strip-ccpp" -t cpp_header | python3 -m filecheck %s

// Wrapper file marker and includes.
// CHECK: // FILE: Tinyddt_chost.hpp
// CHECK: #include <string>
// CHECK: #include "Tinyddt_ccpp_chost_cap.h"

// Namespace and Status struct.
// CHECK: namespace Tinyddt_chost {
// CHECK: struct Status {
// CHECK:     int         code;
// CHECK:     std::string message;
// CHECK:     bool ok() const { return code == 0; }
// CHECK: };

// Run args struct: ncol, state_nz (is_nz), then col_start/col_end, then state_temp.
// No Fortran DDT type in sight — only C-compatible types.
// CHECK-LABEL: struct RunArgs {
// CHECK:     int              ncol;
// CHECK:     int              state_nz;
// CHECK:     int              col_start;
// CHECK:     int              col_end;
// CHECK:     double*          state_temp;

// Run inline function: errmsg/errflg allocated internally; flattened args forwarded.
// CHECK-LABEL: inline Status run(const RunArgs& a) {
// CHECK:     char   errmsg[512]      = {};
// CHECK:     int    errflg           = 0;
// CHECK:     Tinyddt_chost_physics_run(
// CHECK:         a.ncol, a.state_nz, a.col_start, a.col_end,
// CHECK:     return {errflg, errflg ? errmsg : ""};

// State struct: dimension scalars ncol and state_nz initialised; array pointer state_temp nullable.
// CHECK-LABEL: struct State {
// CHECK:     int              ncol = 0;
// CHECK:     int              state_nz = 0;
// CHECK:     double*          state_temp = nullptr;
// Constructor initialises both dimension scalars.
// CHECK:     State(int ncol = 0, int state_nz = 0)
// CHECK:         : ncol(ncol), state_nz(state_nz) {}

// State overload for run — no loop bounds needed.
// CHECK-LABEL: inline Status run(const State& s, int col_start, int col_end) {
// CHECK:     return run({
// CHECK:         .ncol=s.ncol,
// CHECK:         .state_nz=s.state_nz,
