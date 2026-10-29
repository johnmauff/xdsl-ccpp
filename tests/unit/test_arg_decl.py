"""A dummy argument's name and declaration flags come from the arg_attrs its
function records (arg_decl, value_name), and an allocatable local's from
its alloca (mark_allocatable_local), not from a name hint: xDSL drops a
trailing "_<digits>" from a name hint, so a scheme argument named like
opt_arg's "opt_var_2" can't be named by its hint.
"""

from io import StringIO

from xdsl.dialects import builtin, func, memref
from xdsl.dialects.builtin import DYNAMIC_INDEX, ArrayAttr, MemRefType, f64
from xdsl.ir import Block, Region

from xdsl_ccpp.backend.print_ftn import ftnPrintContext
from xdsl_ccpp.transforms.util.cap_shared import value_name
from xdsl_ccpp.util.ccpp_conventions import (
    SUITE_ARG_ALLOCATABLE,
    SUITE_ARG_DIM_NAMES,
    SUITE_ARG_INTENT,
    SUITE_ARG_NAME,
    SUITE_ARG_OPTIONAL,
    ArgDecl,
    arg_attr_dict,
    arg_attr_values,
    arg_decl,
    mark_allocatable_local,
)

_DIMS = ["horizontal_loop_extent"]


def test_recorded_name_and_flags():
    attrs = {SUITE_ARG_NAME: "opt_var_2", SUITE_ARG_OPTIONAL: True,
             SUITE_ARG_INTENT: "in", SUITE_ARG_DIM_NAMES: _DIMS}
    assert arg_decl(attrs, "opt_var", 0) == ArgDecl("opt_var_2", False, True, False)


def test_intent_in_narrowing_is_for_arrays_only():
    array = {SUITE_ARG_NAME: "ps", SUITE_ARG_INTENT: "in", SUITE_ARG_DIM_NAMES: _DIMS}
    scalar = {SUITE_ARG_NAME: "dt", SUITE_ARG_INTENT: "in"}
    assert arg_decl(array, "ps", 0).is_in
    assert not arg_decl(scalar, "dt", 0).is_in


def test_allocatable_over_optional_over_intent_in():
    both = {SUITE_ARG_NAME: "x", SUITE_ARG_ALLOCATABLE: True, SUITE_ARG_OPTIONAL: True,
            SUITE_ARG_INTENT: "in", SUITE_ARG_DIM_NAMES: _DIMS}
    assert arg_decl(both, "x", 0) == ArgDecl("x", True, False, False)
    opt_in = {SUITE_ARG_NAME: "x", SUITE_ARG_OPTIONAL: True,
              SUITE_ARG_INTENT: "in", SUITE_ARG_DIM_NAMES: _DIMS}
    assert arg_decl(opt_in, "x", 0) == ArgDecl("x", False, True, False)


def test_name_hint_fallback_without_recorded_name():
    # A name hint is a name only: nothing is parsed out of it.
    assert arg_decl({}, "x__alloc", 0) == ArgDecl("x__alloc", False, False, False)
    assert arg_decl({}, "x", 0) == ArgDecl("x", False, False, False)
    assert arg_decl({}, None, 3) == ArgDecl("arg_3", False, False, False)


def test_attr_values_round_trip():
    values = {SUITE_ARG_NAME: "x", SUITE_ARG_OPTIONAL: True, SUITE_ARG_DIM_NAMES: _DIMS}
    fn = _fn([values])
    assert arg_attr_values(fn) == [values]


def test_value_name_reads_the_recorded_name():
    fn = _fn([{SUITE_ARG_NAME: "opt_var_2"}, {}])
    named, unnamed = fn.body.block.args
    assert named.name_hint == "opt_var"        # xDSL's rewrite of "opt_var_2"
    assert value_name(named) == "opt_var_2"
    assert value_name(unnamed) == "plain"


def test_allocatable_local_keeps_its_name():
    alloca = memref.AllocaOp.get(f64, shape=[0])
    mark_allocatable_local(alloca, "lc_var_2")
    assert alloca.memref.name_hint == "lc_var"  # xDSL's rewrite of "lc_var_2"
    assert value_name(alloca.memref) == "lc_var_2"


def test_printed_names_and_declarations():
    fn = _fn([{SUITE_ARG_NAME: "opt_var_2", SUITE_ARG_OPTIONAL: True,
               SUITE_ARG_INTENT: "in", SUITE_ARG_DIM_NAMES: _DIMS},
              {SUITE_ARG_NAME: "plain", SUITE_ARG_INTENT: "in",
               SUITE_ARG_DIM_NAMES: _DIMS}])
    alloca = memref.AllocaOp.get(f64, shape=[0])
    mark_allocatable_local(alloca, "lc_var_2")
    fn.body.block.insert_op_before(alloca, fn.body.block.first_op)
    out = StringIO()
    ftnPrintContext(output=out).print_op(fn)
    text = out.getvalue()
    assert "subroutine f(opt_var_2, plain)" in text
    assert "optional, target, intent(inout) :: opt_var_2(:)" in text
    assert "target, intent(in) :: plain(:)" in text
    assert "allocatable :: lc_var_2(:)" in text


def _fn(attrs: list) -> func.FuncOp:
    arg_type = MemRefType(f64, [DYNAMIC_INDEX])
    block = Block(arg_types=[arg_type] * len(attrs))
    for arg, name in zip(block.args, ["opt_var_2", "plain"]):
        arg.name_hint = name
    block.add_op(func.ReturnOp())
    return func.FuncOp(
        "f", builtin.FunctionType.from_lists([arg_type] * len(attrs), []),
        Region(block), arg_attrs=ArrayAttr([arg_attr_dict(a) for a in attrs]),
    )
