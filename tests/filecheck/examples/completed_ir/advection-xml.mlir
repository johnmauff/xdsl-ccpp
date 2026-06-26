// Test the completed IR for the advection XML frontend.
// Exercises: 3-D array types (memref<?x?x?x...>), four distinct schemes,
// apply_constituent_tendencies deduplicated to one call despite appearing
// twice in the suite XML, and host-derived arguments threaded through caps.
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/advection/cld_suite.xml --scheme-files examples/advection/const_indices.meta,examples/advection/cld_liq.meta,examples/advection/cld_ice.meta,examples/advection/apply_constituent_tendencies.meta --host-files examples/advection/test_host_data.meta,examples/advection/test_host.meta,examples/advection/test_host_mod.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap,generate-kinds,strip-ccpp | python3 -m filecheck %s

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
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "num_consts", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_data"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "ncols", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "pver", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "const_index", fortran_type = "integer", rank = 0 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "const_inds", fortran_type = "integer", rank = 1 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "cld_liq_array", fortran_type = "real(kind=kind_phys)", rank = 2 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "tcld", fortran_type = "real(kind=kind_phys)", rank = 0 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "cld_ice_array", fortran_type = "real(kind=kind_phys)", rank = 2 : i64}> : () -> ()
// CHECK-LABEL:     func.func public @cld_suite_suite_register(%dyn_const__alloc : memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>, %dyn_const_ice__alloc : memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %num_consts = "ccpp_utils.host_var_ref"() <{var_name = "num_consts", module_name = "test_host_data"}> : () -> memref<i32>
// CHECK-NEXT:        %ncols = "ccpp_utils.host_var_ref"() <{var_name = "ncols", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:        %pver = "ccpp_utils.host_var_ref"() <{var_name = "pver", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%num_consts) <{var_name = "const_inds", kind_name = "kind_phys"}> : (memref<i32>) -> ()
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ncols, %pver) <{var_name = "cld_liq_array", kind_name = "kind_phys"}> : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ncols, %pver) <{var_name = "cld_ice_array", kind_name = "kind_phys"}> : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        %1 = arith.constant 0 : i32
// CHECK-NEXT:        %2 = arith.cmpi eq, %3, %1 : i32
// CHECK-NEXT:        %3 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          func.call @cld_liq_register(%dyn_const__alloc, %errmsg, %errflg) : (memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %4 = arith.constant 0 : i32
// CHECK-NEXT:        %5 = arith.cmpi eq, %6, %4 : i32
// CHECK-NEXT:        %6 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %5 {
// CHECK-NEXT:          func.call @cld_ice_register(%dyn_const_ice__alloc, %errmsg, %errflg) : (memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @cld_suite_suite_initialize(%const_std_name : memref<512xi8>, %num_consts : memref<i32>, %test_stdname_array__in : memref<?x512xi8>, %const_inds : memref<?xi32>, %tfreeze : memref<!ccpp_utils.real_kind<"kind_phys">>) -> (memref<i32>, memref<512xi8>, memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>) {
// CHECK:             %const_index = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %tcld = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %cld_liq_array = "ccpp_utils.host_var_ref"() <{var_name = "cld_liq_array", module_name = ""}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %ncols = "ccpp_utils.host_var_ref"() <{var_name = "ncols", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:        %pver = "ccpp_utils.host_var_ref"() <{var_name = "pver", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:        %cld_ice_array = "ccpp_utils.host_var_ref"() <{var_name = "cld_ice_array", module_name = ""}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ncols, %pver) <{var_name = "cld_liq_array", kind_name = "kind_phys"}> : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ncols, %pver) <{var_name = "cld_ice_array", kind_name = "kind_phys", init_value = "0.0_kind_phys"}> : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%num_consts) <{var_name = "const_inds", kind_name = "kind_phys"}> : (memref<i32>) -> ()
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
// CHECK-NEXT:        %10 = arith.constant 0 : i32
// CHECK-NEXT:        %11 = arith.cmpi eq, %12, %10 : i32
// CHECK-NEXT:        %12 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %11 {
// CHECK-NEXT:          func.call @const_indices_init(%const_std_name, %num_consts, %test_stdname_array__in, %const_index, %const_inds, %errmsg, %errflg) : (memref<512xi8>, memref<i32>, memref<?x512xi8>, memref<i32>, memref<?xi32>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %13 = arith.constant 0 : i32
// CHECK-NEXT:        %14 = arith.cmpi eq, %15, %13 : i32
// CHECK-NEXT:        %15 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %14 {
// CHECK-NEXT:          func.call @cld_liq_init(%tfreeze, %cld_liq_array, %tcld, %errmsg, %errflg) : (memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %16 = arith.constant 0 : i32
// CHECK-NEXT:        %17 = arith.cmpi eq, %18, %16 : i32
// CHECK-NEXT:        %18 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %17 {
// CHECK-NEXT:          func.call @cld_ice_init(%tfreeze, %cld_ice_array, %errmsg, %errflg) : (memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %19 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %20 = "llvm.load"(%19) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %21 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%20, %21) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %const_index, %errmsg, %errflg, %tcld : memref<i32>, memref<512xi8>, memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @cld_suite_suite_finalize() -> (memref<i32>, memref<512xi8>) {
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
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @cld_suite_suite_timestep_initial() -> (memref<i32>, memref<512xi8>) {
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
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in cld_suite_timestep_initial"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = "llvm.mlir.addressof"() <{global_name = @const_in_time_step}> : () -> !llvm.ptr
// CHECK-NEXT:        %11 = "llvm.load"(%10) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %12 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%11, %12) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @cld_suite_suite_timestep_final() -> (memref<i32>, memref<512xi8>) {
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
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in cld_suite_timestep_final"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %11 = "llvm.load"(%10) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %12 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%11, %12) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @cld_suite_suite_physics(%const_std_name : memref<512xi8>, %num_consts : memref<i32>, %test_stdname_array__in : memref<?x512xi8>, %const_inds : memref<?xi32>, %col_start : memref<i32>, %col_end : memref<i32>, %timestep : memref<!ccpp_utils.real_kind<"kind_phys">>, %tcld : memref<!ccpp_utils.real_kind<"kind_phys">>, %temp : memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, %qv : memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, %ps__in : memref<?x!ccpp_utils.real_kind<"kind_phys">>, %cld_liq_tend : memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, %const_tend : memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, %const : memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>) -> (memref<i32>, memref<512xi8>, memref<i32>) {
// CHECK:             %const_index = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %ncol = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %1 = memref.load %col_start[] : memref<i32>
// CHECK-NEXT:        %2 = memref.load %col_end[] : memref<i32>
// CHECK-NEXT:        %3 = arith.subi %2, %1 : i32
// CHECK-NEXT:        %4 = arith.constant 1 : i32
// CHECK-NEXT:        %5 = arith.addi %3, %4 : i32
// CHECK-NEXT:        memref.store %5, %ncol[] : memref<i32>
// CHECK-NEXT:        %ccpp_lbound_one = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %6 = arith.constant 1 : i32
// CHECK-NEXT:        memref.store %6, %ccpp_lbound_one[] : memref<i32>
// CHECK-NEXT:        %cld_ice_array = "ccpp_utils.host_var_ref"() <{var_name = "cld_ice_array", module_name = ""}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %7 = "llvm.mlir.addressof"() <{global_name = @const_in_time_step}> : () -> !llvm.ptr
// CHECK-NEXT:        %8 = "llvm.load"(%7) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %9 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        %10 = "llvm.load"(%9) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %11 = "ccpp_utils.strcmp"(%8, %10) <{length = 12 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %12 = arith.constant true
// CHECK-NEXT:        %13 = arith.xori %11, %12 : i1
// CHECK-NEXT:        scf.if %13 {
// CHECK-NEXT:          %14 = "ccpp_utils.trim"(%10) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %14) <{prefix = "Invalid initial CCPP state, '", suffix = "' in cld_suite_physics"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %15 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %15, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %16 = arith.constant 0 : i32
// CHECK-NEXT:        %17 = arith.cmpi eq, %18, %16 : i32
// CHECK-NEXT:        %18 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %17 {
// CHECK-NEXT:          func.call @const_indices_run(%const_std_name, %num_consts, %test_stdname_array__in, %const_index, %const_inds, %errmsg, %errflg) : (memref<512xi8>, memref<i32>, memref<?x512xi8>, memref<i32>, memref<?xi32>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %19 = arith.constant 0 : i32
// CHECK-NEXT:        %20 = arith.cmpi eq, %21, %19 : i32
// CHECK-NEXT:        %21 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %20 {
// CHECK-NEXT:          func.call @cld_liq_run(%ncol, %timestep, %tcld, %temp, %qv, %ps__in, %cld_liq_tend, %errmsg, %errflg) : (memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %22 = arith.constant 0 : i32
// CHECK-NEXT:        %23 = arith.cmpi eq, %24, %22 : i32
// CHECK-NEXT:        %24 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %23 {
// CHECK-NEXT:          func.call @apply_constituent_tendencies_run(%const_tend, %const, %errflg, %errmsg) : (memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<512xi8>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %25 = arith.constant 0 : i32
// CHECK-NEXT:        %26 = arith.cmpi eq, %27, %25 : i32
// CHECK-NEXT:        %27 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %26 {
// CHECK-NEXT:          func.call @cld_ice_run(%ncol, %timestep, %temp, %qv, %ps__in, %cld_ice_array, %errmsg, %errflg) : (memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %28 = arith.constant 0 : i32
// CHECK-NEXT:        %29 = arith.cmpi eq, %30, %28 : i32
// CHECK-NEXT:        %30 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %29 {
// CHECK-NEXT:          func.call @apply_constituent_tendencies_run(%const_tend, %const, %errflg, %errmsg) : (memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<512xi8>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %const_index, %errmsg, %errflg : memref<i32>, memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func private @cld_liq_register(memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>, memref<512xi8>, memref<i32>) -> () attributes {module = "cld_liq"}
// CHECK-LABEL:     func.func private @cld_ice_register(memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>, memref<512xi8>, memref<i32>) -> () attributes {module = "cld_ice"}
// CHECK-LABEL:     func.func private @const_indices_init(memref<512xi8>, memref<i32>, memref<?x512xi8>, memref<i32>, memref<?xi32>, memref<512xi8>, memref<i32>) -> () attributes {module = "const_indices"}
// CHECK-LABEL:     func.func private @cld_liq_init(memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "cld_liq"}
// CHECK-LABEL:     func.func private @cld_ice_init(memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "cld_ice"}
// CHECK-LABEL:     func.func private @const_indices_run(memref<512xi8>, memref<i32>, memref<?x512xi8>, memref<i32>, memref<?xi32>, memref<512xi8>, memref<i32>) -> () attributes {module = "const_indices"}
// CHECK-LABEL:     func.func private @cld_liq_run(memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "cld_liq"}
// CHECK-LABEL:     func.func private @apply_constituent_tendencies_run(memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<512xi8>) -> () attributes {module = "apply_constituent_tendencies"}
// CHECK-LABEL:     func.func private @cld_ice_run(memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "cld_ice"}
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
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "tfreeze", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "const_index", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_data"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<9 x i8>, sym_name = "str_cld_suite", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "cld_suite"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<7 x i8>, sym_name = "str_physics", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "physics"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "ccpp_constituent_prop_ptr_t", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "ccpp_constituent_prop_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<0 x i8>, sym_name = "physics_state", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_data"} : () -> ()
// CHECK-LABEL:     func.func public @Cld_ccpp_physics_register(%suite_name : memref<?xi8>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_dyn_const"}> : () -> memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>
// CHECK-NEXT:        %1 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_dyn_const_ice"}> : () -> memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>
// CHECK-NEXT:        %2 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %2, %errflg[] : memref<i32>
// CHECK-NEXT:        %3 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %4 = "ccpp_utils.strcmp"(%3) <{literal = "cld_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %4 {
// CHECK-NEXT:          %5, %6 = func.call @cld_suite_suite_register(%0, %1) : (memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>, memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>) -> (memref<512xi8>, memref<i32>)
// CHECK-NEXT:          "memref.copy"(%5, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:          "memref.copy"(%6, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %3) <{prefix = "No suite named ", suffix = "found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %7 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %7, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @Cld_ccpp_physics_initialize(%suite_name : memref<?xi8>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "cld_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = "ccpp_utils.host_var_ref"() <{var_name = "const_std_name", module_name = "test_host_data"}> : () -> memref<512xi8>
// CHECK-NEXT:          %4 = "ccpp_utils.host_var_ref"() <{var_name = "num_consts", module_name = "test_host_data"}> : () -> memref<i32>
// CHECK-NEXT:          %5 = "ccpp_utils.host_var_ref"() <{var_name = "std_name_array", module_name = "test_host_data"}> : () -> memref<?x512xi8>
// CHECK-NEXT:          %6 = "ccpp_utils.host_var_ref"() <{var_name = "const_inds", module_name = "test_host_data"}> : () -> memref<?xi32>
// CHECK-NEXT:          %7 = "ccpp_utils.host_var_ref"() <{var_name = "tfreeze", module_name = "test_host_mod"}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %8 = "ccpp_utils.host_var_ref"() <{var_name = "const_index", module_name = "test_host_data"}> : () -> memref<i32>
// CHECK-NEXT:          %9 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_tcld"}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %10, %11, %12, %13 = func.call @cld_suite_suite_initialize(%3, %4, %5, %6, %7) : (memref<512xi8>, memref<i32>, memref<?x512xi8>, memref<?xi32>, memref<!ccpp_utils.real_kind<"kind_phys">>) -> (memref<i32>, memref<512xi8>, memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>)
// CHECK-NEXT:          "memref.copy"(%10, %8) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          "memref.copy"(%11, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:          "memref.copy"(%12, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          "memref.copy"(%13, %9) : (memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = "found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %14 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %14, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @Cld_ccpp_physics_finalize(%suite_name : memref<?xi8>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "cld_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3, %4 = func.call @cld_suite_suite_finalize() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:          "memref.copy"(%3, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          "memref.copy"(%4, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = "found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %5 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %5, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @Cld_ccpp_physics_timestep_initial(%suite_name : memref<?xi8>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "cld_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3, %4 = func.call @cld_suite_suite_timestep_initial() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:          "memref.copy"(%3, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          "memref.copy"(%4, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = "found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %5 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %5, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @Cld_ccpp_physics_timestep_final(%suite_name : memref<?xi8>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "cld_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3, %4 = func.call @cld_suite_suite_timestep_final() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:          "memref.copy"(%3, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          "memref.copy"(%4, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = "found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %5 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %5, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @Cld_ccpp_physics_run(%suite_name : memref<?xi8>, %suite_part : memref<?xi8>, %const_std_name : memref<512xi8>, %num_consts : memref<i32>, %test_stdname_array__in : memref<?x512xi8>, %const_inds : memref<?xi32>, %col_start : memref<i32>, %col_end : memref<i32>, %timestep : memref<!ccpp_utils.real_kind<"kind_phys">>, %errmsg : memref<512xi8>, %errflg : memref<i32>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "cld_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:          %4 = "ccpp_utils.strcmp"(%3) <{literal = "physics"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %4 {
// CHECK-NEXT:            %5 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_tcld"}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %6 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_temp(:, :)"}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %7 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_qv(:, :)"}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %8 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_ps(:)"}> : () -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %9 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_cld_liq_tend(:, :)"}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %10 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_const_tend(:, :, :)"}> : () -> memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %11 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_constituent_array(:, :, :)"}> : () -> memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %12 = "ccpp_utils.array_section"(%6, %col_start, %col_end) {operandSegmentSizes = array<i32: 1, 1, 1>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %13 = "ccpp_utils.array_section"(%7, %col_start, %col_end) {operandSegmentSizes = array<i32: 1, 1, 1>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %14 = "ccpp_utils.array_section"(%8, %col_start, %col_end) {operandSegmentSizes = array<i32: 1, 1, 1>} : (memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>) -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %15 = "ccpp_utils.array_section"(%9, %col_start, %col_end) {operandSegmentSizes = array<i32: 1, 1, 1>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %16 = "ccpp_utils.array_section"(%10, %col_start, %col_end) {operandSegmentSizes = array<i32: 1, 1, 1>} : (memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>) -> memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %17 = "ccpp_utils.array_section"(%11, %col_start, %col_end) {operandSegmentSizes = array<i32: 1, 1, 1>} : (memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>) -> memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %18 = "ccpp_utils.host_var_ref"() <{var_name = "const_index", module_name = "test_host_data"}> : () -> memref<i32>
// CHECK-NEXT:            %19, %20, %21 = func.call @cld_suite_suite_physics(%const_std_name, %num_consts, %test_stdname_array__in, %const_inds, %col_start, %col_end, %timestep, %5, %12, %13, %14, %15, %16, %17) : (memref<512xi8>, memref<i32>, memref<?x512xi8>, memref<?xi32>, memref<i32>, memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>) -> (memref<i32>, memref<512xi8>, memref<i32>)
// CHECK-NEXT:            "memref.copy"(%19, %18) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:            "memref.copy"(%20, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:            "memref.copy"(%21, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %3) <{prefix = "No suite part named ", suffix = " found in suite cld_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %22 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %22, %errflg[] : memref<i32>
// CHECK-NEXT:          }
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = "found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %23 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %23, %errflg[] : memref<i32>
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
// CHECK-NEXT:      "ccpp_utils.suite_variables"() <{body = "subroutine ccpp_physics_suite_variables(suite_name, var_list, errmsg, errflg, input_vars, output_vars)\n  character(len=*), intent(in) :: suite_name\n  character(len=*), allocatable, intent(out) :: var_list(:)\n  character(len=512), intent(out) :: errmsg\n  integer, intent(out) :: errflg\n  logical, optional, intent(in) :: input_vars\n  logical, optional, intent(in) :: output_vars\n  logical :: do_input, do_output\n  errmsg = ''\n  errflg = 0\n  do_input = .true.\n  do_output = .true.\n  if (present(input_vars)) do_input = input_vars\n  if (present(output_vars)) do_output = output_vars\n  if (trim(suite_name) .eq. 'cld_suite') then\n    if (do_input .and. .not. do_output) then\n      allocate(var_list(13))\n      var_list(1) = 'banana_array_dim                    '\n      var_list(2) = 'ccpp_constituent_tendencies         '\n      var_list(3) = 'ccpp_constituents                   '\n      var_list(4) = 'cloud_ice_dry_mixing_ratio          '\n      var_list(5) = 'cloud_liquid_dry_mixing_ratio       '\n      var_list(6) = 'minimum_temperature_for_cloud_liquid'\n      var_list(7) = 'number_of_ccpp_constituents         '\n      var_list(8) = 'surface_air_pressure                '\n      var_list(9) = 'temperature                         '\n      var_list(10) = 'tendency_of_cloud_liquid_dry_mixing_ratio'\n      var_list(11) = 'time_step_for_physics               '\n      var_list(12) = 'water_temperature_at_freezing       '\n      var_list(13) = 'water_vapor_specific_humidity       '\n    else if (.not. do_input .and. do_output) then\n      allocate(var_list(14))\n      var_list(1) = 'ccpp_constituent_tendencies         '\n      var_list(2) = 'ccpp_constituents                   '\n      var_list(3) = 'ccpp_error_code                     '\n      var_list(4) = 'ccpp_error_message                  '\n      var_list(5) = 'cloud_ice_dry_mixing_ratio          '\n      var_list(6) = 'cloud_liquid_dry_mixing_ratio       '\n      var_list(7) = 'dynamic_constituents_for_cld_ice    '\n      var_list(8) = 'dynamic_constituents_for_cld_liq    '\n      var_list(9) = 'minimum_temperature_for_cloud_liquid'\n      var_list(10) = 'temperature                         '\n      var_list(11) = 'tendency_of_cloud_liquid_dry_mixing_ratio'\n      var_list(12) = 'test_banana_constituent_index       '\n      var_list(13) = 'test_banana_constituent_indices     '\n      var_list(14) = 'water_vapor_specific_humidity       '\n    else\n      allocate(var_list(19))\n      var_list(1) = 'banana_array_dim                    '\n      var_list(2) = 'ccpp_constituent_tendencies         '\n      var_list(3) = 'ccpp_constituents                   '\n      var_list(4) = 'ccpp_error_code                     '\n      var_list(5) = 'ccpp_error_message                  '\n      var_list(6) = 'cloud_ice_dry_mixing_ratio          '\n      var_list(7) = 'cloud_liquid_dry_mixing_ratio       '\n      var_list(8) = 'dynamic_constituents_for_cld_ice    '\n      var_list(9) = 'dynamic_constituents_for_cld_liq    '\n      var_list(10) = 'minimum_temperature_for_cloud_liquid'\n      var_list(11) = 'number_of_ccpp_constituents         '\n      var_list(12) = 'surface_air_pressure                '\n      var_list(13) = 'temperature                         '\n      var_list(14) = 'tendency_of_cloud_liquid_dry_mixing_ratio'\n      var_list(15) = 'test_banana_constituent_index       '\n      var_list(16) = 'test_banana_constituent_indices     '\n      var_list(17) = 'time_step_for_physics               '\n      var_list(18) = 'water_temperature_at_freezing       '\n      var_list(19) = 'water_vapor_specific_humidity       '\n    end if\n  else\n    write(errmsg, '(3a)') \"No suite named \", trim(suite_name), \" found\"\n    errflg = 1\n  end if\nend subroutine ccpp_physics_suite_variables"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_dyn_const", fortran_type = "type(ccpp_constituent_properties_t)", rank = 1 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_dyn_const_ice", fortran_type = "type(ccpp_constituent_properties_t)", rank = 1 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_all_constituents", fortran_type = "type(ccpp_constituent_properties_t), target", rank = 1 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_constituent_array", fortran_type = "real(kind=kind_phys), target", rank = 3 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_const_tend", fortran_type = "real(kind=kind_phys), target", rank = 3 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_const_props", fortran_type = "type(ccpp_constituent_prop_ptr_t), target", rank = 1 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_tcld", fortran_type = "real(kind=kind_phys)", rank = 0 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_temp", fortran_type = "real(kind=kind_phys)", rank = 2 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_qv", fortran_type = "real(kind=kind_phys)", rank = 2 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_ps", fortran_type = "real(kind=kind_phys)", rank = 1 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_cld_liq_tend", fortran_type = "real(kind=kind_phys), pointer", rank = 2 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.constituent_api"() <{body = "  subroutine Cld_ccpp_is_scheme_constituent(std_name, is_const, errflg, errmsg)\n    character(len=*), intent(in) :: std_name\n    logical, intent(out) :: is_const\n    integer, intent(out) :: errflg\n    character(len=512), intent(out) :: errmsg\n    integer :: lc_idx\n    errflg = 0\n    errmsg = ''\n    is_const = .false.\n    select case (trim(std_name))\n    case ('cloud_liquid_dry_mixing_ratio', 'cloud_ice_dry_mixing_ratio')\n      is_const = .true.\n    case default\n      if (allocated(lc_dyn_const)) then\n        do lc_idx = 1, size(lc_dyn_const)\n          if (trim(lc_dyn_const(lc_idx)%std_name) == trim(std_name)) then\n            is_const = .true.\n            return\n          end if\n        end do\n      end if\n      if (allocated(lc_dyn_const_ice)) then\n        do lc_idx = 1, size(lc_dyn_const_ice)\n          if (trim(lc_dyn_const_ice(lc_idx)%std_name) == trim(std_name)) then\n            is_const = .true.\n            return\n          end if\n        end do\n      end if\n    end select\n  end subroutine Cld_ccpp_is_scheme_constituent\n\n  subroutine Cld_ccpp_deallocate_dynamic_constituents()\n    if (allocated(lc_dyn_const)) deallocate(lc_dyn_const)\n    if (allocated(lc_dyn_const_ice)) deallocate(lc_dyn_const_ice)\n    if (allocated(lc_all_constituents)) deallocate(lc_all_constituents)\n    if (allocated(lc_const_props)) deallocate(lc_const_props)\n    if (allocated(lc_constituent_array)) deallocate(lc_constituent_array)\n    if (allocated(lc_const_tend)) deallocate(lc_const_tend)\n    if (allocated(lc_tcld)) deallocate(lc_tcld)\n    if (allocated(lc_temp)) deallocate(lc_temp)\n    if (allocated(lc_qv)) deallocate(lc_qv)\n    if (allocated(lc_ps)) deallocate(lc_ps)\n    nullify(lc_cld_liq_tend)\n  end subroutine Cld_ccpp_deallocate_dynamic_constituents\n\n  subroutine Cld_ccpp_register_constituents(host_constituents, errmsg, errflg)\n    use ccpp_scheme_utils, only: ccpp_scheme_utils_set_constituents\n    type(ccpp_constituent_properties_t), intent(in) :: host_constituents(:)\n    character(len=512), intent(out) :: errmsg\n    integer, intent(out) :: errflg\n    integer :: lc_max, lc_num, lc_i, lc_j\n    logical :: lc_found\n    type(ccpp_constituent_properties_t), allocatable :: lc_tmp(:)\n    errflg = 0\n    errmsg = ''\n    lc_max = 0\n    if (allocated(lc_dyn_const)) lc_max = lc_max + size(lc_dyn_const)\n    if (allocated(lc_dyn_const_ice)) lc_max = lc_max + size(lc_dyn_const_ice)\n    lc_max = lc_max + 2\n    lc_max = lc_max + size(host_constituents)\n    allocate(lc_tmp(lc_max))\n    lc_num = 0\n    if (allocated(lc_dyn_const)) then\n      do lc_i = 1, size(lc_dyn_const)\n        lc_found = .false.\n        do lc_j = 1, lc_num\n          if (trim(lc_tmp(lc_j)%std_name) == trim(lc_dyn_const(lc_i)%std_name)) then\n            lc_found = .true.\n            if (trim(lc_tmp(lc_j)%units) /= trim(lc_dyn_const(lc_i)%units)) then\n              write(errmsg, '(3a)') 'ccp_model_const_add_metadata ERROR: Trying to add constituent ', trim(lc_dyn_const(lc_i)%std_name), &\n                ' but an incompatible constituent with this name already exists'\n              errflg = 1\n              return\n            end if\n            exit\n          end if\n        end do\n        if (.not. lc_found) then\n          lc_num = lc_num + 1\n          lc_tmp(lc_num) = lc_dyn_const(lc_i)\n        end if\n      end do\n    end if\n    if (allocated(lc_dyn_const_ice)) then\n      do lc_i = 1, size(lc_dyn_const_ice)\n        lc_found = .false.\n        do lc_j = 1, lc_num\n          if (trim(lc_tmp(lc_j)%std_name) == trim(lc_dyn_const_ice(lc_i)%std_name)) then\n            lc_found = .true.\n            if (trim(lc_tmp(lc_j)%units) /= trim(lc_dyn_const_ice(lc_i)%units)) then\n              write(errmsg, '(3a)') 'ccp_model_const_add_metadata ERROR: Trying to add constituent ', trim(lc_dyn_const_ice(lc_i)%std_name), &\n                ' but an incompatible constituent with this name already exists'\n              errflg = 1\n              return\n            end if\n            exit\n          end if\n        end do\n        if (.not. lc_found) then\n          lc_num = lc_num + 1\n          lc_tmp(lc_num) = lc_dyn_const_ice(lc_i)\n        end if\n      end do\n    end if\n    lc_found = .false.\n    do lc_j = 1, lc_num\n      if (trim(lc_tmp(lc_j)%std_name) == 'cloud_liquid_dry_mixing_ratio') then\n        lc_found = .true.\n        if (trim(lc_tmp(lc_j)%units) /= 'kg kg-1') then\n          write(errmsg, '(3a)') 'ccp_model_const_add_metadata ERROR: Trying to add constituent ', 'cloud_liquid_dry_mixing_ratio', &\n            ' but an incompatible constituent with this name already exists'\n          errflg = 1\n          return\n        end if\n        exit\n      end if\n    end do\n    if (.not. lc_found) then\n      lc_num = lc_num + 1\n      call lc_tmp(lc_num)%instantiate(std_name='cloud_liquid_dry_mixing_ratio', long_name='Cloud liquid dry mixing ratio', units='kg kg-1', errcode=errflg, errmsg=errmsg, advected=.true.)\n      if (errflg /= 0) return\n    end if\n    lc_found = .false.\n    do lc_j = 1, lc_num\n      if (trim(lc_tmp(lc_j)%std_name) == 'cloud_ice_dry_mixing_ratio') then\n        lc_found = .true.\n        if (trim(lc_tmp(lc_j)%units) /= 'kg kg-1') then\n          write(errmsg, '(3a)') 'ccp_model_const_add_metadata ERROR: Trying to add constituent ', 'cloud_ice_dry_mixing_ratio', &\n            ' but an incompatible constituent with this name already exists'\n          errflg = 1\n          return\n        end if\n        exit\n      end if\n    end do\n    if (.not. lc_found) then\n      lc_num = lc_num + 1\n      call lc_tmp(lc_num)%instantiate(std_name='cloud_ice_dry_mixing_ratio', long_name='Cloud ice dry mixing ratio', units='kg kg-1', errcode=errflg, errmsg=errmsg, advected=.true., default_value=0.0_kind_phys)\n      if (errflg /= 0) return\n    end if\n    do lc_i = 1, size(host_constituents)\n      lc_found = .false.\n      do lc_j = 1, lc_num\n        if (trim(lc_tmp(lc_j)%std_name) == trim(host_constituents(lc_i)%std_name)) then\n          lc_found = .true.\n          if (trim(lc_tmp(lc_j)%units) /= trim(host_constituents(lc_i)%units)) then\n            write(errmsg, '(3a)') 'ccp_model_const_add_metadata ERROR: Trying to add constituent ', trim(host_constituents(lc_i)%std_name), &\n              ' but an incompatible constituent with this name already exists'\n            errflg = 1\n            return\n          end if\n          exit\n        end if\n      end do\n      if (.not. lc_found) then\n        lc_num = lc_num + 1\n        lc_tmp(lc_num) = host_constituents(lc_i)\n      end if\n    end do\n    if (allocated(lc_all_constituents)) deallocate(lc_all_constituents)\n    allocate(lc_all_constituents(lc_num))\n    lc_all_constituents(1:lc_num) = lc_tmp(1:lc_num)\n    deallocate(lc_tmp)\n    if (allocated(lc_const_props)) deallocate(lc_const_props)\n    allocate(lc_const_props(lc_num))\n    do lc_i = 1, lc_num\n      lc_const_props(lc_i)%ptr => lc_all_constituents(lc_i)\n    end do\n    call ccpp_scheme_utils_set_constituents(lc_all_constituents)\n  end subroutine Cld_ccpp_register_constituents\n\n  subroutine Cld_ccpp_number_constituents(num_advected, errmsg, errflg)\n    integer, intent(out) :: num_advected\n    character(len=512), intent(out) :: errmsg\n    integer, intent(out) :: errflg\n    errflg = 0\n    errmsg = ''\n    if (allocated(lc_all_constituents)) then\n      num_advected = size(lc_all_constituents)\n    else\n      num_advected = 0\n    end if\n  end subroutine Cld_ccpp_number_constituents\n\n  subroutine Cld_ccpp_initialize_constituents(ncols, pver, errflg, errmsg)\n    integer, intent(in) :: ncols\n    integer, intent(in) :: pver\n    integer, intent(out) :: errflg\n    character(len=512), intent(out) :: errmsg\n    integer :: lc_num, lc_i\n    errflg = 0\n    errmsg = ''\n    if (.not. allocated(lc_all_constituents)) then\n      errflg = 1\n      errmsg = 'ccpp_initialize_constituents: register_constituents not called'\n      return\n    end if\n    lc_num = size(lc_all_constituents)\n    if (allocated(lc_constituent_array)) deallocate(lc_constituent_array)\n    allocate(lc_constituent_array(ncols, pver, lc_num))\n    lc_constituent_array = 0.0_kind_phys\n    do lc_i = 1, lc_num\n      if (lc_all_constituents(lc_i)%default_val_set) then\n        lc_constituent_array(:, :, lc_i) = lc_all_constituents(lc_i)%default_val\n      end if\n    end do\n    if (allocated(lc_const_tend)) deallocate(lc_const_tend)\n    allocate(lc_const_tend(ncols, pver, lc_num))\n    lc_const_tend = 0.0_kind_phys\n    if (allocated(lc_tcld)) deallocate(lc_tcld)\n    allocate(lc_tcld(ncols, pver))\n    lc_tcld = 0.0_kind_phys\n    if (allocated(lc_temp)) deallocate(lc_temp)\n    allocate(lc_temp(ncols, pver))\n    lc_temp = 0.0_kind_phys\n    if (allocated(lc_qv)) deallocate(lc_qv)\n    allocate(lc_qv(ncols, pver))\n    lc_qv = 0.0_kind_phys\n    if (allocated(lc_ps)) deallocate(lc_ps)\n    allocate(lc_ps(ncols))\n    lc_ps = 0.0_kind_phys\n    nullify(lc_cld_liq_tend)\n    do lc_i = 1, lc_num\n      if (trim(lc_all_constituents(lc_i)%std_name) == 'cloud_liquid_dry_mixing_ratio') then\n        lc_cld_liq_tend => lc_const_tend(:, :, lc_i)\n        exit\n      end if\n    end do\n  end subroutine Cld_ccpp_initialize_constituents\n\n  function Cld_constituents_array() result(ptr)\n    real(kind=kind_phys), pointer :: ptr(:, :, :)\n    ptr => lc_constituent_array\n  end function Cld_constituents_array\n\n  subroutine Cld_const_get_index(std_name, index, errflg, errmsg)\n    character(len=*), intent(in) :: std_name\n    integer, intent(out) :: index\n    integer, intent(out) :: errflg\n    character(len=512), intent(out) :: errmsg\n    integer :: lc_i\n    errflg = 0\n    errmsg = ''\n    index = -1\n    if (.not. allocated(lc_all_constituents)) then\n      errflg = 1\n      errmsg = 'const_get_index: constituents not registered'\n      return\n    end if\n    do lc_i = 1, size(lc_all_constituents)\n      if (trim(lc_all_constituents(lc_i)%std_name) == trim(std_name)) then\n        index = lc_i\n        return\n      end if\n    end do\n    errflg = 1\n    write(errmsg, '(3a)') 'const_get_index: constituent ', trim(std_name), ' not found'\n  end subroutine Cld_const_get_index\n\n  function Cld_model_const_properties() result(ptr)\n    type(ccpp_constituent_prop_ptr_t), pointer :: ptr(:)\n    ptr => lc_const_props\n  end function Cld_model_const_properties", public_names = ["Cld_ccpp_is_scheme_constituent", "Cld_ccpp_deallocate_dynamic_constituents", "Cld_ccpp_register_constituents", "Cld_ccpp_number_constituents", "Cld_ccpp_initialize_constituents", "Cld_constituents_array", "Cld_const_get_index", "Cld_model_const_properties"]}> : () -> ()
// CHECK-LABEL:     func.func private @cld_suite_suite_register(memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>, memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>) -> (memref<512xi8>, memref<i32>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_suite_initialize(memref<512xi8>, memref<i32>, memref<?x512xi8>, memref<?xi32>, memref<!ccpp_utils.real_kind<"kind_phys">>) -> (memref<i32>, memref<512xi8>, memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_suite_finalize() -> (memref<i32>, memref<512xi8>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_suite_timestep_initial() -> (memref<i32>, memref<512xi8>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_suite_timestep_final() -> (memref<i32>, memref<512xi8>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_suite_physics(memref<512xi8>, memref<i32>, memref<?x512xi8>, memref<?xi32>, memref<i32>, memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>) -> (memref<i32>, memref<512xi8>, memref<i32>) attributes {module = "cld_suite_cap"}
// CHECK:         }
// CHECK-LABEL:   builtin.module @ccpp_kinds {
// CHECK:           "ccpp_utils.kind_def"() <{kind_name = "kind_phys", kind_value = "REAL64"}> : () -> ()
// CHECK-NEXT:    }
// CHECK-NEXT:  }
