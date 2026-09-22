"""Unit tests for suite-scoped GPU residency divergence detection.

Before this fix, cap_shared.find_diverged_suite_vars gated divergence
detection on the HOST's own static model_var_memory_space declaration --
meaning two schemes in the SAME suite could genuinely disagree about
present-vs-update treatment for a host var (one declares
memory_space=device, the other doesn't), and if the HOST's own metadata
never separately declared that var device-resident (a real, confirmed
production bug: air_temperature in registry.xml has no memory_space
attribute anywhere, even though kessler_update correctly declares device
for it), the disagreement was invisible to xdsl_ccpp entirely -- the
host-only scheme's write silently never got synced back to the device,
producing stale reads downstream in the same suite/timestep.

The fix removes that host-level gate from divergence detection (a
disagreement between two schemes' own declarations IS the signal,
independent of what a separate file says) and additionally teaches
gpu_ccpp_cap_pass.py's _analyze_one_suite_residency to also establish
entry/exit residency for diverged vars, since _analyze_one_suite's own
clause-routing correctly excludes them from its copy-family bucket, which
would otherwise leave them with no residency anchoring (enter/exit data)
at all.

Deliberately per-suite, not global: a var's divergence status in one suite
must never influence its treatment in an unrelated suite that never
established device residency for it -- see TestCrossSuiteIsolation below.
"""

from io import StringIO

from tests.unit.helpers import CCPP_MANDATORY_ARGS
from xdsl.context import Context
from xdsl.dialects.builtin import ModuleOp
from xdsl.universe import Universe
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.dialects.ccpp import CCPP
from xdsl_ccpp.dialects.ccpp_utils import CCPPUtils
from xdsl_ccpp.frontend.ccpp_xml import XMLSuite, ccppXML, parse_meta_file
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.ccpp_cap import CCPPCAP
from xdsl_ccpp.transforms.gpu_ccpp_cap_pass import GPUCcppCapPass
from xdsl_ccpp.transforms.gpu_data_pass import GPUDataPass
from xdsl_ccpp.transforms.host_var_match_pass import HostVariableMatchPass
from xdsl_ccpp.transforms.suite_cap import SuiteCAP
from xdsl_ccpp.transforms.suite_meta import MetaCAP

import pytest

pytestmark = pytest.mark.usefixtures("legacy_mode")


# ── shared fixtures ──────────────────────────────────────────────────────────
#
# conflict_var's own host declaration deliberately carries NO memory_space
# attribute at all -- exactly air_temperature's real-world shape.

_HOST_META = """\
[ccpp-table-properties]
  name = test_suite_scoped_host
  type = module
[ccpp-arg-table]
  name = test_suite_scoped_host
  type = module
[ conflict_var ]
  standard_name = test_suite_scoped_conflict_var
  units = kg kg-1
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
"""

_DEVICE_SCHEME = f"""\
[ccpp-table-properties]
  name = test_suite_scoped_device_scheme
  type = scheme
[ccpp-arg-table]
  name = test_suite_scoped_device_scheme_run
  type = scheme
[ qv_a ]
  standard_name = test_suite_scoped_conflict_var
  units = kg kg-1
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  memory_space = device
  intent = in
{CCPP_MANDATORY_ARGS}
"""

_HOST_ONLY_SCHEME = f"""\
[ccpp-table-properties]
  name = test_suite_scoped_host_only_scheme
  type = scheme
[ccpp-arg-table]
  name = test_suite_scoped_host_only_scheme_run
  type = scheme
[ qv_b ]
  standard_name = test_suite_scoped_conflict_var
  units = kg kg-1
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  intent = inout
{CCPP_MANDATORY_ARGS}
"""

_SUITE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite_scoped_suite" version="1.0">
  <group name="physics">
    <scheme>test_suite_scoped_device_scheme</scheme>
    <scheme>test_suite_scoped_host_only_scheme</scheme>
  </group>
