"""Unit tests for GPU residency/clause-routing on DDT-member host vars.

Backlog gap #5: GPUCcppCapPass's whole-suite hoisting (_analyze_one_suite/
_analyze_one_suite_residency + _wrap_scheme_call/_wrap_residency_directives)
keyed its lifetime dicts by the raw model_var_name -- for a DDT member this
is just the bare member name (e.g. "Temp"), while the actual HostVarRefOp
built for that scheme-call argument carries the DDT INSTANCE name (e.g.
"phys_state") with a separate member_name attribute ("Temp"). Every scan
that matched a HostVarRefOp against the lifetime dict compared on var_name
alone, so it never matched a DDT member -- classification was computed
correctly, but directive insertion silently found nothing to attach to.
Confirmed empirically (examples/advection's real temp/qv, run through the
actual production pipeline including generate-host-match) to affect not
just present/update residency but the ordinary copy-family case too --
GPUCcppCapPass established literally zero !$acc treatment for any DDT
member.

GPUDataPass (a different, earlier pass used only for the narrower "two
schemes in a suite disagree" case, see test_gpu_directives.py's
TestGPUDivergedClauseRoutingDDTMember) was never affected -- it works on
already-resolved suite_cap-level block arguments, never scans HostVarRefOp
by name.

Fixed by resolving the DDT type name to its actual module-level instance
(cap_shared.py's _resolve_ddt_access_path/_resolve_member_subscripts,
extracted from run_dispatch.py, which already needed this to build the real
HostVarRefOp) and using that same resolved "instance%member" identity as
the dict key on both the metadata side (_resolve_host_var_key) and the
IR-scanning side (_ref_key) -- see gpu_ccpp_cap_pass.py.
"""

from io import StringIO

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.ccpp_cap import CCPPCAP
from xdsl_ccpp.transforms.gpu_ccpp_cap_pass import GPUCcppCapPass
from xdsl_ccpp.transforms.gpu_data_pass import GPUDataPass
from xdsl_ccpp.transforms.suite_cap import SuiteCAP


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


_DDT_TYPE = """\
[ccpp-table-properties]
  name = test_ddt_residency_type
  type = ddt
[ccpp-arg-table]
  name = test_ddt_residency_type
  type = ddt
[ temp_member ]
  standard_name = test_ddt_residency_temp_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  memory_space = device
[ qv_member ]
  standard_name = test_ddt_residency_qv_var
  units = kg kg-1
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
"""

_DDT_HOST_MOD = """\
[ccpp-table-properties]
  name = test_ddt_residency_host_mod
  type = module
[ccpp-arg-table]
  name = test_ddt_residency_host_mod
  type = module
[ phys_state ]
  standard_name = test_ddt_residency_instance
  type = test_ddt_residency_type
  units = DDT
  dimensions = ()
"""


# ── present: scheme=device, host DDT member=device (single, non-diverged) ──

_PRESENT_SCHEME = f"""\
[ccpp-table-properties]
  name = test_ddt_present_scheme
  type = scheme
[ccpp-arg-table]
  name = test_ddt_present_scheme_run
  type = scheme
[ temp ]
  standard_name = test_ddt_residency_temp_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  memory_space = device
  intent = inout
{CCPP_MANDATORY_ARGS}
"""

_PRESENT_SUITE_XML = minimal_suite_xml(
    "test_ddt_present_scheme", suite_name="test_ddt_present_suite"
)


class TestDDTMemberPresent:
    def test_ddt_member_gets_present_clause(self, run_host_match, ccpp_context):
        """Single (non-diverged) scheme, scheme+host both device -- exercises
        GPUCcppCapPass's own whole-suite path directly (not GPUDataPass's
        diverged-only routing, already covered by
        test_gpu_directives.py::TestGPUDivergedClauseRoutingDDTMember)."""
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_PRESENT_SCHEME], [_DDT_TYPE, _DDT_HOST_MOD], _PRESENT_SUITE_XML,
        )
        run_fn = _fn_body(fortran, "TestDdtPresent_ccpp_physics_run")
        assert "present(phys_state%temp_member" in run_fn


# ── copy-family: scheme=device, host DDT member=host (default) ─────────────

