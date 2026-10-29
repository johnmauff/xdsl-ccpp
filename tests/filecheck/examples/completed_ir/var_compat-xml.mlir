// Test the completed IR for the var_compat XML frontend -- ported from NCAR
// ccpp-framework's feature/capgen-v1 branch, end-to-end-tests/var_compat.
// Exercises: nested-subcycle codegen at the completed-IR level -- the
// var_compatibility_suite_radiation function below contains a
// 3-level-deep nested do-loop structure (an outer dynamic-count scf.for-style
// SubcycleLoopOp around effr_pre/effr_post, with two nested loop=2
// SubcycleLoopOps around effr_calc), plus a second sibling dynamic-count
// SubcycleLoopOp (effrs_calc) -- this is the primary completed-IR-level
// regression coverage for the nested-subcycle-support work. Four distinct
// loop-count allocas (ccpp_loop_cnt/ccpp_loop_cnt0/ccpp_loop_cnt1/
// ccpp_loop_cnt2), each declared exactly once. See examples/var_compat/README.md
// for what this example does and does not cover. The suite's four schemes
// all use the bare local name 'scalar_var' for four unrelated
// standard_names -- a dummy-argument-name collision the host's own metadata
// resolves by giving each standard_name a distinct name (scalar_var/
// scalar_varA/scalar_varB/scalar_varC); this requires the generate-host-match
// pass to run (as the production ccpp_xdsl tool always does whenever host
// files are given) so suite_cap.py has a model_var_name to disambiguate with.
//
// Two standard_names here are declared with genuinely different units,
// kind, or vertical-layer convention (top_at_one) by different schemes (not
// just different from the host): the rain-particle and snow-particle radius
// variables. Each scheme call marshals to its own known mismatch
// independently at the call site -- a VerticalFlipOp/VerticalFlipWriteBackOp
// pair alongside the existing KindCastOp/UnitConvertOp machinery -- rather
// than one conversion applied uniformly to every caller sharing the
// standard_name.
//
// module_rad_ddt.meta is included here -- it wasn't in the original port,
// which silently produced a suite-cap module missing the "use module_rad_ddt,
// only: ty_rad_lw" import its own fluxLW argument needs (and, separately,
// caused rad_sw's DDT-member arguments, sfc_up_sw/sfc_down_sw, to never be
// matched or declared at all) -- found by actually trying to compile this
// example with gfortran for the first time.
//
// scalar_var/tke_inout/tke2_inout are ordinary scheme-declared intent=inout
// scalars with no dedicated framework meaning of their own (unlike
// ccpp_error_message/ccpp_error_code or a ccpp_t handle) -- run_dispatch.py's
// combined ccpp_physics_run wrapper used to have no
// copy-back at all for this case, so it always declared them intent(in)
// even though the suite callee it calls (var_compatibility_suite_
// radiation) correctly declares them intent(inout) -- invalid Fortran.
// Fixed by a new _get_suite_leading_inout_ret_info helper (cap_shared.py)
// that name-resolves this leading-region case the same way the trailing
// alloc-region case was already resolved, plus a matching fix in
// print_ftn.py's keyword-call printer, which had a separate but related
// bug: printing the same variable twice under two different keyword names
// bound to what is really the same dummy argument once the copy-back
// above made that variable eligible for the (pre-existing) inout-echo
// suppression the positional-call printer already had.
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/var_compat/var_compatibility_suite.xml --scheme-files examples/var_compat/effr_pre.meta,examples/var_compat/effr_calc.meta,examples/var_compat/effr_post.meta,examples/var_compat/effrs_calc.meta,examples/var_compat/effr_diag.meta,examples/var_compat/rad_lw.meta,examples/var_compat/rad_sw.meta,examples/var_compat/module_rad_ddt.meta --host-files examples/var_compat/test_host_data.meta,examples/var_compat/test_host_mod.meta,examples/var_compat/test_host.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p generate-meta-cap,generate-meta-kinds,generate-host-match,generate-arg-ownership,generate-suite-cap,generate-ccpp-cap,generate-cpp-cap,generate-kinds,strip-ccpp | python3 -m filecheck %s

