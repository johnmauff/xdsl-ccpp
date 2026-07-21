// Test C++ ergonomics wrapper generation for the tinyddt chost cap with two DDT args.
// Verifies that both DDTs are flattened into the wrapper types:
//   - RunArgs and State have members for both state and tend
//   - State constructor initialises all dimension scalars: ncol, state_nz, tend_nz
//   - allocate() wires both array pointers
//   - inline run() forwards all flattened args
//
// Canonical arg ordering: ncol (is_ncol) → state_nz, tend_nz (is_nz) → others → errmsg → errflg
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/tinyddt/tinyddt_suite.xml --scheme-files examples/tinyddt/tinyddt.meta --host-files examples/tinyddt/host_cpp/tinyddt_host_mod.meta,examples/tinyddt/host_cpp/tinyddt_host_sub.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p "generate-meta-cap,generate-meta-kinds,generate-arg-ownership,generate-suite-cap,generate-ccpp-cap{bind_c=true},generate-cpp-cap,generate-kinds,strip-ccpp" -t cpp_header | python3 -m filecheck %s

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

// RunArgs: ncol, state_nz, tend_nz (both is_nz), then col_start/col_end, then arrays.
// CHECK-LABEL: struct RunArgs {
// CHECK:     int              ncol;
// CHECK:     int              state_nz;
// CHECK:     int              tend_nz;
// CHECK:     int              col_start;
// CHECK:     int              col_end;
// CHECK:     double*          state_temp;
// CHECK:     double*          tend_dtemp;

// Run inline function: errmsg/errflg allocated internally; all flattened args forwarded.
// CHECK-LABEL: inline Status run(const RunArgs& a) {
// CHECK:     char   errmsg[513]      = {};
// CHECK:     int    errflg           = 0;
// CHECK:     Tinyddt_chost_physics_run(
// CHECK:         a.ncol, a.state_nz, a.tend_nz, a.col_start,
// CHECK:     return {errflg, errflg ? errmsg : ""};

// State struct: all dimension scalars and array pointers for both DDTs.
// CHECK-LABEL: struct State {
// CHECK:     int              ncol = 0;
// CHECK:     int              state_nz = 0;
// CHECK:     int              tend_nz = 0;
// CHECK:     double*          state_temp = nullptr;
// CHECK:     double*          tend_dtemp = nullptr;
// Constructor initialises all three dimension scalars.
// CHECK:     State(int ncol = 0, int state_nz = 0, int tend_nz = 0)
// CHECK:         : ncol(ncol), state_nz(state_nz), tend_nz(tend_nz) {}

// State overload for run — no loop bounds needed.
// CHECK-LABEL: inline Status run(const State& s, int col_start, int col_end) {
// CHECK:     return run({
// CHECK:         .ncol=s.ncol,
// CHECK:         .state_nz=s.state_nz,
// CHECK:         .tend_nz=s.tend_nz,
