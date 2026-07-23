"""Unit tests for subcycle support.

Verifies that <subcycle loop="N"> in a suite XML is:
  - parsed into a SubcycleOp in the CCPP IR (frontend)
  - reconstructed into XMLSubcycle by BuildSchemeDescription (transforms)
  - flattened correctly by getSchemeNames / getCallSequence (suite_cap)
  - included in track() results (ccpp_track_variables)

Nested subcycles (a <subcycle> inside another <subcycle>) are a real CCPP
pattern -- see examples/var_compat/var_compatibility_suite.xml (ported from
NCAR ccpp-framework's feature/capgen-v1), which nests three levels deep.
The XML frontend parser, IR-to-descriptor reconstruction, getSchemeNames/
getCallSequence (suite_cap.py), and cap_shared.py's _iter_schemes/
suite_variable_model.py's independent copy all support this recursively now
(TestFrontendParsing / TestBuildSchemeDescription / TestGetSchemeNames
below), including the actual Fortran do-loop codegen
(TestGeneratedFortranLoops below) -- two or more sibling subcycles (nested
or not) sharing the "ccpp_loop_cnt" alloca name_hint used to produce a
duplicate/missing declaration in the generated Fortran; fixed in
print_ftn.py (declaration de-duplication) and suite_cap.py's
_build_call_ops (hoisting every subcycle's alloca to the function's top
level regardless of nesting depth).

The Python suite-authoring DSL (py_api.py's forLoop()) supports nesting too
now -- see TestPythonDSLFrontendNesting below -- via the same recursive
_group_item_to_op, even though nothing in this repo's own examples
exercises this path yet (capgen-v1's var_compat only exercises the XML
path; forLoop() nesting was added for parity, not because a real example
needs it today).
"""

from io import StringIO
from pathlib import Path

from xdsl.utils.hints import isa

