// Test the completed IR (post-optimizer, pre-Fortran-backend) for the
// helloworld XML frontend.  Checks the module structure, public func
// signatures, scheme call sites, and the ccpp_kinds module.
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/helloworld/hello_world_suite.xml --scheme-files examples/helloworld/hello_scheme.meta,examples/helloworld/temp_adjust.meta --host-files examples/helloworld/hello_world_host.meta,examples/helloworld/hello_world_mod.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p generate-meta-cap,generate-meta-kinds,generate-host-match,generate-arg-ownership,generate-suite-cap,generate-ccpp-cap,generate-cpp-cap,generate-kinds,strip-ccpp | python3 -m filecheck %s

// --- Suite cap module ---

// CHECK:       builtin.module {
// CHECK-LABEL:   builtin.module @hello_world_suite_cap attributes {ccpp_suite_cap = "hello_world_suite"} {
// CHECK:           "llvm.mlir.global"() <{global_type = !llvm.array<16 x i8>, sym_name = "ccpp_suite_state", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, value = "uninitialized"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<16 x i8>, sym_name = "const_in_time_step", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "in_time_step"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<16 x i8>, sym_name = "const_initialized", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "initialized"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<16 x i8>, sym_name = "const_uninitialized", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "uninitialized"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-LABEL:     func.func public @hello_world_suite_register() -> (memref<i32>, memref<512xi8>) attributes {ccpp_phase = "suite_register"} {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @hello_world_suite_initialize() -> (memref<i32>, memref<512xi8>) attributes {ccpp_phase = "suite_initialize"} {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_uninitialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        %4 = "llvm.load"(%3) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %5 = "ccpp_utils.strcmp"(%2, %4) <{length = 13 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %6 = arith.constant true
// CHECK-NEXT:        %7 = arith.xori %5, %6 : i1
// CHECK-NEXT:        scf.if %7 {
// CHECK-NEXT:          %8 = "ccpp_utils.trim"(%4) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in hello_world_suite_initialize"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %11 = "llvm.load"(%10) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %12 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%11, %12) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @hello_world_suite_finalize() -> (memref<i32>, memref<512xi8>) attributes {ccpp_phase = "suite_finalize"} {
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
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in hello_world_suite_finalize"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = "llvm.mlir.addressof"() <{global_name = @const_uninitialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %11 = "llvm.load"(%10) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %12 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%11, %12) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @hello_world_suite_init_physics() -> (memref<512xi8>, memref<i32>) attributes {ccpp_phase = "group_init"} {
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
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in hello_world_suite_init_physics"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = arith.constant 0 : i32
// CHECK-NEXT:        %11 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %12 = arith.cmpi eq, %11, %10 : i32
// CHECK-NEXT:        scf.if %12 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%errmsg, %errflg) <{callee = "hello_scheme_init", operand_names = ["errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %13 = arith.constant 0 : i32
// CHECK-NEXT:        %14 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %15 = arith.cmpi eq, %14, %13 : i32
// CHECK-NEXT:        scf.if %15 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%errmsg, %errflg) <{callee = "temp_adjust_init", operand_names = ["errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @hello_world_suite_physics(%ncol : memref<i32> {ccpp.name = "ncol", ccpp.standard_name = "horizontal_dimension", ccpp.intent = "in"}, %lev : memref<i32> {ccpp.name = "lev", ccpp.standard_name = "vertical_layer_dimension", ccpp.intent = "in"}, %ilev : memref<i32> {ccpp.name = "ilev", ccpp.standard_name = "vertical_interface_dimension", ccpp.intent = "in"}, %timestep : memref<!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "timestep", ccpp.standard_name = "time_step_for_physics", ccpp.intent = "in"}, %temp_level : memref<?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "temp_level", ccpp.standard_name = "potential_temperature_at_interface", ccpp.intent = "inout", ccpp.dim_names = ["horizontal_dimension", "vertical_interface_dimension"]}, %temp_layer : memref<?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "temp_layer", ccpp.standard_name = "potential_temperature", ccpp.intent = "inout", ccpp.dim_names = ["horizontal_dimension", "vertical_layer_dimension"]}) -> (memref<512xi8>, memref<i32>) attributes {ccpp_phase = "run"} {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %temp_level_kind_cast = "ccpp_utils.kind_cast"(%temp_level) <{target_kind = "kind_dyn"}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<?x?x!ccpp_utils.real_kind<"kind_dyn">>
// CHECK-NEXT:        %temp_layer_unit_conv = "ccpp_utils.unit_convert"(%temp_layer) <{operation = "add", factor = "273.15"}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_in_time_step}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        %4 = "llvm.load"(%3) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %5 = "ccpp_utils.strcmp"(%2, %4) <{length = 12 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %6 = arith.constant true
// CHECK-NEXT:        %7 = arith.xori %5, %6 : i1
// CHECK-NEXT:        scf.if %7 {
// CHECK-NEXT:          %8 = "ccpp_utils.trim"(%4) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in hello_world_suite_physics"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = arith.constant 0 : i32
// CHECK-NEXT:        %11 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %12 = arith.cmpi eq, %11, %10 : i32
// CHECK-NEXT:        scf.if %12 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%ncol, %lev, %ilev, %timestep, %temp_level_kind_cast, %temp_layer_unit_conv, %errmsg, %errflg) <{callee = "hello_scheme_run", operand_names = ["ncol", "lev", "ilev", "timestep", "temp_level", "temp_layer", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<i32>, memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_dyn">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %13 = arith.constant 0 : i32
// CHECK-NEXT:        %14 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %15 = arith.cmpi eq, %14, %13 : i32
// CHECK-NEXT:        scf.if %15 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%ncol, %lev, %temp_layer_unit_conv, %timestep, %errmsg, %errflg) <{callee = "temp_adjust_run", operand_names = ["nbox", "lev", "temp_layer", "timestep", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<i32>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        "ccpp_utils.kind_write_back"(%temp_level_kind_cast, %temp_level) <{original_kind = "kind_phys"}> : (memref<?x?x!ccpp_utils.real_kind<"kind_dyn">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> ()
// CHECK-NEXT:        "ccpp_utils.unit_write_back"(%temp_layer_unit_conv, %temp_layer) <{operation = "sub", factor = "273.15"}> : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> ()
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @hello_world_suite_timestep_init_physics() -> (memref<i32>, memref<512xi8>) attributes {ccpp_phase = "timestep_init"} {
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
// CHECK-LABEL:     func.func public @hello_world_suite_timestep_final_physics() -> (memref<i32>, memref<512xi8>) attributes {ccpp_phase = "timestep_final"} {
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
// CHECK-LABEL:     func.func public @hello_world_suite_final_physics() -> (memref<512xi8>, memref<i32>) attributes {ccpp_phase = "group_final"} {
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
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in hello_world_suite_final_physics"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = arith.constant 0 : i32
// CHECK-NEXT:        %11 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %12 = arith.cmpi eq, %11, %10 : i32
// CHECK-NEXT:        scf.if %12 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%errmsg, %errflg) <{callee = "hello_scheme_finalize", operand_names = ["errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %13 = arith.constant 0 : i32
// CHECK-NEXT:        %14 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %15 = arith.cmpi eq, %14, %13 : i32
// CHECK-NEXT:        scf.if %15 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%errmsg, %errflg) <{callee = "temp_adjust_finalize", operand_names = ["errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func private @hello_scheme_init(memref<512xi8>, memref<i32>) -> () attributes {module = "hello_scheme"}
// CHECK-LABEL:     func.func private @temp_adjust_init(memref<512xi8>, memref<i32>) -> () attributes {module = "temp_adjust"}
// CHECK-LABEL:     func.func private @hello_scheme_run(memref<i32>, memref<i32>, memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_dyn">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "hello_scheme"}
// CHECK-LABEL:     func.func private @temp_adjust_run(memref<i32>, memref<i32>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "temp_adjust"}
// CHECK-LABEL:     func.func private @hello_scheme_finalize(memref<512xi8>, memref<i32>) -> () attributes {module = "hello_scheme"}
// CHECK-LABEL:     func.func private @temp_adjust_finalize(memref<512xi8>, memref<i32>) -> () attributes {module = "temp_adjust"}
// CHECK:         }
// CHECK-LABEL:   builtin.module @HelloWorld_ccpp_cap {
// CHECK:           "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "ncols", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "hello_world_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "pver", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "hello_world_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "pverp", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "hello_world_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "dt", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "hello_world_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "temp_interfaces", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "hello_world_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "temp_midpoints", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "hello_world_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<17 x i8>, sym_name = "str_hello_world_suite", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "hello_world_suite"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<7 x i8>, sym_name = "str_physics", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "physics"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-LABEL:     func.func public @ccpp_register(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "hello_world_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3, %4 = func.call @hello_world_suite_register() : () -> (memref<i32>, memref<512xi8>)
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
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "hello_world_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3, %4 = func.call @hello_world_suite_initialize() : () -> (memref<i32>, memref<512xi8>)
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
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "hello_world_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3, %4 = func.call @hello_world_suite_finalize() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:          "memref.copy"(%3, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          "memref.copy"(%4, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %5 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %5, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_physics_run(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}, %suite_part : memref<?xi8> {ccpp.name = "suite_part"}, %col_start : memref<i32> {ccpp.name = "col_start"}, %col_end : memref<i32> {ccpp.name = "col_end"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg"}, %errflg : memref<i32> {ccpp.name = "errflg"}) -> (memref<512xi8>, memref<i32>) attributes {bind_c_extents = [[], [], [], [], [], []]} {
// CHECK:             %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "hello_world_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:          %ncol = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:          %4 = memref.load %col_start[] : memref<i32>
// CHECK-NEXT:          %5 = memref.load %col_end[] : memref<i32>
// CHECK-NEXT:          %6 = arith.subi %5, %4 : i32
// CHECK-NEXT:          %7 = arith.constant 1 : i32
// CHECK-NEXT:          %8 = arith.addi %6, %7 : i32
// CHECK-NEXT:          memref.store %8, %ncol[] : memref<i32>
// CHECK-NEXT:          %9 = "ccpp_utils.host_var_ref"() <{var_name = "pver", module_name = "hello_world_mod"}> : () -> memref<i32>
// CHECK-NEXT:          %10 = "ccpp_utils.host_var_ref"() <{var_name = "pverp", module_name = "hello_world_mod"}> : () -> memref<i32>
// CHECK-NEXT:          %11 = "ccpp_utils.host_var_ref"() <{var_name = "dt", module_name = "hello_world_mod"}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %12 = "ccpp_utils.host_var_ref"() <{var_name = "temp_interfaces", module_name = "hello_world_mod"}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %13 = "ccpp_utils.host_var_ref"() <{var_name = "temp_midpoints", module_name = "hello_world_mod"}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %14 = arith.constant 1 : i32
// CHECK-NEXT:          %15 = "ccpp_utils.rank_reducing_slice"(%12, %col_start, %14, %col_end, %10) <{dim_pattern = "RR"}> {operandSegmentSizes = array<i32: 1, 2, 2, 0>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, memref<i32>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %16 = "ccpp_utils.rank_reducing_slice"(%13, %col_start, %14, %col_end, %9) <{dim_pattern = "RR"}> {operandSegmentSizes = array<i32: 1, 2, 2, 0>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, memref<i32>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %17 = "ccpp_utils.strcmp"(%3) <{literal = "physics"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %17 {
// CHECK-NEXT:            %18, %19 = func.call @hello_world_suite_physics(%ncol, %9, %10, %11, %15, %16) : (memref<i32>, memref<i32>, memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> (memref<512xi8>, memref<i32>)
// CHECK-NEXT:            "memref.copy"(%18, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:            "memref.copy"(%19, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %3) <{prefix = "No suite part named ", suffix = " found in suite hello_world_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %20 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %20, %errflg[] : memref<i32>
// CHECK-NEXT:          }
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %21 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %21, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_physics_timestep_init(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}, %suite_part : memref<?xi8> {ccpp.name = "suite_part"}, %col_start : memref<i32> {ccpp.name = "col_start"}, %col_end : memref<i32> {ccpp.name = "col_end"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg"}, %errflg : memref<i32> {ccpp.name = "errflg"}) -> (memref<512xi8>, memref<i32>) attributes {bind_c_extents = [[], [], [], [], [], []]} {
// CHECK:             %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "hello_world_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:          %4 = "ccpp_utils.strcmp"(%3) <{literal = "physics"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %4 {
// CHECK-NEXT:            %5, %6 = func.call @hello_world_suite_timestep_init_physics() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:            "memref.copy"(%5, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:            "memref.copy"(%6, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %3) <{prefix = "No suite part named ", suffix = " found in suite hello_world_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
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
// CHECK-LABEL:     func.func public @ccpp_physics_timestep_final(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}, %suite_part : memref<?xi8> {ccpp.name = "suite_part"}, %col_start : memref<i32> {ccpp.name = "col_start"}, %col_end : memref<i32> {ccpp.name = "col_end"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg"}, %errflg : memref<i32> {ccpp.name = "errflg"}) -> (memref<512xi8>, memref<i32>) attributes {bind_c_extents = [[], [], [], [], [], []]} {
// CHECK:             %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "hello_world_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:          %4 = "ccpp_utils.strcmp"(%3) <{literal = "physics"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %4 {
// CHECK-NEXT:            %5, %6 = func.call @hello_world_suite_timestep_final_physics() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:            "memref.copy"(%5, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:            "memref.copy"(%6, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %3) <{prefix = "No suite part named ", suffix = " found in suite hello_world_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
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
// CHECK-LABEL:     func.func public @ccpp_physics_init(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}, %suite_part : memref<?xi8> {ccpp.name = "suite_part"}, %col_start : memref<i32> {ccpp.name = "col_start"}, %col_end : memref<i32> {ccpp.name = "col_end"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg"}, %errflg : memref<i32> {ccpp.name = "errflg"}) -> (memref<512xi8>, memref<i32>) attributes {bind_c_extents = [[], [], [], [], [], []]} {
// CHECK:             %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "hello_world_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:          %4 = "ccpp_utils.strcmp"(%3) <{literal = "physics"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %4 {
// CHECK-NEXT:            %5, %6 = func.call @hello_world_suite_init_physics() : () -> (memref<512xi8>, memref<i32>)
// CHECK-NEXT:            "memref.copy"(%5, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:            "memref.copy"(%6, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %3) <{prefix = "No suite part named ", suffix = " found in suite hello_world_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
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
// CHECK-LABEL:     func.func public @ccpp_physics_final(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}, %suite_part : memref<?xi8> {ccpp.name = "suite_part"}, %col_start : memref<i32> {ccpp.name = "col_start"}, %col_end : memref<i32> {ccpp.name = "col_end"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg"}, %errflg : memref<i32> {ccpp.name = "errflg"}) -> (memref<512xi8>, memref<i32>) attributes {bind_c_extents = [[], [], [], [], [], []]} {
// CHECK:             %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "hello_world_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:          %4 = "ccpp_utils.strcmp"(%3) <{literal = "physics"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %4 {
// CHECK-NEXT:            %5, %6 = func.call @hello_world_suite_final_physics() : () -> (memref<512xi8>, memref<i32>)
// CHECK-NEXT:            "memref.copy"(%5, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:            "memref.copy"(%6, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %3) <{prefix = "No suite part named ", suffix = " found in suite hello_world_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
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
// CHECK:             %0 = arith.constant 17 : index
// CHECK-NEXT:        %1 = memref.alloc(%0) : memref<?xi8>
// CHECK-NEXT:        %2 = "llvm.mlir.addressof"() <{global_name = @str_hello_world_suite}> : () -> !llvm.ptr
// CHECK-NEXT:        %3 = "llvm.load"(%2) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<17 x i8>
// CHECK-NEXT:        "ccpp_utils.set_string"(%1, %3) : (memref<?xi8>, !llvm.array<17 x i8>) -> ()
// CHECK-NEXT:        memref.store %1, %suites[] : memref<memref<?xi8>>
// CHECK-NEXT:        func.return
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_physics_suite_part_list(%suite_name : memref<?xi8>, %part_list : memref<memref<?xi8>>) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "hello_world_suite"}> : (memref<?xi8>) -> i1
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
// CHECK-LABEL:     func.func public @ccpp_physics_suite_variables(%suite_name : memref<?xi8> {ccpp.name = "suite_name", ccpp.declared_intent = "in"}, %var_list : memref<memref<?xi8>> {ccpp.name = "var_list", ccpp.declared_intent = "out"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg", ccpp.declared_intent = "out"}, %errflg : memref<i32> {ccpp.name = "errflg", ccpp.declared_intent = "out"}, %input_vars : memref<i1> {ccpp.name = "input_vars", ccpp.declared_intent = "in", ccpp.optional}, %output_vars : memref<i1> {ccpp.name = "output_vars", ccpp.declared_intent = "in", ccpp.optional}) attributes {ccpp.fixed_interface} {
// CHECK:             %do_input = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> {ccpp.name = "do_input"} : () -> memref<i1>
// CHECK-NEXT:        %do_output = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> {ccpp.name = "do_output"} : () -> memref<i1>
// CHECK-NEXT:        "ccpp_utils.assign"() ({
// CHECK-NEXT:          "ccpp_utils.value_expr"(%errflg) : (memref<i32>) -> ()
// CHECK-NEXT:        }, {
// CHECK-NEXT:          %0 = arith.constant 0 : i32
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.assign"() ({
// CHECK-NEXT:          "ccpp_utils.value_expr"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        }, {
// CHECK-NEXT:          "ccpp_utils.string_literal_expr"() <{text = ""}> : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.assign"() ({
// CHECK-NEXT:          "ccpp_utils.value_expr"(%do_input) : (memref<i1>) -> ()
// CHECK-NEXT:        }, {
// CHECK-NEXT:          %1 = arith.constant true
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.assign"() ({
// CHECK-NEXT:          "ccpp_utils.value_expr"(%do_output) : (memref<i1>) -> ()
// CHECK-NEXT:        }, {
// CHECK-NEXT:          %2 = arith.constant true
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        %3 = "ccpp_utils.call_expr"() <{callee = "present"}> ({
// CHECK-NEXT:          "ccpp_utils.value_expr"(%input_vars) : (memref<i1>) -> ()
// CHECK-NEXT:        }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i1
// CHECK-NEXT:        scf.if %3 {
// CHECK-NEXT:          "ccpp_utils.assign"() ({
// CHECK-NEXT:            "ccpp_utils.value_expr"(%do_input) : (memref<i1>) -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.value_expr"(%input_vars) : (memref<i1>) -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %4 = "ccpp_utils.call_expr"() <{callee = "present"}> ({
// CHECK-NEXT:          "ccpp_utils.value_expr"(%output_vars) : (memref<i1>) -> ()
// CHECK-NEXT:        }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i1
// CHECK-NEXT:        scf.if %4 {
// CHECK-NEXT:          "ccpp_utils.assign"() ({
// CHECK-NEXT:            "ccpp_utils.value_expr"(%do_output) : (memref<i1>) -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.value_expr"(%output_vars) : (memref<i1>) -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %5 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %6 = "ccpp_utils.strcmp"(%5) <{literal = "hello_world_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %6 {
// CHECK-NEXT:          %7 = "ccpp_utils.value_expr"(%do_input) : (memref<i1>) -> i1
// CHECK-NEXT:          %8 = "ccpp_utils.value_expr"(%do_output) : (memref<i1>) -> i1
// CHECK-NEXT:          %9 = arith.constant true
// CHECK-NEXT:          %10 = arith.xori %8, %9 : i1
// CHECK-NEXT:          %11 = arith.andi %7, %10 : i1
// CHECK-NEXT:          scf.if %11 {
// CHECK-NEXT:            "ccpp_utils.allocate"() <{var_name = "var_list"}> ({
// CHECK-NEXT:              %12 = arith.constant 6 : i32
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 0, 1>} : () -> ()
// CHECK-NEXT:            "ccpp_utils.assign"() ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                %13 = arith.constant 1 : i32
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "horizontal_dimension                "}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:            "ccpp_utils.assign"() ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                %14 = arith.constant 2 : i32
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "potential_temperature               "}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:            "ccpp_utils.assign"() ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                %15 = arith.constant 3 : i32
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "potential_temperature_at_interface  "}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:            "ccpp_utils.assign"() ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                %16 = arith.constant 4 : i32
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "time_step_for_physics               "}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:            "ccpp_utils.assign"() ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                %17 = arith.constant 5 : i32
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "vertical_interface_dimension        "}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:            "ccpp_utils.assign"() ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                %18 = arith.constant 6 : i32
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "vertical_layer_dimension            "}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            %19 = "ccpp_utils.value_expr"(%do_input) : (memref<i1>) -> i1
// CHECK-NEXT:            %20 = arith.constant true
// CHECK-NEXT:            %21 = arith.xori %19, %20 : i1
// CHECK-NEXT:            %22 = "ccpp_utils.value_expr"(%do_output) : (memref<i1>) -> i1
// CHECK-NEXT:            %23 = arith.andi %21, %22 : i1
// CHECK-NEXT:            scf.if %23 {
// CHECK-NEXT:              "ccpp_utils.allocate"() <{var_name = "var_list"}> ({
// CHECK-NEXT:                %24 = arith.constant 4 : i32
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 0, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %25 = arith.constant 1 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "ccpp_error_code                     "}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %26 = arith.constant 2 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "ccpp_error_message                  "}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %27 = arith.constant 3 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "potential_temperature               "}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %28 = arith.constant 4 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "potential_temperature_at_interface  "}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            } else {
// CHECK-NEXT:              "ccpp_utils.allocate"() <{var_name = "var_list"}> ({
// CHECK-NEXT:                %29 = arith.constant 8 : i32
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 0, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %30 = arith.constant 1 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "ccpp_error_code                     "}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %31 = arith.constant 2 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "ccpp_error_message                  "}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %32 = arith.constant 3 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "horizontal_dimension                "}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %33 = arith.constant 4 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "potential_temperature               "}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %34 = arith.constant 5 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "potential_temperature_at_interface  "}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %35 = arith.constant 6 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "time_step_for_physics               "}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %36 = arith.constant 7 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "vertical_interface_dimension        "}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %37 = arith.constant 8 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "vertical_layer_dimension            "}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }
// CHECK-NEXT:          }
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %5) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %38 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %38, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func private @hello_world_suite_register() -> (memref<i32>, memref<512xi8>) attributes {module = "hello_world_suite_cap"}
// CHECK-LABEL:     func.func private @hello_world_suite_initialize() -> (memref<i32>, memref<512xi8>) attributes {module = "hello_world_suite_cap"}
// CHECK-LABEL:     func.func private @hello_world_suite_finalize() -> (memref<i32>, memref<512xi8>) attributes {module = "hello_world_suite_cap"}
// CHECK-LABEL:     func.func private @hello_world_suite_physics(memref<i32>, memref<i32>, memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> (memref<512xi8>, memref<i32>) attributes {module = "hello_world_suite_cap"}
// CHECK-LABEL:     func.func private @hello_world_suite_timestep_init_physics() -> (memref<i32>, memref<512xi8>) attributes {module = "hello_world_suite_cap"}
// CHECK-LABEL:     func.func private @hello_world_suite_timestep_final_physics() -> (memref<i32>, memref<512xi8>) attributes {module = "hello_world_suite_cap"}
// CHECK-LABEL:     func.func private @hello_world_suite_init_physics() -> (memref<512xi8>, memref<i32>) attributes {module = "hello_world_suite_cap"}
// CHECK-LABEL:     func.func private @hello_world_suite_final_physics() -> (memref<512xi8>, memref<i32>) attributes {module = "hello_world_suite_cap"}
// CHECK:         }
// CHECK-LABEL:   builtin.module @ccpp_kinds {
// CHECK:           "ccpp_utils.kind_def"() <{kind_name = "kind_phys", kind_value = "REAL64", kind_module = "iso_fortran_env"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.kind_def"() <{kind_name = "kind_dyn", kind_value = "kind_dyn", kind_module = "iso_fortran_env"}> : () -> ()
// CHECK-NEXT:    }
// CHECK-NEXT:  }
