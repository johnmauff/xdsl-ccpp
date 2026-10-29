// Test the completed MLIR IR (frontend + optimizer, no Fortran backend) for
// the capgen example.  Two suites (ddt_suite, temp_suite) with DDT arguments
// and optional entry points.
//
// RUN: python3 -m xdsl_ccpp.frontend.ccpp_xml --suites examples/capgen/scheme/ddt_suite.xml,examples/capgen/scheme/temp_suite.xml --scheme-files examples/capgen/scheme/make_ddt.meta,examples/capgen/scheme/environ_conditions.meta,examples/capgen/scheme/setup_coeffs.meta,examples/capgen/scheme/temp_set.meta,examples/capgen/scheme/temp_calc_adjust.meta,examples/capgen/scheme/temp_adjust.meta --host-files examples/capgen/host_ftn/test_host_data.meta,examples/capgen/host_ftn/test_host_mod.meta,examples/capgen/host_ftn/test_host.meta | python3 -m xdsl_ccpp.tools.ccpp_opt -p generate-meta-cap,generate-meta-kinds,generate-host-match,generate-arg-ownership,generate-suite-cap,generate-ccpp-cap,generate-cpp-cap,generate-kinds,strip-ccpp | python3 -m filecheck %s

// --- Suite cap module ---

