import json

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
