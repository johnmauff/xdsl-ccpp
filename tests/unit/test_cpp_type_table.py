"""Unit tests for the shared `c_numeric_type` decision table
(`cpp_type_table.py`) and the two preserved per-caller quirks that sit on
top of it in `_chost_arg_type`/`_c_param_type` (BACKLOG.md's
`cpp-type-table-unify`). The table returns MLIR types; the assertions
spell them with `print_cpp_header.cpp_type_name`.

No FileCheck golden exercises this table directly in isolation -- real
suites only reach it through whichever of the two real/int argument
shapes a given scheme happens to declare -- so this is the one place that
pins down the table's own rules, plus the two call sites' adapter-level
overrides, independent of any particular example suite.
"""

from xdsl_ccpp.backend.print_cpp_header import cpp_type_name
from xdsl_ccpp.transforms.cpp_interop import ChostArgInfo, _chost_arg_type
from xdsl_ccpp.util.cpp_type_table import c_numeric_type


def cpp_numeric_type(**kwargs) -> str:
    return cpp_type_name(c_numeric_type(**kwargs))


def _chost_cpp_type(ai) -> str:
    return cpp_type_name(_chost_arg_type(ai))


class TestCppNumericType:
    def test_scalar_in_passes_by_value(self):
        assert cpp_numeric_type(kind="real", width=64, rank=0, intent="in") == "double"
        assert cpp_numeric_type(kind="real", width=32, rank=0, intent="in") == "float"
        assert cpp_numeric_type(kind="int", width=64, rank=0, intent="in") == "int"

    def test_scalar_non_in_passes_by_pointer_no_const(self):
        assert cpp_numeric_type(kind="real", width=64, rank=0, intent="out") == "double*"
        assert cpp_numeric_type(kind="real", width=64, rank=0, intent="inout") == "double*"
        assert cpp_numeric_type(kind="int", width=64, rank=0, intent="out") == "int*"

    def test_array_non_in_passes_by_pointer_no_const(self):
        assert cpp_numeric_type(kind="real", width=32, rank=1, intent="out") == "float*"
        assert cpp_numeric_type(kind="real", width=32, rank=2, intent="inout") == "float*"

    def test_array_in_const_policy_is_explicit_per_caller(self):
        """The one real behavioral divergence between the two existing
        functions: an intent(in) ARRAY gets a const pointer under
        `_chost_arg_type`'s own settled convention (const_in_arrays=True,
        the default) but not under `_c_param_type`'s (const_in_arrays=False)."""
        assert cpp_numeric_type(
            kind="real", width=64, rank=1, intent="in",
        ) == "const double*"
        assert cpp_numeric_type(
            kind="real", width=64, rank=1, intent="in", const_in_arrays=False,
        ) == "double*"


class TestChostCppTypePreservedQuirks:
    """`_chost_arg_type` forces specific (rank, intent) pairs into the
    shared table rather than ever passing the arg's own raw values for
    int, and only for real at rank 0 -- both are pre-existing,
    deliberately-preserved conventions of this call site, not something
    this unification pass changed."""

    def test_real_scalar_always_by_value_regardless_of_declared_intent(self):
        """A rank-0 real chost arg renders as a bare value type even when
        its own declared intent is "out"/"inout" -- the existing
        Fortran-generator convention this call site has always encoded."""
        ai = ChostArgInfo(is_real=True, rank=0, intent="out", real_width=64)
        assert _chost_cpp_type(ai) == "double"
        ai_f32 = ChostArgInfo(is_real=True, rank=0, intent="inout", real_width=32)
        assert _chost_cpp_type(ai_f32) == "float"

    def test_real_array_respects_its_own_declared_intent(self):
        ai_in = ChostArgInfo(is_real=True, rank=1, intent="in", real_width=64)
        assert _chost_cpp_type(ai_in) == "const double*"
        ai_out = ChostArgInfo(is_real=True, rank=1, intent="out", real_width=64)
        assert _chost_cpp_type(ai_out) == "double*"

    def test_int_always_renders_plain_int_even_if_rank_were_nonzero(self):
        """Known pre-existing, unexercised gap: an int DDT-member array
        (rank>0) would still render as plain "int", not "int*" -- not
        fixed by this pass, just confirmed preserved."""
        ai_scalar = ChostArgInfo(is_int=True, is_errflg=False, rank=0, intent="in")
        assert _chost_cpp_type(ai_scalar) == "int"
        ai_array = ChostArgInfo(is_int=True, is_errflg=False, rank=2, intent="out")
        assert _chost_cpp_type(ai_array) == "int"


class TestCppTypeName:
    """`cpp_type_name` spells the C-interop types the C++ host cap uses."""

    def test_structs_containers_and_read_only_access(self):
        from xdsl.dialects.builtin import DYNAMIC_INDEX, MemRefType, f64, i1, i8, i32

        from xdsl_ccpp.dialects.ccpp_utils import (
            DerivedType,
            OwnedArrayType,
            OwnedStringType,
            ReadOnlyType,
        )

        info = DerivedType("CcppConstituentInfo")
        assert cpp_type_name(ReadOnlyType(DerivedType("State"))) == "const State&"
        assert cpp_type_name(ReadOnlyType(MemRefType(i8, [DYNAMIC_INDEX]))) == "const char*"
        assert cpp_type_name(MemRefType(i32, [])) == "int*"
        assert cpp_type_name(MemRefType(info, [DYNAMIC_INDEX]), c_decl=True) == (
            "struct CcppConstituentInfo*"
        )
        assert cpp_type_name(OwnedArrayType(info)) == "std::vector<CcppConstituentInfo>"
        assert cpp_type_name(OwnedArrayType(f64)) == "std::vector<double>"
        assert cpp_type_name(OwnedStringType()) == "std::string"
        assert cpp_type_name(i1) == "bool"

    def test_static_shape_field_is_an_inline_array(self):
        from io import StringIO

        from xdsl.dialects.builtin import MemRefType, i8

        from xdsl_ccpp.backend.print_cpp_header import _print_cpp_op
        from xdsl_ccpp.dialects.ccpp_utils import CppFieldDeclOp

        out = StringIO()
        _print_cpp_op(CppFieldDeclOp("std_name", MemRefType(i8, [129])), out)
        assert out.getvalue().split() == ["char", "std_name[129];"]
