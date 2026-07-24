"""Unit tests for VerticalFlipOp/VerticalFlipWriteBackOp in isolation.

Stage 2 of the vertical-flip work: these two operations (modeled directly on
the existing KindCastOp/KindWriteBackOp pair) and their print_ftn.py cases
are tested here by constructing the IR directly and printing it, WITHOUT
going through suite_cap.py -- nothing in the real generation pipeline
inserts these ops yet. That wiring is a later stage.

VerticalFlipOp allocates a local temp and reverses an array section along
the vertical (layer) dimension:

    allocate(result(size(source,1), size(source,2)))
    result = source(:, size(source, 2):1:-1)

for a rank-2 array with the vertical dimension at (1-based) Fortran index 2.
VerticalFlipWriteBackOp applies the identical reversed-section expression on
the *source* side of the write-back assignment, since reversing a reversal
restores the original order.
"""

from io import StringIO

from xdsl.dialects import func
from xdsl.dialects.builtin import ModuleOp, StringAttr
from xdsl.ir import Block, Region

from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.dialects.ccpp_utils import VerticalFlipOp, VerticalFlipWriteBackOp
from xdsl_ccpp.transforms.util.typing import TypeConversions


def _wrap_and_print(block, arg_types, fn_name="test_fn") -> str:
    fn_type = func.FunctionType.from_lists(arg_types, [])
    fn = func.FuncOp(fn_name, fn_type, Region([block]), visibility="public")
    named_module = ModuleOp([fn])
    named_module.properties["sym_name"] = StringAttr("test_mod")
    prog = ModuleOp([named_module])
    out = StringIO()
    print_to_ftn(prog, out)
    return out.getvalue()


def _rank2_array_type():
    return TypeConversions.convert("real", "kind_phys", 2)


class TestVerticalFlipOpPrinting:
    def test_allocates_and_reverses_correct_dimension(self):
        arr_type = _rank2_array_type()
        block = Block(arg_types=[arr_type])
        source = block.args[0]
        source.name_hint = "effrr_in"

        flip_op = VerticalFlipOp(source, 2, arr_type)
        flip_op.res.name_hint = "effrr_in_flip"

        block.add_ops([flip_op, func.ReturnOp()])
        out = _wrap_and_print(block, [arr_type])

        assert "allocate(effrr_in_flip(size(effrr_in, 1), size(effrr_in, 2)))" in out
        assert "effrr_in_flip = effrr_in(:, size(effrr_in, 2):1:-1)" in out

    def test_reverses_first_dimension_when_vertical_dim_is_1(self):
        arr_type = _rank2_array_type()
        block = Block(arg_types=[arr_type])
        source = block.args[0]
        source.name_hint = "x"

        flip_op = VerticalFlipOp(source, 1, arr_type)
        flip_op.res.name_hint = "x_flip"

        block.add_ops([flip_op, func.ReturnOp()])
        out = _wrap_and_print(block, [arr_type])

        assert "x_flip = x(size(x, 1):1:-1, :)" in out


class TestVerticalFlipWriteBackOpPrinting:
    def test_write_back_reverses_and_deallocates(self):
        arr_type = _rank2_array_type()
        block = Block(arg_types=[arr_type])
        dest = block.args[0]
        dest.name_hint = "effrr_in"

        flip_op = VerticalFlipOp(dest, 2, arr_type)
        flip_op.res.name_hint = "effrr_in_flip"
        writeback_op = VerticalFlipWriteBackOp(flip_op.res, dest, 2)

        block.add_ops([flip_op, writeback_op, func.ReturnOp()])
        out = _wrap_and_print(block, [arr_type])

        assert "effrr_in = effrr_in_flip(:, size(effrr_in_flip, 2):1:-1)" in out
        assert "deallocate(effrr_in_flip)" in out
