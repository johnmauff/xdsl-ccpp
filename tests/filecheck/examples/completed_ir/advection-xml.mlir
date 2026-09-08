// Test the completed IR for the advection XML frontend.
// Exercises: 3-D array types (memref<?x?x?x...>), five distinct schemes,
// apply_constituent_tendencies deduplicated to one call despite appearing
// twice in the suite XML, host-derived arguments threaded through caps, and
// cld_shadow -- a scheme reusing local names ("cld_ice_array", "ncols")
// already used elsewhere in the group cap for unrelated standard_names,
// each correctly renamed to avoid a module-scope declaration collision.
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/advection/cld_suite.xml --scheme-files examples/advection/const_indices.meta,examples/advection/cld_liq.meta,examples/advection/cld_ice.meta,examples/advection/apply_constituent_tendencies.meta,examples/advection/cld_shadow.meta --host-files examples/advection/test_host_data.meta,examples/advection/test_host.meta,examples/advection/test_host_mod.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p generate-meta-cap,generate-meta-kinds,generate-host-match,generate-arg-ownership,generate-suite-cap,generate-ccpp-cap,generate-cpp-cap,generate-kinds,strip-ccpp | python3 -m filecheck %s

// --- Suite cap module ---

// CHECK:       builtin.module {
// CHECK-LABEL:   builtin.module @cld_suite_cap {
// CHECK:           "llvm.mlir.global"() <{global_type = !llvm.array<16 x i8>, sym_name = "ccpp_suite_state", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, value = "uninitialized"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<16 x i8>, sym_name = "const_in_time_step", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "in_time_step"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<16 x i8>, sym_name = "const_initialized", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "initialized"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<16 x i8>, sym_name = "const_uninitialized", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "uninitialized"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "ncols", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "pver", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-LABEL:     func.func private @ccpp_constituent_indices() -> () attributes {module = "ccpp_scheme_utils"}
// CHECK:           "ccpp_utils.module_var"() <{var_name = "cld_liq_array", base_type = "real", rank = 2 : i64, kind = "kind_phys"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "tcld", base_type = "real", rank = 0 : i64, kind = "kind_phys"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "cld_ice_cld_ice_array", base_type = "real", rank = 2 : i64, kind = "kind_phys"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "cld_shadow_cld_ice_array", base_type = "real", rank = 2 : i64, kind = "kind_phys"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "cld_shadow_ncols", base_type = "real", rank = 1 : i64, kind = "kind_phys"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_const_indices", base_type = "integer", rank = 1 : i64, fixed_dim = 2 : i64, init_value = "[1, 2]"}> : () -> ()
// CHECK-LABEL:     func.func public @cld_suite_register(%dyn_const__alloc : memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>, %dyn_const_ice__alloc : memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %1 = arith.constant 0 : i32
// CHECK-NEXT:        %2 = arith.cmpi eq, %3, %1 : i32
// CHECK-NEXT:        %3 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%dyn_const__alloc, %errmsg, %errflg) <{callee = "cld_liq_register", operand_names = ["dyn_const", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %4 = arith.constant 0 : i32
// CHECK-NEXT:        %5 = arith.cmpi eq, %6, %4 : i32
// CHECK-NEXT:        %6 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %5 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%dyn_const_ice__alloc, %errmsg, %errflg) <{callee = "cld_ice_register", operand_names = ["dyn_const_ice", "errmsg", "errcode"], result_names = [], overrides = {}}> : (memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @cld_suite_initialize() -> (memref<i32>, memref<512xi8>) {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %ncols = "ccpp_utils.host_var_ref"() <{var_name = "ncols", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:        %pver = "ccpp_utils.host_var_ref"() <{var_name = "pver", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ncols, %pver) <{var_name = "cld_liq_array", kind_name = "kind_phys", needs_device_residency = true}> : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ncols, %pver) <{var_name = "cld_ice_cld_ice_array", kind_name = "kind_phys", needs_device_residency = true}> : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ncols, %pver) <{var_name = "cld_shadow_cld_ice_array", kind_name = "kind_phys"}> : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ncols) <{var_name = "cld_shadow_ncols", kind_name = "kind_phys"}> : (memref<i32>) -> ()
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_uninitialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        %4 = "llvm.load"(%3) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %5 = "ccpp_utils.strcmp"(%2, %4) <{length = 13 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %6 = arith.constant true
// CHECK-NEXT:        %7 = arith.xori %5, %6 : i1
// CHECK-NEXT:        scf.if %7 {
// CHECK-NEXT:          %8 = "ccpp_utils.trim"(%4) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in cld_suite_initialize"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %11 = "llvm.load"(%10) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %12 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%11, %12) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @cld_suite_finalize() -> (memref<i32>, memref<512xi8>) {
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
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in cld_suite_finalize"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = "llvm.mlir.addressof"() <{global_name = @const_uninitialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %11 = "llvm.load"(%10) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %12 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%11, %12) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        %13 = "ccpp_utils.host_var_ref"() <{var_name = "cld_ice_cld_ice_array", module_name = ""}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        "ccpp_utils.acc_exit_data"(%13) {operandSegmentSizes = array<i32: 0, 1>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> ()
// CHECK-NEXT:        %14 = "ccpp_utils.host_var_ref"() <{var_name = "cld_liq_array", module_name = ""}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        "ccpp_utils.acc_exit_data"(%14) {operandSegmentSizes = array<i32: 0, 1>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @cld_suite_init_physics(%const_std_name : memref<32xi8>, %num_consts : memref<i32>, %test_stdname_array__in : memref<?x32xi8>, %const_inds : memref<?xi32>, %tfreeze : memref<!ccpp_utils.real_kind<"kind_phys">>) -> (memref<i32>, memref<512xi8>, memref<i32>) {
// CHECK:             "ccpp_utils.constituent_index_lookup"() <{std_names = ["cloud_liquid_dry_mixing_ratio", "cloud_ice_dry_mixing_ratio"], err_var_name = "errflg"}> : () -> ()
// CHECK-NEXT:        %const_index = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %cld_liq_array = "ccpp_utils.host_var_ref"() <{var_name = "cld_liq_array", module_name = ""}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %ncols = "ccpp_utils.host_var_ref"() <{var_name = "ncols", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:        %pver = "ccpp_utils.host_var_ref"() <{var_name = "pver", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:        %tcld = "ccpp_utils.host_var_ref"() <{var_name = "tcld", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %cld_ice_cld_ice_array = "ccpp_utils.host_var_ref"() <{var_name = "cld_ice_cld_ice_array", module_name = ""}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ncols, %pver) <{var_name = "cld_liq_array", kind_name = "kind_phys", needs_device_residency = true}> : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ncols, %pver) <{var_name = "cld_ice_cld_ice_array", kind_name = "kind_phys", init_value = "0.0_kind_phys", needs_device_residency = true}> : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ncols, %pver) <{var_name = "cld_shadow_cld_ice_array", kind_name = "kind_phys"}> : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ncols) <{var_name = "cld_shadow_ncols", kind_name = "kind_phys"}> : (memref<i32>) -> ()
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        %4 = "llvm.load"(%3) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %5 = "ccpp_utils.strcmp"(%2, %4) <{length = 11 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %6 = arith.constant true
// CHECK-NEXT:        %7 = arith.xori %5, %6 : i1
// CHECK-NEXT:        scf.if %7 {
// CHECK-NEXT:          %8 = "ccpp_utils.trim"(%4) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in cld_suite_init_physics"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = arith.constant 0 : i32
// CHECK-NEXT:        %11 = arith.cmpi eq, %12, %10 : i32
// CHECK-NEXT:        %12 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %11 {
// CHECK-NEXT:          %13 = builtin.unrealized_conversion_cast %const_std_name : memref<32xi8> to memref<512xi8>
// CHECK-NEXT:          %14 = builtin.unrealized_conversion_cast %test_stdname_array__in : memref<?x32xi8> to memref<?x512xi8>
// CHECK-NEXT:          "ccpp_utils.kw_call"(%13, %num_consts, %14, %const_index, %const_inds, %errmsg, %errflg) <{callee = "const_indices_init", operand_names = ["const_std_name", "num_consts", "test_stdname_array", "const_index", "const_inds", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<512xi8>, memref<i32>, memref<?x512xi8>, memref<i32>, memref<?xi32>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %15 = arith.constant 0 : i32
// CHECK-NEXT:        %16 = arith.cmpi eq, %17, %15 : i32
// CHECK-NEXT:        %17 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %16 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%tfreeze, %cld_liq_array, %tcld, %errmsg, %errflg) <{callee = "cld_liq_init", operand_names = ["tfreeze", "cld_liq_array", "tcld", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %18 = arith.constant 0 : i32
// CHECK-NEXT:        %19 = arith.cmpi eq, %20, %18 : i32
// CHECK-NEXT:        %20 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %19 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%tfreeze, %cld_ice_cld_ice_array, %errmsg, %errflg) <{callee = "cld_ice_init", operand_names = ["tfreeze", "cld_ice_array", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %const_index, %errmsg, %errflg : memref<i32>, memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @cld_suite_physics(%const_std_name : memref<32xi8>, %num_consts : memref<i32>, %test_stdname_array__in : memref<?x32xi8>, %const_inds : memref<?xi32>, %ncol : memref<i32>, %timestep : memref<!ccpp_utils.real_kind<"kind_phys">>, %temp : memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, %qv : memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, %ps__in : memref<?x!ccpp_utils.real_kind<"kind_phys">>, %cld_liq_tend : memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, %const_tend : memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, %const : memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>) -> (memref<i32>, memref<512xi8>, memref<i32>) {
// CHECK:             %const_index = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %tcld = "ccpp_utils.host_var_ref"() <{var_name = "tcld", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %cld_ice_cld_ice_array = "ccpp_utils.host_var_ref"() <{var_name = "cld_ice_cld_ice_array", module_name = ""}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %cld_shadow_cld_ice_array = "ccpp_utils.host_var_ref"() <{var_name = "cld_shadow_cld_ice_array", module_name = ""}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %cld_shadow_ncols = "ccpp_utils.host_var_ref"() <{var_name = "cld_shadow_ncols", module_name = ""}> : () -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_in_time_step}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        %4 = "llvm.load"(%3) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %5 = "ccpp_utils.strcmp"(%2, %4) <{length = 12 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %6 = arith.constant true
// CHECK-NEXT:        %7 = arith.xori %5, %6 : i1
// CHECK-NEXT:        scf.if %7 {
// CHECK-NEXT:          %8 = "ccpp_utils.trim"(%4) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in cld_suite_physics"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        "ccpp_utils.constituent_sync"() <{var_name = "cld_liq_array", q_name = "const", ncol_name = "ncol", constituent_idx = 1 : i32, direction = "extract"}> : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_sync"() <{var_name = "cld_ice_cld_ice_array", q_name = "const", ncol_name = "ncol", constituent_idx = 2 : i32, direction = "extract"}> : () -> ()
// CHECK-NEXT:        %10 = arith.constant 0 : i32
// CHECK-NEXT:        %11 = arith.cmpi eq, %12, %10 : i32
// CHECK-NEXT:        %12 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %11 {
// CHECK-NEXT:          %13 = builtin.unrealized_conversion_cast %const_std_name : memref<32xi8> to memref<512xi8>
// CHECK-NEXT:          %14 = builtin.unrealized_conversion_cast %test_stdname_array__in : memref<?x32xi8> to memref<?x512xi8>
// CHECK-NEXT:          "ccpp_utils.kw_call"(%13, %num_consts, %14, %const_index, %const_inds, %errmsg, %errflg) <{callee = "const_indices_run", operand_names = ["const_std_name", "num_consts", "test_stdname_array", "const_index", "const_inds", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<512xi8>, memref<i32>, memref<?x512xi8>, memref<i32>, memref<?xi32>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %15 = arith.constant 0 : i32
// CHECK-NEXT:        %16 = arith.cmpi eq, %17, %15 : i32
// CHECK-NEXT:        %17 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %16 {
// CHECK-NEXT:          %ps_unit_conv = "ccpp_utils.unit_convert"(%ps__in) <{to_scheme_expr = "* 0.01"}> : (memref<?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          "ccpp_utils.kw_call"(%ncol, %timestep, %tcld, %temp, %qv, %ps_unit_conv, %cld_liq_tend, %errmsg, %errflg) <{callee = "cld_liq_run", operand_names = ["ncol", "timestep", "tcld", "temp", "qv", "ps", "cld_liq_tend", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %18 = arith.constant 0 : i32
// CHECK-NEXT:        %19 = arith.cmpi eq, %20, %18 : i32
// CHECK-NEXT:        %20 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %19 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%ncol, %timestep, %temp, %qv, %ps__in, %cld_ice_cld_ice_array, %errmsg, %errflg) <{callee = "cld_ice_run", operand_names = ["ncol", "timestep", "temp", "qv", "ps", "cld_ice_array", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %21 = arith.constant 0 : i32
// CHECK-NEXT:        %22 = arith.cmpi eq, %23, %21 : i32
// CHECK-NEXT:        %23 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %22 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%ncol, %timestep, %cld_shadow_cld_ice_array, %cld_shadow_ncols, %errmsg, %errflg) <{callee = "cld_shadow_run", operand_names = ["ncol", "timestep", "cld_ice_array", "ncols", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        "ccpp_utils.constituent_sync"() <{var_name = "cld_liq_array", q_name = "const", ncol_name = "ncol", constituent_idx = 1 : i32, direction = "writeback"}> : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_sync"() <{var_name = "cld_ice_cld_ice_array", q_name = "const", ncol_name = "ncol", constituent_idx = 2 : i32, direction = "writeback"}> : () -> ()
// CHECK-NEXT:        %24 = arith.constant 0 : i32
// CHECK-NEXT:        %25 = arith.cmpi eq, %26, %24 : i32
// CHECK-NEXT:        %26 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %25 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%const_tend, %const, %errflg, %errmsg) <{callee = "apply_constituent_tendencies_run", operand_names = ["const_tend", "const", "errcode", "errmsg"], result_names = [], overrides = {}}> : (memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<512xi8>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %27 = arith.constant 0 : i32
// CHECK-NEXT:        %28 = arith.cmpi eq, %29, %27 : i32
// CHECK-NEXT:        %29 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %28 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%const_tend, %const, %errflg, %errmsg) <{callee = "apply_constituent_tendencies_run", operand_names = ["const_tend", "const", "errcode", "errmsg"], result_names = [], overrides = {}}> : (memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<512xi8>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        "ccpp_utils.constituent_sync"() <{var_name = "cld_liq_array", q_name = "const", ncol_name = "ncol", constituent_idx = 1 : i32, direction = "extract"}> : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_sync"() <{var_name = "cld_ice_cld_ice_array", q_name = "const", ncol_name = "ncol", constituent_idx = 2 : i32, direction = "extract"}> : () -> ()
// CHECK-NEXT:        func.return %const_index, %errmsg, %errflg : memref<i32>, memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @cld_suite_timestep_init_physics() -> (memref<i32>, memref<512xi8>) {
// CHECK:             "ccpp_utils.constituent_index_lookup"() <{std_names = ["cloud_liquid_dry_mixing_ratio", "cloud_ice_dry_mixing_ratio"], err_var_name = "errflg"}> : () -> ()
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
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
// CHECK-LABEL:     func.func public @cld_suite_timestep_final_physics() -> (memref<i32>, memref<512xi8>) {
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
// CHECK-LABEL:     func.func public @cld_suite_final_physics() -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
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
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in cld_suite_final_physics"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = arith.constant 0 : i32
// CHECK-NEXT:        %11 = arith.cmpi eq, %12, %10 : i32
// CHECK-NEXT:        %12 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %11 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%errmsg, %errflg) <{callee = "cld_ice_final", operand_names = ["errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func private @cld_liq_register(memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>, memref<512xi8>, memref<i32>) -> () attributes {module = "cld_liq"}
// CHECK-LABEL:     func.func private @cld_ice_register(memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>, memref<512xi8>, memref<i32>) -> () attributes {module = "cld_ice"}
// CHECK-LABEL:     func.func private @const_indices_init(memref<512xi8>, memref<i32>, memref<?x512xi8>, memref<i32>, memref<?xi32>, memref<512xi8>, memref<i32>) -> () attributes {module = "const_indices"}
// CHECK-LABEL:     func.func private @cld_liq_init(memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "cld_liq"}
// CHECK-LABEL:     func.func private @cld_ice_init(memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "cld_ice"}
// CHECK-LABEL:     func.func private @const_indices_run(memref<512xi8>, memref<i32>, memref<?x512xi8>, memref<i32>, memref<?xi32>, memref<512xi8>, memref<i32>) -> () attributes {module = "const_indices"}
// CHECK-LABEL:     func.func private @cld_liq_run(memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "cld_liq"}
// CHECK-LABEL:     func.func private @cld_ice_run(memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "cld_ice"}
// CHECK-LABEL:     func.func private @cld_shadow_run(memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "cld_shadow"}
// CHECK-LABEL:     func.func private @apply_constituent_tendencies_run(memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<512xi8>) -> () attributes {module = "apply_constituent_tendencies"}
// CHECK-LABEL:     func.func private @cld_ice_final(memref<512xi8>, memref<i32>) -> () attributes {module = "cld_ice"}
// CHECK:         }
// CHECK-LABEL:   builtin.module @Cld_ccpp_cap {
// CHECK:           "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "ccpp_constituent_properties_t", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "ccpp_constituent_prop_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "const_std_name", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_data"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "num_consts", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_data"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "std_name_array", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_data"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "const_inds", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_data"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "ncols", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "dt", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "phys_state", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "index_qv", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "pver", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "ncnst", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "const_index", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_data"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "tfreeze", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<9 x i8>, sym_name = "str_cld_suite", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "cld_suite"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<7 x i8>, sym_name = "str_physics", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "physics"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "ccpp_constituent_prop_ptr_t", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "ccpp_constituent_prop_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "ccpp_model_constituents_t", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "ccpp_constituent_prop_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<0 x i8>, sym_name = "physics_state", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_data"} : () -> ()
// CHECK-LABEL:     func.func public @ccpp_register(%suite_name : memref<?xi8>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_dyn_const"}> : () -> memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>
// CHECK-NEXT:        %1 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_dyn_const_ice"}> : () -> memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>
// CHECK-NEXT:        %2 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %2, %errflg[] : memref<i32>
// CHECK-NEXT:        %3 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %4 = "ccpp_utils.strcmp"(%3) <{literal = "cld_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %4 {
// CHECK-NEXT:          %5, %6 = func.call @cld_suite_register(%0, %1) : (memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>, memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>) -> (memref<512xi8>, memref<i32>)
// CHECK-NEXT:          "memref.copy"(%5, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:          "memref.copy"(%6, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %3) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %7 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %7, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_init(%suite_name : memref<?xi8>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "cld_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3, %4 = func.call @cld_suite_initialize() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:          "memref.copy"(%3, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          "memref.copy"(%4, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %5 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %5, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_final(%suite_name : memref<?xi8>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "cld_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3, %4 = func.call @cld_suite_finalize() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:          "memref.copy"(%3, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          "memref.copy"(%4, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %5 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %5, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %6 = "ccpp_utils.host_var_ref"() <{var_name = "lc_const_tend", module_name = ""}> : () -> memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        "ccpp_utils.acc_exit_data"(%6) {operandSegmentSizes = array<i32: 0, 1>} : (memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>) -> ()
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_physics_run(%suite_name : memref<?xi8>, %suite_part : memref<?xi8>, %col_start : memref<i32>, %col_end : memref<i32>, %errmsg : memref<512xi8>, %errflg : memref<i32>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "cld_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:          %4 = "ccpp_utils.host_var_ref"() <{var_name = "const_std_name", module_name = "test_host_data"}> : () -> memref<32xi8>
// CHECK-NEXT:          %5 = "ccpp_utils.host_var_ref"() <{var_name = "num_consts", module_name = "test_host_data"}> : () -> memref<i32>
// CHECK-NEXT:          %6 = "ccpp_utils.host_var_ref"() <{var_name = "std_name_array", module_name = "test_host_data"}> : () -> memref<?x32xi8>
// CHECK-NEXT:          %7 = "ccpp_utils.host_var_ref"() <{var_name = "const_inds", module_name = "test_host_data"}> : () -> memref<?xi32>
// CHECK-NEXT:          %ncol = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:          %8 = memref.load %col_start[] : memref<i32>
// CHECK-NEXT:          %9 = memref.load %col_end[] : memref<i32>
// CHECK-NEXT:          %10 = arith.subi %9, %8 : i32
// CHECK-NEXT:          %11 = arith.constant 1 : i32
// CHECK-NEXT:          %12 = arith.addi %10, %11 : i32
// CHECK-NEXT:          memref.store %12, %ncol[] : memref<i32>
// CHECK-NEXT:          %13 = "ccpp_utils.host_var_ref"() <{var_name = "dt", module_name = "test_host_mod"}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %14 = "ccpp_utils.host_var_ref"() <{var_name = "phys_state", module_name = "test_host_mod"}> {member_name = "Temp"} : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %15 = "ccpp_utils.host_var_ref"() <{var_name = "phys_state", module_name = "test_host_mod"}> {member_name = "q(:, :, index_qv)"} : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %16 = "ccpp_utils.host_var_ref"() <{var_name = "phys_state", module_name = "test_host_mod"}> {member_name = "ps"} : () -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %17 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_cld_liq_tend"}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %18 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_const_tend"}> : () -> memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %19 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_constituent_array"}> : () -> memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %20 = arith.constant 1 : i32
// CHECK-NEXT:          %21 = "ccpp_utils.host_var_ref"() <{var_name = "pver", module_name = "test_host_mod"}> : () -> i32
// CHECK-NEXT:          %22 = "ccpp_utils.host_var_ref"() <{var_name = "ncnst", module_name = "test_host_mod"}> : () -> i32
// CHECK-NEXT:          %23 = "ccpp_utils.array_section"(%14, %col_start, %20, %col_end, %21) {operandSegmentSizes = array<i32: 1, 2, 2>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, i32) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %24 = "ccpp_utils.array_section"(%15, %col_start, %20, %20, %col_end, %21, %22) {operandSegmentSizes = array<i32: 1, 3, 3>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, i32, memref<i32>, i32, i32) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %25 = "ccpp_utils.array_section"(%16, %col_start, %col_end) {operandSegmentSizes = array<i32: 1, 1, 1>} : (memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>) -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %26 = "ccpp_utils.array_section"(%17, %col_start, %20, %col_end, %21) {operandSegmentSizes = array<i32: 1, 2, 2>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, i32) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %27 = "ccpp_utils.strcmp"(%3) <{literal = "physics"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %27 {
// CHECK-NEXT:            %28 = "ccpp_utils.host_var_ref"() <{var_name = "const_index", module_name = "test_host_data"}> : () -> memref<i32>
// CHECK-NEXT:            %29, %30, %31 = func.call @cld_suite_physics(%4, %5, %6, %7, %ncol, %13, %23, %24, %25, %26, %18, %19) : (memref<32xi8>, memref<i32>, memref<?x32xi8>, memref<?xi32>, memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>) -> (memref<i32>, memref<512xi8>, memref<i32>)
// CHECK-NEXT:            "memref.copy"(%29, %28) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:            "memref.copy"(%30, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:            "memref.copy"(%31, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %3) <{prefix = "No suite part named ", suffix = " found in suite cld_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %32 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %32, %errflg[] : memref<i32>
// CHECK-NEXT:          }
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %33 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %33, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_physics_timestep_init(%suite_name : memref<?xi8>, %suite_part : memref<?xi8>, %col_start : memref<i32>, %col_end : memref<i32>, %errmsg : memref<512xi8>, %errflg : memref<i32>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "cld_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:          %4 = "ccpp_utils.strcmp"(%3) <{literal = "physics"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %4 {
// CHECK-NEXT:            %5, %6 = func.call @cld_suite_timestep_init_physics() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:            "memref.copy"(%5, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:            "memref.copy"(%6, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %3) <{prefix = "No suite part named ", suffix = " found in suite cld_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
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
// CHECK-LABEL:     func.func public @ccpp_physics_timestep_final(%suite_name : memref<?xi8>, %suite_part : memref<?xi8>, %col_start : memref<i32>, %col_end : memref<i32>, %errmsg : memref<512xi8>, %errflg : memref<i32>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "cld_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:          %4 = "ccpp_utils.strcmp"(%3) <{literal = "physics"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %4 {
// CHECK-NEXT:            %5, %6 = func.call @cld_suite_timestep_final_physics() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:            "memref.copy"(%5, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:            "memref.copy"(%6, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %3) <{prefix = "No suite part named ", suffix = " found in suite cld_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
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
// CHECK-LABEL:     func.func public @ccpp_physics_init(%suite_name : memref<?xi8>, %suite_part : memref<?xi8>, %col_start : memref<i32>, %col_end : memref<i32>, %errmsg : memref<512xi8>, %errflg : memref<i32>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "cld_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:          %4 = "ccpp_utils.host_var_ref"() <{var_name = "const_std_name", module_name = "test_host_data"}> : () -> memref<32xi8>
// CHECK-NEXT:          %5 = "ccpp_utils.host_var_ref"() <{var_name = "num_consts", module_name = "test_host_data"}> : () -> memref<i32>
// CHECK-NEXT:          %6 = "ccpp_utils.host_var_ref"() <{var_name = "std_name_array", module_name = "test_host_data"}> : () -> memref<?x32xi8>
// CHECK-NEXT:          %7 = "ccpp_utils.host_var_ref"() <{var_name = "const_inds", module_name = "test_host_data"}> : () -> memref<?xi32>
// CHECK-NEXT:          %8 = "ccpp_utils.host_var_ref"() <{var_name = "tfreeze", module_name = "test_host_mod"}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %9 = "ccpp_utils.strcmp"(%3) <{literal = "physics"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %9 {
// CHECK-NEXT:            %10 = "ccpp_utils.host_var_ref"() <{var_name = "const_index", module_name = "test_host_data"}> : () -> memref<i32>
// CHECK-NEXT:            %11, %12, %13 = func.call @cld_suite_init_physics(%4, %5, %6, %7, %8) : (memref<32xi8>, memref<i32>, memref<?x32xi8>, memref<?xi32>, memref<!ccpp_utils.real_kind<"kind_phys">>) -> (memref<i32>, memref<512xi8>, memref<i32>)
// CHECK-NEXT:            "memref.copy"(%11, %10) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:            "memref.copy"(%12, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:            "memref.copy"(%13, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %3) <{prefix = "No suite part named ", suffix = " found in suite cld_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %14 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %14, %errflg[] : memref<i32>
// CHECK-NEXT:          }
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %15 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %15, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_physics_final(%suite_name : memref<?xi8>, %suite_part : memref<?xi8>, %col_start : memref<i32>, %col_end : memref<i32>, %errmsg : memref<512xi8>, %errflg : memref<i32>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "cld_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:          %4 = "ccpp_utils.strcmp"(%3) <{literal = "physics"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %4 {
// CHECK-NEXT:            %5, %6 = func.call @cld_suite_final_physics() : () -> (memref<512xi8>, memref<i32>)
// CHECK-NEXT:            "memref.copy"(%5, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:            "memref.copy"(%6, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %3) <{prefix = "No suite part named ", suffix = " found in suite cld_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
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
// CHECK:             %0 = arith.constant 9 : index
// CHECK-NEXT:        %1 = memref.alloc(%0) : memref<?xi8>
// CHECK-NEXT:        %2 = "llvm.mlir.addressof"() <{global_name = @str_cld_suite}> : () -> !llvm.ptr
// CHECK-NEXT:        %3 = "llvm.load"(%2) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<9 x i8>
// CHECK-NEXT:        "ccpp_utils.set_string"(%1, %3) : (memref<?xi8>, !llvm.array<9 x i8>) -> ()
// CHECK-NEXT:        memref.store %1, %suites[] : memref<memref<?xi8>>
// CHECK-NEXT:        func.return
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_physics_suite_part_list(%suite_name : memref<?xi8>, %part_list : memref<memref<?xi8>>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "cld_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = arith.constant 7 : index
// CHECK-NEXT:          %4 = memref.alloc(%3) : memref<?xi8>
// CHECK-NEXT:          %5 = "llvm.mlir.addressof"() <{global_name = @str_physics}> : () -> !llvm.ptr
// CHECK-NEXT:          %6 = "llvm.load"(%5) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<7 x i8>
// CHECK-NEXT:          "ccpp_utils.set_string"(%4, %6) : (memref<?xi8>, !llvm.array<7 x i8>) -> ()
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
// CHECK-NEXT:          "ccpp_utils.raw_fortran_lines"() <{lines = "errmsg = ''\nerrflg = 0\ndo_input = .true.\ndo_output = .true.\nif (present(input_vars)) do_input = input_vars\nif (present(output_vars)) do_output = output_vars\nif (trim(suite_name) .eq. 'cld_suite') then\n  if (do_input .and. .not. do_output) then\n    allocate(var_list(12))\n    var_list(1) = 'banana_array_dim                    '\n    var_list(2) = 'ccpp_constituent_tendencies         '\n    var_list(3) = 'ccpp_constituents                   '\n    var_list(4) = 'cloud_ice_dry_mixing_ratio          '\n    var_list(5) = 'cloud_liquid_dry_mixing_ratio       '\n    var_list(6) = 'number_of_ccpp_constituents         '\n    var_list(7) = 'surface_air_pressure                '\n    var_list(8) = 'temperature                         '\n    var_list(9) = 'tendency_of_cloud_liquid_dry_mixing_ratio'\n    var_list(10) = 'time_step_for_physics               '\n    var_list(11) = 'water_temperature_at_freezing       '\n    var_list(12) = 'water_vapor_specific_humidity       '\n  else if (.not. do_input .and. do_output) then\n    allocate(var_list(13))\n    var_list(1) = 'ccpp_constituent_tendencies         '\n    var_list(2) = 'ccpp_constituents                   '\n    var_list(3) = 'ccpp_error_code                     '\n    var_list(4) = 'ccpp_error_message                  '\n    var_list(5) = 'cloud_ice_dry_mixing_ratio          '\n    var_list(6) = 'cloud_liquid_dry_mixing_ratio       '\n    var_list(7) = 'dynamic_constituents_for_cld_ice    '\n    var_list(8) = 'dynamic_constituents_for_cld_liq    '\n    var_list(9) = 'temperature                         '\n    var_list(10) = 'tendency_of_cloud_liquid_dry_mixing_ratio'\n    var_list(11) = 'test_banana_constituent_index       '\n    var_list(12) = 'test_banana_constituent_indices     '\n    var_list(13) = 'water_vapor_specific_humidity       '\n  else\n    allocate(var_list(18))\n    var_list(1) = 'banana_array_dim                    '\n    var_list(2) = 'ccpp_constituent_tendencies         '\n    var_list(3) = 'ccpp_constituents                   '\n    var_list(4) = 'ccpp_error_code                     '\n    var_list(5) = 'ccpp_error_message                  '\n    var_list(6) = 'cloud_ice_dry_mixing_ratio          '\n    var_list(7) = 'cloud_liquid_dry_mixing_ratio       '\n    var_list(8) = 'dynamic_constituents_for_cld_ice    '\n    var_list(9) = 'dynamic_constituents_for_cld_liq    '\n    var_list(10) = 'number_of_ccpp_constituents         '\n    var_list(11) = 'surface_air_pressure                '\n    var_list(12) = 'temperature                         '\n    var_list(13) = 'tendency_of_cloud_liquid_dry_mixing_ratio'\n    var_list(14) = 'test_banana_constituent_index       '\n    var_list(15) = 'test_banana_constituent_indices     '\n    var_list(16) = 'time_step_for_physics               '\n    var_list(17) = 'water_temperature_at_freezing       '\n    var_list(18) = 'water_vapor_specific_humidity       '\n  end if\nelse\n  write(errmsg, '(3a)') \"No suite named \", trim(suite_name), \" found\"\n  errflg = 1\nend if"}> : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "cam_constituents_obj", base_type = "type", rank = 0 : i64, ddt_name = "ccpp_model_constituents_t", is_target = true}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_dyn_const", base_type = "type", rank = 1 : i64, ddt_name = "ccpp_constituent_properties_t", is_target = true}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_dyn_const_ice", base_type = "type", rank = 1 : i64, ddt_name = "ccpp_constituent_properties_t", is_target = true}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_all_constituents", base_type = "integer", rank = 1 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_constituent_array", base_type = "real", rank = 3 : i64, kind = "kind_phys", is_pointer = true}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_const_tend", base_type = "real", rank = 3 : i64, kind = "kind_phys", is_target = true}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_const_props", base_type = "type", rank = 1 : i64, ddt_name = "ccpp_constituent_prop_ptr_t", is_target = true}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_cld_liq_tend", base_type = "real", rank = 2 : i64, kind = "kind_phys", is_pointer = true}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "cam_model_const_stdnames", base_type = "character", rank = 0 : i64, kind = "29", fixed_dim = 2 : i64, init_value = "[ character(len=29) :: 'cloud_liquid_dry_mixing_ratio', &\n      'cloud_ice_dry_mixing_ratio' ]"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "cam_model_const_indices", base_type = "integer", rank = 0 : i64, fixed_dim = 2 : i64, init_value = "-1"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.non_cam_host_constituent_api"() <{public_names = ["Cld_ccpp_is_scheme_constituent", "Cld_ccpp_deallocate_dynamic_constituents", "Cld_ccpp_register_constituents", "Cld_ccpp_number_constituents", "Cld_ccpp_initialize_constituents", "Cld_constituents_array", "Cld_const_get_index", "Cld_model_const_properties"]}> ({
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "Cld_ccpp_is_scheme_constituent", is_function = false, args = ["std_name", "is_const", "errflg", "errmsg"], use_stmts = [], arg_decls = ["character(len=*), intent(in) :: std_name", "logical, intent(out) :: is_const", "integer, intent(out) :: errflg", "character(len=512), intent(out) :: errmsg"], local_decls = ["integer :: lc_idx", "character(len=256) :: lc_std_name"]}> ({
// CHECK-NEXT:          "ccpp_utils.raw_fortran_lines"() <{lines = "errflg = 0\nerrmsg = ''\nis_const = .false.\nif (any(cam_model_const_stdnames == std_name)) then\n  is_const = .true.\n  return\nend if\nif (allocated(lc_dyn_const)) then\n  do lc_idx = 1, size(lc_dyn_const)\n    call lc_dyn_const(lc_idx)%standard_name(lc_std_name)\n    if (trim(lc_std_name) == trim(std_name)) then\n      is_const = .true.\n      return\n    end if\n  end do\nend if\nif (allocated(lc_dyn_const_ice)) then\n  do lc_idx = 1, size(lc_dyn_const_ice)\n    call lc_dyn_const_ice(lc_idx)%standard_name(lc_std_name)\n    if (trim(lc_std_name) == trim(std_name)) then\n      is_const = .true.\n      return\n    end if\n  end do\nend if"}> : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "Cld_ccpp_deallocate_dynamic_constituents", is_function = false, args = [], use_stmts = [], arg_decls = [], local_decls = []}> ({
// CHECK-NEXT:          "ccpp_utils.raw_fortran_lines"() <{lines = "if (allocated(lc_dyn_const)) deallocate(lc_dyn_const)\nif (allocated(lc_dyn_const_ice)) deallocate(lc_dyn_const_ice)\nif (allocated(lc_all_constituents)) deallocate(lc_all_constituents)\nif (allocated(lc_const_props)) deallocate(lc_const_props)\nif (associated(lc_constituent_array)) nullify(lc_constituent_array)\nif (allocated(lc_const_tend)) deallocate(lc_const_tend)\nnullify(lc_cld_liq_tend)\ncall cam_constituents_obj%reset()"}> : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "Cld_ccpp_register_constituents", is_function = false, args = ["host_constituents", "errmsg", "errcode"], use_stmts = ["use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t, ccpp_constituent_prop_ptr_t", "use ccpp_scheme_utils, only: ccpp_scheme_utils_set_constituents"], arg_decls = ["type(ccpp_constituent_properties_t), target, intent(in) :: host_constituents(:)", "character(len=512), intent(out) :: errmsg", "integer, intent(out) :: errcode"], local_decls = ["integer :: lc_i, lc_num_consts, field_ind", "type(ccpp_constituent_properties_t), pointer :: const_prop", "type(ccpp_constituent_prop_ptr_t), pointer :: lc_props_ptr(:)"]}> ({
// CHECK-NEXT:          "ccpp_utils.raw_fortran_lines"() <{lines = "errcode = 0\nerrmsg = ''\nlc_num_consts = size(host_constituents)\nif (allocated(lc_dyn_const)) lc_num_consts = lc_num_consts + size(lc_dyn_const)\nif (allocated(lc_dyn_const_ice)) lc_num_consts = lc_num_consts + size(lc_dyn_const_ice)\nlc_num_consts = lc_num_consts + 2\ncall cam_constituents_obj%initialize_table(lc_num_consts)\ndo lc_i = 1, size(host_constituents)\n  allocate(const_prop, stat=errcode)\n  if (errcode /= 0) then\n    errmsg = 'ERROR allocating const_prop'\n    return\n  end if\n  const_prop = host_constituents(lc_i)\n  call cam_constituents_obj%new_field(const_prop, errcode=errcode, errmsg=errmsg)\n  nullify(const_prop)\n  if (errcode /= 0) return\nend do\nif (allocated(lc_dyn_const)) then\n  do lc_i = 1, size(lc_dyn_const)\n    allocate(const_prop, stat=errcode)\n    if (errcode /= 0) then\n      errmsg = 'ERROR allocating const_prop'\n      return\n    end if\n    const_prop = lc_dyn_const(lc_i)\n    call cam_constituents_obj%new_field(const_prop, errcode=errcode, errmsg=errmsg)\n    nullify(const_prop)\n    if (errcode /= 0) return\n  end do\nend if\nif (allocated(lc_dyn_const_ice)) then\n  do lc_i = 1, size(lc_dyn_const_ice)\n    allocate(const_prop, stat=errcode)\n    if (errcode /= 0) then\n      errmsg = 'ERROR allocating const_prop'\n      return\n    end if\n    const_prop = lc_dyn_const_ice(lc_i)\n    call cam_constituents_obj%new_field(const_prop, errcode=errcode, errmsg=errmsg)\n    nullify(const_prop)\n    if (errcode /= 0) return\n  end do\nend if\nallocate(const_prop, stat=errcode)\nif (errcode /= 0) then\n  errmsg = 'ERROR allocating const_prop'\n  return\nend if\ncall const_prop%instantiate( &\n    std_name='cloud_liquid_dry_mixing_ratio', &\n    long_name='Cloud liquid dry mixing ratio', &\n    diag_name='cld_liq_array', units='kg kg-1', &\n    vertical_dim='vertical_layer_dimension', &\n    advected=.true., errcode=errcode, errmsg=errmsg)\nif (errcode /= 0) return\ncall cam_constituents_obj%new_field(const_prop, errcode=errcode, errmsg=errmsg)\nnullify(const_prop)\nif (errcode /= 0) return\nallocate(const_prop, stat=errcode)\nif (errcode /= 0) then\n  errmsg = 'ERROR allocating const_prop'\n  return\nend if\ncall const_prop%instantiate( &\n    std_name='cloud_ice_dry_mixing_ratio', &\n    long_name='Cloud ice dry mixing ratio', &\n    diag_name='cld_ice_array', units='kg kg-1', &\n    vertical_dim='vertical_layer_dimension', &\n    advected=.true., default_value=0.0_kind_phys, errcode=errcode, errmsg=errmsg)\nif (errcode /= 0) return\ncall cam_constituents_obj%new_field(const_prop, errcode=errcode, errmsg=errmsg)\nnullify(const_prop)\nif (errcode /= 0) return\ncall cam_constituents_obj%lock_table(errcode=errcode, errmsg=errmsg)\nif (errcode /= 0) return\nlc_props_ptr => cam_constituents_obj%constituent_props_ptr()\nif (allocated(lc_const_props)) deallocate(lc_const_props)\nallocate(lc_const_props(size(lc_props_ptr)))\nlc_const_props = lc_props_ptr\nnullify(lc_props_ptr)\ncall ccpp_scheme_utils_set_constituents(lc_const_props)\ncall cam_constituents_obj%num_constituents(lc_num_consts, errcode=errcode, errmsg=errmsg)\nif (errcode /= 0) return\nif (allocated(lc_all_constituents)) deallocate(lc_all_constituents)\nallocate(lc_all_constituents(lc_num_consts))\ndo lc_i = 1, size(cam_model_const_indices)\n  call cam_constituents_obj%const_index(field_ind, cam_model_const_stdnames(lc_i), &\n      errcode=errcode, errmsg=errmsg)\n  if (errcode /= 0) return\n  if (field_ind > 0) then\n    cam_model_const_indices(lc_i) = field_ind\n  else\n    errcode = 1\n    errmsg = 'No field index for '//trim(cam_model_const_stdnames(lc_i))\n    return\n  end if\nend do"}> : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "Cld_ccpp_number_constituents", is_function = false, args = ["num_advected", "errmsg", "errcode", "advected"], use_stmts = [], arg_decls = ["integer, intent(out) :: num_advected", "character(len=512), intent(out) :: errmsg", "integer, intent(out) :: errcode", "logical, optional, intent(in) :: advected"], local_decls = []}> ({
// CHECK-NEXT:          "ccpp_utils.raw_fortran_lines"() <{lines = "errcode = 0\nerrmsg = ''\nif (allocated(lc_all_constituents)) then\n  num_advected = size(lc_all_constituents)\nelse\n  num_advected = 0\nend if"}> : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "Cld_ccpp_initialize_constituents", is_function = false, args = ["ncols", "pver", "errflg", "errmsg"], use_stmts = [], arg_decls = ["integer, intent(in) :: ncols", "integer, intent(in) :: pver", "integer, intent(out) :: errflg", "character(len=512), intent(out) :: errmsg"], local_decls = []}> ({
// CHECK-NEXT:          "ccpp_utils.raw_fortran_lines"() <{lines = "errflg = 0\nerrmsg = ''\nif (.not. allocated(lc_all_constituents)) then\n  errflg = 1\n  errmsg = 'ccpp_initialize_constituents: register_constituents not called'\n  return\nend if\ncall cam_constituents_obj%lock_data(ncols, pver, errcode=errflg, errmsg=errmsg)\nif (errflg /= 0) return\nlc_constituent_array => cam_constituents_obj%field_data_ptr()\nif (allocated(lc_const_tend)) deallocate(lc_const_tend)\nallocate(lc_const_tend(ncols, pver, size(lc_all_constituents)))\nlc_const_tend = 0.0_kind_phys\n#ifdef USE_GPU\n!$acc enter data copyin(lc_const_tend)\n#endif\nblock\n  integer :: lc_tend_idx\n  character(len=512) :: lc_tend_errmsg\n  nullify(lc_cld_liq_tend)\n  call cam_constituents_obj%const_index(lc_tend_idx, 'cloud_liquid_dry_mixing_ratio', &\n      errcode=errflg, errmsg=lc_tend_errmsg)\n  if (errflg == 0 .and. lc_tend_idx > 0) then\n    lc_cld_liq_tend => lc_const_tend(:, :, lc_tend_idx)\n  else\n    errflg = 0\n  end if\nend block"}> : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "Cld_constituents_array", is_function = true, args = [], use_stmts = [], arg_decls = [], local_decls = [], result_name = "ptr", result_decl = "real(kind=kind_phys), pointer :: ptr(:, :, :)"}> ({
// CHECK-NEXT:          "ccpp_utils.raw_fortran_lines"() <{lines = "ptr => lc_constituent_array"}> : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "Cld_const_get_index", is_function = false, args = ["std_name", "index", "errflg", "errmsg"], use_stmts = ["use ccpp_constituent_prop_mod, only: to_lower"], arg_decls = ["character(len=*), intent(in) :: std_name", "integer, intent(out) :: index", "integer, intent(out) :: errflg", "character(len=512), intent(out) :: errmsg"], local_decls = []}> ({
// CHECK-NEXT:          "ccpp_utils.raw_fortran_lines"() <{lines = "errflg = 0\nerrmsg = ''\nindex = -1\nif (.not. allocated(lc_all_constituents)) then\n  errflg = 1\n  errmsg = 'const_get_index: constituents not registered'\n  return\nend if\ncall cam_constituents_obj%const_index(index, to_lower(std_name), &\n    errcode=errflg, errmsg=errmsg)\nif (errflg /= 0 .or. index <= 0) then\n  errflg = 1\n  write(errmsg, '(3a)') 'const_get_index: constituent ', trim(std_name), ' not found'\nend if"}> : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "Cld_model_const_properties", is_function = true, args = [], use_stmts = [], arg_decls = [], local_decls = [], result_name = "ptr", result_decl = "type(ccpp_constituent_prop_ptr_t), pointer :: ptr(:)"}> ({
// CHECK-NEXT:          "ccpp_utils.raw_fortran_lines"() <{lines = "ptr => lc_const_props"}> : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-LABEL:     func.func private @cld_suite_register(memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>, memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>) -> (memref<512xi8>, memref<i32>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_initialize() -> (memref<i32>, memref<512xi8>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_finalize() -> (memref<i32>, memref<512xi8>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_physics(memref<32xi8>, memref<i32>, memref<?x32xi8>, memref<?xi32>, memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>) -> (memref<i32>, memref<512xi8>, memref<i32>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_timestep_init_physics() -> (memref<i32>, memref<512xi8>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_timestep_final_physics() -> (memref<i32>, memref<512xi8>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_init_physics(memref<32xi8>, memref<i32>, memref<?x32xi8>, memref<?xi32>, memref<!ccpp_utils.real_kind<"kind_phys">>) -> (memref<i32>, memref<512xi8>, memref<i32>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_final_physics() -> (memref<512xi8>, memref<i32>) attributes {module = "cld_suite_cap"}
// CHECK:         }
// CHECK-LABEL:   builtin.module @ccpp_kinds {
// CHECK:           "ccpp_utils.kind_def"() <{kind_name = "kind_phys", kind_value = "REAL64", kind_module = "iso_fortran_env"}> : () -> ()
// CHECK-NEXT:    }
// CHECK-NEXT:  }
