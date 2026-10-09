import json
import os

from xdsl_ccpp.tools.ccpp_dsl import ccppMain


def _base_options_db(tool, tmp_path):
    options_db = tool.default_options_db()
    options_db.update({
        "suites": ["examples/helloworld/hello_world_suite.xml"],
        "scheme_files": [
            "examples/helloworld/hello_scheme.meta",
            "examples/helloworld/temp_adjust.meta",
        ],
        "host_files": [
            "examples/helloworld/hello_world_host.meta",
            "examples/helloworld/hello_world_mod.meta",
        ],
        "out": str(tmp_path / "out"),
        "tempdir": str(tmp_path / "tmp"),
        "verbose": 0,
    })
    return options_db


def test_run_returns_resolved_vars_matching_json_file(tmp_path):
    resolved_vars_path = tmp_path / "resolved_vars.json"
    tool = ccppMain()
    options_db = _base_options_db(tool, tmp_path)
    options_db["emit_resolved_vars"] = str(resolved_vars_path)

    result = tool.run(options_db)

    assert result.written
    assert result.datatable_path is None
    assert result.resolved_vars is not None

    with open(resolved_vars_path) as f:
        on_disk = json.load(f)
    assert result.resolved_vars == on_disk
    assert "run" in result.resolved_vars["phases"]
    names = {r["standard_name"] for r in result.resolved_vars["phases"]["run"]}
    assert "potential_temperature" in names


def test_run_without_emit_resolved_vars_returns_none(tmp_path):
    tool = ccppMain()
    options_db = _base_options_db(tool, tmp_path)
    result = tool.run(options_db)
    assert result.resolved_vars is None


def test_run_normalizes_options_db_missing_host_files(tmp_path):
    """Regression test for a Copilot review comment on PR #122:
    `run(options_db=...)` must route the caller-supplied dict through the
    same normalization `build_options_db_from_args` applies to a CLI
    invocation. `default_options_db()` documents `host_files=None` as a
    valid "no host files" config (host_files is optional -- only `suites`
    and `scheme_files`/`meta_file` are required) -- without normalization,
    `run_frontend()`'s `list(self.options_db["host_files"])` crashes with
    TypeError the moment a programmatic caller omits it."""
    tool = ccppMain()
    options_db = tool.default_options_db()
    options_db.update({
        "suites": ["examples/helloworld/hello_world_suite.xml"],
        "scheme_files": [
            "examples/helloworld/hello_scheme.meta",
            "examples/helloworld/temp_adjust.meta",
        ],
        "out": str(tmp_path / "out"),
        "tempdir": str(tmp_path / "tmp"),
        "verbose": 0,
    })
    assert options_db["host_files"] is None  # default_options_db()'s own documented contract

    tool.options_db = tool._normalize_options_db(dict(options_db))
    assert tool.options_db["host_files"] == []

    os.makedirs(tool.options_db["tempdir"], exist_ok=True)
    mlir_file = tool.run_frontend(tool.options_db["tempdir"])
    assert os.path.isfile(mlir_file)
