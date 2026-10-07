"""Unit tests for the shared `cpp_numeric_type` decision table
(`cpp_type_table.py`) and the two preserved per-caller quirks that sit on
top of it in `_chost_cpp_type`/`_cpp_type` (BACKLOG.md's
`cpp-type-table-unify`).

No FileCheck golden exercises this table directly in isolation -- real
suites only reach it through whichever of the two real/int argument
shapes a given scheme happens to declare -- so this is the one place that
pins down the table's own rules, plus the two call sites' adapter-level
overrides, independent of any particular example suite.
"""

from xdsl_ccpp.transforms.cpp_interop import ChostArgInfo, _chost_cpp_type
from xdsl_ccpp.util.cpp_type_table import cpp_numeric_type


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
        `_chost_cpp_type`'s own settled convention (const_in_arrays=True,
        the default) but not under `_cpp_type`'s (const_in_arrays=False)."""
        assert cpp_numeric_type(
            kind="real", width=64, rank=1, intent="in",
        ) == "const double*"
        assert cpp_numeric_type(
            kind="real", width=64, rank=1, intent="in", const_in_arrays=False,
        ) == "double*"


class TestChostCppTypePreservedQuirks:
    """`_chost_cpp_type` forces specific (rank, intent) pairs into the
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
