"""Unit tests for rejecting unhandled suite-XML elements.

XMLGroup/XMLSubcycle/XMLSuite used to skip any child element they did not
recognize, so a <process_split>, <time_split> or <subcol> block -- or a
typo such as <schme> -- vanished from the generated caps together with every
scheme inside it, without a message. capgen-v1's suite_v1_0.xsd still
accepts <time_split>/<process_split>, so such a suite passes schema
validation. Each unhandled element now raises ValueError.
"""

import xml.etree.ElementTree as ET

import pytest

from xdsl_ccpp.frontend.ccpp_xml import XMLGroup, XMLSubcycle, XMLSuite


def _group(body):
    return ET.fromstring(f'<group name="physics">{body}</group>')


class TestUnsupportedElements:
    @pytest.mark.parametrize("tag", ["time_split", "process_split"])
    def test_split_region_in_group_rejected(self, tag):
        node = _group(f"<{tag}><scheme>a</scheme></{tag}>")
        with pytest.raises(ValueError, match=f"<{tag}> in <group> 'physics' is not supported"):
            XMLGroup(node)

    def test_subcol_in_subcycle_rejected(self):
        node = ET.fromstring(
            '<subcycle loop="2"><subcol gen="g" avg="a"><scheme>a</scheme></subcol></subcycle>'
        )
        with pytest.raises(ValueError, match="<subcol> in <subcycle> is not supported"):
            XMLSubcycle(node)

    def test_rejected_inside_nested_subcycle(self):
        node = _group(
            '<subcycle loop="2"><subcycle loop="3">'
            "<process_split><scheme>a</scheme></process_split>"
            "</subcycle></subcycle>"
        )
        with pytest.raises(ValueError, match="<process_split>"):
            XMLGroup(node)


class TestUnknownElements:
    def test_typo_in_group_rejected(self):
        with pytest.raises(ValueError, match="Unknown element <schme> in <group> 'physics'"):
            XMLGroup(_group("<schme>a</schme>"))

    def test_typo_at_suite_level_names_file(self, tmp_path):
        sdf = tmp_path / "suite_typo.xml"
        sdf.write_text(
            '<suite name="s" version="1.0">'
            '<grup name="physics"><scheme>a</scheme></grup>'
            "</suite>"
        )
        with pytest.raises(ValueError, match=r"Unknown element <grup> in <suite> 's' of suite file '.*suite_typo\.xml'"):
            XMLSuite(str(sdf))

    def test_group_error_names_file(self, tmp_path):
        sdf = tmp_path / "suite_split.xml"
        sdf.write_text(
            '<suite name="s" version="1.0"><group name="physics">'
            "<process_split><scheme>a</scheme></process_split>"
            "</group></suite>"
        )
        with pytest.raises(ValueError, match=r"of suite file '.*suite_split\.xml'"):
            XMLSuite(str(sdf))


class TestSupportedElementsStillParse:
    def test_valid_suite(self, tmp_path):
        sdf = tmp_path / "suite_ok.xml"
        sdf.write_text(
            '<suite name="s" version="2.0"><init>a</init><final>a</final>'
            '<group name="physics"><scheme>a</scheme>'
            '<subcycle loop="2"><scheme>b</scheme><subcycle loop="3"><scheme>c</scheme></subcycle></subcycle>'
            "</group></suite>"
        )
        suite = XMLSuite(str(sdf))
        assert suite.init_scheme == "a" and suite.final_scheme == "a"
        (group,) = suite.children
        assert [type(c).__name__ for c in group.children] == ["XMLScheme", "XMLSubcycle"]
