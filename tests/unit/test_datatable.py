"""Unit tests for datatable.xml and HTML documentation generation.

Tests cover:
  - build_datatable: IR walking, XML structure, var_dictionary population
  - write_datatable: file written, valid XML
  - write_html: HTML file per entry point, expected columns present
  - _phase_for_entry: lifecycle phase detection
"""

import io
import os
from xml.etree import ElementTree as ET

import pytest

from xdsl.printer import Printer

from xdsl_ccpp.tools.ccpp_datatable import (
    _phase_for_entry,
    build_datatable,
    write_datatable,
    write_html,
)

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml

pytestmark = pytest.mark.usefixtures("legacy_mode")


# ── helpers ───────────────────────────────────────────────────────────────────

def _scheme_meta(name: str, phase: str = "run", extra_args: str = "") -> str:
    return f"""\
[ccpp-table-properties]
  name = {name}
  type = scheme
[ccpp-arg-table]
  name = {name}_{phase}
  type = scheme
{extra_args}
{CCPP_MANDATORY_ARGS}
"""


def _scheme_meta_with_var(name: str) -> str:
    return f"""\
[ccpp-table-properties]
  name = {name}
  type = scheme
[ccpp-arg-table]
  name = {name}_run
  type = scheme
[ ncols ]
  standard_name = horizontal_loop_extent
  long_name = horizontal loop extent
  units = count
  dimensions = ()
  type = integer
  intent = in
{CCPP_MANDATORY_ARGS}
"""


def _module_to_mlir(module) -> str:
    buf = io.StringIO()
    Printer(stream=buf).print_op(module)
    return buf.getvalue()


def _scheme_meta_with_dependencies(name: str, dependencies: str, phase: str = "run") -> str:
    """A scheme .meta with a `dependencies = ...` table-properties entry
    (task #6 Tier 1's already-IR-forwarded attribute) -- used to test
    _collect_dependencies()'s own reference filter (capgen_v1_parity_
    backlog.md Stage 8b/task #75), not the argument-table shape.
    """
    return f"""\
[ccpp-table-properties]
  name = {name}
  type = scheme
  dependencies = {dependencies}
[ccpp-arg-table]
  name = {name}_{phase}
  type = scheme
{CCPP_MANDATORY_ARGS}
"""


# ── Phase detection ───────────────────────────────────────────────────────────

class TestPhaseDetection:
    def test_run_suffix(self):
        assert _phase_for_entry("my_scheme_run", "my_scheme") == "run"

    def test_init_suffix(self):
        assert _phase_for_entry("my_scheme_init", "my_scheme") == "init"

    def test_finalize_suffix(self):
        assert _phase_for_entry("my_scheme_finalize", "my_scheme") == "finalize"

    def test_timestep_final_suffix(self):
        assert _phase_for_entry("my_scheme_timestep_final", "my_scheme") == "timestep_final"

    def test_case_insensitive(self):
        assert _phase_for_entry("My_Scheme_Run", "my_scheme") == "run"

    def test_fallback_strips_prefix(self):
        assert _phase_for_entry("my_scheme_custom", "my_scheme") == "custom"


# ── build_datatable ───────────────────────────────────────────────────────────

