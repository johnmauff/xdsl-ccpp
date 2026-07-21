// Test C++ ergonomics wrapper generation for the kessler chost cap.
// Verifies Option A (named arg structs) + Option 2 (Status return) design:
//   - Wrapper file emitted as a separate // FILE: section after the .h header.
//   - Status struct with code/message/ok().
//   - Per-lifecycle arg structs excluding errmsg/errflg/scheme_name.
//   - inline free functions allocating errmsg/errflg/scheme_name internally.
//   - Namespace Kessler_chost wraps all declarations.
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/kessler/scheme/kessler_suite.xml --scheme-files examples/kessler/scheme/kessler.meta,examples/kessler/scheme/kessler_update.meta --host-files examples/kessler/host_cpp/kessler_host_mod.meta,examples/kessler/host_cpp/kessler_host_sub.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p "generate-meta-cap,generate-meta-kinds,generate-arg-ownership,generate-suite-cap,generate-ccpp-cap{bind_c=true},generate-cpp-cap,generate-kinds,strip-ccpp" -t cpp_header | python3 -m filecheck %s

// Wrapper file marker and includes.
// CHECK: // FILE: Kessler_chost.hpp
// CHECK: #include <string>
// CHECK: #include "Kessler_ccpp_chost_cap.h"

// Namespace and Status struct.
// CHECK: namespace Kessler_chost {
// CHECK: struct Status {
// CHECK:     int         code;
// CHECK:     std::string message;
// CHECK:     bool ok() const { return code == 0; }
// CHECK: };

// Initialize args struct has scalar real fields; errmsg/errflg not present.
// CHECK-LABEL: struct InitializeArgs {
// CHECK:     double           lv;
// CHECK:     double           gravit;

// Initialize inline function: errmsg/errflg allocated internally.
// CHECK-LABEL: inline Status initialize(const InitializeArgs& a) {
// CHECK:     char   errmsg[513]      = {};
// CHECK:     int    errflg           = 0;
// CHECK:     Kessler_chost_physics_initialize(
// CHECK:     return {errflg, errflg ? errmsg : ""};

// Finalize has no physics args — no struct, bare function signature.
// CHECK-LABEL: inline Status finalize() {
// CHECK:     Kessler_chost_physics_finalize(errmsg, &errflg);
// CHECK:     return {errflg, errflg ? errmsg : ""};

// Run args struct: ncol, nz, col_start, col_end, scalars, then arrays.
// scheme_name is NOT a struct member (handled internally).
// CHECK-LABEL: struct RunArgs {
// CHECK:     int              ncol;
// CHECK:     int              nz;
// CHECK:     int              col_start;
// CHECK:     int              col_end;
// CHECK:     double           dt;
// CHECK:     const double*    cpair;
// CHECK:     double*          theta;
// CHECK:     double*          precl;

// Run inline function: scheme_name allocated internally, errmsg/errflg too.
// CHECK-LABEL: inline Status run(const RunArgs& a) {
// CHECK:     char   scheme_name[65]  = {};
// CHECK:     char   errmsg[513]      = {};
// CHECK:     int    errflg           = 0;
// CHECK:     Kessler_chost_physics_run(
// CHECK:         a.ncol, a.nz, a.col_start, a.col_end,
// CHECK:     return {errflg, errflg ? errmsg : ""};

// State struct aggregates all lifecycle fields; col_start/col_end excluded.
// Fields appear in order of first use across lifecycles (initialize → run).
// All pointer fields are non-const (host owns and initialises the memory).
// CHECK-LABEL: struct State {
// CHECK:     double           lv = 0;
// CHECK:     int              ncol = 0;
// CHECK:     double*          cpair = nullptr;
// CHECK:     double           dt = 0;
// CHECK:     double*          theta = nullptr;
// CHECK:     double*          precl = nullptr;
// Constructor initialises dimension scalars; remaining fields default to 0/nullptr.
// CHECK:     State(int ncol = 0, int nz = 0)
// CHECK:         : ncol(ncol), nz(nz) {}

// State overload for initialize — no loop bounds.
// CHECK-LABEL: inline Status initialize(const State& s) {
// CHECK:     return initialize({
// CHECK:         .lv=s.lv,

// State overload for run — col_start and col_end passed per-call.
// CHECK-LABEL: inline Status run(const State& s, int col_start, int col_end) {
// CHECK:     return run({
// CHECK:         .col_start=col_start,
// CHECK:         .col_end=col_end,
// CHECK:         .dt=s.dt,
// CHECK:         .theta=s.theta,

// Namespace close.
// CHECK: } // namespace Kessler_chost
