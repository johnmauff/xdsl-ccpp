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