class TestBuildDatatable:
    def test_returns_element(self, build_module):
        suite_xml = minimal_suite_xml("simple_scheme")
        module = build_module([_scheme_meta("simple_scheme")], [], suite_xml)
        mlir_text = _module_to_mlir(module)
        root = build_datatable(mlir_text, [], host_name="test_host")
        assert root.tag == "datatable"
        assert root.get("host_name") == "test_host"

    def test_ccpp_files_section_present(self, build_module):
        module = build_module([_scheme_meta("s1")], [], None)
        mlir_text = _module_to_mlir(module)
        root = build_datatable(mlir_text, ["caps/s1_cap.F90", "caps/ccpp_kinds.F90"])
        files = [el.get("path") for el in root.findall("./ccpp_files/file")]
        assert "caps/s1_cap.F90" in files
        assert "caps/ccpp_kinds.F90" in files

    def test_schemes_section_contains_entry_point(self, build_module):
        module = build_module([_scheme_meta("alpha")], [], None)
        mlir_text = _module_to_mlir(module)
        root = build_datatable(mlir_text, [])
        schemes = root.findall("./schemes/scheme")
        names = [s.get("name") for s in schemes]
        assert "alpha" in names

    def test_entry_point_phase_label(self, build_module):
        module = build_module([_scheme_meta("alpha", phase="run")], [], None)
        mlir_text = _module_to_mlir(module)
        root = build_datatable(mlir_text, [])
        ep = root.find("./schemes/scheme[@name='alpha']/entry_point")
        assert ep is not None
        assert ep.get("phase") == "run"

    def test_api_section_contains_suite(self, build_module):
        suite_xml = minimal_suite_xml("beta_scheme")
        module = build_module([_scheme_meta("beta_scheme")], [], suite_xml)
        mlir_text = _module_to_mlir(module)
        root = build_datatable(mlir_text, [])
        suites = root.findall("./api/suite")
        assert len(suites) >= 1
        # At least one suite contains a group with beta_scheme
        scheme_names = [el.get("name") for el in root.findall("./api/suite/group/scheme")]
        assert "beta_scheme" in scheme_names

    def test_var_dictionary_populated(self, build_module):
        module = build_module([_scheme_meta_with_var("gamma")], [], None)
        mlir_text = _module_to_mlir(module)
        root = build_datatable(mlir_text, [])
        dicts = root.findall("./var_dictionaries/var_dictionary[@source='gamma_run']")
        assert len(dicts) == 1
        vars_ = dicts[0].findall("variable")
        std_names = [v.get("standard_name") for v in vars_]
        assert "horizontal_loop_extent" in std_names

    def test_var_dictionary_mandatory_args_included(self, build_module):
        module = build_module([_scheme_meta("delta")], [], None)
        mlir_text = _module_to_mlir(module)
        root = build_datatable(mlir_text, [])
        dicts = root.findall("./var_dictionaries/var_dictionary[@source='delta_run']")
        assert len(dicts) == 1
        std_names = [v.get("standard_name") for v in dicts[0].findall("variable")]
        assert "ccpp_error_message" in std_names
        assert "ccpp_error_code" in std_names

    def test_multiple_schemes_no_duplicates(self, build_module):
        module = build_module([_scheme_meta("s1"), _scheme_meta("s2")], [], None)
        mlir_text = _module_to_mlir(module)
        root = build_datatable(mlir_text, [])
        scheme_names = [s.get("name") for s in root.findall("./schemes/scheme")]
        assert len(scheme_names) == len(set(scheme_names)), "Duplicate scheme entries found"


# ── capgen_files / dependencies (task #75, capgen_v1_parity_backlog.md) ────────
# Real capgen-v1's own vendored ccpp_datafile.py reads these two sections
# directly, unmodified (confirmed via cam_autogen.py's DatatableReport
# ("utility_files")/DatatableReport("dependencies") calls) -- these tests
# assert on the exact schema real capgen-v1 expects (element names,
# nesting), not just "something got written".

class TestCapgenFilesSection:
    def test_utilities_contains_generated_kinds_file(self, build_module):
        module = build_module([_scheme_meta("s1")], [], None)
        mlir_text = _module_to_mlir(module)
        root = build_datatable(
            mlir_text, ["caps/s1_cap.F90", "caps/ccpp_kinds.F90"]
        )
        utility_paths = [
            el.text for el in root.findall("./capgen_files/utilities/file")
        ]
        assert "caps/ccpp_kinds.F90" in utility_paths
        # Only the generated kinds file, not every cap -- s1_cap.F90 is a
        # suite cap, not a utility.
        assert "caps/s1_cap.F90" not in utility_paths

    def test_utilities_contains_vendored_framework_files(self, build_module):
        module = build_module([_scheme_meta("s1")], [], None)
        mlir_text = _module_to_mlir(module)
        root = build_datatable(mlir_text, [])
        utility_paths = [
            el.text for el in root.findall("./capgen_files/utilities/file")
        ]
        basenames = {os.path.basename(p) for p in utility_paths}
        assert "ccpp_constituent_prop_mod.F90" in basenames
        assert "ccpp_scheme_utils.F90" in basenames

    def test_host_files_and_suite_files_sections_present(self, build_module):
        module = build_module([_scheme_meta("s1")], [], None)
        mlir_text = _module_to_mlir(module)
        root = build_datatable(mlir_text, [])
        # Empty-but-present (capgen_v1_parity_backlog.md's own rationale --
        # real capgen-v1 always writes these, even when empty, to keep the
        # schema stable for a reader that unconditionally looks them up).
        assert root.find("./capgen_files/host_files") is not None
        assert root.find("./capgen_files/suite_files") is not None


