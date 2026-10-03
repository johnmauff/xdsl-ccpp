"""lang-neutral-expr-ir Stage 4 early checkpoint.

Builds small IR trees directly from real arith/math ops plus the new
ccpp_utils expression ops (Stage 1b), and asserts both print_ftn.py's
print_expr (via _render_expr) and print_cpp_header.py's expr_to_cpp_str
against literal expected strings -- the primary verification artifact for
this item's whole claimed value: one shared, language-neutral IR tree,
two correct renderings, with real xDSL arith/math ops doing the
arithmetic/logical/comparison work rather than reinvented custom ops.

Four cases, per the plan (lang-neutral-expr-ir Stage 4, "early
checkpoint"):
  1. The ``.or.``/``||`` + ``%``/``.``-access worked example, from one
     shared constructed tree.
  2. The ``(a .or. b) .and. c`` parenthesization case.
  3. The UnitConvertOp-style ``source``-referencing ``arith.AddfOp``
     pattern.
  4. A CallExprOp with one KeywordArgExprOp -- asserts the Fortran
     rendering and asserts the C++ path raises for non-empty kwargs.
"""

from io import StringIO

from xdsl.dialects import arith
from xdsl.dialects.builtin import FloatAttr, f64, i1, i32

from xdsl_ccpp.backend.print_cpp_header import expr_to_cpp_str
from xdsl_ccpp.backend.print_ftn import ftnPrintContext
from xdsl_ccpp.dialects.ccpp_utils import (
    CallExprOp,
    KeywordArgExprOp,
    MemberAccessExprOp,
    StringLiteralExprOp,
    UnitConvertOp,
    VarRefExprOp,
)


def _ftn_render(op) -> str:
    ctx = ftnPrintContext(output=StringIO())
    ctx.register_binops()
    return ctx._render_expr(op)


class TestOrMemberAccessWorkedExample:
    """state%errflg == 0 .or. state%active (Fortran) /
    state.errflg == 0 || state.active (C++), from one shared tree."""

    def _build_tree(self):
        errflg_ref = MemberAccessExprOp(VarRefExprOp("state"), "errflg", result_type=i32)
        zero = arith.ConstantOp.from_int_and_width(0, 32)
        cmp = arith.CmpiOp(errflg_ref, zero, "eq")
        active_ref = MemberAccessExprOp(VarRefExprOp("state"), "active", result_type=i1)
        return arith.OrIOp(cmp, active_ref)

    def test_fortran_rendering(self):
        assert _ftn_render(self._build_tree()) == "state%errflg .eq. 0 .or. state%active"

    def test_cpp_rendering(self):
        assert expr_to_cpp_str(self._build_tree()) == "state.errflg == 0 || state.active"


class TestParenthesizationContrast:
    """(a .or. b) .and. c -- proves parens are inserted when a looser-
    precedence child sits under a tighter-precedence parent."""

    def _build_tree(self):
        a = arith.ConstantOp.from_int_and_width(1, 1)
        b = arith.ConstantOp.from_int_and_width(1, 1)
        c = arith.ConstantOp.from_int_and_width(1, 1)
        return arith.AndIOp(arith.OrIOp(a, b), c)

    def test_fortran_rendering(self):
        assert _ftn_render(self._build_tree()) == "(.true. .or. .true.) .and. .true."

    def test_cpp_rendering(self):
        assert expr_to_cpp_str(self._build_tree()) == "(true || true) && true"


class TestUnitConvertRegionShape:
    """UnitConvertOp's structured alternative: a real arith.AddfOp whose
    lhs operand is the same SSA value as UnitConvertOp's own source."""

    def test_conversion_region_references_source(self):
        source = arith.ConstantOp(FloatAttr(300.0, f64))
        offset = arith.ConstantOp(FloatAttr(273.15, f64))
        conversion = arith.AddfOp(source.result, offset.result)
        uc = UnitConvertOp(source, conversion_op=conversion, result_type=f64)

        (conv_op,) = uc.conversion.block.ops
        assert conv_op is conversion
        assert conversion.lhs.owner is source

    def test_legacy_and_structured_forms_are_mutually_exclusive(self):
        source = arith.ConstantOp(FloatAttr(300.0, f64))
        offset = arith.ConstantOp(FloatAttr(273.15, f64))
        conversion = arith.AddfOp(source.result, offset.result)
        try:
            UnitConvertOp(source, "+ 273.15", f64, conversion_op=conversion)
        except ValueError:
            pass
        else:
            raise AssertionError("expected ValueError for both to_scheme_expr and conversion_op")


class TestCallExprWithKeywordArg:
    """A CallExprOp with one positional arg and one KeywordArgExprOp:
    Fortran renders name=value syntax; C++ has no such syntax and raises."""

    def _build_tree(self):
        callee_vr = VarRefExprOp("ncol")
        kw = KeywordArgExprOp("advected", StringLiteralExprOp(".true."))
        return CallExprOp("set_opts", [callee_vr], [kw])

    def test_fortran_rendering(self):
        assert _ftn_render(self._build_tree()) == "set_opts(ncol, advected='.true.')"

    def test_cpp_raises_on_nonempty_kwargs(self):
        try:
            expr_to_cpp_str(self._build_tree())
        except AssertionError:
            pass
        else:
            raise AssertionError("expected expr_to_cpp_str to raise for non-empty kwargs")
