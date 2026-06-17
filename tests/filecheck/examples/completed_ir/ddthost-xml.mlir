// Test the completed IR for the ddthost XML frontend.
// Exercises: DDT argument types (!ccpp_utils.derived_type<"vmr_type">) in
// func signatures and call sites, and optional entry points
// (make_ddt_timestep_final present, make_ddt_finalize absent).
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/ddthost/ddt_suite.xml --scheme-files examples/ddthost/make_ddt.meta,examples/ddthost/environ_conditions.meta --host-files examples/ddthost/test_host_data.meta,examples/ddthost/test_host_mod.meta,examples/ddthost/host_ccpp_ddt.meta,examples/ddthost/test_host.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap,generate-kinds,strip-ccpp | python3 -m filecheck %s

// --- Suite cap module ---

// CHECK:       builtin.module {
// CHECK-LABEL:   builtin.module @ddt_suite_cap {
// CHECK:           "llvm.mlir.global"() <{global_type = !llvm.array<16 x i8>, sym_name = "ccpp_suite_state", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, value = "uninitialized"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<16 x i8>, sym_name = "const_in_time_step", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "in_time_step"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<16 x i8>, sym_name = "const_initialized", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "initialized"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<16 x i8>, sym_name = "const_uninitialized", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "uninitialized"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<0 x i8>, sym_name = "vmr_type", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "make_ddt"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<0 x i8>, sym_name = "ccpp_info_t", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "host_ccpp_ddt"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "ncols", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "num_model_times", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "vmr", fortran_type = "type(vmr_type)", rank = 0 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "o3", fortran_type = "real(kind=kind_phys)", rank = 1 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "hno3", fortran_type = "real(kind=kind_phys)", rank = 1 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "ntimes", fortran_type = "integer", rank = 0 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "model_times", fortran_type = "integer", rank = 1 : i64}> : () -> ()
// CHECK-LABEL:     func.func public @ddt_suite_suite_register() -> (memref<i32>, memref<512xi8>) {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %ncols = "ccpp_utils.host_var_ref"() <{var_name = "ncols", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:        %num_model_times = "ccpp_utils.host_var_ref"() <{var_name = "num_model_times", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ncols) <{var_name = "o3", kind_name = "kind_phys"}> : (memref<i32>) -> ()
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ncols) <{var_name = "hno3", kind_name = "kind_phys"}> : (memref<i32>) -> ()
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%num_model_times) <{var_name = "model_times", kind_name = "kind_phys"}> : (memref<i32>) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ddt_suite_suite_initialize(%nbox : memref<i32>, %ccpp_info : memref<!ccpp_utils.derived_type<"ccpp_info_t">>, %o3 : memref<?x!ccpp_utils.real_kind<"kind_phys">>, %hno3 : memref<?x!ccpp_utils.real_kind<"kind_phys">>, %model_times__alloc : memref<?xi32>) -> (memref<!ccpp_utils.derived_type<"vmr_type">>, memref<512xi8>, memref<i32>, memref<i32>) {
// CHECK:             %vmr = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<!ccpp_utils.derived_type<"vmr_type">>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %ntimes = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%nbox) <{var_name = "o3", kind_name = "kind_phys"}> : (memref<i32>) -> ()
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%nbox) <{var_name = "hno3", kind_name = "kind_phys"}> : (memref<i32>) -> ()
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ntimes) <{var_name = "model_times", kind_name = "kind_phys"}> : (memref<i32>) -> ()
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_uninitialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        %4 = "llvm.load"(%3) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %5 = "ccpp_utils.strcmp"(%2, %4) <{length = 13 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %6 = arith.constant true
// CHECK-NEXT:        %7 = arith.xori %5, %6 : i1
// CHECK-NEXT:        scf.if %7 {
// CHECK-NEXT:          %8 = "ccpp_utils.trim"(%4) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in ddt_suite_initialize"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = arith.constant 0 : i32
// CHECK-NEXT:        %11 = arith.cmpi eq, %12, %10 : i32
// CHECK-NEXT:        %12 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %11 {
// CHECK-NEXT:          func.call @make_ddt_init(%nbox, %ccpp_info, %vmr, %errmsg, %errflg) : (memref<i32>, memref<!ccpp_utils.derived_type<"ccpp_info_t">>, memref<!ccpp_utils.derived_type<"vmr_type">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %13 = arith.constant 0 : i32
// CHECK-NEXT:        %14 = arith.cmpi eq, %15, %13 : i32
// CHECK-NEXT:        %15 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %14 {
// CHECK-NEXT:          func.call @environ_conditions_init(%nbox, %o3, %hno3, %ntimes, %model_times__alloc, %errmsg, %errflg) : (memref<i32>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<?xi32>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %16 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %17 = "llvm.load"(%16) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %18 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%17, %18) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %vmr, %errmsg, %errflg, %ntimes : memref<!ccpp_utils.derived_type<"vmr_type">>, memref<512xi8>, memref<i32>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ddt_suite_suite_finalize(%ntimes : memref<i32>, %model_times__in : memref<?xi32>) -> (memref<512xi8>, memref<i32>) {
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
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in ddt_suite_finalize"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = arith.constant 0 : i32
// CHECK-NEXT:        %11 = arith.cmpi eq, %12, %10 : i32
// CHECK-NEXT:        %12 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %11 {
// CHECK-NEXT:          func.call @environ_conditions_finalize(%ntimes, %model_times__in, %errmsg, %errflg) : (memref<i32>, memref<?xi32>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %13 = "llvm.mlir.addressof"() <{global_name = @const_uninitialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %14 = "llvm.load"(%13) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %15 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%14, %15) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ddt_suite_suite_timestep_initial() -> (memref<i32>, memref<512xi8>) {
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
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in ddt_suite_timestep_initial"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = "llvm.mlir.addressof"() <{global_name = @const_in_time_step}> : () -> !llvm.ptr
// CHECK-NEXT:        %11 = "llvm.load"(%10) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %12 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%11, %12) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ddt_suite_suite_timestep_final() -> (memref<i32>, memref<512xi8>) {
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
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in ddt_suite_timestep_final"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %11 = "llvm.load"(%10) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %12 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%11, %12) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ddt_suite_suite_data_prep(%cols : memref<i32>, %cole : memref<i32>, %O3__in : memref<?x!ccpp_utils.real_kind<"kind_phys">>, %HNO3__in : memref<?x!ccpp_utils.real_kind<"kind_phys">>, %vmr : memref<!ccpp_utils.derived_type<"vmr_type">>, %psurf__in : memref<?x!ccpp_utils.real_kind<"kind_phys">>) -> (memref<!ccpp_utils.derived_type<"vmr_type">>, memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
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
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in ddt_suite_data_prep"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = arith.constant 0 : i32
// CHECK-NEXT:        %11 = arith.cmpi eq, %12, %10 : i32
// CHECK-NEXT:        %12 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %11 {
// CHECK-NEXT:          func.call @make_ddt_run(%cols, %cole, %O3__in, %HNO3__in, %vmr, %errmsg, %errflg) : (memref<i32>, memref<i32>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.derived_type<"vmr_type">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %13 = arith.constant 0 : i32
// CHECK-NEXT:        %14 = arith.cmpi eq, %15, %13 : i32
// CHECK-NEXT:        %15 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %14 {
// CHECK-NEXT:          func.call @environ_conditions_run(%psurf__in, %errmsg, %errflg) : (memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %vmr, %errmsg, %errflg : memref<!ccpp_utils.derived_type<"vmr_type">>, memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func private @make_ddt_init(memref<i32>, memref<!ccpp_utils.derived_type<"ccpp_info_t">>, memref<!ccpp_utils.derived_type<"vmr_type">>, memref<512xi8>, memref<i32>) -> () attributes {module = "make_ddt"}
// CHECK-LABEL:     func.func private @environ_conditions_init(memref<i32>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<?xi32>, memref<512xi8>, memref<i32>) -> () attributes {module = "environ_conditions"}
// CHECK-LABEL:     func.func private @environ_conditions_finalize(memref<i32>, memref<?xi32>, memref<512xi8>, memref<i32>) -> () attributes {module = "environ_conditions"}
// CHECK-LABEL:     func.func private @make_ddt_run(memref<i32>, memref<i32>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.derived_type<"vmr_type">>, memref<512xi8>, memref<i32>) -> () attributes {module = "make_ddt"}
// CHECK-LABEL:     func.func private @environ_conditions_run(memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "environ_conditions"}
// CHECK:         }
// CHECK-LABEL:   builtin.module @Ddt_ccpp_cap {
// CHECK:           "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "ncols", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "model_times", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "num_model_times", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<9 x i8>, sym_name = "str_ddt_suite", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "ddt_suite"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<9 x i8>, sym_name = "str_data_prep", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "data_prep"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<0 x i8>, sym_name = "vmr_type", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "make_ddt"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<0 x i8>, sym_name = "ccpp_info_t", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "host_ccpp_ddt"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<0 x i8>, sym_name = "physics_state", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_data"} : () -> ()
// CHECK-LABEL:     func.func public @Ddt_ccpp_physics_register(%suite_name : memref<?xi8>, %ccpp_info : memref<!ccpp_utils.derived_type<"ccpp_info_t">>) -> memref<!ccpp_utils.derived_type<"ccpp_info_t">> {
// CHECK:             %0 = "ccpp_utils.host_var_ref"() <{var_name = "ccpp_info", module_name = "host_ccpp_ddt"}> {member_name = "errmsg"} : () -> memref<512xi8>
// CHECK-NEXT:        %1 = "ccpp_utils.host_var_ref"() <{var_name = "ccpp_info", module_name = "host_ccpp_ddt"}> {member_name = "errflg"} : () -> memref<i32>
// CHECK-NEXT:        %2 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %2, %1[] : memref<i32>
// CHECK-NEXT:        %3 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %4 = "ccpp_utils.strcmp"(%3) <{literal = "ddt_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %4 {
// CHECK-NEXT:          %5, %6 = func.call @ddt_suite_suite_register() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:          "memref.copy"(%5, %1) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          "memref.copy"(%6, %0) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%0, %3) <{prefix = "No suite named ", suffix = "found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %7 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %7, %1[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %ccpp_info : memref<!ccpp_utils.derived_type<"ccpp_info_t">>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @Ddt_ccpp_physics_initialize(%suite_name : memref<?xi8>, %ccpp_info : memref<!ccpp_utils.derived_type<"ccpp_info_t">>) -> memref<!ccpp_utils.derived_type<"ccpp_info_t">> {
// CHECK:             %0 = "ccpp_utils.host_var_ref"() <{var_name = "ccpp_info", module_name = "host_ccpp_ddt"}> {member_name = "errmsg"} : () -> memref<512xi8>
// CHECK-NEXT:        %1 = "ccpp_utils.host_var_ref"() <{var_name = "ccpp_info", module_name = "host_ccpp_ddt"}> {member_name = "errflg"} : () -> memref<i32>
// CHECK-NEXT:        %2 = arith.constant 0 : index
// CHECK-NEXT:        %lc_o3__alloc = "memref.alloca"(%2) <{operandSegmentSizes = array<i32: 1, 0>}> : (index) -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %3 = arith.constant 0 : index
// CHECK-NEXT:        %lc_hno3__alloc = "memref.alloca"(%3) <{operandSegmentSizes = array<i32: 1, 0>}> : (index) -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %4 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %4, %1[] : memref<i32>
// CHECK-NEXT:        %5 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %6 = "ccpp_utils.strcmp"(%5) <{literal = "ddt_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %6 {
// CHECK-NEXT:          %7 = "ccpp_utils.host_var_ref"() <{var_name = "ncols", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:          %8 = "ccpp_utils.host_var_ref"() <{var_name = "model_times", module_name = "test_host_mod"}> : () -> memref<?xi32>
// CHECK-NEXT:          %9 = "ccpp_utils.host_var_ref"() <{var_name = "num_model_times", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:          %10, %11, %12, %13 = func.call @ddt_suite_suite_initialize(%7, %ccpp_info, %lc_o3__alloc, %lc_hno3__alloc, %8) : (memref<i32>, memref<!ccpp_utils.derived_type<"ccpp_info_t">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?xi32>) -> (memref<!ccpp_utils.derived_type<"vmr_type">>, memref<512xi8>, memref<i32>, memref<i32>)
// CHECK-NEXT:          "memref.copy"(%11, %0) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:          "memref.copy"(%12, %1) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          "memref.copy"(%13, %9) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%0, %5) <{prefix = "No suite named ", suffix = "found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %14 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %14, %1[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %ccpp_info : memref<!ccpp_utils.derived_type<"ccpp_info_t">>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @Ddt_ccpp_physics_finalize(%suite_name : memref<?xi8>, %ccpp_info : memref<!ccpp_utils.derived_type<"ccpp_info_t">>) -> memref<!ccpp_utils.derived_type<"ccpp_info_t">> {
// CHECK:             %0 = "ccpp_utils.host_var_ref"() <{var_name = "ccpp_info", module_name = "host_ccpp_ddt"}> {member_name = "errmsg"} : () -> memref<512xi8>
// CHECK-NEXT:        %1 = "ccpp_utils.host_var_ref"() <{var_name = "ccpp_info", module_name = "host_ccpp_ddt"}> {member_name = "errflg"} : () -> memref<i32>
// CHECK-NEXT:        %2 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %2, %1[] : memref<i32>
// CHECK-NEXT:        %3 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %4 = "ccpp_utils.strcmp"(%3) <{literal = "ddt_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %4 {
// CHECK-NEXT:          %5 = "ccpp_utils.host_var_ref"() <{var_name = "num_model_times", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:          %6 = "ccpp_utils.host_var_ref"() <{var_name = "model_times", module_name = "test_host_mod"}> : () -> memref<?xi32>
// CHECK-NEXT:          %7, %8 = func.call @ddt_suite_suite_finalize(%5, %6) : (memref<i32>, memref<?xi32>) -> (memref<512xi8>, memref<i32>)
// CHECK-NEXT:          "memref.copy"(%7, %0) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:          "memref.copy"(%8, %1) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%0, %3) <{prefix = "No suite named ", suffix = "found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %1[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %ccpp_info : memref<!ccpp_utils.derived_type<"ccpp_info_t">>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @Ddt_ccpp_physics_timestep_initial(%suite_name : memref<?xi8>, %ccpp_info : memref<!ccpp_utils.derived_type<"ccpp_info_t">>) -> memref<!ccpp_utils.derived_type<"ccpp_info_t">> {
// CHECK:             %0 = "ccpp_utils.host_var_ref"() <{var_name = "ccpp_info", module_name = "host_ccpp_ddt"}> {member_name = "errmsg"} : () -> memref<512xi8>
// CHECK-NEXT:        %1 = "ccpp_utils.host_var_ref"() <{var_name = "ccpp_info", module_name = "host_ccpp_ddt"}> {member_name = "errflg"} : () -> memref<i32>
// CHECK-NEXT:        %2 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %2, %1[] : memref<i32>
// CHECK-NEXT:        %3 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %4 = "ccpp_utils.strcmp"(%3) <{literal = "ddt_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %4 {
// CHECK-NEXT:          %5, %6 = func.call @ddt_suite_suite_timestep_initial() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:          "memref.copy"(%5, %1) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          "memref.copy"(%6, %0) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%0, %3) <{prefix = "No suite named ", suffix = "found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %7 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %7, %1[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %ccpp_info : memref<!ccpp_utils.derived_type<"ccpp_info_t">>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @Ddt_ccpp_physics_timestep_final(%suite_name : memref<?xi8>, %ccpp_info : memref<!ccpp_utils.derived_type<"ccpp_info_t">>) -> memref<!ccpp_utils.derived_type<"ccpp_info_t">> {
// CHECK:             %0 = "ccpp_utils.host_var_ref"() <{var_name = "ccpp_info", module_name = "host_ccpp_ddt"}> {member_name = "errmsg"} : () -> memref<512xi8>
// CHECK-NEXT:        %1 = "ccpp_utils.host_var_ref"() <{var_name = "ccpp_info", module_name = "host_ccpp_ddt"}> {member_name = "errflg"} : () -> memref<i32>
// CHECK-NEXT:        %2 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %2, %1[] : memref<i32>
// CHECK-NEXT:        %3 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %4 = "ccpp_utils.strcmp"(%3) <{literal = "ddt_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %4 {
// CHECK-NEXT:          %5, %6 = func.call @ddt_suite_suite_timestep_final() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:          "memref.copy"(%5, %1) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          "memref.copy"(%6, %0) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%0, %3) <{prefix = "No suite named ", suffix = "found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %7 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %7, %1[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %ccpp_info : memref<!ccpp_utils.derived_type<"ccpp_info_t">>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @Ddt_ccpp_physics_run(%suite_name : memref<?xi8>, %suite_part : memref<?xi8>, %ccpp_info : memref<!ccpp_utils.derived_type<"ccpp_info_t">>, %O3__in : memref<?x!ccpp_utils.real_kind<"kind_phys">>, %HNO3__in : memref<?x!ccpp_utils.real_kind<"kind_phys">>, %vmr : memref<!ccpp_utils.derived_type<"vmr_type">>, %psurf__in : memref<?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<!ccpp_utils.derived_type<"ccpp_info_t">> {
// CHECK:             %0 = "ccpp_utils.host_var_ref"() <{var_name = "ccpp_info", module_name = "host_ccpp_ddt"}> {member_name = "col_start"} : () -> memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.host_var_ref"() <{var_name = "ccpp_info", module_name = "host_ccpp_ddt"}> {member_name = "col_end"} : () -> memref<i32>
// CHECK-NEXT:        %2 = "ccpp_utils.host_var_ref"() <{var_name = "ccpp_info", module_name = "host_ccpp_ddt"}> {member_name = "errmsg"} : () -> memref<512xi8>
// CHECK-NEXT:        %3 = "ccpp_utils.host_var_ref"() <{var_name = "ccpp_info", module_name = "host_ccpp_ddt"}> {member_name = "errflg"} : () -> memref<i32>
// CHECK-NEXT:        %4 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %4, %3[] : memref<i32>
// CHECK-NEXT:        %5 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %6 = "ccpp_utils.strcmp"(%5) <{literal = "ddt_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %6 {
// CHECK-NEXT:          %7 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:          %8 = "ccpp_utils.strcmp"(%7) <{literal = "data_prep"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %8 {
// CHECK-NEXT:            %9, %10, %11 = func.call @ddt_suite_suite_data_prep(%0, %1, %O3__in, %HNO3__in, %vmr, %psurf__in) : (memref<i32>, memref<i32>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.derived_type<"vmr_type">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>) -> (memref<!ccpp_utils.derived_type<"vmr_type">>, memref<512xi8>, memref<i32>)
// CHECK-NEXT:            "memref.copy"(%10, %2) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:            "memref.copy"(%11, %3) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%2, %7) <{prefix = "No suite part named ", suffix = " found in suite ddt_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %12 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %12, %3[] : memref<i32>
// CHECK-NEXT:          }
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%2, %5) <{prefix = "No suite named ", suffix = "found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %13 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %13, %3[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %ccpp_info : memref<!ccpp_utils.derived_type<"ccpp_info_t">>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_physics_suite_list(%suites : memref<memref<?xi8>>) {
// CHECK:             %0 = arith.constant 9 : index
// CHECK-NEXT:        %1 = memref.alloc(%0) : memref<?xi8>
// CHECK-NEXT:        %2 = "llvm.mlir.addressof"() <{global_name = @str_ddt_suite}> : () -> !llvm.ptr
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
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "ddt_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = arith.constant 9 : index
// CHECK-NEXT:          %4 = memref.alloc(%3) : memref<?xi8>
// CHECK-NEXT:          %5 = "llvm.mlir.addressof"() <{global_name = @str_data_prep}> : () -> !llvm.ptr
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
// CHECK-NEXT:      "ccpp_utils.suite_variables"() <{body = "subroutine ccpp_physics_suite_variables(suite_name, var_list, errmsg, errflg, input_vars, output_vars)\n  character(len=*), intent(in) :: suite_name\n  character(len=*), allocatable, intent(out) :: var_list(:)\n  character(len=512), intent(out) :: errmsg\n  integer, intent(out) :: errflg\n  logical, optional, intent(in) :: input_vars\n  logical, optional, intent(in) :: output_vars\n  logical :: do_input, do_output\n  errmsg = ''\n  errflg = 0\n  do_input = .true.\n  do_output = .true.\n  if (present(input_vars)) do_input = input_vars\n  if (present(output_vars)) do_output = output_vars\n  if (trim(suite_name) .eq. 'ddt_suite') then\n    if (do_input .and. .not. do_output) then\n      allocate(var_list(4))\n      var_list(1) = 'host_standard_ccpp_type             '\n      var_list(2) = 'model_times                         '\n      var_list(3) = 'number_of_model_times               '\n      var_list(4) = 'surface_air_pressure                '\n    else if (.not. do_input .and. do_output) then\n      allocate(var_list(5))\n      var_list(1) = 'ccpp_error_code                     '\n      var_list(2) = 'ccpp_error_message                  '\n      var_list(3) = 'model_times                         '\n      var_list(4) = 'number_of_model_times               '\n      var_list(5) = 'surface_air_pressure                '\n    else\n      allocate(var_list(6))\n      var_list(1) = 'ccpp_error_code                     '\n      var_list(2) = 'ccpp_error_message                  '\n      var_list(3) = 'host_standard_ccpp_type             '\n      var_list(4) = 'model_times                         '\n      var_list(5) = 'number_of_model_times               '\n      var_list(6) = 'surface_air_pressure                '\n    end if\n  else\n    write(errmsg, '(3a)') \"No suite named \", trim(suite_name), \" found\"\n    errflg = 1\n  end if\nend subroutine ccpp_physics_suite_variables"}> : () -> ()
// CHECK-LABEL:     func.func private @ddt_suite_suite_register() -> (memref<i32>, memref<512xi8>) attributes {module = "ddt_suite_cap"}
// CHECK-LABEL:     func.func private @ddt_suite_suite_initialize(memref<i32>, memref<!ccpp_utils.derived_type<"ccpp_info_t">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?xi32>) -> (memref<!ccpp_utils.derived_type<"vmr_type">>, memref<512xi8>, memref<i32>, memref<i32>) attributes {module = "ddt_suite_cap"}
// CHECK-LABEL:     func.func private @ddt_suite_suite_finalize(memref<i32>, memref<?xi32>) -> (memref<512xi8>, memref<i32>) attributes {module = "ddt_suite_cap"}
// CHECK-LABEL:     func.func private @ddt_suite_suite_timestep_initial() -> (memref<i32>, memref<512xi8>) attributes {module = "ddt_suite_cap"}
// CHECK-LABEL:     func.func private @ddt_suite_suite_timestep_final() -> (memref<i32>, memref<512xi8>) attributes {module = "ddt_suite_cap"}
// CHECK-LABEL:     func.func private @ddt_suite_suite_data_prep(memref<i32>, memref<i32>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.derived_type<"vmr_type">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>) -> (memref<!ccpp_utils.derived_type<"vmr_type">>, memref<512xi8>, memref<i32>) attributes {module = "ddt_suite_cap"}
// CHECK:         }
// CHECK-LABEL:   builtin.module @ccpp_kinds {
// CHECK:           "ccpp_utils.kind_def"() <{kind_name = "kind_phys", kind_value = "REAL64"}> : () -> ()
// CHECK-NEXT:    }
// CHECK-NEXT:  }
