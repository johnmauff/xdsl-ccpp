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
// CHECK-LABEL:   builtin.module @cld_suite_cap attributes {ccpp_suite_cap = "cld_suite"} {
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
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "tcld", base_type = "real", rank = 0 : i64, kind = "kind_phys"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "cld_liq_tend", base_type = "real", rank = 2 : i64, kind = "kind_phys"}> : () -> ()
// CHECK-LABEL:     func.func public @cld_suite_register(%dyn_const : memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">> {ccpp.name = "dyn_const", ccpp.standard_name = "dynamic_constituents_for_cld_liq", ccpp.intent = "out", ccpp.dim_names = [":"], ccpp.allocatable}, %instance : memref<i32> {ccpp.name = "instance", ccpp.standard_name = "instance_number", ccpp.intent = "in"}, %ninstances : memref<i32> {ccpp.name = "ninstances", ccpp.standard_name = "number_of_instances", ccpp.intent = "in"}) -> (memref<512xi8>, memref<i32>) attributes {ccpp_phase = "suite_register"} {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errcode = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errcode[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %1 = arith.constant 0 : i32
// CHECK-NEXT:        %2 = memref.load %errcode[] : memref<i32>
// CHECK-NEXT:        %3 = arith.cmpi eq, %2, %1 : i32
// CHECK-NEXT:        scf.if %3 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%dyn_const, %errmsg, %errcode) <{callee = "cld_liq_register", operand_names = ["dyn_const", "errmsg", "errcode"], result_names = [], overrides = {}}> : (memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errcode : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @cld_suite_initialize(%instance : memref<i32> {ccpp.name = "instance", ccpp.standard_name = "instance_number", ccpp.intent = "in"}, %ninstances : memref<i32> {ccpp.name = "ninstances", ccpp.standard_name = "number_of_instances", ccpp.intent = "in"}) -> (memref<i32>, memref<512xi8>) attributes {ccpp_phase = "suite_initialize"} {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %ncols = "ccpp_utils.host_var_ref"() <{var_name = "ncols", module_name = "data"}> : () -> memref<i32>
// CHECK-NEXT:        %pver = "ccpp_utils.host_var_ref"() <{var_name = "pver", module_name = "data"}> : () -> memref<i32>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ncols, %pver) <{var_name = "cld_liq_tend", kind_name = "kind_phys"}> : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ninstances) <{var_name = "ccpp_suite_state", kind_name = "character"}> ({
// CHECK-NEXT:          "ccpp_utils.string_literal_expr"() <{text = "uninitialized"}> : () -> ()
// CHECK-NEXT:        }) : (memref<i32>) -> ()
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_uninitialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> {ccpp_instance_ref = "instance"} : () -> !llvm.ptr
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
// CHECK-NEXT:        %12 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> {ccpp_instance_ref = "instance"} : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%11, %12) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @cld_suite_finalize(%instance : memref<i32> {ccpp.name = "instance", ccpp.standard_name = "instance_number", ccpp.intent = "in"}, %ninstances : memref<i32> {ccpp.name = "ninstances", ccpp.standard_name = "number_of_instances", ccpp.intent = "in"}) -> (memref<i32>, memref<512xi8>) attributes {ccpp_phase = "suite_finalize"} {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %tcld = "ccpp_utils.host_var_ref"() <{var_name = "tcld", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ninstances) <{var_name = "ccpp_suite_state", kind_name = "character"}> ({
// CHECK-NEXT:          "ccpp_utils.string_literal_expr"() <{text = "uninitialized"}> : () -> ()
// CHECK-NEXT:        }) : (memref<i32>) -> ()
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> {ccpp_instance_ref = "instance"} : () -> !llvm.ptr
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
// CHECK-NEXT:        %12 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> {ccpp_instance_ref = "instance"} : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%11, %12) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @cld_suite_init_physics(%tfreeze : memref<!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "tfreeze", ccpp.standard_name = "water_temperature_at_freezing", ccpp.intent = "in"}, %instance : memref<i32> {ccpp.name = "instance", ccpp.standard_name = "instance_number", ccpp.intent = "in"}, %ninstances : memref<i32> {ccpp.name = "ninstances", ccpp.standard_name = "number_of_instances", ccpp.intent = "in"}) -> (memref<512xi8>, memref<i32>) attributes {ccpp_phase = "group_init"} {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errcode = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errcode[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %tcld = "ccpp_utils.host_var_ref"() <{var_name = "tcld", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %ncols = "ccpp_utils.host_var_ref"() <{var_name = "ncols", module_name = "data"}> : () -> memref<i32>
// CHECK-NEXT:        %pver = "ccpp_utils.host_var_ref"() <{var_name = "pver", module_name = "data"}> : () -> memref<i32>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ncols, %pver) <{var_name = "cld_liq_tend", kind_name = "kind_phys"}> : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ninstances) <{var_name = "ccpp_suite_state", kind_name = "character"}> ({
// CHECK-NEXT:          "ccpp_utils.string_literal_expr"() <{text = "uninitialized"}> : () -> ()
// CHECK-NEXT:        }) : (memref<i32>) -> ()
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> {ccpp_instance_ref = "instance"} : () -> !llvm.ptr
// CHECK-NEXT:        %4 = "llvm.load"(%3) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %5 = "ccpp_utils.strcmp"(%2, %4) <{length = 11 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %6 = arith.constant true
// CHECK-NEXT:        %7 = arith.xori %5, %6 : i1
// CHECK-NEXT:        scf.if %7 {
// CHECK-NEXT:          %8 = "ccpp_utils.trim"(%4) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in cld_suite_init_physics"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errcode[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = arith.constant 0 : i32
// CHECK-NEXT:        %11 = memref.load %errcode[] : memref<i32>
// CHECK-NEXT:        %12 = arith.cmpi eq, %11, %10 : i32
// CHECK-NEXT:        scf.if %12 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%tfreeze, %tcld, %errmsg, %errcode) <{callee = "cld_liq_init", operand_names = ["tfreeze", "tcld", "errmsg", "errcode"], result_names = [], overrides = {}}> : (memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errcode : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @cld_suite_physics(%ncol : memref<i32> {ccpp.name = "ncol", ccpp.standard_name = "horizontal_dimension", ccpp.intent = "in"}, %timestep : memref<!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "timestep", ccpp.standard_name = "time_step_for_physics", ccpp.intent = "in"}, %temp : memref<?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "temp", ccpp.standard_name = "temperature", ccpp.intent = "inout", ccpp.dim_names = ["horizontal_dimension", "vertical_layer_dimension"]}, %qv : memref<?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "qv", ccpp.standard_name = "water_vapor_specific_humidity", ccpp.intent = "inout", ccpp.dim_names = ["horizontal_dimension", "vertical_layer_dimension"]}, %ps : memref<?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "ps", ccpp.standard_name = "surface_air_pressure", ccpp.intent = "in", ccpp.dim_names = ["horizontal_dimension"]}, %cld_liq_array : memref<?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "cld_liq_array", ccpp.standard_name = "cloud_liquid_dry_mixing_ratio", ccpp.intent = "inout", ccpp.dim_names = ["horizontal_dimension", "vertical_layer_dimension"]}, %cld_liq_tend : memref<?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "cld_liq_tend", ccpp.standard_name = "tendency_of_cloud_liquid_dry_mixing_ratio", ccpp.intent = "out", ccpp.dim_names = ["horizontal_dimension", "vertical_layer_dimension"]}, %const_tend : memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "const_tend", ccpp.standard_name = "ccpp_constituent_tendencies", ccpp.intent = "inout", ccpp.dim_names = ["horizontal_dimension", "vertical_layer_dimension", "number_of_ccpp_constituents"]}, %const : memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "const", ccpp.standard_name = "ccpp_constituents", ccpp.intent = "inout", ccpp.dim_names = ["horizontal_dimension", "vertical_layer_dimension", "number_of_ccpp_constituents"]}, %instance : memref<i32> {ccpp.name = "instance", ccpp.standard_name = "instance_number", ccpp.intent = "in"}, %ninstances : memref<i32> {ccpp.name = "ninstances", ccpp.standard_name = "number_of_instances", ccpp.intent = "in"}) -> (memref<512xi8>, memref<i32>) attributes {ccpp_phase = "run"} {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errcode = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errcode[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %tcld = "ccpp_utils.host_var_ref"() <{var_name = "tcld", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ninstances) <{var_name = "ccpp_suite_state", kind_name = "character"}> ({
// CHECK-NEXT:          "ccpp_utils.string_literal_expr"() <{text = "uninitialized"}> : () -> ()
// CHECK-NEXT:        }) : (memref<i32>) -> ()
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_in_time_step}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> {ccpp_instance_ref = "instance"} : () -> !llvm.ptr
// CHECK-NEXT:        %4 = "llvm.load"(%3) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %5 = "ccpp_utils.strcmp"(%2, %4) <{length = 12 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %6 = arith.constant true
// CHECK-NEXT:        %7 = arith.xori %5, %6 : i1
// CHECK-NEXT:        scf.if %7 {
// CHECK-NEXT:          %8 = "ccpp_utils.trim"(%4) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in cld_suite_physics"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errcode[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = arith.constant 0 : i32
// CHECK-NEXT:        %11 = memref.load %errcode[] : memref<i32>
// CHECK-NEXT:        %12 = arith.cmpi eq, %11, %10 : i32
// CHECK-NEXT:        scf.if %12 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%ncol, %timestep, %tcld, %temp, %qv, %ps, %cld_liq_array, %cld_liq_tend, %errmsg, %errcode) <{callee = "cld_liq_run", operand_names = ["ncol", "timestep", "tcld", "temp", "qv", "ps", "cld_liq_array", "cld_liq_tend", "errmsg", "errcode"], result_names = [], overrides = {}}> : (memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %13 = arith.constant 0 : i32
// CHECK-NEXT:        %14 = memref.load %errcode[] : memref<i32>
// CHECK-NEXT:        %15 = arith.cmpi eq, %14, %13 : i32
// CHECK-NEXT:        scf.if %15 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%const_tend, %const, %errcode, %errmsg) <{callee = "apply_constituent_tendencies_run", operand_names = ["const_tend", "const", "errcode", "errmsg"], result_names = [], overrides = {}}> : (memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<512xi8>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errcode : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @cld_suite_timestep_init_physics(%instance : memref<i32> {ccpp.name = "instance", ccpp.standard_name = "instance_number", ccpp.intent = "in"}, %ninstances : memref<i32> {ccpp.name = "ninstances", ccpp.standard_name = "number_of_instances", ccpp.intent = "in"}) -> (memref<i32>, memref<512xi8>) attributes {ccpp_phase = "timestep_init"} {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %tcld = "ccpp_utils.host_var_ref"() <{var_name = "tcld", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ninstances) <{var_name = "ccpp_suite_state", kind_name = "character"}> ({
// CHECK-NEXT:          "ccpp_utils.string_literal_expr"() <{text = "uninitialized"}> : () -> ()
// CHECK-NEXT:        }) : (memref<i32>) -> ()
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_in_time_step}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> {ccpp_instance_ref = "instance"} : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%2, %3) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @cld_suite_timestep_final_physics(%instance : memref<i32> {ccpp.name = "instance", ccpp.standard_name = "instance_number", ccpp.intent = "in"}, %ninstances : memref<i32> {ccpp.name = "ninstances", ccpp.standard_name = "number_of_instances", ccpp.intent = "in"}) -> (memref<i32>, memref<512xi8>) attributes {ccpp_phase = "timestep_final"} {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %tcld = "ccpp_utils.host_var_ref"() <{var_name = "tcld", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ninstances) <{var_name = "ccpp_suite_state", kind_name = "character"}> ({
// CHECK-NEXT:          "ccpp_utils.string_literal_expr"() <{text = "uninitialized"}> : () -> ()
// CHECK-NEXT:        }) : (memref<i32>) -> ()
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> {ccpp_instance_ref = "instance"} : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%2, %3) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @cld_suite_final_physics(%instance : memref<i32> {ccpp.name = "instance", ccpp.standard_name = "instance_number", ccpp.intent = "in"}, %ninstances : memref<i32> {ccpp.name = "ninstances", ccpp.standard_name = "number_of_instances", ccpp.intent = "in"}) -> (memref<i32>, memref<512xi8>) attributes {ccpp_phase = "group_final"} {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %tcld = "ccpp_utils.host_var_ref"() <{var_name = "tcld", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ninstances) <{var_name = "ccpp_suite_state", kind_name = "character"}> ({
// CHECK-NEXT:          "ccpp_utils.string_literal_expr"() <{text = "uninitialized"}> : () -> ()
// CHECK-NEXT:        }) : (memref<i32>) -> ()
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> {ccpp_instance_ref = "instance"} : () -> !llvm.ptr
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
// CHECK-LABEL:     func.func public @ccpp_register(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}, %instance : memref<i32> {ccpp.name = "instance"}, %ninstances : memref<i32> {ccpp.name = "ninstances"}) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ninstances) <{var_name = "lc_instances", kind_name = "type"}> : (memref<i32>) -> ()
// CHECK-NEXT:        %0 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_instances(instance)%lc_dyn_const"}> : () -> memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>
// CHECK-NEXT:        %1 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %1, %errflg[] : memref<i32>
// CHECK-NEXT:        %2 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %3 = "ccpp_utils.strcmp"(%2) <{literal = "cld_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %3 {
// CHECK-NEXT:          %4, %5 = func.call @cld_suite_register(%0, %instance, %ninstances) : (memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>, memref<i32>, memref<i32>) -> (memref<512xi8>, memref<i32>)
// CHECK-NEXT:          "memref.copy"(%4, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:          "memref.copy"(%5, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %2) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %6 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %6, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_init(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}, %instance : memref<i32> {ccpp.name = "instance"}, %ninstances : memref<i32> {ccpp.name = "ninstances"}) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "cld_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3, %4 = func.call @cld_suite_initialize(%instance, %ninstances) : (memref<i32>, memref<i32>) -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:          "memref.copy"(%3, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          "memref.copy"(%4, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %5 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %5, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_final(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}, %instance : memref<i32> {ccpp.name = "instance"}, %ninstances : memref<i32> {ccpp.name = "ninstances"}) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "cld_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3, %4 = func.call @cld_suite_finalize(%instance, %ninstances) : (memref<i32>, memref<i32>) -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:          "memref.copy"(%3, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          "memref.copy"(%4, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %5 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %5, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_physics_run(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}, %suite_part : memref<?xi8> {ccpp.name = "suite_part"}, %lb : memref<i32> {ccpp.name = "lb"}, %ub : memref<i32> {ccpp.name = "ub"}, %instance : memref<i32> {ccpp.name = "instance", ccpp.standard_name = "instance_number", ccpp.intent = "in"}, %ninstances : memref<i32> {ccpp.name = "ninstances", ccpp.standard_name = "number_of_instances", ccpp.intent = "in"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg"}, %errflg : memref<i32> {ccpp.name = "errflg"}) -> (memref<512xi8>, memref<i32>) attributes {bind_c_dim_exprs = ["", "", "", "", "", "", "", ""]} {
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
// CHECK-NEXT:          %13 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_instances(instance)%lc_cld_liq_array"}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %14 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_instances(instance)%lc_cld_liq_tend"}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %15 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_instances(instance)%lc_const_tend"}> : () -> memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %16 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_instances(instance)%lc_constituent_array"}> : () -> memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %17 = arith.constant 1 : i32
// CHECK-NEXT:          %18 = "ccpp_utils.host_var_ref"() <{var_name = "pver", module_name = "data"}> : () -> i32
// CHECK-NEXT:          %19 = "ccpp_utils.rank_reducing_slice"(%10, %lb, %17, %ub, %18) <{dim_pattern = "RR"}> {operandSegmentSizes = array<i32: 1, 2, 2, 0>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, i32) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %20 = "ccpp_utils.rank_reducing_slice"(%12, %lb, %ub) <{dim_pattern = "R"}> {operandSegmentSizes = array<i32: 1, 1, 1, 0>} : (memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>) -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %21 = "ccpp_utils.rank_reducing_slice"(%13, %lb, %17, %ub, %18) <{dim_pattern = "RR"}> {operandSegmentSizes = array<i32: 1, 2, 2, 0>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, i32) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %22 = "ccpp_utils.rank_reducing_slice"(%14, %lb, %17, %ub, %18) <{dim_pattern = "RR"}> {operandSegmentSizes = array<i32: 1, 2, 2, 0>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, i32) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %23 = "ccpp_utils.strcmp"(%3) <{literal = "physics"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %23 {
// CHECK-NEXT:            %24, %25 = func.call @cld_suite_physics(%ncol, %9, %19, %11, %20, %21, %22, %15, %16, %instance, %ninstances) : (memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>) -> (memref<512xi8>, memref<i32>)
// CHECK-NEXT:            "memref.copy"(%24, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:            "memref.copy"(%25, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %3) <{prefix = "No suite part named ", suffix = " found in suite cld_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %26 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %26, %errflg[] : memref<i32>
// CHECK-NEXT:          }
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %27 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %27, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_physics_timestep_init(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}, %suite_part : memref<?xi8> {ccpp.name = "suite_part"}, %lb : memref<i32> {ccpp.name = "lb"}, %ub : memref<i32> {ccpp.name = "ub"}, %instance : memref<i32> {ccpp.name = "instance", ccpp.standard_name = "instance_number", ccpp.intent = "in"}, %ninstances : memref<i32> {ccpp.name = "ninstances", ccpp.standard_name = "number_of_instances", ccpp.intent = "in"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg"}, %errflg : memref<i32> {ccpp.name = "errflg"}) -> (memref<512xi8>, memref<i32>) attributes {bind_c_dim_exprs = ["", "", "", "", "", "", "", ""]} {
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
// CHECK-LABEL:     func.func public @ccpp_physics_timestep_final(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}, %suite_part : memref<?xi8> {ccpp.name = "suite_part"}, %lb : memref<i32> {ccpp.name = "lb"}, %ub : memref<i32> {ccpp.name = "ub"}, %instance : memref<i32> {ccpp.name = "instance", ccpp.standard_name = "instance_number", ccpp.intent = "in"}, %ninstances : memref<i32> {ccpp.name = "ninstances", ccpp.standard_name = "number_of_instances", ccpp.intent = "in"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg"}, %errflg : memref<i32> {ccpp.name = "errflg"}) -> (memref<512xi8>, memref<i32>) attributes {bind_c_dim_exprs = ["", "", "", "", "", "", "", ""]} {
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
// CHECK-LABEL:     func.func public @ccpp_physics_init(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}, %suite_part : memref<?xi8> {ccpp.name = "suite_part"}, %lb : memref<i32> {ccpp.name = "lb"}, %ub : memref<i32> {ccpp.name = "ub"}, %instance : memref<i32> {ccpp.name = "instance", ccpp.standard_name = "instance_number", ccpp.intent = "in"}, %ninstances : memref<i32> {ccpp.name = "ninstances", ccpp.standard_name = "number_of_instances", ccpp.intent = "in"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg"}, %errflg : memref<i32> {ccpp.name = "errflg"}) -> (memref<512xi8>, memref<i32>) attributes {bind_c_dim_exprs = ["", "", "", "", "", "", "", ""]} {
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
// CHECK-LABEL:     func.func public @ccpp_physics_final(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}, %suite_part : memref<?xi8> {ccpp.name = "suite_part"}, %lb : memref<i32> {ccpp.name = "lb"}, %ub : memref<i32> {ccpp.name = "ub"}, %instance : memref<i32> {ccpp.name = "instance", ccpp.standard_name = "instance_number", ccpp.intent = "in"}, %ninstances : memref<i32> {ccpp.name = "ninstances", ccpp.standard_name = "number_of_instances", ccpp.intent = "in"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg"}, %errflg : memref<i32> {ccpp.name = "errflg"}) -> (memref<512xi8>, memref<i32>) attributes {bind_c_dim_exprs = ["", "", "", "", "", "", "", ""]} {
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
// CHECK-NEXT:          %8 = "ccpp_utils.strcmp"(%7) <{literal = "cld_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %8 {
// CHECK-NEXT:            %9 = "ccpp_utils.var_ref_expr"() <{var_name = "do_input"}> : () -> i1
// CHECK-NEXT:            %10 = "ccpp_utils.var_ref_expr"() <{var_name = "do_output"}> : () -> i1
// CHECK-NEXT:            %11 = arith.constant true
// CHECK-NEXT:            %12 = arith.xori %10, %11 : i1
// CHECK-NEXT:            %13 = arith.andi %9, %12 : i1
// CHECK-NEXT:            scf.if %13 {
// CHECK-NEXT:              "ccpp_utils.allocate"() <{var_name = "var_list"}> ({
// CHECK-NEXT:                %14 = arith.constant 7 : i32
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %15 = arith.constant 1 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "ccpp_constituent_tendencies         "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %16 = arith.constant 2 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "ccpp_constituents                   "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %17 = arith.constant 3 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "cloud_liquid_dry_mixing_ratio       "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %18 = arith.constant 4 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "number_of_ccpp_constituents         "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %19 = arith.constant 5 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "surface_air_pressure                "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %20 = arith.constant 6 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "temperature                         "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %21 = arith.constant 7 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "water_vapor_specific_humidity       "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:            } else {
// CHECK-NEXT:              %22 = "ccpp_utils.var_ref_expr"() <{var_name = "do_input"}> : () -> i1
// CHECK-NEXT:              %23 = arith.constant true
// CHECK-NEXT:              %24 = arith.xori %22, %23 : i1
// CHECK-NEXT:              %25 = "ccpp_utils.var_ref_expr"() <{var_name = "do_output"}> : () -> i1
// CHECK-NEXT:              %26 = arith.andi %24, %25 : i1
// CHECK-NEXT:              scf.if %26 {
// CHECK-NEXT:                "ccpp_utils.allocate"() <{var_name = "var_list"}> ({
// CHECK-NEXT:                  %27 = arith.constant 9 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %28 = arith.constant 1 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "ccpp_constituent_tendencies         "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %29 = arith.constant 2 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "ccpp_constituents                   "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %30 = arith.constant 3 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "ccpp_error_code                     "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %31 = arith.constant 4 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "ccpp_error_message                  "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %32 = arith.constant 5 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "cloud_liquid_dry_mixing_ratio       "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %33 = arith.constant 6 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "dynamic_constituents_for_cld_liq    "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %34 = arith.constant 7 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "temperature                         "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %35 = arith.constant 8 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "tendency_of_cloud_liquid_dry_mixing_ratio"}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %36 = arith.constant 9 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "water_vapor_specific_humidity       "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              } else {
// CHECK-NEXT:                "ccpp_utils.allocate"() <{var_name = "var_list"}> ({
// CHECK-NEXT:                  %37 = arith.constant 11 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %38 = arith.constant 1 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "ccpp_constituent_tendencies         "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %39 = arith.constant 2 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "ccpp_constituents                   "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %40 = arith.constant 3 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "ccpp_error_code                     "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %41 = arith.constant 4 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "ccpp_error_message                  "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %42 = arith.constant 5 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "cloud_liquid_dry_mixing_ratio       "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %43 = arith.constant 6 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "dynamic_constituents_for_cld_liq    "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %44 = arith.constant 7 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "number_of_ccpp_constituents         "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %45 = arith.constant 8 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "surface_air_pressure                "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %46 = arith.constant 9 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "temperature                         "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %47 = arith.constant 10 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "tendency_of_cloud_liquid_dry_mixing_ratio"}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "var_list"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %48 = arith.constant 11 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "water_vapor_specific_humidity       "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              }
// CHECK-NEXT:            }
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%1, %7) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %49 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %49, %2[] : memref<i32>
// CHECK-NEXT:          }
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
// CHECK-NEXT:          "ccpp_utils.ddt_component_decl"() <{var_name = "lc_cld_liq_array", base_type = "real", rank = 2 : i64, kind = "kind_phys", is_pointer = true}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.ddt_component_decl"() <{var_name = "lc_cld_liq_tend", base_type = "real", rank = 2 : i64, kind = "kind_phys", is_pointer = true}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.ddt_component_decl"() <{var_name = "cam_model_const_stdnames", base_type = "character", rank = 0 : i64, kind = "29", fixed_dim = 1 : i64, init_value = "[ character(len=29) :: 'cloud_liquid_dry_mixing_ratio' ]"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.ddt_component_decl"() <{var_name = "cam_model_const_indices", base_type = "integer", rank = 0 : i64, fixed_dim = 1 : i64, init_value = "-1"}> : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "Cld_ccpp_is_scheme_constituent", is_function = false, args = ["std_name", "is_const", "errflg", "errmsg", "instance"], use_stmts = [], arg_decls = ["character(len=*), intent(in) :: std_name", "logical, intent(out) :: is_const", "integer, intent(out) :: errflg", "character(len=512), intent(out) :: errmsg", "integer, intent(in) :: instance"], local_decls = ["integer :: lc_idx", "character(len=256) :: lc_std_name"]}> ({
// CHECK-NEXT:          "ccpp_utils.clear_err_state"() <{errcode_var = "errflg", errmsg_var = "errmsg"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.assign"() ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "is_const"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            %50 = arith.constant false
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:          %51 = "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i1
// CHECK-NEXT:          scf.if %51 {
// CHECK-NEXT:            %52 = "ccpp_utils.call_expr"() <{callee = "any"}> ({
// CHECK-NEXT:              %53 = "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances(instance)%cam_model_const_stdnames"}> : () -> i32
// CHECK-NEXT:              %54 = "ccpp_utils.var_ref_expr"() <{var_name = "std_name"}> : () -> i32
// CHECK-NEXT:              %55 = arith.cmpi eq, %53, %54 : i32
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i1
// CHECK-NEXT:            scf.if %52 {
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "is_const"}> : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                %56 = arith.constant true
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.return_stmt"() : () -> ()
// CHECK-NEXT:            }
// CHECK-NEXT:          }
// CHECK-NEXT:          %57 = "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i1
// CHECK-NEXT:          scf.if %57 {
// CHECK-NEXT:            %58 = "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances(instance)%lc_dyn_const"}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i1
// CHECK-NEXT:            scf.if %58 {
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
// CHECK-NEXT:                %59 = "ccpp_utils.call_expr"() <{callee = "trim"}> ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "lc_std_name"}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i32
// CHECK-NEXT:                %60 = "ccpp_utils.call_expr"() <{callee = "trim"}> ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "std_name"}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i32
// CHECK-NEXT:                %61 = arith.cmpi eq, %59, %60 : i32
// CHECK-NEXT:                scf.if %61 {
// CHECK-NEXT:                  "ccpp_utils.assign"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "is_const"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %62 = arith.constant true
// CHECK-NEXT:                  }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                  "ccpp_utils.return_stmt"() : () -> ()
// CHECK-NEXT:                }
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }
// CHECK-NEXT:          }
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "Cld_ccpp_deallocate_dynamic_constituents", is_function = false, args = ["instance"], use_stmts = [], arg_decls = ["integer, intent(in) :: instance"], local_decls = []}> ({
// CHECK-NEXT:          "ccpp_utils.return_stmt"() ({
// CHECK-NEXT:            %63 = "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i1
// CHECK-NEXT:            %64 = arith.constant true
// CHECK-NEXT:            %65 = arith.xori %63, %64 : i1
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          "ccpp_utils.safe_dealloc"() <{var_name = "lc_instances(instance)%lc_dyn_const"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.safe_dealloc"() <{var_name = "lc_instances(instance)%lc_all_constituents"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.safe_dealloc"() <{var_name = "lc_instances(instance)%lc_const_props"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.nullify_pointer"() <{ptr_name = "lc_instances(instance)%lc_constituent_array", if_associated}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.safe_dealloc"() <{var_name = "lc_instances(instance)%lc_const_tend"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.nullify_pointer"() <{ptr_name = "lc_instances(instance)%lc_cld_liq_array"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.nullify_pointer"() <{ptr_name = "lc_instances(instance)%lc_cld_liq_tend"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.cam_direct_call"() <{callee = "lc_instances(instance)%cam_constituents_obj%reset", call_args = []}> : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "Cld_ccpp_register_constituents", is_function = false, args = ["host_constituents", "errmsg", "errcode", "instance", "ninstances"], use_stmts = ["use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t, ccpp_constituent_prop_ptr_t", "use ccpp_scheme_utils, only: ccpp_scheme_utils_set_constituents"], arg_decls = ["type(ccpp_constituent_properties_t), target, intent(in) :: host_constituents(:)", "character(len=512), intent(out) :: errmsg", "integer, intent(out) :: errcode", "integer, intent(in) :: instance", "integer, intent(in) :: ninstances"], local_decls = ["integer :: lc_i, lc_num_consts, field_ind", "type(ccpp_constituent_properties_t), pointer :: const_prop", "type(ccpp_constituent_prop_ptr_t), pointer :: lc_props_ptr(:)"]}> ({
// CHECK-NEXT:          "ccpp_utils.clear_err_state"() <{errcode_var = "errcode", errmsg_var = "errmsg"}> : () -> ()
// CHECK-NEXT:          %66 = "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i1
// CHECK-NEXT:          %67 = arith.constant true
// CHECK-NEXT:          %68 = arith.xori %66, %67 : i1
// CHECK-NEXT:          scf.if %68 {
// CHECK-NEXT:            "ccpp_utils.allocate"() <{var_name = "lc_instances"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "ninstances"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }
// CHECK-NEXT:          "ccpp_utils.assign"() ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "lc_num_consts"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            %69 = "ccpp_utils.call_expr"() <{callee = "size"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "host_constituents"}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i32
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:          %70 = "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:            "ccpp_utils.member_access_expr"() <{member = "lc_dyn_const"}> ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "instance"}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i1
// CHECK-NEXT:          scf.if %70 {
// CHECK-NEXT:            "ccpp_utils.assign"() ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "lc_num_consts"}> : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              %71 = "ccpp_utils.var_ref_expr"() <{var_name = "lc_num_consts"}> : () -> i32
// CHECK-NEXT:              %72 = "ccpp_utils.call_expr"() <{callee = "size"}> ({
// CHECK-NEXT:                "ccpp_utils.member_access_expr"() <{member = "lc_dyn_const"}> ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    "ccpp_utils.var_ref_expr"() <{var_name = "instance"}> : () -> ()
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i32
// CHECK-NEXT:              %73 = arith.addi %71, %72 : i32
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:          }
// CHECK-NEXT:          "ccpp_utils.assign"() ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "lc_num_consts"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            %74 = "ccpp_utils.var_ref_expr"() <{var_name = "lc_num_consts"}> : () -> i32
// CHECK-NEXT:            %75 = arith.constant 1 : i32
// CHECK-NEXT:            %76 = arith.addi %74, %75 : i32
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
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
// CHECK-NEXT:            %77 = "ccpp_utils.var_ref_expr"() <{var_name = "errcode"}> : () -> i32
// CHECK-NEXT:            %78 = arith.constant 0 : i32
// CHECK-NEXT:            %79 = arith.cmpi ne, %77, %78 : i32
// CHECK-NEXT:            scf.if %79 {
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
// CHECK-NEXT:          %80 = "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances(instance)%lc_dyn_const"}> : () -> ()
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i1
// CHECK-NEXT:          scf.if %80 {
// CHECK-NEXT:            "ccpp_utils.text_bounded_do_loop"() <{loop_var = "lc_i", upper_expr = "size(lc_instances(instance)%lc_dyn_const)"}> ({
// CHECK-NEXT:              "ccpp_utils.allocate"() <{var_name = "const_prop", dims = [], stat_var = "errcode"}> : () -> ()
// CHECK-NEXT:              %81 = "ccpp_utils.var_ref_expr"() <{var_name = "errcode"}> : () -> i32
// CHECK-NEXT:              %82 = arith.constant 0 : i32
// CHECK-NEXT:              %83 = arith.cmpi ne, %81, %82 : i32
// CHECK-NEXT:              scf.if %83 {
// CHECK-NEXT:                "ccpp_utils.error_exit"() <{errmsg_var = "errmsg", errmsg_text = "ERROR allocating const_prop"}> : () -> ()
// CHECK-NEXT:              }
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "const_prop"}> : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.member_access_expr"() <{member = "lc_dyn_const"}> ({
// CHECK-NEXT:                    "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                      "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:                    }, {
// CHECK-NEXT:                      "ccpp_utils.var_ref_expr"() <{var_name = "instance"}> : () -> ()
// CHECK-NEXT:                    }) : () -> ()
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "lc_i"}> : () -> ()
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
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
// CHECK-NEXT:          }
// CHECK-NEXT:          "ccpp_utils.allocate"() <{var_name = "const_prop", dims = [], stat_var = "errcode"}> : () -> ()
// CHECK-NEXT:          %84 = "ccpp_utils.var_ref_expr"() <{var_name = "errcode"}> : () -> i32
// CHECK-NEXT:          %85 = arith.constant 0 : i32
// CHECK-NEXT:          %86 = arith.cmpi ne, %84, %85 : i32
// CHECK-NEXT:          scf.if %86 {
// CHECK-NEXT:            "ccpp_utils.error_exit"() <{errmsg_var = "errmsg", errmsg_text = "ERROR allocating const_prop"}> : () -> ()
// CHECK-NEXT:          }
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
// CHECK-NEXT:              %87 = arith.constant true
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
// CHECK-NEXT:          "ccpp_utils.assign"() ({
// CHECK-NEXT:            "ccpp_utils.member_access_expr"() <{member = "lc_const_props"}> ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "instance"}> : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "lc_props_ptr"}> : () -> ()
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
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
// CHECK-NEXT:              %88 = "ccpp_utils.var_ref_expr"() <{var_name = "field_ind"}> : () -> i32
// CHECK-NEXT:              %89 = arith.constant 0 : i32
// CHECK-NEXT:              %90 = arith.cmpi sgt, %88, %89 : i32
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.member_access_expr"() <{member = "cam_model_const_indices"}> ({
// CHECK-NEXT:                    "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                      "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:                    }, {
// CHECK-NEXT:                      "ccpp_utils.var_ref_expr"() <{var_name = "instance"}> : () -> ()
// CHECK-NEXT:                    }) : () -> ()
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "lc_i"}> : () -> ()
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "field_ind"}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.error_exit"() <{errmsg_var = "errmsg", errflg_var = "errcode"}> ({
// CHECK-NEXT:                "ccpp_utils.string_concat_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "No field index for "}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.call_expr"() <{callee = "trim"}> ({
// CHECK-NEXT:                    "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                      "ccpp_utils.member_access_expr"() <{member = "cam_model_const_stdnames"}> ({
// CHECK-NEXT:                        "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                          "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:                        }, {
// CHECK-NEXT:                          "ccpp_utils.var_ref_expr"() <{var_name = "instance"}> : () -> ()
// CHECK-NEXT:                        }) : () -> ()
// CHECK-NEXT:                      }) : () -> ()
// CHECK-NEXT:                    }, {
// CHECK-NEXT:                      "ccpp_utils.var_ref_expr"() <{var_name = "lc_i"}> : () -> ()
// CHECK-NEXT:                    }) : () -> ()
// CHECK-NEXT:                  }) {regionSegmentSizes = array<i32: 1, 0>} : () -> ()
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "Cld_ccpp_number_constituents", is_function = false, args = ["num_advected", "errmsg", "errcode", "advected", "instance"], use_stmts = [], arg_decls = ["integer, intent(out) :: num_advected", "character(len=512), intent(out) :: errmsg", "integer, intent(out) :: errcode", "logical, optional, intent(in) :: advected", "integer, intent(in) :: instance"], local_decls = []}> ({
// CHECK-NEXT:          "ccpp_utils.clear_err_state"() <{errcode_var = "errcode", errmsg_var = "errmsg"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.active_check"() ({
// CHECK-NEXT:            %91 = "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i1
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
// CHECK-NEXT:            "ccpp_utils.assign"() ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "num_advected"}> : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              %92 = arith.constant 0 : i32
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        "ccpp_utils.constituent_function"() <{fn_name = "Cld_ccpp_initialize_constituents", is_function = false, args = ["ncols", "pver", "errflg", "errmsg", "instance"], use_stmts = [], arg_decls = ["integer, intent(in) :: ncols", "integer, intent(in) :: pver", "integer, intent(out) :: errflg", "character(len=512), intent(out) :: errmsg", "integer, intent(in) :: instance"], local_decls = []}> ({
// CHECK-NEXT:          "ccpp_utils.clear_err_state"() <{errcode_var = "errflg", errmsg_var = "errmsg"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.error_guard"() <{errmsg_text = "ccpp_initialize_constituents: register_constituents not called"}> ({
// CHECK-NEXT:            %93 = "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i1
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          "ccpp_utils.error_guard"() <{errmsg_text = "ccpp_initialize_constituents: register_constituents not called"}> ({
// CHECK-NEXT:            %94 = "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances(instance)%lc_all_constituents"}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i1
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
// CHECK-NEXT:            "ccpp_utils.nullify_pointer"() <{ptr_name = "lc_instances(instance)%lc_cld_liq_array"}> : () -> ()
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
// CHECK-NEXT:              %95 = "ccpp_utils.var_ref_expr"() <{var_name = "errflg"}> : () -> i32
// CHECK-NEXT:              %96 = arith.constant 0 : i32
// CHECK-NEXT:              %97 = arith.cmpi eq, %95, %96 : i32
// CHECK-NEXT:              %98 = "ccpp_utils.var_ref_expr"() <{var_name = "lc_tend_idx"}> : () -> i32
// CHECK-NEXT:              %99 = arith.constant 0 : i32
// CHECK-NEXT:              %100 = arith.cmpi sgt, %98, %99 : i32
// CHECK-NEXT:              %101 = arith.andi %97, %100 : i1
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.pointer_slice_assign"() <{ptr_name = "lc_instances(instance)%lc_cld_liq_array", array_name = "lc_instances(instance)%lc_constituent_array", index_var = "lc_tend_idx"}> : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.error_exit"() <{errmsg_var = "errmsg", errflg_var = "errflg", errmsg_text = "ccpp_initialize_constituents: no constituent cloud_liquid_dry_mixing_ratio"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }) : () -> ()
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
// CHECK-NEXT:              %102 = "ccpp_utils.var_ref_expr"() <{var_name = "errflg"}> : () -> i32
// CHECK-NEXT:              %103 = arith.constant 0 : i32
// CHECK-NEXT:              %104 = arith.cmpi eq, %102, %103 : i32
// CHECK-NEXT:              %105 = "ccpp_utils.var_ref_expr"() <{var_name = "lc_tend_idx"}> : () -> i32
// CHECK-NEXT:              %106 = arith.constant 0 : i32
// CHECK-NEXT:              %107 = arith.cmpi sgt, %105, %106 : i32
// CHECK-NEXT:              %108 = arith.andi %104, %107 : i1
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.pointer_slice_assign"() <{ptr_name = "lc_instances(instance)%lc_cld_liq_tend", array_name = "lc_instances(instance)%lc_const_tend", index_var = "lc_tend_idx"}> : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.error_exit"() <{errmsg_var = "errmsg", errflg_var = "errflg", errmsg_text = "ccpp_initialize_constituents: no constituent for tendency cloud_liquid_dry_mixing_ratio"}> : () -> ()
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
// CHECK-NEXT:          "ccpp_utils.clear_err_state"() <{errcode_var = "errflg", errmsg_var = "errmsg"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.assign"() ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "index"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            %109 = arith.constant -1 : i32
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:          "ccpp_utils.error_guard"() <{errmsg_text = "const_get_index: constituents not registered"}> ({
// CHECK-NEXT:            %110 = "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances"}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i1
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          "ccpp_utils.error_guard"() <{errmsg_text = "const_get_index: constituents not registered"}> ({
// CHECK-NEXT:            %111 = "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "lc_instances(instance)%lc_all_constituents"}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i1
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
// CHECK-NEXT:          %112 = "ccpp_utils.var_ref_expr"() <{var_name = "errflg"}> : () -> i32
// CHECK-NEXT:          %113 = arith.constant 0 : i32
// CHECK-NEXT:          %114 = arith.cmpi ne, %112, %113 : i32
// CHECK-NEXT:          %115 = "ccpp_utils.var_ref_expr"() <{var_name = "index"}> : () -> i32
// CHECK-NEXT:          %116 = arith.constant 0 : i32
// CHECK-NEXT:          %117 = arith.cmpi sle, %115, %116 : i32
// CHECK-NEXT:          %118 = arith.ori %114, %117 : i1
// CHECK-NEXT:          scf.if %118 {
// CHECK-NEXT:            "ccpp_utils.assign"() <{lhs_expr = "errflg", rhs_expr = "1"}> {regionSegmentSizes = array<i32: 0, 0>} : () -> ()
// CHECK-NEXT:            "ccpp_utils.write_stmt"() <{dest = "errmsg", format_spec = "(3a)", items = ["'const_get_index: constituent '", "trim(std_name)", "' not found'"]}> : () -> ()
// CHECK-NEXT:          }
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
// CHECK-LABEL:     func.func private @cld_suite_physics(memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>) -> (memref<512xi8>, memref<i32>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_timestep_init_physics(memref<i32>, memref<i32>) -> (memref<i32>, memref<512xi8>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_timestep_final_physics(memref<i32>, memref<i32>) -> (memref<i32>, memref<512xi8>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_init_physics(memref<!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>) -> (memref<512xi8>, memref<i32>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_final_physics(memref<i32>, memref<i32>) -> (memref<i32>, memref<512xi8>) attributes {module = "cld_suite_cap"}
// CHECK:         }
// CHECK-LABEL:   builtin.module @ccpp_kinds {
// CHECK:           "ccpp_utils.kind_def"() <{kind_name = "kind_phys", kind_value = "REAL64", kind_module = "iso_fortran_env"}> : () -> ()
// CHECK-NEXT:    }
// CHECK-NEXT:  }
