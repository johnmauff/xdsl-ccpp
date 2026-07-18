"""Unit tests for xdsl_ccpp.transforms.util.cap_shared.

Phase 4 (narrow extraction): _is_framework_managed moved here from suite_cap.py
so it can be shared with _get_suite_lifecycle_ret_info, which was previously
hand-rolling a partial mirror of the same logic (is_interstitial only, missing
the advected/allocatable-real-array branch). This is its first direct unit
test -- previously only exercised indirectly via end-to-end examples.

_build_no_suite_matched_false_ops was added later, consolidating three
independent copies of the same "no suite matched" error sequence
(run_dispatch.py x2, lifecycle_cap.py x1) into one shared function.

_iter_schemes was added later still, consolidating ccpp_cap.py's and
suite_cap.py's independent copies of the same subcycle-flattening logic
(suite_variable_model.py has a third, deliberately separate copy -- see its
own comment for why it isn't unified here).
"""

from xdsl.dialects import memref, scf

from xdsl_ccpp.dialects.ccpp_utils import WriteErrMsgOp
from xdsl_ccpp.transforms.util.cap_shared import (
    _build_no_suite_matched_false_ops,
    _is_framework_managed,
    _iter_schemes,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    CCPPArgument,
    XMLGroup,
    XMLScheme,
    XMLSubcycle,
)
from xdsl_ccpp.transforms.util.typing import TypeConversions


def _make_arg(name, **attrs):
    arg = CCPPArgument(name)
    for k, v in attrs.items():
        arg.setAttr(k, v)
    return arg


class TestIsFrameworkManaged:
    """_is_framework_managed: interstitials of any type, plus
    advected/allocatable real arrays."""

    def test_interstitial_is_framework_managed_regardless_of_type(self):
        arg = _make_arg("x", is_interstitial=True, type="integer")
        assert _is_framework_managed(arg) is True

    def test_real_array_with_advected_is_framework_managed(self):
        arg = _make_arg("x", type="real", dimensions=2, advected=True)
        assert _is_framework_managed(arg) is True

    def test_real_array_with_allocatable_is_framework_managed(self):
        arg = _make_arg("x", type="real", dimensions=2, allocatable=True)
        assert _is_framework_managed(arg) is True

    def test_real_array_without_advected_or_allocatable_is_not(self):
        arg = _make_arg("x", type="real", dimensions=2)
        assert _is_framework_managed(arg) is False

    def test_non_real_type_with_advected_is_not(self):
        """The advected/allocatable branch only applies to real arrays."""
        arg = _make_arg("x", type="integer", dimensions=2, advected=True)
        assert _is_framework_managed(arg) is False

    def test_real_scalar_with_advected_is_not(self):
        """dimensions must be > 0 -- a scalar can't be an advected array."""
        arg = _make_arg("x", type="real", dimensions=0, advected=True)
        assert _is_framework_managed(arg) is False

    def test_plain_scalar_arg_is_not(self):
        arg = _make_arg("x", type="integer", dimensions=0)
        assert _is_framework_managed(arg) is False


class TestBuildNoSuiteMatchedFalseOps:
    """_build_no_suite_matched_false_ops: the shared "no suite matched"
    fallback error sequence -- previously duplicated three ways
    (run_dispatch.py x2, lifecycle_cap.py x1), which is exactly the failure
    shape that let a Phase 3a review fix land on two copies and miss the
    third. Now a single implementation, directly testable."""

    def _fixture_operands(self):
        errmsg_dest = memref.AllocaOp.get(
            TypeConversions.getBaseType("character"), shape=[512]
        ).memref
        trim_suite_name_res = memref.AllocaOp.get(
            TypeConversions.getBaseType("character"), shape=[64]
        ).memref
        errflg_dest = memref.AllocaOp.get(
            TypeConversions.getBaseType("integer"), shape=[]
        ).memref
        return errmsg_dest, trim_suite_name_res, errflg_dest

    def test_returns_four_ops_in_order(self):
        errmsg_dest, trim_suite_name_res, errflg_dest = self._fixture_operands()
        ops = _build_no_suite_matched_false_ops(
            errmsg_dest, trim_suite_name_res, errflg_dest
        )
        assert len(ops) == 4
        write_err, one_err, store_errflg_err, yield_op = ops
        assert isinstance(write_err, WriteErrMsgOp)
        assert isinstance(store_errflg_err, memref.StoreOp)
        assert isinstance(yield_op, scf.YieldOp)

    def test_error_message_text_has_leading_and_trailing_space(self):
        """Prefix ends and suffix starts with a space so the trimmed suite
        name reads correctly on both sides: "No suite named <name> found"."""
        errmsg_dest, trim_suite_name_res, errflg_dest = self._fixture_operands()
        write_err, _one_err, _store, _yield = _build_no_suite_matched_false_ops(
            errmsg_dest, trim_suite_name_res, errflg_dest
        )
        assert write_err.prefix.data == "No suite named "
        assert write_err.suffix.data == " found"

    def test_writes_to_the_given_errmsg_and_var_operands(self):
        errmsg_dest, trim_suite_name_res, errflg_dest = self._fixture_operands()
        write_err, _one_err, _store, _yield = _build_no_suite_matched_false_ops(
            errmsg_dest, trim_suite_name_res, errflg_dest
        )
        assert write_err.dest == errmsg_dest
        assert write_err.var == trim_suite_name_res

    def test_sets_errflg_to_one_on_the_given_dest(self):
        errmsg_dest, trim_suite_name_res, errflg_dest = self._fixture_operands()
        _write, one_err, store_errflg_err, _yield = _build_no_suite_matched_false_ops(
            errmsg_dest, trim_suite_name_res, errflg_dest
        )
        assert one_err.value.value.data == 1
        assert store_errflg_err.memref == errflg_dest


class TestIterSchemes:
    """_iter_schemes: yield a group's XMLScheme leaves, flattening one level
    of XMLSubcycle nesting."""

    def test_plain_schemes_yielded_directly(self):
        group = XMLGroup("physics")
        group.addChild(XMLScheme("scheme_a"))
        group.addChild(XMLScheme("scheme_b"))
        names = [s.attributes["name"] for s in _iter_schemes(group)]
        assert names == ["scheme_a", "scheme_b"]

    def test_subcycle_schemes_flattened(self):
        group = XMLGroup("physics")
        subcycle = XMLSubcycle(loop_count=2)
        subcycle.addChild(XMLScheme("scheme_a"))
        subcycle.addChild(XMLScheme("scheme_b"))
        group.addChild(subcycle)
        names = [s.attributes["name"] for s in _iter_schemes(group)]
        assert names == ["scheme_a", "scheme_b"]

    def test_mixed_plain_and_subcycle_schemes_preserve_order(self):
        group = XMLGroup("physics")
        subcycle = XMLSubcycle(loop_count=3)
        subcycle.addChild(XMLScheme("scheme_b"))
        subcycle.addChild(XMLScheme("scheme_c"))
        group.addChild(XMLScheme("scheme_a"))
        group.addChild(subcycle)
        group.addChild(XMLScheme("scheme_d"))
        names = [s.attributes["name"] for s in _iter_schemes(group)]
        assert names == ["scheme_a", "scheme_b", "scheme_c", "scheme_d"]

    def test_empty_group_yields_nothing(self):
        group = XMLGroup("physics")
        assert list(_iter_schemes(group)) == []
