"""Shared fixtures for xdsl-ccpp Python unit tests.

These fixtures run passes programmatically against .meta content supplied as
strings.  No Fortran compilation is required — they test the Python logic only.

They are the foundation for Option 2 (compiled Fortran) tests: the same
fixtures plus a Fortran compile+run step on top of run_host_match /
run_gpu_passes etc.

Usage::

    pytest tests/unit/

"""

import pytest

from xdsl.context import Context
from xdsl.dialects.builtin import ModuleOp
from xdsl.universe import Universe

from xdsl_ccpp.dialects.ccpp import CCPP
from xdsl_ccpp.dialects.ccpp_utils import CCPPUtils
from xdsl_ccpp.frontend.ccpp_xml import XMLSuite, ccppXML, parse_meta_file
from xdsl_ccpp.transforms.host_var_match_pass import HostVariableMatchPass
from xdsl_ccpp.transforms.suite_meta import MetaCAP


# ── Context factory ───────────────────────────────────────────────────────────

def _make_context() -> Context:
    ctx = Context()
    for name, factory in Universe.get_multiverse().all_dialects.items():
        ctx.register_dialect(name, factory)
    ctx.load_dialect(CCPP)
    ctx.load_dialect(CCPPUtils)
    return ctx


# ── Core module-building helper ───────────────────────────────────────────────

def _build_module(
    scheme_metas: list[str],
    host_metas: list[str],
    suite_xml: str | None,
    tmp_path,
) -> ModuleOp:
    """Parse .meta strings and an optional suite XML into an IR ModuleOp.

    Writes content to temporary files (required by the file-based frontend
    parser) then calls the ccppXML frontend methods directly.
    """
    frontend = ccppXML()
    ir_ops = []

    if suite_xml is not None:
        suite_file = tmp_path / "test_suite.xml"
        suite_file.write_text(suite_xml)
        ir_ops.append(frontend.build_suite_ir(XMLSuite(str(suite_file))))

    for i, content in enumerate(scheme_metas):
        meta_file = tmp_path / f"scheme_{i}.meta"
        meta_file.write_text(content)
        for meta in parse_meta_file(str(meta_file), True):
            ir_ops.append(frontend.build_meta_ir(meta))

    for i, content in enumerate(host_metas):
        meta_file = tmp_path / f"host_{i}.meta"
        meta_file.write_text(content)
        for meta in parse_meta_file(str(meta_file), False):
            ir_ops.append(frontend.build_meta_ir(meta))

    return ModuleOp(ir_ops)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def ccpp_context():
    """A fresh xDSL context with all CCPP dialects loaded."""
    return _make_context()


@pytest.fixture
def build_module(tmp_path):
    """Parse .meta content strings into a raw IR ModuleOp (no passes run)."""
    def _build(
        scheme_metas: list[str],
        host_metas: list[str],
        suite_xml: str | None = None,
    ) -> ModuleOp:
        return _build_module(scheme_metas, host_metas, suite_xml, tmp_path)
    return _build


@pytest.fixture
def run_host_match(tmp_path, ccpp_context):
    """Run MetaCAP + HostVariableMatchPass and return the annotated module.

    Raises ValueError if the match/compatibility checks fail, exactly as the
    production pass does.  Use with pytest.raises() to test error cases.
    """
    def _run(
        scheme_metas: list[str],
        host_metas: list[str],
        suite_xml: str | None = None,
    ) -> ModuleOp:
        module = _build_module(scheme_metas, host_metas, suite_xml, tmp_path)
        MetaCAP().apply(ccpp_context, module)
        HostVariableMatchPass().apply(ccpp_context, module)
        return module
    return _run
