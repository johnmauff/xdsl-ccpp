"""Unit tests for xdsl_ccpp.transforms.util.suite_variable_model.

_iter_schemes_duck_typed is the module's own private, duck-typed mirror of
cap_shared._iter_schemes (see the comment at SuiteVariableModel's one call
site for why the two can't be unified: this module's own contract, per its
docstring, is zero xDSL/MLIR imports, and cap_shared transitively imports
xdsl.dialects). Both must independently support recursing into a nested
subcycle, so both get the same direct test coverage.
"""

from xdsl_ccpp.transforms.util.ccpp_descriptors import XMLGroup, XMLScheme, XMLSubcycle
from xdsl_ccpp.transforms.util.suite_variable_model import _iter_schemes_duck_typed


class TestIterSchemesDuckTyped:
    """_iter_schemes_duck_typed: yield a group's XMLScheme leaves, flattening
    a group's XMLSubcycle nesting recursively, to arbitrary depth."""

    def test_plain_schemes_yielded_directly(self):
        group = XMLGroup("physics")
        group.addChild(XMLScheme("scheme_a"))
        group.addChild(XMLScheme("scheme_b"))
        names = [s.attributes["name"] for s in _iter_schemes_duck_typed(group)]
        assert names == ["scheme_a", "scheme_b"]

    def test_subcycle_schemes_flattened(self):
        group = XMLGroup("physics")
        subcycle = XMLSubcycle(loop_count=2)
        subcycle.addChild(XMLScheme("scheme_a"))
        subcycle.addChild(XMLScheme("scheme_b"))
        group.addChild(subcycle)
        names = [s.attributes["name"] for s in _iter_schemes_duck_typed(group)]
        assert names == ["scheme_a", "scheme_b"]

    def test_nested_subcycle_schemes_flattened_recursively(self):
        """A subcycle nested inside another subcycle -- real CCPP pattern,
        see examples/var_compat/var_compatibility_suite.xml (ported from
        NCAR ccpp-framework's feature/capgen-v1), which nests three levels
        deep in one branch."""
        group = XMLGroup("physics")
        inner = XMLSubcycle(loop_count=2)
        inner.addChild(XMLScheme("inner_scheme"))
        outer = XMLSubcycle(loop_count=3)
        outer.addChild(XMLScheme("outer_scheme"))
        outer.addChild(inner)
        group.addChild(outer)
        names = [s.attributes["name"] for s in _iter_schemes_duck_typed(group)]
        assert names == ["outer_scheme", "inner_scheme"]

    def test_mixed_plain_and_subcycle_schemes_preserve_order(self):
        group = XMLGroup("physics")
        subcycle = XMLSubcycle(loop_count=3)
        subcycle.addChild(XMLScheme("scheme_b"))
        subcycle.addChild(XMLScheme("scheme_c"))
        group.addChild(XMLScheme("scheme_a"))
        group.addChild(subcycle)
        group.addChild(XMLScheme("scheme_d"))
        names = [s.attributes["name"] for s in _iter_schemes_duck_typed(group)]
        assert names == ["scheme_a", "scheme_b", "scheme_c", "scheme_d"]

    def test_empty_group_yields_nothing(self):
        group = XMLGroup("physics")
        assert list(_iter_schemes_duck_typed(group)) == []