class TestDependenciesSection:
    def test_used_schemes_dependency_included(self, build_module):
        suite_xml = minimal_suite_xml("scheme_used")
        module = build_module(
            [_scheme_meta_with_dependencies("scheme_used", "used_dep.F90")],
            [], suite_xml,
        )
        mlir_text = _module_to_mlir(module)
        root = build_datatable(mlir_text, [])
        deps = [el.text for el in root.findall("./dependencies/dependency")]
        assert "used_dep.F90" in deps

    def test_unreferenced_scheme_dependency_excluded(self, build_module):
        # scheme_unused is passed as a scheme file but never referenced by
        # the loaded suite -- mirrors real capgen-v1's own filter
        # (ccpp_capgen.py's used_scheme_names gate): an unreferenced
        # scheme's dependencies must not leak into the datatable.
        suite_xml = minimal_suite_xml("scheme_used")
        module = build_module(
            [
                _scheme_meta_with_dependencies("scheme_used", "used_dep.F90"),
                _scheme_meta_with_dependencies("scheme_unused", "unused_dep.F90"),
            ],
            [], suite_xml,
        )
        mlir_text = _module_to_mlir(module)
        root = build_datatable(mlir_text, [])
        deps = [el.text for el in root.findall("./dependencies/dependency")]
        assert "used_dep.F90" in deps
        assert "unused_dep.F90" not in deps

    def test_no_dependencies_declared_yields_empty_section(self, build_module):
        module = build_module([_scheme_meta("s1")], [], None)
        mlir_text = _module_to_mlir(module)
        root = build_datatable(mlir_text, [])
        deps_el = root.find("./dependencies")
        assert deps_el is not None
        assert list(deps_el) == []

    def test_deduped_across_schemes(self, build_module):
        # Two schemes, both used, both declaring the identical dependency
        # (the same real situation Stage 8b's own verification found in
        # examples/capgen: temp_set.meta and temp_adjust.meta both declare
        # `dependencies = temp_kinds.F90`) -- must appear exactly once.
        suite_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="1.0">
  <group name="physics">
    <scheme>s1</scheme>
    <scheme>s2</scheme>
  </group>
</suite>
"""
        module = build_module(
            [
                _scheme_meta_with_dependencies("s1", "shared_dep.F90"),
                _scheme_meta_with_dependencies("s2", "shared_dep.F90"),
            ],
            [], suite_xml,
        )
        mlir_text = _module_to_mlir(module)
        root = build_datatable(mlir_text, [])
        deps = [el.text for el in root.findall("./dependencies/dependency")]
        assert deps.count("shared_dep.F90") == 1

    def test_deeply_nested_subcycle_scheme_included(self, build_module):
        # Mirrors examples/var_compat/var_compatibility_suite.xml:5-11 --
        # a scheme three subcycle levels deep. Copilot review (PR #94)
        # correctly flagged that _iter_schemes_in_group only descended one
        # level, so a scheme at this depth was silently treated as unused
        # and its dependency wrongly excluded.
        suite_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="1.0">
  <group name="radiation">
    <subcycle loop="2">
      <subcycle loop="2">
        <scheme>deeply_nested_scheme</scheme>
      </subcycle>
    </subcycle>
  </group>
</suite>
"""
        module = build_module(
            [_scheme_meta_with_dependencies("deeply_nested_scheme", "nested_dep.F90")],
            [], suite_xml,
        )
        mlir_text = _module_to_mlir(module)
        root = build_datatable(mlir_text, [])
        deps = [el.text for el in root.findall("./dependencies/dependency")]
        assert "nested_dep.F90" in deps

    def test_suite_init_scheme_dependency_included(self, build_module):
        # A suite-level <init> scheme (v2.0 SDF schema, SuiteOp.init_scheme)
        # is never a group member at all -- Copilot review (PR #94)
        # correctly flagged that _used_scheme_names only walked group
        # membership, so this scheme's own dependency was always excluded,
        # matching real capgen-v1's own used_scheme_names gate (which adds
        # suite_init_call's scheme name explicitly).
        suite_xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite" version="1.0">
  <init>init_only_scheme</init>
  <group name="physics">
    <scheme>run_scheme</scheme>
  </group>