// CHECK:       builtin.module {
// CHECK-LABEL:   builtin.module @temp_suite_cap attributes {ccpp_suite_cap = "temp_suite"} {
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
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "pcnst", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "index_qv", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "dim_inter", base_type = "integer", rank = 0 : i64}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "temp_inc_set", base_type = "real", rank = 0 : i64, kind = "kind_phys"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "to_promote", base_type = "real", rank = 2 : i64, kind = "kind_temp"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "promote_pcnst", base_type = "real", rank = 1 : i64, kind = "kind_phys"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "temp_calc", base_type = "real", rank = 2 : i64, kind = "kind_phys"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "interstitial_var", base_type = "integer", rank = 1 : i64}> : () -> ()
// CHECK-LABEL:     func.func public @temp_suite_register(%config_var : memref<i1> {ccpp.name = "config_var", ccpp.standard_name = "configuration_variable", ccpp.intent = "in"}) -> (memref<512xi8>, memref<i32>) attributes {ccpp_phase = "suite_register"} {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %dim_inter = "ccpp_utils.host_var_ref"() <{var_name = "dim_inter", module_name = ""}> : () -> memref<i32>
// CHECK-NEXT:        %1 = arith.constant 0 : i32
// CHECK-NEXT:        %2 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %3 = arith.cmpi eq, %2, %1 : i32
// CHECK-NEXT:        scf.if %3 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%dim_inter, %errmsg, %errflg) <{callee = "temp_calc_adjust_register", operand_names = ["dim_inter", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %4 = arith.constant 0 : i32
// CHECK-NEXT:        %5 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %6 = arith.cmpi eq, %5, %4 : i32
// CHECK-NEXT:        scf.if %6 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%config_var, %errmsg, %errflg) <{callee = "temp_adjust_register", operand_names = ["config_var", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i1>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @temp_suite_initialize() -> (memref<i32>, memref<512xi8>) attributes {ccpp_phase = "suite_initialize"} {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %ncols = "ccpp_utils.host_var_ref"() <{var_name = "ncols", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:        %pver = "ccpp_utils.host_var_ref"() <{var_name = "pver", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:        %pcnst = "ccpp_utils.host_var_ref"() <{var_name = "pcnst", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ncols, %pver) <{var_name = "to_promote", kind_name = "kind_temp"}> : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%pcnst) <{var_name = "promote_pcnst", kind_name = "kind_phys"}> : (memref<i32>) -> ()
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ncols, %pver) <{var_name = "temp_calc", kind_name = "kind_phys"}> : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_uninitialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        %4 = "llvm.load"(%3) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %5 = "ccpp_utils.strcmp"(%2, %4) <{length = 13 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %6 = arith.constant true
// CHECK-NEXT:        %7 = arith.xori %5, %6 : i1
// CHECK-NEXT:        scf.if %7 {
// CHECK-NEXT:          %8 = "ccpp_utils.trim"(%4) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in temp_suite_initialize"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %11 = "llvm.load"(%10) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %12 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%11, %12) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @temp_suite_finalize() -> (memref<i32>, memref<512xi8>) attributes {ccpp_phase = "suite_finalize"} {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %dim_inter = "ccpp_utils.host_var_ref"() <{var_name = "dim_inter", module_name = ""}> : () -> memref<i32>
// CHECK-NEXT:        %temp_inc_set = "ccpp_utils.host_var_ref"() <{var_name = "temp_inc_set", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        %4 = "llvm.load"(%3) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %5 = "ccpp_utils.strcmp"(%2, %4) <{length = 11 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %6 = arith.constant true
// CHECK-NEXT:        %7 = arith.xori %5, %6 : i1
// CHECK-NEXT:        scf.if %7 {
// CHECK-NEXT:          %8 = "ccpp_utils.trim"(%4) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in temp_suite_finalize"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = "llvm.mlir.addressof"() <{global_name = @const_uninitialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %11 = "llvm.load"(%10) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %12 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%11, %12) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @temp_suite_init_physics1(%temp_inc_in : memref<!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "temp_inc_in", ccpp.standard_name = "potential_temperature_increment", ccpp.intent = "in"}, %fudge : memref<!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "fudge", ccpp.standard_name = "random_fudge_factor", ccpp.intent = "in"}) -> (memref<512xi8>, memref<i32>) attributes {ccpp_phase = "group_init"} {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %temp_inc_set = "ccpp_utils.host_var_ref"() <{var_name = "temp_inc_set", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %ncols = "ccpp_utils.host_var_ref"() <{var_name = "ncols", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:        %pver = "ccpp_utils.host_var_ref"() <{var_name = "pver", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:        %pcnst = "ccpp_utils.host_var_ref"() <{var_name = "pcnst", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ncols, %pver) <{var_name = "to_promote", kind_name = "kind_temp"}> : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%pcnst) <{var_name = "promote_pcnst", kind_name = "kind_phys"}> : (memref<i32>) -> ()
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ncols, %pver) <{var_name = "temp_calc", kind_name = "kind_phys"}> : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        %4 = "llvm.load"(%3) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %5 = "ccpp_utils.strcmp"(%2, %4) <{length = 11 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %6 = arith.constant true
// CHECK-NEXT:        %7 = arith.xori %5, %6 : i1
// CHECK-NEXT:        scf.if %7 {
// CHECK-NEXT:          %8 = "ccpp_utils.trim"(%4) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in temp_suite_init_physics1"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = arith.constant 0 : i32
// CHECK-NEXT:        %11 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %12 = arith.cmpi eq, %11, %10 : i32
// CHECK-NEXT:        scf.if %12 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%temp_inc_in, %fudge, %temp_inc_set, %errmsg, %errflg) <{callee = "temp_set_init", operand_names = ["temp_inc_in", "fudge", "temp_inc_set", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @temp_suite_physics1(%ncol : memref<i32> {ccpp.name = "ncol", ccpp.standard_name = "horizontal_dimension", ccpp.intent = "in"}, %lev : memref<i32> {ccpp.name = "lev", ccpp.standard_name = "vertical_layer_dimension", ccpp.intent = "in"}, %timestep : memref<!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "timestep", ccpp.standard_name = "time_step_for_physics", ccpp.intent = "in"}, %temp_level : memref<?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "temp_level", ccpp.standard_name = "potential_temperature_at_interface", ccpp.intent = "inout", ccpp.dim_names = ["horizontal_dimension", "vertical_interface_dimension"]}, %temp_diag : memref<?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "temp_diag", ccpp.standard_name = "temperature_at_diagnostic_levels", ccpp.intent = "inout", ccpp.dim_names = ["horizontal_dimension", "6"]}, %temp : memref<?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "temp", ccpp.standard_name = "potential_temperature", ccpp.intent = "out", ccpp.dim_names = ["horizontal_dimension", "vertical_layer_dimension"]}, %ps : memref<?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "ps", ccpp.standard_name = "surface_air_pressure", ccpp.intent = "in", ccpp.dim_names = ["horizontal_dimension"]}, %slev_lbound : memref<i32> {ccpp.name = "slev_lbound", ccpp.standard_name = "lower_bound_of_vertical_dimension_of_soil", ccpp.intent = "in"}, %soil_levs : memref<?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "soil_levs", ccpp.standard_name = "soil_levels", ccpp.intent = "inout", ccpp.dim_names = ["upper_bound_of_vertical_dimension_of_soil"]}, %var_array : memref<?x?x?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "var_array", ccpp.standard_name = "array_variable_for_testing", ccpp.intent = "inout", ccpp.dim_names = ["horizontal_dimension", "2", "4", "6"]}) -> (memref<512xi8>, memref<i32>) attributes {ccpp_phase = "run"} {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %dim_inter = "ccpp_utils.host_var_ref"() <{var_name = "dim_inter", module_name = ""}> : () -> memref<i32>
// CHECK-NEXT:        %temp_inc_set = "ccpp_utils.host_var_ref"() <{var_name = "temp_inc_set", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %to_promote = "ccpp_utils.host_var_ref"() <{var_name = "to_promote", module_name = ""}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_temp">>
// CHECK-NEXT:        %promote_pcnst = "ccpp_utils.host_var_ref"() <{var_name = "promote_pcnst", module_name = ""}> : () -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_in_time_step}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        %4 = "llvm.load"(%3) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %5 = "ccpp_utils.strcmp"(%2, %4) <{length = 12 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %6 = arith.constant true
// CHECK-NEXT:        %7 = arith.xori %5, %6 : i1
// CHECK-NEXT:        scf.if %7 {
// CHECK-NEXT:          %8 = "ccpp_utils.trim"(%4) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in temp_suite_physics1"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = arith.constant 0 : i32
// CHECK-NEXT:        %11 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %12 = arith.cmpi eq, %11, %10 : i32
// CHECK-NEXT:        scf.if %12 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%ncol, %lev, %timestep, %temp_level, %temp_diag, %temp, %ps, %to_promote, %promote_pcnst, %slev_lbound, %soil_levs, %var_array, %errmsg, %errflg) <{callee = "temp_set_run", operand_names = ["ncol", "lev", "timestep", "temp_level", "temp_diag", "temp", "ps", "to_promote", "promote_pcnst", "slev_lbound", "soil_levs", "var_array", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_temp">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @temp_suite_timestep_init_physics1(%coeffs : memref<?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "coeffs", ccpp.standard_name = "coefficients_for_interpolation", ccpp.intent = "inout", ccpp.dim_names = ["horizontal_dimension"]}, %ncol : memref<i32> {ccpp.name = "ncol", ccpp.standard_name = "horizontal_dimension", ccpp.intent = "in"}, %temp_level : memref<?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "temp_level", ccpp.standard_name = "potential_temperature_at_interface", ccpp.intent = "inout", ccpp.dim_names = ["horizontal_dimension", "vertical_interface_dimension"]}) -> (memref<512xi8>, memref<i32>) attributes {ccpp_phase = "timestep_init"} {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %dim_inter = "ccpp_utils.host_var_ref"() <{var_name = "dim_inter", module_name = ""}> : () -> memref<i32>
// CHECK-NEXT:        %temp_inc_set = "ccpp_utils.host_var_ref"() <{var_name = "temp_inc_set", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %1 = arith.constant 0 : i32
// CHECK-NEXT:        %2 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %3 = arith.cmpi eq, %2, %1 : i32
// CHECK-NEXT:        scf.if %3 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%coeffs, %errmsg, %errflg) <{callee = "setup_coeffs_timestep_init", operand_names = ["coeffs", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %4 = arith.constant 0 : i32
// CHECK-NEXT:        %5 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %6 = arith.cmpi eq, %5, %4 : i32
// CHECK-NEXT:        scf.if %6 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%ncol, %temp_inc_set, %temp_level, %errmsg, %errflg) <{callee = "temp_set_timestep_initialize", operand_names = ["ncol", "temp_inc", "temp_level", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %7 = "llvm.mlir.addressof"() <{global_name = @const_in_time_step}> : () -> !llvm.ptr
// CHECK-NEXT:        %8 = "llvm.load"(%7) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %9 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%8, %9) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @temp_suite_timestep_final_physics1() -> (memref<i32>, memref<512xi8>) attributes {ccpp_phase = "timestep_final"} {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %dim_inter = "ccpp_utils.host_var_ref"() <{var_name = "dim_inter", module_name = ""}> : () -> memref<i32>
// CHECK-NEXT:        %temp_inc_set = "ccpp_utils.host_var_ref"() <{var_name = "temp_inc_set", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%2, %3) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @temp_suite_final_physics1() -> (memref<512xi8>, memref<i32>) attributes {ccpp_phase = "group_final"} {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %dim_inter = "ccpp_utils.host_var_ref"() <{var_name = "dim_inter", module_name = ""}> : () -> memref<i32>
// CHECK-NEXT:        %temp_inc_set = "ccpp_utils.host_var_ref"() <{var_name = "temp_inc_set", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        %4 = "llvm.load"(%3) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %5 = "ccpp_utils.strcmp"(%2, %4) <{length = 11 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %6 = arith.constant true
// CHECK-NEXT:        %7 = arith.xori %5, %6 : i1
// CHECK-NEXT:        scf.if %7 {
// CHECK-NEXT:          %8 = "ccpp_utils.trim"(%4) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in temp_suite_final_physics1"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = arith.constant 0 : i32
// CHECK-NEXT:        %11 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %12 = arith.cmpi eq, %11, %10 : i32
// CHECK-NEXT:        scf.if %12 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%errmsg, %errflg) <{callee = "temp_set_finalize", operand_names = ["errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @temp_suite_init_physics2() -> (memref<512xi8>, memref<i32>) attributes {ccpp_phase = "group_init"} {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %ncols = "ccpp_utils.host_var_ref"() <{var_name = "ncols", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:        %pver = "ccpp_utils.host_var_ref"() <{var_name = "pver", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:        %pcnst = "ccpp_utils.host_var_ref"() <{var_name = "pcnst", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ncols, %pver) <{var_name = "to_promote", kind_name = "kind_temp"}> : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%pcnst) <{var_name = "promote_pcnst", kind_name = "kind_phys"}> : (memref<i32>) -> ()
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ncols, %pver) <{var_name = "temp_calc", kind_name = "kind_phys"}> : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        %4 = "llvm.load"(%3) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %5 = "ccpp_utils.strcmp"(%2, %4) <{length = 11 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %6 = arith.constant true
// CHECK-NEXT:        %7 = arith.xori %5, %6 : i1
// CHECK-NEXT:        scf.if %7 {
// CHECK-NEXT:          %8 = "ccpp_utils.trim"(%4) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in temp_suite_init_physics2"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = arith.constant 0 : i32
// CHECK-NEXT:        %11 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %12 = arith.cmpi eq, %11, %10 : i32
// CHECK-NEXT:        scf.if %12 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%errmsg, %errflg) <{callee = "temp_calc_adjust_init", operand_names = ["errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %13 = arith.constant 0 : i32
// CHECK-NEXT:        %14 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %15 = arith.cmpi eq, %14, %13 : i32
// CHECK-NEXT:        scf.if %15 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%errmsg, %errflg) <{callee = "temp_adjust_init", operand_names = ["errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @temp_suite_physics2(%nbox : memref<i32> {ccpp.name = "nbox", ccpp.standard_name = "horizontal_dimension", ccpp.intent = "in"}, %timestep : memref<!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "timestep", ccpp.standard_name = "time_step_for_physics", ccpp.intent = "in"}, %temp_level : memref<?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "temp_level", ccpp.standard_name = "potential_temperature_at_interface", ccpp.intent = "in", ccpp.dim_names = ["horizontal_dimension", "vertical_interface_dimension"]}, %temp_layer : memref<?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "temp_layer", ccpp.standard_name = "potential_temperature", ccpp.intent = "inout", ccpp.dim_names = ["horizontal_dimension", "vertical_layer_dimension"]}, %qv : memref<?x?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "qv", ccpp.standard_name = "water_vapor_specific_humidity", ccpp.intent = "inout", ccpp.dim_names = ["horizontal_dimension", "vertical_layer_dimension"], ccpp.optional}, %ps : memref<?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "ps", ccpp.standard_name = "surface_air_pressure", ccpp.intent = "inout", ccpp.dim_names = ["horizontal_dimension"]}) -> (memref<512xi8>, memref<i32>) attributes {ccpp_phase = "run"} {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %dim_inter = "ccpp_utils.host_var_ref"() <{var_name = "dim_inter", module_name = ""}> : () -> memref<i32>
// CHECK-NEXT:        %temp_inc_set = "ccpp_utils.host_var_ref"() <{var_name = "temp_inc_set", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %temp_calc = "ccpp_utils.host_var_ref"() <{var_name = "temp_calc", module_name = ""}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %interstitial_var = "ccpp_utils.host_var_ref"() <{var_name = "interstitial_var", module_name = ""}> : () -> memref<?xi32>
// CHECK-NEXT:        %to_promote = "ccpp_utils.host_var_ref"() <{var_name = "to_promote", module_name = ""}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_temp">>
// CHECK-NEXT:        %promote_pcnst = "ccpp_utils.host_var_ref"() <{var_name = "promote_pcnst", module_name = ""}> : () -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%dim_inter) <{var_name = "interstitial_var", kind_name = "kind_phys"}> : (memref<i32>) -> ()
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_in_time_step}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        %4 = "llvm.load"(%3) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %5 = "ccpp_utils.strcmp"(%2, %4) <{length = 12 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %6 = arith.constant true
// CHECK-NEXT:        %7 = arith.xori %5, %6 : i1
// CHECK-NEXT:        scf.if %7 {
// CHECK-NEXT:          %8 = "ccpp_utils.trim"(%4) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in temp_suite_physics2"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = arith.constant 0 : i32
// CHECK-NEXT:        %11 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %12 = arith.cmpi eq, %11, %10 : i32
// CHECK-NEXT:        scf.if %12 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%nbox, %timestep, %temp_level, %temp_calc, %errmsg, %errflg) <{callee = "temp_calc_adjust_run", operand_names = ["nbox", "timestep", "temp_level", "temp_calc", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        "ccpp_utils.active_check"() <{condition_expr = "(index_qv > 0)"}> ({
// CHECK-NEXT:          %13 = arith.constant 0 : i32
// CHECK-NEXT:          %14 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:          %15 = arith.cmpi eq, %14, %13 : i32
// CHECK-NEXT:          scf.if %15 {
// CHECK-NEXT:            "ccpp_utils.kw_call"(%nbox, %timestep, %interstitial_var, %temp_calc, %temp_layer, %qv, %ps, %to_promote, %promote_pcnst, %errmsg, %errflg) <{callee = "temp_adjust_run", operand_names = ["foo", "timestep", "interstitial_var", "temp_prev", "temp_layer", "qv", "ps", "to_promote", "promote_pcnst", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?xi32>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_temp">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:          }
// CHECK-NEXT:        }, {
// CHECK-NEXT:          %16 = arith.constant 0 : i32
// CHECK-NEXT:          %17 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:          %18 = arith.cmpi eq, %17, %16 : i32
// CHECK-NEXT:          scf.if %18 {
// CHECK-NEXT:            "ccpp_utils.kw_call"(%nbox, %timestep, %interstitial_var, %temp_calc, %temp_layer, %ps, %to_promote, %promote_pcnst, %errmsg, %errflg) <{callee = "temp_adjust_run", operand_names = ["foo", "timestep", "interstitial_var", "temp_prev", "temp_layer", "ps", "to_promote", "promote_pcnst", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?xi32>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_temp">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:          }
// CHECK-NEXT:        }) : () -> ()
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @temp_suite_timestep_init_physics2() -> (memref<i32>, memref<512xi8>) attributes {ccpp_phase = "timestep_init"} {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %dim_inter = "ccpp_utils.host_var_ref"() <{var_name = "dim_inter", module_name = ""}> : () -> memref<i32>
// CHECK-NEXT:        %temp_inc_set = "ccpp_utils.host_var_ref"() <{var_name = "temp_inc_set", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_in_time_step}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%2, %3) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @temp_suite_timestep_final_physics2() -> (memref<i32>, memref<512xi8>) attributes {ccpp_phase = "timestep_final"} {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %dim_inter = "ccpp_utils.host_var_ref"() <{var_name = "dim_inter", module_name = ""}> : () -> memref<i32>
// CHECK-NEXT:        %temp_inc_set = "ccpp_utils.host_var_ref"() <{var_name = "temp_inc_set", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%2, %3) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @temp_suite_final_physics2() -> (memref<512xi8>, memref<i32>) attributes {ccpp_phase = "group_final"} {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %dim_inter = "ccpp_utils.host_var_ref"() <{var_name = "dim_inter", module_name = ""}> : () -> memref<i32>
// CHECK-NEXT:        %temp_inc_set = "ccpp_utils.host_var_ref"() <{var_name = "temp_inc_set", module_name = ""}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %interstitial_var = "ccpp_utils.host_var_ref"() <{var_name = "interstitial_var", module_name = ""}> : () -> memref<?xi32>
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        %4 = "llvm.load"(%3) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %5 = "ccpp_utils.strcmp"(%2, %4) <{length = 11 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %6 = arith.constant true
// CHECK-NEXT:        %7 = arith.xori %5, %6 : i1
// CHECK-NEXT:        scf.if %7 {
// CHECK-NEXT:          %8 = "ccpp_utils.trim"(%4) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in temp_suite_final_physics2"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = arith.constant 0 : i32
// CHECK-NEXT:        %11 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %12 = arith.cmpi eq, %11, %10 : i32
// CHECK-NEXT:        scf.if %12 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%errmsg, %errflg) <{callee = "temp_calc_adjust_finalize", operand_names = ["errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %13 = arith.constant 0 : i32
// CHECK-NEXT:        %14 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %15 = arith.cmpi eq, %14, %13 : i32
// CHECK-NEXT:        scf.if %15 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%interstitial_var, %errmsg, %errflg) <{callee = "temp_adjust_finalize", operand_names = ["interstitial_var", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<?xi32>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func private @temp_calc_adjust_register(memref<i32>, memref<512xi8>, memref<i32>) -> () attributes {module = "temp_calc_adjust"}
// CHECK-LABEL:     func.func private @temp_adjust_register(memref<i1>, memref<512xi8>, memref<i32>) -> () attributes {module = "temp_adjust"}
// CHECK-LABEL:     func.func private @temp_set_init(memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "temp_set"}
// CHECK-LABEL:     func.func private @temp_set_run(memref<i32>, memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_temp">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "temp_set"}
// CHECK-LABEL:     func.func private @setup_coeffs_timestep_init(memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "setup_coeffs"}
// CHECK-LABEL:     func.func private @temp_set_timestep_initialize(memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "temp_set"}
// CHECK-LABEL:     func.func private @temp_set_finalize(memref<512xi8>, memref<i32>) -> () attributes {module = "temp_set"}
// CHECK-LABEL:     func.func private @temp_calc_adjust_init(memref<512xi8>, memref<i32>) -> () attributes {module = "temp_calc_adjust"}
// CHECK-LABEL:     func.func private @temp_adjust_init(memref<512xi8>, memref<i32>) -> () attributes {module = "temp_adjust"}
// CHECK-LABEL:     func.func private @temp_calc_adjust_run(memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "temp_calc_adjust"}
// CHECK-LABEL:     func.func private @temp_adjust_run(memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?xi32>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_temp">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "temp_adjust"}
// CHECK-LABEL:     func.func private @temp_calc_adjust_finalize(memref<512xi8>, memref<i32>) -> () attributes {module = "temp_calc_adjust"}
// CHECK-LABEL:     func.func private @temp_adjust_finalize(memref<?xi32>, memref<512xi8>, memref<i32>) -> () attributes {module = "temp_adjust"}
// CHECK:         }
// CHECK-LABEL:   builtin.module @ddt_suite_cap attributes {ccpp_suite_cap = "ddt_suite"} {
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
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "ncols", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "vmr", base_type = "type", rank = 0 : i64, ddt_name = "vmr_type"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "o3", base_type = "real", rank = 1 : i64, kind = "kind_phys"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "hno3", base_type = "real", rank = 1 : i64, kind = "kind_phys"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.module_var"() <{var_name = "model_times", base_type = "integer", rank = 1 : i64}> : () -> ()
// CHECK-LABEL:     func.func public @ddt_suite_register() -> (memref<i32>, memref<512xi8>) attributes {ccpp_phase = "suite_register"} {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ddt_suite_initialize() -> (memref<i32>, memref<512xi8>) attributes {ccpp_phase = "suite_initialize"} {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %ncols = "ccpp_utils.host_var_ref"() <{var_name = "ncols", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ncols) <{var_name = "o3", kind_name = "kind_phys"}> : (memref<i32>) -> ()
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%ncols) <{var_name = "hno3", kind_name = "kind_phys"}> : (memref<i32>) -> ()
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
// CHECK-NEXT:        %10 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %11 = "llvm.load"(%10) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %12 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%11, %12) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ddt_suite_finalize() -> (memref<i32>, memref<512xi8>) attributes {ccpp_phase = "suite_finalize"} {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %vmr = "ccpp_utils.host_var_ref"() <{var_name = "vmr", module_name = ""}> : () -> memref<!ccpp_utils.derived_type<"vmr_type">>
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
// CHECK-NEXT:        %10 = "llvm.mlir.addressof"() <{global_name = @const_uninitialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %11 = "llvm.load"(%10) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %12 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%11, %12) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ddt_suite_init_data_prep(%nbox : memref<i32> {ccpp.name = "nbox", ccpp.standard_name = "horizontal_dimension", ccpp.intent = "in"}, %model_times : memref<?xi32> {ccpp.name = "model_times", ccpp.standard_name = "model_times", ccpp.intent = "out", ccpp.dim_names = ["number_of_model_times"], ccpp.allocatable}) -> (memref<512xi8>, memref<i32>, memref<i32>) attributes {ccpp_phase = "group_init"} {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %ntimes = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %vmr = "ccpp_utils.host_var_ref"() <{var_name = "vmr", module_name = ""}> : () -> memref<!ccpp_utils.derived_type<"vmr_type">>
// CHECK-NEXT:        %o3 = "ccpp_utils.host_var_ref"() <{var_name = "o3", module_name = ""}> : () -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %hno3 = "ccpp_utils.host_var_ref"() <{var_name = "hno3", module_name = ""}> : () -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%nbox) <{var_name = "o3", kind_name = "kind_phys"}> : (memref<i32>) -> ()
// CHECK-NEXT:        "ccpp_utils.lazy_alloc"(%nbox) <{var_name = "hno3", kind_name = "kind_phys"}> : (memref<i32>) -> ()
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        %4 = "llvm.load"(%3) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %5 = "ccpp_utils.strcmp"(%2, %4) <{length = 11 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %6 = arith.constant true
// CHECK-NEXT:        %7 = arith.xori %5, %6 : i1
// CHECK-NEXT:        scf.if %7 {
// CHECK-NEXT:          %8 = "ccpp_utils.trim"(%4) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in ddt_suite_init_data_prep"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = arith.constant 0 : i32
// CHECK-NEXT:        %11 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %12 = arith.cmpi eq, %11, %10 : i32
// CHECK-NEXT:        scf.if %12 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%nbox, %vmr, %errmsg, %errflg) <{callee = "make_ddt_init", operand_names = ["nbox", "vmr", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<!ccpp_utils.derived_type<"vmr_type">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %13 = arith.constant 0 : i32
// CHECK-NEXT:        %14 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %15 = arith.cmpi eq, %14, %13 : i32
// CHECK-NEXT:        scf.if %15 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%nbox, %o3, %hno3, %ntimes, %model_times, %errmsg, %errflg) <{callee = "environ_conditions_init", operand_names = ["nbox", "o3", "hno3", "ntimes", "model_times", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<?xi32>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg, %ntimes : memref<512xi8>, memref<i32>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ddt_suite_data_prep(%cols : memref<i32> {ccpp.name = "cols", ccpp.standard_name = "horizontal_loop_begin", ccpp.intent = "in"}, %cole : memref<i32> {ccpp.name = "cole", ccpp.standard_name = "horizontal_loop_end", ccpp.intent = "in"}, %psurf : memref<?x!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "psurf", ccpp.standard_name = "surface_air_pressure", ccpp.intent = "in", ccpp.dim_names = ["horizontal_dimension"]}) -> (memref<512xi8>, memref<i32>) attributes {ccpp_phase = "run"} {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %o3 = "ccpp_utils.host_var_ref"() <{var_name = "o3", module_name = ""}> : () -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %1 = "ccpp_utils.rank_reducing_slice"(%o3, %cols, %cole) <{dim_pattern = "R"}> {operandSegmentSizes = array<i32: 1, 1, 1, 0>} : (memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>) -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %hno3 = "ccpp_utils.host_var_ref"() <{var_name = "hno3", module_name = ""}> : () -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %2 = "ccpp_utils.rank_reducing_slice"(%hno3, %cols, %cole) <{dim_pattern = "R"}> {operandSegmentSizes = array<i32: 1, 1, 1, 0>} : (memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>) -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:        %vmr = "ccpp_utils.host_var_ref"() <{var_name = "vmr", module_name = ""}> : () -> memref<!ccpp_utils.derived_type<"vmr_type">>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @const_in_time_step}> : () -> !llvm.ptr
// CHECK-NEXT:        %4 = "llvm.load"(%3) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %5 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        %6 = "llvm.load"(%5) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %7 = "ccpp_utils.strcmp"(%4, %6) <{length = 12 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %8 = arith.constant true
// CHECK-NEXT:        %9 = arith.xori %7, %8 : i1
// CHECK-NEXT:        scf.if %9 {
// CHECK-NEXT:          %10 = "ccpp_utils.trim"(%6) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %10) <{prefix = "Invalid initial CCPP state, '", suffix = "' in ddt_suite_data_prep"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %11 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %11, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %12 = arith.constant 0 : i32
// CHECK-NEXT:        %13 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %14 = arith.cmpi eq, %13, %12 : i32
// CHECK-NEXT:        scf.if %14 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%cols, %cole, %1, %2, %vmr, %errmsg, %errflg) <{callee = "make_ddt_run", operand_names = ["cols", "cole", "O3", "HNO3", "vmr", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<i32>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.derived_type<"vmr_type">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %15 = arith.constant 0 : i32
// CHECK-NEXT:        %16 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %17 = arith.cmpi eq, %16, %15 : i32
// CHECK-NEXT:        scf.if %17 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%psurf, %errmsg, %errflg) <{callee = "environ_conditions_run", operand_names = ["psurf", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ddt_suite_timestep_init_data_prep() -> (memref<i32>, memref<512xi8>) attributes {ccpp_phase = "timestep_init"} {
// CHECK:             %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %vmr = "ccpp_utils.host_var_ref"() <{var_name = "vmr", module_name = ""}> : () -> memref<!ccpp_utils.derived_type<"vmr_type">>
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_in_time_step}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%2, %3) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errflg, %errmsg : memref<i32>, memref<512xi8>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ddt_suite_timestep_final_data_prep(%ncols : memref<i32> {ccpp.name = "ncols", ccpp.standard_name = "horizontal_dimension", ccpp.intent = "in"}) -> (memref<512xi8>, memref<i32>) attributes {ccpp_phase = "timestep_final"} {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %vmr = "ccpp_utils.host_var_ref"() <{var_name = "vmr", module_name = ""}> : () -> memref<!ccpp_utils.derived_type<"vmr_type">>
// CHECK-NEXT:        %1 = arith.constant 0 : i32
// CHECK-NEXT:        %2 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %3 = arith.cmpi eq, %2, %1 : i32
// CHECK-NEXT:        scf.if %3 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%ncols, %vmr, %errmsg, %errflg) <{callee = "make_ddt_timestep_final", operand_names = ["ncols", "vmr", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<!ccpp_utils.derived_type<"vmr_type">>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        %4 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %5 = "llvm.load"(%4) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %6 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        "llvm.store"(%5, %6) <{ordering = 0 : i64}> : (!llvm.array<16 x i8>, !llvm.ptr) -> ()
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ddt_suite_final_data_prep(%ntimes : memref<i32> {ccpp.name = "ntimes", ccpp.standard_name = "number_of_model_times", ccpp.intent = "in"}, %model_times : memref<?xi32> {ccpp.name = "model_times", ccpp.standard_name = "model_times", ccpp.intent = "in", ccpp.dim_names = ["number_of_model_times"]}) -> (memref<512xi8>, memref<i32>) attributes {ccpp_phase = "group_final"} {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        "ccpp_utils.clear_string"(%errmsg) : (memref<512xi8>) -> ()
// CHECK-NEXT:        %vmr = "ccpp_utils.host_var_ref"() <{var_name = "vmr", module_name = ""}> : () -> memref<!ccpp_utils.derived_type<"vmr_type">>
// CHECK-NEXT:        %1 = "llvm.mlir.addressof"() <{global_name = @const_initialized}> : () -> !llvm.ptr
// CHECK-NEXT:        %2 = "llvm.load"(%1) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %3 = "llvm.mlir.addressof"() <{global_name = @ccpp_suite_state}> : () -> !llvm.ptr
// CHECK-NEXT:        %4 = "llvm.load"(%3) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<16 x i8>
// CHECK-NEXT:        %5 = "ccpp_utils.strcmp"(%2, %4) <{length = 11 : i64}> : (!llvm.array<16 x i8>, !llvm.array<16 x i8>) -> i1
// CHECK-NEXT:        %6 = arith.constant true
// CHECK-NEXT:        %7 = arith.xori %5, %6 : i1
// CHECK-NEXT:        scf.if %7 {
// CHECK-NEXT:          %8 = "ccpp_utils.trim"(%4) : (!llvm.array<16 x i8>) -> !llvm.array<16 x i8>
// CHECK-NEXT:          "ccpp_utils.write_errmsg"(%errmsg, %8) <{prefix = "Invalid initial CCPP state, '", suffix = "' in ddt_suite_final_data_prep"}> : (memref<512xi8>, !llvm.array<16 x i8>) -> ()
// CHECK-NEXT:          %9 = arith.constant 1 : i32
// CHECK-NEXT:          memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:        }
// CHECK-NEXT:        %10 = arith.constant 0 : i32
// CHECK-NEXT:        %11 = memref.load %errflg[] : memref<i32>
// CHECK-NEXT:        %12 = arith.cmpi eq, %11, %10 : i32
// CHECK-NEXT:        scf.if %12 {
// CHECK-NEXT:          "ccpp_utils.kw_call"(%ntimes, %model_times, %errmsg, %errflg) <{callee = "environ_conditions_finalize", operand_names = ["ntimes", "model_times", "errmsg", "errflg"], result_names = [], overrides = {}}> : (memref<i32>, memref<?xi32>, memref<512xi8>, memref<i32>) -> ()
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func private @make_ddt_init(memref<i32>, memref<!ccpp_utils.derived_type<"vmr_type">>, memref<512xi8>, memref<i32>) -> () attributes {module = "make_ddt"}
// CHECK-LABEL:     func.func private @environ_conditions_init(memref<i32>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<?xi32>, memref<512xi8>, memref<i32>) -> () attributes {module = "environ_conditions"}
// CHECK-LABEL:     func.func private @make_ddt_run(memref<i32>, memref<i32>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.derived_type<"vmr_type">>, memref<512xi8>, memref<i32>) -> () attributes {module = "make_ddt"}
// CHECK-LABEL:     func.func private @environ_conditions_run(memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<512xi8>, memref<i32>) -> () attributes {module = "environ_conditions"}
// CHECK-LABEL:     func.func private @make_ddt_timestep_final(memref<i32>, memref<!ccpp_utils.derived_type<"vmr_type">>, memref<512xi8>, memref<i32>) -> () attributes {module = "make_ddt"}
// CHECK-LABEL:     func.func private @environ_conditions_finalize(memref<i32>, memref<?xi32>, memref<512xi8>, memref<i32>) -> () attributes {module = "environ_conditions"}
// CHECK:         }
// CHECK-LABEL:   builtin.module @Ddt_ccpp_cap {
// CHECK:           "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "config_var", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "phys_state", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "ncols", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "pver", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "dt", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "temp_interfaces", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "temp_diag", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "temp_midpoints", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "slev_lbound", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "var_array", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "index_qv", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "pverP", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "pcnst", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "coeffs", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "temp_inc", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "num_model_times", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<1 x i8>, sym_name = "model_times", linkage = #llvm.linkage<"external">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_mod"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<9 x i8>, sym_name = "str_ddt_suite", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "ddt_suite"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<10 x i8>, sym_name = "str_temp_suite", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "temp_suite"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<9 x i8>, sym_name = "str_data_prep", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "data_prep"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<8 x i8>, sym_name = "str_physics1", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "physics1"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<8 x i8>, sym_name = "str_physics2", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32, constant, value = "physics2"}> ({
// CHECK-NEXT:      }) : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<0 x i8>, sym_name = "vmr_type", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "make_ddt"} : () -> ()
// CHECK-NEXT:      "llvm.mlir.global"() <{global_type = !llvm.array<0 x i8>, sym_name = "physics_state", linkage = #llvm.linkage<"internal">, addr_space = 0 : i32}> ({
// CHECK-NEXT:      }) {module = "test_host_data"} : () -> ()
// CHECK-LABEL:     func.func public @ccpp_register(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "ddt_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3, %4 = func.call @ddt_suite_register() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:          "memref.copy"(%3, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          "memref.copy"(%4, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          %5 = "ccpp_utils.strcmp"(%1) <{literal = "temp_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %5 {
// CHECK-NEXT:            %6 = "ccpp_utils.host_var_ref"() <{var_name = "config_var", module_name = "test_host_mod"}> : () -> memref<i1>
// CHECK-NEXT:            %7, %8 = func.call @temp_suite_register(%6) : (memref<i1>) -> (memref<512xi8>, memref<i32>)
// CHECK-NEXT:            "memref.copy"(%7, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:            "memref.copy"(%8, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %9 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:          }
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_init(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "ddt_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3, %4 = func.call @ddt_suite_initialize() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:          "memref.copy"(%3, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          "memref.copy"(%4, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          %5 = "ccpp_utils.strcmp"(%1) <{literal = "temp_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %5 {
// CHECK-NEXT:            %6, %7 = func.call @temp_suite_initialize() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:            "memref.copy"(%6, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:            "memref.copy"(%7, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %8 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %8, %errflg[] : memref<i32>
// CHECK-NEXT:          }
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_final(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}) -> (memref<512xi8>, memref<i32>) {
// CHECK:             %errmsg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<512xi8>
// CHECK-NEXT:        %errflg = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:        %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "ddt_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3, %4 = func.call @ddt_suite_finalize() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:          "memref.copy"(%3, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          "memref.copy"(%4, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:        } else {
// CHECK-NEXT:          %5 = "ccpp_utils.strcmp"(%1) <{literal = "temp_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %5 {
// CHECK-NEXT:            %6, %7 = func.call @temp_suite_finalize() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:            "memref.copy"(%6, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:            "memref.copy"(%7, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %8 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %8, %errflg[] : memref<i32>
// CHECK-NEXT:          }
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_physics_run(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}, %suite_part : memref<?xi8> {ccpp.name = "suite_part"}, %cols : memref<i32> {ccpp.name = "cols", ccpp.standard_name = "horizontal_loop_begin", ccpp.intent = "in"}, %cole : memref<i32> {ccpp.name = "cole", ccpp.standard_name = "horizontal_loop_end", ccpp.intent = "in"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg"}, %errflg : memref<i32> {ccpp.name = "errflg"}) -> (memref<512xi8>, memref<i32>) attributes {bind_c_dim_exprs = ["", "", "", "", "", ""]} {
// CHECK:             %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "ddt_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:          %4 = "ccpp_utils.host_var_ref"() <{var_name = "phys_state", module_name = "test_host_mod"}> {member_name = "ps"} : () -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %5 = "ccpp_utils.rank_reducing_slice"(%4, %cols, %cole) <{dim_pattern = "R"}> {operandSegmentSizes = array<i32: 1, 1, 1, 0>} : (memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>) -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:          %6 = "ccpp_utils.strcmp"(%3) <{literal = "data_prep"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %6 {
// CHECK-NEXT:            %7, %8 = func.call @ddt_suite_data_prep(%cols, %cole, %5) : (memref<i32>, memref<i32>, memref<?x!ccpp_utils.real_kind<"kind_phys">>) -> (memref<512xi8>, memref<i32>)
// CHECK-NEXT:            "memref.copy"(%7, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:            "memref.copy"(%8, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %3) <{prefix = "No suite part named ", suffix = " found in suite ddt_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %9 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:          }
// CHECK-NEXT:        } else {
// CHECK-NEXT:          %10 = "ccpp_utils.strcmp"(%1) <{literal = "temp_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %10 {
// CHECK-NEXT:            %11 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:            %nbox = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:            %12 = memref.load %cols[] : memref<i32>
// CHECK-NEXT:            %13 = memref.load %cole[] : memref<i32>
// CHECK-NEXT:            %14 = arith.subi %13, %12 : i32
// CHECK-NEXT:            %15 = arith.constant 1 : i32
// CHECK-NEXT:            %16 = arith.addi %14, %15 : i32
// CHECK-NEXT:            memref.store %16, %nbox[] : memref<i32>
// CHECK-NEXT:            %17 = "ccpp_utils.host_var_ref"() <{var_name = "dt", module_name = "test_host_mod"}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %18 = "ccpp_utils.host_var_ref"() <{var_name = "temp_interfaces", module_name = "test_host_mod"}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %19 = "ccpp_utils.host_var_ref"() <{var_name = "temp_midpoints", module_name = "test_host_mod"}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %20 = "ccpp_utils.host_var_ref"() <{var_name = "phys_state", module_name = "test_host_mod"}> {member_name = "q(:, :, index_qv)"} : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %21 = "ccpp_utils.host_var_ref"() <{var_name = "phys_state", module_name = "test_host_mod"}> {member_name = "ps"} : () -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %ncol = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:            %22 = memref.load %cols[] : memref<i32>
// CHECK-NEXT:            %23 = memref.load %cole[] : memref<i32>
// CHECK-NEXT:            %24 = arith.subi %23, %22 : i32
// CHECK-NEXT:            %25 = arith.constant 1 : i32
// CHECK-NEXT:            %26 = arith.addi %24, %25 : i32
// CHECK-NEXT:            memref.store %26, %ncol[] : memref<i32>
// CHECK-NEXT:            %27 = "ccpp_utils.host_var_ref"() <{var_name = "pver", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:            %28 = "ccpp_utils.host_var_ref"() <{var_name = "dt", module_name = "test_host_mod"}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %29 = "ccpp_utils.host_var_ref"() <{var_name = "temp_interfaces", module_name = "test_host_mod"}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %30 = "ccpp_utils.host_var_ref"() <{var_name = "temp_diag", module_name = "test_host_mod"}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %31 = "ccpp_utils.host_var_ref"() <{var_name = "temp_midpoints", module_name = "test_host_mod"}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %32 = "ccpp_utils.host_var_ref"() <{var_name = "phys_state", module_name = "test_host_mod"}> {member_name = "ps"} : () -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %33 = "ccpp_utils.host_var_ref"() <{var_name = "slev_lbound", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:            %34 = "ccpp_utils.host_var_ref"() <{var_name = "phys_state", module_name = "test_host_mod"}> {member_name = "soil_levs"} : () -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %35 = "ccpp_utils.host_var_ref"() <{var_name = "var_array", module_name = "test_host_mod"}> : () -> memref<?x?x?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %36 = arith.constant 1 : i32
// CHECK-NEXT:            %37 = "ccpp_utils.host_var_ref"() <{var_name = "pverP", module_name = "test_host_mod"}> : () -> i32
// CHECK-NEXT:            %38 = "ccpp_utils.host_var_ref"() <{var_name = "pver", module_name = "test_host_mod"}> : () -> i32
// CHECK-NEXT:            %39 = "ccpp_utils.host_var_ref"() <{var_name = "pcnst", module_name = "test_host_mod"}> : () -> i32
// CHECK-NEXT:            %40 = "ccpp_utils.rank_reducing_slice"(%18, %cols, %36, %cole, %37) <{dim_pattern = "RR"}> {operandSegmentSizes = array<i32: 1, 2, 2, 0>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, i32) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %41 = "ccpp_utils.rank_reducing_slice"(%19, %cols, %36, %cole, %38) <{dim_pattern = "RR"}> {operandSegmentSizes = array<i32: 1, 2, 2, 0>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, i32) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %42 = "ccpp_utils.rank_reducing_slice"(%20, %cols, %36, %36, %cole, %38, %39) <{dim_pattern = "RRR"}> {operandSegmentSizes = array<i32: 1, 3, 3, 0>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, i32, memref<i32>, i32, i32) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %43 = "ccpp_utils.rank_reducing_slice"(%21, %cols, %cole) <{dim_pattern = "R"}> {operandSegmentSizes = array<i32: 1, 1, 1, 0>} : (memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>) -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %44 = arith.constant 1 : i32
// CHECK-NEXT:            %45 = "ccpp_utils.host_var_ref"() <{var_name = "pverP", module_name = "test_host_mod"}> : () -> i32
// CHECK-NEXT:            %46 = "ccpp_utils.rank_reducing_slice"(%29, %cols, %44, %cole, %45) <{dim_pattern = "RR"}> {operandSegmentSizes = array<i32: 1, 2, 2, 0>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, i32) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %47 = "ccpp_utils.rank_reducing_slice"(%31, %cols, %44, %cole, %27) <{dim_pattern = "RR"}> {operandSegmentSizes = array<i32: 1, 2, 2, 0>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, memref<i32>) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %48 = "ccpp_utils.rank_reducing_slice"(%32, %cols, %cole) <{dim_pattern = "R"}> {operandSegmentSizes = array<i32: 1, 1, 1, 0>} : (memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>) -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %49 = "ccpp_utils.strcmp"(%11) <{literal = "physics1"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:            scf.if %49 {
// CHECK-NEXT:              %50, %51 = func.call @temp_suite_physics1(%ncol, %27, %28, %46, %30, %47, %48, %33, %34, %35) : (memref<i32>, memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x?x!ccpp_utils.real_kind<"kind_phys">>) -> (memref<512xi8>, memref<i32>)
// CHECK-NEXT:              "memref.copy"(%50, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:              "memref.copy"(%51, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:            } else {
// CHECK-NEXT:              %52 = "ccpp_utils.strcmp"(%11) <{literal = "physics2"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:              scf.if %52 {
// CHECK-NEXT:                %53, %54 = "ccpp_utils.kw_call"(%nbox, %17, %40, %41, %42, %43) <{callee = "temp_suite_physics2", operand_names = ["nbox", "timestep", "temp_level", "temp_layer", "qv", "ps"], result_names = ["errmsg", "errflg"], overrides = {}}> : (memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>) -> (memref<512xi8>, memref<i32>)
// CHECK-NEXT:                "memref.copy"(%53, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:                "memref.copy"(%54, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:              } else {
// CHECK-NEXT:                "ccpp_utils.write_errmsg"(%errmsg, %11) <{prefix = "No suite part named ", suffix = " found in suite temp_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:                %55 = arith.constant 1 : i32
// CHECK-NEXT:                memref.store %55, %errflg[] : memref<i32>
// CHECK-NEXT:              }
// CHECK-NEXT:            }
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %56 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %56, %errflg[] : memref<i32>
// CHECK-NEXT:          }
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_physics_timestep_init(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}, %suite_part : memref<?xi8> {ccpp.name = "suite_part"}, %col_start : memref<i32> {ccpp.name = "col_start"}, %col_end : memref<i32> {ccpp.name = "col_end"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg"}, %errflg : memref<i32> {ccpp.name = "errflg"}) -> (memref<512xi8>, memref<i32>) attributes {bind_c_dim_exprs = ["", "", "", "", "", ""]} {
// CHECK:             %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "ddt_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:          %4 = "ccpp_utils.strcmp"(%3) <{literal = "data_prep"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %4 {
// CHECK-NEXT:            %5, %6 = func.call @ddt_suite_timestep_init_data_prep() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:            "memref.copy"(%5, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:            "memref.copy"(%6, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %3) <{prefix = "No suite part named ", suffix = " found in suite ddt_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %7 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %7, %errflg[] : memref<i32>
// CHECK-NEXT:          }
// CHECK-NEXT:        } else {
// CHECK-NEXT:          %8 = "ccpp_utils.strcmp"(%1) <{literal = "temp_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %8 {
// CHECK-NEXT:            %9 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:            %10 = "ccpp_utils.host_var_ref"() <{var_name = "coeffs", module_name = "test_host_mod"}> : () -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %ncol = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:            %11 = memref.load %col_start[] : memref<i32>
// CHECK-NEXT:            %12 = memref.load %col_end[] : memref<i32>
// CHECK-NEXT:            %13 = arith.subi %12, %11 : i32
// CHECK-NEXT:            %14 = arith.constant 1 : i32
// CHECK-NEXT:            %15 = arith.addi %13, %14 : i32
// CHECK-NEXT:            memref.store %15, %ncol[] : memref<i32>
// CHECK-NEXT:            %16 = "ccpp_utils.host_var_ref"() <{var_name = "temp_interfaces", module_name = "test_host_mod"}> : () -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %17 = arith.constant 1 : i32
// CHECK-NEXT:            %18 = "ccpp_utils.host_var_ref"() <{var_name = "pverP", module_name = "test_host_mod"}> : () -> i32
// CHECK-NEXT:            %19 = "ccpp_utils.rank_reducing_slice"(%10, %col_start, %col_end) <{dim_pattern = "R"}> {operandSegmentSizes = array<i32: 1, 1, 1, 0>} : (memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<i32>) -> memref<?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %20 = "ccpp_utils.rank_reducing_slice"(%16, %col_start, %17, %col_end, %18) <{dim_pattern = "RR"}> {operandSegmentSizes = array<i32: 1, 2, 2, 0>} : (memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, i32, memref<i32>, i32) -> memref<?x?x!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %21 = "ccpp_utils.strcmp"(%9) <{literal = "physics1"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:            scf.if %21 {
// CHECK-NEXT:              %22, %23 = func.call @temp_suite_timestep_init_physics1(%19, %ncol, %20) : (memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> (memref<512xi8>, memref<i32>)
// CHECK-NEXT:              "memref.copy"(%22, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:              "memref.copy"(%23, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:            } else {
// CHECK-NEXT:              %24 = "ccpp_utils.strcmp"(%9) <{literal = "physics2"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:              scf.if %24 {
// CHECK-NEXT:                %25, %26 = func.call @temp_suite_timestep_init_physics2() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:                "memref.copy"(%25, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:                "memref.copy"(%26, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:              } else {
// CHECK-NEXT:                "ccpp_utils.write_errmsg"(%errmsg, %9) <{prefix = "No suite part named ", suffix = " found in suite temp_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:                %27 = arith.constant 1 : i32
// CHECK-NEXT:                memref.store %27, %errflg[] : memref<i32>
// CHECK-NEXT:              }
// CHECK-NEXT:            }
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %28 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %28, %errflg[] : memref<i32>
// CHECK-NEXT:          }
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_physics_timestep_final(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}, %suite_part : memref<?xi8> {ccpp.name = "suite_part"}, %col_start : memref<i32> {ccpp.name = "col_start"}, %col_end : memref<i32> {ccpp.name = "col_end"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg"}, %errflg : memref<i32> {ccpp.name = "errflg"}) -> (memref<512xi8>, memref<i32>) attributes {bind_c_dim_exprs = ["", "", "", "", "", ""]} {
// CHECK:             %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "ddt_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:          %ncols = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:          %4 = memref.load %col_start[] : memref<i32>
// CHECK-NEXT:          %5 = memref.load %col_end[] : memref<i32>
// CHECK-NEXT:          %6 = arith.subi %5, %4 : i32
// CHECK-NEXT:          %7 = arith.constant 1 : i32
// CHECK-NEXT:          %8 = arith.addi %6, %7 : i32
// CHECK-NEXT:          memref.store %8, %ncols[] : memref<i32>
// CHECK-NEXT:          %9 = "ccpp_utils.strcmp"(%3) <{literal = "data_prep"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %9 {
// CHECK-NEXT:            %10, %11 = func.call @ddt_suite_timestep_final_data_prep(%ncols) : (memref<i32>) -> (memref<512xi8>, memref<i32>)
// CHECK-NEXT:            "memref.copy"(%10, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:            "memref.copy"(%11, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %3) <{prefix = "No suite part named ", suffix = " found in suite ddt_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %12 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %12, %errflg[] : memref<i32>
// CHECK-NEXT:          }
// CHECK-NEXT:        } else {
// CHECK-NEXT:          %13 = "ccpp_utils.strcmp"(%1) <{literal = "temp_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %13 {
// CHECK-NEXT:            %14 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:            %15 = "ccpp_utils.strcmp"(%14) <{literal = "physics1"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:            scf.if %15 {
// CHECK-NEXT:              %16, %17 = func.call @temp_suite_timestep_final_physics1() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:              "memref.copy"(%16, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:              "memref.copy"(%17, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:            } else {
// CHECK-NEXT:              %18 = "ccpp_utils.strcmp"(%14) <{literal = "physics2"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:              scf.if %18 {
// CHECK-NEXT:                %19, %20 = func.call @temp_suite_timestep_final_physics2() : () -> (memref<i32>, memref<512xi8>)
// CHECK-NEXT:                "memref.copy"(%19, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:                "memref.copy"(%20, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:              } else {
// CHECK-NEXT:                "ccpp_utils.write_errmsg"(%errmsg, %14) <{prefix = "No suite part named ", suffix = " found in suite temp_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:                %21 = arith.constant 1 : i32
// CHECK-NEXT:                memref.store %21, %errflg[] : memref<i32>
// CHECK-NEXT:              }
// CHECK-NEXT:            }
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %22 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %22, %errflg[] : memref<i32>
// CHECK-NEXT:          }
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_physics_init(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}, %suite_part : memref<?xi8> {ccpp.name = "suite_part"}, %col_start : memref<i32> {ccpp.name = "col_start"}, %col_end : memref<i32> {ccpp.name = "col_end"}, %model_times : memref<?xi32> {ccpp.name = "model_times", ccpp.standard_name = "model_times", ccpp.intent = "out", ccpp.dim_names = ["number_of_model_times"], ccpp.allocatable}, %fudge : memref<!ccpp_utils.real_kind<"kind_phys">> {ccpp.name = "fudge", ccpp.standard_name = "random_fudge_factor", ccpp.intent = "in"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg"}, %errflg : memref<i32> {ccpp.name = "errflg"}) -> (memref<512xi8>, memref<i32>) attributes {bind_c_dim_exprs = ["", "", "", "", "", "", "", ""]} {
// CHECK:             %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "ddt_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:          %nbox = "memref.alloca"() <{operandSegmentSizes = array<i32: 0, 0>}> : () -> memref<i32>
// CHECK-NEXT:          %4 = memref.load %col_start[] : memref<i32>
// CHECK-NEXT:          %5 = memref.load %col_end[] : memref<i32>
// CHECK-NEXT:          %6 = arith.subi %5, %4 : i32
// CHECK-NEXT:          %7 = arith.constant 1 : i32
// CHECK-NEXT:          %8 = arith.addi %6, %7 : i32
// CHECK-NEXT:          memref.store %8, %nbox[] : memref<i32>
// CHECK-NEXT:          %9 = "ccpp_utils.strcmp"(%3) <{literal = "data_prep"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %9 {
// CHECK-NEXT:            %10 = "ccpp_utils.host_var_ref"() <{var_name = "num_model_times", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:            %11, %12, %13 = func.call @ddt_suite_init_data_prep(%nbox, %model_times) : (memref<i32>, memref<?xi32>) -> (memref<512xi8>, memref<i32>, memref<i32>)
// CHECK-NEXT:            "memref.copy"(%11, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:            "memref.copy"(%12, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:            "memref.copy"(%13, %10) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %3) <{prefix = "No suite part named ", suffix = " found in suite ddt_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %14 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %14, %errflg[] : memref<i32>
// CHECK-NEXT:          }
// CHECK-NEXT:        } else {
// CHECK-NEXT:          %15 = "ccpp_utils.strcmp"(%1) <{literal = "temp_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %15 {
// CHECK-NEXT:            %16 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:            %17 = "ccpp_utils.host_var_ref"() <{var_name = "temp_inc", module_name = "test_host_mod"}> : () -> memref<!ccpp_utils.real_kind<"kind_phys">>
// CHECK-NEXT:            %18 = "ccpp_utils.strcmp"(%16) <{literal = "physics1"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:            scf.if %18 {
// CHECK-NEXT:              %19, %20 = func.call @temp_suite_init_physics1(%17, %fudge) : (memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>) -> (memref<512xi8>, memref<i32>)
// CHECK-NEXT:              "memref.copy"(%19, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:              "memref.copy"(%20, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:            } else {
// CHECK-NEXT:              %21 = "ccpp_utils.strcmp"(%16) <{literal = "physics2"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:              scf.if %21 {
// CHECK-NEXT:                %22, %23 = func.call @temp_suite_init_physics2() : () -> (memref<512xi8>, memref<i32>)
// CHECK-NEXT:                "memref.copy"(%22, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:                "memref.copy"(%23, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:              } else {
// CHECK-NEXT:                "ccpp_utils.write_errmsg"(%errmsg, %16) <{prefix = "No suite part named ", suffix = " found in suite temp_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:                %24 = arith.constant 1 : i32
// CHECK-NEXT:                memref.store %24, %errflg[] : memref<i32>
// CHECK-NEXT:              }
// CHECK-NEXT:            }
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %25 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %25, %errflg[] : memref<i32>
// CHECK-NEXT:          }
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return %errmsg, %errflg : memref<512xi8>, memref<i32>
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func public @ccpp_physics_final(%suite_name : memref<?xi8> {ccpp.name = "suite_name"}, %suite_part : memref<?xi8> {ccpp.name = "suite_part"}, %col_start : memref<i32> {ccpp.name = "col_start"}, %col_end : memref<i32> {ccpp.name = "col_end"}, %errmsg : memref<512xi8> {ccpp.name = "errmsg"}, %errflg : memref<i32> {ccpp.name = "errflg"}) -> (memref<512xi8>, memref<i32>) attributes {bind_c_dim_exprs = ["", "", "", "", "", ""]} {
// CHECK:             %0 = arith.constant 0 : i32
// CHECK-NEXT:        memref.store %0, %errflg[] : memref<i32>
// CHECK-NEXT:        %1 = "ccpp_utils.trim"(%suite_name) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:        %2 = "ccpp_utils.strcmp"(%1) <{literal = "ddt_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %2 {
// CHECK-NEXT:          %3 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:          %4 = "ccpp_utils.host_var_ref"() <{var_name = "num_model_times", module_name = "test_host_mod"}> : () -> memref<i32>
// CHECK-NEXT:          %5 = "ccpp_utils.host_var_ref"() <{var_name = "model_times", module_name = "test_host_mod"}> : () -> memref<?xi32>
// CHECK-NEXT:          %6 = "ccpp_utils.strcmp"(%3) <{literal = "data_prep"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %6 {
// CHECK-NEXT:            %7, %8 = func.call @ddt_suite_final_data_prep(%4, %5) : (memref<i32>, memref<?xi32>) -> (memref<512xi8>, memref<i32>)
// CHECK-NEXT:            "memref.copy"(%7, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:            "memref.copy"(%8, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %3) <{prefix = "No suite part named ", suffix = " found in suite ddt_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %9 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %9, %errflg[] : memref<i32>
// CHECK-NEXT:          }
// CHECK-NEXT:        } else {
// CHECK-NEXT:          %10 = "ccpp_utils.strcmp"(%1) <{literal = "temp_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %10 {
// CHECK-NEXT:            %11 = "ccpp_utils.trim"(%suite_part) : (memref<?xi8>) -> memref<?xi8>
// CHECK-NEXT:            %12 = "ccpp_utils.strcmp"(%11) <{literal = "physics1"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:            scf.if %12 {
// CHECK-NEXT:              %13, %14 = func.call @temp_suite_final_physics1() : () -> (memref<512xi8>, memref<i32>)
// CHECK-NEXT:              "memref.copy"(%13, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:              "memref.copy"(%14, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:            } else {
// CHECK-NEXT:              %15 = "ccpp_utils.strcmp"(%11) <{literal = "physics2"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:              scf.if %15 {
// CHECK-NEXT:                %16, %17 = func.call @temp_suite_final_physics2() : () -> (memref<512xi8>, memref<i32>)
// CHECK-NEXT:                "memref.copy"(%16, %errmsg) : (memref<512xi8>, memref<512xi8>) -> ()
// CHECK-NEXT:                "memref.copy"(%17, %errflg) : (memref<i32>, memref<i32>) -> ()
// CHECK-NEXT:              } else {
// CHECK-NEXT:                "ccpp_utils.write_errmsg"(%errmsg, %11) <{prefix = "No suite part named ", suffix = " found in suite temp_suite"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:                %18 = arith.constant 1 : i32
// CHECK-NEXT:                memref.store %18, %errflg[] : memref<i32>
// CHECK-NEXT:              }
// CHECK-NEXT:            }
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %19 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %19, %errflg[] : memref<i32>
// CHECK-NEXT:          }
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
// CHECK-NEXT:        %4 = arith.constant 10 : index
// CHECK-NEXT:        %5 = memref.alloc(%4) : memref<?xi8>
// CHECK-NEXT:        %6 = "llvm.mlir.addressof"() <{global_name = @str_temp_suite}> : () -> !llvm.ptr
// CHECK-NEXT:        %7 = "llvm.load"(%6) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<10 x i8>
// CHECK-NEXT:        "ccpp_utils.set_string"(%5, %7) : (memref<?xi8>, !llvm.array<10 x i8>) -> ()
// CHECK-NEXT:        memref.store %5, %suites[] : memref<memref<?xi8>>
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
// CHECK-NEXT:          %7 = "ccpp_utils.strcmp"(%1) <{literal = "temp_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %7 {
// CHECK-NEXT:            %8 = arith.constant 8 : index
// CHECK-NEXT:            %9 = memref.alloc(%8) : memref<?xi8>
// CHECK-NEXT:            %10 = "llvm.mlir.addressof"() <{global_name = @str_physics1}> : () -> !llvm.ptr
// CHECK-NEXT:            %11 = "llvm.load"(%10) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<8 x i8>
// CHECK-NEXT:            "ccpp_utils.set_string"(%9, %11) : (memref<?xi8>, !llvm.array<8 x i8>) -> ()
// CHECK-NEXT:            memref.store %9, %part_list[] : memref<memref<?xi8>>
// CHECK-NEXT:            %12 = arith.constant 8 : index
// CHECK-NEXT:            %13 = memref.alloc(%12) : memref<?xi8>
// CHECK-NEXT:            %14 = "llvm.mlir.addressof"() <{global_name = @str_physics2}> : () -> !llvm.ptr
// CHECK-NEXT:            %15 = "llvm.load"(%14) <{ordering = 0 : i64}> : (!llvm.ptr) -> !llvm.array<8 x i8>
// CHECK-NEXT:            "ccpp_utils.set_string"(%13, %15) : (memref<?xi8>, !llvm.array<8 x i8>) -> ()
// CHECK-NEXT:            memref.store %13, %part_list[] : memref<memref<?xi8>>
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %1) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %16 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %16, %errflg[] : memref<i32>
// CHECK-NEXT:          }
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
// CHECK-NEXT:        %6 = "ccpp_utils.strcmp"(%5) <{literal = "ddt_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:        scf.if %6 {
// CHECK-NEXT:          %7 = "ccpp_utils.value_expr"(%do_input) : (memref<i1>) -> i1
// CHECK-NEXT:          %8 = "ccpp_utils.value_expr"(%do_output) : (memref<i1>) -> i1
// CHECK-NEXT:          %9 = arith.constant true
// CHECK-NEXT:          %10 = arith.xori %8, %9 : i1
// CHECK-NEXT:          %11 = arith.andi %7, %10 : i1
// CHECK-NEXT:          scf.if %11 {
// CHECK-NEXT:            "ccpp_utils.allocate"() <{var_name = "var_list"}> ({
// CHECK-NEXT:              %12 = arith.constant 3 : i32
// CHECK-NEXT:            }) : () -> ()
// CHECK-NEXT:            "ccpp_utils.assign"() ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                %13 = arith.constant 1 : i32
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "model_times                         "}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:            "ccpp_utils.assign"() ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                %14 = arith.constant 2 : i32
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "number_of_model_times               "}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:            "ccpp_utils.assign"() ({
// CHECK-NEXT:              "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                %15 = arith.constant 3 : i32
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:            }, {
// CHECK-NEXT:              "ccpp_utils.string_literal_expr"() <{text = "surface_air_pressure                "}> : () -> ()
// CHECK-NEXT:            }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:          } else {
// CHECK-NEXT:            %16 = "ccpp_utils.value_expr"(%do_input) : (memref<i1>) -> i1
// CHECK-NEXT:            %17 = arith.constant true
// CHECK-NEXT:            %18 = arith.xori %16, %17 : i1
// CHECK-NEXT:            %19 = "ccpp_utils.value_expr"(%do_output) : (memref<i1>) -> i1
// CHECK-NEXT:            %20 = arith.andi %18, %19 : i1
// CHECK-NEXT:            scf.if %20 {
// CHECK-NEXT:              "ccpp_utils.allocate"() <{var_name = "var_list"}> ({
// CHECK-NEXT:                %21 = arith.constant 5 : i32
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %22 = arith.constant 1 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "ccpp_error_code                     "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %23 = arith.constant 2 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "ccpp_error_message                  "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %24 = arith.constant 3 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "model_times                         "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %25 = arith.constant 4 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "number_of_model_times               "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %26 = arith.constant 5 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "surface_air_pressure                "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:            } else {
// CHECK-NEXT:              "ccpp_utils.allocate"() <{var_name = "var_list"}> ({
// CHECK-NEXT:                %27 = arith.constant 5 : i32
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %28 = arith.constant 1 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "ccpp_error_code                     "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %29 = arith.constant 2 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "ccpp_error_message                  "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %30 = arith.constant 3 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "model_times                         "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %31 = arith.constant 4 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "number_of_model_times               "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %32 = arith.constant 5 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "surface_air_pressure                "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:            }
// CHECK-NEXT:          }
// CHECK-NEXT:        } else {
// CHECK-NEXT:          %33 = "ccpp_utils.strcmp"(%5) <{literal = "temp_suite"}> : (memref<?xi8>) -> i1
// CHECK-NEXT:          scf.if %33 {
// CHECK-NEXT:            %34 = "ccpp_utils.value_expr"(%do_input) : (memref<i1>) -> i1
// CHECK-NEXT:            %35 = "ccpp_utils.value_expr"(%do_output) : (memref<i1>) -> i1
// CHECK-NEXT:            %36 = arith.constant true
// CHECK-NEXT:            %37 = arith.xori %35, %36 : i1
// CHECK-NEXT:            %38 = arith.andi %34, %37 : i1
// CHECK-NEXT:            scf.if %38 {
// CHECK-NEXT:              "ccpp_utils.allocate"() <{var_name = "var_list"}> ({
// CHECK-NEXT:                %39 = arith.constant 10 : i32
// CHECK-NEXT:              }) : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %40 = arith.constant 1 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "array_variable_for_testing          "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %41 = arith.constant 2 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "coefficients_for_interpolation      "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %42 = arith.constant 3 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "potential_temperature               "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %43 = arith.constant 4 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "potential_temperature_at_interface  "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %44 = arith.constant 5 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "potential_temperature_increment     "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %45 = arith.constant 6 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "soil_levels                         "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %46 = arith.constant 7 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "surface_air_pressure                "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %47 = arith.constant 8 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "temperature_at_diagnostic_levels    "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %48 = arith.constant 9 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "time_step_for_physics               "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              "ccpp_utils.assign"() ({
// CHECK-NEXT:                "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                  "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  %49 = arith.constant 10 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:              }, {
// CHECK-NEXT:                "ccpp_utils.string_literal_expr"() <{text = "water_vapor_specific_humidity       "}> : () -> ()
// CHECK-NEXT:              }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:            } else {
// CHECK-NEXT:              %50 = "ccpp_utils.value_expr"(%do_input) : (memref<i1>) -> i1
// CHECK-NEXT:              %51 = arith.constant true
// CHECK-NEXT:              %52 = arith.xori %50, %51 : i1
// CHECK-NEXT:              %53 = "ccpp_utils.value_expr"(%do_output) : (memref<i1>) -> i1
// CHECK-NEXT:              %54 = arith.andi %52, %53 : i1
// CHECK-NEXT:              scf.if %54 {
// CHECK-NEXT:                "ccpp_utils.allocate"() <{var_name = "var_list"}> ({
// CHECK-NEXT:                  %55 = arith.constant 10 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %56 = arith.constant 1 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "array_variable_for_testing          "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %57 = arith.constant 2 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "ccpp_error_code                     "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %58 = arith.constant 3 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "ccpp_error_message                  "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %59 = arith.constant 4 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "coefficients_for_interpolation      "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %60 = arith.constant 5 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "potential_temperature               "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %61 = arith.constant 6 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "potential_temperature_at_interface  "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %62 = arith.constant 7 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "soil_levels                         "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %63 = arith.constant 8 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "surface_air_pressure                "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %64 = arith.constant 9 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "temperature_at_diagnostic_levels    "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %65 = arith.constant 10 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "water_vapor_specific_humidity       "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              } else {
// CHECK-NEXT:                "ccpp_utils.allocate"() <{var_name = "var_list"}> ({
// CHECK-NEXT:                  %66 = arith.constant 12 : i32
// CHECK-NEXT:                }) : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %67 = arith.constant 1 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "array_variable_for_testing          "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %68 = arith.constant 2 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "ccpp_error_code                     "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %69 = arith.constant 3 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "ccpp_error_message                  "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %70 = arith.constant 4 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "coefficients_for_interpolation      "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %71 = arith.constant 5 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "potential_temperature               "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %72 = arith.constant 6 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "potential_temperature_at_interface  "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %73 = arith.constant 7 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "potential_temperature_increment     "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %74 = arith.constant 8 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "soil_levels                         "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %75 = arith.constant 9 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "surface_air_pressure                "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %76 = arith.constant 10 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "temperature_at_diagnostic_levels    "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %77 = arith.constant 11 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "time_step_for_physics               "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:                "ccpp_utils.assign"() ({
// CHECK-NEXT:                  "ccpp_utils.index_expr"() ({
// CHECK-NEXT:                    "ccpp_utils.value_expr"(%var_list) : (memref<memref<?xi8>>) -> ()
// CHECK-NEXT:                  }, {
// CHECK-NEXT:                    %78 = arith.constant 12 : i32
// CHECK-NEXT:                  }) : () -> ()
// CHECK-NEXT:                }, {
// CHECK-NEXT:                  "ccpp_utils.string_literal_expr"() <{text = "water_vapor_specific_humidity       "}> : () -> ()
// CHECK-NEXT:                }) {regionSegmentSizes = array<i32: 1, 1>} : () -> ()
// CHECK-NEXT:              }
// CHECK-NEXT:            }
// CHECK-NEXT:          } else {
// CHECK-NEXT:            "ccpp_utils.write_errmsg"(%errmsg, %5) <{prefix = "No suite named ", suffix = " found"}> : (memref<512xi8>, memref<?xi8>) -> ()
// CHECK-NEXT:            %79 = arith.constant 1 : i32
// CHECK-NEXT:            memref.store %79, %errflg[] : memref<i32>
// CHECK-NEXT:          }
// CHECK-NEXT:        }
// CHECK-NEXT:        func.return
// CHECK-NEXT:      }
// CHECK-LABEL:     func.func private @ddt_suite_register() -> (memref<i32>, memref<512xi8>) attributes {module = "ddt_suite_cap"}
// CHECK-LABEL:     func.func private @temp_suite_register(memref<i1>) -> (memref<512xi8>, memref<i32>) attributes {module = "temp_suite_cap"}
// CHECK-LABEL:     func.func private @ddt_suite_initialize() -> (memref<i32>, memref<512xi8>) attributes {module = "ddt_suite_cap"}
// CHECK-LABEL:     func.func private @temp_suite_initialize() -> (memref<i32>, memref<512xi8>) attributes {module = "temp_suite_cap"}
// CHECK-LABEL:     func.func private @ddt_suite_finalize() -> (memref<i32>, memref<512xi8>) attributes {module = "ddt_suite_cap"}
// CHECK-LABEL:     func.func private @temp_suite_finalize() -> (memref<i32>, memref<512xi8>) attributes {module = "temp_suite_cap"}
// CHECK-LABEL:     func.func private @temp_suite_physics2(memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>) -> (memref<512xi8>, memref<i32>) attributes {module = "temp_suite_cap"}
// CHECK-LABEL:     func.func private @temp_suite_physics1(memref<i32>, memref<i32>, memref<!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<?x?x?x?x!ccpp_utils.real_kind<"kind_phys">>) -> (memref<512xi8>, memref<i32>) attributes {module = "temp_suite_cap"}
// CHECK-LABEL:     func.func private @ddt_suite_data_prep(memref<i32>, memref<i32>, memref<?x!ccpp_utils.real_kind<"kind_phys">>) -> (memref<512xi8>, memref<i32>) attributes {module = "ddt_suite_cap"}
// CHECK-LABEL:     func.func private @temp_suite_timestep_init_physics2() -> (memref<i32>, memref<512xi8>) attributes {module = "temp_suite_cap"}
// CHECK-LABEL:     func.func private @temp_suite_timestep_init_physics1(memref<?x!ccpp_utils.real_kind<"kind_phys">>, memref<i32>, memref<?x?x!ccpp_utils.real_kind<"kind_phys">>) -> (memref<512xi8>, memref<i32>) attributes {module = "temp_suite_cap"}
// CHECK-LABEL:     func.func private @ddt_suite_timestep_init_data_prep() -> (memref<i32>, memref<512xi8>) attributes {module = "ddt_suite_cap"}
// CHECK-LABEL:     func.func private @temp_suite_timestep_final_physics2() -> (memref<i32>, memref<512xi8>) attributes {module = "temp_suite_cap"}
// CHECK-LABEL:     func.func private @temp_suite_timestep_final_physics1() -> (memref<i32>, memref<512xi8>) attributes {module = "temp_suite_cap"}
// CHECK-LABEL:     func.func private @ddt_suite_timestep_final_data_prep(memref<i32>) -> (memref<512xi8>, memref<i32>) attributes {module = "ddt_suite_cap"}
// CHECK-LABEL:     func.func private @temp_suite_init_physics2() -> (memref<512xi8>, memref<i32>) attributes {module = "temp_suite_cap"}
// CHECK-LABEL:     func.func private @temp_suite_init_physics1(memref<!ccpp_utils.real_kind<"kind_phys">>, memref<!ccpp_utils.real_kind<"kind_phys">>) -> (memref<512xi8>, memref<i32>) attributes {module = "temp_suite_cap"}
// CHECK-LABEL:     func.func private @ddt_suite_init_data_prep(memref<i32>, memref<?xi32>) -> (memref<512xi8>, memref<i32>, memref<i32>) attributes {module = "ddt_suite_cap"}
// CHECK-LABEL:     func.func private @temp_suite_final_physics2() -> (memref<512xi8>, memref<i32>) attributes {module = "temp_suite_cap"}
// CHECK-LABEL:     func.func private @temp_suite_final_physics1() -> (memref<512xi8>, memref<i32>) attributes {module = "temp_suite_cap"}
// CHECK-LABEL:     func.func private @ddt_suite_final_data_prep(memref<i32>, memref<?xi32>) -> (memref<512xi8>, memref<i32>) attributes {module = "ddt_suite_cap"}
// CHECK:         }
// CHECK-LABEL:   builtin.module @ccpp_kinds {
// CHECK:           "ccpp_utils.kind_def"() <{kind_name = "kind_phys", kind_value = "REAL64", kind_module = "iso_fortran_env"}> : () -> ()
// CHECK-NEXT:      "ccpp_utils.kind_def"() <{kind_name = "kind_temp", kind_value = "temp_r8", kind_module = "temp_kinds"}> : () -> ()
// CHECK-NEXT:    }
// CHECK-NEXT:  }