// CHECK:       builtin.module {
// CHECK-LABEL:   builtin.module @var_compatibility_suite_cap attributes {ccpp_suite_cap = "var_compatibility_suite"} {
// CHECK:           "llvm.mlir.global"() <{global_type = !llvm.array<16 x i8>, sym_name = "ccpp_suite_state", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, value = "uninitialized"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<16 x i8>, sym_name = "const_in_time_step", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "in_time_step"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<16 x i8>, sym_name = "const_initialized", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "initialized"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<16 x i8>, sym_name = "const_uninitialized", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "uninitialized"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<0 x i8>, sym_name = "ty_rad_lw", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "mod_rad_ddt"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "ncols", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "pver", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "has_graupel", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "has_ice", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "ncl_out", base_type = "real", rank = 2 : i64, kind = "kind_phys"}> : () -> ()
// CHECK-LABEL:     func.func public @var_compatibility_suite_register() -> (memref<i32>, memref<512xi8>) attributes {ccpp_phase = "suite_register"} {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @var_compatibility_suite_initialize() -> (memref<i32>, memref<512xi8>) attributes {ccpp_phase = "suite_initialize"} {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %ncols = "ccpp_utils.host_var_ref"() <{var_name = "ncols", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:        %pver = "ccpp_utils.host_var_ref"() <{var_name = "pver", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ncols, %pver) <{var_name = "ncl_out", kind_name = "kind_phys"}> : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_uninitialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        %4 = "llvm.load"(%3) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %5 = "ccpp_utils.strcmp"(%2, %4) <{length = 13 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %6 = arith.constant true
// CHECK-NEXT:        %7 = arith.xori %5, %6 : i1
// CHECK-NEXT:        scf.if %7 {
// CHECK-NEXT:          %8 = "ccpp_utils.trim"(%4) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in var_compatibility_suite_initialize"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %11 = "llvm.load"(%10) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %12 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%11, %12) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @var_compatibility_suite_finalize() -> (memref<i32>, memref<512xi8>) attributes {ccpp_phase = "suite_finalize"} {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        %4 = "llvm.load"(%3) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %5 = "ccpp_utils.strcmp"(%2, %4) <{length = 11 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %6 = arith.constant true
// CHECK-NEXT:        %7 = arith.xori %5, %6 : i1
// CHECK-NEXT:        scf.if %7 {
// CHECK-NEXT:          %8 = "ccpp_utils.trim"(%4) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in var_compatibility_suite_finalize"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = "llvm.mlir.addressof"() <{global_name = @const_uninitialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %11 = "llvm.load"(%10) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %12 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%11, %12) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @var_compatibility_suite_init_radiation(%scheme_order : memref<i32> {ccpp.name = "scheme_order", ccpp.standard_name = "scheme_order_in_suite", ccpp.intent = "inout"}) -> (memref<i32>, memref<512xi8>, memref<i32>) attributes {ccpp_phase = "group_init"} {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %ncols = "ccpp_utils.host_var_ref"() <{var_name = "ncols", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:        %pver = "ccpp_utils.host_var_ref"() <{var_name = "pver", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ncols, %pver) <{var_name = "ncl_out", kind_name = "kind_phys"}> : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        %4 = "llvm.load"(%3) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %5 = "ccpp_utils.strcmp"(%2, %4) <{length = 11 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %6 = arith.constant true
// CHECK-NEXT:        %7 = arith.xori %5, %6 : i1
// CHECK-NEXT:        scf.if %7 {
// CHECK-NEXT:          %8 = "ccpp_utils.trim"(%4) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in var_compatibility_suite_init_radiation"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = arith.constant 0 : i32
// CHECK-NEXT:        %11 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %12 = arith.cmpi eq, %11, %10 : i32
// CHECK-NEXT:        scf.if %12 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%scheme_order, %errmsg, %errflg) <{callee = "effr_pre_init", operand_names = ["scheme_order", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %13 = arith.constant 0 : i32
// CHECK-NEXT:        %14 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %15 = arith.cmpi eq, %14, %13 : i32
// CHECK-NEXT:        scf.if %15 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%scheme_order, %errmsg, %errflg) <{callee = "effr_calc_init", operand_names = ["scheme_order", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %16 = arith.constant 0 : i32
// CHECK-NEXT:        %17 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %18 = arith.cmpi eq, %17, %16 : i32
// CHECK-NEXT:        scf.if %18 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%scheme_order, %errmsg, %errflg) <{callee = "effr_post_init", operand_names = ["scheme_order", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %19 = arith.constant 0 : i32
// CHECK-NEXT:        %20 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %21 = arith.cmpi eq, %20, %19 : i32
// CHECK-NEXT:        scf.if %21 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%scheme_order, %errmsg, %errflg) <{callee = "effr_diag_init", operand_names = ["scheme_order", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %scheme_order, %errmsg, %errflg : memref<i32>, memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @var_compatibility_suite_radiation(%effrr_inout : memref<?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "effrr_inout", ccpp.standard_name = "effective_radius_of_stratiform_cloud_rain_particle", ccpp.intent = "inout", ccpp.dim_names = ["horizontal_dimension", "vertical_layer_dimension"]}, %scalar_varA : memref<!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "scalar_varA", ccpp.standard_name = "scalar_variable_for_testing_a", ccpp.intent = "in"}, %ncol : memref<i32> {ccpp.name = "ncol", ccpp.standard_name = "horizontal_dimension", ccpp.intent = "in"}, %nlev : memref<i32> {ccpp.name = "nlev", ccpp.standard_name = "vertical_layer_dimension", ccpp.intent = "in"}, %effrg_in : memref<?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "effrg_in", ccpp.standard_name = "effective_radius_of_stratiform_cloud_graupel", ccpp.intent = "in", ccpp.dim_names = ["horizontal_dimension", "vertical_layer_dimension"], ccpp.optional}, %ncg_in : memref<?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "ncg_in", ccpp.standard_name = "cloud_graupel_number_concentration", ccpp.intent = "in", ccpp.dim_names = ["horizontal_dimension", "vertical_layer_dimension"], ccpp.optional}, %nci_out : memref<?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "nci_out", ccpp.standard_name = "cloud_ice_number_concentration", ccpp.intent = "out", ccpp.dim_names = ["horizontal_dimension", "vertical_layer_dimension"], ccpp.optional}, %effrl_inout : memref<?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "effrl_inout", ccpp.standard_name = "effective_radius_of_stratiform_cloud_liquid_water_particle", ccpp.intent = "inout", ccpp.dim_names = ["horizontal_dimension", "vertical_layer_dimension"]}, %effri_out : memref<?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "effri_out", ccpp.standard_name = "effective_radius_of_stratiform_cloud_ice_particle", ccpp.intent = "out", ccpp.dim_names = ["horizontal_dimension", "vertical_layer_dimension"], ccpp.optional}, %effrs_inout : memref<?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "effrs_inout", ccpp.standard_name = "effective_radius_of_stratiform_cloud_snow_particle", ccpp.intent = "inout", ccpp.dim_names = ["horizontal_dimension", "vertical_layer_dimension"]}, %ncl_out : memref<?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "ncl_out", ccpp.standard_name = "cloud_liquid_number_concentration", ccpp.intent = "out", ccpp.dim_names = ["horizontal_dimension", "vertical_layer_dimension"], ccpp.optional}, %has_graupel : memref<i1> {ccpp.name = "has_graupel", ccpp.standard_name = "flag_indicating_cloud_microphysics_has_graupel", ccpp.intent = "in"}, %scalar_var : memref<!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "scalar_var", ccpp.standard_name = "scalar_variable_for_testing", ccpp.intent = "inout"}, %tke_inout : memref<!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "tke_inout", ccpp.standard_name = "turbulent_kinetic_energy", ccpp.intent = "inout"}, %tke2_inout : memref<!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "tke2_inout", ccpp.standard_name = "turbulent_kinetic_energy2", ccpp.intent = "inout"}, %scalar_varB : memref<!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "scalar_varB", ccpp.standard_name = "scalar_variable_for_testing_b", ccpp.intent = "in"}, %scalar_varC : memref<i32> {ccpp.name = "scalar_varC", ccpp.standard_name = "scalar_variable_for_testing_c", ccpp.intent = "in"}, %fluxLW : memref<?x!ccpp_utils.derived_type<"ty_rad_lw">> {ccpp.name = "fluxLW", ccpp.standard_name = "longwave_radiation_fluxes", ccpp.intent = "inout", ccpp.dim_names = ["horizontal_dimension"]}, %sfc_up_sw : memref<?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "sfc_up_sw", ccpp.standard_name = "surface_upwelling_shortwave_radiation_flux", ccpp.intent = "inout", ccpp.dim_names = ["horizontal_dimension"]}, %sfc_down_sw : memref<?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "sfc_down_sw", ccpp.standard_name = "surface_downwelling_shortwave_radiation_flux", ccpp.intent = "inout", ccpp.dim_names = ["horizontal_dimension"]}, %num_subcycles : memref<i32> {ccpp.name = "num_subcycles", ccpp.standard_name = "num_subcycles_for_effr", ccpp.intent = "in"}) -> (memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) attributes {ccpp_phase = "run"} {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %effrg_in_unit_conv = "ccpp_utils.unit_convert"(%effrg_in) <{to_scheme_expr = "* 1.0E6"}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %effrl_inout_unit_conv = "ccpp_utils.unit_convert"(%effrl_inout) <{to_scheme_expr = "* 1.0E6"}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %effri_out_unit_conv = "ccpp_utils.unit_convert"(%effri_out) <{to_scheme_expr = ""}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %scalar_var_unit_conv = "ccpp_utils.unit_convert"(%scalar_var) <{to_scheme_expr = "* 0.001"}> : (memref<!ccpp_utils.real_kind<"kind_phys">>) -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %tke_inout_unit_conv = "ccpp_utils.unit_convert"(%tke_inout) <{to_scheme_expr = "* 1.0"}> : (memref<!ccpp_utils.real_kind<"kind_phys">>) -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_in_time_step}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        %4 = "llvm.load"(%3) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %5 = "ccpp_utils.strcmp"(%2, %4) <{length = 12 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %6 = arith.constant true
// CHECK-NEXT:        %7 = arith.xori %5, %6 : i1
// CHECK-NEXT:        scf.if %7 {
// CHECK-NEXT:          %8 = "ccpp_utils.trim"(%4) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in var_compatibility_suite_radiation"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %ccpp_loop_cnt = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %ccpp_loop_cnt_1 = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %ccpp_loop_cnt_2 = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %ccpp_loop_cnt_3 = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        "ccpp_utils.subcycle_loop"(%ccpp_loop_cnt_2) <{is_literal = false}> ({
// CHECK-NEXT:          "ccpp_utils.var_ref_expr"() <{var_name = "num_subcycles"}> : () -> ()
// CHECK-NEXT:        }, {
// CHECK-NEXT:          %10 = arith.constant 0 : i32
// CHECK-NEXT:          %11 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:          %12 = arith.cmpi eq, %11, %10 : i32
// CHECK-NEXT:          scf.if %12 {
// CHECK-NEXT:            "ccpp_utils.kw_call"(%effrr_inout, %scalar_varA, %errmsg, %errflg) <{callee = "effr_pre_run", operand_names = ["effrr_inout", "scalar_var", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:          }
// CHECK-NEXT:          "ccpp_utils.subcycle_loop"(%ccpp_loop_cnt_1) <{is_literal = true}> ({
// CHECK-NEXT:            %13 = arith.constant 2 : i32
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.subcycle_loop"(%ccpp_loop_cnt) <{is_literal = true}> ({
// CHECK-NEXT:              %14 = arith.constant 2 : i32
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.active_check"() <{condition_expr = "(has_graupel)"}> ({
// CHECK-NEXT:                "ccpp_utils.active_check"() <{condition_expr = "(has_ice)"}> ({
// CHECK-NEXT:                  %15 = arith.constant 0 : i32
// CHECK-NEXT:                  %16 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:                  %17 = arith.cmpi eq, %16, %15 : i32
// CHECK-NEXT:                  scf.if %17 {
// CHECK-NEXT:                    %effrr_in_unit_conv = "ccpp_utils.unit_convert"(%effrr_inout) <{to_scheme_expr = "* 1.0E6"}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:                    %effrr_in_vert_flip = "ccpp_utils.vertical_flip"(%effrr_in_unit_conv) <{vertical_dim = 2 : i64}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:                    %effrs_inout_kind_cast = "ccpp_utils.kind_cast"(%effrs_inout) <{target_kind = "8"}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<?x?xf64>
// CHECK-NEXT:                    %effrs_inout_unit_conv = "ccpp_utils.unit_convert"(%effrs_inout_kind_cast) <{to_scheme_expr = "* 1.0E6"}> : (memref<?x?xf64>) -> memref<?x?xf64>
// CHECK-NEXT:                    %effrs_inout_vert_flip = "ccpp_utils.vertical_flip"(%effrs_inout_unit_conv) <{vertical_dim = 2 : i64}> : (memref<?x?xf64>) -> memref<?x?xf64>
// CHECK-NEXT:                    "ccpp_utils.kw_call"(%ncol, %nlev, %effrr_in_vert_flip, %effrg_in_unit_conv, %ncg_in, %nci_out, %effrl_inout_unit_conv, %effri_out_unit_conv, %effrs_inout_vert_flip, %ncl_out, %has_graupel, %scalar_var_unit_conv, %tke_inout_unit_conv, %tke2_inout, %errmsg, %errflg) <{callee = "effr_calc_run", operand_names = ["ncol", "nlev", "effrr_in", "effrg_in", "ncg_in", "nci_out", "effrl_inout", "effri_out", "effrs_inout", "ncl_out", "has_graupel", "scalar_var", "tke_inout", "tke2_inout", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<i32>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?xf64>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i1>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:                    "ccpp_utils.vertical_flip_write_back"(%effrs_inout_vert_flip, %effrs_inout_unit_conv) <{vertical_dim = 2 : i64}> : (memref<?x?xf64>, memref<?x?xf64>) -> ()
// CHECK-NEXT:                    "ccpp_utils.unit_write_back"(%effrs_inout_unit_conv, %effrs_inout_kind_cast) <{to_host_expr = "* 1.0E-6"}> : (memref<?x?xf64>, memref<?x?xf64>) -> ()
// CHECK-NEXT:                    "ccpp_utils.kind_write_back"(%effrs_inout_kind_cast, %effrs_inout) <{original_kind = "kind_phys"}> : (memref<?x?xf64>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> ()
// CHECK-NEXT:                  }
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %18 = arith.constant 0 : i32
// CHECK-NEXT:                  %19 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:                  %20 = arith.cmpi eq, %19, %18 : i32
// CHECK-NEXT:                  scf.if %20 {
// CHECK-NEXT:                    %effrr_in_unit_conv_1 = "ccpp_utils.unit_convert"(%effrr_inout) <{to_scheme_expr = "* 1.0E6"}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:                    %effrr_in_vert_flip_1 = "ccpp_utils.vertical_flip"(%effrr_in_unit_conv_1) <{vertical_dim = 2 : i64}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:                    %effrs_inout_kind_cast_1 = "ccpp_utils.kind_cast"(%effrs_inout) <{target_kind = "8"}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<?x?xf64>
// CHECK-NEXT:                    %effrs_inout_unit_conv_1 = "ccpp_utils.unit_convert"(%effrs_inout_kind_cast_1) <{to_scheme_expr = "* 1.0E6"}> : (memref<?x?xf64>) -> memref<?x?xf64>
// CHECK-NEXT:                    %effrs_inout_vert_flip_1 = "ccpp_utils.vertical_flip"(%effrs_inout_unit_conv_1) <{vertical_dim = 2 : i64}> : (memref<?x?xf64>) -> memref<?x?xf64>
// CHECK-NEXT:                    "ccpp_utils.kw_call"(%ncol, %nlev, %effrr_in_vert_flip_1, %effrg_in_unit_conv, %ncg_in, %effrl_inout_unit_conv, %effrs_inout_vert_flip_1, %ncl_out, %has_graupel, %scalar_var_unit_conv, %tke_inout_unit_conv, %tke2_inout, %errmsg, %errflg) <{callee = "effr_calc_run", operand_names = ["ncol", "nlev", "effrr_in", "effrg_in", "ncg_in", "effrl_inout", "effrs_inout", "ncl_out", "has_graupel", "scalar_var", "tke_inout", "tke2_inout", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<i32>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?xf64>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i1>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:                    "ccpp_utils.vertical_flip_write_back"(%effrs_inout_vert_flip_1, %effrs_inout_unit_conv_1) <{vertical_dim = 2 : i64}> : (memref<?x?xf64>, memref<?x?xf64>) -> ()
// CHECK-NEXT:                    "ccpp_utils.unit_write_back"(%effrs_inout_unit_conv_1, %effrs_inout_kind_cast_1) <{to_host_expr = "* 1.0E-6"}> : (memref<?x?xf64>, memref<?x?xf64>) -> ()
// CHECK-NEXT:                    "ccpp_utils.kind_write_back"(%effrs_inout_kind_cast_1, %effrs_inout) <{original_kind = "kind_phys"}> : (memref<?x?xf64>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> ()
// CHECK-NEXT:                  }
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.active_check"() <{condition_expr = "(has_ice)"}> ({
// CHECK-NEXT:                  %21 = arith.constant 0 : i32
// CHECK-NEXT:                  %22 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:                  %23 = arith.cmpi eq, %22, %21 : i32
// CHECK-NEXT:                  scf.if %23 {
// CHECK-NEXT:                    %effrr_in_unit_conv_2 = "ccpp_utils.unit_convert"(%effrr_inout) <{to_scheme_expr = "* 1.0E6"}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:                    %effrr_in_vert_flip_2 = "ccpp_utils.vertical_flip"(%effrr_in_unit_conv_2) <{vertical_dim = 2 : i64}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:                    %effrs_inout_kind_cast_2 = "ccpp_utils.kind_cast"(%effrs_inout) <{target_kind = "8"}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<?x?xf64>
// CHECK-NEXT:                    %effrs_inout_unit_conv_2 = "ccpp_utils.unit_convert"(%effrs_inout_kind_cast_2) <{to_scheme_expr = "* 1.0E6"}> : (memref<?x?xf64>) -> memref<?x?xf64>
// CHECK-NEXT:                    %effrs_inout_vert_flip_2 = "ccpp_utils.vertical_flip"(%effrs_inout_unit_conv_2) <{vertical_dim = 2 : i64}> : (memref<?x?xf64>) -> memref<?x?xf64>
// CHECK-NEXT:                    "ccpp_utils.kw_call"(%ncol, %nlev, %effrr_in_vert_flip_2, %nci_out, %effrl_inout_unit_conv, %effri_out_unit_conv, %effrs_inout_vert_flip_2, %ncl_out, %has_graupel, %scalar_var_unit_conv, %tke_inout_unit_conv, %tke2_inout, %errmsg, %errflg) <{callee = "effr_calc_run", operand_names = ["ncol", "nlev", "effrr_in", "nci_out", "effrl_inout", "effri_out", "effrs_inout", "ncl_out", "has_graupel", "scalar_var", "tke_inout", "tke2_inout", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<i32>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?xf64>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i1>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:                    "ccpp_utils.vertical_flip_write_back"(%effrs_inout_vert_flip_2, %effrs_inout_unit_conv_2) <{vertical_dim = 2 : i64}> : (memref<?x?xf64>, memref<?x?xf64>) -> ()
// CHECK-NEXT:                    "ccpp_utils.unit_write_back"(%effrs_inout_unit_conv_2, %effrs_inout_kind_cast_2) <{to_host_expr = "* 1.0E-6"}> : (memref<?x?xf64>, memref<?x?xf64>) -> ()
// CHECK-NEXT:                    "ccpp_utils.kind_write_back"(%effrs_inout_kind_cast_2, %effrs_inout) <{original_kind = "kind_phys"}> : (memref<?x?xf64>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> ()
// CHECK-NEXT:                  }
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %24 = arith.constant 0 : i32
// CHECK-NEXT:                  %25 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:                  %26 = arith.cmpi eq, %25, %24 : i32
// CHECK-NEXT:                  scf.if %26 {
// CHECK-NEXT:                    %effrr_in_unit_conv_3 = "ccpp_utils.unit_convert"(%effrr_inout) <{to_scheme_expr = "* 1.0E6"}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:                    %effrr_in_vert_flip_3 = "ccpp_utils.vertical_flip"(%effrr_in_unit_conv_3) <{vertical_dim = 2 : i64}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:                    %effrs_inout_kind_cast_3 = "ccpp_utils.kind_cast"(%effrs_inout) <{target_kind = "8"}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<?x?xf64>
// CHECK-NEXT:                    %effrs_inout_unit_conv_3 = "ccpp_utils.unit_convert"(%effrs_inout_kind_cast_3) <{to_scheme_expr = "* 1.0E6"}> : (memref<?x?xf64>) -> memref<?x?xf64>
// CHECK-NEXT:                    %effrs_inout_vert_flip_3 = "ccpp_utils.vertical_flip"(%effrs_inout_unit_conv_3) <{vertical_dim = 2 : i64}> : (memref<?x?xf64>) -> memref<?x?xf64>
// CHECK-NEXT:                    "ccpp_utils.kw_call"(%ncol, %nlev, %effrr_in_vert_flip_3, %effrl_inout_unit_conv, %effrs_inout_vert_flip_3, %ncl_out, %has_graupel, %scalar_var_unit_conv, %tke_inout_unit_conv, %tke2_inout, %errmsg, %errflg) <{callee = "effr_calc_run", operand_names = ["ncol", "nlev", "effrr_in", "effrl_inout", "effrs_inout", "ncl_out", "has_graupel", "scalar_var", "tke_inout", "tke2_inout", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<i32>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?xf64>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i1>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:                    "ccpp_utils.vertical_flip_write_back"(%effrs_inout_vert_flip_3, %effrs_inout_unit_conv_3) <{vertical_dim = 2 : i64}> : (memref<?x?xf64>, memref<?x?xf64>) -> ()
// CHECK-NEXT:                    "ccpp_utils.unit_write_back"(%effrs_inout_unit_conv_3, %effrs_inout_kind_cast_3) <{to_host_expr = "* 1.0E-6"}> : (memref<?x?xf64>, memref<?x?xf64>) -> ()
// CHECK-NEXT:                    "ccpp_utils.kind_write_back"(%effrs_inout_kind_cast_3, %effrs_inout) <{original_kind = "kind_phys"}> : (memref<?x?xf64>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> ()
// CHECK-NEXT:                  }
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }) : (memref<i32>) -> ()
// CHECK-NEXT:          }) : (memref<i32>) -> ()
// CHECK-NEXT:          %27 = arith.constant 0 : i32
// CHECK-NEXT:          %28 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:          %29 = arith.cmpi eq, %28, %27 : i32
// CHECK-NEXT:          scf.if %29 {
// CHECK-NEXT:            "ccpp_utils.kw_call"(%effrr_inout, %scalar_varB, %errmsg, %errflg) <{callee = "effr_post_run", operand_names = ["effrr_inout", "scalar_var", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:          }
// CHECK-NEXT:        }) : (memref<i32>) -> ()
// CHECK-NEXT:        "ccpp_utils.subcycle_loop"(%ccpp_loop_cnt_3) <{is_literal = false}> ({
// CHECK-NEXT:          "ccpp_utils.var_ref_expr"() <{var_name = "num_subcycles"}> : () -> ()
// CHECK-NEXT:        }, {
// CHECK-NEXT:          %30 = arith.constant 0 : i32
// CHECK-NEXT:          %31 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:          %32 = arith.cmpi eq, %31, %30 : i32
// CHECK-NEXT:          scf.if %32 {
// CHECK-NEXT:            "ccpp_utils.kw_call"(%effrs_inout, %errmsg, %errflg) <{callee = "effrs_calc_run", operand_names = ["effrs_inout", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:          }
// CHECK-NEXT:        }) : (memref<i32>) -> ()
// CHECK-NEXT:        %33 = arith.constant 0 : i32
// CHECK-NEXT:        %34 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %35 = arith.cmpi eq, %34, %33 : i32
// CHECK-NEXT:        scf.if %35 {
// CHECK-NEXT:          %effrr_in_unit_conv_4 = "ccpp_utils.unit_convert"(%effrr_inout) <{to_scheme_expr = "* 1.0E6"}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %effrr_in_vert_flip_4 = "ccpp_utils.vertical_flip"(%effrr_in_unit_conv_4) <{vertical_dim = 2 : i64}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          "ccpp_utils.kw_call"(%effrr_in_vert_flip_4, %scalar_varC, %errmsg, %errflg) <{callee = "effr_diag_run", operand_names = ["effrr_in", "scalar_var", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %36 = arith.constant 0 : i32
// CHECK-NEXT:        %37 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %38 = arith.cmpi eq, %37, %36 : i32
// CHECK-NEXT:        scf.if %38 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%ncol, %fluxLW, %errmsg, %errflg) <{callee = "rad_lw_run", operand_names = ["ncol", "fluxLW", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<?x!ccpp_utils.derived_type<"ty_rad_lw">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %39 = arith.constant 0 : i32
// CHECK-NEXT:        %40 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %41 = arith.cmpi eq, %40, %39 : i32
// CHECK-NEXT:        scf.if %41 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%ncol, %sfc_up_sw, %sfc_down_sw, %errmsg, %errflg) <{callee = "rad_sw_run", operand_names = ["ncol", "sfc_up_sw", "sfc_down_sw", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        "ccpp_utils.unit_write_back"(%effrl_inout_unit_conv, %effrl_inout) <{to_host_expr = "* 1.0E-6"}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> ()
// CHECK-NEXT:        "ccpp_utils.unit_write_back"(%effri_out_unit_conv, %effri_out) <{to_host_expr = "* 1.0E-6"}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> ()
// CHECK-NEXT:        "ccpp_utils.unit_write_back"(%scalar_var_unit_conv, %scalar_var) <{to_host_expr = "* 1000.0"}> : (memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>) -> ()
// CHECK-NEXT:        "ccpp_utils.unit_write_back"(%tke_inout_unit_conv, %tke_inout) <{to_host_expr = "* 1.0"}> : (memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>) -> ()
// CHECK-NEXT:        func.return %scalar_var, %tke_inout, %tke2_inout, %errmsg, %errflg : memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @var_compatibility_suite_timestep_init_radiation() -> (memref<i32>, memref<512xi8>) attributes {ccpp_phase = "timestep_init"} {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_in_time_step}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%2, %3) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @var_compatibility_suite_timestep_final_radiation() -> (memref<i32>, memref<512xi8>) attributes {ccpp_phase = "timestep_final"} {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%2, %3) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @var_compatibility_suite_final_radiation() -> (memref<i32>, memref<512xi8>) attributes {ccpp_phase = "group_final"} {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        %4 = "llvm.load"(%3) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %5 = "ccpp_utils.strcmp"(%2, %4) <{length = 11 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %6 = arith.constant true
// CHECK-NEXT:        %7 = arith.xori %5, %6 : i1
// CHECK-NEXT:        scf.if %7 {
// CHECK-NEXT:          %8 = "ccpp_utils.trim"(%4) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in var_compatibility_suite_final_radiation"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func private @effr_pre_init(memref<i32>, memref<512xi8>, memref<i32>) -> () attributes {module = "mod_effr_pre"}
// CHECK-LABEL:     func.func private @effr_calc_init(memref<i32>, memref<512xi8>, memref<i32>) -> () attributes {module = "effr_calc"}
// CHECK-LABEL:     func.func private @effr_post_init(memref<i32>, memref<512xi8>, memref<i32>) -> () attributes {module = "effr_post"}
// CHECK-LABEL:     func.func private @effr_diag_init(memref<i32>, memref<512xi8>, memref<i32>) -> () attributes {module = "effr_diag"}
// CHECK-LABEL:     func.func private @effr_pre_run(memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "mod_effr_pre"}
// CHECK-LABEL:     func.func private @effr_calc_run(memref<i32>, memref<i32>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?xf64>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i1>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "effr_calc"}
// CHECK-LABEL:     func.func private @effr_post_run(memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "effr_post"}
// CHECK-LABEL:     func.func private @effrs_calc_run(memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "effrs_calc"}
// CHECK-LABEL:     func.func private @effr_diag_run(memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<512xi8>, memref<i32>) -> () attributes {module = "effr_diag"}
// CHECK-LABEL:     func.func private @rad_lw_run(memref<i32>, memref<?x!ccpp_utils.derived_type<"ty_rad_lw">>, memref<512xi8>, memref<i32>) -> () attributes {module = "rad_lw"}
// CHECK-LABEL:     func.func private @rad_sw_run(memref<i32>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "rad_sw"}
// CHECK:         }
// CHECK-LABEL:   builtin.module @VarCompatibility_ccpp_cap {
// CHECK:           "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "phys_state", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "ncols", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "pver", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "effrs", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "has_graupel", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<23 x i8>, sym_name = "str_var_compatibility_suite", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "var_compatibility_suite"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<9 x i8>, sym_name = "str_radiation", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "radiation"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "ccpp_constituent_properties_t", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "ccpp_constituent_prop_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "ccpp_constituent_prop_ptr_t", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "ccpp_constituent_prop_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "ccpp_model_constituents_t", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "ccpp_constituent_prop_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<0 x i8>, sym_name = "ty_rad_lw", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "mod_rad_ddt"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<0 x i8>, sym_name = "ty_rad_sw", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "mod_rad_ddt"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<0 x i8>, sym_name = "physics_state", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_data"} : () -> ()
// CHECK-LABEL:     func.func public @ccpp_register(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "var_compatibility_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3, %4 = func.call @var_compatibility_suite_register() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:          "memref.copy"(%3, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          "memref.copy"(%4, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %5 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %5, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_init(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "var_compatibility_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3, %4 = func.call @var_compatibility_suite_initialize() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:          "memref.copy"(%3, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          "memref.copy"(%4, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %5 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %5, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_final(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "var_compatibility_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3, %4 = func.call @var_compatibility_suite_finalize() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:          "memref.copy"(%3, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          "memref.copy"(%4, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %5 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %5, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_physics_run(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}, %suite_part : memref<?xi8> {ccpp.name = "suite_part"}, %col_start : memref<i32> {ccpp.name = "col_start"}, %col_end : memref<i32> {ccpp.name = "col_end"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg"}, %errflg : memref<i32> {ccpp.name = "errflg"}) -> (memref<512xi8>, memref<i32>) attributes {bind_c_dim_exprs = ["", "", "", "", "", ""]} {
// CHECK:             %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "var_compatibility_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:          %4 = "ccpp_utils.host_var_ref"() <{var_name = "phys_state", module_name = "test_host_mod"}> {member_name = "effrr"} : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %5 = "ccpp_utils.host_var_ref"() <{var_name = "phys_state", module_name = "test_host_mod"}> {member_name = "scalar_varA"} : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %ncol = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:          %6 = memref.load %col_start[] : memref<i32>
// CHECK-NEXT:          %7 = memref.load %col_end[] : memref<i32>
// CHECK-NEXT:          %8 = arith.subi %7, %6 : i32
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          %10 = arith.addi %8, %9 : i32
// CHECK-NEXT:          memref.store %10, %ncol[] : memref<i32>
// CHECK-NEXT:          %11 = "ccpp_utils.host_var_ref"() <{var_name = "pver", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:          %12 = "ccpp_utils.host_var_ref"() <{var_name = "phys_state", module_name = "test_host_mod"}> {member_name = "effrg"} : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %13 = "ccpp_utils.host_var_ref"() <{var_name = "phys_state", module_name = "test_host_mod"}> {member_name = "ncg"} : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %14 = "ccpp_utils.host_var_ref"() <{var_name = "phys_state", module_name = "test_host_mod"}> {member_name = "nci"} : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %15 = "ccpp_utils.host_var_ref"() <{var_name = "phys_state", module_name = "test_host_mod"}> {member_name = "effrl"} : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %16 = "ccpp_utils.host_var_ref"() <{var_name = "phys_state", module_name = "test_host_mod"}> {member_name = "effri"} : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %17 = "ccpp_utils.host_var_ref"() <{var_name = "effrs", module_name = "test_host_mod"}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %18 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_ncl_out"}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %19 = "ccpp_utils.host_var_ref"() <{var_name = "has_graupel", module_name = "test_host_mod"}> : () -> memref<i1>
// CHECK-NEXT:          %20 = "ccpp_utils.host_var_ref"() <{var_name = "phys_state", module_name = "test_host_mod"}> {member_name = "scalar_var"} : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %21 = "ccpp_utils.host_var_ref"() <{var_name = "phys_state", module_name = "test_host_mod"}> {member_name = "tke"} : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %22 = "ccpp_utils.host_var_ref"() <{var_name = "phys_state", module_name = "test_host_mod"}> {member_name = "tke2"} : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %23 = "ccpp_utils.host_var_ref"() <{var_name = "phys_state", module_name = "test_host_mod"}> {member_name = "scalar_varB"} : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %24 = "ccpp_utils.host_var_ref"() <{var_name = "phys_state", module_name = "test_host_mod"}> {member_name = "scalar_varC"} : () -> memref<i32>
// CHECK-NEXT:          %25 = "ccpp_utils.host_var_ref"() <{var_name = "phys_state", module_name = "test_host_mod"}> {member_name = "fluxLW"} : () -> memref<?x!ccpp_utils.derived_type<"ty_rad_lw">>
// CHECK-NEXT:          %26 = "ccpp_utils.host_var_ref"() <{var_name = "phys_state", module_name = "test_host_mod"}> {member_name = "fluxSW%sfc_up_sw"} : () -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %27 = "ccpp_utils.host_var_ref"() <{var_name = "phys_state", module_name = "test_host_mod"}> {member_name = "fluxSW%sfc_down_sw"} : () -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %28 = "ccpp_utils.host_var_ref"() <{var_name = "phys_state", module_name = "test_host_mod"}> {member_name = "num_subcycles"} : () -> memref<i32>
// CHECK-NEXT:          %29 = arith.constant 1 : i32
// CHECK-NEXT:          %30 = "ccpp_utils.rank_reducing_slice"(%4, %col_start, %29, %col_end, %11) <{dim_pattern = "RR"}> {operandSegmentSizes = array<i32: 1, 2, 2, 0>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, memref<i32>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %31 = "ccpp_utils.rank_reducing_slice"(%12, %col_start, %29, %col_end, %11) <{dim_pattern = "RR"}> {operandSegmentSizes = array<i32: 1, 2, 2, 0>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, memref<i32>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %32 = "ccpp_utils.rank_reducing_slice"(%13, %col_start, %29, %col_end, %11) <{dim_pattern = "RR"}> {operandSegmentSizes = array<i32: 1, 2, 2, 0>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, memref<i32>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %33 = "ccpp_utils.rank_reducing_slice"(%14, %col_start, %29, %col_end, %11) <{dim_pattern = "RR"}> {operandSegmentSizes = array<i32: 1, 2, 2, 0>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, memref<i32>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %34 = "ccpp_utils.rank_reducing_slice"(%15, %col_start, %29, %col_end, %11) <{dim_pattern = "RR"}> {operandSegmentSizes = array<i32: 1, 2, 2, 0>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, memref<i32>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %35 = "ccpp_utils.rank_reducing_slice"(%16, %col_start, %29, %col_end, %11) <{dim_pattern = "RR"}> {operandSegmentSizes = array<i32: 1, 2, 2, 0>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, memref<i32>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %36 = "ccpp_utils.rank_reducing_slice"(%17, %col_start, %29, %col_end, %11) <{dim_pattern = "RR"}> {operandSegmentSizes = array<i32: 1, 2, 2, 0>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, memref<i32>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %37 = "ccpp_utils.rank_reducing_slice"(%18, %col_start, %29, %col_end, %11) <{dim_pattern = "RR"}> {operandSegmentSizes = array<i32: 1, 2, 2, 0>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, memref<i32>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %38 = "ccpp_utils.rank_reducing_slice"(%25, %col_start, %col_end) <{dim_pattern = "R"}> {operandSegmentSizes = array<i32: 1, 1, 1, 0>} : (memref<?x!ccpp_utils.derived_type<"ty_rad_lw">>, memref<i32>, memref<i32>) -> memref<?x!ccpp_utils.derived_type<"ty_rad_lw">>
// CHECK-NEXT:          %39 = "ccpp_utils.rank_reducing_slice"(%26, %col_start, %col_end) <{dim_pattern = "R"}> {operandSegmentSizes = array<i32: 1, 1, 1, 0>} : (memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>) -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %40 = "ccpp_utils.rank_reducing_slice"(%27, %col_start, %col_end) <{dim_pattern = "R"}> {operandSegmentSizes = array<i32: 1, 1, 1, 0>} : (memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>) -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %41 = "ccpp_utils.strcmp"(%3) <{literal = "radiation"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %41 {
// CHECK-NEXT:            %42, %43, %44, %45, %46 = "ccpp_utils.kw_call"(%30, %5, %ncol, %11, %31, %32, %33, %34, %35, %36, %37, %19, %20, %21, %22, %23, %24, %38, %39, %40, %28) <{callee = "var_compatibility_suite_radiation", operand_names = ["effrr_inout", "scalar_varA", "ncol", "nlev", "effrg_in", "ncg_in", "nci_out", "effrl_inout", "effri_out", "effrs_inout", "ncl_out", "has_graupel", "scalar_var", "tke_inout", "tke2_inout", "scalar_varB", "scalar_varC", "fluxLW", "sfc_up_sw", "sfc_down_sw", "num_subcycles"], result_names = ["scalar_var", "tke_inout", "tke2_inout", "errmsg", "errflg"], overrides = {}}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i1>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<?x!ccpp_utils.derived_type<"ty_rad_lw">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>) -> (memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>)
// CHECK-NEXT:            "memref.copy"(%42, %20) : (memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>) -> ()
// CHECK-NEXT:            "memref.copy"(%43, %21) : (memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>) -> ()
// CHECK-NEXT:            "memref.copy"(%44, %22) : (memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>) -> ()
// CHECK-NEXT:            "memref.copy"(%45, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:            "memref.copy"(%46, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %3) <{prefix = "No suite part named ", suffix = " found in suite var_compatibility_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %47 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %47, %errflg[] : memref<i32>
// CHECK-NEXT:          }
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %48 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %48, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_physics_timestep_init(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}, %suite_part : memref<?xi8> {ccpp.name = "suite_part"}, %col_start : memref<i32> {ccpp.name = "col_start"}, %col_end : memref<i32> {ccpp.name = "col_end"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg"}, %errflg : memref<i32> {ccpp.name = "errflg"}) -> (memref<512xi8>, memref<i32>) attributes {bind_c_dim_exprs = ["", "", "", "", "", ""]} {
// CHECK:             %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "var_compatibility_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:          %4 = "ccpp_utils.strcmp"(%3) <{literal = "radiation"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %4 {
// CHECK-NEXT:            %5, %6 = func.call @var_compatibility_suite_timestep_init_radiation() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:            "memref.copy"(%5, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:            "memref.copy"(%6, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %3) <{prefix = "No suite part named ", suffix = " found in suite var_compatibility_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %7 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %7, %errflg[] : memref<i32>
// CHECK-NEXT:          }
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %8 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %8, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_physics_timestep_final(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}, %suite_part : memref<?xi8> {ccpp.name = "suite_part"}, %col_start : memref<i32> {ccpp.name = "col_start"}, %col_end : memref<i32> {ccpp.name = "col_end"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg"}, %errflg : memref<i32> {ccpp.name = "errflg"}) -> (memref<512xi8>, memref<i32>) attributes {bind_c_dim_exprs = ["", "", "", "", "", ""]} {
// CHECK:             %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "var_compatibility_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:          %4 = "ccpp_utils.strcmp"(%3) <{literal = "radiation"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %4 {
// CHECK-NEXT:            %5, %6 = func.call @var_compatibility_suite_timestep_final_radiation() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:            "memref.copy"(%5, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:            "memref.copy"(%6, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %3) <{prefix = "No suite part named ", suffix = " found in suite var_compatibility_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %7 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %7, %errflg[] : memref<i32>
// CHECK-NEXT:          }
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %8 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %8, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_physics_init(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}, %suite_part : memref<?xi8> {ccpp.name = "suite_part"}, %col_start : memref<i32> {ccpp.name = "col_start"}, %col_end : memref<i32> {ccpp.name = "col_end"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg"}, %errflg : memref<i32> {ccpp.name = "errflg"}) -> (memref<512xi8>, memref<i32>) attributes {bind_c_dim_exprs = ["", "", "", "", "", ""]} {
// CHECK:             %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "var_compatibility_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:          %4 = "ccpp_utils.host_var_ref"() <{var_name = "phys_state", module_name = "test_host_mod"}> {member_name = "scheme_order"} : () -> memref<i32>
// CHECK-NEXT:          %5 = "ccpp_utils.strcmp"(%3) <{literal = "radiation"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %5 {
// CHECK-NEXT:            %6, %7, %8 = func.call @var_compatibility_suite_init_radiation(%4) : (memref<i32>) -> (memref<i32>, memref<512xi8>, memref<i32>)
// CHECK-NEXT:            "memref.copy"(%6, %4) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:            "memref.copy"(%7, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:            "memref.copy"(%8, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %3) <{prefix = "No suite part named ", suffix = " found in suite var_compatibility_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %9 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:          }
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %10 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %10, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_physics_final(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}, %suite_part : memref<?xi8> {ccpp.name = "suite_part"}, %col_start : memref<i32> {ccpp.name = "col_start"}, %col_end : memref<i32> {ccpp.name = "col_end"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg"}, %errflg : memref<i32> {ccpp.name = "errflg"}) -> (memref<512xi8>, memref<i32>) attributes {bind_c_dim_exprs = ["", "", "", "", "", ""]} {
// CHECK:             %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "var_compatibility_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:          %4 = "ccpp_utils.strcmp"(%3) <{literal = "radiation"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %4 {
// CHECK-NEXT:            %5, %6 = func.call @var_compatibility_suite_final_radiation() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:            "memref.copy"(%5, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:            "memref.copy"(%6, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %3) <{prefix = "No suite part named ", suffix = " found in suite var_compatibility_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %7 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %7, %errflg[] : memref<i32>
// CHECK-NEXT:          }
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %8 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %8, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_physics_suite_list(%suites : memref<memref<?xi8>>) {
// CHECK:             %0 = arith.constant 23 : index
// CHECK-NEXT:        %1 = memref.alloc(%0) : memref<?xi8>
// CHECK-NEXT:        %2 = "llvm.mlir.addressof"() <{global_name = @str_var_compatibility_suite}> : () -> !llvm.ptr
// CHECK-NEXT:        %3 = "llvm.load"(%2) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<23 x i8>
// CHECK-NEXT:        "ccpp_utils.set_string"(%1, %3) : (memref<?xi8>, !llvm.array<23 x i8>) -> ()
// CHECK-NEXT:        memref.store %1, %suites[] : memref<memref<?xi8>>
// CHECK-NEXT:        func.return
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_physics_suite_part_list(%suite_name : memref<?xi8>, %part_list : memref<memref<?xi8>>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "var_compatibility_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = arith.constant 9 : index
// CHECK-NEXT:          %4 = memref.alloc(%3) : memref<?xi8>
// CHECK-NEXT:          %5 = "llvm.mlir.addressof"() <{global_name = @str_radiation}> : () -> !llvm.ptr
// CHECK-NEXT:          %6 = "llvm.load"(%5) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<9 x i8>
// CHECK-NEXT:          "ccpp_utils.set_string"(%4, %6) : (memref<?xi8>, !llvm.array<9 x i8>) -> ()
// CHECK-NEXT:          memref.store %4, %part_list[] : memref<memref<?xi8>>
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %7 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %7, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-NEXT:      "ccpp_utils.suite_variables"() ({
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "ccpp_physics_suite_variables", is_function = false, args = ["suite_name", "var_list", "errmsg", "errflg", "input_vars", "output_vars"], use_stmts = [], arg_decls = ["character(len=*), intent(in) :: suite_name", "character(len=*), allocatable, intent(out) :: var_list(:)", "character(len=512), intent(out) :: errmsg", "integer, intent(out) :: errflg", "logical, optional, intent(in) :: input_vars", "logical, optional, intent(in) :: output_vars"], local_decls = ["logical :: do_input, do_output"]}> ({
// CHECK-NEXT:          %0 = "ccpp_utils.host_var_ref"() <{var_name = "suite_name", module_name = ""}> : () -> memref<?xi8>
// CHECK-NEXT:          %1 = "ccpp_utils.host_var_ref"() <{var_name = "errmsg", module_name = ""}> : () -> memref<512xi8>
// CHECK-NEXT:          %2 = "ccpp_utils.host_var_ref"() <{var_name = "errflg", module_name = ""}> : () -> memref<i32>
// CHECK-NEXT:          "ccpp_utils.clear_err_state"() <{errcode_var = "errflg", errmsg_var = "errmsg"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.assign"() ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "do_input"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            %3 = arith.constant true
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:          "ccpp_utils.assign"() ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "do_output"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            %4 = arith.constant true
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:          %5 = "ccpp_utils.call_expr"() <{callee = "present"}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "input_vars"}> : () -> ()
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i1
// CHECK-NEXT:          scf.if %5 {
// CHECK-NEXT:            "ccpp_utils.assign"() ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "do_input"}> : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "input_vars"}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:          }
// CHECK-NEXT:          %6 = "ccpp_utils.call_expr"() <{callee = "present"}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "output_vars"}> : () -> ()
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i1
// CHECK-NEXT:          scf.if %6 {
// CHECK-NEXT:            "ccpp_utils.assign"() ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "do_output"}> : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "output_vars"}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:          }
// CHECK-NEXT:          %7 = "ccpp_utils.trim"(%0) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:          %8 = "ccpp_utils.strcmp"(%7) <{literal = "var_compatibility_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %8 {
// CHECK-NEXT:            %9 = "ccpp_utils.var_ref_expr"() <{var_name = "do_input"}> : () -> i1
// CHECK-NEXT:            %10 = "ccpp_utils.var_ref_expr"() <{var_name = "do_output"}> : () -> i1
// CHECK-NEXT:            %11 = arith.constant true
// CHECK-NEXT:            %12 = arith.xori %10, %11 : i1
// CHECK-NEXT:            %13 = arith.andi %9, %12 : i1
// CHECK-NEXT:            scf.if %13 {
// CHECK-NEXT:              "ccpp_utils.allocate"() <{var_name = "var_list"}> ({
// CHECK-NEXT:                %14 = arith.constant 18 : i32
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %15 = arith.constant 1 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "cloud_graupel_number_concentration  "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %16 = arith.constant 2 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "effective_radius_of_stratiform_cloud_graupel"}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %17 = arith.constant 3 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "effective_radius_of_stratiform_cloud_liquid_water_particle"}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %18 = arith.constant 4 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "effective_radius_of_stratiform_cloud_rain_particle"}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %19 = arith.constant 5 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "effective_radius_of_stratiform_cloud_snow_particle"}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %20 = arith.constant 6 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "flag_indicating_cloud_microphysics_has_graupel"}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %21 = arith.constant 7 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "flag_indicating_cloud_microphysics_has_ice"}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %22 = arith.constant 8 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "longwave_radiation_fluxes           "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %23 = arith.constant 9 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "num_subcycles_for_effr              "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %24 = arith.constant 10 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "scalar_variable_for_testing         "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %25 = arith.constant 11 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "scalar_variable_for_testing_a       "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %26 = arith.constant 12 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "scalar_variable_for_testing_b       "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %27 = arith.constant 13 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "scalar_variable_for_testing_c       "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %28 = arith.constant 14 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "scheme_order_in_suite               "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %29 = arith.constant 15 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "surface_downwelling_shortwave_radiation_flux"}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %30 = arith.constant 16 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "surface_upwelling_shortwave_radiation_flux"}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %31 = arith.constant 17 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "turbulent_kinetic_energy            "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %32 = arith.constant 18 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "turbulent_kinetic_energy2           "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:            } else {
// CHECK-NEXT:              %33 = "ccpp_utils.var_ref_expr"() <{var_name = "do_input"}> : () -> i1
// CHECK-NEXT:              %34 = arith.constant true
// CHECK-NEXT:              %35 = arith.xori %33, %34 : i1
// CHECK-NEXT:              %36 = "ccpp_utils.var_ref_expr"() <{var_name = "do_output"}> : () -> i1
// CHECK-NEXT:              %37 = arith.andi %35, %36 : i1
// CHECK-NEXT:              scf.if %37 {
// CHECK-NEXT:                "ccpp_utils.allocate"() <{var_name = "var_list"}> ({
// CHECK-NEXT:                  %38 = arith.constant 14 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %39 = arith.constant 1 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "ccpp_error_code                     "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %40 = arith.constant 2 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "ccpp_error_message                  "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %41 = arith.constant 3 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "cloud_ice_number_concentration      "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %42 = arith.constant 4 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "effective_radius_of_stratiform_cloud_ice_particle"}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %43 = arith.constant 5 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "effective_radius_of_stratiform_cloud_liquid_water_particle"}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %44 = arith.constant 6 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "effective_radius_of_stratiform_cloud_rain_particle"}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %45 = arith.constant 7 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "effective_radius_of_stratiform_cloud_snow_particle"}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %46 = arith.constant 8 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "longwave_radiation_fluxes           "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %47 = arith.constant 9 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "scalar_variable_for_testing         "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %48 = arith.constant 10 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "scheme_order_in_suite               "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %49 = arith.constant 11 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "surface_downwelling_shortwave_radiation_flux"}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %50 = arith.constant 12 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "surface_upwelling_shortwave_radiation_flux"}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %51 = arith.constant 13 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "turbulent_kinetic_energy            "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %52 = arith.constant 14 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "turbulent_kinetic_energy2           "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              } else {
// CHECK-NEXT:                "ccpp_utils.allocate"() <{var_name = "var_list"}> ({
// CHECK-NEXT:                  %53 = arith.constant 22 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %54 = arith.constant 1 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "ccpp_error_code                     "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %55 = arith.constant 2 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "ccpp_error_message                  "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %56 = arith.constant 3 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "cloud_graupel_number_concentration  "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %57 = arith.constant 4 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "cloud_ice_number_concentration      "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %58 = arith.constant 5 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "effective_radius_of_stratiform_cloud_graupel"}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %59 = arith.constant 6 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "effective_radius_of_stratiform_cloud_ice_particle"}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %60 = arith.constant 7 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "effective_radius_of_stratiform_cloud_liquid_water_particle"}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %61 = arith.constant 8 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "effective_radius_of_stratiform_cloud_rain_particle"}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %62 = arith.constant 9 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "effective_radius_of_stratiform_cloud_snow_particle"}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %63 = arith.constant 10 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "flag_indicating_cloud_microphysics_has_graupel"}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %64 = arith.constant 11 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "flag_indicating_cloud_microphysics_has_ice"}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %65 = arith.constant 12 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "longwave_radiation_fluxes           "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %66 = arith.constant 13 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "num_subcycles_for_effr              "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %67 = arith.constant 14 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "scalar_variable_for_testing         "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %68 = arith.constant 15 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "scalar_variable_for_testing_a       "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %69 = arith.constant 16 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "scalar_variable_for_testing_b       "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %70 = arith.constant 17 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "scalar_variable_for_testing_c       "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %71 = arith.constant 18 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "scheme_order_in_suite               "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %72 = arith.constant 19 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "surface_downwelling_shortwave_radiation_flux"}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %73 = arith.constant 20 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "surface_upwelling_shortwave_radiation_flux"}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %74 = arith.constant 21 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "turbulent_kinetic_energy            "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %75 = arith.constant 22 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "turbulent_kinetic_energy2           "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              }
// CHECK-NEXT:            }
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%1, %7) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %76 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %76, %2[] : memref<i32>
// CHECK-NEXT:          }
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "cam_constituents_obj", base_type = "type", rank = 0 : i64, ddt_name = "ccpp_model_constituents_t", is_target = true}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_all_constituents", base_type = "integer", rank = 1 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_constituent_array", base_type = "real", rank = 3 : i64, kind = "kind_phys", is_pointer = true}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_const_props", base_type = "type", rank = 1 : i64, ddt_name = "ccpp_constituent_prop_ptr_t", is_target = true}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_ncl_out", base_type = "real", rank = 2 : i64, kind = "kind_phys"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.non_cam_host_constituent_api"() <{public_names = ["VarCompatibility_ccpp_is_scheme_constituent", "VarCompatibility_ccpp_deallocate_dynamic_constituents", "VarCompatibility_ccpp_register_constituents", "VarCompatibility_ccpp_number_constituents", "VarCompatibility_ccpp_initialize_constituents", "VarCompatibility_constituents_array", "VarCompatibility_advected_constituents_array", "VarCompatibility_const_get_index", "VarCompatibility_model_const_properties"]}> ({
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "VarCompatibility_ccpp_is_scheme_constituent", is_function = false, args = ["std_name", "is_const", "errflg", "errmsg"], use_stmts = [], arg_decls = ["character(len=*), intent(in) :: std_name", "logical, intent(out) :: is_const", "integer, intent(out) :: errflg", "character(len=512), intent(out) :: errmsg"], local_decls = ["integer :: lc_idx", "character(len=256) :: lc_std_name"]}> ({
// CHECK-NEXT:          "ccpp_utils.clear_err_state"() <{errcode_var = "errflg", errmsg_var = "errmsg"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.assign"() ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "is_const"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            %77 = arith.constant false
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "VarCompatibility_ccpp_deallocate_dynamic_constituents", is_function = false, args = [], use_stmts = [], arg_decls = [], local_decls = []}> ({
// CHECK-NEXT:          "ccpp_utils.safe_dealloc"() <{var_name = "lc_all_constituents"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.safe_dealloc"() <{var_name = "lc_const_props"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.nullify_pointer"() <{ptr_name = "lc_constituent_array", if_associated}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.safe_dealloc"() <{var_name = "lc_ncl_out"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.cam_direct_call"() <{callee = "cam_constituents_obj%reset", call_args = []}> : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "VarCompatibility_ccpp_register_constituents", is_function = false, args = ["host_constituents", "errmsg", "errcode"], use_stmts = ["use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t, ccpp_constituent_prop_ptr_t", "use ccpp_scheme_utils, only: ccpp_scheme_utils_set_constituents"], arg_decls = ["type(ccpp_constituent_properties_t), target, intent(in) :: host_constituents(:)", "character(len=512), intent(out) :: errmsg", "integer, intent(out) :: errcode"], local_decls = ["integer :: lc_i, lc_num_consts", "type(ccpp_constituent_properties_t), pointer :: const_prop", "type(ccpp_constituent_prop_ptr_t), pointer :: lc_props_ptr(:)"]}> ({
// CHECK-NEXT:          "ccpp_utils.clear_err_state"() <{errcode_var = "errcode", errmsg_var = "errmsg"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.assign"() ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "lc_num_consts"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            %78 = "ccpp_utils.call_expr"() <{callee = "size"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "host_constituents"}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i32
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:          "ccpp_utils.assign"() ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "lc_num_consts"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            %79 = "ccpp_utils.var_ref_expr"() <{var_name = "lc_num_consts"}> : () -> i32
// CHECK-NEXT:            %80 = arith.constant 0 : i32
// CHECK-NEXT:            %81 = arith.addi %79, %80 : i32
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:          "ccpp_utils.ddt_method_call"() <{method = "initialize_table", kwargs = []}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "cam_constituents_obj"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "lc_num_consts"}> : () -> ()
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 1, 0>} : () -> ()
// CHECK-NEXT:          "ccpp_utils.text_bounded_do_loop"() <{loop_var = "lc_i", upper_expr = "size(host_constituents)"}> ({
// CHECK-NEXT:            "ccpp_utils.allocate"() <{var_name = "const_prop", dims = [], stat_var = "errcode"}> : () -> ()
// CHECK-NEXT:            %82 = "ccpp_utils.var_ref_expr"() <{var_name = "errcode"}> : () -> i32
// CHECK-NEXT:            %83 = arith.constant 0 : i32
// CHECK-NEXT:            %84 = arith.cmpi ne, %82, %83 : i32
// CHECK-NEXT:            scf.if %84 {
// CHECK-NEXT:              "ccpp_utils.error_exit"() <{errmsg_var = "errmsg", errmsg_text = "ERROR allocating const_prop"}> : () -> ()
// CHECK-NEXT:            }
// CHECK-NEXT:            "ccpp_utils.assign"() ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "const_prop"}> : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "host_constituents"}> : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "lc_i"}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:            "ccpp_utils.ddt_method_call"() <{method = "new_field"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "cam_constituents_obj"}> : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "const_prop"}> : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.keyword_arg_expr"() <{arg_name = "errcode"}> ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "errcode"}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.keyword_arg_expr"() <{arg_name = "errmsg"}> ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "errmsg"}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 1, 2>} : () -> ()
// CHECK-NEXT:            "ccpp_utils.nullify_pointer"() <{ptr_name = "const_prop"}> : () -> ()
// CHECK-NEXT:            "ccpp_utils.error_propagate"() <{errcode_var = "errcode"}> : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          "ccpp_utils.ddt_method_call"() <{method = "lock_table", args = []}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "cam_constituents_obj"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.keyword_arg_expr"() <{arg_name = "errcode"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "errcode"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.keyword_arg_expr"() <{arg_name = "errmsg"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "errmsg"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 0, 2>} : () -> ()
// CHECK-NEXT:          "ccpp_utils.error_propagate"() <{errcode_var = "errcode"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.pointer_assign"() <{ptr_name = "lc_props_ptr"}> ({
// CHECK-NEXT:            "ccpp_utils.member_access_expr"() <{member = "constituent_props_ptr()"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "cam_constituents_obj"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          "ccpp_utils.safe_dealloc"() <{var_name = "lc_const_props"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.allocate"() <{var_name = "lc_const_props"}> ({
// CHECK-NEXT:            "ccpp_utils.call_expr"() <{callee = "size"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "lc_props_ptr"}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 0>} : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          "ccpp_utils.assign"() ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "lc_const_props"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "lc_props_ptr"}> : () -> ()
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:          "ccpp_utils.nullify_pointer"() <{ptr_name = "lc_props_ptr"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.cam_direct_call"() <{callee = "ccpp_scheme_utils_set_constituents", call_args = ["lc_const_props"]}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.ddt_method_call"() <{method = "num_constituents"}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "cam_constituents_obj"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "lc_num_consts"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.keyword_arg_expr"() <{arg_name = "errcode"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "errcode"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.keyword_arg_expr"() <{arg_name = "errmsg"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "errmsg"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 1, 2>} : () -> ()
// CHECK-NEXT:          "ccpp_utils.error_propagate"() <{errcode_var = "errcode"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.safe_dealloc"() <{var_name = "lc_all_constituents"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.allocate"() <{var_name = "lc_all_constituents"}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "lc_num_consts"}> : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "VarCompatibility_ccpp_number_constituents", is_function = false, args = ["num_advected", "errmsg", "errcode", "advected"], use_stmts = [], arg_decls = ["integer, intent(out) :: num_advected", "character(len=512), intent(out) :: errmsg", "integer, intent(out) :: errcode", "logical, optional, intent(in) :: advected"], local_decls = []}> ({
// CHECK-NEXT:          "ccpp_utils.clear_err_state"() <{errcode_var = "errcode", errmsg_var = "errmsg"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.ddt_method_call"() <{method = "num_constituents"}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "cam_constituents_obj"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "num_advected"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.keyword_arg_expr"() <{arg_name = "advected"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "advected"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.keyword_arg_expr"() <{arg_name = "errcode"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "errcode"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.keyword_arg_expr"() <{arg_name = "errmsg"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "errmsg"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 1, 3>} : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "VarCompatibility_ccpp_initialize_constituents", is_function = false, args = ["ncols", "pver", "errflg", "errmsg"], use_stmts = [], arg_decls = ["integer, intent(in) :: ncols", "integer, intent(in) :: pver", "integer, intent(out) :: errflg", "character(len=512), intent(out) :: errmsg"], local_decls = []}> ({
// CHECK-NEXT:          "ccpp_utils.clear_err_state"() <{errcode_var = "errflg", errmsg_var = "errmsg"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.error_guard"() <{errmsg_text = "ccpp_initialize_constituents: register_constituents not called"}> ({
// CHECK-NEXT:            %85 = "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "lc_all_constituents"}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i1
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          "ccpp_utils.ddt_method_call"() <{method = "lock_data"}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "cam_constituents_obj"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "ncols"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "pver"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.keyword_arg_expr"() <{arg_name = "errcode"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "errflg"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.keyword_arg_expr"() <{arg_name = "errmsg"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "errmsg"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 2, 2>} : () -> ()
// CHECK-NEXT:          "ccpp_utils.error_propagate"() <{errcode_var = "errflg"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.pointer_assign"() <{ptr_name = "lc_constituent_array"}> ({
// CHECK-NEXT:            "ccpp_utils.member_access_expr"() <{member = "field_data_ptr()"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "cam_constituents_obj"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          "ccpp_utils.safe_dealloc"() <{var_name = "lc_ncl_out"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.allocate"() <{var_name = "lc_ncl_out"}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "ncols, pver"}> : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          "ccpp_utils.zero_fill"() <{var_name = "lc_ncl_out"}> : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "VarCompatibility_constituents_array", is_function = true, args = [], use_stmts = [], arg_decls = [], local_decls = [], result_name = "ptr", result_decl = "real(kind=kind_phys), pointer :: ptr(:, :, :)"}> ({
// CHECK-NEXT:          "ccpp_utils.pointer_assign"() <{ptr_name = "ptr"}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "lc_constituent_array"}> : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "VarCompatibility_advected_constituents_array", is_function = true, args = [], use_stmts = [], arg_decls = [], local_decls = [], result_name = "ptr", result_decl = "real(kind=kind_phys), pointer :: ptr(:, :, :)"}> ({
// CHECK-NEXT:          "ccpp_utils.pointer_assign"() <{ptr_name = "ptr"}> ({
// CHECK-NEXT:            "ccpp_utils.member_access_expr"() <{member = "advected_constituents_ptr()"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "cam_constituents_obj"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "VarCompatibility_const_get_index", is_function = false, args = ["std_name", "index", "errflg", "errmsg"], use_stmts = ["use ccpp_constituent_prop_mod, only: to_lower"], arg_decls = ["character(len=*), intent(in) :: std_name", "integer, intent(out) :: index", "integer, intent(out) :: errflg", "character(len=512), intent(out) :: errmsg"], local_decls = []}> ({
// CHECK-NEXT:          "ccpp_utils.clear_err_state"() <{errcode_var = "errflg", errmsg_var = "errmsg"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.assign"() ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "index"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            %86 = arith.constant -1 : i32
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:          "ccpp_utils.error_guard"() <{errmsg_text = "const_get_index: constituents not registered"}> ({
// CHECK-NEXT:            %87 = "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "lc_all_constituents"}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i1
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          "ccpp_utils.ddt_method_call"() <{method = "const_index"}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "cam_constituents_obj"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "index"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.call_expr"() <{callee = "to_lower"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "std_name"}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 0>} : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.keyword_arg_expr"() <{arg_name = "errcode"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "errflg"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.keyword_arg_expr"() <{arg_name = "errmsg"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "errmsg"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 2, 2>} : () -> ()
// CHECK-NEXT:          %88 = "ccpp_utils.var_ref_expr"() <{var_name = "errflg"}> : () -> i32
// CHECK-NEXT:          %89 = arith.constant 0 : i32
// CHECK-NEXT:          %90 = arith.cmpi ne, %88, %89 : i32
// CHECK-NEXT:          %91 = "ccpp_utils.var_ref_expr"() <{var_name = "index"}> : () -> i32
// CHECK-NEXT:          %92 = arith.constant 0 : i32
// CHECK-NEXT:          %93 = arith.cmpi sle, %91, %92 : i32
// CHECK-NEXT:          %94 = arith.ori %90, %93 : i1
// CHECK-NEXT:          scf.if %94 {
// CHECK-NEXT:            "ccpp_utils.assign"() <{lhs_expr = "errflg", rhs_expr = "1"}> {regionSegmentSizes = array<i32: 0, 0>} : () -> ()
// CHECK-NEXT:            "ccpp_utils.write_stmt"() <{dest = "errmsg", format_spec = "(3a)", items = ["'const_get_index: constituent '", "trim(std_name)", "' not found'"]}> : () -> ()
// CHECK-NEXT:          }
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "VarCompatibility_model_const_properties", is_function = true, args = [], use_stmts = [], arg_decls = [], local_decls = [], result_name = "ptr", result_decl = "type(ccpp_constituent_prop_ptr_t), pointer :: ptr(:)"}> ({
// CHECK-NEXT:          "ccpp_utils.pointer_assign"() <{ptr_name = "ptr"}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "lc_const_props"}> : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-LABEL:     func.func private @var_compatibility_suite_register() -> (memref<i32>, memref<512xi8>) attributes {module = "var_compatibility_suite_cap"}
// CHECK-LABEL:     func.func private @var_compatibility_suite_initialize() -> (memref<i32>, memref<512xi8>) attributes {module = "var_compatibility_suite_cap"}
// CHECK-LABEL:     func.func private @var_compatibility_suite_finalize() -> (memref<i32>, memref<512xi8>) attributes {module = "var_compatibility_suite_cap"}
// CHECK-LABEL:     func.func private @var_compatibility_suite_radiation(memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i1>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<?x!ccpp_utils.derived_type<"ty_rad_lw">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>) -> (memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) attributes {module = "var_compatibility_suite_cap"}
// CHECK-LABEL:     func.func private @var_compatibility_suite_timestep_init_radiation() -> (memref<i32>, memref<512xi8>) attributes {module = "var_compatibility_suite_cap"}
// CHECK-LABEL:     func.func private @var_compatibility_suite_timestep_final_radiation() -> (memref<i32>, memref<512xi8>) attributes {module = "var_compatibility_suite_cap"}
// CHECK-LABEL:     func.func private @var_compatibility_suite_init_radiation(memref<i32>) -> (memref<i32>, memref<512xi8>, memref<i32>) attributes {module = "var_compatibility_suite_cap"}
// CHECK-LABEL:     func.func private @var_compatibility_suite_final_radiation() -> (memref<i32>, memref<512xi8>) attributes {module = "var_compatibility_suite_cap"}
// CHECK:         }
// CHECK-LABEL:   builtin.module @ccpp_kinds {
// CHECK:           "ccpp_utils.kind_def"() <{kind_name = "kind_phys", kind_value = "REAL64", kind_module = "iso_fortran_env"}> : () -> ()
// CHECK-NEXT:    }
// CHECK-NEXT:  }
