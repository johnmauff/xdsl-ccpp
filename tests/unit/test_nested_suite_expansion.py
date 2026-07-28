"""Unit tests for XMLSuite's <nested_suite> cross-file expansion.

Backlog item: `nested_suite` in ccpp_cap_refactor_plan.md. Ported from
reading NCAR ccpp-framework's real feature/capgen-v1 source directly
(capgen/metadata/parse_tools/xml_tools.py's expand_nested_suites /
replace_nested_suite / load_suite_by_name), not guessed from the SDF v2.0
schema alone -- confirmed against the real end-to-end-tests/nested_suite
example (main_suite.xml/radiation2_suite.xml/radiation3_suite.xml/
radiation3_subsuite.xml/radiation4_suite.xml), which this test's own
fixtures mirror structurally at a smaller scale.

A <nested_suite name=... group=... file=.../> splices groups/schemes from a
*different* suite XML file into this one, either at suite level or inside a
group, resolved and expanded as a pure XML-tree preprocessing pass before
any XMLGroup/XMLScheme/XMLSubcycle object is built -- so nothing downstream
needs to know cross-file composition was ever involved.
"""

import pytest

from xdsl_ccpp.frontend.ccpp_xml import XMLScheme, XMLSuite


def _scheme_names(node) -> list:
    """Recursively collect XMLScheme names from a group/subcycle's children."""
    names = []
    for child in node:
        if isinstance(child, XMLScheme):
            names.append(child.scheme_name)
        else:
            names.extend(_scheme_names(child))
    return names


class TestSuiteLevelSpliceWithGroupWrapsFresh:
    """A <nested_suite> declared directly under <suite> (not inside a
    <group>) that also names group= gets its referenced group's own
    children re-wrapped in a fresh <group name=group_attr> -- mirrors
    main_suite.xml's own radiation4_suite reference exactly."""

    def test_referenced_group_becomes_a_new_top_level_group(self, tmp_path):
        (tmp_path / "other.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<suite name="other_suite" version="2.0">\n'
            '  <group name="g2">\n'
            '    <scheme>scheme_b</scheme>\n'
            '  </group>\n'
            '</suite>\n'
        )
        (tmp_path / "main.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<suite name="main" version="2.0">\n'
            '  <nested_suite name="other_suite" group="g2" file="other.xml"/>\n'
            '</suite>\n'
        )
        suite = XMLSuite(str(tmp_path / "main.xml"))
        assert [g.attributes.get("name") for g in suite.children] == ["g2"]
        assert _scheme_names(suite.children[0]) == ["scheme_b"]


class TestGroupLevelSpliceDoesNotWrap:
    """A <nested_suite> declared inside a <group> splices the referenced
    group's own children in directly, unwrapped -- mirrors main_suite.xml's
    own radiation2_suite reference (inside <group name="radiation1">)."""

    def test_referenced_schemes_merge_into_the_existing_group(self, tmp_path):
        (tmp_path / "other.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<suite name="other_suite" version="2.0">\n'
            '  <group name="g2">\n'
            '    <scheme>scheme_b</scheme>\n'
            '  </group>\n'
            '</suite>\n'
        )
        (tmp_path / "main.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<suite name="main" version="2.0">\n'
            '  <group name="g1">\n'
            '    <scheme>scheme_a</scheme>\n'
            '    <nested_suite name="other_suite" group="g2" file="other.xml"/>\n'
            '  </group>\n'
            '</suite>\n'
        )
        suite = XMLSuite(str(tmp_path / "main.xml"))
        # No new group -- still exactly one, and it now has both schemes.
        assert [g.attributes.get("name") for g in suite.children] == ["g1"]
        assert _scheme_names(suite.children[0]) == ["scheme_a", "scheme_b"]


