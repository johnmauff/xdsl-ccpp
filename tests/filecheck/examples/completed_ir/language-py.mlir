// Test that after generate-suite-cap, the func.FuncOp declaration for a C++
// scheme carries language = "c++", while the Fortran scheme declaration does not.
//
// RUN: python3 tests/filecheck/examples/language_suite.py | python3 -m xdsl_ccpp.tools.ccpp_opt -p generate-meta-cap,generate-meta-kinds,generate-suite-cap | python3 -m filecheck %s

// Fortran scheme: module annotation present, no language attribute.
// CHECK:      func.func private @tiny_fortran_scheme_run
// CHECK-SAME: attributes {module = "tiny_fortran_scheme"}
// CHECK-NOT:  language

// C++ scheme: both module and language attributes present.
// CHECK:      func.func private @tiny_cxx_scheme_run
// CHECK-SAME: attributes {module = "tiny_cxx_scheme", language = "c++"}