</suite>
"""


def _fortran_output(run_host_match, ccpp_context, scheme_metas, host_metas, suite_xml) -> str:
    module = run_host_match(
        scheme_metas=scheme_metas,
        host_metas=host_metas,
        suite_xml=suite_xml,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    GPUDataPass(directive="acc").apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    GPUCcppCapPass(directive="acc").apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


def _fn_body(fortran: str, fn_name: str) -> str:
    return fortran.split(f"subroutine {fn_name}")[1].split(f"end subroutine {fn_name}")[0]


class TestSuiteScopedDivergenceWithoutHostDeclaration:
    def test_diverges_and_gets_synced_despite_no_host_level_memory_space(
        self, run_host_match, ccpp_context
    ):
        """qv_a (device) and qv_b (host-only) genuinely disagree about
        test_suite_scoped_conflict_var, but the host's own meta never
        declares memory_space=device for it at all -- confirms divergence
        detection (and the resulting update self/device sync) no longer
        depends on that separate, easy-to-forget declaration."""
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_DEVICE_SCHEME, _HOST_ONLY_SCHEME], [_HOST_META], _SUITE_XML,
        )
        suite_fn = _fn_body(fortran, "test_suite_scoped_suite_physics")
        assert "present(qv_a" in suite_fn
        assert "update self(qv_a" in suite_fn
        assert "update device(qv_a" in suite_fn

    def test_residency_established_at_ccpp_cap_level(self, run_host_match, ccpp_context):
        """Before this fix, a diverged var with no host-level memory_space
        declaration got NO residency treatment at all at the ccpp_cap
        level -- excluded from copy-family by divergence (correct), and
        excluded from residency establishment by the missing host
        declaration (the actual root cause of the stale-read bug this fix
        closes). Confirms _analyze_one_suite_residency now steps in for
        it: single-phase (run-only) usage is the "degenerate" residency
        case, wrapped in a plain per-call copy() region -- the same
        treatment copy-family's own "legacy_copy" vars already get (see
        _analyze_one_suite_residency's docstring)."""
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_DEVICE_SCHEME, _HOST_ONLY_SCHEME], [_HOST_META], _SUITE_XML,
        )
        run_fn = _fn_body(fortran, "ccpp_physics_run")
        assert "copy(conflict_var" in run_fn or "copyin(conflict_var" in run_fn


# ── cross-suite isolation ────────────────────────────────────────────────────

_SUITE_TWO_HOST_ONLY_SCHEME = f"""\
[ccpp-table-properties]
  name = test_suite_scoped_other_suite_scheme
  type = scheme
[ccpp-arg-table]
  name = test_suite_scoped_other_suite_scheme_run
  type = scheme
[ qv_c ]
  standard_name = test_suite_scoped_conflict_var
  units = kg kg-1
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  intent = in
{CCPP_MANDATORY_ARGS}
"""

_SUITE_TWO_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_suite_scoped_other_suite" version="1.0">
  <group name="physics">
    <scheme>test_suite_scoped_other_suite_scheme</scheme>
  </group>
</suite>
"""


def _make_context() -> Context:
    ctx = Context()
    for name, factory in Universe.get_multiverse().all_dialects.items():
        ctx.register_dialect(name, factory)
    ctx.load_dialect(CCPP)
    ctx.load_dialect(CCPPUtils)
    return ctx


def _build_multi_suite_module(scheme_metas, host_metas, suite_xmls, tmp_path, ctx):
    """Same shape as test_gpu_data_hoisting.py's own helper of this name --
    conftest's run_host_match/build_module fixtures only take a single
    suite_xml, which can't express a multi-suite build without changing
    shared test infrastructure other tests depend on."""
    frontend = ccppXML()
    ir_ops = []
    for i, xml in enumerate(suite_xmls):
        suite_file = tmp_path / f"suite_{i}.xml"
        suite_file.write_text(xml)
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
    module = ModuleOp(ir_ops)
    MetaCAP().apply(ctx, module)
    HostVariableMatchPass().apply(ctx, module)
    return module


class TestCrossSuiteIsolation:
    def test_unrelated_suite_never_gets_device_treatment_for_shared_standard_name(
        self, tmp_path
    ):
        """Suite one has two schemes genuinely disagreeing about
        test_suite_scoped_conflict_var (device vs host-only) -- diverged.
        Suite two touches the SAME standard_name via a single scheme that
        never declares memory_space=device at all. Divergence detection is
        suite-scoped (scheme_names), so suite two's own generated code must
        be completely untouched by suite one's own divergence -- no
        update self/device, no residency establishment, no !$acc anything
        for it at all. (A global, cross-suite union would have been
        actively unsafe here: update self/update device require the
        variable to already be present on the device, which suite two
        never establishes -- a hard PRESENT-clause crash, not just an
        inefficiency.)"""
        ctx = _make_context()
        module = _build_multi_suite_module(
            scheme_metas=[_DEVICE_SCHEME, _HOST_ONLY_SCHEME, _SUITE_TWO_HOST_ONLY_SCHEME],
            host_metas=[_HOST_META],
            suite_xmls=[_SUITE_XML, _SUITE_TWO_XML],
            tmp_path=tmp_path,
            ctx=ctx,
        )
        ArgOwnershipPass().apply(ctx, module)
        SuiteCAP().apply(ctx, module)
        GPUDataPass(directive="acc").apply(ctx, module)
        CCPPCAP().apply(ctx, module)
        GPUCcppCapPass(directive="acc").apply(ctx, module)
        out = StringIO()
        print_to_ftn(module, out)
        fortran = out.getvalue()

        suite_two_fn = _fn_body(fortran, "test_suite_scoped_other_suite_physics")
        assert "!$acc" not in suite_two_fn
