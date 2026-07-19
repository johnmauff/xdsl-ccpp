"""Unit tests for subcycle support.

Verifies that <subcycle loop="N"> in a suite XML is:
  - parsed into a SubcycleOp in the CCPP IR (frontend)
  - reconstructed into XMLSubcycle by BuildSchemeDescription (transforms)
  - flattened correctly by getSchemeNames / getCallSequence (suite_cap)
  - included in track() results (ccpp_track_variables)

Nested subcycles (a <subcycle> inside another <subcycle>, or a forLoop()
inside another forLoop()) are explicitly rejected, not supported: real CCPP
suites use multiple sibling subcycles (see
examples/atmospheric_physics/suite_cam4_py.py), never nesting, and the
Python suite-authoring API's own type contract doesn't allow it either.
Rejected at three entry points -- the XML frontend parser, the Python DSL
frontend's IR-emission, and (defense in depth) IR-to-descriptor
reconstruction, shared by both frontends -- so a nested subcycle fails
loudly instead of silently dropping every scheme inside it.
"""

import pytest

from xdsl.utils.hints import isa

from xdsl_ccpp.dialects.ccpp import GroupOp, SchemeOp, SubcycleOp, SuiteOp
from xdsl_ccpp.frontend.py_api import (
    SchemeDescriptor,
    SubcycleDescriptor,
    _group_item_to_op,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    BuildSchemeDescription,
    XMLSubcycle,
)
from xdsl_ccpp.transforms.suite_cap import GenerateSuiteSubroutine
from xdsl_ccpp.tools.ccpp_track_variables import track

from tests.unit.helpers import CCPP_MANDATORY_ARGS, two_scheme_subcycle_xml


# ── helpers ───────────────────────────────────────────────────────────────────

def _scheme_meta(name: str, extra_args: str = "") -> str:
    return f"""\
[ccpp-table-properties]
  name = {name}
  type = scheme
[ccpp-arg-table]
  name = {name}_run
  type = scheme
{extra_args}
{CCPP_MANDATORY_ARGS}
"""


# ── Frontend parsing ──────────────────────────────────────────────────────────

class TestFrontendParsing:
    """<subcycle> XML → SubcycleOp in the CCPP IR."""

    def test_subcycle_emits_subcycle_op(self, build_module):
        suite_xml = two_scheme_subcycle_xml("scheme_a", "scheme_b", loop=2)
        module = build_module(
            [_scheme_meta("scheme_a"), _scheme_meta("scheme_b")], [], suite_xml
        )
        suite_op = next(op for op in module.body.ops if isa(op, SuiteOp))
        group_op = next(op for op in suite_op.body.ops if isa(op, GroupOp))
        children = list(group_op.body.ops)

        assert len(children) == 1
        assert isa(children[0], SubcycleOp)
        assert children[0].loop_count.data == "2"

    def test_subcycle_contains_scheme_ops(self, build_module):
        suite_xml = two_scheme_subcycle_xml("scheme_a", "scheme_b", loop=2)
        module = build_module(
            [_scheme_meta("scheme_a"), _scheme_meta("scheme_b")], [], suite_xml
        )
        suite_op = next(op for op in module.body.ops if isa(op, SuiteOp))
        group_op = next(op for op in suite_op.body.ops if isa(op, GroupOp))
        subcycle_op = next(op for op in group_op.body.ops if isa(op, SubcycleOp))
        scheme_names = [
            op.scheme_name.data for op in subcycle_op.body.ops if isa(op, SchemeOp)
        ]

        assert scheme_names == ["scheme_a", "scheme_b"]

    def test_loop_count_one(self, build_module):
        suite_xml = two_scheme_subcycle_xml("scheme_a", "scheme_b", loop=1)
        module = build_module(
            [_scheme_meta("scheme_a"), _scheme_meta("scheme_b")], [], suite_xml
        )
        suite_op = next(op for op in module.body.ops if isa(op, SuiteOp))
        group_op = next(op for op in suite_op.body.ops if isa(op, GroupOp))
        subcycle_op = next(op for op in group_op.body.ops if isa(op, SubcycleOp))
        assert subcycle_op.loop_count.data == "1"

    def test_mixed_flat_and_subcycled_schemes(self, build_module):
        """A group with a flat scheme before and after a subcycle block."""
        suite_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="1.0">
  <group name="physics">
    <scheme>pre_scheme</scheme>
    <subcycle loop="3">
      <scheme>fast_scheme</scheme>
    </subcycle>
    <scheme>post_scheme</scheme>
  </group>
