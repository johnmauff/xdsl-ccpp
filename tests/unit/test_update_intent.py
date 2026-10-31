"""emit_coalesced_updates: a run of host calls is pulled (`update self`)
before it, and pushed back (`update device`) after it only if some call in
the run may write the variable; a run that starts by overwriting (intent
out) the section it is passed is not pulled, and pushes only that section
(gpu-sync-intent-aware)."""

from types import SimpleNamespace

from xdsl.dialects import arith, builtin, scf
from xdsl.dialects.builtin import ArrayAttr, MemRefType, StringAttr, f64
from xdsl.ir import Block, Region

from xdsl_ccpp.dialects.ccpp_utils import (
    AccUpdateDeviceOp,
    AccUpdateSelfOp,
    HostVarRefOp,
    KeywordCallOp,
    RankReducingSliceOp,
)
from xdsl_ccpp.transforms.util.cap_shared import (
    Touch,
    _expr_text,
    arg_overwrites,
    arg_writes,
    call_section,
    emit_coalesced_updates,
)


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


# --- runs that start by overwriting what they are passed (stage 3) ---------

def _sliced_block(names, n_calls):
    """A block with a rank-1 HostVarRef per name, the section name(1:2) of
    each, and n_calls stand-in calls. Returns (block, refs, sections, calls)."""
    block = Block()
    lo = arith.ConstantOp.from_int_and_width(1, 32)
    hi = arith.ConstantOp.from_int_and_width(2, 32)
    block.add_ops([lo, hi])
    refs, sections = {}, {}
    for name in names:
        refs[name] = HostVarRefOp(name, "m", MemRefType(f64, [-1]))
        sections[name] = RankReducingSliceOp(refs[name].res, "R", [lo.result], [hi.result], [])
        block.add_ops([refs[name], sections[name]])
    calls = [arith.ConstantOp.from_int_and_width(100 + i, 32) for i in range(n_calls)]
    block.add_ops(calls)
    builtin.ModuleOp(Region([block]))
    return block, refs, sections, calls


def _tokens(block, calls):
    out = []
    for op in block.ops:
        if isinstance(op, AccUpdateSelfOp):
            out.append("self(" + ",".join(_expr_text(v) for v in op.arrays) + ")")
        elif isinstance(op, AccUpdateDeviceOp):
            out.append("device(" + ",".join(_expr_text(v) for v in op.arrays) + ")")
        elif op in calls:
            out.append(f"call{calls.index(op)}")
    return out


def test_run_starting_with_intent_out_is_not_pulled_and_pushes_its_section():
    block, refs, sec, calls = _sliced_block(["a"], 2)
    emit_coalesced_updates("acc", {"a": (refs["a"].res, [
        Touch(calls[0], "update", True, True, sec["a"].results[0]),
        Touch(calls[1], "update", False, False, sec["a"].results[0]),
    ])}, lambda ref, call: None)
    assert _tokens(block, calls) == ["call0", "call1", "device(a(1:2))"]


def test_run_starting_with_intent_inout_is_pulled():
    block, refs, sec, calls = _sliced_block(["a"], 1)
    emit_coalesced_updates("acc", {"a": (refs["a"].res, [
        Touch(calls[0], "update", True, False, sec["a"].results[0]),
    ])}, lambda ref, call: None)
    assert _tokens(block, calls) == ["self(a)", "call0", "device(a)"]


def test_overwrite_without_a_known_section_is_pulled():
    block, refs, _, calls = _sliced_block(["a"], 1)
    emit_coalesced_updates("acc", {"a": (refs["a"].res, [
        Touch(calls[0], "update", True, True, None),
    ])}, lambda ref, call: None)
    assert _tokens(block, calls) == ["self(a)", "call0", "device(a)"]


def test_run_passing_different_sections_is_pulled():
    block, refs, sec, calls = _sliced_block(["a"], 2)
    other = RankReducingSliceOp(
        refs["a"].res, "R", [sec["a"].range_lowers[0]], [sec["a"].range_lowers[0]], []
    )
    block.insert_op_before(other, calls[0])
    emit_coalesced_updates("acc", {"a": (refs["a"].res, [
        Touch(calls[0], "update", True, True, sec["a"].results[0]),
        Touch(calls[1], "update", True, False, other.results[0]),
    ])}, lambda ref, call: None)
    assert _tokens(block, calls) == ["self(a)", "call0", "call1", "device(a)"]


def test_scheme_intent_wins_over_the_suite_merged_intent():
    """The suite cap merges intents across schemes into one scheme's
    argument ("in" + "out" -> "inout") and keeps its own as declared_intent."""
    def arg(**attrs):
        return SimpleNamespace(hasAttr=lambda k: k in attrs, getAttr=lambda k: attrs[k])

    assert arg_overwrites(arg(intent="inout", declared_intent="out"))
    assert not arg_writes(arg(intent="inout", declared_intent="in"))
    assert not arg_overwrites(arg(intent="inout"))
    assert arg_overwrites(arg(intent="out"))


def _guarded_call(block, value, before):
    """Insert `if (true) call s(x=value)` before op *before*; return the if."""
    cond = arith.ConstantOp(builtin.IntegerAttr(1, 1))
    call = KeywordCallOp("s", ArrayAttr([StringAttr("x")]), ArrayAttr([]), [value], [])
    if_op = scf.IfOp(cond.result, [], [call, scf.YieldOp()])
    block.insert_ops_before([cond, if_op], before)
    return if_op, call


def test_call_section_is_the_argument_when_valid_before_the_call():
    block, refs, sec, calls = _sliced_block(["a", "b"], 1)
    if_op, _ = _guarded_call(block, sec["a"].results[0], calls[0])
    assert call_section(if_op, "x", None) is sec["a"].results[0]
    assert call_section(if_op, "y", None) is None  # not passed

    if_op, _ = _guarded_call(block, refs["b"].res, calls[0])
    assert call_section(if_op, "x", refs["b"].res) is refs["b"].res  # the whole variable


def test_call_section_ignores_a_section_built_inside_the_guard():
    block, refs, sec, calls = _sliced_block(["a"], 1)
    if_op, call = _guarded_call(block, refs["a"].res, calls[0])
    inner = RankReducingSliceOp(
        refs["a"].res, "R", [sec["a"].range_lowers[0]], [sec["a"].range_uppers[0]], []
    )
    if_op.true_region.blocks[0].insert_op_before(inner, call)
    call.operands[0] = inner.results[0]
    assert call_section(if_op, "x", None) is None
