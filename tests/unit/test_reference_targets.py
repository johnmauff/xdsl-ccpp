"""Ops that name a variable take a plain identifier or a reference expression
op (fortran-exprs-as-text): a reference such as lc_instances(instance)%x is
never text, and a name that is not an identifier is rejected.
"""

from io import StringIO

import pytest

from xdsl_ccpp.backend.print_ftn import ftnPrintContext
from xdsl_ccpp.dialects.ccpp_utils import (
    AllocateOp,
    IndexExprOp,
    MemberAccessExprOp,
    NullifyPointerOp,
    PointerAssignOp,
    SafeDeallocOp,
    SliceExprOp,
    VarRefExprOp,
    ZeroFillOp,
)


def _instance_member(name: str):
    """lc_instances(instance)%<name>, as ops."""
    return MemberAccessExprOp(
        IndexExprOp(VarRefExprOp("lc_instances"), [VarRefExprOp("instance")]), name,
    )


def _printed(op) -> str:
    out = StringIO()
    ftnPrintContext(output=out).print_op(op)
    return out.getvalue().strip()


def test_reference_targets_print_as_references():
    assert _printed(SafeDeallocOp(target_op=_instance_member("x"))) == (
        "if (allocated(lc_instances(instance)%x)) deallocate(lc_instances(instance)%x)"
    )
    assert _printed(NullifyPointerOp(target_op=_instance_member("p"), if_associated=True)) == (
        "if (associated(lc_instances(instance)%p)) nullify(lc_instances(instance)%p)"
    )
    assert _printed(ZeroFillOp(target_op=_instance_member("t"))) == (
        "lc_instances(instance)%t = 0.0_kind_phys"
    )
    assert _printed(AllocateOp(target_op=_instance_member("a"), dim_ops=[VarRefExprOp("n")])) == (
        "allocate(lc_instances(instance)%a(n))"
    )
    # A slice of a 3-D array: what PointerSliceAssignOp used to print.
    assert _printed(PointerAssignOp(
        target_op=_instance_member("view"),
        rhs_expr_op=IndexExprOp(_instance_member("tend"), [
            SliceExprOp(), SliceExprOp(), VarRefExprOp("idx"),
        ]),
    )) == "lc_instances(instance)%view => lc_instances(instance)%tend(:, :, idx)"


def test_identifier_names_still_work():
    assert _printed(SafeDeallocOp("lc_x")) == "if (allocated(lc_x)) deallocate(lc_x)"


@pytest.mark.parametrize("make", [
    lambda name: SafeDeallocOp(name),
    lambda name: NullifyPointerOp(name),
    lambda name: ZeroFillOp(name),
    lambda name: AllocateOp(name),
    lambda name: PointerAssignOp(name, rhs_expr_op=VarRefExprOp("q")),
])
def test_text_references_are_rejected(make):
    with pytest.raises(ValueError, match="not an identifier"):
        make("lc_instances(instance)%x")


def test_cap_var_refs_compose_instance_section_and_count():
    """cap_var_map references (cap_shared.CapVarRef) are built as ops: the
    count of a multi-instance array is size() of its component, not a
    component named size(...)."""
    from xdsl.dialects.builtin import i32

    from xdsl_ccpp.transforms.util.cap_shared import CapVarRef, framework_cap_var_ref

    ctx = ftnPrintContext(output=StringIO())
    count = framework_cap_var_ref("number_of_ccpp_constituents", "instance")
    assert ctx._render_expr(count.expr_op()) == "size(lc_instances(instance)%lc_all_constituents)"
    assert ctx._render_expr(CapVarRef("lc_qv").expr_op(section_rank=2)) == "lc_qv(:, :)"
    ref = CapVarRef("lc_qv").ref_op(i32)
    assert ref.var_name.data == "lc_qv"   # a plain variable stays an identifier
