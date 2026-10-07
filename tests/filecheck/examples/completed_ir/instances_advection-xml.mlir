// Test the completed (post-optimizer) IR for the instances_advection
// example. Exercises: the instance_number/number_of_instances multi-instance
// dispatch pattern combined with host + scheme-registered constituents --
// the only example in this repo that drives constituent_cap.py's
// multi-instance path, so the only golden pinning DerivedTypeDefOp/
// DdtComponentDeclOp's actual IR shape (the per-instance bundle type,
// test_host_lc_instance_t). Added as part of tdb-002's Stage A completion
// (2026-09-30).
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/instances_advection/cld_suite.xml --scheme-files examples/instances_advection/cld_liq.meta,examples/instances_advection/apply_constituent_tendencies.meta --host-files examples/instances_advection/data.meta,examples/instances_advection/test_host.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p generate-meta-cap,generate-meta-kinds,generate-host-match,generate-arg-ownership,generate-suite-cap,generate-ccpp-cap,generate-cpp-cap,generate-kinds,strip-ccpp | python3 -m filecheck %s

// CHECK:       builtin.module {
// CHECK-LABEL:   builtin.module @cld_suite_cap {
// CHECK:           "llvm.mlir.global"() <{global_type = !llvm.array<16 x i8>, sym_name = "ccpp_suite_state", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, value = "uninitialized"}> ({
// CHECK-NEXT:      }) {allocatable = "1"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<16 x i8>, sym_name = "const_in_time_step", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "in_time_step"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<16 x i8>, sym_name = "const_initialized", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "initialized"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<16 x i8>, sym_name = "const_uninitialized", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "uninitialized"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "ncols", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "data"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "pver", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "data"} : () -> ()
// CHECK-LABEL:     func.func private @ccpp_constituent_indices() -> () attributes {module = "ccpp_scheme_utils"}
// CHECK:           "ccpp_utils.module_var"() <{var_name = "tcld", base_type = "real", rank = 0 : i64, kind = "kind_phys"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "cld_liq_array", base_type = "real", rank = 2 : i64, kind = "kind_phys", is_pointer = true}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "cld_liq_tend", base_type = "real", rank = 2 : i64, kind = "kind_phys"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_const_indices", base_type = "integer", rank = 1 : i64, fixed_dim = 1 : i64}> ({
// CHECK-NEXT:        "ccpp_utils.array_constructor_expr"() ({
// CHECK-NEXT:          %0 = arith.constant 1 : i32
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-LABEL:     func.func public @cld_suite_register(%dyn_const__alloc : memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>, %instance : memref<i32>, %ninstances : memref<i32>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errcode = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %1 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %1, %errcode[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %2 = arith.constant 0 : i32
// CHECK-NEXT:        %3 = memref.load %errcode[] : memref<i32>
// CHECK-NEXT:        %4 = arith.cmpi eq, %3, %2 : i32
// CHECK-NEXT:        scf.if %4 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%dyn_const__alloc, %errmsg, %errcode) <{callee = "cld_liq_register", operand_names = ["dyn_const", "errmsg", "errcode"], result_names = [], overrides = {}}> : (memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errcode : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @cld_suite_initialize(%instance : memref<i32>, %ninstances : memref<i32>) -> (memref<i32>, memref<512xi8>) {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %1 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %1, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %ncols = "ccpp_utils.host_var_ref"() <{var_name = "ncols", module_name = "data"}> : () -> memref<i32>
// CHECK-NEXT:        %pver = "ccpp_utils.host_var_ref"() <{var_name = "pver", module_name = "data"}> : () -> memref<i32>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ncols, %pver) <{var_name = "cld_liq_tend", kind_name = "kind_phys"}> : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ninstances) <{var_name = "ccpp_suite_state", kind_name = "character"}> ({
// CHECK-NEXT:          "ccpp_utils.string_literal_expr"() <{text = "uninitialized"}> : () -> ()
// CHECK-NEXT:        }) : (memref<i32>) -> ()
// CHECK-NEXT:        %2 = "llvm.mlir.addressof"() <{global_name = @const_uninitialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %3 = "llvm.load"(%2) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %4 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> {ccpp_instance_ref = "instance"} : () -> !llvm.ptr
// CHECK-NEXT:        %5 = "llvm.load"(%4) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %6 = "ccpp_utils.strcmp"(%3, %5) <{length = 13 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %7 = arith.constant true
// CHECK-NEXT:        %8 = arith.xori %6, %7 : i1
// CHECK-NEXT:        scf.if %8 {
// CHECK-NEXT:          %9 = "ccpp_utils.trim"(%5) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %9) <{prefix = "Invalid initial CCPP state, '", suffix = "' in cld_suite_initialize"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %10 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %10, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %11 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %12 = "llvm.load"(%11) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %13 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> {ccpp_instance_ref = "instance"} : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%12, %13) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @cld_suite_finalize(%instance : memref<i32>, %ninstances : memref<i32>) -> (memref<i32>, memref<512xi8>) {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %1 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %1, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %tcld = "ccpp_utils.host_var_ref"() <{var_name = "tcld", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ninstances) <{var_name = "ccpp_suite_state", kind_name = "character"}> ({
// CHECK-NEXT:          "ccpp_utils.string_literal_expr"() <{text = "uninitialized"}> : () -> ()
// CHECK-NEXT:        }) : (memref<i32>) -> ()
// CHECK-NEXT:        %2 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %3 = "llvm.load"(%2) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %4 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> {ccpp_instance_ref = "instance"} : () -> !llvm.ptr
// CHECK-NEXT:        %5 = "llvm.load"(%4) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %6 = "ccpp_utils.strcmp"(%3, %5) <{length = 11 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %7 = arith.constant true
// CHECK-NEXT:        %8 = arith.xori %6, %7 : i1
// CHECK-NEXT:        scf.if %8 {
// CHECK-NEXT:          %9 = "ccpp_utils.trim"(%5) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %9) <{prefix = "Invalid initial CCPP state, '", suffix = "' in cld_suite_finalize"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %10 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %10, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %11 = "llvm.mlir.addressof"() <{global_name = @const_uninitialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %12 = "llvm.load"(%11) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %13 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> {ccpp_instance_ref = "instance"} : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%12, %13) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @cld_suite_init_physics(%tfreeze : memref<!ccpp_utils.real_kind<"kind_phys">>, %instance : memref<i32>, %ninstances : memref<i32>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             "ccpp_utils.constituent_index_lookup"() <{std_names = ["cloud_liquid_dry_mixing_ratio"], err_var_name = "errcode"}> : () -> ()
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errcode = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %1 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %1, %errcode[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %tcld = "ccpp_utils.host_var_ref"() <{var_name = "tcld", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %ncols = "ccpp_utils.host_var_ref"() <{var_name = "ncols", module_name = "data"}> : () -> memref<i32>
// CHECK-NEXT:        %pver = "ccpp_utils.host_var_ref"() <{var_name = "pver", module_name = "data"}> : () -> memref<i32>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ncols, %pver) <{var_name = "cld_liq_tend", kind_name = "kind_phys"}> : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ninstances) <{var_name = "ccpp_suite_state", kind_name = "character"}> ({
// CHECK-NEXT:          "ccpp_utils.string_literal_expr"() <{text = "uninitialized"}> : () -> ()
// CHECK-NEXT:        }) : (memref<i32>) -> ()
// CHECK-NEXT:        %2 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %3 = "llvm.load"(%2) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %4 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> {ccpp_instance_ref = "instance"} : () -> !llvm.ptr
// CHECK-NEXT:        %5 = "llvm.load"(%4) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %6 = "ccpp_utils.strcmp"(%3, %5) <{length = 11 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %7 = arith.constant true
// CHECK-NEXT:        %8 = arith.xori %6, %7 : i1
// CHECK-NEXT:        scf.if %8 {
// CHECK-NEXT:          %9 = "ccpp_utils.trim"(%5) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %9) <{prefix = "Invalid initial CCPP state, '", suffix = "' in cld_suite_init_physics"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %10 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %10, %errcode[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %11 = arith.constant 0 : i32
// CHECK-NEXT:        %12 = memref.load %errcode[] : memref<i32>
// CHECK-NEXT:        %13 = arith.cmpi eq, %12, %11 : i32
// CHECK-NEXT:        scf.if %13 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%tfreeze, %tcld, %errmsg, %errcode) <{callee = "cld_liq_init", operand_names = ["tfreeze", "tcld", "errmsg", "errcode"], result_names = [], overrides = {}}> : (memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errcode : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @cld_suite_physics(%ncol : memref<i32>, %timestep : memref<!ccpp_utils.real_kind<"kind_phys">>, %temp : memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, %qv : memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, %ps__in : memref<?x!ccpp_utils.real_kind<"kind_phys">>, %cld_liq_tend : memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, %const_tend : memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, %const : memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, %instance : memref<i32>, %ninstances : memref<i32>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errcode = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %1 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %1, %errcode[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %tcld = "ccpp_utils.host_var_ref"() <{var_name = "tcld", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %cld_liq_array = "ccpp_utils.host_var_ref"() <{var_name = "cld_liq_array", module_name = ""}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ninstances) <{var_name = "ccpp_suite_state", kind_name = "character"}> ({
// CHECK-NEXT:          "ccpp_utils.string_literal_expr"() <{text = "uninitialized"}> : () -> ()
// CHECK-NEXT:        }) : (memref<i32>) -> ()
// CHECK-NEXT:        %2 = "llvm.mlir.addressof"() <{global_name = @const_in_time_step}> : () -> !llvm.ptr
// CHECK-NEXT:        %3 = "llvm.load"(%2) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %4 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> {ccpp_instance_ref = "instance"} : () -> !llvm.ptr
// CHECK-NEXT:        %5 = "llvm.load"(%4) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %6 = "ccpp_utils.strcmp"(%3, %5) <{length = 12 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %7 = arith.constant true
// CHECK-NEXT:        %8 = arith.xori %6, %7 : i1
// CHECK-NEXT:        scf.if %8 {
// CHECK-NEXT:          %9 = "ccpp_utils.trim"(%5) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %9) <{prefix = "Invalid initial CCPP state, '", suffix = "' in cld_suite_physics"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %10 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %10, %errcode[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        "ccpp_utils.pointer_slice_assign"() <{ptr_name = "cld_liq_array", array_name = "const", index_var = "lc_const_indices(1)"}> : () -> ()
// CHECK-NEXT:        %11 = arith.constant 0 : i32
// CHECK-NEXT:        %12 = memref.load %errcode[] : memref<i32>
// CHECK-NEXT:        %13 = arith.cmpi eq, %12, %11 : i32
// CHECK-NEXT:        scf.if %13 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%ncol, %timestep, %tcld, %temp, %qv, %ps__in, %cld_liq_array, %cld_liq_tend, %errmsg, %errcode) <{callee = "cld_liq_run", operand_names = ["ncol", "timestep", "tcld", "temp", "qv", "ps", "cld_liq_array", "cld_liq_tend", "errmsg", "errcode"], result_names = [], overrides = {}}> : (memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %14 = arith.constant 0 : i32
// CHECK-NEXT:        %15 = memref.load %errcode[] : memref<i32>
// CHECK-NEXT:        %16 = arith.cmpi eq, %15, %14 : i32
// CHECK-NEXT:        scf.if %16 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%const_tend, %const, %errcode, %errmsg) <{callee = "apply_constituent_tendencies_run", operand_names = ["const_tend", "const", "errcode", "errmsg"], result_names = [], overrides = {}}> : (memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<512xi8>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        "ccpp_utils.nullify_pointer"() <{ptr_name = "cld_liq_array"}> : () -> ()
// CHECK-NEXT:        func.return %errmsg, %errcode : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @cld_suite_timestep_init_physics(%instance : memref<i32>, %ninstances : memref<i32>) -> (memref<i32>, memref<512xi8>) {
// CHECK:             "ccpp_utils.constituent_index_lookup"() <{std_names = ["cloud_liquid_dry_mixing_ratio"], err_var_name = "errflg"}> : () -> ()
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %1 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %1, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %tcld = "ccpp_utils.host_var_ref"() <{var_name = "tcld", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ninstances) <{var_name = "ccpp_suite_state", kind_name = "character"}> ({
// CHECK-NEXT:          "ccpp_utils.string_literal_expr"() <{text = "uninitialized"}> : () -> ()
// CHECK-NEXT:        }) : (memref<i32>) -> ()
// CHECK-NEXT:        %2 = "llvm.mlir.addressof"() <{global_name = @const_in_time_step}> : () -> !llvm.ptr
// CHECK-NEXT:        %3 = "llvm.load"(%2) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %4 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> {ccpp_instance_ref = "instance"} : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%3, %4) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @cld_suite_timestep_final_physics(%instance : memref<i32>, %ninstances : memref<i32>) -> (memref<i32>, memref<512xi8>) {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %1 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %1, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %tcld = "ccpp_utils.host_var_ref"() <{var_name = "tcld", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ninstances) <{var_name = "ccpp_suite_state", kind_name = "character"}> ({
// CHECK-NEXT:          "ccpp_utils.string_literal_expr"() <{text = "uninitialized"}> : () -> ()
// CHECK-NEXT:        }) : (memref<i32>) -> ()
// CHECK-NEXT:        %2 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %3 = "llvm.load"(%2) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %4 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> {ccpp_instance_ref = "instance"} : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%3, %4) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @cld_suite_final_physics(%instance : memref<i32>, %ninstances : memref<i32>) -> (memref<i32>, memref<512xi8>) {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %1 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %1, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %tcld = "ccpp_utils.host_var_ref"() <{var_name = "tcld", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ninstances) <{var_name = "ccpp_suite_state", kind_name = "character"}> ({
// CHECK-NEXT:          "ccpp_utils.string_literal_expr"() <{text = "uninitialized"}> : () -> ()
// CHECK-NEXT:        }) : (memref<i32>) -> ()
// CHECK-NEXT:        %2 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %3 = "llvm.load"(%2) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %4 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> {ccpp_instance_ref = "instance"} : () -> !llvm.ptr
// CHECK-NEXT:        %5 = "llvm.load"(%4) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %6 = "ccpp_utils.strcmp"(%3, %5) <{length = 11 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %7 = arith.constant true
// CHECK-NEXT:        %8 = arith.xori %6, %7 : i1
// CHECK-NEXT:        scf.if %8 {
// CHECK-NEXT:          %9 = "ccpp_utils.trim"(%5) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %9) <{prefix = "Invalid initial CCPP state, '", suffix = "' in cld_suite_final_physics"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %10 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %10, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func private @cld_liq_register(memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>, memref<512xi8>, memref<i32>) -> () attributes {module = "cld_liq"}
// CHECK-LABEL:     func.func private @cld_liq_init(memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "cld_liq"}
// CHECK-LABEL:     func.func private @cld_liq_run(memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "cld_liq"}
// CHECK-LABEL:     func.func private @apply_constituent_tendencies_run(memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<512xi8>) -> () attributes {module = "apply_constituent_tendencies"}
// CHECK:         }
// CHECK-LABEL:   builtin.module @Cld_ccpp_cap {
// CHECK:           "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "ccpp_constituent_properties_t", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "ccpp_constituent_prop_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "ncols", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "data"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "dt", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "data"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "phys_state", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "data"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "index_qv", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "data"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "pver", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "data"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "tfreeze", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "data"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<9 x i8>, sym_name = "str_cld_suite", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "cld_suite"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<7 x i8>, sym_name = "str_physics", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "physics"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "ccpp_constituent_prop_ptr_t", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "ccpp_constituent_prop_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "ccpp_model_constituents_t", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "ccpp_constituent_prop_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<0 x i8>, sym_name = "physics_state", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "data"} : () -> ()
// CHECK-LABEL:     func.func public @ccpp_register(%suite_name : memref<?xi8>, %instance__hostarg : memref<i32>, %ninstances__hostarg : memref<i32>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ninstances__hostarg) <{var_name = "lc_instances", kind_name = "type"}> : (memref<i32>) -> ()
// CHECK-NEXT:        %0 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_instances(instance)%lc_dyn_const"}> : () -> memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>
// CHECK-NEXT:        %1 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %1, %errflg[] : memref<i32>
// CHECK-NEXT:        %2 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %3 = "ccpp_utils.strcmp"(%2) <{literal = "cld_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %3 {
// CHECK-NEXT:          %4, %5 = func.call @cld_suite_register(%0, %instance__hostarg, %ninstances__hostarg) : (memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>, memref<i32>, memref<i32>) -> (memref<512xi8>, memref<i32>)
// CHECK-NEXT:          "memref.copy"(%4, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:          "memref.copy"(%5, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %2) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %6 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %6, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_init(%suite_name : memref<?xi8>, %instance__hostarg : memref<i32>, %ninstances__hostarg : memref<i32>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "cld_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3, %4 = func.call @cld_suite_initialize(%instance__hostarg, %ninstances__hostarg) : (memref<i32>, memref<i32>) -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:          "memref.copy"(%3, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          "memref.copy"(%4, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %5 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %5, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_final(%suite_name : memref<?xi8>, %instance__hostarg : memref<i32>, %ninstances__hostarg : memref<i32>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "cld_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3, %4 = func.call @cld_suite_finalize(%instance__hostarg, %ninstances__hostarg) : (memref<i32>, memref<i32>) -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:          "memref.copy"(%3, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          "memref.copy"(%4, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %5 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %5, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_physics_run(%suite_name : memref<?xi8>, %suite_part : memref<?xi8>, %lb : memref<i32>, %ub : memref<i32>, %instance : memref<i32>, %ninstances : memref<i32>, %errmsg : memref<512xi8>, %errflg : memref<i32>) -> (memref<512xi8>, memref<i32>) attributes {bind_c_dim_exprs = ["", "", "", "", "", "", "", ""]} {
// CHECK:             %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "cld_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:          %ncol = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:          %4 = memref.load %lb[] : memref<i32>
// CHECK-NEXT:          %5 = memref.load %ub[] : memref<i32>
// CHECK-NEXT:          %6 = arith.subi %5, %4 : i32
// CHECK-NEXT:          %7 = arith.constant 1 : i32
// CHECK-NEXT:          %8 = arith.addi %6, %7 : i32
// CHECK-NEXT:          memref.store %8, %ncol[] : memref<i32>
// CHECK-NEXT:          %9 = "ccpp_utils.host_var_ref"() <{var_name = "dt", module_name = "data"}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %10 = "ccpp_utils.host_var_ref"() <{var_name = "phys_state", module_name = "data"}> {member_name = "temp", index_expr = "instance"} : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %11 = "ccpp_utils.host_var_ref"() <{var_name = "phys_state", module_name = "data"}> {member_name = "q(:, :, index_qv)", index_expr = "instance"} : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %12 = "ccpp_utils.host_var_ref"() <{var_name = "phys_state", module_name = "data"}> {member_name = "ps", index_expr = "instance"} : () -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %13 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_instances(instance)%lc_cld_liq_tend"}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %14 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_instances(instance)%lc_const_tend"}> : () -> memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %15 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_instances(instance)%lc_constituent_array"}> : () -> memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %16 = arith.constant 1 : i32
// CHECK-NEXT:          %17 = "ccpp_utils.host_var_ref"() <{var_name = "pver", module_name = "data"}> : () -> i32
// CHECK-NEXT:          %18 = "ccpp_utils.array_section"(%10, %lb, %16, %ub, %17) {operandSegmentSizes = array<i32: 1, 2, 2>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, i32) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %19 = "ccpp_utils.array_section"(%12, %lb, %ub) {operandSegmentSizes = array<i32: 1, 1, 1>} : (memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>) -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %20 = "ccpp_utils.array_section"(%13, %lb, %16, %ub, %17) {operandSegmentSizes = array<i32: 1, 2, 2>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, i32) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %21 = "ccpp_utils.strcmp"(%3) <{literal = "physics"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %21 {
// CHECK-NEXT:            %22, %23 = func.call @cld_suite_physics(%ncol, %9, %18, %11, %19, %20, %14, %15, %instance, %ninstances) : (memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>) -> (memref<512xi8>, memref<i32>)
// CHECK-NEXT:            "memref.copy"(%22, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:            "memref.copy"(%23, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %3) <{prefix = "No suite part named ", suffix = " found in suite cld_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %24 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %24, %errflg[] : memref<i32>
// CHECK-NEXT:          }
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %25 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %25, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_physics_timestep_init(%suite_name : memref<?xi8>, %suite_part : memref<?xi8>, %lb : memref<i32>, %ub : memref<i32>, %instance : memref<i32>, %ninstances : memref<i32>, %errmsg : memref<512xi8>, %errflg : memref<i32>) -> (memref<512xi8>, memref<i32>) attributes {bind_c_dim_exprs = ["", "", "", "", "", "", "", ""]} {
// CHECK:             %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "cld_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:          %4 = "ccpp_utils.strcmp"(%3) <{literal = "physics"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %4 {
// CHECK-NEXT:            %5, %6 = func.call @cld_suite_timestep_init_physics(%instance, %ninstances) : (memref<i32>, memref<i32>) -> (memref<i32>, memref<512xi8>)
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
// CHECK-LABEL:     func.func public @ccpp_physics_timestep_final(%suite_name : memref<?xi8>, %suite_part : memref<?xi8>, %lb : memref<i32>, %ub : memref<i32>, %instance : memref<i32>, %ninstances : memref<i32>, %errmsg : memref<512xi8>, %errflg : memref<i32>) -> (memref<512xi8>, memref<i32>) attributes {bind_c_dim_exprs = ["", "", "", "", "", "", "", ""]} {
// CHECK:             %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "cld_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:          %4 = "ccpp_utils.strcmp"(%3) <{literal = "physics"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %4 {
// CHECK-NEXT:            %5, %6 = func.call @cld_suite_timestep_final_physics(%instance, %ninstances) : (memref<i32>, memref<i32>) -> (memref<i32>, memref<512xi8>)
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
// CHECK-LABEL:     func.func public @ccpp_physics_init(%suite_name : memref<?xi8>, %suite_part : memref<?xi8>, %lb : memref<i32>, %ub : memref<i32>, %instance : memref<i32>, %ninstances : memref<i32>, %errmsg : memref<512xi8>, %errflg : memref<i32>) -> (memref<512xi8>, memref<i32>) attributes {bind_c_dim_exprs = ["", "", "", "", "", "", "", ""]} {
// CHECK:             %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "cld_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:          %4 = "ccpp_utils.host_var_ref"() <{var_name = "tfreeze", module_name = "data"}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %5 = "ccpp_utils.strcmp"(%3) <{literal = "physics"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %5 {
// CHECK-NEXT:            %6, %7 = func.call @cld_suite_init_physics(%4, %instance, %ninstances) : (memref<!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>) -> (memref<512xi8>, memref<i32>)
// CHECK-NEXT:            "memref.copy"(%6, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:            "memref.copy"(%7, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %3) <{prefix = "No suite part named ", suffix = " found in suite cld_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %8 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %8, %errflg[] : memref<i32>
// CHECK-NEXT:          }
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_physics_final(%suite_name : memref<?xi8>, %suite_part : memref<?xi8>, %lb : memref<i32>, %ub : memref<i32>, %instance : memref<i32>, %ninstances : memref<i32>, %errmsg : memref<512xi8>, %errflg : memref<i32>) -> (memref<512xi8>, memref<i32>) attributes {bind_c_dim_exprs = ["", "", "", "", "", "", "", ""]} {
// CHECK:             %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "cld_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:          %4 = "ccpp_utils.strcmp"(%3) <{literal = "physics"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %4 {
// CHECK-NEXT:            %5, %6 = func.call @cld_suite_final_physics(%instance, %ninstances) : (memref<i32>, memref<i32>) -> (memref<i32>, memref<512xi8>)
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
// CHECK-NEXT:          "ccpp_utils.raw_fortran_lines"() <{lines = "errmsg = ''\nerrflg = 0\ndo_input = .true.\ndo_output = .true.\nif (present(input_vars)) do_input = input_vars\nif (present(output_vars)) do_output = output_vars\nif (trim(suite_name) .eq. 'cld_suite') then\n  if (do_input .and. .not. do_output) then\n    allocate(var_list(7))\n    var_list(1) = 'ccpp_constituent_tendencies         '\n    var_list(2) = 'ccpp_constituents                   '\n    var_list(3) = 'cloud_liquid_dry_mixing_ratio       '\n    var_list(4) = 'number_of_ccpp_constituents         '\n    var_list(5) = 'surface_air_pressure                '\n    var_list(6) = 'temperature                         '\n    var_list(7) = 'water_vapor_specific_humidity       '\n  else if (.not. do_input .and. do_output) then\n    allocate(var_list(9))\n    var_list(1) = 'ccpp_constituent_tendencies         '\n    var_list(2) = 'ccpp_constituents                   '\n    var_list(3) = 'ccpp_error_code                     '\n    var_list(4) = 'ccpp_error_message                  '\n    var_list(5) = 'cloud_liquid_dry_mixing_ratio       '\n    var_list(6) = 'dynamic_constituents_for_cld_liq    '\n    var_list(7) = 'temperature                         '\n    var_list(8) = 'tendency_of_cloud_liquid_dry_mixing_ratio'\n    var_list(9) = 'water_vapor_specific_humidity       '\n  else\n    allocate(var_list(11))\n    var_list(1) = 'ccpp_constituent_tendencies         '\n    var_list(2) = 'ccpp_constituents                   '\n    var_list(3) = 'ccpp_error_code                     '\n    var_list(4) = 'ccpp_error_message                  '\n    var_list(5) = 'cloud_liquid_dry_mixing_ratio       '\n    var_list(6) = 'dynamic_constituents_for_cld_liq    '\n    var_list(7) = 'number_of_ccpp_constituents         '\n    var_list(8) = 'surface_air_pressure                '\n    var_list(9) = 'temperature                         '\n    var_list(10) = 'tendency_of_cloud_liquid_dry_mixing_ratio'\n    var_list(11) = 'water_vapor_specific_humidity       '\n  end if\nelse\n  write(errmsg, '(3a)') \"No suite named \", trim(suite_name), \" found\"\n  errflg = 1\nend if"}> : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_instances", base_type = "type", rank = 1 : i64, ddt_name = "Cld_lc_instance_t", is_target = true}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.non_cam_host_constituent_api"() <{public_names = ["Cld_ccpp_is_scheme_constituent", "Cld_ccpp_deallocate_dynamic_constituents", "Cld_ccpp_register_constituents", "Cld_ccpp_number_constituents", "Cld_ccpp_initialize_constituents", "Cld_constituents_array", "Cld_advected_constituents_array", "Cld_const_get_index", "Cld_model_const_properties"]}> ({
// CHECK-NEXT:        "ccpp_utils.derived_type_def"() <{type_name = "Cld_lc_instance_t"}> ({
// CHECK-NEXT:          "ccpp_utils.ddt_component_decl"() <{var_name = "cam_constituents_obj", base_type = "type", rank = 0 : i64, ddt_name = "ccpp_model_constituents_t"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.ddt_component_decl"() <{var_name = "lc_dyn_const", base_type = "type", rank = 1 : i64, ddt_name = "ccpp_constituent_properties_t"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.ddt_component_decl"() <{var_name = "lc_all_constituents", base_type = "integer", rank = 1 : i64}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.ddt_component_decl"() <{var_name = "lc_constituent_array", base_type = "real", rank = 3 : i64, kind = "kind_phys", is_pointer = true}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.ddt_component_decl"() <{var_name = "lc_const_tend", base_type = "real", rank = 3 : i64, kind = "kind_phys"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.ddt_component_decl"() <{var_name = "lc_const_props", base_type = "type", rank = 1 : i64, ddt_name = "ccpp_constituent_prop_ptr_t"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.ddt_component_decl"() <{var_name = "lc_cld_liq_tend", base_type = "real", rank = 2 : i64, kind = "kind_phys", is_pointer = true}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.ddt_component_decl"() <{var_name = "cam_model_const_stdnames", base_type = "character", rank = 0 : i64, kind = "29", fixed_dim = 1 : i64, init_value = "[ character(len=29) :: 'cloud_liquid_dry_mixing_ratio' ]"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.ddt_component_decl"() <{var_name = "cam_model_const_indices", base_type = "integer", rank = 0 : i64, fixed_dim = 1 : i64, init_value = "-1"}> : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "Cld_ccpp_is_scheme_constituent", is_function = false, args = ["std_name", "is_const", "errflg", "errmsg", "instance"], use_stmts = [], arg_decls = ["character(len=*), intent(in) :: std_name", "logical, intent(out) :: is_const", "integer, intent(out) :: errflg", "character(len=512), intent(out) :: errmsg", "integer, intent(in) :: instance"], local_decls = ["integer :: lc_idx", "character(len=256) :: lc_std_name"]}> ({
// CHECK-NEXT:          "ccpp_utils.raw_fortran_lines"() <{lines = "errflg = 0\nerrmsg = ''\nis_const = .false."}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.if_then"() ({
// CHECK-NEXT:            "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 0>} : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.if_then"() ({
// CHECK-NEXT:              "ccpp_utils.call_expr"() <{callee = "any"}> ({
// CHECK-NEXT:                %0 = "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances(instance)%cam_model_const_stdnames"}> : () -> i32
// CHECK-NEXT:                %1 = "ccpp_utils.var_ref_expr"() <{var_name = "std_name"}> : () -> i32
// CHECK-NEXT:                %2 = arith.cmpi eq, %0, %1 : i32
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 0>} : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.raw_fortran_lines"() <{lines = "is_const = .true.\nreturn"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          "ccpp_utils.if_then"() ({
// CHECK-NEXT:            "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 0>} : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.if_then"() ({
// CHECK-NEXT:              "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances(instance)%lc_dyn_const"}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 0>} : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.text_bounded_do_loop"() <{loop_var = "lc_idx", upper_expr = "size(lc_instances(instance)%lc_dyn_const)"}> ({
// CHECK-NEXT:                "ccpp_utils.ddt_method_call"() <{method = "standard_name", kwargs = []}> ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.member_access_expr"() <{member = "lc_dyn_const"}> ({
// CHECK-NEXT:                      "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                        "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:                      }, {
// CHECK-NEXT:                        "ccpp_utils.var_ref_expr"() <{var_name = "instance"}> : () -> ()
// CHECK-NEXT:                      }) : () -> ()
// CHECK-NEXT:                    }) : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "lc_idx"}> : () -> ()
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "lc_std_name"}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1, 0>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.if_then"() ({
// CHECK-NEXT:                  %3 = "ccpp_utils.call_expr"() <{callee = "trim"}> ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "lc_std_name"}> : () -> ()
// CHECK-NEXT:                  }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i32
// CHECK-NEXT:                  %4 = "ccpp_utils.call_expr"() <{callee = "trim"}> ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "std_name"}> : () -> ()
// CHECK-NEXT:                  }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i32
// CHECK-NEXT:                  %5 = arith.cmpi eq, %3, %4 : i32
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.raw_fortran_lines"() <{lines = "is_const = .true.\nreturn"}> : () -> ()
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "Cld_ccpp_deallocate_dynamic_constituents", is_function = false, args = ["instance"], use_stmts = [], arg_decls = ["integer, intent(in) :: instance"], local_decls = []}> ({
// CHECK-NEXT:          "ccpp_utils.raw_fortran_lines"() <{lines = "if (.not. allocated(lc_instances)) return"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.safe_dealloc"() <{var_name = "lc_instances(instance)%lc_dyn_const"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.safe_dealloc"() <{var_name = "lc_instances(instance)%lc_all_constituents"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.safe_dealloc"() <{var_name = "lc_instances(instance)%lc_const_props"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.raw_fortran_lines"() <{lines = "if (associated(lc_instances(instance)%lc_constituent_array)) nullify(lc_instances(instance)%lc_constituent_array)"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.safe_dealloc"() <{var_name = "lc_instances(instance)%lc_const_tend"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.nullify_pointer"() <{ptr_name = "lc_instances(instance)%lc_cld_liq_tend"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.cam_direct_call"() <{callee = "lc_instances(instance)%cam_constituents_obj%reset", call_args = []}> : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "Cld_ccpp_register_constituents", is_function = false, args = ["host_constituents", "errmsg", "errcode", "instance", "ninstances"], use_stmts = ["use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t, ccpp_constituent_prop_ptr_t", "use ccpp_scheme_utils, only: ccpp_scheme_utils_set_constituents"], arg_decls = ["type(ccpp_constituent_properties_t), target, intent(in) :: host_constituents(:)", "character(len=512), intent(out) :: errmsg", "integer, intent(out) :: errcode", "integer, intent(in) :: instance", "integer, intent(in) :: ninstances"], local_decls = ["integer :: lc_i, lc_num_consts, field_ind", "type(ccpp_constituent_properties_t), pointer :: const_prop", "type(ccpp_constituent_prop_ptr_t), pointer :: lc_props_ptr(:)"]}> ({
// CHECK-NEXT:          "ccpp_utils.raw_fortran_lines"() <{lines = "errcode = 0\nerrmsg = ''"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.if_then"() ({
// CHECK-NEXT:            %6 = "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i1
// CHECK-NEXT:            %7 = arith.constant true
// CHECK-NEXT:            %8 = arith.xori %6, %7 : i1
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.raw_fortran_lines"() <{lines = "allocate(lc_instances(ninstances))"}> : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          "ccpp_utils.raw_fortran_lines"() <{lines = "lc_num_consts = size(host_constituents)"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.raw_fortran_lines"() <{lines = "if (allocated(lc_instances(instance)%lc_dyn_const)) lc_num_consts = lc_num_consts + size(lc_instances(instance)%lc_dyn_const)"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.raw_fortran_lines"() <{lines = "lc_num_consts = lc_num_consts + 1"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.ddt_method_call"() <{method = "initialize_table", kwargs = []}> ({
// CHECK-NEXT:            "ccpp_utils.member_access_expr"() <{member = "cam_constituents_obj"}> ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "instance"}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "lc_num_consts"}> : () -> ()
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 1, 0>} : () -> ()
// CHECK-NEXT:          "ccpp_utils.text_bounded_do_loop"() <{loop_var = "lc_i", upper_expr = "size(host_constituents)"}> ({
// CHECK-NEXT:            "ccpp_utils.allocate"() <{var_name = "const_prop", dims = [], stat_var = "errcode"}> : () -> ()
// CHECK-NEXT:            "ccpp_utils.if_then"() ({
// CHECK-NEXT:              %9 = "ccpp_utils.var_ref_expr"() <{var_name = "errcode"}> : () -> i32
// CHECK-NEXT:              %10 = arith.constant 0 : i32
// CHECK-NEXT:              %11 = arith.cmpi ne, %9, %10 : i32
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.raw_fortran_lines"() <{lines = "errmsg = 'ERROR allocating const_prop'\nreturn"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:            "ccpp_utils.raw_fortran_lines"() <{lines = "const_prop = host_constituents(lc_i)"}> : () -> ()
// CHECK-NEXT:            "ccpp_utils.ddt_method_call"() <{method = "new_field"}> ({
// CHECK-NEXT:              "ccpp_utils.member_access_expr"() <{member = "cam_constituents_obj"}> ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "instance"}> : () -> ()
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }) : () -> ()
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
// CHECK-NEXT:          "ccpp_utils.if_then"() ({
// CHECK-NEXT:            "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances(instance)%lc_dyn_const"}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 0>} : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.text_bounded_do_loop"() <{loop_var = "lc_i", upper_expr = "size(lc_instances(instance)%lc_dyn_const)"}> ({
// CHECK-NEXT:              "ccpp_utils.allocate"() <{var_name = "const_prop", dims = [], stat_var = "errcode"}> : () -> ()
// CHECK-NEXT:              "ccpp_utils.if_then"() ({
// CHECK-NEXT:                %12 = "ccpp_utils.var_ref_expr"() <{var_name = "errcode"}> : () -> i32
// CHECK-NEXT:                %13 = arith.constant 0 : i32
// CHECK-NEXT:                %14 = arith.cmpi ne, %12, %13 : i32
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.raw_fortran_lines"() <{lines = "errmsg = 'ERROR allocating const_prop'\nreturn"}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:              "ccpp_utils.raw_fortran_lines"() <{lines = "const_prop = lc_instances(instance)%lc_dyn_const(lc_i)"}> : () -> ()
// CHECK-NEXT:              "ccpp_utils.ddt_method_call"() <{method = "new_field"}> ({
// CHECK-NEXT:                "ccpp_utils.member_access_expr"() <{member = "cam_constituents_obj"}> ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "instance"}> : () -> ()
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "const_prop"}> : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.keyword_arg_expr"() <{arg_name = "errcode"}> ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "errcode"}> : () -> ()
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.keyword_arg_expr"() <{arg_name = "errmsg"}> ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "errmsg"}> : () -> ()
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1, 2>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.nullify_pointer"() <{ptr_name = "const_prop"}> : () -> ()
// CHECK-NEXT:              "ccpp_utils.error_propagate"() <{errcode_var = "errcode"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          "ccpp_utils.allocate"() <{var_name = "const_prop", dims = [], stat_var = "errcode"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.if_then"() ({
// CHECK-NEXT:            %15 = "ccpp_utils.var_ref_expr"() <{var_name = "errcode"}> : () -> i32
// CHECK-NEXT:            %16 = arith.constant 0 : i32
// CHECK-NEXT:            %17 = arith.cmpi ne, %15, %16 : i32
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.raw_fortran_lines"() <{lines = "errmsg = 'ERROR allocating const_prop'\nreturn"}> : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          "ccpp_utils.ddt_method_call"() <{method = "instantiate", args = []}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "const_prop"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.keyword_arg_expr"() <{arg_name = "std_name"}> ({
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "cloud_liquid_dry_mixing_ratio"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.keyword_arg_expr"() <{arg_name = "long_name"}> ({
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "Cloud liquid dry mixing ratio"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.keyword_arg_expr"() <{arg_name = "diag_name"}> ({
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "cld_liq_array"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.keyword_arg_expr"() <{arg_name = "units"}> ({
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "kg kg-1"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.keyword_arg_expr"() <{arg_name = "vertical_dim"}> ({
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "vertical_layer_dimension"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.keyword_arg_expr"() <{arg_name = "advected"}> ({
// CHECK-NEXT:              %18 = arith.constant true
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.keyword_arg_expr"() <{arg_name = "errcode"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "errcode"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.keyword_arg_expr"() <{arg_name = "errmsg"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "errmsg"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 0, 8>} : () -> ()
// CHECK-NEXT:          "ccpp_utils.error_propagate"() <{errcode_var = "errcode"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.ddt_method_call"() <{method = "new_field"}> ({
// CHECK-NEXT:            "ccpp_utils.member_access_expr"() <{member = "cam_constituents_obj"}> ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "instance"}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "const_prop"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.keyword_arg_expr"() <{arg_name = "errcode"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "errcode"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.keyword_arg_expr"() <{arg_name = "errmsg"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "errmsg"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 1, 2>} : () -> ()
// CHECK-NEXT:          "ccpp_utils.nullify_pointer"() <{ptr_name = "const_prop"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.error_propagate"() <{errcode_var = "errcode"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.ddt_method_call"() <{method = "lock_table", args = []}> ({
// CHECK-NEXT:            "ccpp_utils.member_access_expr"() <{member = "cam_constituents_obj"}> ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "instance"}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }) : () -> ()
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
// CHECK-NEXT:              "ccpp_utils.member_access_expr"() <{member = "cam_constituents_obj"}> ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "instance"}> : () -> ()
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          "ccpp_utils.safe_dealloc"() <{var_name = "lc_instances(instance)%lc_const_props"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.allocate"() <{var_name = "lc_instances(instance)%lc_const_props"}> ({
// CHECK-NEXT:            "ccpp_utils.call_expr"() <{callee = "size"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "lc_props_ptr"}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 0>} : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          "ccpp_utils.raw_fortran_lines"() <{lines = "lc_instances(instance)%lc_const_props = lc_props_ptr"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.nullify_pointer"() <{ptr_name = "lc_props_ptr"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.cam_direct_call"() <{callee = "ccpp_scheme_utils_set_constituents", call_args = ["lc_instances(instance)%lc_const_props"]}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.ddt_method_call"() <{method = "num_constituents"}> ({
// CHECK-NEXT:            "ccpp_utils.member_access_expr"() <{member = "cam_constituents_obj"}> ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "instance"}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }) : () -> ()
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
// CHECK-NEXT:          "ccpp_utils.safe_dealloc"() <{var_name = "lc_instances(instance)%lc_all_constituents"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.allocate"() <{var_name = "lc_instances(instance)%lc_all_constituents"}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "lc_num_consts"}> : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          "ccpp_utils.text_bounded_do_loop"() <{loop_var = "lc_i", upper_expr = "size(lc_instances(instance)%cam_model_const_indices)"}> ({
// CHECK-NEXT:            "ccpp_utils.ddt_method_call"() <{method = "const_index"}> ({
// CHECK-NEXT:              "ccpp_utils.member_access_expr"() <{member = "cam_constituents_obj"}> ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "instance"}> : () -> ()
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "field_ind"}> : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.member_access_expr"() <{member = "cam_model_const_stdnames"}> ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "instance"}> : () -> ()
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "lc_i"}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.keyword_arg_expr"() <{arg_name = "errcode"}> ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "errcode"}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.keyword_arg_expr"() <{arg_name = "errmsg"}> ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "errmsg"}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 2, 2>} : () -> ()
// CHECK-NEXT:            "ccpp_utils.error_propagate"() <{errcode_var = "errcode"}> : () -> ()
// CHECK-NEXT:            "ccpp_utils.active_check"() ({
// CHECK-NEXT:              %19 = "ccpp_utils.var_ref_expr"() <{var_name = "field_ind"}> : () -> i32
// CHECK-NEXT:              %20 = arith.constant 0 : i32
// CHECK-NEXT:              %21 = arith.cmpi sgt, %19, %20 : i32
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.raw_fortran_lines"() <{lines = "lc_instances(instance)%cam_model_const_indices(lc_i) = field_ind"}> : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.raw_fortran_lines"() <{lines = "errcode = 1\nerrmsg = 'No field index for '//trim(lc_instances(instance)%cam_model_const_stdnames(lc_i))\nreturn"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "Cld_ccpp_number_constituents", is_function = false, args = ["num_advected", "errmsg", "errcode", "advected", "instance"], use_stmts = [], arg_decls = ["integer, intent(out) :: num_advected", "character(len=512), intent(out) :: errmsg", "integer, intent(out) :: errcode", "logical, optional, intent(in) :: advected", "integer, intent(in) :: instance"], local_decls = []}> ({
// CHECK-NEXT:          "ccpp_utils.raw_fortran_lines"() <{lines = "errcode = 0\nerrmsg = ''"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.active_check"() ({
// CHECK-NEXT:            "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 0>} : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.ddt_method_call"() <{method = "num_constituents"}> ({
// CHECK-NEXT:              "ccpp_utils.member_access_expr"() <{member = "cam_constituents_obj"}> ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "instance"}> : () -> ()
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "num_advected"}> : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.keyword_arg_expr"() <{arg_name = "advected"}> ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "advected"}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.keyword_arg_expr"() <{arg_name = "errcode"}> ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "errcode"}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.keyword_arg_expr"() <{arg_name = "errmsg"}> ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "errmsg"}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 1, 3>} : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.raw_fortran_lines"() <{lines = "num_advected = 0"}> : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "Cld_ccpp_initialize_constituents", is_function = false, args = ["ncols", "pver", "errflg", "errmsg", "instance"], use_stmts = [], arg_decls = ["integer, intent(in) :: ncols", "integer, intent(in) :: pver", "integer, intent(out) :: errflg", "character(len=512), intent(out) :: errmsg", "integer, intent(in) :: instance"], local_decls = []}> ({
// CHECK-NEXT:          "ccpp_utils.raw_fortran_lines"() <{lines = "errflg = 0\nerrmsg = ''"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.error_guard"() <{errmsg_text = "ccpp_initialize_constituents: register_constituents not called"}> ({
// CHECK-NEXT:            "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 0>} : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          "ccpp_utils.error_guard"() <{errmsg_text = "ccpp_initialize_constituents: register_constituents not called"}> ({
// CHECK-NEXT:            "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances(instance)%lc_all_constituents"}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 0>} : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          "ccpp_utils.ddt_method_call"() <{method = "lock_data"}> ({
// CHECK-NEXT:            "ccpp_utils.member_access_expr"() <{member = "cam_constituents_obj"}> ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "instance"}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }) : () -> ()
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
// CHECK-NEXT:          "ccpp_utils.pointer_assign"() <{ptr_name = "lc_instances(instance)%lc_constituent_array"}> ({
// CHECK-NEXT:            "ccpp_utils.member_access_expr"() <{member = "field_data_ptr()"}> ({
// CHECK-NEXT:              "ccpp_utils.member_access_expr"() <{member = "cam_constituents_obj"}> ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "instance"}> : () -> ()
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          "ccpp_utils.safe_dealloc"() <{var_name = "lc_instances(instance)%lc_const_tend"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.allocate"() <{var_name = "lc_instances(instance)%lc_const_tend"}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "ncols"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "pver"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.call_expr"() <{callee = "size"}> ({
// CHECK-NEXT:              "ccpp_utils.member_access_expr"() <{member = "lc_all_constituents"}> ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "instance"}> : () -> ()
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 0>} : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          "ccpp_utils.zero_fill"() <{var_name = "lc_instances(instance)%lc_const_tend"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.scoped_block"() <{local_decls = ["integer :: lc_tend_idx", "character(len=512) :: lc_tend_errmsg"]}> ({
// CHECK-NEXT:            "ccpp_utils.nullify_pointer"() <{ptr_name = "lc_instances(instance)%lc_cld_liq_tend"}> : () -> ()
// CHECK-NEXT:            "ccpp_utils.ddt_method_call"() <{method = "const_index"}> ({
// CHECK-NEXT:              "ccpp_utils.member_access_expr"() <{member = "cam_constituents_obj"}> ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "instance"}> : () -> ()
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "lc_tend_idx"}> : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "cloud_liquid_dry_mixing_ratio"}> : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.keyword_arg_expr"() <{arg_name = "errcode"}> ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "errflg"}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.keyword_arg_expr"() <{arg_name = "errmsg"}> ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "lc_tend_errmsg"}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 2, 2>} : () -> ()
// CHECK-NEXT:            "ccpp_utils.active_check"() ({
// CHECK-NEXT:              %22 = "ccpp_utils.var_ref_expr"() <{var_name = "errflg"}> : () -> i32
// CHECK-NEXT:              %23 = arith.constant 0 : i32
// CHECK-NEXT:              %24 = arith.cmpi eq, %22, %23 : i32
// CHECK-NEXT:              %25 = "ccpp_utils.var_ref_expr"() <{var_name = "lc_tend_idx"}> : () -> i32
// CHECK-NEXT:              %26 = arith.constant 0 : i32
// CHECK-NEXT:              %27 = arith.cmpi sgt, %25, %26 : i32
// CHECK-NEXT:              %28 = arith.andi %24, %27 : i1
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.pointer_slice_assign"() <{ptr_name = "lc_instances(instance)%lc_cld_liq_tend", array_name = "lc_instances(instance)%lc_const_tend", index_var = "lc_tend_idx"}> : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.raw_fortran_lines"() <{lines = "errflg = 0"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "Cld_constituents_array", is_function = true, args = ["instance"], use_stmts = [], arg_decls = ["integer, intent(in) :: instance"], local_decls = [], result_name = "ptr", result_decl = "real(kind=kind_phys), pointer :: ptr(:, :, :)"}> ({
// CHECK-NEXT:          "ccpp_utils.pointer_assign"() <{ptr_name = "ptr"}> ({
// CHECK-NEXT:            "ccpp_utils.member_access_expr"() <{member = "lc_constituent_array"}> ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "instance"}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "Cld_advected_constituents_array", is_function = true, args = ["instance"], use_stmts = [], arg_decls = ["integer, intent(in) :: instance"], local_decls = [], result_name = "ptr", result_decl = "real(kind=kind_phys), pointer :: ptr(:, :, :)"}> ({
// CHECK-NEXT:          "ccpp_utils.pointer_assign"() <{ptr_name = "ptr"}> ({
// CHECK-NEXT:            "ccpp_utils.member_access_expr"() <{member = "advected_constituents_ptr()"}> ({
// CHECK-NEXT:              "ccpp_utils.member_access_expr"() <{member = "cam_constituents_obj"}> ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "instance"}> : () -> ()
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "Cld_const_get_index", is_function = false, args = ["std_name", "index", "errflg", "errmsg", "instance"], use_stmts = ["use ccpp_constituent_prop_mod, only: to_lower"], arg_decls = ["character(len=*), intent(in) :: std_name", "integer, intent(out) :: index", "integer, intent(out) :: errflg", "character(len=512), intent(out) :: errmsg", "integer, intent(in) :: instance"], local_decls = []}> ({
// CHECK-NEXT:          "ccpp_utils.raw_fortran_lines"() <{lines = "errflg = 0\nerrmsg = ''\nindex = -1"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.error_guard"() <{errmsg_text = "const_get_index: constituents not registered"}> ({
// CHECK-NEXT:            "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 0>} : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          "ccpp_utils.error_guard"() <{errmsg_text = "const_get_index: constituents not registered"}> ({
// CHECK-NEXT:            "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances(instance)%lc_all_constituents"}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 0>} : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          "ccpp_utils.ddt_method_call"() <{method = "const_index"}> ({
// CHECK-NEXT:            "ccpp_utils.member_access_expr"() <{member = "cam_constituents_obj"}> ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "instance"}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }) : () -> ()
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
// CHECK-NEXT:          "ccpp_utils.if_then"() ({
// CHECK-NEXT:            %29 = "ccpp_utils.var_ref_expr"() <{var_name = "errflg"}> : () -> i32
// CHECK-NEXT:            %30 = arith.constant 0 : i32
// CHECK-NEXT:            %31 = arith.cmpi ne, %29, %30 : i32
// CHECK-NEXT:            %32 = "ccpp_utils.var_ref_expr"() <{var_name = "index"}> : () -> i32
// CHECK-NEXT:            %33 = arith.constant 0 : i32
// CHECK-NEXT:            %34 = arith.cmpi sle, %32, %33 : i32
// CHECK-NEXT:            %35 = arith.ori %31, %34 : i1
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.assign"() <{lhs_expr = "errflg", rhs_expr = "1"}> : () -> ()
// CHECK-NEXT:            "ccpp_utils.write_stmt"() <{dest = "errmsg", format_spec = "(3a)", items = ["'const_get_index: constituent '", "trim(std_name)", "' not found'"]}> : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "Cld_model_const_properties", is_function = true, args = ["instance"], use_stmts = [], arg_decls = ["integer, intent(in) :: instance"], local_decls = [], result_name = "ptr", result_decl = "type(ccpp_constituent_prop_ptr_t), pointer :: ptr(:)"}> ({
// CHECK-NEXT:          "ccpp_utils.pointer_assign"() <{ptr_name = "ptr"}> ({
// CHECK-NEXT:            "ccpp_utils.member_access_expr"() <{member = "lc_const_props"}> ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "instance"}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-LABEL:     func.func private @cld_suite_register(memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>, memref<i32>, memref<i32>) -> (memref<512xi8>, memref<i32>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_initialize(memref<i32>, memref<i32>) -> (memref<i32>, memref<512xi8>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_finalize(memref<i32>, memref<i32>) -> (memref<i32>, memref<512xi8>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_physics(memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>) -> (memref<512xi8>, memref<i32>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_timestep_init_physics(memref<i32>, memref<i32>) -> (memref<i32>, memref<512xi8>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_timestep_final_physics(memref<i32>, memref<i32>) -> (memref<i32>, memref<512xi8>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_init_physics(memref<!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>) -> (memref<512xi8>, memref<i32>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_final_physics(memref<i32>, memref<i32>) -> (memref<i32>, memref<512xi8>) attributes {module = "cld_suite_cap"}
// CHECK:         }
// CHECK-LABEL:   builtin.module @ccpp_kinds {
// CHECK:           "ccpp_utils.kind_def"() <{kind_name = "kind_phys", kind_value = "REAL64", kind_module = "iso_fortran_env"}> : () -> ()
// CHECK-NEXT:    }
// CHECK-NEXT:  }