from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.dialects.ccpp import GroupOp, SchemeOp, SubcycleOp, SuiteOp
from xdsl_ccpp.frontend.py_api import (
    SchemeDescriptor,
    SubcycleDescriptor,
    _group_item_to_op,
)
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    BuildSchemeDescription,
    XMLSubcycle,
)
from xdsl_ccpp.transforms.suite_cap import GenerateSuiteSubroutine, SuiteCAP
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

    def test_nested_subcycle_is_parsed_recursively(self, build_module):
        """A <subcycle> nested inside another <subcycle> parses into a
        correctly-nested SubcycleOp tree, not a flattened or dropped one.

        Real CCPP suites do this -- see
        examples/var_compat/var_compatibility_suite.xml (ported from NCAR
        ccpp-framework's feature/capgen-v1), which nests three levels deep.
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
        module = build_module(metas, [], suite_xml)
        suite_op = next(op for op in module.body.ops if isa(op, SuiteOp))
        group_op = next(op for op in suite_op.body.ops if isa(op, GroupOp))
        children = list(group_op.body.ops)

        assert len(children) == 1
        outer_op = children[0]
        assert isa(outer_op, SubcycleOp)
        assert outer_op.loop_count.data == "2"
        outer_children = list(outer_op.body.ops)
        assert len(outer_children) == 2
        assert isa(outer_children[0], SchemeOp)
        assert outer_children[0].scheme_name.data == "outer_scheme"
        assert isa(outer_children[1], SubcycleOp)
        inner_op = outer_children[1]
        assert inner_op.loop_count.data == "3"
        inner_children = list(inner_op.body.ops)
        assert len(inner_children) == 1
        assert isa(inner_children[0], SchemeOp)
        assert inner_children[0].scheme_name.data == "inner_scheme"

    def test_real_var_compat_suite_is_parsed(self, build_module):
        """examples/var_compat/var_compatibility_suite.xml is a real suite
        ported from NCAR/ccpp-framework's feature/capgen-v1 branch,
        end-to-end-tests/var_compat -- not a synthetic fixture. Its
        'radiation' group nests <subcycle> three levels deep in one branch
        (a dynamic-count subcycle containing two nested loop="2" subcycles),
        plus two sibling subcycles sharing the same dynamic-count
        standard_name (num_subcycles_for_effr).

        Confirms the real, 3-level-deep structure parses into IR correctly,
        not just that it doesn't raise. Downstream scheme-flattening and
        codegen support for this structure lands in follow-on work (see
        examples/var_compat/README.md) -- this test covers the frontend
        parsing layer only.
        """
        suite_xml_path = (
            Path(__file__).resolve().parents[2]
            / "examples" / "var_compat" / "var_compatibility_suite.xml"
        )
        suite_xml = suite_xml_path.read_text()
        metas = [
            _scheme_meta(n)
            for n in (
                "effr_pre", "effr_calc", "effr_post",
                "effrs_calc", "effr_diag", "rad_lw", "rad_sw",
            )
        ]
        module = build_module(metas, [], suite_xml)
        suite_op = next(op for op in module.body.ops if isa(op, SuiteOp))
        group_op = next(op for op in suite_op.body.ops if isa(op, GroupOp))
        children = list(group_op.body.ops)

        assert len(children) == 5
        first_subcycle, second_subcycle, effr_diag, rad_lw, rad_sw = children
        assert isa(first_subcycle, SubcycleOp)
        assert first_subcycle.loop_count.data == "num_subcycles_for_effr"
        assert not bool(first_subcycle.is_literal.value.data)

        first_children = list(first_subcycle.body.ops)
        assert len(first_children) == 3
        effr_pre, mid_subcycle, effr_post = first_children
        assert isa(effr_pre, SchemeOp) and effr_pre.scheme_name.data == "effr_pre"
        assert isa(effr_post, SchemeOp) and effr_post.scheme_name.data == "effr_post"
        assert isa(mid_subcycle, SubcycleOp)
        assert mid_subcycle.loop_count.data == "2"

        mid_children = list(mid_subcycle.body.ops)
        assert len(mid_children) == 1
        inner_subcycle = mid_children[0]
        assert isa(inner_subcycle, SubcycleOp)
        assert inner_subcycle.loop_count.data == "2"

        inner_children = list(inner_subcycle.body.ops)
        assert len(inner_children) == 1
        assert isa(inner_children[0], SchemeOp)
        assert inner_children[0].scheme_name.data == "effr_calc"

        assert isa(second_subcycle, SubcycleOp)
        assert second_subcycle.loop_count.data == "num_subcycles_for_effr"
        second_children = list(second_subcycle.body.ops)
        assert len(second_children) == 1
        assert isa(second_children[0], SchemeOp)
        assert second_children[0].scheme_name.data == "effrs_calc"

        assert isa(effr_diag, SchemeOp) and effr_diag.scheme_name.data == "effr_diag"
        assert isa(rad_lw, SchemeOp) and rad_lw.scheme_name.data == "rad_lw"
        assert isa(rad_sw, SchemeOp) and rad_sw.scheme_name.data == "rad_sw"


# ── Python DSL frontend ────────────────────────────────────────────────────────

class TestPythonDSLFrontendNesting:
    """forLoop() bypasses the XML parser entirely (py_api.py builds SubcycleOp
    directly), so it needs its own recursive handling -- mirrors the XML
    frontend's own nested-<subcycle> support (ccpp_xml.py's XMLSubcycle)."""

    def test_nested_forloop_is_parsed_recursively(self):
        """A forLoop() result nested inside another forLoop()'s schemes list
        converts into a correctly-nested SubcycleOp tree, not a flattened
        one or a raised error."""
        inner_scheme = SchemeDescriptor("inner_scheme", {})
        inner = SubcycleDescriptor(2, [inner_scheme])
        outer_scheme = SchemeDescriptor("outer_scheme", {})
        outer = SubcycleDescriptor(3, [outer_scheme, inner])

        seen_schemes: dict = {}
        op = _group_item_to_op(outer, seen_schemes)

        assert isa(op, SubcycleOp)
        assert op.loop_count.data == "3"
        outer_children = list(op.body.ops)
        assert len(outer_children) == 2
        assert isa(outer_children[0], SchemeOp)
        assert outer_children[0].scheme_name.data == "outer_scheme"
        assert isa(outer_children[1], SubcycleOp)
        inner_op = outer_children[1]
        assert inner_op.loop_count.data == "2"
        inner_children = list(inner_op.body.ops)
        assert len(inner_children) == 1
        assert isa(inner_children[0], SchemeOp)
        assert inner_children[0].scheme_name.data == "inner_scheme"

        # Both schemes, at any nesting depth, must be registered.
        assert set(seen_schemes) == {"outer_scheme", "inner_scheme"}

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

    def test_nested_subcycle_op_is_reconstructed_recursively(self):
        """A nested SubcycleOp reconstructs into a correctly-nested
        XMLSubcycle tree, not a flattened or dropped one -- mirrors
        TestFrontendParsing.test_nested_subcycle_is_parsed_recursively at
        the descriptor-reconstruction layer."""
        inner = SubcycleOp(loop_count=2, body=[SchemeOp("inner_scheme")])
        outer = SubcycleOp(loop_count=3, body=[inner])
        group_op = GroupOp("physics", body=[outer])

        bsd = BuildSchemeDescription()
        bsd.traverse(group_op)

        outer_desc = list(bsd.current_group)[0]
        assert isinstance(outer_desc, XMLSubcycle)
        assert outer_desc.attributes["loop_count"] == "3"
        outer_children = list(outer_desc)
        assert len(outer_children) == 1
        inner_desc = outer_children[0]
        assert isinstance(inner_desc, XMLSubcycle)
        assert inner_desc.attributes["loop_count"] == "2"
        inner_children = list(inner_desc)
        assert len(inner_children) == 1
        assert inner_children[0].attributes["name"] == "inner_scheme"


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

    def test_flat_names_from_nested_subcycle(self, build_module):
        """getSchemeNames (via cap_shared._iter_schemes) must flatten through
        a subcycle nested inside another subcycle, not just one level."""
        suite_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="1.0">
  <group name="physics">
    <subcycle loop="3">
      <scheme>outer_scheme</scheme>
      <subcycle loop="2">
        <scheme>inner_scheme</scheme>
      </subcycle>
    </subcycle>
  </group>
</suite>
"""
        metas = [_scheme_meta(n) for n in ("outer_scheme", "inner_scheme")]
        suite_desc = self._get_suite_desc(build_module, suite_xml, metas)
        names = [n for n, _ in self._gss().getSchemeNames(suite_desc)]
        assert names == ["outer_scheme", "inner_scheme"]

    def test_call_sequence_has_subcycle_item(self, build_module):
        suite_xml = two_scheme_subcycle_xml("scheme_a", "scheme_b", loop=3)
        suite_desc = self._get_suite_desc(
            build_module, suite_xml,
            [_scheme_meta("scheme_a"), _scheme_meta("scheme_b")],
        )
        seq = self._gss().getCallSequence(suite_desc)
        assert len(seq) == 1
        kind, loop_count, is_literal, items = seq[0]
        assert kind == "subcycle"
        assert loop_count == "3"
        assert is_literal is True
        assert items == [
            ("scheme", "scheme_a", {}),
            ("scheme", "scheme_b", {}),
        ]

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

    def test_call_sequence_nested_subcycle_item(self, build_module):
        """A subcycle's own item list uses the same recursive shape as the
        top-level call sequence, so a nested subcycle appears as a nested
        ('subcycle', ...) item rather than a flat scheme list -- real
        pattern, see examples/var_compat/var_compatibility_suite.xml
        (ported from NCAR ccpp-framework's feature/capgen-v1), which nests
        three levels deep in one branch."""
        suite_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="1.0">
  <group name="physics">
    <subcycle loop="3">
      <scheme>outer_scheme</scheme>
      <subcycle loop="2">
        <scheme>inner_scheme</scheme>
      </subcycle>
    </subcycle>
  </group>
