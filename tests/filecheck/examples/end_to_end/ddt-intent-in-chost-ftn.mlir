// Test chost cap Fortran output for an intent=in DDT argument (Gap 2).
//
// Uses the ddthost make_ddt scheme whose timestep_final entry point has
// vmr (vmr_type, intent=in).  The generated timestep_final chost subroutine
// must:
//   - Declare vmr_vmr_array as intent(in)   (read-only pointer from C++)
//   - Allocate vmr_local%vmr_array and fill it from vmr_vmr_array (copy-in)
//   - Call the suite timestep_final subroutine
//   - Deallocate vmr_local%vmr_array
//   - NOT write vmr_vmr_array back from vmr_local%vmr_array (no writeback)
//
// Contrast with the run/physics subroutine where vmr has intent=inout:
//   - vmr_vmr_array declared intent(inout)
//   - writeback IS emitted before dealloc
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites tests/filecheck/fixtures/ddt_intent_in/suite.xml --scheme-files examples/ddthost/make_ddt.meta --host-files tests/filecheck/fixtures/ddt_intent_in/host_mod.meta,tests/filecheck/fixtures/ddt_intent_in/host_sub.meta,examples/ddthost/host_ccpp_ddt.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p "generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap{bind_c=true},generate-kinds,strip-ccpp" -t ftn | python3 -m filecheck %s

// ── timestep_final: vmr is intent=in → no writeback ──────────────────────────

// The chost subroutine for timestep_final is generated.
// CHECK-LABEL: subroutine DdtIn_chost_physics_timestep_final(

// vmr_nvmr (integer scalar) and vmr_vmr_array (real 2-D array) are declared.
// vmr_vmr_array must be intent(in) because the DDT arg is intent=in.
// CHECK:     integer(c_int), value, intent(in) :: vmr_nvmr
// CHECK:     real(c_double), target, intent(in) :: vmr_vmr_array(ncols, vmr_nvmr)

// Copy-in: scalar assignment and array allocation+fill must be present.
// CHECK:     vmr_local%nvmr = vmr_nvmr
// CHECK:     allocate(vmr_local%vmr_array(ncols, vmr_nvmr))
// CHECK:     vmr_local%vmr_array = real(vmr_vmr_array, kind_phys)

// Suite call must be present.
// CHECK:     call ddt_in_suite_suite_timestep_final(

// Deallocation must happen (even for intent=in).
// CHECK:     deallocate(vmr_local%vmr_array)

// Writeback must NOT be present in this subroutine.
// The real(vmr_local%vmr_array, c_double) assignment that would copy data back
// to vmr_vmr_array is absent for intent=in.
// CHECK-NOT: vmr_vmr_array = real(vmr_local%vmr_array

// ── run/physics: vmr is intent=inout → writeback present ─────────────────────

// The run subroutine declares vmr_vmr_array as intent(inout).
// CHECK-LABEL: subroutine DdtIn_chost_physics_run(
// CHECK:     real(c_double), target, intent(inout) :: vmr_vmr_array(ncols, vmr_nvmr)

// Writeback IS present in the run subroutine.
// CHECK:     vmr_vmr_array = real(vmr_local%vmr_array, c_double)
// CHECK:     deallocate(vmr_local%vmr_array)
