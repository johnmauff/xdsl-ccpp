"""Generated API routines are func.FuncOps built by cap_shared.fixed_interface_fn
(fortran-decls-as-text): declarations come from types and attributes, and the
printer spells them -- function results, pointer locals, BLOCK-construct
locals, and array-constructor initial values.
"""

from io import StringIO

from xdsl.dialects import memref
from xdsl.dialects.builtin import DYNAMIC_INDEX, MemRefType, i8, i32

from xdsl_ccpp.backend.print_ftn import ftnPrintContext
from xdsl_ccpp.dialects.ccpp_utils import (
    ArrayConstructorExprOp,
    PointerAssignOp,
    ScopedBlockOp,
    StringLiteralExprOp,
    VarRefExprOp,
)
from xdsl_ccpp.transforms.util.cap_shared import fixed_interface_fn
from xdsl_ccpp.util.ccpp_conventions import mark_pointer_local, name_local


def _printed(op) -> str:
    out = StringIO()
    ftnPrintContext(output=out).print_op(op)
    return out.getvalue()


def _local(name, elem, shape=(), pointer=False):
    alloca = memref.AllocaOp.get(elem, shape=list(shape))
    (mark_pointer_local if pointer else name_local)(alloca, name)
    return alloca


def test_function_result_and_declared_interface():
    fn = fixed_interface_fn(
        "get_names",
        [("instance", MemRefType(i32, []), "in", ()),
         ("names", MemRefType(i8, [DYNAMIC_INDEX]), "in", ("target",))],
        [PointerAssignOp("ptr", rhs_expr_op=VarRefExprOp("lc_names"))],
        result=_local("ptr", i32, [0], pointer=True),
        uses={"some_mod": ["a", "b"]},
    )
    text = _printed(fn)
    assert "function get_names(instance, names) result(ptr)" in text
    assert "use some_mod, only: a, b" in text
    assert "integer, intent(in) :: instance" in text
    assert "character(len=*), target, intent(in) :: names" in text
    assert "integer, pointer :: ptr(:)" in text
    assert "end function get_names" in text


def test_block_locals_are_declared_in_the_block():
    block = ScopedBlockOp(
        [_local("lc_idx", i32), _local("lc_msg", i8, [512])],
        [PointerAssignOp("p", rhs_expr_op=VarRefExprOp("q"))],
    )
    fn = fixed_interface_fn("f", [], [block], locals_=[_local("outer", i32)])
    lines = [line.strip() for line in _printed(fn).splitlines()]
    block_at = lines.index("block")
    assert lines.index("integer :: outer") < block_at
    assert lines[block_at + 1:block_at + 3] == [
        "integer :: lc_idx", "character(len=512) :: lc_msg",
    ]
    assert lines.count("integer :: lc_idx") == 1  # not also a function local


def test_array_constructor_puts_each_element_on_its_own_line():
    names = ["cloud_liquid_dry_mixing_ratio", "cloud_ice_dry_mixing_ratio",
             "rain_mixing_ratio_wrt_moist_air_and_condensed_water"]
    ctx = ftnPrintContext(output=StringIO())
    text = ctx._render_expr(ArrayConstructorExprOp(
        [StringLiteralExprOp(n) for n in names], elem_type=MemRefType(i8, [51]),
    ))
    assert text.startswith("[ character(len=51) :: 'cloud_liquid_dry_mixing_ratio', &\n")
    # Every line stays well inside Fortran's 132-column limit.
    assert all(len(line) < 100 for line in text.splitlines())