</suite>
"""
        module = build_module(
            [
                _scheme_meta_with_dependencies("init_only_scheme", "init_dep.F90", phase="init"),
                _scheme_meta("run_scheme"),
            ],
            [], suite_xml,
        )
        mlir_text = _module_to_mlir(module)
        root = build_datatable(mlir_text, [])
        deps = [el.text for el in root.findall("./dependencies/dependency")]
        assert "init_dep.F90" in deps


# ── write_datatable ───────────────────────────────────────────────────────────

class TestWriteDatatable:
    def test_writes_file(self, tmp_path, build_module):
        module = build_module([_scheme_meta("ws1")], [], None)
        mlir_text = _module_to_mlir(module)
        root = build_datatable(mlir_text, [])
        out = str(tmp_path / "datatable.xml")
        write_datatable(root, out)
        assert os.path.isfile(out)

    def test_output_is_valid_xml(self, tmp_path, build_module):
        module = build_module([_scheme_meta("ws2")], [], None)
        mlir_text = _module_to_mlir(module)
        root = build_datatable(mlir_text, [])
        out = str(tmp_path / "datatable.xml")
        write_datatable(root, out)
        tree = ET.parse(out)
        assert tree.getroot().tag == "datatable"

    def test_xml_contains_xml_declaration(self, tmp_path, build_module):
        module = build_module([_scheme_meta("ws3")], [], None)
        mlir_text = _module_to_mlir(module)
        root = build_datatable(mlir_text, [])
        out = str(tmp_path / "datatable.xml")
        write_datatable(root, out)
        with open(out) as f:
            first_line = f.readline()
        assert first_line.startswith("<?xml")


# ── write_html ────────────────────────────────────────────────────────────────

class TestWriteHtml:
    def test_creates_html_files(self, tmp_path, build_module):
        module = build_module([_scheme_meta_with_var("html_scheme")], [], None)
        mlir_text = _module_to_mlir(module)
        root = build_datatable(mlir_text, [])
        html_dir = str(tmp_path / "docs")
        written = write_html(root, html_dir)
        assert any("html_scheme_run" in p for p in written)

    def test_html_file_contains_standard_name(self, tmp_path, build_module):
        module = build_module([_scheme_meta_with_var("html_scheme2")], [], None)
        mlir_text = _module_to_mlir(module)
        root = build_datatable(mlir_text, [])
        html_dir = str(tmp_path / "docs2")
        write_html(root, html_dir)
        html_path = os.path.join(html_dir, "html_scheme2_run.html")
        assert os.path.isfile(html_path)
        content = open(html_path).read()
        assert "horizontal_loop_extent" in content

    def test_html_file_has_table_columns(self, tmp_path, build_module):
        module = build_module([_scheme_meta_with_var("html_scheme3")], [], None)
        mlir_text = _module_to_mlir(module)
        root = build_datatable(mlir_text, [])
        html_dir = str(tmp_path / "docs3")
        write_html(root, html_dir)
        html_path = os.path.join(html_dir, "html_scheme3_run.html")
        content = open(html_path).read()
        for col in ("Standard name", "Local name", "Units", "Intent"):
            assert col in content

    def test_html_dir_created_if_absent(self, tmp_path, build_module):
        module = build_module([_scheme_meta_with_var("html_scheme4")], [], None)
        mlir_text = _module_to_mlir(module)
        root = build_datatable(mlir_text, [])
        new_dir = str(tmp_path / "new_subdir" / "docs")
        write_html(root, new_dir)
        assert os.path.isdir(new_dir)

    def test_returns_written_paths(self, tmp_path, build_module):
        module = build_module([_scheme_meta("novar_scheme")], [], None)
        mlir_text = _module_to_mlir(module)
        root = build_datatable(mlir_text, [])
        html_dir = str(tmp_path / "ret_docs")
        written = write_html(root, html_dir)
        assert isinstance(written, list)
        for p in written:
            assert os.path.isfile(p)
