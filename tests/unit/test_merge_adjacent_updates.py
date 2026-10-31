"""merge_adjacent_updates: adjacent update directives of one kind become one,
so `update self(a)` + `update self(b)` is printed as `update self(a, b)`."""

from xdsl.dialects import builtin
from xdsl.dialects.builtin import f64
from xdsl.ir import Block, Region

from xdsl_ccpp.dialects.ccpp_utils import (
    AccUpdateDeviceOp,
    AccUpdateSelfOp,
    HostVarRefOp,
    OmpTargetUpdateFromOp,
)
from xdsl_ccpp.transforms.util.cap_shared import _expr_text, merge_adjacent_updates


def _module(build):
    """A module whose body is filled by build(add, ref) -> ops in order."""
    block = Block()
    refs = {}

    def ref(name):
        if name not in refs:
            refs[name] = HostVarRefOp(name, "m", f64)
            block.add_op(refs[name])
        return refs[name].res

    build(block.add_op, ref)
    return builtin.ModuleOp(Region([block]))


def _updates(module):
    """[(kind, [variable text, ...]), ...] for every update op, in order."""
    return [
        (type(op).__name__, [_expr_text(v) for v in op.arrays])
        for op in module.body.block.ops
        if not isinstance(op, HostVarRefOp)
    ]


def test_adjacent_same_kind_updates_merge():
    def build(add, ref):
        a, b, c = ref("a"), ref("b"), ref("c")
        add(AccUpdateSelfOp([a]))
        add(AccUpdateSelfOp([b, c]))
        add(AccUpdateDeviceOp([a]))
        add(AccUpdateDeviceOp([b]))

    module = _module(build)
    merge_adjacent_updates(module)
    assert _updates(module) == [
        ("AccUpdateSelfOp", ["a", "b", "c"]),
        ("AccUpdateDeviceOp", ["a", "b"]),
    ]


def test_a_variable_is_listed_once():
    """Two references to the same variable (separate HostVarRefOps) are one."""
    def build(add, ref):
        a = ref("a")
        again = HostVarRefOp("a", "m", f64)
        add(again)
        add(AccUpdateSelfOp([a]))
        add(AccUpdateSelfOp([again.res, ref("b")]))

    module = _module(build)
    merge_adjacent_updates(module)
    assert _updates(module)[-1] == ("AccUpdateSelfOp", ["a", "b"])


def test_other_ops_and_kinds_are_boundaries():
    """Updates separated by another op, or of a different kind, stay apart."""
    def build(add, ref):
        a, b = ref("a"), ref("b")
        add(AccUpdateSelfOp([a]))
        add(HostVarRefOp("c", "m", f64))          # any other op
        add(AccUpdateSelfOp([b]))
        add(OmpTargetUpdateFromOp([a]))           # different kind
        add(AccUpdateDeviceOp([b]))

    module = _module(build)
    merge_adjacent_updates(module)
    assert [kind for kind, _ in _updates(module)] == [
        "AccUpdateSelfOp", "AccUpdateSelfOp", "OmpTargetUpdateFromOp", "AccUpdateDeviceOp",
    ]
