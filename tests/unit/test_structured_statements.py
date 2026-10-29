"""Statement ops take their expressions as ops, not Fortran text
(fortran-exprs-as-text): loop bounds, write items, call arguments, method
receivers and assignment sides are composed from expression ops, and the
printer spells them.
"""

from io import StringIO

import pytest
from xdsl.dialects import arith
from xdsl.dialects.builtin import IntegerAttr, i32

from xdsl_ccpp.backend.print_ftn import ftnPrintContext
from xdsl_ccpp.dialects.ccpp_utils import (
    AssignOp,
    CallExprOp,
    CallStatementOp,
    DdtComponentDeclOp,
    DdtMethodCallOp,
    DoLoopOp,
    IndexExprOp,
    KeywordArgExprOp,
    MemberAccessExprOp,
    MetadataLiteralExprOp,
    MethodCallExprOp,
    ModuleVarOp,
    SliceExprOp,
    StringLiteralExprOp,
    VarRefExprOp,
    WriteStmtOp,
)


def _printed(op) -> str:
    out = StringIO()
    ctx = ftnPrintContext(output=out)
    ctx.register_binops()
    ctx.print_op(op)
    return out.getvalue()


def _lines(op) -> list[str]:
    return [line.strip() for line in _printed(op).splitlines()]


def _const(value: int):
    return arith.ConstantOp(IntegerAttr.from_int_and_width(value, 32))


def test_do_loop_bound_is_an_expression():
    src = VarRefExprOp("src")
    loop = DoLoopOp("j", CallExprOp("size", [VarRefExprOp("x")]), [AssignOp(
        lhs_op=IndexExprOp(VarRefExprOp("dst"), [VarRefExprOp("j")]),
        rhs_op=IndexExprOp(src, [SliceExprOp(VarRefExprOp("j"), VarRefExprOp("j"))]),
    )])
    assert _lines(loop) == ["do j = 1, size(x)", "dst(j) = src(j:j)", "end do"]


def test_assign_composes_arith_and_intrinsics():
    n = VarRefExprOp("n", result_type=i32)
    size_n = CallExprOp("int", [CallExprOp("size", [VarRefExprOp("q")]), VarRefExprOp("c_int")],
                        result_type=i32)
    assert _lines(AssignOp(lhs_op=VarRefExprOp("n"), rhs_op=arith.AddiOp(n, size_n))) == [
        "n = n + int(size(q), c_int)",
    ]
    assert _lines(AssignOp(lhs_op=VarRefExprOp("s"), rhs_op=StringLiteralExprOp(""))) == [
        "s = ''",
    ]
    assert _lines(AssignOp(lhs_op=VarRefExprOp("k"), rhs_op=_const(0))) == ["k = 0"]


def test_write_statement_items_are_expressions():
    write = WriteStmtOp(VarRefExprOp("errmsg"), [
        StringLiteralExprOp("constituent "),
        CallExprOp("trim", [VarRefExprOp("std_name")]),
        StringLiteralExprOp(" not found"),
    ])
    assert _lines(write) == [
        "write(errmsg, '(3a)') 'constituent ', trim(std_name), ' not found'",
    ]


def test_method_calls_take_a_receiver_expression():
    obj = MemberAccessExprOp(
        IndexExprOp(VarRefExprOp("lc_instances"), [VarRefExprOp("instance")]), "obj",
    )
    call = DdtMethodCallOp(
        obj_expr_op=obj, method="instantiate",
        arg_ops=[VarRefExprOp("errcode")],
        kwarg_ops=[KeywordArgExprOp("default_value", MetadataLiteralExprOp("1.0e-12_kind_phys"))],
    )
    assert _lines(call) == [
        "call lc_instances(instance)%obj%instantiate(errcode, "
        "default_value=1.0e-12_kind_phys)",
    ]
    ptr = AssignOp(lhs_op=VarRefExprOp("p"),
                   rhs_op=MethodCallExprOp(VarRefExprOp("obj"), "field_data_ptr"))
    assert _lines(ptr) == ["p = obj%field_data_ptr()"]


def test_call_statement_arguments_are_expressions():
    call = CallStatementOp("run", arg_ops=[
        CallExprOp("real", [VarRefExprOp("dt"), VarRefExprOp("kind_phys")]),
        VarRefExprOp("errmsg_f"),
    ])
    assert _lines(call) == ["call run(real(dt, kind_phys), errmsg_f)"]


@pytest.mark.parametrize("make", [
    lambda: MemberAccessExprOp(VarRefExprOp("x"), "a(1)"),
    lambda: MethodCallExprOp(VarRefExprOp("x"), "f()"),
    lambda: DdtMethodCallOp(obj_expr_op=VarRefExprOp("x"), method="a%b"),
])
def test_member_and_method_names_must_be_identifiers(make):
    with pytest.raises(ValueError, match="not an identifier"):
        make()


@pytest.mark.parametrize("make", [
    lambda: AssignOp("x", "1"),
    lambda: CallStatementOp("run", ["a + b"]),
    lambda: DdtMethodCallOp("obj(i)", "m"),
])
def test_text_expression_forms_are_gone(make):
    with pytest.raises(TypeError):
        make()


@pytest.mark.parametrize("operation, factor", [
    ("div", "2.0"),          # not a supported operation
    ("mul", "* 0.01"),       # an expression, not a literal
    ("add", "273.15_kind_phys"),
    ("mul", None),
])
def test_unit_conversion_is_operation_and_literal(operation, factor):
    from xdsl.dialects.builtin import f64

    from xdsl_ccpp.dialects.ccpp_utils import UnitConvertOp

    source = arith.ConstantOp(IntegerAttr.from_int_and_width(1, 32))
    with pytest.raises(ValueError):
        UnitConvertOp(source, f64, operation, factor)


def test_declaration_types_are_structured():
    """A character's length is char_len and a kind is an identifier or an
    integer; the printer spells the Fortran type."""
    from xdsl_ccpp.backend.print_ftn import _decl_fortran_type

    assert _decl_fortran_type(ModuleVarOp("s", "character", char_len=64)) == "character(len=64)"
    assert _decl_fortran_type(DdtComponentDeclOp("c", "character", kind="c_char")) == (
        "character(kind=c_char)"
    )
    assert _decl_fortran_type(ModuleVarOp("x", "real", kind="8", is_target=True)) == (
        "real(kind=8), target"
    )


@pytest.mark.parametrize("make", [
    lambda: ModuleVarOp("s", "character", kind="len=64"),
    lambda: ModuleVarOp("s", "character", kind="64"),
    lambda: DdtComponentDeclOp("c", "character", kind="kind=c_char"),
    lambda: ModuleVarOp("s", "character", char_len=0),
])
def test_declaration_type_text_is_rejected(make):
    with pytest.raises(ValueError):
        make()