</suite>
"""
        metas = [_scheme_meta(n) for n in ("pre_scheme", "fast_scheme", "post_scheme")]
        module = build_module(metas, [], suite_xml)
        suite_op = next(op for op in module.body.ops if isa(op, SuiteOp))
        group_op = next(op for op in suite_op.body.ops if isa(op, GroupOp))
        children = list(group_op.body.ops)

        assert isa(children[0], SchemeOp) and children[0].scheme_name.data == "pre_scheme"
        assert isa(children[1], SubcycleOp) and children[1].loop_count.data == "3"
        assert isa(children[2], SchemeOp) and children[2].scheme_name.data == "post_scheme"

    def test_nested_subcycle_is_rejected(self, build_module):
        """A <subcycle> nested inside another <subcycle> must raise a clear
        error at parse time, not silently drop the nested schemes.

        Real CCPP suites (CAM4's diagnostic radiation subcycles) use multiple
        sibling subcycles, never nesting -- confirmed via
        examples/atmospheric_physics/suite_cam4_py.py and the Python
        suite-authoring API's own type contract (forLoop only accepts a list
        of schemes, not another subcycle).
        """
        suite_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="1.0">
  <group name="physics">
    <subcycle loop="2">
      <scheme>outer_scheme</scheme>
      <subcycle loop="3">
        <scheme>inner_scheme</scheme>
      </subcycle>
    </subcycle>
  </group>
</suite>
"""
        metas = [_scheme_meta(n) for n in ("outer_scheme", "inner_scheme")]
        with pytest.raises(ValueError, match="Nested <subcycle> elements are not supported"):
            build_module(metas, [], suite_xml)


# ── Python DSL frontend ────────────────────────────────────────────────────────

class TestPythonDSLFrontendRejectsNesting:
    """forLoop() bypasses the XML parser entirely (py_api.py builds SubcycleOp
    directly), so it needs its own guard against nesting."""

    def test_nested_forloop_is_rejected(self):
        inner_scheme = SchemeDescriptor("inner_scheme", {})
        inner = SubcycleDescriptor(2, [inner_scheme])
        outer_scheme = SchemeDescriptor("outer_scheme", {})
        outer = SubcycleDescriptor(3, [outer_scheme, inner])

        with pytest.raises(ValueError, match="Nested forLoop\\(\\) blocks are not supported"):
            _group_item_to_op(outer, {})

    def test_non_nested_forloop_still_works(self):
        """Sanity check: a plain (non-nested) forLoop still converts fine."""
        scheme_a = SchemeDescriptor("scheme_a", {})
        scheme_b = SchemeDescriptor("scheme_b", {})
        subcycle = SubcycleDescriptor(2, [scheme_a, scheme_b])

        op = _group_item_to_op(subcycle, {})

        assert isa(op, SubcycleOp)
        assert op.loop_count.data == "2"


# ── Descriptor reconstruction ─────────────────────────────────────────────────

class TestBuildSchemeDescription:
    """SubcycleOp in IR → XMLSubcycle in the descriptor tree."""

    def test_subcycle_becomes_xml_subcycle(self, build_module):
        suite_xml = two_scheme_subcycle_xml("scheme_a", "scheme_b", loop=2)
        module = build_module(
            [_scheme_meta("scheme_a"), _scheme_meta("scheme_b")], [], suite_xml
        )
        bsd = BuildSchemeDescription()
        bsd.traverse(module)

        suite_desc = bsd.schemes["test_suite"]
        group = list(suite_desc)[0]
        children = list(group)

        assert len(children) == 1
        assert isinstance(children[0], XMLSubcycle)
        assert children[0].attributes["loop_count"] == "2"

    def test_subcycle_children_are_xml_schemes(self, build_module):
        suite_xml = two_scheme_subcycle_xml("scheme_a", "scheme_b", loop=2)
        module = build_module(
            [_scheme_meta("scheme_a"), _scheme_meta("scheme_b")], [], suite_xml
        )
        bsd = BuildSchemeDescription()
        bsd.traverse(module)

        suite_desc = bsd.schemes["test_suite"]
        group = list(suite_desc)[0]
        subcycle = list(group)[0]
        scheme_names = [s.attributes["name"] for s in subcycle]

        assert scheme_names == ["scheme_a", "scheme_b"]

    def test_mixed_group_preserves_order(self, build_module):
        suite_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="1.0">
  <group name="physics">
    <scheme>pre_scheme</scheme>
    <subcycle loop="2">
      <scheme>fast_scheme</scheme>
    </subcycle>
    <scheme>post_scheme</scheme>
  </group>