class TestSuiteLevelSpliceWithGroupOmitted:
    """A suite-level <nested_suite> with no group= splices in the
    referenced suite's own top-level children as-is (its own <group> tags
    carry through unwrapped) -- mirrors main_suite.xml's own radiation3_suite
    reference. Using two groups in the referenced file proves this pulls in
    everything, not just one arbitrarily-chosen group."""

    def test_all_of_the_referenced_suites_groups_are_spliced_in(self, tmp_path):
        (tmp_path / "other.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<suite name="other_suite" version="2.0">\n'
            '  <group name="g2">\n'
            '    <scheme>scheme_b</scheme>\n'
            '  </group>\n'
            '  <group name="g3">\n'
            '    <scheme>scheme_c</scheme>\n'
            '  </group>\n'
            '</suite>\n'
        )
        (tmp_path / "main.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<suite name="main" version="2.0">\n'
            '  <nested_suite name="other_suite" file="other.xml"/>\n'
            '</suite>\n'
        )
        suite = XMLSuite(str(tmp_path / "main.xml"))
        assert [g.attributes.get("name") for g in suite.children] == ["g2", "g3"]


class TestTwoLevelRecursiveNesting:
    """A referenced file's own group may itself contain a <nested_suite> --
    mirrors radiation3_suite -> radiation3_subsuite (2 levels deep in the
    real upstream example). The inner reference is group-level (parent is a
    <group>, not <suite>), so it does NOT get fresh-group-wrapped even
    though it names group=, matching the wrap rule precisely."""

    def test_inner_reference_resolves_after_outer_splice(self, tmp_path):
        (tmp_path / "suite_y.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<suite name="suite_y" version="2.0">\n'
            '  <group name="gy">\n'
            '    <scheme>scheme_y</scheme>\n'
            '  </group>\n'
            '</suite>\n'
        )
        (tmp_path / "suite_x.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<suite name="suite_x" version="2.0">\n'
            '  <group name="gx">\n'
            '    <nested_suite name="suite_y" group="gy" file="suite_y.xml"/>\n'
            '  </group>\n'
            '</suite>\n'
        )
        (tmp_path / "main.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<suite name="main" version="2.0">\n'
            '  <nested_suite name="suite_x" file="suite_x.xml"/>\n'
            '</suite>\n'
        )
        suite = XMLSuite(str(tmp_path / "main.xml"))
        assert [g.attributes.get("name") for g in suite.children] == ["gx"]
        assert _scheme_names(suite.children[0]) == ["scheme_y"]


class TestSuiteNameMismatchRejected:
    """load_suite_by_name validates the referenced file's own <suite name=...>
    actually matches what was asked for -- not just that the file= path
    opened successfully."""

    def test_raises_clear_error(self, tmp_path):
        (tmp_path / "other.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<suite name="something_else" version="2.0">\n'
            '  <group name="g2"><scheme>scheme_b</scheme></group>\n'
            '</suite>\n'
        )
        (tmp_path / "main.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<suite name="main" version="2.0">\n'
            '  <nested_suite name="other_suite" file="other.xml"/>\n'
            '</suite>\n'
        )
        with pytest.raises(ValueError, match="other_suite.*not found"):
            XMLSuite(str(tmp_path / "main.xml"))


class TestMutualReferenceCycleRejected:
    """Two files referencing each other must not loop forever -- capped at
    _MAX_NESTED_SUITE_ITERATIONS re-scans, matching capgen-v1's own
    max_iterations=10 safety cap."""

    def test_raises_clear_error(self, tmp_path):
        (tmp_path / "a.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<suite name="suite_a" version="2.0">\n'
            '  <nested_suite name="suite_b" file="b.xml"/>\n'
            '</suite>\n'
        )
        (tmp_path / "b.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<suite name="suite_b" version="2.0">\n'
            '  <nested_suite name="suite_a" file="a.xml"/>\n'
            '</suite>\n'
        )
        with pytest.raises(ValueError, match="[Ee]xceeded max iterations"):
            XMLSuite(str(tmp_path / "a.xml"))
