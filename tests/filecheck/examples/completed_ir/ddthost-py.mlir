// Test the completed IR for the ddthost Python frontend.
// Should produce the same IR structure as the XML frontend.
//
// RUN: python3 examples/ddthost/ddthost_py.py | python3 -m xdsl_ccpp.tools.ccpp_opt -p generate-meta-cap,generate-meta-kinds,generate-suite-cap,generate-ccpp-cap,generate-kinds,strip-ccpp | python3 -m filecheck %s

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
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ddt_suite_suite_initialize(%nbox : memref<i32>, %ccpp_info : memref<!ccpp_utils.derived_type<"ccpp_info_t">>, %o3 : memref<?x!ccpp_utils.real_kind<"kind_phys">>, %hno3 : memref<?x!ccpp_utils.real_kind<"kind_phys">>, %model_times : memref<?xi32>) -> (memref<!ccpp_utils.derived_type<"vmr_type">>, memref<512xi8>, memref<i32>, memref<i32>) {
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
// CHECK-NEXT:          func.call @environ_conditions_init(%nbox, %o3, %hno3, %ntimes, %model_times, %errmsg, %errflg) : (memref<i32>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<?xi32>, memref<512xi8>, memref<i32>) -> ()
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
// CHECK-LABEL:     func.func public @ddt_suite_suite_timestep_final(%ncols : memref<i32>, %vmr : memref<!ccpp_utils.derived_type<"vmr_type">>) -> (memref<512xi8>, memref<i32>) {
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
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in ddt_suite_timestep_final"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = arith.constant 0 : i32
// CHECK-NEXT:        %11 = arith.cmpi eq, %12, %10 : i32
// CHECK-NEXT:        %12 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        scf.if %11 {
// CHECK-NEXT:          func.call @make_ddt_timestep_final(%ncols, %vmr, %errmsg, %errflg) : (memref<i32>, memref<!ccpp_utils.derived_type<"vmr_type">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %13 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %14 = "llvm.load"(%13) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %15 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%14, %15) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
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
// CHECK:           "llvm.mlir.global"() <{global_type = !llvm.array<9 x i8>, sym_name = "str_ddt_suite", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "ddt_suite"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<9 x i8>, sym_name = "str_data_prep", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "data_prep"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "ccpp_constituent_properties_t", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "ccpp_constituent_prop_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "ccpp_constituent_prop_ptr_t", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "ccpp_constituent_prop_mod"} : () -> ()
// CHECK-LABEL:     func.func public @Ddt_ccpp_physics_register(%suite_name : memref<?xi8>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "ddt_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3, %4 = func.call @ddt_suite_suite_register() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:          "memref.copy"(%3, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          "memref.copy"(%4, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = "found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %5 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %5, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @Ddt_ccpp_physics_initialize(%suite_name : memref<?xi8>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %lc_nbox = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %lc_ccpp_info = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<!ccpp_utils.derived_type<"ccpp_info_t">>
// CHECK-NEXT:        %0 = arith.constant 0 : index
// CHECK-NEXT:        %lc_o3__alloc = "memref.alloca"(%0) <{operandSegmentSizes = array<i32: 1, 0>}> : (index) -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %1 = arith.constant 0 : index
// CHECK-NEXT:        %lc_hno3__alloc = "memref.alloca"(%1) <{operandSegmentSizes = array<i32: 1, 0>}> : (index) -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %2 = arith.constant 0 : index
// CHECK-NEXT:        %lc_model_times__alloc = "memref.alloca"(%2) <{operandSegmentSizes = array<i32: 1, 0>}> : (index) -> memref<?xi32>
// CHECK-NEXT:        %3 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %3, %errflg[] : memref<i32>
// CHECK-NEXT:        %4 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %5 = "ccpp_utils.strcmp"(%4) <{literal = "ddt_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %5 {
// CHECK-NEXT:          %6 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_vmr"}> : () -> memref<!ccpp_utils.derived_type<"vmr_type">>
// CHECK-NEXT:          %7, %8, %9, %10 = func.call @ddt_suite_suite_initialize(%lc_nbox, %lc_ccpp_info, %lc_o3__alloc, %lc_hno3__alloc, %lc_model_times__alloc) : (memref<i32>, memref<!ccpp_utils.derived_type<"ccpp_info_t">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?xi32>) -> (memref<!ccpp_utils.derived_type<"vmr_type">>, memref<512xi8>, memref<i32>, memref<i32>)
// CHECK-NEXT:          "memref.copy"(%7, %6) : (memref<!ccpp_utils.derived_type<"vmr_type">>, memref<!ccpp_utils.derived_type<"vmr_type">>) -> ()
// CHECK-NEXT:          "memref.copy"(%8, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:          "memref.copy"(%9, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %4) <{prefix = "No suite named ", suffix = "found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %11 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %11, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @Ddt_ccpp_physics_finalize(%suite_name : memref<?xi8>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %lc_ntimes = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : index
// CHECK-NEXT:        %lc_model_times__alloc = "memref.alloca"(%0) <{operandSegmentSizes = array<i32: 1, 0>}> : (index) -> memref<?xi32>
// CHECK-NEXT:        %1 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %1, %errflg[] : memref<i32>
// CHECK-NEXT:        %2 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %3 = "ccpp_utils.strcmp"(%2) <{literal = "ddt_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %3 {
// CHECK-NEXT:          %4, %5 = func.call @ddt_suite_suite_finalize(%lc_ntimes, %lc_model_times__alloc) : (memref<i32>, memref<?xi32>) -> (memref<512xi8>, memref<i32>)
// CHECK-NEXT:          "memref.copy"(%4, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:          "memref.copy"(%5, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %2) <{prefix = "No suite named ", suffix = "found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %6 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %6, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @Ddt_ccpp_physics_timestep_initial(%suite_name : memref<?xi8>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "ddt_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3, %4 = func.call @ddt_suite_suite_timestep_initial() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:          "memref.copy"(%3, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          "memref.copy"(%4, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = "found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %5 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %5, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @Ddt_ccpp_physics_timestep_final(%suite_name : memref<?xi8>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %lc_ncols = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %lc_vmr = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<!ccpp_utils.derived_type<"vmr_type">>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "ddt_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3, %4 = func.call @ddt_suite_suite_timestep_final(%lc_ncols, %lc_vmr) : (memref<i32>, memref<!ccpp_utils.derived_type<"vmr_type">>) -> (memref<512xi8>, memref<i32>)
// CHECK-NEXT:          "memref.copy"(%3, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:          "memref.copy"(%4, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = "found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %5 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %5, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @Ddt_ccpp_physics_run(%suite_name : memref<?xi8>, %suite_part : memref<?xi8>, %errmsg : memref<512xi8>, %errflg : memref<i32>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "ddt_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:          %4 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_cols"}> : () -> memref<i32>
// CHECK-NEXT:          %5 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_cole"}> : () -> memref<i32>
// CHECK-NEXT:          %6 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_O3(:)"}> : () -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %7 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_HNO3(:)"}> : () -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %8 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_vmr"}> : () -> memref<!ccpp_utils.derived_type<"vmr_type">>
// CHECK-NEXT:          %9 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_psurf(:)"}> : () -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %10 = "ccpp_utils.strcmp"(%3) <{literal = "data_prep"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %10 {
// CHECK-NEXT:            %11, %12, %13 = func.call @ddt_suite_suite_data_prep(%4, %5, %6, %7, %8, %9) : (memref<i32>, memref<i32>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.derived_type<"vmr_type">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>) -> (memref<!ccpp_utils.derived_type<"vmr_type">>, memref<512xi8>, memref<i32>)
// CHECK-NEXT:            "memref.copy"(%12, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:            "memref.copy"(%13, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %3) <{prefix = "No suite part named ", suffix = " found in suite ddt_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %14 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %14, %errflg[] : memref<i32>
// CHECK-NEXT:          }
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = "found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %15 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %15, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
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
// CHECK-NEXT:      "ccpp_utils.suite_variables"() <{body = "subroutine ccpp_physics_suite_variables(suite_name, var_list, errmsg, errflg, input_vars, output_vars)\n  character(len=*), intent(in) :: suite_name\n  character(len=*), allocatable, intent(out) :: var_list(:)\n  character(len=512), intent(out) :: errmsg\n  integer, intent(out) :: errflg\n  logical, optional, intent(in) :: input_vars\n  logical, optional, intent(in) :: output_vars\n  logical :: do_input, do_output\n  errmsg = ''\n  errflg = 0\n  do_input = .true.\n  do_output = .true.\n  if (present(input_vars)) do_input = input_vars\n  if (present(output_vars)) do_output = output_vars\n  if (trim(suite_name) .eq. 'ddt_suite') then\n    if (do_input .and. .not. do_output) then\n      allocate(var_list(10))\n      var_list(1) = 'horizontal_dimension                '\n      var_list(2) = 'horizontal_loop_begin               '\n      var_list(3) = 'horizontal_loop_end                 '\n      var_list(4) = 'host_standard_ccpp_type             '\n      var_list(5) = 'model_times                         '\n      var_list(6) = 'nitric_acid                         '\n      var_list(7) = 'number_of_model_times               '\n      var_list(8) = 'ozone                               '\n      var_list(9) = 'surface_air_pressure                '\n      var_list(10) = 'volume_mixing_ratio_ddt             '\n    else if (.not. do_input .and. do_output) then\n      allocate(var_list(7))\n      var_list(1) = 'ccpp_error_code                     '\n      var_list(2) = 'ccpp_error_message                  '\n      var_list(3) = 'model_times                         '\n      var_list(4) = 'nitric_acid                         '\n      var_list(5) = 'number_of_model_times               '\n      var_list(6) = 'ozone                               '\n      var_list(7) = 'volume_mixing_ratio_ddt             '\n    else\n      allocate(var_list(12))\n      var_list(1) = 'ccpp_error_code                     '\n      var_list(2) = 'ccpp_error_message                  '\n      var_list(3) = 'horizontal_dimension                '\n      var_list(4) = 'horizontal_loop_begin               '\n      var_list(5) = 'horizontal_loop_end                 '\n      var_list(6) = 'host_standard_ccpp_type             '\n      var_list(7) = 'model_times                         '\n      var_list(8) = 'nitric_acid                         '\n      var_list(9) = 'number_of_model_times               '\n      var_list(10) = 'ozone                               '\n      var_list(11) = 'surface_air_pressure                '\n      var_list(12) = 'volume_mixing_ratio_ddt             '\n    end if\n  else\n    write(errmsg, '(3a)') \"No suite named \", trim(suite_name), \" found\"\n    errflg = 1\n  end if\nend subroutine ccpp_physics_suite_variables"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_all_constituents", fortran_type = "type(ccpp_constituent_properties_t), target", rank = 1 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_constituent_array", fortran_type = "real(kind=kind_phys), target", rank = 3 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_const_tend", fortran_type = "real(kind=kind_phys), target", rank = 3 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_const_props", fortran_type = "type(ccpp_constituent_prop_ptr_t), target", rank = 1 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_cols", fortran_type = "real(kind=kind_phys)", rank = 0 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_cole", fortran_type = "real(kind=kind_phys)", rank = 0 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_O3", fortran_type = "real(kind=kind_phys)", rank = 1 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_HNO3", fortran_type = "real(kind=kind_phys)", rank = 1 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_vmr", fortran_type = "real(kind=kind_phys)", rank = 0 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_psurf", fortran_type = "real(kind=kind_phys)", rank = 1 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.constituent_api"() <{body = "  subroutine Ddt_ccpp_is_scheme_constituent(std_name, is_const, errflg, errmsg)\n    character(len=*), intent(in) :: std_name\n    logical, intent(out) :: is_const\n    integer, intent(out) :: errflg\n    character(len=512), intent(out) :: errmsg\n    integer :: lc_idx\n    errflg = 0\n    errmsg = ''\n    is_const = .false.\n    select case (trim(std_name))\n    case default\n    end select\n  end subroutine Ddt_ccpp_is_scheme_constituent\n\n  subroutine Ddt_ccpp_deallocate_dynamic_constituents()\n    if (allocated(lc_all_constituents)) deallocate(lc_all_constituents)\n    if (allocated(lc_const_props)) deallocate(lc_const_props)\n    if (allocated(lc_constituent_array)) deallocate(lc_constituent_array)\n    if (allocated(lc_const_tend)) deallocate(lc_const_tend)\n    if (allocated(lc_cols)) deallocate(lc_cols)\n    if (allocated(lc_cole)) deallocate(lc_cole)\n    if (allocated(lc_O3)) deallocate(lc_O3)\n    if (allocated(lc_HNO3)) deallocate(lc_HNO3)\n    if (allocated(lc_vmr)) deallocate(lc_vmr)\n    if (allocated(lc_psurf)) deallocate(lc_psurf)\n  end subroutine Ddt_ccpp_deallocate_dynamic_constituents\n\n  subroutine Ddt_ccpp_register_constituents(host_constituents, errmsg, errflg)\n    use ccpp_scheme_utils, only: ccpp_scheme_utils_set_constituents\n    type(ccpp_constituent_properties_t), intent(in) :: host_constituents(:)\n    character(len=512), intent(out) :: errmsg\n    integer, intent(out) :: errflg\n    integer :: lc_max, lc_num, lc_i, lc_j\n    logical :: lc_found\n    type(ccpp_constituent_properties_t), allocatable :: lc_tmp(:)\n    errflg = 0\n    errmsg = ''\n    lc_max = 0\n    lc_max = lc_max + 0\n    lc_max = lc_max + size(host_constituents)\n    allocate(lc_tmp(lc_max))\n    lc_num = 0\n    do lc_i = 1, size(host_constituents)\n      lc_found = .false.\n      do lc_j = 1, lc_num\n        if (trim(lc_tmp(lc_j)%std_name) == trim(host_constituents(lc_i)%std_name)) then\n          lc_found = .true.\n          if (trim(lc_tmp(lc_j)%units) /= trim(host_constituents(lc_i)%units)) then\n            write(errmsg, '(3a)') 'ccp_model_const_add_metadata ERROR: Trying to add constituent ', trim(host_constituents(lc_i)%std_name), &\n              ' but an incompatible constituent with this name already exists'\n            errflg = 1\n            return\n          end if\n          exit\n        end if\n      end do\n      if (.not. lc_found) then\n        lc_num = lc_num + 1\n        lc_tmp(lc_num) = host_constituents(lc_i)\n      end if\n    end do\n    if (allocated(lc_all_constituents)) deallocate(lc_all_constituents)\n    allocate(lc_all_constituents(lc_num))\n    lc_all_constituents(1:lc_num) = lc_tmp(1:lc_num)\n    deallocate(lc_tmp)\n    if (allocated(lc_const_props)) deallocate(lc_const_props)\n    allocate(lc_const_props(lc_num))\n    do lc_i = 1, lc_num\n      lc_const_props(lc_i)%ptr => lc_all_constituents(lc_i)\n    end do\n    call ccpp_scheme_utils_set_constituents(lc_all_constituents)\n  end subroutine Ddt_ccpp_register_constituents\n\n  subroutine Ddt_ccpp_number_constituents(num_advected, errmsg, errflg)\n    integer, intent(out) :: num_advected\n    character(len=512), intent(out) :: errmsg\n    integer, intent(out) :: errflg\n    errflg = 0\n    errmsg = ''\n    if (allocated(lc_all_constituents)) then\n      num_advected = size(lc_all_constituents)\n    else\n      num_advected = 0\n    end if\n  end subroutine Ddt_ccpp_number_constituents\n\n  subroutine Ddt_ccpp_initialize_constituents(ncols, pver, errflg, errmsg)\n    integer, intent(in) :: ncols\n    integer, intent(in) :: pver\n    integer, intent(out) :: errflg\n    character(len=512), intent(out) :: errmsg\n    integer :: lc_num, lc_i\n    errflg = 0\n    errmsg = ''\n    if (.not. allocated(lc_all_constituents)) then\n      errflg = 1\n      errmsg = 'ccpp_initialize_constituents: register_constituents not called'\n      return\n    end if\n    lc_num = size(lc_all_constituents)\n    if (allocated(lc_constituent_array)) deallocate(lc_constituent_array)\n    allocate(lc_constituent_array(ncols, pver, lc_num))\n    lc_constituent_array = 0.0_kind_phys\n    do lc_i = 1, lc_num\n      if (lc_all_constituents(lc_i)%default_val_set) then\n        lc_constituent_array(:, :, lc_i) = lc_all_constituents(lc_i)%default_val\n      end if\n    end do\n    if (allocated(lc_const_tend)) deallocate(lc_const_tend)\n    allocate(lc_const_tend(ncols, pver, lc_num))\n    lc_const_tend = 0.0_kind_phys\n    if (allocated(lc_cols)) deallocate(lc_cols)\n    allocate(lc_cols(ncols, pver))\n    lc_cols = 0.0_kind_phys\n    if (allocated(lc_cole)) deallocate(lc_cole)\n    allocate(lc_cole(ncols, pver))\n    lc_cole = 0.0_kind_phys\n    if (allocated(lc_O3)) deallocate(lc_O3)\n    allocate(lc_O3(ncols))\n    lc_O3 = 0.0_kind_phys\n    if (allocated(lc_HNO3)) deallocate(lc_HNO3)\n    allocate(lc_HNO3(ncols))\n    lc_HNO3 = 0.0_kind_phys\n    if (allocated(lc_vmr)) deallocate(lc_vmr)\n    allocate(lc_vmr(ncols, pver))\n    lc_vmr = 0.0_kind_phys\n    if (allocated(lc_psurf)) deallocate(lc_psurf)\n    allocate(lc_psurf(ncols))\n    lc_psurf = 0.0_kind_phys\n  end subroutine Ddt_ccpp_initialize_constituents\n\n  function Ddt_constituents_array() result(ptr)\n    real(kind=kind_phys), pointer :: ptr(:, :, :)\n    ptr => lc_constituent_array\n  end function Ddt_constituents_array\n\n  subroutine Ddt_const_get_index(std_name, index, errflg, errmsg)\n    character(len=*), intent(in) :: std_name\n    integer, intent(out) :: index\n    integer, intent(out) :: errflg\n    character(len=512), intent(out) :: errmsg\n    integer :: lc_i\n    errflg = 0\n    errmsg = ''\n    index = -1\n    if (.not. allocated(lc_all_constituents)) then\n      errflg = 1\n      errmsg = 'const_get_index: constituents not registered'\n      return\n    end if\n    do lc_i = 1, size(lc_all_constituents)\n      if (trim(lc_all_constituents(lc_i)%std_name) == trim(std_name)) then\n        index = lc_i\n        return\n      end if\n    end do\n    errflg = 1\n    write(errmsg, '(3a)') 'const_get_index: constituent ', trim(std_name), ' not found'\n  end subroutine Ddt_const_get_index\n\n  function Ddt_model_const_properties() result(ptr)\n    type(ccpp_constituent_prop_ptr_t), pointer :: ptr(:)\n    ptr => lc_const_props\n  end function Ddt_model_const_properties", public_names = ["Ddt_ccpp_is_scheme_constituent", "Ddt_ccpp_deallocate_dynamic_constituents", "Ddt_ccpp_register_constituents", "Ddt_ccpp_number_constituents", "Ddt_ccpp_initialize_constituents", "Ddt_constituents_array", "Ddt_const_get_index", "Ddt_model_const_properties"]}> : () -> ()
// CHECK-LABEL:     func.func private @ddt_suite_suite_register() -> (memref<i32>, memref<512xi8>) attributes {module = "ddt_suite_cap"}
// CHECK-LABEL:     func.func private @ddt_suite_suite_initialize(memref<i32>, memref<!ccpp_utils.derived_type<"ccpp_info_t">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?xi32>) -> (memref<!ccpp_utils.derived_type<"vmr_type">>, memref<512xi8>, memref<i32>, memref<i32>) attributes {module = "ddt_suite_cap"}
// CHECK-LABEL:     func.func private @ddt_suite_suite_finalize(memref<i32>, memref<?xi32>) -> (memref<512xi8>, memref<i32>) attributes {module = "ddt_suite_cap"}
// CHECK-LABEL:     func.func private @ddt_suite_suite_timestep_initial() -> (memref<i32>, memref<512xi8>) attributes {module = "ddt_suite_cap"}
// CHECK-LABEL:     func.func private @ddt_suite_suite_timestep_final(memref<i32>, memref<!ccpp_utils.derived_type<"vmr_type">>) -> (memref<512xi8>, memref<i32>) attributes {module = "ddt_suite_cap"}
// CHECK-LABEL:     func.func private @ddt_suite_suite_data_prep(memref<i32>, memref<i32>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.derived_type<"vmr_type">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>) -> (memref<!ccpp_utils.derived_type<"vmr_type">>, memref<512xi8>, memref<i32>) attributes {module = "ddt_suite_cap"}
// CHECK:         }
// CHECK-LABEL:   builtin.module @ccpp_kinds {
// CHECK:           "ccpp_utils.kind_def"() <{kind_name = "kind_phys", kind_value = "REAL64"}> : () -> ()
// CHECK-NEXT:    }
// CHECK-NEXT:  }
