// Test that language = "c++" on a scheme descriptor is parsed and emitted
// as an IR attribute on the TablePropertiesOp, while a Fortran scheme
// (the default) carries no language attribute.
//
// RUN: python3 tests/filecheck/examples/language_suite.py | python3 -m filecheck %s

// The Fortran scheme table has no language attribute (Fortran is the default).
// CHECK:      "ccpp.table_properties"() <{name = "tiny_fortran_scheme"
// CHECK-NOT:  language

// The C++ scheme table carries language = "c++".
// CHECK:      "ccpp.table_properties"() <{name = "tiny_cxx_scheme"
// CHECK:      }) {language = "c++"} : () -> ()
