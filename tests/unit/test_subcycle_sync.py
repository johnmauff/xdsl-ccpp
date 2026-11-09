"""GPU syncs for scheme calls inside subcycle loops (xdsl72gpu rrtmgp: the
radiation schemes run in `do ccpp_loop_cnt = 1, num_diag_subcycles` and got
no update self/device at all, so a device scheme read fluxes a CPU scheme
had just written on the host).

iter_call_guards finds the calls inside loops; emit_coalesced_updates ends a
host run where the call sequence enters or leaves a loop body, so each run's
syncs sit in one block and run on every iteration."""

from xdsl.dialects import arith, builtin, memref, scf
from xdsl.dialects.builtin import f64, i32
from xdsl.ir import Block, Region

from xdsl_ccpp.dialects.ccpp_utils import (
    AccUpdateDeviceOp,
    AccUpdateSelfOp,
    HostVarRefOp,
    SubcycleLoopOp,
)
from xdsl_ccpp.transforms.util.cap_shared import (
    Touch,
    _expr_text,
    emit_coalesced_updates,
    iter_call_guards,
    top_level_ancestor,
)


def _call(i):
    """A stand-in for a scheme call (emit_coalesced_updates only inserts
    around it)."""
    return arith.ConstantOp.from_int_and_width(100 + i, 32)


def _guard(i):
    """A stand-in error guard: `if (true) <call i>`."""
    cond = arith.ConstantOp(builtin.IntegerAttr(1, 1))
    return cond, scf.IfOp(cond.result, [], [_call(i), scf.YieldOp()])


def _loop(body_ops):
    counter = memref.AllocaOp.get(i32, shape=[])
    return counter, SubcycleLoopOp(2, counter.memref, body_ops, True)


def _tokens(block, calls):
    out = []
    for op in block.ops:
        if isinstance(op, AccUpdateSelfOp):
            out.append("self(" + ",".join(_expr_text(v) for v in op.arrays) + ")")
        elif isinstance(op, AccUpdateDeviceOp):
            out.append("device(" + ",".join(_expr_text(v) for v in op.arrays) + ")")
        elif isinstance(op, SubcycleLoopOp):
            out.append("loop[" + " ".join(_tokens(op.body.block, calls)) + "]")
        elif op in calls:
            out.append(f"call{calls.index(op)}")
    return out


def test_iter_call_guards_includes_calls_in_loops_in_program_order():
    block = Block()
    c0, g0 = _guard(0)
    c1, g1 = _guard(1)
    c2, g2 = _guard(2)
    c3, g3 = _guard(3)
    counter, loop = _loop([c1, g1, c2, g2])
    block.add_ops([c0, g0, counter, loop, c3, g3])
    builtin.ModuleOp(Region([block]))
    assert list(iter_call_guards(block)) == [g0, g1, g2, g3]
    assert top_level_ancestor(g1, block) is loop
    assert top_level_ancestor(g0, block) is g0


def _block_with_loop():
    """call0; do { call1; call2 }; call3 -- with a host variable a."""
    block = Block()
    ref = HostVarRefOp("a", "m", f64)
    calls = [_call(i) for i in range(4)]
    counter, loop = _loop([calls[1], calls[2]])
    block.add_ops([ref, calls[0], counter, loop, calls[3]])
    builtin.ModuleOp(Region([block]))
    return block, ref, calls


def test_run_does_not_cross_into_a_loop():
    # A host read before the loop and one inside it, with a device write
    # after it in the loop: the second iteration's host read needs its own
    # pull, inside the loop.
    block, ref, calls = _block_with_loop()
    emit_coalesced_updates("acc", {"a": (ref.res, [
        Touch(calls[0], "update", False),
        Touch(calls[1], "update", False),
        Touch(calls[2], "present", True),
    ])}, lambda r, call: None)
    assert _tokens(block, calls) == [
        "self(a)", "call0", "loop[self(a) call1 call2]", "call3",
    ]


def test_run_does_not_cross_out_of_a_loop():
    # A host write in the loop and a host read after it: the push stays in
    # the loop (every iteration), the read after the loop pulls again.
    block, ref, calls = _block_with_loop()
    emit_coalesced_updates("acc", {"a": (ref.res, [
        Touch(calls[1], "update", True),
        Touch(calls[2], "present", False),
        Touch(calls[3], "update", False),
    ])}, lambda r, call: None)
    assert _tokens(block, calls) == [
        "call0", "loop[self(a) call1 device(a) call2]", "self(a)", "call3",
    ]


def test_run_inside_one_loop_body_is_still_coalesced():
    block, ref, calls = _block_with_loop()
    emit_coalesced_updates("acc", {"a": (ref.res, [
        Touch(calls[1], "update", False),
        Touch(calls[2], "update", True),
    ])}, lambda r, call: None)
    assert _tokens(block, calls) == ["call0", "loop[self(a) call1 call2 device(a)]", "call3"]


# ── a device call that only reads keeps the host copy current ──────────────

def _flat_block(n):
    """call0 .. call<n-1> in one block, with a host variable a."""
    block = Block()
    ref = HostVarRefOp("a", "m", f64)
    calls = [_call(i) for i in range(n)]
    block.add_ops([ref, *calls])
    builtin.ModuleOp(Region([block]))
    return block, ref, calls


def _emit(ref, touches):
    emit_coalesced_updates("acc", {"a": (ref.res, touches)}, lambda r, call: None)


def test_device_read_keeps_host_current():
    # cam4: a diagnostics scheme reads T on the device between two CPU
    # schemes; the second CPU scheme needs no second pull.
    block, ref, calls = _flat_block(3)
    _emit(ref, [
        Touch(calls[0], "update", False),
        Touch(calls[1], "present", False),
        Touch(calls[2], "update", False),
    ])
    assert _tokens(block, calls) == ["self(a)", "call0", "call1", "call2"]


def test_device_write_needs_a_new_pull():
    block, ref, calls = _flat_block(3)
    _emit(ref, [
        Touch(calls[0], "update", False),
        Touch(calls[1], "present", True),
        Touch(calls[2], "update", False),
    ])
    assert _tokens(block, calls) == ["self(a)", "call0", "call1", "self(a)", "call2"]


def test_host_write_pushed_before_device_read_then_no_pull():
    block, ref, calls = _flat_block(3)
    _emit(ref, [
        Touch(calls[0], "update", True),
        Touch(calls[1], "present", False),
        Touch(calls[2], "update", False),
    ])
    assert _tokens(block, calls) == ["self(a)", "call0", "device(a)", "call1", "call2"]


def test_section_only_run_leaves_host_stale():
    # A run that overwrites (intent out) the section it is passed pulls
    # nothing; the rest of the host copy is still stale afterwards.
    block, ref, calls = _flat_block(3)
    _emit(ref, [
        Touch(calls[0], "update", True, True, ref.res),
        Touch(calls[1], "present", False),
        Touch(calls[2], "update", False),
    ])
    assert _tokens(block, calls) == ["call0", "device(a)", "call1", "self(a)", "call2"]


def test_loop_boundary_resets_host_current():
    # call0 (host) before the loop, call1 (device read) and call2 (host)
    # in it: the host copy is not trusted across the boundary, so call2
    # pulls inside the loop.
    block, ref, calls = _block_with_loop()
    _emit(ref, [
        Touch(calls[0], "update", False),
        Touch(calls[1], "present", False),
        Touch(calls[2], "update", False),
    ])
    assert _tokens(block, calls) == ["self(a)", "call0", "loop[call1 self(a) call2]", "call3"]