</suite>
"""
        metas = [_scheme_meta(n) for n in ("outer_scheme", "inner_scheme")]
        suite_desc = self._get_suite_desc(build_module, suite_xml, metas)
        seq = self._gss().getCallSequence(suite_desc)

        assert len(seq) == 1
        kind, loop_count, is_literal, items = seq[0]
        assert kind == "subcycle"
        assert loop_count == "3"
        assert is_literal is True
        assert len(items) == 2
        assert items[0] == ("scheme", "outer_scheme", {})
        assert items[1][0] == "subcycle"
        assert items[1][1] == "2"
        assert items[1][2] is True
        assert items[1][3] == [("scheme", "inner_scheme", {})]


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


# ── Generated Fortran do-loop codegen ─────────────────────────────────────────

class TestGeneratedFortranLoops:
    """suite_cap.py's _build_call_ops -> print_ftn.py: every subcycle's own
    loop-count variable must be declared exactly once and referenced
    consistently, regardless of nesting depth or how many sibling subcycles
    a suite has.

    Two or more sibling subcycles (nested or not) each allocate their own
    loop-count variable sharing the "ccpp_loop_cnt" name_hint. Before the
    fix: print_ftn.py's declaration-printing loop bypassed the same
    _get_variable_name_for de-duplication its own do-loop-body printing
    already used, so two flat sibling subcycles produced a duplicate
    "integer :: ccpp_loop_cnt" declaration (invalid Fortran); separately,
    suite_cap.py embedded a nested subcycle's own alloca inside its parent
    SubcycleLoopOp's body region, which print_ftn.py's declaration scan
    (top-level-only, not recursive) never finds, so its loop variable was
    referenced in the generated code but never declared at all (also
    invalid Fortran). Both fixed; this test would have caught either.
    """

    def _fortran_output(self, run_host_match, ccpp_context, scheme_metas, suite_xml) -> str:
        module = run_host_match(scheme_metas=scheme_metas, host_metas=[], suite_xml=suite_xml)
        ArgOwnershipPass().apply(ccpp_context, module)
        SuiteCAP().apply(ccpp_context, module)
        out = StringIO()
        print_to_ftn(module, out)
        return out.getvalue()

    def _fn_body(self, fortran: str, fn_name: str) -> str:
        return fortran.split(f"subroutine {fn_name}")[1].split(f"end subroutine {fn_name}")[0]

    def _declared_integers(self, fn_body: str) -> list[str]:
        return [
            line.strip().split("::")[1].strip()
            for line in fn_body.splitlines()
            if line.strip().startswith("integer ::")
        ]

    def test_two_sibling_subcycles_declare_distinct_loop_vars_once_each(
        self, run_host_match, ccpp_context
    ):
        suite_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="1.0">
  <group name="physics">
    <subcycle loop="2">
      <scheme>scheme_a</scheme>
    </subcycle>
    <subcycle loop="3">
      <scheme>scheme_b</scheme>
    </subcycle>
  </group>
</suite>
"""
        metas = [_scheme_meta(n) for n in ("scheme_a", "scheme_b")]
        fortran = self._fortran_output(run_host_match, ccpp_context, metas, suite_xml)
        fn = self._fn_body(fortran, "test_suite_suite_physics")

        declared = self._declared_integers(fn)
        assert len(declared) == len(set(declared)), (
            f"duplicate loop-variable declaration(s) in: {declared}"
        )
        assert len(declared) == 2

        referenced = {
            line.strip().split()[1]
            for line in fn.splitlines()
            if line.strip().startswith("do ccpp_loop_cnt")
        }
        assert referenced == set(declared), (
            "every 'do <var> = ...' loop variable must have a matching "
            f"declaration -- declared: {declared}, referenced: {sorted(referenced)}"
        )

    def test_nested_subcycle_loop_var_is_declared(self, run_host_match, ccpp_context):
        """The nested subcycle's own alloca must be hoisted to the function's
        top level (declared), not left embedded inside its parent
        SubcycleLoopOp's body where print_ftn.py's declaration scan can't
        find it."""
        suite_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="1.0">
  <group name="physics">
    <subcycle loop="2">
      <scheme>outer_scheme</scheme>
      <subcycle loop="2">
        <scheme>inner_scheme</scheme>
      </subcycle>
    </subcycle>
    <subcycle loop="3">
      <scheme>scheme_b</scheme>
    </subcycle>
  </group>
</suite>
"""
        metas = [_scheme_meta(n) for n in ("outer_scheme", "inner_scheme", "scheme_b")]
        fortran = self._fortran_output(run_host_match, ccpp_context, metas, suite_xml)
        fn = self._fn_body(fortran, "test_suite_suite_physics")

        declared = self._declared_integers(fn)
        assert len(declared) == len(set(declared)), (
            f"duplicate loop-variable declaration(s) in: {declared}"
        )
        assert len(declared) == 3

        referenced = {
            line.strip().split()[1]
            for line in fn.splitlines()
            if line.strip().startswith("do ccpp_loop_cnt")
        }
        assert referenced == set(declared), (
            "every 'do <var> = ...' loop variable must have a matching "
            f"declaration -- declared: {declared}, referenced: {sorted(referenced)}"
        )
