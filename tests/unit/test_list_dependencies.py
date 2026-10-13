"""Unit tests for `--list-dependencies` (cmake-configure-regen's Part B):
`ccppMain.predict_dependencies` predicts the same `<dependencies>` content
a real `--emit-datatable` run would produce, without running a real
generation.

Mirrors `ccpp_datatable.py`'s own `_collect_dependencies` filtering rule
(HOST/MODULE/DDT tables always contribute; SCHEME tables only if the
suite actually references them) by calling it directly against a cheaply
built, pre-MetaCAP module -- these tests exercise that filtering plus the
two real examples (`capgen`, `ddthost`) already known to declare real
dependencies, confirming the prediction matches their real,
freshly-regenerated `--emit-datatable` output byte-for-byte.
"""

from xdsl_ccpp.tools.ccpp_dsl import ccppMain


def _options_db(tool, suites, scheme_files, host_files, **overrides):
    options_db = tool.default_options_db()
    options_db.update({
        "suites": suites,
        "scheme_files": scheme_files,
        "host_files": host_files,
        "verbose": 0,
    })
    options_db.update(overrides)
    return options_db


def _predict(options_db):
    tool = ccppMain()
    tool.options_db = tool._normalize_options_db(dict(options_db))
    return tool.predict_dependencies()


class TestRealExamples:
    def test_capgen_plain_call_matches_real_dependencies(self):
        deps = _predict(_options_db(
            ccppMain(),
            suites=[
                "examples/capgen/scheme/ddt_suite.xml",
                "examples/capgen/scheme/temp_suite.xml",
            ],
            scheme_files=[
                "examples/capgen/scheme/make_ddt.meta",
                "examples/capgen/scheme/environ_conditions.meta",
                "examples/capgen/scheme/setup_coeffs.meta",
                "examples/capgen/scheme/temp_set.meta",
                "examples/capgen/scheme/temp_calc_adjust.meta",
                "examples/capgen/scheme/temp_adjust.meta",
            ],
            host_files=[
                "examples/capgen/host_ftn/test_host_data.meta",
                "examples/capgen/host_ftn/test_host_mod.meta",
                "examples/capgen/host_ftn/test_host.meta",
            ],
            host_name="test_host",
        ))
        assert any(d.endswith("scheme/adjust/temp_kinds.F90") for d in deps)
        assert any(d.endswith("scheme/ddt2.F90") for d in deps)
        assert len(deps) == 2
        assert all(d.startswith("/") for d in deps)  # resolved, not relative

    def test_instances_declares_no_dependencies(self):
        deps = _predict(_options_db(
            ccppMain(),
            suites=["examples/instances/suite_unit_conv_suite.xml"],
            scheme_files=[
                "examples/instances/unit_conv_scheme_1.meta",
                "examples/instances/unit_conv_scheme_2.meta",
            ],
            host_files=[
                "examples/instances/data.meta",
                "examples/instances/test_host.meta",
            ],
            host_name="test_host",
        ))
        assert deps == []


class TestSchemeFiltering:
    """Synthetic fixtures (tmp_path) for the one rule real examples don't
    happen to exercise: a scheme's own dependencies are only collected if
    some suite actually references that scheme -- an unused scheme file
    passed on --scheme-files but never called by any suite must not leak
    its own declared dependency into the prediction."""

    def _write_suite(self, tmp_path, used_scheme_name):
        suite_path = tmp_path / "suite.xml"
        suite_path.write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<suite name="test_suite" version="1.0">\n'
            '  <group name="physics">\n'
            f'    <scheme>{used_scheme_name}</scheme>\n'
            '  </group>\n'
            '</suite>\n'
        )
        return suite_path

    def _write_scheme(self, tmp_path, name, dependency_filename):
        path = tmp_path / f"{name}.meta"
        path.write_text(
            "[ccpp-table-properties]\n"
            f"  name = {name}\n"
            "  type = scheme\n"
            f"  dependencies = {dependency_filename}\n"
            "[ccpp-arg-table]\n"
            f"  name = {name}_run\n"
            "  type = scheme\n"
        )
        return path

    def _write_host(self, tmp_path, dependency_filename):
        path = tmp_path / "host.meta"
        path.write_text(
            "[ccpp-table-properties]\n"
            "  name = test_host\n"
            "  type = host\n"
            f"  dependencies = {dependency_filename}\n"
            "[ccpp-arg-table]\n"
            "  name = test_host\n"
            "  type = host\n"
        )
        return path

    def test_unused_scheme_dependency_is_excluded(self, tmp_path):
        suite_path = self._write_suite(tmp_path, used_scheme_name="used_scheme")
        used = self._write_scheme(tmp_path, "used_scheme", "used.F90")
        unused = self._write_scheme(tmp_path, "unused_scheme", "unused.F90")
        host = self._write_host(tmp_path, "host_dep.F90")

        deps = _predict(_options_db(
            ccppMain(),
            suites=[str(suite_path)],
            scheme_files=[str(used), str(unused)],
            host_files=[str(host)],
        ))

        assert any(d.endswith("used.F90") for d in deps)
        assert any(d.endswith("host_dep.F90") for d in deps)
        assert not any(d.endswith("unused.F90") for d in deps)
        assert len(deps) == 2

    def test_host_type_dependency_always_included(self, tmp_path):
        """HOST-type tables contribute their own dependencies
        unconditionally (never gated on "is this host used by a suite" --
        there's no equivalent concept for host tables)."""
        suite_path = self._write_suite(tmp_path, used_scheme_name="used_scheme")
        used = self._write_scheme(tmp_path, "used_scheme", "used.F90")
        host = self._write_host(tmp_path, "host_dep.F90")

        deps = _predict(_options_db(
            ccppMain(),
            suites=[str(suite_path)],
            scheme_files=[str(used)],
            host_files=[str(host)],
        ))

        assert any(d.endswith("host_dep.F90") for d in deps)


class TestUnsupportedModes:
    def test_py_mode_rejected(self):
        tool = ccppMain()
        options_db = tool.default_options_db()
        options_db.update({"py": "xdsl_ccpp/tools/ccpp_dsl.py", "list_dependencies": True})
        tool.options_db = tool._normalize_options_db(dict(options_db))
        try:
            tool.predict_dependencies()
            assert False, "expected CcppDslError"
        except Exception as exc:
            assert "py" in str(exc)
