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


_ADVECTION_SCHEMES = ("const_indices", "cld_liq", "apply_constituent_tendencies",
                      "cld_ice", "cld_shadow")


def _generate(tmp_path, label, a, tagged, **source):
    """Generate caps from directory *a*'s advection schemes and host .meta
    plus *source* (suites= or py=); return {filename: Fortran text}.  With
    *tagged*, scheme .meta is generated from the !$ccpp-tagged sources (as
    CMake does, via ccpp_generate_meta) instead of read from *a*."""
    from xdsl_ccpp.tools.ccpp_generate_meta import generate_meta_for_file

    meta_dir = tmp_path / label / "meta"
    meta_dir.mkdir(parents=True)
    scheme_files = []
    for name in _ADVECTION_SCHEMES:
        if tagged:
            path = meta_dir / f"{name}.meta"
            path.write_text(generate_meta_for_file(f"{a}/{name}.F90", a))
        else:
            path = f"{a}/{name}.meta"
        scheme_files.append(str(path))
    tool = ccppMain()
    options_db = tool.default_options_db()
    options_db.update({
        "scheme_files": scheme_files,
        "host_files": [f"{a}/test_host_data.meta", f"{a}/test_host_mod.meta",
                       f"{a}/test_host.meta"],
        "host_name": "test_host",
        "directive": "acc",
        "out": str(tmp_path / label / "out"),
        "tempdir": str(tmp_path / label / "tmp"),
        "verbose": 0,
        **source,
    })
    result = tool.run(options_db)
    out = options_db["out"]
    return {os.path.basename(p): open(os.path.join(out, p)).read()
            for p in result.written if p.endswith(".F90")}


def test_py_composite_suite_generates_same_caps_as_xml(tmp_path):
    """examples/advection_composite (Python suite with name-only scheme
    references and a process-update combinator; scheme metadata generated
    from !$ccpp tags) generates exactly the caps examples/advection's
    cld_suite.xml does from its hand-written .meta -- checking both the
    Python path (including constituent handling, which needs --py's metadata
    merge to match the XML frontend) and that the hand-written metadata,
    GPU residency included, agrees with the tagged sources."""
    xml = _generate(tmp_path, "xml", "examples/advection", tagged=False,
                    suites=["examples/advection/cld_suite.xml"])
    py = _generate(tmp_path, "py", "examples/advection_composite", tagged=True,
                   py="examples/advection_composite/advection_composite_py.py")
    assert sorted(xml) == ["ccpp_kinds.F90", "cld_suite_cap.F90", "test_host_ccpp_cap.F90"]
    assert py == xml
    # ...and the Python suite really does record its cloud package as a composite
    import subprocess
    import sys
    ir = subprocess.run([sys.executable,
                         "examples/advection_composite/advection_composite_py.py"],
                        capture_output=True, text=True, check=True).stdout
    assert 'composite_name = "cloud_microphysics"' in ir


def test_rrtmgp_composite_matches_reference_suite(legacy_mode):
    """examples/rrtmgp_composite: the RRTMGP package + CAM-SIMA adapter +
    suite (Python, name-only references) define exactly the suite
    atmospheric_physics' flat suite_rrtmgp.xml does -- same groups, scheme
    sequence, loops and scheme metadata -- compared as the metadata module
    real generation starts from, built from the example's metadata snapshot,
    after the flatten-composites pass that begins the real pipeline (the
    package's entry points are @rrtmgp.entry_point).
    (Full cap generation would need CAM-SIMA's host metadata; out of scope
    for this not-to-be-compiled example.)"""
    import glob

    from xdsl_ccpp.tools.ctx_utils import make_ccpp_context
    from xdsl_ccpp.transforms.flatten_composites import FlattenComposites

    d = "examples/rrtmgp_composite"
    schemes = sorted(f for f in glob.glob(f"{d}/meta/**/*.meta", recursive=True)
                     if "/objects/" not in f)

    def metadata_module(**source):
        tool = ccppMain()
        options_db = tool.default_options_db()
        options_db.update({"scheme_files": schemes, "host_files": [],
                           "legacy_mode": True, "verbose": 0, **source})
        tool.options_db = tool._normalize_options_db(dict(options_db))
        return tool._build_cheap_metadata_module()

    def flattened(module):
        FlattenComposites().apply(make_ccpp_context(), module)
        return str(module)

    xml = metadata_module(suites=[f"{d}/suite_rrtmgp.xml"])
    py = metadata_module(suites=[], py=f"{d}/suite_rrtmgp_composite_py.py")
    composites = [op for op in py.walk() if op.name == "ccpp.composite"]
    entry_points = [op.composite_name.data for op in composites if op.hook is None]
    assert entry_points == ["rrtmgp_prepare", "rrtmgp_shortwave",
                            "rrtmgp_longwave", "rrtmgp_init_only"]
    assert {op.package.data for op in composites if op.hook is None} == {"rrtmgp"}
    # Host code run through hooks is marked, nested in its entry point.
    def entry_point(op):
        op = op.parent_op()
        while op.name != "ccpp.composite":
            op = op.parent_op()
        return op.composite_name.data

    hooks = sorted({(entry_point(op), op.composite_name.data)
                    for op in composites if op.hook is not None})
    assert hooks == [
        ("rrtmgp_longwave", "diagnostics"), ("rrtmgp_longwave", "gas_source"),
        ("rrtmgp_longwave", "next_call"),
        ("rrtmgp_prepare", "tropopause"),
        ("rrtmgp_shortwave", "aerosol_optics"),
        ("rrtmgp_shortwave", "cloud_diagnostics"),
        ("rrtmgp_shortwave", "diagnostics"), ("rrtmgp_shortwave", "gas_source"),
        ("rrtmgp_shortwave", "next_call"), ("rrtmgp_shortwave", "solar_source")]
    assert str(xml).count('"ccpp.scheme"') == 40
    assert flattened(py) == flattened(xml)
