// Test the completed IR for the var_compat XML frontend -- ported from NCAR
// ccpp-framework's feature/capgen-v1 branch, end-to-end-tests/var_compat.
// Exercises: nested-subcycle codegen at the completed-IR level -- the
// var_compatibility_suite_suite_radiation function below contains a
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
// combined VarCompatibility_ccpp_physics_run wrapper used to have no
// copy-back at all for this case, so it always declared them intent(in)
// even though the suite callee it calls (var_compatibility_suite_suite_
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
// CHECK-LABEL:   builtin.module @var_compatibility_suite_cap {
// CHECK:           "llvm.mlir.global"() <{global_type = !llvm.array<16 x i8>, sym_name = "ccpp_suite_state", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, value = "uninitialized"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<16 x i8>, sym_name = "const_in_time_step", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "in_time_step"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<16 x i8>, sym_name = "const_initialized", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "initialized"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<16 x i8>, sym_name = "const_uninitialized", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "uninitialized"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<0 x i8>, sym_name = "ty_rad_lw", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "module_rad_ddt"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "ncols", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "pver", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "ncl_out", base_type = "real", rank = 2 : i64, kind = "kind_phys"}> : () -> ()
// CHECK-LABEL:     func.func public @var_compatibility_suite_suite_register() -> (memref<i32>, memref<512xi8>) {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %ncols = "ccpp_utils.host_var_ref"() <{var_name = "ncols", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:        %pver = "ccpp_utils.host_var_ref"() <{var_name = "pver", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ncols, %pver) <{var_name = "ncl_out", kind_name = "kind_phys"}> : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @var_compatibility_suite_suite_initialize(%scheme_order : memref<i32>) -> (memref<i32>, memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
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
// CHECK-NEXT:        %10 = arith.constant 0 : i32
// CHECK-NEXT:        %11 = arith.cmpi eq, %12, %10 : i32
// CHECK-NEXT:        %12 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %11 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%scheme_order, %errmsg, %errflg) <{callee = "effr_pre_init", operand_names = ["scheme_order", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %13 = arith.constant 0 : i32
// CHECK-NEXT:        %14 = arith.cmpi eq, %15, %13 : i32
// CHECK-NEXT:        %15 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %14 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%scheme_order, %errmsg, %errflg) <{callee = "effr_calc_init", operand_names = ["scheme_order", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %16 = arith.constant 0 : i32
// CHECK-NEXT:        %17 = arith.cmpi eq, %18, %16 : i32
// CHECK-NEXT:        %18 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %17 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%scheme_order, %errmsg, %errflg) <{callee = "effr_post_init", operand_names = ["scheme_order", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %19 = arith.constant 0 : i32
// CHECK-NEXT:        %20 = arith.cmpi eq, %21, %19 : i32
// CHECK-NEXT:        %21 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %20 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%scheme_order, %errmsg, %errflg) <{callee = "effr_diag_init", operand_names = ["scheme_order", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %22 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %23 = "llvm.load"(%22) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %24 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%23, %24) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %scheme_order, %errmsg, %errflg : memref<i32>, memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @var_compatibility_suite_suite_finalize() -> (memref<i32>, memref<512xi8>) {
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
// CHECK-LABEL:     func.func public @var_compatibility_suite_suite_timestep_initial() -> (memref<i32>, memref<512xi8>) {
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
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in var_compatibility_suite_timestep_initial"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = "llvm.mlir.addressof"() <{global_name = @const_in_time_step}> : () -> !llvm.ptr
// CHECK-NEXT:        %11 = "llvm.load"(%10) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %12 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%11, %12) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @var_compatibility_suite_suite_timestep_final() -> (memref<i32>, memref<512xi8>) {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_in_time_step}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        %4 = "llvm.load"(%3) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %5 = "ccpp_utils.strcmp"(%2, %4) <{length = 12 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %6 = arith.constant true
// CHECK-NEXT:        %7 = arith.xori %5, %6 : i1
// CHECK-NEXT:        scf.if %7 {
// CHECK-NEXT:          %8 = "ccpp_utils.trim"(%4) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in var_compatibility_suite_timestep_final"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %11 = "llvm.load"(%10) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %12 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%11, %12) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @var_compatibility_suite_suite_radiation(%effrr_inout : memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, %scalar_varA : memref<!ccpp_utils.real_kind<"kind_phys">>, %ncol : memref<i32>, %nlev : memref<i32>, %effrg_in__opt : memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, %ncg_in__opt : memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, %nci_out__opt : memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, %effrl_inout : memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, %effri_out__opt : memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, %effrs_inout : memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, %ncl_out__opt : memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, %has_graupel : memref<i1>, %scalar_var : memref<!ccpp_utils.real_kind<"kind_phys">>, %tke_inout : memref<!ccpp_utils.real_kind<"kind_phys">>, %tke2_inout : memref<!ccpp_utils.real_kind<"kind_phys">>, %scalar_varB : memref<!ccpp_utils.real_kind<"kind_phys">>, %scalar_varC : memref<i32>, %fluxLW : memref<?x!ccpp_utils.derived_type<"ty_rad_lw">>, %sfc_up_sw : memref<?x!ccpp_utils.real_kind<"kind_phys">>, %sfc_down_sw : memref<?x!ccpp_utils.real_kind<"kind_phys">>, %num_subcycles : memref<i32>) -> (memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %effrg_in_unit_conv = "ccpp_utils.unit_convert"(%effrg_in__opt) <{to_scheme_expr = "* 1.0E6"}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %effrl_inout_unit_conv = "ccpp_utils.unit_convert"(%effrl_inout) <{to_scheme_expr = "* 1.0E6"}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %effri_out_unit_conv = "ccpp_utils.unit_convert"(%effri_out__opt) <{to_scheme_expr = ""}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
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
// CHECK-NEXT:        "ccpp_utils.subcycle_loop"(%ccpp_loop_cnt_2) <{loop_count = "num_subcycles", is_literal = false}> ({
// CHECK-NEXT:          %10 = arith.constant 0 : i32
// CHECK-NEXT:          %11 = arith.cmpi eq, %12, %10 : i32
// CHECK-NEXT:          %12 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:          scf.if %11 {
// CHECK-NEXT:            "ccpp_utils.kw_call"(%effrr_inout, %scalar_varA, %errmsg, %errflg) <{callee = "effr_pre_run", operand_names = ["effrr_inout", "scalar_var", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:          }
// CHECK-NEXT:          "ccpp_utils.subcycle_loop"(%ccpp_loop_cnt_1) <{loop_count = "2", is_literal = true}> ({
// CHECK-NEXT:            "ccpp_utils.subcycle_loop"(%ccpp_loop_cnt) <{loop_count = "2", is_literal = true}> ({
// CHECK-NEXT:              %13 = arith.constant 0 : i32
// CHECK-NEXT:              %14 = arith.cmpi eq, %15, %13 : i32
// CHECK-NEXT:              %15 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:              scf.if %14 {
// CHECK-NEXT:                %effrr_in_unit_conv = "ccpp_utils.unit_convert"(%effrr_inout) <{to_scheme_expr = "* 1.0E6"}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:                %effrr_in_vert_flip = "ccpp_utils.vertical_flip"(%effrr_in_unit_conv) <{vertical_dim = 2 : i64}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:                %effrs_inout_kind_cast = "ccpp_utils.kind_cast"(%effrs_inout) <{target_kind = "8"}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<?x?x!ccpp_utils.real_kind<"8">>
// CHECK-NEXT:                %effrs_inout_unit_conv = "ccpp_utils.unit_convert"(%effrs_inout_kind_cast) <{to_scheme_expr = "* 1.0E6"}> : (memref<?x?x!ccpp_utils.real_kind<"8">>) -> memref<?x?x!ccpp_utils.real_kind<"8">>
// CHECK-NEXT:                %effrs_inout_vert_flip = "ccpp_utils.vertical_flip"(%effrs_inout_unit_conv) <{vertical_dim = 2 : i64}> : (memref<?x?x!ccpp_utils.real_kind<"8">>) -> memref<?x?x!ccpp_utils.real_kind<"8">>
// CHECK-NEXT:                "ccpp_utils.kw_call"(%ncol, %nlev, %effrr_in_vert_flip, %effrg_in_unit_conv, %ncg_in__opt, %nci_out__opt, %effrl_inout_unit_conv, %effri_out_unit_conv, %effrs_inout_vert_flip, %ncl_out__opt, %has_graupel, %scalar_var_unit_conv, %tke_inout_unit_conv, %tke2_inout, %errmsg, %errflg) <{callee = "effr_calc_run", operand_names = ["ncol", "nlev", "effrr_in", "effrg_in", "ncg_in", "nci_out", "effrl_inout", "effri_out", "effrs_inout", "ncl_out", "has_graupel", "scalar_var", "tke_inout", "tke2_inout", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<i32>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"8">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i1>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:                "ccpp_utils.vertical_flip_write_back"(%effrs_inout_vert_flip, %effrs_inout_unit_conv) <{vertical_dim = 2 : i64}> : (memref<?x?x!ccpp_utils.real_kind<"8">>, memref<?x?x!ccpp_utils.real_kind<"8">>) -> ()
// CHECK-NEXT:                "ccpp_utils.unit_write_back"(%effrs_inout_unit_conv, %effrs_inout_kind_cast) <{to_host_expr = "* 1.0E-6"}> : (memref<?x?x!ccpp_utils.real_kind<"8">>, memref<?x?x!ccpp_utils.real_kind<"8">>) -> ()
// CHECK-NEXT:                "ccpp_utils.kind_write_back"(%effrs_inout_kind_cast, %effrs_inout) <{original_kind = "kind_phys"}> : (memref<?x?x!ccpp_utils.real_kind<"8">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> ()
// CHECK-NEXT:              }
// CHECK-NEXT:            }) : (memref<i32>) -> ()
// CHECK-NEXT:          }) : (memref<i32>) -> ()
// CHECK-NEXT:          %16 = arith.constant 0 : i32
// CHECK-NEXT:          %17 = arith.cmpi eq, %18, %16 : i32
// CHECK-NEXT:          %18 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:          scf.if %17 {
// CHECK-NEXT:            "ccpp_utils.kw_call"(%effrr_inout, %scalar_varB, %errmsg, %errflg) <{callee = "effr_post_run", operand_names = ["effrr_inout", "scalar_var", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:          }
// CHECK-NEXT:        }) : (memref<i32>) -> ()
// CHECK-NEXT:        "ccpp_utils.subcycle_loop"(%ccpp_loop_cnt_3) <{loop_count = "num_subcycles", is_literal = false}> ({
// CHECK-NEXT:          %19 = arith.constant 0 : i32
// CHECK-NEXT:          %20 = arith.cmpi eq, %21, %19 : i32
// CHECK-NEXT:          %21 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:          scf.if %20 {
// CHECK-NEXT:            "ccpp_utils.kw_call"(%effrs_inout, %errmsg, %errflg) <{callee = "effrs_calc_run", operand_names = ["effrs_inout", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:          }
// CHECK-NEXT:        }) : (memref<i32>) -> ()
// CHECK-NEXT:        %22 = arith.constant 0 : i32
// CHECK-NEXT:        %23 = arith.cmpi eq, %24, %22 : i32
// CHECK-NEXT:        %24 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %23 {
// CHECK-NEXT:          %effrr_in_unit_conv_1 = "ccpp_utils.unit_convert"(%effrr_inout) <{to_scheme_expr = "* 1.0E6"}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %effrr_in_vert_flip_1 = "ccpp_utils.vertical_flip"(%effrr_in_unit_conv_1) <{vertical_dim = 2 : i64}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          "ccpp_utils.kw_call"(%effrr_in_vert_flip_1, %scalar_varC, %errmsg, %errflg) <{callee = "effr_diag_run", operand_names = ["effrr_in", "scalar_var", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %25 = arith.constant 0 : i32
// CHECK-NEXT:        %26 = arith.cmpi eq, %27, %25 : i32
// CHECK-NEXT:        %27 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %26 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%ncol, %fluxLW, %errmsg, %errflg) <{callee = "rad_lw_run", operand_names = ["ncol", "fluxLW", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<?x!ccpp_utils.derived_type<"ty_rad_lw">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %28 = arith.constant 0 : i32
// CHECK-NEXT:        %29 = arith.cmpi eq, %30, %28 : i32
// CHECK-NEXT:        %30 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %29 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%ncol, %sfc_up_sw, %sfc_down_sw, %errmsg, %errflg) <{callee = "rad_sw_run", operand_names = ["ncol", "sfc_up_sw", "sfc_down_sw", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        "ccpp_utils.unit_write_back"(%effrl_inout_unit_conv, %effrl_inout) <{to_host_expr = "* 1.0E-6"}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> ()
// CHECK-NEXT:        "ccpp_utils.unit_write_back"(%effri_out_unit_conv, %effri_out__opt) <{to_host_expr = "* 1.0E-6"}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> ()
// CHECK-NEXT:        "ccpp_utils.unit_write_back"(%scalar_var_unit_conv, %scalar_var) <{to_host_expr = "* 1000.0"}> : (memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>) -> ()
// CHECK-NEXT:        "ccpp_utils.unit_write_back"(%tke_inout_unit_conv, %tke_inout) <{to_host_expr = "* 1.0"}> : (memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>) -> ()
// CHECK-NEXT:        func.return %scalar_var, %tke_inout, %tke2_inout, %errmsg, %errflg : memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func private @effr_pre_init(memref<i32>, memref<512xi8>, memref<i32>) -> () attributes {module = "effr_pre"}
// CHECK-LABEL:     func.func private @effr_calc_init(memref<i32>, memref<512xi8>, memref<i32>) -> () attributes {module = "effr_calc"}
// CHECK-LABEL:     func.func private @effr_post_init(memref<i32>, memref<512xi8>, memref<i32>) -> () attributes {module = "effr_post"}
// CHECK-LABEL:     func.func private @effr_diag_init(memref<i32>, memref<512xi8>, memref<i32>) -> () attributes {module = "effr_diag"}
// CHECK-LABEL:     func.func private @effr_pre_run(memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "effr_pre"}
// CHECK-LABEL:     func.func private @effr_calc_run(memref<i32>, memref<i32>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"8">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i1>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "effr_calc"}
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
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<0 x i8>, sym_name = "ty_rad_lw", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "module_rad_ddt"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<0 x i8>, sym_name = "ty_rad_sw", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "module_rad_ddt"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<0 x i8>, sym_name = "physics_state", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_data"} : () -> ()
// CHECK-LABEL:     func.func public @VarCompatibility_ccpp_physics_register(%suite_name : memref<?xi8>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "var_compatibility_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3, %4 = func.call @var_compatibility_suite_suite_register() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:          "memref.copy"(%3, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          "memref.copy"(%4, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %5 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %5, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @VarCompatibility_ccpp_physics_initialize(%suite_name : memref<?xi8>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "var_compatibility_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = "ccpp_utils.host_var_ref"() <{var_name = "phys_state", module_name = "test_host_mod"}> {member_name = "scheme_order"} : () -> memref<i32>
// CHECK-NEXT:          %4, %5 = func.call @var_compatibility_suite_suite_initialize(%3) : (memref<i32>) -> (memref<512xi8>, memref<i32>)
// CHECK-NEXT:          "memref.copy"(%4, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:          "memref.copy"(%5, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %6 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %6, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @VarCompatibility_ccpp_physics_finalize(%suite_name : memref<?xi8>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "var_compatibility_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3, %4 = func.call @var_compatibility_suite_suite_finalize() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:          "memref.copy"(%3, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          "memref.copy"(%4, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %5 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %5, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @VarCompatibility_ccpp_physics_timestep_initial(%suite_name : memref<?xi8>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "var_compatibility_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3, %4 = func.call @var_compatibility_suite_suite_timestep_initial() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:          "memref.copy"(%3, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          "memref.copy"(%4, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %5 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %5, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @VarCompatibility_ccpp_physics_timestep_final(%suite_name : memref<?xi8>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "var_compatibility_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3, %4 = func.call @var_compatibility_suite_suite_timestep_final() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:          "memref.copy"(%3, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          "memref.copy"(%4, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %5 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %5, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @VarCompatibility_ccpp_physics_run(%suite_name : memref<?xi8>, %suite_part : memref<?xi8>, %col_start : memref<i32>, %col_end : memref<i32>, %errmsg : memref<512xi8>, %errflg : memref<i32>) -> (memref<512xi8>, memref<i32>) {
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
// CHECK-NEXT:          %30 = "ccpp_utils.array_section"(%4, %col_start, %29, %col_end, %11) {operandSegmentSizes = array<i32: 1, 2, 2>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, memref<i32>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %31 = "ccpp_utils.array_section"(%12, %col_start, %29, %col_end, %11) {operandSegmentSizes = array<i32: 1, 2, 2>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, memref<i32>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %32 = "ccpp_utils.array_section"(%13, %col_start, %29, %col_end, %11) {operandSegmentSizes = array<i32: 1, 2, 2>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, memref<i32>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %33 = "ccpp_utils.array_section"(%14, %col_start, %29, %col_end, %11) {operandSegmentSizes = array<i32: 1, 2, 2>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, memref<i32>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %34 = "ccpp_utils.array_section"(%15, %col_start, %29, %col_end, %11) {operandSegmentSizes = array<i32: 1, 2, 2>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, memref<i32>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %35 = "ccpp_utils.array_section"(%16, %col_start, %29, %col_end, %11) {operandSegmentSizes = array<i32: 1, 2, 2>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, memref<i32>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %36 = "ccpp_utils.array_section"(%17, %col_start, %29, %col_end, %11) {operandSegmentSizes = array<i32: 1, 2, 2>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, memref<i32>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %37 = "ccpp_utils.array_section"(%18, %col_start, %29, %col_end, %11) {operandSegmentSizes = array<i32: 1, 2, 2>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, memref<i32>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %38 = "ccpp_utils.array_section"(%25, %col_start, %col_end) {operandSegmentSizes = array<i32: 1, 1, 1>} : (memref<?x!ccpp_utils.derived_type<"ty_rad_lw">>, memref<i32>, memref<i32>) -> memref<?x!ccpp_utils.derived_type<"ty_rad_lw">>
// CHECK-NEXT:          %39 = "ccpp_utils.array_section"(%26, %col_start, %col_end) {operandSegmentSizes = array<i32: 1, 1, 1>} : (memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>) -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %40 = "ccpp_utils.array_section"(%27, %col_start, %col_end) {operandSegmentSizes = array<i32: 1, 1, 1>} : (memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>) -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %41 = "ccpp_utils.strcmp"(%3) <{literal = "radiation"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %41 {
// CHECK-NEXT:            %42, %43, %44, %45, %46 = "ccpp_utils.kw_call"(%30, %5, %ncol, %11, %31, %32, %33, %34, %35, %36, %37, %19, %20, %21, %22, %23, %24, %38, %39, %40, %28) <{callee = "var_compatibility_suite_suite_radiation", operand_names = ["effrr_inout", "scalar_varA", "ncol", "nlev", "effrg_in", "ncg_in", "nci_out", "effrl_inout", "effri_out", "effrs_inout", "ncl_out", "has_graupel", "scalar_var", "tke_inout", "tke2_inout", "scalar_varB", "scalar_varC", "fluxLW", "sfc_up_sw", "sfc_down_sw", "num_subcycles"], result_names = ["scalar_var", "tke_inout", "tke2_inout", "errmsg", "errflg"], overrides = {}}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i1>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<?x!ccpp_utils.derived_type<"ty_rad_lw">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>) -> (memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>)
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
// CHECK-NEXT:      "ccpp_utils.suite_variables"() <{body = "subroutine ccpp_physics_suite_variables(suite_name, var_list, errmsg, errflg, input_vars, output_vars)\n  character(len=*), intent(in) :: suite_name\n  character(len=*), allocatable, intent(out) :: var_list(:)\n  character(len=512), intent(out) :: errmsg\n  integer, intent(out) :: errflg\n  logical, optional, intent(in) :: input_vars\n  logical, optional, intent(in) :: output_vars\n  logical :: do_input, do_output\n  errmsg = ''\n  errflg = 0\n  do_input = .true.\n  do_output = .true.\n  if (present(input_vars)) do_input = input_vars\n  if (present(output_vars)) do_output = output_vars\n  if (trim(suite_name) .eq. 'var_compatibility_suite') then\n    if (do_input .and. .not. do_output) then\n      allocate(var_list(18))\n      var_list(1) = 'cloud_graupel_number_concentration  '\n      var_list(2) = 'effective_radius_of_stratiform_cloud_graupel'\n      var_list(3) = 'effective_radius_of_stratiform_cloud_liquid_water_particle'\n      var_list(4) = 'effective_radius_of_stratiform_cloud_rain_particle'\n      var_list(5) = 'effective_radius_of_stratiform_cloud_snow_particle'\n      var_list(6) = 'flag_indicating_cloud_microphysics_has_graupel'\n      var_list(7) = 'flag_indicating_cloud_microphysics_has_ice'\n      var_list(8) = 'longwave_radiation_fluxes           '\n      var_list(9) = 'num_subcycles_for_effr              '\n      var_list(10) = 'scalar_variable_for_testing         '\n      var_list(11) = 'scalar_variable_for_testing_a       '\n      var_list(12) = 'scalar_variable_for_testing_b       '\n      var_list(13) = 'scalar_variable_for_testing_c       '\n      var_list(14) = 'scheme_order_in_suite               '\n      var_list(15) = 'surface_downwelling_shortwave_radiation_flux'\n      var_list(16) = 'surface_upwelling_shortwave_radiation_flux'\n      var_list(17) = 'turbulent_kinetic_energy            '\n      var_list(18) = 'turbulent_kinetic_energy2           '\n    else if (.not. do_input .and. do_output) then\n      allocate(var_list(14))\n      var_list(1) = 'ccpp_error_code                     '\n      var_list(2) = 'ccpp_error_message                  '\n      var_list(3) = 'cloud_ice_number_concentration      '\n      var_list(4) = 'effective_radius_of_stratiform_cloud_ice_particle'\n      var_list(5) = 'effective_radius_of_stratiform_cloud_liquid_water_particle'\n      var_list(6) = 'effective_radius_of_stratiform_cloud_rain_particle'\n      var_list(7) = 'effective_radius_of_stratiform_cloud_snow_particle'\n      var_list(8) = 'longwave_radiation_fluxes           '\n      var_list(9) = 'scalar_variable_for_testing         '\n      var_list(10) = 'scheme_order_in_suite               '\n      var_list(11) = 'surface_downwelling_shortwave_radiation_flux'\n      var_list(12) = 'surface_upwelling_shortwave_radiation_flux'\n      var_list(13) = 'turbulent_kinetic_energy            '\n      var_list(14) = 'turbulent_kinetic_energy2           '\n    else\n      allocate(var_list(22))\n      var_list(1) = 'ccpp_error_code                     '\n      var_list(2) = 'ccpp_error_message                  '\n      var_list(3) = 'cloud_graupel_number_concentration  '\n      var_list(4) = 'cloud_ice_number_concentration      '\n      var_list(5) = 'effective_radius_of_stratiform_cloud_graupel'\n      var_list(6) = 'effective_radius_of_stratiform_cloud_ice_particle'\n      var_list(7) = 'effective_radius_of_stratiform_cloud_liquid_water_particle'\n      var_list(8) = 'effective_radius_of_stratiform_cloud_rain_particle'\n      var_list(9) = 'effective_radius_of_stratiform_cloud_snow_particle'\n      var_list(10) = 'flag_indicating_cloud_microphysics_has_graupel'\n      var_list(11) = 'flag_indicating_cloud_microphysics_has_ice'\n      var_list(12) = 'longwave_radiation_fluxes           '\n      var_list(13) = 'num_subcycles_for_effr              '\n      var_list(14) = 'scalar_variable_for_testing         '\n      var_list(15) = 'scalar_variable_for_testing_a       '\n      var_list(16) = 'scalar_variable_for_testing_b       '\n      var_list(17) = 'scalar_variable_for_testing_c       '\n      var_list(18) = 'scheme_order_in_suite               '\n      var_list(19) = 'surface_downwelling_shortwave_radiation_flux'\n      var_list(20) = 'surface_upwelling_shortwave_radiation_flux'\n      var_list(21) = 'turbulent_kinetic_energy            '\n      var_list(22) = 'turbulent_kinetic_energy2           '\n    end if\n  else\n    write(errmsg, '(3a)') \"No suite named \", trim(suite_name), \" found\"\n    errflg = 1\n  end if\nend subroutine ccpp_physics_suite_variables"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_all_constituents", base_type = "type", rank = 1 : i64, ddt_name = "ccpp_constituent_properties_t", ftn_attrs = "target"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_constituent_array", base_type = "real", rank = 3 : i64, kind = "kind_phys", ftn_attrs = "target"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_const_tend", base_type = "real", rank = 3 : i64, kind = "kind_phys", ftn_attrs = "target"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_const_props", base_type = "type", rank = 1 : i64, ddt_name = "ccpp_constituent_prop_ptr_t", ftn_attrs = "target"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_ncl_out", base_type = "real", rank = 2 : i64, kind = "kind_phys"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.constituent_api"() <{body = "  subroutine VarCompatibility_ccpp_is_scheme_constituent(std_name, is_const, errflg, errmsg)\n    character(len=*), intent(in) :: std_name\n    logical, intent(out) :: is_const\n    integer, intent(out) :: errflg\n    character(len=512), intent(out) :: errmsg\n    integer :: lc_idx\n    errflg = 0\n    errmsg = ''\n    is_const = .false.\n    select case (trim(std_name))\n    case default\n    end select\n  end subroutine VarCompatibility_ccpp_is_scheme_constituent\n\n  subroutine VarCompatibility_ccpp_deallocate_dynamic_constituents()\n    if (allocated(lc_all_constituents)) deallocate(lc_all_constituents)\n    if (allocated(lc_const_props)) deallocate(lc_const_props)\n    if (allocated(lc_constituent_array)) deallocate(lc_constituent_array)\n    if (allocated(lc_const_tend)) deallocate(lc_const_tend)\n    if (allocated(lc_ncl_out)) deallocate(lc_ncl_out)\n  end subroutine VarCompatibility_ccpp_deallocate_dynamic_constituents\n\n  subroutine VarCompatibility_ccpp_register_constituents(host_constituents, errmsg, errflg)\n    use ccpp_scheme_utils, only: ccpp_scheme_utils_set_constituents\n    type(ccpp_constituent_properties_t), intent(in) :: host_constituents(:)\n    character(len=512), intent(out) :: errmsg\n    integer, intent(out) :: errflg\n    integer :: lc_max, lc_num, lc_i, lc_j\n    logical :: lc_found\n    type(ccpp_constituent_properties_t), allocatable :: lc_tmp(:)\n    errflg = 0\n    errmsg = ''\n    lc_max = 0\n    lc_max = lc_max + 0\n    lc_max = lc_max + size(host_constituents)\n    allocate(lc_tmp(lc_max))\n    lc_num = 0\n    do lc_i = 1, size(host_constituents)\n      lc_found = .false.\n      do lc_j = 1, lc_num\n        if (trim(lc_tmp(lc_j)%std_name) == trim(host_constituents(lc_i)%std_name)) then\n          lc_found = .true.\n          if (trim(lc_tmp(lc_j)%units) /= trim(host_constituents(lc_i)%units)) then\n            write(errmsg, '(3a)') 'ccp_model_const_add_metadata ERROR: Trying to add constituent ', trim(host_constituents(lc_i)%std_name), &\n              ' but an incompatible constituent with this name already exists'\n            errflg = 1\n            return\n          end if\n          exit\n        end if\n      end do\n      if (.not. lc_found) then\n        lc_num = lc_num + 1\n        lc_tmp(lc_num) = host_constituents(lc_i)\n      end if\n    end do\n    if (allocated(lc_all_constituents)) deallocate(lc_all_constituents)\n    allocate(lc_all_constituents(lc_num))\n    lc_all_constituents(1:lc_num) = lc_tmp(1:lc_num)\n    deallocate(lc_tmp)\n    if (allocated(lc_const_props)) deallocate(lc_const_props)\n    allocate(lc_const_props(lc_num))\n    do lc_i = 1, lc_num\n      lc_const_props(lc_i)%ptr => lc_all_constituents(lc_i)\n    end do\n    call ccpp_scheme_utils_set_constituents(lc_all_constituents)\n  end subroutine VarCompatibility_ccpp_register_constituents\n\n  subroutine VarCompatibility_ccpp_number_constituents(num_advected, errmsg, errflg)\n    integer, intent(out) :: num_advected\n    character(len=512), intent(out) :: errmsg\n    integer, intent(out) :: errflg\n    errflg = 0\n    errmsg = ''\n    if (allocated(lc_all_constituents)) then\n      num_advected = size(lc_all_constituents)\n    else\n      num_advected = 0\n    end if\n  end subroutine VarCompatibility_ccpp_number_constituents\n\n  subroutine VarCompatibility_ccpp_initialize_constituents(ncols, pver, errflg, errmsg)\n    integer, intent(in) :: ncols\n    integer, intent(in) :: pver\n    integer, intent(out) :: errflg\n    character(len=512), intent(out) :: errmsg\n    integer :: lc_num, lc_i\n    errflg = 0\n    errmsg = ''\n    if (.not. allocated(lc_all_constituents)) then\n      errflg = 1\n      errmsg = 'ccpp_initialize_constituents: register_constituents not called'\n      return\n    end if\n    lc_num = size(lc_all_constituents)\n    if (allocated(lc_constituent_array)) deallocate(lc_constituent_array)\n    allocate(lc_constituent_array(ncols, pver, lc_num))\n    lc_constituent_array = 0.0_kind_phys\n    do lc_i = 1, lc_num\n      if (lc_all_constituents(lc_i)%default_val_set) then\n        lc_constituent_array(:, :, lc_i) = lc_all_constituents(lc_i)%default_val\n      end if\n    end do\n    if (allocated(lc_const_tend)) deallocate(lc_const_tend)\n    allocate(lc_const_tend(ncols, pver, lc_num))\n    lc_const_tend = 0.0_kind_phys\n    if (allocated(lc_ncl_out)) deallocate(lc_ncl_out)\n    allocate(lc_ncl_out(ncols, pver))\n    lc_ncl_out = 0.0_kind_phys\n  end subroutine VarCompatibility_ccpp_initialize_constituents\n\n  function VarCompatibility_constituents_array() result(ptr)\n    real(kind=kind_phys), pointer :: ptr(:, :, :)\n    ptr => lc_constituent_array\n  end function VarCompatibility_constituents_array\n\n  subroutine VarCompatibility_const_get_index(std_name, index, errflg, errmsg)\n    character(len=*), intent(in) :: std_name\n    integer, intent(out) :: index\n    integer, intent(out) :: errflg\n    character(len=512), intent(out) :: errmsg\n    integer :: lc_i\n    errflg = 0\n    errmsg = ''\n    index = -1\n    if (.not. allocated(lc_all_constituents)) then\n      errflg = 1\n      errmsg = 'const_get_index: constituents not registered'\n      return\n    end if\n    do lc_i = 1, size(lc_all_constituents)\n      if (trim(lc_all_constituents(lc_i)%std_name) == trim(std_name)) then\n        index = lc_i\n        return\n      end if\n    end do\n    errflg = 1\n    write(errmsg, '(3a)') 'const_get_index: constituent ', trim(std_name), ' not found'\n  end subroutine VarCompatibility_const_get_index\n\n  function VarCompatibility_model_const_properties() result(ptr)\n    type(ccpp_constituent_prop_ptr_t), pointer :: ptr(:)\n    ptr => lc_const_props\n  end function VarCompatibility_model_const_properties", public_names = ["VarCompatibility_ccpp_is_scheme_constituent", "VarCompatibility_ccpp_deallocate_dynamic_constituents", "VarCompatibility_ccpp_register_constituents", "VarCompatibility_ccpp_number_constituents", "VarCompatibility_ccpp_initialize_constituents", "VarCompatibility_constituents_array", "VarCompatibility_const_get_index", "VarCompatibility_model_const_properties"]}> : () -> ()
// CHECK-LABEL:     func.func private @var_compatibility_suite_suite_register() -> (memref<i32>, memref<512xi8>) attributes {module = "var_compatibility_suite_cap"}
// CHECK-LABEL:     func.func private @var_compatibility_suite_suite_initialize(memref<i32>) -> (memref<512xi8>, memref<i32>) attributes {module = "var_compatibility_suite_cap"}
// CHECK-LABEL:     func.func private @var_compatibility_suite_suite_finalize() -> (memref<i32>, memref<512xi8>) attributes {module = "var_compatibility_suite_cap"}
// CHECK-LABEL:     func.func private @var_compatibility_suite_suite_timestep_initial() -> (memref<i32>, memref<512xi8>) attributes {module = "var_compatibility_suite_cap"}
// CHECK-LABEL:     func.func private @var_compatibility_suite_suite_timestep_final() -> (memref<i32>, memref<512xi8>) attributes {module = "var_compatibility_suite_cap"}
// CHECK-LABEL:     func.func private @var_compatibility_suite_suite_radiation(memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i1>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<?x!ccpp_utils.derived_type<"ty_rad_lw">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>) -> (memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) attributes {module = "var_compatibility_suite_cap"}
// CHECK:         }
// CHECK-LABEL:   builtin.module @ccpp_kinds {
// CHECK:           "ccpp_utils.kind_def"() <{kind_name = "kind_phys", kind_value = "REAL64"}> : () -> ()
// CHECK-NEXT:    }
// CHECK-NEXT:  }
