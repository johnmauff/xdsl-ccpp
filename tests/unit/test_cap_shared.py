"""Unit tests for xdsl_ccpp.transforms.util.cap_shared.

Phase 4 (narrow extraction): _is_framework_managed moved here from suite_cap.py
so it can be shared with _get_suite_lifecycle_ret_info, which was previously
hand-rolling a partial mirror of the same logic (is_interstitial only, missing
the advected/allocatable-real-array branch). This is its first direct unit
test -- previously only exercised indirectly via end-to-end examples.
"""

from xdsl_ccpp.transforms.util.cap_shared import _is_framework_managed
from xdsl_ccpp.transforms.util.ccpp_descriptors import CCPPArgument


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
