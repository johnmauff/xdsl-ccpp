// Test chost cap Fortran output for intent=out DDT (Gap 3) and character
// DDT members (Gap 4).
//
// Uses the ddthost make_ddt scheme whose initialize entry point has:
//   - ccpp_info (ccpp_info_t, intent=in)  — a DDT with a character member errmsg
//   - vmr       (vmr_type,   intent=out)  — a DDT that the scheme allocates
//
// Gap 3: vmr is intent=out.  The MLIR encodes it as a function *output*, not an
// input, so it does not appear in pfn_hints/pfn_types.  The generated initialize
// chost subroutine must:
//   - Include vmr_nvmr (integer, intent=in) and vmr_vmr_array (real, intent=out).
//   - NOT allocate vmr_local%vmr_array before the suite call (scheme does it).
//   - Pass vmr_local to the suite call.
//   - Write vmr_vmr_array back from vmr_local%vmr_array after the suite call.
//   - Deallocate vmr_local%vmr_array.
//
// Gap 4: ccpp_info_t has a character(len=512) member errmsg.  The generated code
// must NOT expose ccpp_info_errmsg in the chost signature and must initialise
// ccpp_info_local%errmsg to blank internally.
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites tests/filecheck/fixtures/ddt_intent_in/suite.xml --scheme-files examples/ddthost/make_ddt.meta --host-files tests/filecheck/fixtures/ddt_intent_in/host_mod.meta,tests/filecheck/fixtures/ddt_intent_in/host_sub.meta,examples/ddthost/host_ccpp_ddt.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p "generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap{bind_c=true},generate-kinds,strip-ccpp" -t ftn | python3 -m filecheck %s

// ── Gap 3 + Gap 4: initialize subroutine ────────────────────────────────────

// CHECK-LABEL: subroutine DdtIn_chost_physics_initialize(

// Gap 4: ccpp_info_errmsg must NOT appear in the signature or body.
// (It must be absent from the whole module since ccpp_info is only used here.)
// CHECK-NOT: ccpp_info_errmsg

// Gap 3: vmr_nvmr and vmr_vmr_array must be present in the signature.
// CHECK:     integer(c_int), value, intent(in) :: vmr_nvmr
// CHECK:     real(c_double), target, intent(out) :: vmr_vmr_array(ncols, vmr_nvmr)

// Gap 4: character member must be blank-initialized inside the subroutine body.
// CHECK:     ccpp_info_local%errmsg = ' '

// Gap 3 copy-in: scalar must be set from C++ arg for allocation sizing.
// CHECK:     vmr_local%nvmr = vmr_nvmr

// Gap 3: allocate must NOT be emitted for vmr_local%vmr_array before the call.
// CHECK-NOT: allocate(vmr_local%vmr_array

// Suite call must include vmr_local (the intent=out DDT local variable).
// CHECK:     call ddt_in_suite_suite_initialize(
// CHECK:     ncols, ccpp_info_local, vmr_local, errmsg_f, errflg)

// Gap 3 writeback: vmr_vmr_array must be assigned from vmr_local%vmr_array.
// CHECK:     vmr_vmr_array = real(vmr_local%vmr_array, c_double)
// CHECK:     deallocate(vmr_local%vmr_array)
