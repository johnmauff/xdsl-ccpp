// Test that after generate-suite-cap, the func.FuncOp declaration for a C++
// scheme carries language = "c++", while the Fortran scheme declaration does not.
//
// RUN: python3 tests/filecheck/examples/language_suite.py | python3 -m xdsl_ccpp.tools.ccpp_opt -p generate-meta-cap,generate-meta-kinds,generate-arg-ownership,generate-suite-cap | python3 -m filecheck %s

// Fortran scheme: module annotation present, no language attribute.
// CHECK:      func.func private @tiny_fortran_scheme_run
// CHECK-SAME: attributes {module = "tiny_fortran_scheme"}
// CHECK-NOT:  language

// C++ scheme: module, language, arg_names, and arg_intents all stamped.
// CHECK:      func.func private @tiny_cxx_scheme_run
// CHECK-SAME: module = "tiny_cxx_scheme"
// CHECK-SAME: language = "c++"
// CHECK-SAME: arg_names = ["ncol", "temp", "errmsg", "errflg"]
// CHECK-SAME: arg_intents = ["in", "inout", "out", "out"]
