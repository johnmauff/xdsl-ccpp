"""emit_coalesced_updates: a run of host calls is pulled (`update self`)
before it, and pushed back (`update device`) after it only if some call in
the run may write the variable (gpu-sync-intent-aware)."""

from types import SimpleNamespace

from xdsl.dialects import arith, builtin
from xdsl.dialects.builtin import f64
from xdsl.ir import Block, Region

from xdsl_ccpp.dialects.ccpp_utils import AccUpdateDeviceOp, AccUpdateSelfOp, HostVarRefOp
from xdsl_ccpp.transforms.util.cap_shared import _expr_text, arg_writes, emit_coalesced_updates


def _emit(touches_by_var, n_calls=2):
    """Build a block with HostVarRefs and n_calls stand-in calls, emit the
    updates for {var: [(call index, writes), ...]} (all "update" touches),
    and return the block's ops as text tokens in order."""
    block = Block()
    refs = {}
    for name in touches_by_var:
        refs[name] = HostVarRefOp(name, "m", f64)
        block.add_op(refs[name])
    calls = [arith.ConstantOp.from_int_and_width(i, 32) for i in range(n_calls)]
    for call in calls:
        block.add_op(call)
    builtin.ModuleOp(Region([block]))
    resolved = {
        name: (refs[name].res, [(calls[i], "update", writes) for i, writes in touches])
        for name, touches in touches_by_var.items()
    }
    emit_coalesced_updates("acc", resolved, lambda ref, call: None)
    out = []
    for op in block.ops:
        if isinstance(op, AccUpdateSelfOp):
            out.append("self(" + ",".join(_expr_text(v) for v in op.arrays) + ")")
        elif isinstance(op, AccUpdateDeviceOp):
            out.append("device(" + ",".join(_expr_text(v) for v in op.arrays) + ")")
        elif isinstance(op, arith.ConstantOp):
            out.append(f"call{calls.index(op)}")
    return out


def test_read_only_run_is_pulled_not_pushed():
    assert _emit({"a": [(0, False), (1, False)]}) == ["self(a)", "call0", "call1"]


def test_run_that_writes_is_pulled_and_pushed():
    assert _emit({"a": [(0, False), (1, True)]}) == ["self(a)", "call0", "call1", "device(a)"]


def test_variables_sharing_a_run_push_only_what_was_written():
    assert _emit({"a": [(0, True)], "b": [(0, False)]}, n_calls=1) == [
        "self(a,b)", "call0", "device(a)",
    ]


def test_arg_writes_follows_intent():
    def arg(**attrs):
        return SimpleNamespace(hasAttr=lambda k: k in attrs, getAttr=lambda k: attrs[k])

    assert not arg_writes(arg(intent="in"))
    assert arg_writes(arg(intent="out"))
    assert arg_writes(arg(intent="inout"))
    assert arg_writes(arg())  # no intent declared: assume it writes