</suite>
"""
        metas = [_scheme_meta(n) for n in ("pre_scheme", "fast_scheme", "post_scheme")]
        module = build_module(metas, [], suite_xml)
        bsd = BuildSchemeDescription()
        bsd.traverse(module)

        from xdsl_ccpp.transforms.util.ccpp_descriptors import XMLScheme
        suite_desc = bsd.schemes["test_suite"]
        group = list(suite_desc)[0]
        children = list(group)

        assert len(children) == 3
        assert isinstance(children[0], XMLScheme)
        assert children[0].attributes["name"] == "pre_scheme"
        assert isinstance(children[1], XMLSubcycle)
        assert isinstance(children[2], XMLScheme)
        assert children[2].attributes["name"] == "post_scheme"

    def test_nested_subcycle_op_is_rejected(self):
        """Defense in depth: even if a nested SubcycleOp reached the IR by
        some route other than the (now-blocking) XML parser, reconstruction
        must raise rather than silently drop the nested schemes."""
        inner = SubcycleOp(loop_count=2, body=[SchemeOp("inner_scheme")])
        outer = SubcycleOp(loop_count=3, body=[inner])
        group_op = GroupOp("physics", body=[outer])

        bsd = BuildSchemeDescription()
        with pytest.raises(ValueError, match="Nested ccpp.subcycle ops are not supported"):
            bsd.traverse(group_op)


# ── getSchemeNames / getCallSequence ─────────────────────────────────────────

class TestGetSchemeNames:
    """getSchemeNames must flatten through XMLSubcycle nodes."""

    def _get_suite_desc(self, build_module, suite_xml, metas):
        module = build_module(metas, [], suite_xml)
        bsd = BuildSchemeDescription()
        bsd.traverse(module)
        return bsd.schemes["test_suite"]

    def _gss(self):
        """Return a GenerateSuiteSubroutine instance bypassing __init__."""
        return object.__new__(GenerateSuiteSubroutine)

    def test_flat_names_from_subcycle(self, build_module):
        suite_xml = two_scheme_subcycle_xml("scheme_a", "scheme_b", loop=2)
        suite_desc = self._get_suite_desc(
            build_module, suite_xml,
            [_scheme_meta("scheme_a"), _scheme_meta("scheme_b")],
        )
        names = [n for n, _ in self._gss().getSchemeNames(suite_desc)]
        assert names == ["scheme_a", "scheme_b"]

    def test_call_sequence_has_subcycle_item(self, build_module):
        suite_xml = two_scheme_subcycle_xml("scheme_a", "scheme_b", loop=3)
        suite_desc = self._get_suite_desc(
            build_module, suite_xml,
            [_scheme_meta("scheme_a"), _scheme_meta("scheme_b")],
        )
        seq = self._gss().getCallSequence(suite_desc)
        assert len(seq) == 1
        kind, loop_count, is_literal, schemes = seq[0]
        assert kind == "subcycle"
        assert loop_count == "3"
        assert is_literal is True
        assert [n for n, _ in schemes] == ["scheme_a", "scheme_b"]

    def test_call_sequence_mixed(self, build_module):
        suite_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="1.0">
  <group name="physics">
    <scheme>pre_scheme</scheme>
    <subcycle loop="2">
      <scheme>fast_scheme</scheme>
    </subcycle>
    <scheme>post_scheme</scheme>
  </group>
</suite>
"""
        metas = [_scheme_meta(n) for n in ("pre_scheme", "fast_scheme", "post_scheme")]
        suite_desc = self._get_suite_desc(build_module, suite_xml, metas)
        seq = self._gss().getCallSequence(suite_desc)

        assert len(seq) == 3
        assert seq[0][0] == "scheme" and seq[0][1] == "pre_scheme"
        assert seq[1][0] == "subcycle" and seq[1][1] == "2"
        assert seq[2][0] == "scheme" and seq[2][1] == "post_scheme"


# ── ccpp_track_variables integration ─────────────────────────────────────────

class TestTrackVariablesWithSubcycle:
    """track() should find variables inside subcycled schemes."""

    def test_variable_found_inside_subcycle(self, build_module):
        scheme_a = _scheme_meta("scheme_a", """\
[ ps ]
  standard_name = surface_air_pressure
  type = real
  kind = kind_phys
  intent = in
  dimensions = (horizontal_loop_extent)
  units = Pa
""")
        suite_xml = two_scheme_subcycle_xml("scheme_a", "scheme_b", loop=2)
        module = build_module(
            [scheme_a, _scheme_meta("scheme_b")], [], suite_xml
        )
        results, _ = track(module, "surface_air_pressure")

        assert len(results) == 1
        assert results[0].entry_point == "scheme_a_run"

    def test_variable_found_in_both_subcycle_schemes(self, build_module):
        pressure_arg = """\
[ ps ]
  standard_name = surface_air_pressure
  type = real
  kind = kind_phys
  intent = in
  dimensions = (horizontal_loop_extent)
  units = Pa
"""
        suite_xml = two_scheme_subcycle_xml("scheme_a", "scheme_b", loop=2)
        module = build_module(
            [_scheme_meta("scheme_a", pressure_arg),
             _scheme_meta("scheme_b", pressure_arg)],
            [],
            suite_xml,
        )
        results, _ = track(module, "surface_air_pressure")
        entry_points = [r.entry_point for r in results]

        assert "scheme_a_run" in entry_points
        assert "scheme_b_run" in entry_points
