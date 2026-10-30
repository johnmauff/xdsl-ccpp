"""C++ wrapper expressions are ops (cpp-text-in-ir): the address of a
variable, the null pointer, and constructor defaults/initializers are
built from expression ops, and the C++ printer spells them.
"""

from io import StringIO

import pytest
from xdsl.dialects import arith
from xdsl.dialects.builtin import DYNAMIC_INDEX, IntegerAttr, MemRefType, f64, i32

from xdsl_ccpp.backend.print_cpp_header import _print_cpp_constructor, _print_cpp_op, expr_to_cpp_str
from xdsl_ccpp.dialects.ccpp_utils import (
    AddressOfExprOp,
    CppCallStatementOp,
    CppConstructorOp,
    CppFieldDeclOp,
    NullPointerExprOp,
    VarRefExprOp,
)


def _printed(op) -> str:
    """op printed as a statement in a function body."""
    out = StringIO()
    _print_cpp_op(op, out, "    ")
    return out.getvalue()


def test_call_passes_the_error_flag_by_address():
    call = CppCallStatementOp("run", call_arg_ops=[
        VarRefExprOp("errmsg"), AddressOfExprOp(VarRefExprOp("errflg")),
    ])
    assert _printed(call) == "    run(errmsg, &errflg);\n"


def test_pointer_field_defaults_to_nullptr():
    field = CppFieldDeclOp("t", MemRefType(f64, [DYNAMIC_INDEX]), type_width=16,
                           init_expr_op=NullPointerExprOp())
    assert _printed(field).split() == ["double*", "t", "=", "nullptr;"]
    assert expr_to_cpp_str(NullPointerExprOp()) == "nullptr"


def test_constructor_defaults_and_initializers_are_expressions():
    zero = arith.ConstantOp(IntegerAttr.from_int_and_width(0, 32))
    ctor = CppConstructorOp(
        ["ncol"], [i32], [zero], ["ncol"], [VarRefExprOp("ncol")], [],
    )
    out = StringIO()
    _print_cpp_constructor("State", ctor, out)
    assert out.getvalue() == "    State(int ncol = 0)\n        : ncol(ncol) {}\n"


@pytest.mark.parametrize("name", ["&errflg", "a.b", "x(1)", "0"])
def test_var_ref_names_must_be_identifiers(name):
    with pytest.raises(ValueError, match="not an identifier"):
        VarRefExprOp(name)


def test_statements_without_text():
    """Locals, returns, one-line ifs, method calls and assignments -- the
    statements the C++ wrapper's function bodies are built from."""
    from xdsl.dialects.builtin import IndexType, i8

    from xdsl_ccpp.dialects.ccpp_utils import (
        AssignOp,
        CallExprOp,
        CastExprOp,
        ConditionalExprOp,
        DdtMethodCallOp,
        LocalVarOp,
        MethodCallExprOp,
        OwnedArrayType,
        ReturnStmtOp,
        StringLiteralExprOp,
        StructLiteralExprOp,
    )
    from xdsl_ccpp.transforms.util.cap_shared import _scf_if

    def zero():
        return arith.ConstantOp(IntegerAttr.from_int_and_width(0, 32))

    aligned = {"type_width": 6, "name_width": 16}
    assert _printed(LocalVarOp("errmsg", MemRefType(i8, [513]), zero_init=True, **aligned)) == (
        "    char   errmsg[513]      = {};\n"
    )
    assert _printed(LocalVarOp("errflg", i32, init_op=zero(), **aligned)) == (
        "    int    errflg           = 0;\n"
    )
    assert _printed(LocalVarOp(
        "v", OwnedArrayType(f64), size_op=CastExprOp(VarRefExprOp("n", i32), IndexType()),
    )) == "    std::vector<double> v(static_cast<std::size_t>(n));\n"
    assert _printed(ReturnStmtOp(value_op=StructLiteralExprOp([
        VarRefExprOp("errflg"),
        ConditionalExprOp(VarRefExprOp("errflg"), VarRefExprOp("errmsg"), StringLiteralExprOp("")),
    ]))) == '    return {errflg, errflg ? errmsg : ""};\n'
    assert _printed(ReturnStmtOp(value_op=StructLiteralExprOp([zero(), StringLiteralExprOp("")]))) == (
        '    return {0, ""};\n'
    )
    if_ops = _scf_if(
        arith.CmpiOp(VarRefExprOp("n", i32), zero(), "sgt"),
        [CppCallStatementOp("get", call_arg_ops=[MethodCallExprOp(VarRefExprOp("v"), "data")])],
    )
    assert "".join(_printed(o) for o in if_ops) == "    if (n > 0) get(v.data());\n"
    size = arith.MuliOp(CastExprOp(VarRefExprOp("ncol", i32), IndexType()),
                        VarRefExprOp("nz", IndexType()))
    assert _printed(DdtMethodCallOp(
        obj_expr_op=VarRefExprOp("_q"), method="assign", arg_ops=[size, zero()],
    )) == "    _q.assign(static_cast<std::size_t>(ncol) * nz, 0);\n"
    assert _printed(AssignOp(
        lhs_op=VarRefExprOp("q"), rhs_op=MethodCallExprOp(VarRefExprOp("_q"), "data"),
    )) == "    q = _q.data();\n"
    assert _printed(ReturnStmtOp(value_op=CallExprOp("count"))) == "    return count();\n"
