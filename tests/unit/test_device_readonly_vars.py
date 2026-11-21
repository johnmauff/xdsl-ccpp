"""Host variables the device only reads (find_device_readonly_host_vars)
need no update self pull before their CPU users: emit_coalesced_updates
treats their host copy as current at function entry and across subcycle-loop
boundaries (host_current_at_entry). cam4: latitude, read by zm_convr on the
device, was pulled before each of its CPU readers in every phase."""

from types import SimpleNamespace

from xdsl.dialects import arith, builtin
from xdsl.dialects.builtin import f64
from xdsl.ir import Block, Region

from xdsl_ccpp.dialects.ccpp_utils import AccUpdateDeviceOp, AccUpdateSelfOp, HostVarRefOp
from xdsl_ccpp.transforms.util.cap_shared import (
    _expr_text,
    emit_coalesced_updates,
    find_device_readonly_host_vars,
)


# --- find_device_readonly_host_vars ----------------------------------------

def _arg(**attrs):
    return SimpleNamespace(hasAttr=lambda k: k in attrs, getAttr=lambda k: attrs[k])


def _scheme(**tables):
    """A scheme's metadata: {table name: [arg, ...]}."""
    return SimpleNamespace(arg_tables={
        name: SimpleNamespace(getFunctionArguments=lambda args=args: args)
        for name, args in tables.items()
    })


def test_device_reader_only_is_readonly():
    meta = {
        "dev": _scheme(dev_run=[_arg(model_var_name="lat", memory_space="device", intent="in")]),
        "cpu": _scheme(cpu_run=[_arg(model_var_name="lat", intent="in")]),
    }
    assert find_device_readonly_host_vars({"dev", "cpu"}, meta) == {"lat"}


def test_device_writer_in_any_phase_is_not_readonly():
    meta = {
        "dev": _scheme(
            dev_run=[_arg(model_var_name="t", memory_space="device", intent="in")],
            dev_timestep_init=[_arg(model_var_name="t", memory_space="device", intent="inout")],
        ),
    }
    assert find_device_readonly_host_vars({"dev"}, meta) == frozenset()


def test_device_writer_in_another_scheme_is_not_readonly():
    meta = {
        "a": _scheme(a_run=[_arg(model_var_name="t", memory_space="device", intent="in")]),
        "b": _scheme(b_run=[_arg(model_var_name="t", memory_space="device", intent="out")]),
    }
    assert find_device_readonly_host_vars({"a", "b"}, meta) == frozenset()
    # Only the schemes passed count (callers pass every suite of the module).
    assert find_device_readonly_host_vars({"a"}, meta) == {"t"}


def test_declared_intent_wins_and_no_intent_counts_as_a_writer():
    meta = {
        # The suite cap merged "inout" into this arg; the scheme declares "in".
        "a": _scheme(a_run=[_arg(model_var_name="x", memory_space="device",
                                 intent="inout", declared_intent="in")]),
        "b": _scheme(b_run=[_arg(model_var_name="y", memory_space="device")]),
    }
    assert find_device_readonly_host_vars({"a", "b"}, meta) == {"x"}


def test_cpu_writer_does_not_matter_and_host_only_vars_are_excluded():
    meta = {
        "dev": _scheme(dev_run=[_arg(model_var_name="lat", memory_space="device", intent="in")]),
        "cpu": _scheme(cpu_run=[_arg(model_var_name="lat", intent="inout"),
                                _arg(model_var_name="ps", intent="in")]),
    }
    assert find_device_readonly_host_vars({"dev", "cpu"}, meta) == {"lat"}


# --- emit_coalesced_updates(host_current_at_entry=...) -----------------------

def _emit(touches_by_var, n_calls, host_current_at_entry=frozenset()):
    """{var: [(call index, category, writes), ...]} -> the block's ops as
    text tokens in order."""
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
        name: (refs[name].res, [(calls[i], cat, writes) for i, cat, writes in touches])
        for name, touches in touches_by_var.items()
    }
    emit_coalesced_updates("acc", resolved, lambda ref, call: None, host_current_at_entry)
    out = []
    for op in block.ops:
        if isinstance(op, AccUpdateSelfOp):
            out.append("self(" + ",".join(_expr_text(v) for v in op.arrays) + ")")
        elif isinstance(op, AccUpdateDeviceOp):
            out.append("device(" + ",".join(_expr_text(v) for v in op.arrays) + ")")
        elif isinstance(op, arith.ConstantOp):
            out.append(f"call{calls.index(op)}")
    return out


def test_cpu_reader_first_in_the_function_is_pulled_by_default():
    assert _emit({"lat": [(0, "update", False), (1, "present", False)]}, 2) == [
        "self(lat)", "call0", "call1",
    ]


def test_readonly_var_is_not_pulled():
    touches = {"lat": [(0, "update", False), (1, "present", False), (2, "update", False)]}
    assert _emit(touches, 3, {"lat"}) == ["call0", "call1", "call2"]


def test_readonly_var_written_on_the_cpu_is_still_pushed():
    touches = {"lat": [(0, "update", True), (1, "present", False)]}
    assert _emit(touches, 2, {"lat"}) == ["call0", "device(lat)", "call1"]


def test_only_the_named_identities_skip_the_pull():
    touches = {
        "lat": [(0, "update", False), (1, "present", False)],
        "t": [(0, "update", False), (1, "present", True)],
    }
    assert _emit(touches, 2, {"lat"}) == ["self(t)", "call0", "call1"]
