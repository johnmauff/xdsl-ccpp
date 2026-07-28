"""Unit tests for whitespace tolerance in the frontend suite-XML/CLI parsers.

Found by auditing ccpp_xml.py after fixing the ".meta" argument-bracket
spacing bug (see ccpp_cap_refactor_plan.md and
tests/unit/test_meta_parser_bracket_spacing.py): the same class of bug --
user-authored text taken at face value without stripping, relying entirely
on everyone happening to format things the same tight way -- turned up in
three more spots. None are currently live failures (every suite XML/CLI
invocation in this repo happens to already avoid the incidental whitespace),
but all three would previously have failed silently or confusingly:

1. XMLScheme.scheme_name (a suite XML <scheme> element's text content) was
   used unstripped. Every suite XML in this repo writes the name tight
   against the tags on one line, but XML preserves indentation whitespace
   verbatim in element text -- an indented "<scheme>\\n  x\\n</scheme>"
   would have produced a scheme_name that never matches anything in scheme
   metadata, with no clear error pointing at whitespace as the cause.

2. XMLSubcycle's own `loop` attribute was read unstripped. Attribute values
   rarely pick up incidental whitespace (nobody indents inside a quoted
   attribute), but the same bug applies if one ever did.

3. Both ccpp_xml.py's ccppXML.build_options_db_from_args and
   ccpp_dsl.py's ccppMain.build_options_db_from_args split
   --scheme-files/--host-files/--suites on comma with no per-entry
   stripping -- "a.meta, b.meta" would silently produce a path with a
   leading space, failing to open with a confusing error instead of being
   tolerated the way most CLI tools handle incidental whitespace.

All three fixed by adding a .strip() at the point the raw text is taken.
"""

import xml.etree.ElementTree as ET

from xdsl_ccpp.frontend.ccpp_xml import XMLScheme, XMLSubcycle, ccppXML
from xdsl_ccpp.tools.ccpp_dsl import ccppMain


class TestSchemeNameStripped:
    def test_indented_multiline_scheme_text_is_stripped(self):
        node = ET.fromstring("<scheme>\n      effr_calc\n    </scheme>")
        scheme = XMLScheme(node)
        assert scheme.scheme_name == "effr_calc"

    def test_tight_single_line_scheme_text_unaffected(self):
        node = ET.fromstring("<scheme>effr_calc</scheme>")
        scheme = XMLScheme(node)
        assert scheme.scheme_name == "effr_calc"


class TestSubcycleLoopAttributeStripped:
    def test_literal_loop_count_with_padding_whitespace(self):
        node = ET.fromstring('<subcycle loop=" 2 "></subcycle>')
        subcycle = XMLSubcycle(node)
        assert subcycle.is_literal is True
        assert subcycle.loop_count == "2"

    def test_dynamic_loop_count_std_name_with_padding_whitespace(self):
        node = ET.fromstring('<subcycle loop=" num_subcycles_for_effr "></subcycle>')
        subcycle = XMLSubcycle(node)
        assert subcycle.is_literal is False
        assert subcycle.loop_count == "num_subcycles_for_effr"


class TestCommaSeparatedCliArgsStripped:
    def test_ccpp_xml_frontend_strips_entries_after_comma(self):
        frontend = ccppXML()
        parser = frontend.initialise_argument_parser()
        args = parser.parse_args([
            "--scheme-files", "a.meta, b.meta",
            "--host-files", "c.meta ,d.meta",
            "--suites", "e.xml, f.xml",
        ])
        options_db = frontend.build_options_db_from_args(args)
        assert options_db["scheme_files"] == ["a.meta", "b.meta"]
        assert options_db["host_files"] == ["c.meta", "d.meta"]
        assert options_db["suites"] == ["e.xml", "f.xml"]

    def test_ccpp_dsl_tool_strips_entries_after_comma(self):
        # ccppMain.build_options_db_from_args also validates that every
        # input file actually exists (os.path.exists), right after the
        # comma-split -- use real, existing files rather than made-up
        # paths, so a leading-space entry fails *that* check (proving the
        # split still produced a bad path) rather than being masked by an
        # earlier, unrelated failure.
        main = ccppMain()
        parser = main.initialise_argument_parser()
        args = parser.parse_args([
            "--suites", "examples/helloworld/hello_world_suite.xml",
            "--scheme-files",
            "examples/helloworld/hello_scheme.meta, examples/helloworld/temp_adjust.meta",
            "--host-files",
            "examples/helloworld/hello_world_host.meta"
            " ,examples/helloworld/hello_world_mod.meta",
        ])
        options_db = main.build_options_db_from_args(args)
        assert options_db["scheme_files"] == [
            "examples/helloworld/hello_scheme.meta",
            "examples/helloworld/temp_adjust.meta",
        ]
        assert options_db["host_files"] == [
            "examples/helloworld/hello_world_host.meta",
            "examples/helloworld/hello_world_mod.meta",
        ]
