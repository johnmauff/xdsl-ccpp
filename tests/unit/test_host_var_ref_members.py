"""A DDT member reference is structure, not text (active-condition-ir):
HostVarRefOp carries a member path of identifiers and subscript ops, the
printer spells the reference and merges a section into the subscripts, and
the identity key is the same from metadata and from the op."""

from io import StringIO

import pytest
from xdsl.dialects import arith
from xdsl.dialects.builtin import MemRefType, f64, i32
from xdsl.ir import Block

from xdsl_ccpp.backend.print_ftn import ftnPrintContext
from xdsl_ccpp.dialects.ccpp_utils import HostVarRefOp, RankReducingSliceOp, SliceExprOp
from xdsl_ccpp.frontend.meta_expr import FullSlice
from xdsl_ccpp.transforms.util.cap_shared import (
    MemberRef,
    host_var_ref_key,
    member_ref_of,
    member_subscript_ops,
    resolve_member,
)

_ARRAY2 = MemRefType(f64, [-1, -1])
_HOST_VAR_MAP = {"index_of_water_vapor_specific_humidity": ("index_qv", "host_mod")}


def _q_ref():
    member, use_vars = resolve_member(
        ("state",), "q(:,:,index_of_water_vapor_specific_humidity)", _HOST_VAR_MAP,
    )
    assert use_vars == [("index_qv", "host_mod")]
    return HostVarRefOp(
        "phys_state", "host_mod", _ARRAY2, member_path=member.path,
        subscript_ops=member_subscript_ops(member),
    )


def _registered(*ops) -> str:
    """The text the printer registers for the last op's result."""
    ctx = ftnPrintContext(output=StringIO())
    ctx.register_binops()
    for op in ops:
        ctx.print_op(op)
    return ctx.variables[ops[-1].results[0]]


def test_member_path_and_subscripts_print():
    assert _registered(_q_ref()) == "phys_state%state%q(:, :, index_qv)"


def test_plain_member_and_instance_index():
    ref = HostVarRefOp("inst", "m", f64, member_path=["rad", "temp"], index_expr="i")
    assert _registered(ref) == "inst(i)%rad%temp"


def test_section_merges_into_member_subscripts():
    block = Block(arg_types=[i32, i32, i32])
    for arg, name in zip(block.args, ("col_start", "col_end", "pver")):
        arg.name_hint = name
    one = arith.ConstantOp.from_int_and_width(1, 32)
    ref = _q_ref()
    section = RankReducingSliceOp(
        ref.res, dim_pattern="RR",
        range_lowers=[block.args[0], one.result], range_uppers=[block.args[1], block.args[2]],
        scalar_indices=[],
    )
    assert _registered(one, ref, section) == (
        "phys_state%state%q(col_start:col_end, 1:pver, index_qv)"
    )


def test_identity_key_round_trips():
    ref = _q_ref()
    assert member_ref_of(ref) == MemberRef(("state", "q"), (FullSlice(), FullSlice(), "index_qv"))
    assert host_var_ref_key(ref) == "phys_state%state%q(:, :, index_qv)"


@pytest.mark.parametrize("make", [
    lambda: HostVarRefOp("s", "m", f64, member_path="q(:, :, index_qv)"),
    lambda: HostVarRefOp("s", "m", f64, member_path="rad%temp"),
    lambda: HostVarRefOp("s", "m", f64, subscript_ops=[SliceExprOp()]),
    lambda: HostVarRefOp("s", "m", f64, member_path="x", index_expr="i + 1"),
])
def test_text_members_are_rejected(make):
    with pytest.raises(ValueError, match="identifier|needs a member_path"):
        make()
