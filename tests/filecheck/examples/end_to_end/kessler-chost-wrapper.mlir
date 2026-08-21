// Test C++ ergonomics wrapper generation for the kessler chost cap.
// Verifies Option A (named arg structs) + Option 2 (Status return) design:
//   - Wrapper file emitted as a separate // FILE: section after the .h header.
//   - Status struct with code/message/ok().
//   - Per-lifecycle arg structs excluding errmsg/errflg/scheme_name.
//   - inline free functions allocating errmsg/errflg/scheme_name internally.
//   - Namespace Kessler_chost wraps all declarations.
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/kessler/scheme/kessler_suite.xml --scheme-files examples/kessler/scheme/kessler.meta,examples/kessler/scheme/kessler_update.meta --host-files examples/kessler/host_cpp/kessler_host_mod.meta,examples/kessler/host_cpp/kessler_host_sub.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p "generate-meta-cap,generate-meta-kinds,generate-host-match,generate-arg-ownership,generate-suite-cap,generate-ccpp-cap{bind_c=true},generate-cpp-cap,generate-kinds,strip-ccpp" -t cpp_header | python3 -m filecheck %s

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

// Initialize (task #28 Stage 3): scheme calls moved to the new
// physics_initial entry point below -- initialize itself has no physics
// args left, so (like finalize) it's a bare function, no struct.
// CHECK-LABEL: inline Status initialize() {
// CHECK:     char   errmsg[513]      = {};
// CHECK:     int    errflg           = 0;
// CHECK:     Kessler_chost_physics_initialize(errmsg, &errflg);
// CHECK:     return {errflg, errflg ? errmsg : ""};

// Finalize has no physics args — no struct, bare function signature.
// CHECK-LABEL: inline Status finalize() {
// CHECK:     Kessler_chost_physics_finalize(errmsg, &errflg);
// CHECK:     return {errflg, errflg ? errmsg : ""};

// Run args struct: ncol, nz, then scalars, then arrays. col_start/col_end
// are no longer struct members -- they were unused placeholders in the
// chost API and are dropped now that the horizontal_dimension convention
// resolves the call window internally.  scheme_name is NOT a struct member
// (handled internally) either.
// CHECK-LABEL: struct RunArgs {
// CHECK:     int              ncol;
// CHECK:     int              nz;
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
// CHECK:         a.ncol, a.nz, a.dt, a.lyr_surf,
// CHECK:     return {errflg, errflg ? errmsg : ""};

// Physics initial (task #28 Stage 3): net-new entry point, generated last
// (after run/timestep_initial/timestep_final) -- owns the scalar physics
// constants (and the scheme call using them) initialize used to have.
// CHECK-LABEL: struct PhysicsInitialArgs {
// CHECK:     double           lv;
// CHECK:     double           gravit;

// Physics initial inline function: errmsg/errflg allocated internally.
// CHECK-LABEL: inline Status physics_initial(const PhysicsInitialArgs& a) {
// CHECK:     char   errmsg[513]      = {};
// CHECK:     int    errflg           = 0;
// CHECK:     Kessler_chost_physics_physics_initial(
// CHECK:     return {errflg, errflg ? errmsg : ""};

// Physics final (task #28 Stage 3): net-new entry point; kessler_update has
// no _finalize table, so this reduces to a bare function like finalize.
// CHECK-LABEL: inline Status physics_final() {
// CHECK:     Kessler_chost_physics_physics_final(errmsg, &errflg);
// CHECK:     return {errflg, errflg ? errmsg : ""};

// State struct aggregates all lifecycle fields; col_start/col_end excluded.
// Fields appear in order of first use across lifecycles, scanned in fixed
// canonical phase order (register, initialize, finalize, run,
// timestep_initial, timestep_final, physics_initial, physics_final) --
// task #28 Stage 3 added physics_initial/physics_final at the END of that
// order (net-new entry points, not moved existing ones), so lv/gravit
// (used only by physics_initial) now appear LAST, after every field run/
// timestep_final already introduced -- not first, like the old flat
// initialize used to put them.
// All pointer fields are non-const (host owns and initialises the memory).
// CHECK-LABEL: struct State {
// CHECK:     int              ncol = 0;
// CHECK:     double           dt = 0;
// CHECK:     double*          cpair = nullptr;
// CHECK:     double*          theta = nullptr;
// CHECK:     double*          precl = nullptr;
// CHECK:     double           lv = 0;
// CHECK:     double           gravit = 0;
// Constructor initialises dimension scalars; remaining fields default to 0/nullptr.
// CHECK:     State(int ncol = 0, int nz = 0)
// CHECK:         : ncol(ncol), nz(nz) {}

// State overload for run — no loop bounds; ncol/nz already live on State.
// CHECK-LABEL: inline Status run(const State& s) {
// CHECK:     return run({
// CHECK:         .ncol=s.ncol,
// CHECK:         .nz=s.nz,
// CHECK:         .dt=s.dt,
// CHECK:         .theta=s.theta,

// State overload for physics_initial — generated last (task #28 Stage 3:
// after run/timestep_initial/timestep_final's own State overloads).
// CHECK-LABEL: inline Status physics_initial(const State& s) {
// CHECK:     return physics_initial({
// CHECK:         .lv=s.lv,

// Namespace close.
// CHECK: } // namespace Kessler_chost
