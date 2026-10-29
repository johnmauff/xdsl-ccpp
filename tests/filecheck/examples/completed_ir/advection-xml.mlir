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
// CHECK-LABEL:   builtin.module @cld_suite_cap attributes {ccpp_suite_cap = "cld_suite"} {
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
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "tcld", base_type = "real", rank = 0 : i64, kind = "kind_phys"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "cld_shadow_cld_ice_array", base_type = "real", rank = 2 : i64, kind = "kind_phys"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "cld_shadow_ncols", base_type = "real", rank = 1 : i64, kind = "kind_phys"}> : () -> ()
// CHECK-LABEL:     func.func public @cld_suite_register(%dyn_const : memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">> {ccpp.name = "dyn_const", ccpp.standard_name = "dynamic_constituents_for_cld_liq", ccpp.intent = "out", ccpp.dim_names = [":"], ccpp.allocatable}, %dyn_const_ice : memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">> {ccpp.name = "dyn_const_ice", ccpp.standard_name = "dynamic_constituents_for_cld_ice", ccpp.intent = "out", ccpp.dim_names = [":"], ccpp.allocatable}) -> (memref<512xi8>, memref<i32>) attributes {ccpp_phase = "suite_register"} {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %1 = arith.constant 0 : i32
// CHECK-NEXT:        %2 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %3 = arith.cmpi eq, %2, %1 : i32
// CHECK-NEXT:        scf.if %3 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%dyn_const, %errmsg, %errflg) <{callee = "cld_liq_register", operand_names = ["dyn_const", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %4 = arith.constant 0 : i32
// CHECK-NEXT:        %5 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %6 = arith.cmpi eq, %5, %4 : i32
// CHECK-NEXT:        scf.if %6 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%dyn_const_ice, %errmsg, %errflg) <{callee = "cld_ice_register", operand_names = ["dyn_const_ice", "errmsg", "errcode"], result_names = [], overrides = {}}> : (memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @cld_suite_initialize() -> (memref<i32>, memref<512xi8>) attributes {ccpp_phase = "suite_initialize"} {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %ncols = "ccpp_utils.host_var_ref"() <{var_name = "ncols", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:        %pver = "ccpp_utils.host_var_ref"() <{var_name = "pver", module_name = "test_host_mod"}> : () -> memref<i32>
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
// CHECK-LABEL:     func.func public @cld_suite_finalize() -> (memref<i32>, memref<512xi8>) attributes {ccpp_phase = "suite_finalize"} {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %tcld = "ccpp_utils.host_var_ref"() <{var_name = "tcld", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
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
// CHECK-LABEL:     func.func public @cld_suite_init_physics(%const_std_name : memref<32xi8> {ccpp.name = "const_std_name", ccpp.standard_name = "test_banana_name", ccpp.intent = "in"}, %num_consts : memref<i32> {ccpp.name = "num_consts", ccpp.standard_name = "banana_array_dim", ccpp.intent = "in"}, %test_stdname_array : memref<?x32xi8> {ccpp.name = "test_stdname_array", ccpp.standard_name = "test_banana_name_array", ccpp.intent = "in", ccpp.dim_names = ["banana_array_dim"]}, %const_inds : memref<?xi32> {ccpp.name = "const_inds", ccpp.standard_name = "test_banana_constituent_indices", ccpp.intent = "out", ccpp.dim_names = ["banana_array_dim"]}, %tfreeze : memref<!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "tfreeze", ccpp.standard_name = "water_temperature_at_freezing", ccpp.intent = "in"}, %cld_liq_array : memref<?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "cld_liq_array", ccpp.standard_name = "cloud_liquid_dry_mixing_ratio", ccpp.intent = "out", ccpp.dim_names = ["horizontal_dimension", "vertical_layer_dimension"]}, %cld_ice_array : memref<?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "cld_ice_array", ccpp.standard_name = "cloud_ice_dry_mixing_ratio", ccpp.intent = "inout", ccpp.dim_names = ["horizontal_dimension", "vertical_layer_dimension"]}) -> (memref<i32>, memref<512xi8>, memref<i32>) attributes {ccpp_phase = "group_init"} {
// CHECK:             %const_index = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %tcld = "ccpp_utils.host_var_ref"() <{var_name = "tcld", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %ncols = "ccpp_utils.host_var_ref"() <{var_name = "ncols", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:        %pver = "ccpp_utils.host_var_ref"() <{var_name = "pver", module_name = "test_host_mod"}> : () -> memref<i32>
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
// CHECK-NEXT:        %11 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %12 = arith.cmpi eq, %11, %10 : i32
// CHECK-NEXT:        scf.if %12 {
// CHECK-NEXT:          %13 = builtin.unrealized_conversion_cast %const_std_name : memref<32xi8> to memref<512xi8>
// CHECK-NEXT:          %14 = builtin.unrealized_conversion_cast %test_stdname_array : memref<?x32xi8> to memref<?x512xi8>
// CHECK-NEXT:          "ccpp_utils.kw_call"(%13, %num_consts, %14, %const_index, %const_inds, %errmsg, %errflg) <{callee = "const_indices_init", operand_names = ["const_std_name", "num_consts", "test_stdname_array", "const_index", "const_inds", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<512xi8>, memref<i32>, memref<?x512xi8>, memref<i32>, memref<?xi32>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %15 = arith.constant 0 : i32
// CHECK-NEXT:        %16 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %17 = arith.cmpi eq, %16, %15 : i32
// CHECK-NEXT:        scf.if %17 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%tfreeze, %cld_liq_array, %tcld, %errmsg, %errflg) <{callee = "cld_liq_init", operand_names = ["tfreeze", "cld_liq_array", "tcld", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %18 = arith.constant 0 : i32
// CHECK-NEXT:        %19 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %20 = arith.cmpi eq, %19, %18 : i32
// CHECK-NEXT:        scf.if %20 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%tfreeze, %cld_ice_array, %errmsg, %errflg) <{callee = "cld_ice_init", operand_names = ["tfreeze", "cld_ice_array", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %const_index, %errmsg, %errflg : memref<i32>, memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @cld_suite_physics(%const_std_name : memref<32xi8> {ccpp.name = "const_std_name", ccpp.standard_name = "test_banana_name", ccpp.intent = "in"}, %num_consts : memref<i32> {ccpp.name = "num_consts", ccpp.standard_name = "banana_array_dim", ccpp.intent = "in"}, %test_stdname_array : memref<?x32xi8> {ccpp.name = "test_stdname_array", ccpp.standard_name = "test_banana_name_array", ccpp.intent = "in", ccpp.dim_names = ["banana_array_dim"]}, %const_inds : memref<?xi32> {ccpp.name = "const_inds", ccpp.standard_name = "test_banana_constituent_indices", ccpp.intent = "out", ccpp.dim_names = ["banana_array_dim"]}, %ncol : memref<i32> {ccpp.name = "ncol", ccpp.standard_name = "horizontal_dimension", ccpp.intent = "in"}, %timestep : memref<!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "timestep", ccpp.standard_name = "time_step_for_physics", ccpp.intent = "in"}, %temp : memref<?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "temp", ccpp.standard_name = "temperature", ccpp.intent = "inout", ccpp.dim_names = ["horizontal_dimension", "vertical_layer_dimension"]}, %qv : memref<?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "qv", ccpp.standard_name = "water_vapor_specific_humidity", ccpp.intent = "inout", ccpp.dim_names = ["horizontal_dimension", "vertical_layer_dimension"]}, %ps : memref<?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "ps", ccpp.standard_name = "surface_air_pressure", ccpp.intent = "in", ccpp.dim_names = ["horizontal_dimension"]}, %cld_liq_tend : memref<?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "cld_liq_tend", ccpp.standard_name = "tendency_of_cloud_liquid_dry_mixing_ratio", ccpp.intent = "inout", ccpp.dim_names = ["horizontal_dimension", "vertical_layer_dimension"]}, %const_tend : memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "const_tend", ccpp.standard_name = "ccpp_constituent_tendencies", ccpp.intent = "inout", ccpp.dim_names = ["horizontal_dimension", "vertical_layer_dimension", "number_of_ccpp_constituents"]}, %const : memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "const", ccpp.standard_name = "ccpp_constituents", ccpp.intent = "inout", ccpp.dim_names = ["horizontal_dimension", "vertical_layer_dimension", "number_of_ccpp_constituents"]}, %cld_ice_array : memref<?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "cld_ice_array", ccpp.standard_name = "cloud_ice_dry_mixing_ratio", ccpp.intent = "inout", ccpp.dim_names = ["horizontal_dimension", "vertical_layer_dimension"]}) -> (memref<i32>, memref<512xi8>, memref<i32>) attributes {ccpp_phase = "run"} {
// CHECK:             %const_index = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %tcld = "ccpp_utils.host_var_ref"() <{var_name = "tcld", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
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
// CHECK-NEXT:        %10 = arith.constant 0 : i32
// CHECK-NEXT:        %11 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %12 = arith.cmpi eq, %11, %10 : i32
// CHECK-NEXT:        scf.if %12 {
// CHECK-NEXT:          %13 = builtin.unrealized_conversion_cast %const_std_name : memref<32xi8> to memref<512xi8>
// CHECK-NEXT:          %14 = builtin.unrealized_conversion_cast %test_stdname_array : memref<?x32xi8> to memref<?x512xi8>
// CHECK-NEXT:          "ccpp_utils.kw_call"(%13, %num_consts, %14, %const_index, %const_inds, %errmsg, %errflg) <{callee = "const_indices_run", operand_names = ["const_std_name", "num_consts", "test_stdname_array", "const_index", "const_inds", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<512xi8>, memref<i32>, memref<?x512xi8>, memref<i32>, memref<?xi32>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %15 = arith.constant 0 : i32
// CHECK-NEXT:        %16 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %17 = arith.cmpi eq, %16, %15 : i32
// CHECK-NEXT:        scf.if %17 {
// CHECK-NEXT:          %ps_unit_conv = "ccpp_utils.unit_convert"(%ps) <{to_scheme_expr = "* 0.01"}> : (memref<?x!ccpp_utils.real_kind<"kind_phys">>) -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          "ccpp_utils.kw_call"(%ncol, %timestep, %tcld, %temp, %qv, %ps_unit_conv, %cld_liq_tend, %errmsg, %errflg) <{callee = "cld_liq_run", operand_names = ["ncol", "timestep", "tcld", "temp", "qv", "ps", "cld_liq_tend", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %18 = arith.constant 0 : i32
// CHECK-NEXT:        %19 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %20 = arith.cmpi eq, %19, %18 : i32
// CHECK-NEXT:        scf.if %20 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%const_tend, %const, %errflg, %errmsg) <{callee = "apply_constituent_tendencies_run", operand_names = ["const_tend", "const", "errcode", "errmsg"], result_names = [], overrides = {}}> : (memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<512xi8>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %21 = arith.constant 0 : i32
// CHECK-NEXT:        %22 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %23 = arith.cmpi eq, %22, %21 : i32
// CHECK-NEXT:        scf.if %23 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%ncol, %timestep, %temp, %qv, %ps, %cld_ice_array, %errmsg, %errflg) <{callee = "cld_ice_run", operand_names = ["ncol", "timestep", "temp", "qv", "ps", "cld_ice_array", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %24 = arith.constant 0 : i32
// CHECK-NEXT:        %25 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %26 = arith.cmpi eq, %25, %24 : i32
// CHECK-NEXT:        scf.if %26 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%const_tend, %const, %errflg, %errmsg) <{callee = "apply_constituent_tendencies_run", operand_names = ["const_tend", "const", "errcode", "errmsg"], result_names = [], overrides = {}}> : (memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<512xi8>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %27 = arith.constant 0 : i32
// CHECK-NEXT:        %28 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %29 = arith.cmpi eq, %28, %27 : i32
// CHECK-NEXT:        scf.if %29 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%ncol, %timestep, %cld_shadow_cld_ice_array, %cld_shadow_ncols, %errmsg, %errflg) <{callee = "cld_shadow_run", operand_names = ["ncol", "timestep", "cld_ice_array", "ncols", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %const_index, %errmsg, %errflg : memref<i32>, memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @cld_suite_timestep_init_physics() -> (memref<i32>, memref<512xi8>) attributes {ccpp_phase = "timestep_init"} {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %tcld = "ccpp_utils.host_var_ref"() <{var_name = "tcld", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_in_time_step}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%2, %3) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @cld_suite_timestep_final_physics() -> (memref<i32>, memref<512xi8>) attributes {ccpp_phase = "timestep_final"} {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %tcld = "ccpp_utils.host_var_ref"() <{var_name = "tcld", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%2, %3) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @cld_suite_final_physics() -> (memref<512xi8>, memref<i32>) attributes {ccpp_phase = "group_final"} {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %tcld = "ccpp_utils.host_var_ref"() <{var_name = "tcld", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
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
// CHECK-NEXT:        %11 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %12 = arith.cmpi eq, %11, %10 : i32
// CHECK-NEXT:        scf.if %12 {
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
// CHECK-LABEL:     func.func private @apply_constituent_tendencies_run(memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<512xi8>) -> () attributes {module = "apply_constituent_tendencies"}
// CHECK-LABEL:     func.func private @cld_ice_run(memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "cld_ice"}
// CHECK-LABEL:     func.func private @cld_shadow_run(memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "cld_shadow"}
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
// CHECK-LABEL:     func.func public @ccpp_register(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}) -> (memref<512xi8>, memref<i32>) {
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
// CHECK-LABEL:     func.func public @ccpp_init(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}) -> (memref<512xi8>, memref<i32>) {
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
// CHECK-LABEL:     func.func public @ccpp_final(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}) -> (memref<512xi8>, memref<i32>) {
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
// CHECK-LABEL:     func.func public @ccpp_physics_run(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}, %suite_part : memref<?xi8> {ccpp.name = "suite_part"}, %col_start : memref<i32> {ccpp.name = "col_start"}, %col_end : memref<i32> {ccpp.name = "col_end"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg"}, %errflg : memref<i32> {ccpp.name = "errflg"}) -> (memref<512xi8>, memref<i32>) attributes {bind_c_dim_exprs = ["", "", "", "", "", ""]} {
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
// CHECK-NEXT:          %20 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_cld_ice_array"}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %21 = arith.constant 1 : i32
// CHECK-NEXT:          %22 = "ccpp_utils.host_var_ref"() <{var_name = "pver", module_name = "test_host_mod"}> : () -> i32
// CHECK-NEXT:          %23 = "ccpp_utils.host_var_ref"() <{var_name = "ncnst", module_name = "test_host_mod"}> : () -> i32
// CHECK-NEXT:          %24 = "ccpp_utils.rank_reducing_slice"(%14, %col_start, %21, %col_end, %22) <{dim_pattern = "RR"}> {operandSegmentSizes = array<i32: 1, 2, 2, 0>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, i32) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %25 = "ccpp_utils.rank_reducing_slice"(%15, %col_start, %21, %21, %col_end, %22, %23) <{dim_pattern = "RRR"}> {operandSegmentSizes = array<i32: 1, 3, 3, 0>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, i32, memref<i32>, i32, i32) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %26 = "ccpp_utils.rank_reducing_slice"(%16, %col_start, %col_end) <{dim_pattern = "R"}> {operandSegmentSizes = array<i32: 1, 1, 1, 0>} : (memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>) -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %27 = "ccpp_utils.rank_reducing_slice"(%17, %col_start, %21, %col_end, %22) <{dim_pattern = "RR"}> {operandSegmentSizes = array<i32: 1, 2, 2, 0>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, i32) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %28 = "ccpp_utils.rank_reducing_slice"(%20, %col_start, %21, %col_end, %22) <{dim_pattern = "RR"}> {operandSegmentSizes = array<i32: 1, 2, 2, 0>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, i32) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %29 = "ccpp_utils.strcmp"(%3) <{literal = "physics"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %29 {
// CHECK-NEXT:            %30 = "ccpp_utils.host_var_ref"() <{var_name = "const_index", module_name = "test_host_data"}> : () -> memref<i32>
// CHECK-NEXT:            %31, %32, %33 = func.call @cld_suite_physics(%4, %5, %6, %7, %ncol, %13, %24, %25, %26, %27, %18, %19, %28) : (memref<32xi8>, memref<i32>, memref<?x32xi8>, memref<?xi32>, memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> (memref<i32>, memref<512xi8>, memref<i32>)
// CHECK-NEXT:            "memref.copy"(%31, %30) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:            "memref.copy"(%32, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:            "memref.copy"(%33, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %3) <{prefix = "No suite part named ", suffix = " found in suite cld_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %34 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %34, %errflg[] : memref<i32>
// CHECK-NEXT:          }
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %35 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %35, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_physics_timestep_init(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}, %suite_part : memref<?xi8> {ccpp.name = "suite_part"}, %col_start : memref<i32> {ccpp.name = "col_start"}, %col_end : memref<i32> {ccpp.name = "col_end"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg"}, %errflg : memref<i32> {ccpp.name = "errflg"}) -> (memref<512xi8>, memref<i32>) attributes {bind_c_dim_exprs = ["", "", "", "", "", ""]} {
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
// CHECK-LABEL:     func.func public @ccpp_physics_timestep_final(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}, %suite_part : memref<?xi8> {ccpp.name = "suite_part"}, %col_start : memref<i32> {ccpp.name = "col_start"}, %col_end : memref<i32> {ccpp.name = "col_end"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg"}, %errflg : memref<i32> {ccpp.name = "errflg"}) -> (memref<512xi8>, memref<i32>) attributes {bind_c_dim_exprs = ["", "", "", "", "", ""]} {
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
// CHECK-LABEL:     func.func public @ccpp_physics_init(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}, %suite_part : memref<?xi8> {ccpp.name = "suite_part"}, %col_start : memref<i32> {ccpp.name = "col_start"}, %col_end : memref<i32> {ccpp.name = "col_end"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg"}, %errflg : memref<i32> {ccpp.name = "errflg"}) -> (memref<512xi8>, memref<i32>) attributes {bind_c_dim_exprs = ["", "", "", "", "", ""]} {
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
// CHECK-NEXT:          %9 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_cld_liq_array"}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %10 = "ccpp_utils.cap_var_ref"() <{var_name = "lc_cld_ice_array"}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %11 = arith.constant 1 : i32
// CHECK-NEXT:          %12 = "ccpp_utils.host_var_ref"() <{var_name = "pver", module_name = "test_host_mod"}> : () -> i32
// CHECK-NEXT:          %13 = "ccpp_utils.rank_reducing_slice"(%9, %col_start, %11, %col_end, %12) <{dim_pattern = "RR"}> {operandSegmentSizes = array<i32: 1, 2, 2, 0>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, i32) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %14 = "ccpp_utils.rank_reducing_slice"(%10, %col_start, %11, %col_end, %12) <{dim_pattern = "RR"}> {operandSegmentSizes = array<i32: 1, 2, 2, 0>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, i32) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %15 = "ccpp_utils.strcmp"(%3) <{literal = "physics"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %15 {
// CHECK-NEXT:            %16 = "ccpp_utils.host_var_ref"() <{var_name = "const_index", module_name = "test_host_data"}> : () -> memref<i32>
// CHECK-NEXT:            %17, %18, %19 = func.call @cld_suite_init_physics(%4, %5, %6, %7, %8, %13, %14) : (memref<32xi8>, memref<i32>, memref<?x32xi8>, memref<?xi32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> (memref<i32>, memref<512xi8>, memref<i32>)
// CHECK-NEXT:            "memref.copy"(%17, %16) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:            "memref.copy"(%18, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:            "memref.copy"(%19, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %3) <{prefix = "No suite part named ", suffix = " found in suite cld_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
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
// CHECK-LABEL:     func.func public @ccpp_physics_final(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}, %suite_part : memref<?xi8> {ccpp.name = "suite_part"}, %col_start : memref<i32> {ccpp.name = "col_start"}, %col_end : memref<i32> {ccpp.name = "col_end"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg"}, %errflg : memref<i32> {ccpp.name = "errflg"}) -> (memref<512xi8>, memref<i32>) attributes {bind_c_dim_exprs = ["", "", "", "", "", ""]} {
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
// CHECK-LABEL:     func.func public @ccpp_physics_suite_variables(%suite_name : memref<?xi8> {ccpp.name = "suite_name", ccpp.declared_intent = "in"}, %var_list : memref<memref<?xi8>> {ccpp.name = "var_list", ccpp.declared_intent = "out"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg", ccpp.declared_intent = "out"}, %errflg : memref<i32> {ccpp.name = "errflg", ccpp.declared_intent = "out"}, %input_vars : memref<i1> {ccpp.name = "input_vars", ccpp.declared_intent = "in", ccpp.optional}, %output_vars : memref<i1> {ccpp.name = "output_vars", ccpp.declared_intent = "in", ccpp.optional}) attributes {ccpp.fixed_interface} {
// CHECK:             %do_input = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> {ccpp.name = "do_input"} : () -> memref<i1>
// CHECK-NEXT:        %do_output = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> {ccpp.name = "do_output"} : () -> memref<i1>
// CHECK-NEXT:        "ccpp_utils.assign"() ({
// CHECK-NEXT:          "ccpp_utils.value_expr"(%errflg) : (memref<i32>) -> ()
// CHECK-NEXT:        }, {
// CHECK-NEXT:          %0 = arith.constant 0 : i32
// CHECK-NEXT:        }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:        "ccpp_utils.assign"() ({
// CHECK-NEXT:          "ccpp_utils.value_expr"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        }, {
// CHECK-NEXT:          "ccpp_utils.string_literal_expr"() <{text = ""}> : () -> ()
// CHECK-NEXT:        }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:        "ccpp_utils.assign"() ({
// CHECK-NEXT:          "ccpp_utils.value_expr"(%do_input) : (memref<i1>) -> ()
// CHECK-NEXT:        }, {
// CHECK-NEXT:          %1 = arith.constant true
// CHECK-NEXT:        }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:        "ccpp_utils.assign"() ({
// CHECK-NEXT:          "ccpp_utils.value_expr"(%do_output) : (memref<i1>) -> ()
// CHECK-NEXT:        }, {
// CHECK-NEXT:          %2 = arith.constant true
// CHECK-NEXT:        }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:        %3 = "ccpp_utils.call_expr"() <{callee = "present"}> ({
// CHECK-NEXT:          "ccpp_utils.value_expr"(%input_vars) : (memref<i1>) -> ()
// CHECK-NEXT:        }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i1
// CHECK-NEXT:        scf.if %3 {
// CHECK-NEXT:          "ccpp_utils.assign"() ({
// CHECK-NEXT:            "ccpp_utils.value_expr"(%do_input) : (memref<i1>) -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.value_expr"(%input_vars) : (memref<i1>) -> ()
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %4 = "ccpp_utils.call_expr"() <{callee = "present"}> ({
// CHECK-NEXT:          "ccpp_utils.value_expr"(%output_vars) : (memref<i1>) -> ()
// CHECK-NEXT:        }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i1
// CHECK-NEXT:        scf.if %4 {
// CHECK-NEXT:          "ccpp_utils.assign"() ({
// CHECK-NEXT:            "ccpp_utils.value_expr"(%do_output) : (memref<i1>) -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.value_expr"(%output_vars) : (memref<i1>) -> ()
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %5 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %6 = "ccpp_utils.strcmp"(%5) <{literal = "cld_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %6 {
// CHECK-NEXT:          %7 = "ccpp_utils.value_expr"(%do_input) : (memref<i1>) -> i1
// CHECK-NEXT:          %8 = "ccpp_utils.value_expr"(%do_output) : (memref<i1>) -> i1
// CHECK-NEXT:          %9 = arith.constant true
// CHECK-NEXT:          %10 = arith.xori %8, %9 : i1
// CHECK-NEXT:          %11 = arith.andi %7, %10 : i1
// CHECK-NEXT:          scf.if %11 {
// CHECK-NEXT:            "ccpp_utils.allocate"() <{var_name = "var_list"}> ({
// CHECK-NEXT:              %12 = arith.constant 12 : i32
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:            "ccpp_utils.assign"() ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                %13 = arith.constant 1 : i32
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "banana_array_dim                    "}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:            "ccpp_utils.assign"() ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                %14 = arith.constant 2 : i32
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "ccpp_constituent_tendencies         "}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:            "ccpp_utils.assign"() ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                %15 = arith.constant 3 : i32
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "ccpp_constituents                   "}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:            "ccpp_utils.assign"() ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                %16 = arith.constant 4 : i32
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "cloud_ice_dry_mixing_ratio          "}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:            "ccpp_utils.assign"() ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                %17 = arith.constant 5 : i32
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "cloud_liquid_dry_mixing_ratio       "}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:            "ccpp_utils.assign"() ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                %18 = arith.constant 6 : i32
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "number_of_ccpp_constituents         "}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:            "ccpp_utils.assign"() ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                %19 = arith.constant 7 : i32
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "surface_air_pressure                "}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:            "ccpp_utils.assign"() ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                %20 = arith.constant 8 : i32
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "temperature                         "}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:            "ccpp_utils.assign"() ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                %21 = arith.constant 9 : i32
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "tendency_of_cloud_liquid_dry_mixing_ratio"}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:            "ccpp_utils.assign"() ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                %22 = arith.constant 10 : i32
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "time_step_for_physics               "}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:            "ccpp_utils.assign"() ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                %23 = arith.constant 11 : i32
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "water_temperature_at_freezing       "}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:            "ccpp_utils.assign"() ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                %24 = arith.constant 12 : i32
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "water_vapor_specific_humidity       "}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            %25 = "ccpp_utils.value_expr"(%do_input) : (memref<i1>) -> i1
// CHECK-NEXT:            %26 = arith.constant true
// CHECK-NEXT:            %27 = arith.xori %25, %26 : i1
// CHECK-NEXT:            %28 = "ccpp_utils.value_expr"(%do_output) : (memref<i1>) -> i1
// CHECK-NEXT:            %29 = arith.andi %27, %28 : i1
// CHECK-NEXT:            scf.if %29 {
// CHECK-NEXT:              "ccpp_utils.allocate"() <{var_name = "var_list"}> ({
// CHECK-NEXT:                %30 = arith.constant 13 : i32
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %31 = arith.constant 1 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "ccpp_constituent_tendencies         "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %32 = arith.constant 2 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "ccpp_constituents                   "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %33 = arith.constant 3 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "ccpp_error_code                     "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %34 = arith.constant 4 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "ccpp_error_message                  "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %35 = arith.constant 5 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "cloud_ice_dry_mixing_ratio          "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %36 = arith.constant 6 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "cloud_liquid_dry_mixing_ratio       "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %37 = arith.constant 7 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "dynamic_constituents_for_cld_ice    "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %38 = arith.constant 8 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "dynamic_constituents_for_cld_liq    "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %39 = arith.constant 9 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "temperature                         "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %40 = arith.constant 10 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "tendency_of_cloud_liquid_dry_mixing_ratio"}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %41 = arith.constant 11 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "test_banana_constituent_index       "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %42 = arith.constant 12 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "test_banana_constituent_indices     "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %43 = arith.constant 13 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "water_vapor_specific_humidity       "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:            } else {
// CHECK-NEXT:              "ccpp_utils.allocate"() <{var_name = "var_list"}> ({
// CHECK-NEXT:                %44 = arith.constant 18 : i32
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %45 = arith.constant 1 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "banana_array_dim                    "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %46 = arith.constant 2 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "ccpp_constituent_tendencies         "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %47 = arith.constant 3 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "ccpp_constituents                   "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %48 = arith.constant 4 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "ccpp_error_code                     "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %49 = arith.constant 5 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "ccpp_error_message                  "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %50 = arith.constant 6 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "cloud_ice_dry_mixing_ratio          "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %51 = arith.constant 7 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "cloud_liquid_dry_mixing_ratio       "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %52 = arith.constant 8 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "dynamic_constituents_for_cld_ice    "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %53 = arith.constant 9 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "dynamic_constituents_for_cld_liq    "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %54 = arith.constant 10 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "number_of_ccpp_constituents         "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %55 = arith.constant 11 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "surface_air_pressure                "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %56 = arith.constant 12 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "temperature                         "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %57 = arith.constant 13 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "tendency_of_cloud_liquid_dry_mixing_ratio"}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %58 = arith.constant 14 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "test_banana_constituent_index       "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %59 = arith.constant 15 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "test_banana_constituent_indices     "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %60 = arith.constant 16 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "time_step_for_physics               "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %61 = arith.constant 17 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "water_temperature_at_freezing       "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %62 = arith.constant 18 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "water_vapor_specific_humidity       "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:            }
// CHECK-NEXT:          }
// CHECK-NEXT:        } else {
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %5) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:          %63 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %63, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return
// CHECK-NEXT:      }
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "cam_constituents_obj", base_type = "type", rank = 0 : i64, ddt_name = "ccpp_model_constituents_t", is_target = true}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_dyn_const", base_type = "type", rank = 1 : i64, ddt_name = "ccpp_constituent_properties_t", is_target = true}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_dyn_const_ice", base_type = "type", rank = 1 : i64, ddt_name = "ccpp_constituent_properties_t", is_target = true}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_all_constituents", base_type = "integer", rank = 1 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_constituent_array", base_type = "real", rank = 3 : i64, kind = "kind_phys", is_pointer = true}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_const_tend", base_type = "real", rank = 3 : i64, kind = "kind_phys", is_target = true}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_const_props", base_type = "type", rank = 1 : i64, ddt_name = "ccpp_constituent_prop_ptr_t", is_target = true}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_cld_liq_tend", base_type = "real", rank = 2 : i64, kind = "kind_phys", is_pointer = true}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_cld_ice_array", base_type = "real", rank = 2 : i64, kind = "kind_phys", is_pointer = true}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "lc_cld_liq_array", base_type = "real", rank = 2 : i64, kind = "kind_phys", is_pointer = true}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "cam_model_const_stdnames", base_type = "character", rank = 0 : i64, kind = "29", fixed_dim = 2 : i64}> ({
// CHECK-NEXT:        "ccpp_utils.array_constructor_expr"() <{elem_type = memref<29xi8>}> ({
// CHECK-NEXT:          "ccpp_utils.string_literal_expr"() <{text = "cloud_liquid_dry_mixing_ratio"}> : () -> ()
// CHECK-NEXT:        }, {
// CHECK-NEXT:          "ccpp_utils.string_literal_expr"() <{text = "cloud_ice_dry_mixing_ratio"}> : () -> ()
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "cam_model_const_indices", base_type = "integer", rank = 0 : i64, fixed_dim = 2 : i64}> ({
// CHECK-NEXT:        %0 = arith.constant -1 : i32
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "ccpp_utils.non_cam_host_constituent_api"() <{public_names = ["Cld_ccpp_is_scheme_constituent", "Cld_ccpp_deallocate_dynamic_constituents", "Cld_ccpp_register_constituents", "Cld_ccpp_number_constituents", "Cld_ccpp_initialize_constituents", "Cld_constituents_array", "Cld_advected_constituents_array", "Cld_const_get_index", "Cld_model_const_properties"]}> ({
// CHECK-NEXT:        func.func public @Cld_ccpp_is_scheme_constituent(%std_name : memref<?xi8> {ccpp.name = "std_name", ccpp.declared_intent = "in"}, %is_const : memref<i1> {ccpp.name = "is_const", ccpp.declared_intent = "out"}, %errflg : memref<i32> {ccpp.name = "errflg", ccpp.declared_intent = "out"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg", ccpp.declared_intent = "out"}) attributes {ccpp.fixed_interface} {
// CHECK-NEXT:          %lc_idx = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> {ccpp.name = "lc_idx"} : () -> memref<i32>
// CHECK-NEXT:          %lc_std_name = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> {ccpp.name = "lc_std_name"} : () -> memref<256xi8>
// CHECK-NEXT:          "ccpp_utils.clear_err_state"() <{errcode_var = "errflg", errmsg_var = "errmsg"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.assign"() ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "is_const"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            %1 = arith.constant false
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:          %2 = "ccpp_utils.call_expr"() <{callee = "any"}> ({
// CHECK-NEXT:            %3 = "ccpp_utils.var_ref_expr"() <{var_name = "cam_model_const_stdnames"}> : () -> i32
// CHECK-NEXT:            %4 = "ccpp_utils.var_ref_expr"() <{var_name = "std_name"}> : () -> i32
// CHECK-NEXT:            %5 = arith.cmpi eq, %3, %4 : i32
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i1
// CHECK-NEXT:          scf.if %2 {
// CHECK-NEXT:            "ccpp_utils.assign"() ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "is_const"}> : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              %6 = arith.constant true
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:            "ccpp_utils.return_stmt"() : () -> ()
// CHECK-NEXT:          }
// CHECK-NEXT:          %7 = "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "lc_dyn_const"}> : () -> ()
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i1
// CHECK-NEXT:          scf.if %7 {
// CHECK-NEXT:            "ccpp_utils.text_bounded_do_loop"() <{loop_var = "lc_idx", upper_expr = "size(lc_dyn_const)"}> ({
// CHECK-NEXT:              "ccpp_utils.ddt_method_call"() <{method = "standard_name", kwargs = []}> ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "lc_dyn_const"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "lc_idx"}> : () -> ()
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "lc_std_name"}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1, 0>} : () -> ()
// CHECK-NEXT:              %8 = "ccpp_utils.call_expr"() <{callee = "trim"}> ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "lc_std_name"}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i32
// CHECK-NEXT:              %9 = "ccpp_utils.call_expr"() <{callee = "trim"}> ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "std_name"}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i32
// CHECK-NEXT:              %10 = arith.cmpi eq, %8, %9 : i32
// CHECK-NEXT:              scf.if %10 {
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "is_const"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %11 = arith.constant true
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.return_stmt"() : () -> ()
// CHECK-NEXT:              }
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }
// CHECK-NEXT:          %12 = "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "lc_dyn_const_ice"}> : () -> ()
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i1
// CHECK-NEXT:          scf.if %12 {
// CHECK-NEXT:            "ccpp_utils.text_bounded_do_loop"() <{loop_var = "lc_idx", upper_expr = "size(lc_dyn_const_ice)"}> ({
// CHECK-NEXT:              "ccpp_utils.ddt_method_call"() <{method = "standard_name", kwargs = []}> ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "lc_dyn_const_ice"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "lc_idx"}> : () -> ()
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "lc_std_name"}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1, 0>} : () -> ()
// CHECK-NEXT:              %13 = "ccpp_utils.call_expr"() <{callee = "trim"}> ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "lc_std_name"}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i32
// CHECK-NEXT:              %14 = "ccpp_utils.call_expr"() <{callee = "trim"}> ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "std_name"}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i32
// CHECK-NEXT:              %15 = arith.cmpi eq, %13, %14 : i32
// CHECK-NEXT:              scf.if %15 {
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "is_const"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %16 = arith.constant true
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.return_stmt"() : () -> ()
// CHECK-NEXT:              }
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }
// CHECK-NEXT:          func.return
// CHECK-NEXT:        }
// CHECK-NEXT:        func.func public @Cld_ccpp_deallocate_dynamic_constituents() attributes {ccpp.fixed_interface} {
// CHECK-NEXT:          "ccpp_utils.safe_dealloc"() <{var_name = "lc_dyn_const"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.safe_dealloc"() <{var_name = "lc_dyn_const_ice"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.safe_dealloc"() <{var_name = "lc_all_constituents"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.safe_dealloc"() <{var_name = "lc_const_props"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.nullify_pointer"() <{ptr_name = "lc_constituent_array", if_associated}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.safe_dealloc"() <{var_name = "lc_const_tend"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.nullify_pointer"() <{ptr_name = "lc_cld_liq_tend"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.nullify_pointer"() <{ptr_name = "lc_cld_ice_array"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.nullify_pointer"() <{ptr_name = "lc_cld_liq_array"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.cam_direct_call"() <{callee = "cam_constituents_obj%reset", call_args = []}> : () -> ()
// CHECK-NEXT:          func.return
// CHECK-NEXT:        }
// CHECK-NEXT:        func.func public @Cld_ccpp_register_constituents(%host_constituents : memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">> {ccpp.name = "host_constituents", ccpp.declared_intent = "in", ccpp.target}, %errmsg : memref<512xi8> {ccpp.name = "errmsg", ccpp.declared_intent = "out"}, %errcode : memref<i32> {ccpp.name = "errcode", ccpp.declared_intent = "out"}) attributes {ccpp.fixed_interface, ccpp.uses = {ccpp_constituent_prop_mod = ["ccpp_constituent_properties_t", "ccpp_constituent_prop_ptr_t"], ccpp_scheme_utils = ["ccpp_scheme_utils_set_constituents"]}} {
// CHECK-NEXT:          %lc_i = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> {ccpp.name = "lc_i"} : () -> memref<i32>
// CHECK-NEXT:          %lc_num_consts = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> {ccpp.name = "lc_num_consts"} : () -> memref<i32>
// CHECK-NEXT:          %field_ind = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> {ccpp.name = "field_ind"} : () -> memref<i32>
// CHECK-NEXT:          %const_prop = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> {ccpp.name = "const_prop", ccpp.pointer} : () -> memref<!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>
// CHECK-NEXT:          %lc_props_ptr = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> {ccpp.name = "lc_props_ptr", ccpp.pointer} : () -> memref<0x!ccpp_utils.derived_type<"ccpp_constituent_prop_ptr_t">>
// CHECK-NEXT:          "ccpp_utils.clear_err_state"() <{errcode_var = "errcode", errmsg_var = "errmsg"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.assign"() ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "lc_num_consts"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            %1 = "ccpp_utils.call_expr"() <{callee = "size"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "host_constituents"}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i32
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:          %2 = "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "lc_dyn_const"}> : () -> ()
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i1
// CHECK-NEXT:          scf.if %2 {
// CHECK-NEXT:            "ccpp_utils.assign"() ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "lc_num_consts"}> : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              %3 = "ccpp_utils.var_ref_expr"() <{var_name = "lc_num_consts"}> : () -> i32
// CHECK-NEXT:              %4 = "ccpp_utils.call_expr"() <{callee = "size"}> ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "lc_dyn_const"}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i32
// CHECK-NEXT:              %5 = arith.addi %3, %4 : i32
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:          }
// CHECK-NEXT:          %6 = "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "lc_dyn_const_ice"}> : () -> ()
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i1
// CHECK-NEXT:          scf.if %6 {
// CHECK-NEXT:            "ccpp_utils.assign"() ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "lc_num_consts"}> : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              %7 = "ccpp_utils.var_ref_expr"() <{var_name = "lc_num_consts"}> : () -> i32
// CHECK-NEXT:              %8 = "ccpp_utils.call_expr"() <{callee = "size"}> ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "lc_dyn_const_ice"}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i32
// CHECK-NEXT:              %9 = arith.addi %7, %8 : i32
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:          }
// CHECK-NEXT:          "ccpp_utils.assign"() ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "lc_num_consts"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            %10 = "ccpp_utils.var_ref_expr"() <{var_name = "lc_num_consts"}> : () -> i32
// CHECK-NEXT:            %11 = arith.constant 2 : i32
// CHECK-NEXT:            %12 = arith.addi %10, %11 : i32
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:          "ccpp_utils.ddt_method_call"() <{method = "initialize_table", kwargs = []}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "cam_constituents_obj"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "lc_num_consts"}> : () -> ()
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 1, 0>} : () -> ()
// CHECK-NEXT:          "ccpp_utils.text_bounded_do_loop"() <{loop_var = "lc_i", upper_expr = "size(host_constituents)"}> ({
// CHECK-NEXT:            "ccpp_utils.allocate"() <{var_name = "const_prop", dims = [], stat_var = "errcode"}> : () -> ()
// CHECK-NEXT:            %13 = "ccpp_utils.var_ref_expr"() <{var_name = "errcode"}> : () -> i32
// CHECK-NEXT:            %14 = arith.constant 0 : i32
// CHECK-NEXT:            %15 = arith.cmpi ne, %13, %14 : i32
// CHECK-NEXT:            scf.if %15 {
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
// CHECK-NEXT:          %16 = "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "lc_dyn_const"}> : () -> ()
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i1
// CHECK-NEXT:          scf.if %16 {
// CHECK-NEXT:            "ccpp_utils.text_bounded_do_loop"() <{loop_var = "lc_i", upper_expr = "size(lc_dyn_const)"}> ({
// CHECK-NEXT:              "ccpp_utils.allocate"() <{var_name = "const_prop", dims = [], stat_var = "errcode"}> : () -> ()
// CHECK-NEXT:              %17 = "ccpp_utils.var_ref_expr"() <{var_name = "errcode"}> : () -> i32
// CHECK-NEXT:              %18 = arith.constant 0 : i32
// CHECK-NEXT:              %19 = arith.cmpi ne, %17, %18 : i32
// CHECK-NEXT:              scf.if %19 {
// CHECK-NEXT:                "ccpp_utils.error_exit"() <{errmsg_var = "errmsg", errmsg_text = "ERROR allocating const_prop"}> : () -> ()
// CHECK-NEXT:              }
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "const_prop"}> : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "lc_dyn_const"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "lc_i"}> : () -> ()
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.ddt_method_call"() <{method = "new_field"}> ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "cam_constituents_obj"}> : () -> ()
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
// CHECK-NEXT:          %20 = "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "lc_dyn_const_ice"}> : () -> ()
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 0>} : () -> i1
// CHECK-NEXT:          scf.if %20 {
// CHECK-NEXT:            "ccpp_utils.text_bounded_do_loop"() <{loop_var = "lc_i", upper_expr = "size(lc_dyn_const_ice)"}> ({
// CHECK-NEXT:              "ccpp_utils.allocate"() <{var_name = "const_prop", dims = [], stat_var = "errcode"}> : () -> ()
// CHECK-NEXT:              %21 = "ccpp_utils.var_ref_expr"() <{var_name = "errcode"}> : () -> i32
// CHECK-NEXT:              %22 = arith.constant 0 : i32
// CHECK-NEXT:              %23 = arith.cmpi ne, %21, %22 : i32
// CHECK-NEXT:              scf.if %23 {
// CHECK-NEXT:                "ccpp_utils.error_exit"() <{errmsg_var = "errmsg", errmsg_text = "ERROR allocating const_prop"}> : () -> ()
// CHECK-NEXT:              }
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "const_prop"}> : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "lc_dyn_const_ice"}> : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "lc_i"}> : () -> ()
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.ddt_method_call"() <{method = "new_field"}> ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "cam_constituents_obj"}> : () -> ()
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
// CHECK-NEXT:          %24 = "ccpp_utils.var_ref_expr"() <{var_name = "errcode"}> : () -> i32
// CHECK-NEXT:          %25 = arith.constant 0 : i32
// CHECK-NEXT:          %26 = arith.cmpi ne, %24, %25 : i32
// CHECK-NEXT:          scf.if %26 {
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
// CHECK-NEXT:              %27 = arith.constant true
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
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "cam_constituents_obj"}> : () -> ()
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
// CHECK-NEXT:          "ccpp_utils.allocate"() <{var_name = "const_prop", dims = [], stat_var = "errcode"}> : () -> ()
// CHECK-NEXT:          %28 = "ccpp_utils.var_ref_expr"() <{var_name = "errcode"}> : () -> i32
// CHECK-NEXT:          %29 = arith.constant 0 : i32
// CHECK-NEXT:          %30 = arith.cmpi ne, %28, %29 : i32
// CHECK-NEXT:          scf.if %30 {
// CHECK-NEXT:            "ccpp_utils.error_exit"() <{errmsg_var = "errmsg", errmsg_text = "ERROR allocating const_prop"}> : () -> ()
// CHECK-NEXT:          }
// CHECK-NEXT:          "ccpp_utils.ddt_method_call"() <{method = "instantiate", args = []}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "const_prop"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.keyword_arg_expr"() <{arg_name = "std_name"}> ({
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "cloud_ice_dry_mixing_ratio"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.keyword_arg_expr"() <{arg_name = "long_name"}> ({
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "Cloud ice dry mixing ratio"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.keyword_arg_expr"() <{arg_name = "diag_name"}> ({
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "cld_ice_array"}> : () -> ()
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
// CHECK-NEXT:              %31 = arith.constant true
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.keyword_arg_expr"() <{arg_name = "default_value"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "0.0_kind_phys"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.keyword_arg_expr"() <{arg_name = "errcode"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "errcode"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.keyword_arg_expr"() <{arg_name = "errmsg"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "errmsg"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 0, 9>} : () -> ()
// CHECK-NEXT:          "ccpp_utils.error_propagate"() <{errcode_var = "errcode"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.ddt_method_call"() <{method = "new_field"}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "cam_constituents_obj"}> : () -> ()
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
// CHECK-NEXT:          "ccpp_utils.text_bounded_do_loop"() <{loop_var = "lc_i", upper_expr = "size(cam_model_const_indices)"}> ({
// CHECK-NEXT:            "ccpp_utils.ddt_method_call"() <{method = "const_index"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "cam_constituents_obj"}> : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "field_ind"}> : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.var_ref_expr"() <{var_name = "cam_model_const_stdnames"}> : () -> ()
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
// CHECK-NEXT:              %32 = "ccpp_utils.var_ref_expr"() <{var_name = "field_ind"}> : () -> i32
// CHECK-NEXT:              %33 = arith.constant 0 : i32
// CHECK-NEXT:              %34 = arith.cmpi sgt, %32, %33 : i32
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.var_ref_expr"() <{var_name = "cam_model_const_indices"}> : () -> ()
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
// CHECK-NEXT:                      "ccpp_utils.var_ref_expr"() <{var_name = "cam_model_const_stdnames"}> : () -> ()
// CHECK-NEXT:                    }, {
// CHECK-NEXT:                      "ccpp_utils.var_ref_expr"() <{var_name = "lc_i"}> : () -> ()
// CHECK-NEXT:                    }) : () -> ()
// CHECK-NEXT:                  }) {regionSegmentSizes = array<i32: 1, 0>} : () -> ()
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          func.return
// CHECK-NEXT:        }
// CHECK-NEXT:        func.func public @Cld_ccpp_number_constituents(%num_advected : memref<i32> {ccpp.name = "num_advected", ccpp.declared_intent = "out"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg", ccpp.declared_intent = "out"}, %errcode : memref<i32> {ccpp.name = "errcode", ccpp.declared_intent = "out"}, %advected : memref<i1> {ccpp.name = "advected", ccpp.declared_intent = "in", ccpp.optional}) attributes {ccpp.fixed_interface} {
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
// CHECK-NEXT:          func.return
// CHECK-NEXT:        }
// CHECK-NEXT:        func.func public @Cld_ccpp_initialize_constituents(%ncols : memref<i32> {ccpp.name = "ncols", ccpp.declared_intent = "in"}, %pver : memref<i32> {ccpp.name = "pver", ccpp.declared_intent = "in"}, %errflg : memref<i32> {ccpp.name = "errflg", ccpp.declared_intent = "out"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg", ccpp.declared_intent = "out"}) attributes {ccpp.fixed_interface} {
// CHECK-NEXT:          "ccpp_utils.clear_err_state"() <{errcode_var = "errflg", errmsg_var = "errmsg"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.error_guard"() <{errmsg_text = "ccpp_initialize_constituents: register_constituents not called"}> ({
// CHECK-NEXT:            %1 = "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
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
// CHECK-NEXT:          "ccpp_utils.safe_dealloc"() <{var_name = "lc_const_tend"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.allocate"() <{var_name = "lc_const_tend"}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "ncols"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "pver"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            "ccpp_utils.call_expr"() <{callee = "size"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "lc_all_constituents"}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 0>} : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          "ccpp_utils.zero_fill"() <{var_name = "lc_const_tend"}> : () -> ()
// CHECK-NEXT:          %2 = "ccpp_utils.host_var_ref"() <{var_name = "lc_const_tend", module_name = ""}> : () -> memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          "ccpp_utils.acc_enter_data"(%2) {operandSegmentSizes = array<i32: 1, 0>} : (memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>) -> ()
// CHECK-NEXT:          "ccpp_utils.scoped_block"() ({
// CHECK-NEXT:            %lc_tend_idx = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> {ccpp.name = "lc_tend_idx"} : () -> memref<i32>
// CHECK-NEXT:            %lc_tend_errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> {ccpp.name = "lc_tend_errmsg"} : () -> memref<512xi8>
// CHECK-NEXT:            "ccpp_utils.nullify_pointer"() <{ptr_name = "lc_cld_liq_tend"}> : () -> ()
// CHECK-NEXT:            "ccpp_utils.ddt_method_call"() <{method = "const_index"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "cam_constituents_obj"}> : () -> ()
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
// CHECK-NEXT:              %3 = "ccpp_utils.var_ref_expr"() <{var_name = "errflg"}> : () -> i32
// CHECK-NEXT:              %4 = arith.constant 0 : i32
// CHECK-NEXT:              %5 = arith.cmpi eq, %3, %4 : i32
// CHECK-NEXT:              %6 = "ccpp_utils.var_ref_expr"() <{var_name = "lc_tend_idx"}> : () -> i32
// CHECK-NEXT:              %7 = arith.constant 0 : i32
// CHECK-NEXT:              %8 = arith.cmpi sgt, %6, %7 : i32
// CHECK-NEXT:              %9 = arith.andi %5, %8 : i1
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.pointer_slice_assign"() <{ptr_name = "lc_cld_liq_tend", array_name = "lc_const_tend", index_var = "lc_tend_idx"}> : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.error_exit"() <{errmsg_var = "errmsg", errflg_var = "errflg", errmsg_text = "ccpp_initialize_constituents: no constituent for tendency cloud_liquid_dry_mixing_ratio"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          "ccpp_utils.scoped_block"() ({
// CHECK-NEXT:            %lc_tend_idx_1 = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> {ccpp.name = "lc_tend_idx"} : () -> memref<i32>
// CHECK-NEXT:            %lc_tend_errmsg_1 = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> {ccpp.name = "lc_tend_errmsg"} : () -> memref<512xi8>
// CHECK-NEXT:            "ccpp_utils.nullify_pointer"() <{ptr_name = "lc_cld_ice_array"}> : () -> ()
// CHECK-NEXT:            "ccpp_utils.ddt_method_call"() <{method = "const_index"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "cam_constituents_obj"}> : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "lc_tend_idx"}> : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "cloud_ice_dry_mixing_ratio"}> : () -> ()
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
// CHECK-NEXT:              %10 = "ccpp_utils.var_ref_expr"() <{var_name = "errflg"}> : () -> i32
// CHECK-NEXT:              %11 = arith.constant 0 : i32
// CHECK-NEXT:              %12 = arith.cmpi eq, %10, %11 : i32
// CHECK-NEXT:              %13 = "ccpp_utils.var_ref_expr"() <{var_name = "lc_tend_idx"}> : () -> i32
// CHECK-NEXT:              %14 = arith.constant 0 : i32
// CHECK-NEXT:              %15 = arith.cmpi sgt, %13, %14 : i32
// CHECK-NEXT:              %16 = arith.andi %12, %15 : i1
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.pointer_slice_assign"() <{ptr_name = "lc_cld_ice_array", array_name = "lc_constituent_array", index_var = "lc_tend_idx"}> : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.error_exit"() <{errmsg_var = "errmsg", errflg_var = "errflg", errmsg_text = "ccpp_initialize_constituents: no constituent cloud_ice_dry_mixing_ratio"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          "ccpp_utils.scoped_block"() ({
// CHECK-NEXT:            %lc_tend_idx_2 = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> {ccpp.name = "lc_tend_idx"} : () -> memref<i32>
// CHECK-NEXT:            %lc_tend_errmsg_2 = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> {ccpp.name = "lc_tend_errmsg"} : () -> memref<512xi8>
// CHECK-NEXT:            "ccpp_utils.nullify_pointer"() <{ptr_name = "lc_cld_liq_array"}> : () -> ()
// CHECK-NEXT:            "ccpp_utils.ddt_method_call"() <{method = "const_index"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "cam_constituents_obj"}> : () -> ()
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
// CHECK-NEXT:              %17 = "ccpp_utils.var_ref_expr"() <{var_name = "errflg"}> : () -> i32
// CHECK-NEXT:              %18 = arith.constant 0 : i32
// CHECK-NEXT:              %19 = arith.cmpi eq, %17, %18 : i32
// CHECK-NEXT:              %20 = "ccpp_utils.var_ref_expr"() <{var_name = "lc_tend_idx"}> : () -> i32
// CHECK-NEXT:              %21 = arith.constant 0 : i32
// CHECK-NEXT:              %22 = arith.cmpi sgt, %20, %21 : i32
// CHECK-NEXT:              %23 = arith.andi %19, %22 : i1
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.pointer_slice_assign"() <{ptr_name = "lc_cld_liq_array", array_name = "lc_constituent_array", index_var = "lc_tend_idx"}> : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.error_exit"() <{errmsg_var = "errmsg", errflg_var = "errflg", errmsg_text = "ccpp_initialize_constituents: no constituent cloud_liquid_dry_mixing_ratio"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          func.return
// CHECK-NEXT:        }
// CHECK-NEXT:        func.func public @Cld_constituents_array() -> memref<0x0x0x!ccpp_utils.real_kind<"kind_phys">> attributes {ccpp.fixed_interface, ccpp.function_result} {
// CHECK-NEXT:          %ptr = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> {ccpp.name = "ptr", ccpp.pointer} : () -> memref<0x0x0x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          "ccpp_utils.pointer_assign"() <{ptr_name = "ptr"}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "lc_constituent_array"}> : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          func.return %ptr : memref<0x0x0x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.func public @Cld_advected_constituents_array() -> memref<0x0x0x!ccpp_utils.real_kind<"kind_phys">> attributes {ccpp.fixed_interface, ccpp.function_result} {
// CHECK-NEXT:          %ptr = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> {ccpp.name = "ptr", ccpp.pointer} : () -> memref<0x0x0x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          "ccpp_utils.pointer_assign"() <{ptr_name = "ptr"}> ({
// CHECK-NEXT:            "ccpp_utils.member_access_expr"() <{member = "advected_constituents_ptr()"}> ({
// CHECK-NEXT:              "ccpp_utils.var_ref_expr"() <{var_name = "cam_constituents_obj"}> : () -> ()
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          func.return %ptr : memref<0x0x0x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        }
// CHECK-NEXT:        func.func public @Cld_const_get_index(%std_name : memref<?xi8> {ccpp.name = "std_name", ccpp.declared_intent = "in"}, %index : memref<i32> {ccpp.name = "index", ccpp.declared_intent = "out"}, %errflg : memref<i32> {ccpp.name = "errflg", ccpp.declared_intent = "out"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg", ccpp.declared_intent = "out"}) attributes {ccpp.fixed_interface, ccpp.uses = {ccpp_constituent_prop_mod = ["to_lower"]}} {
// CHECK-NEXT:          "ccpp_utils.clear_err_state"() <{errcode_var = "errflg", errmsg_var = "errmsg"}> : () -> ()
// CHECK-NEXT:          "ccpp_utils.assign"() ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "index"}> : () -> ()
// CHECK-NEXT:          }, {
// CHECK-NEXT:            %1 = arith.constant -1 : i32
// CHECK-NEXT:          }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:          "ccpp_utils.error_guard"() <{errmsg_text = "const_get_index: constituents not registered"}> ({
// CHECK-NEXT:            %2 = "ccpp_utils.call_expr"() <{callee = "allocated"}> ({
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
// CHECK-NEXT:          %3 = "ccpp_utils.var_ref_expr"() <{var_name = "errflg"}> : () -> i32
// CHECK-NEXT:          %4 = arith.constant 0 : i32
// CHECK-NEXT:          %5 = arith.cmpi ne, %3, %4 : i32
// CHECK-NEXT:          %6 = "ccpp_utils.var_ref_expr"() <{var_name = "index"}> : () -> i32
// CHECK-NEXT:          %7 = arith.constant 0 : i32
// CHECK-NEXT:          %8 = arith.cmpi sle, %6, %7 : i32
// CHECK-NEXT:          %9 = arith.ori %5, %8 : i1
// CHECK-NEXT:          scf.if %9 {
// CHECK-NEXT:            "ccpp_utils.assign"() <{lhs_expr = "errflg", rhs_expr = "1"}> {regionSegmentSizes = array<i32: 0, 0>} : () -> ()
// CHECK-NEXT:            "ccpp_utils.write_stmt"() <{dest = "errmsg", format_spec = "(3a)", items = ["'const_get_index: constituent '", "trim(std_name)", "' not found'"]}> : () -> ()
// CHECK-NEXT:          }
// CHECK-NEXT:          func.return
// CHECK-NEXT:        }
// CHECK-NEXT:        func.func public @Cld_model_const_properties() -> memref<0x!ccpp_utils.derived_type<"ccpp_constituent_prop_ptr_t">> attributes {ccpp.fixed_interface, ccpp.function_result} {
// CHECK-NEXT:          %ptr = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> {ccpp.name = "ptr", ccpp.pointer} : () -> memref<0x!ccpp_utils.derived_type<"ccpp_constituent_prop_ptr_t">>
// CHECK-NEXT:          "ccpp_utils.pointer_assign"() <{ptr_name = "ptr"}> ({
// CHECK-NEXT:            "ccpp_utils.var_ref_expr"() <{var_name = "lc_const_props"}> : () -> ()
// CHECK-NEXT:          }) : () -> ()
// CHECK-NEXT:          func.return %ptr : memref<0x!ccpp_utils.derived_type<"ccpp_constituent_prop_ptr_t">>
// CHECK-NEXT:        }
// CHECK-NEXT:      }) : () -> ()
// CHECK-LABEL:     func.func private @cld_suite_register(memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>, memref<?x!ccpp_utils.derived_type<"ccpp_constituent_properties_t">>) -> (memref<512xi8>, memref<i32>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_initialize() -> (memref<i32>, memref<512xi8>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_finalize() -> (memref<i32>, memref<512xi8>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_physics(memref<32xi8>, memref<i32>, memref<?x32xi8>, memref<?xi32>, memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> (memref<i32>, memref<512xi8>, memref<i32>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_timestep_init_physics() -> (memref<i32>, memref<512xi8>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_timestep_final_physics() -> (memref<i32>, memref<512xi8>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_init_physics(memref<32xi8>, memref<i32>, memref<?x32xi8>, memref<?xi32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> (memref<i32>, memref<512xi8>, memref<i32>) attributes {module = "cld_suite_cap"}
// CHECK-LABEL:     func.func private @cld_suite_final_physics() -> (memref<512xi8>, memref<i32>) attributes {module = "cld_suite_cap"}
// CHECK:         }
// CHECK-LABEL:   builtin.module @ccpp_kinds {
// CHECK:           "ccpp_utils.kind_def"() <{kind_name = "kind_phys", kind_value = "REAL64", kind_module = "iso_fortran_env"}> : () -> ()
// CHECK-NEXT:    }
// CHECK-NEXT:  }