_COPY_SCHEME = f"""\
[ccpp-table-properties]
  name = test_ddt_copy_scheme
  type = scheme
[ccpp-arg-table]
  name = test_ddt_copy_scheme_run
  type = scheme
[ qv ]
  standard_name = test_ddt_residency_qv_var
  units = kg kg-1
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  memory_space = device
  intent = inout
{CCPP_MANDATORY_ARGS}
"""

_COPY_SUITE_XML = minimal_suite_xml(
    "test_ddt_copy_scheme", suite_name="test_ddt_copy_suite"
)


class TestDDTMemberCopyFamily:
    def test_ddt_member_gets_copy_region(self, run_host_match, ccpp_context):
        """scheme=device + host DDT member=host is copy-family, not
        present/update -- before the fix this got literally zero !$acc
        treatment (not even the ordinary copy() region an equivalent plain
        host var already received)."""
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_COPY_SCHEME], [_DDT_TYPE, _DDT_HOST_MOD], _COPY_SUITE_XML,
        )
        run_fn = _fn_body(fortran, "TestDdtCopy_ccpp_physics_run")
        assert "!$acc data copy(phys_state%qv_member" in run_fn


# ── multi-phase: hoisted enter at initialize, exit at finalize ─────────────

_MULTI_PHASE_SCHEME = f"""\
[ccpp-table-properties]
  name = test_ddt_multi_scheme
  type = scheme
[ccpp-arg-table]
  name = test_ddt_multi_scheme_init
  type = scheme
[ temp ]
  standard_name = test_ddt_residency_temp_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  memory_space = device
  intent = inout
{CCPP_MANDATORY_ARGS}
[ccpp-arg-table]
  name = test_ddt_multi_scheme_run
  type = scheme
[ temp ]
  standard_name = test_ddt_residency_temp_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  memory_space = device
  intent = inout
{CCPP_MANDATORY_ARGS}
"""

_MULTI_PHASE_SUITE_XML = minimal_suite_xml(
    "test_ddt_multi_scheme", suite_name="test_ddt_multi_suite"
)


class TestDDTMemberMultiPhaseHoisting:
    def test_hoisted_enter_at_initialize_exit_at_finalize_nothing_at_run(
        self, run_host_match, ccpp_context
    ):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_MULTI_PHASE_SCHEME], [_DDT_TYPE, _DDT_HOST_MOD], _MULTI_PHASE_SUITE_XML,
        )
        init_fn = _fn_body(fortran, "TestDdtMulti_ccpp_physics_initialize")
        run_fn = _fn_body(fortran, "TestDdtMulti_ccpp_physics_run")
        finalize_fn = _fn_body(fortran, "TestDdtMulti_ccpp_physics_finalize")

        assert "present(phys_state%temp_member" in init_fn
        assert "present(phys_state%temp_member" in finalize_fn
        for line in run_fn.splitlines():
            stripped = line.strip()
            if "phys_state" in stripped and "!$acc" in stripped:
                assert stripped.startswith("!$acc data present") or "present(phys_state" in stripped


# ── residency establishment: host DDT member=device, scheme itself=host ────

_RESIDENCY_SCHEME = f"""\
[ccpp-table-properties]
  name = test_ddt_res_estab_scheme
  type = scheme
[ccpp-arg-table]
  name = test_ddt_res_estab_scheme_run
  type = scheme
[ temp ]
  standard_name = test_ddt_residency_temp_var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  intent = inout
{CCPP_MANDATORY_ARGS}
"""

_RESIDENCY_SUITE_XML = minimal_suite_xml(
    "test_ddt_res_estab_scheme", suite_name="test_ddt_res_estab_suite"
)


class TestDDTMemberResidencyEstablishment:
    def test_host_side_device_ddt_member_gets_residency(self, run_host_match, ccpp_context):
        """Scheme itself declares no memory_space (scheme=host) -- doesn't
        touch present/update/copy at all in _analyze_one_suite -- but the
        host DDT member is device-resident (memory_space=device in the DDT
        table), so _analyze_one_suite_residency/_wrap_residency_directives
        must independently establish residency for it (the CapScratch/
        HostMatched residency mechanism from PR #37), DDT member and all."""
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            [_RESIDENCY_SCHEME], [_DDT_TYPE, _DDT_HOST_MOD], _RESIDENCY_SUITE_XML,
        )
        run_fn = _fn_body(fortran, "TestDdtResEstab_ccpp_physics_run")
        assert "!$acc data copy(phys_state%temp_member" in run_fn
