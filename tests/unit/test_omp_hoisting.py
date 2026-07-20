"""Unit tests for cross-function OMP target-directive hoisting (directive="omp").

GPUCcppCapPass's cross-function data hoisting ("Option 2") originally only
applied when directive == "acc" -- _role_at hard-coded a
`self.directive != "acc"` gate that forced every OMP variable onto the
legacy per-call path unconditionally, and the update-clause hoisting
extension (item 1(a)) inherited the same gate. Both gates are now removed:
OMP variables get the same earliest/latest-phase hoisting ACC variables do,
using OmpTargetEnterDataOp/OmpTargetExitDataOp (map(to:)/map(alloc:) and
map(from:)/map(release:)) and OmpTargetUpdateFromOp/OmpTargetUpdateToOp in
place of the ACC-specific ops.

These are OMP equivalents of test_gpu_data_hoisting.py's ACC groups (A, B, C,
D, E, F), reusing that file's exact scheme/host/suite fixtures with
directive="omp" instead of "acc" -- the lifetime analysis itself is
directive-agnostic, so if a given var/phase shape hoists correctly under
ACC, the only new thing to verify here is that the OMP-specific ops/clause
text come out correctly, not the phase-anchor logic itself (already covered
by test_gpu_data_hoisting.py).
"""

from io import StringIO

from tests.unit.test_gpu_data_hoisting import (
    _GROUP_A_HOST,
    _GROUP_A_SCHEME_A,
    _GROUP_A_SCHEME_B,
    _GROUP_A_SUITE_XML,
    _GROUP_B_HOST,
    _GROUP_B_SCHEME,
    _GROUP_B_SUITE_XML,
    _GROUP_C_HOST,
    _GROUP_C_SCHEME_SUITE_A,
    _GROUP_C_SCHEME_SUITE_B,
    _GROUP_C_SUITE_A_XML,
    _GROUP_C_SUITE_B_XML,
    _GROUP_D_HOST,
    _GROUP_D_SCHEME,
    _GROUP_D_SUITE_XML,
    _GROUP_E_HOST,
    _GROUP_E_SCHEME,
    _GROUP_E_SUITE_XML,
    _GROUP_F_HOST,
    _GROUP_F_SCHEME,
    _GROUP_F_SUITE_XML,
    _GROUP_F_UPD_HOST,
    _GROUP_F_UPD_SCHEME,
    _GROUP_F_UPD_SUITE_XML,
    _build_multi_suite_module,
    _fn_body,
    _make_context,
)
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.transforms.ccpp_cap import CCPPCAP
from xdsl_ccpp.transforms.gpu_ccpp_cap_pass import GPUCcppCapPass
from xdsl_ccpp.transforms.gpu_data_pass import GPUDataPass
from xdsl_ccpp.transforms.suite_cap import SuiteCAP


def _omp_fortran_output(run_host_match, ccpp_context, scheme_metas, host_metas, suite_xml) -> str:
    """Same pipeline as test_gpu_data_hoisting.py's _fortran_output, but with
    directive="omp" for both GPU passes."""
    module = run_host_match(
        scheme_metas=scheme_metas,
        host_metas=host_metas,
        suite_xml=suite_xml,
    )
    SuiteCAP().apply(ccpp_context, module)
    GPUDataPass(directive="omp").apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    GPUCcppCapPass(directive="omp").apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


def _no_omp_data_directive_line_mentions(body: str, var_name: str) -> bool:
    """OMP equivalent of test_gpu_data_hoisting.py's
    _no_data_directive_line_mentions -- true if no target enter/exit data
    line in body references var_name."""
    for line in body.splitlines():
        stripped = line.strip()
        if ("target enter data" in stripped or "target exit data" in stripped) and var_name in stripped:
            return False
    return True


def _group_a_omp_fortran(run_host_match, ccpp_context) -> str:
    return _omp_fortran_output(
        run_host_match, ccpp_context,
        scheme_metas=[_GROUP_A_SCHEME_A, _GROUP_A_SCHEME_B],
        host_metas=[_GROUP_A_HOST],
        suite_xml=_GROUP_A_SUITE_XML,
    )


class TestOmpPerTimestepHoisting:
    """Group A equivalent: real cpair-shaped hoisting across two schemes."""

    def test_cross_scheme_var_enters_at_run_exits_at_timestep_final(
        self, run_host_match, ccpp_context
    ):
        fortran = _group_a_omp_fortran(run_host_match, ccpp_context)
        run_fn = _fn_body(fortran, "HoistSuiteA_ccpp_physics_run")
        final_fn = _fn_body(fortran, "HoistSuiteA_ccpp_physics_timestep_final")

        assert "target enter data" in run_fn
        assert "map(to:cross_var" in run_fn
        assert "target exit data" in final_fn
        assert "cross_var" in final_fn
        # No re-transfer: the old per-call legacy path must be gone.
        assert "map(to:cross_var" not in final_fn
        assert "map(tofrom:cross_var" not in final_fn

    def test_three_phase_var_hoists_with_passthrough_at_run(
        self, run_host_match, ccpp_context
    ):
        fortran = _group_a_omp_fortran(run_host_match, ccpp_context)
        initial_fn = _fn_body(fortran, "HoistSuiteA_ccpp_physics_timestep_initial")
        run_fn = _fn_body(fortran, "HoistSuiteA_ccpp_physics_run")
        final_fn = _fn_body(fortran, "HoistSuiteA_ccpp_physics_timestep_final")

        assert "target enter data" in initial_fn
        assert "map(to:three_phase" in initial_fn
        assert "map(alloc:" in run_fn
        assert "three_phase" in run_fn.split("map(alloc:")[1].split(")")[0]
        assert "target exit data" in final_fn
        assert "three_phase" in final_fn
        # No re-transfer at the passthrough phase.
        assert "map(to:three_phase" not in run_fn
        assert "map(tofrom:three_phase" not in run_fn

    def test_single_phase_var_stays_on_legacy_path(self, run_host_match, ccpp_context):
        """Used only in _run -- degenerate, stays on the structured
        !$omp target data path, no target enter/exit data anywhere."""
        fortran = _group_a_omp_fortran(run_host_match, ccpp_context)
        run_fn = _fn_body(fortran, "HoistSuiteA_ccpp_physics_run")
        assert "map(tofrom:single_phase" in run_fn or "single_phase" in run_fn.split("map(tofrom:")[1].split(")")[0]
        for fn_name in (
            "HoistSuiteA_ccpp_physics_run",
            "HoistSuiteA_ccpp_physics_initialize",
            "HoistSuiteA_ccpp_physics_finalize",
        ):
            body = _fn_body(fortran, fn_name)
            assert _no_omp_data_directive_line_mentions(body, "single_phase")


def _group_b_omp_fortran(run_host_match, ccpp_context) -> str:
    return _omp_fortran_output(
        run_host_match, ccpp_context,
        scheme_metas=[_GROUP_B_SCHEME],
        host_metas=[_GROUP_B_HOST],
        suite_xml=_GROUP_B_SUITE_XML,
    )


class TestOmpWholeSimulationScope:
    """Group B equivalent: register/initialize/finalize-anchored hoisting."""

    def test_init_run_only_var_exits_at_finalize_via_synthesized_ref(
        self, run_host_match, ccpp_context
    ):
        fortran = _group_b_omp_fortran(run_host_match, ccpp_context)
        init_fn = _fn_body(fortran, "HoistSuiteWholesim_ccpp_physics_initialize")
        run_fn = _fn_body(fortran, "HoistSuiteWholesim_ccpp_physics_run")
        finalize_fn = _fn_body(fortran, "HoistSuiteWholesim_ccpp_physics_finalize")

        assert "target enter data" in init_fn
        assert "wholesim_init_run" in init_fn
        assert "map(alloc:" in run_fn
        assert "wholesim_init_run" in run_fn.split("map(alloc:")[1].split(")")[0]
        assert "target exit data" in finalize_fn
        assert "wholesim_init_run" in finalize_fn

    def test_register_only_var_entry_anchor_is_register_not_initialize(
        self, run_host_match, ccpp_context
    ):
        fortran = _group_b_omp_fortran(run_host_match, ccpp_context)
        register_fn = _fn_body(fortran, "HoistSuiteWholesim_ccpp_physics_register")
        init_fn = _fn_body(fortran, "HoistSuiteWholesim_ccpp_physics_initialize")

        assert "target enter data" in register_fn
        assert "register_only" in register_fn
        assert _no_omp_data_directive_line_mentions(init_fn, "register_only")


class TestOmpUpdateClauseHoisting:
    """Group E equivalent: item 1(a)'s update-clause hoisting, extended to OMP."""

    def test_three_phase_update_var_syncs_once_each_way_nothing_at_passthrough(
        self, run_host_match, ccpp_context
    ):
        fortran = _omp_fortran_output(
            run_host_match, ccpp_context,
            scheme_metas=[_GROUP_E_SCHEME],
            host_metas=[_GROUP_E_HOST],
            suite_xml=_GROUP_E_SUITE_XML,
        )
        initial_fn = _fn_body(fortran, "HoistSuiteUpd_ccpp_physics_timestep_initial")
        run_fn = _fn_body(fortran, "HoistSuiteUpd_ccpp_physics_run")
        final_fn = _fn_body(fortran, "HoistSuiteUpd_ccpp_physics_timestep_final")

        assert "target update from(three_phase_upd" in initial_fn
        assert "target update to(three_phase_upd" not in initial_fn
        assert "target update to(three_phase_upd" in final_fn
        assert "target update from(three_phase_upd" not in final_fn
        # Nothing at all -- no directive, no clause -- at the passthrough phase.
        for line in run_fn.splitlines():
            stripped = line.strip()
            if "!$omp" in stripped:
                assert "three_phase_upd" not in stripped


class TestOmpMultiSuiteScoping:
    """Group C equivalent: a variable's classification in one suite must not
    be influenced by an unrelated suite's usage of a same-named host var."""

    def test_suite_a_run_only_usage_stays_degenerate_despite_suite_b(self, tmp_path):
        ctx = _make_context()
        module = _build_multi_suite_module(
            scheme_metas=[_GROUP_C_SCHEME_SUITE_A, _GROUP_C_SCHEME_SUITE_B],
            host_metas=[_GROUP_C_HOST],
            suite_xmls=[_GROUP_C_SUITE_A_XML, _GROUP_C_SUITE_B_XML],
            tmp_path=tmp_path,
            ctx=ctx,
        )
        SuiteCAP().apply(ctx, module)
        GPUDataPass(directive="omp").apply(ctx, module)
        CCPPCAP().apply(ctx, module)
        GPUCcppCapPass(directive="omp").apply(ctx, module)
        out = StringIO()
        print_to_ftn(module, out)
        fortran = out.getvalue()

        run_fn = _fn_body(fortran, "HoistSuiteMultiA_ccpp_physics_run")
        # Suite A's own usage (run-only) must stay degenerate/legacy: plain
        # !$omp target data map(tofrom:...), no target enter/exit data
        # forced by suite B's unrelated _init-phase usage of the same
        # variable name.
        assert "map(tofrom:shared_var" in run_fn
        assert _no_omp_data_directive_line_mentions(run_fn, "shared_var")


class TestOmpUpdateClauseRegression:
    """Group D equivalent: a single-phase (degenerate) update-clause
    variable stays on the legacy per-call target update from/to path,
    unaffected by hoisting."""

    def test_update_from_to_unaffected_by_hoisting(self, run_host_match, ccpp_context):
        fortran = _omp_fortran_output(
            run_host_match, ccpp_context,
            scheme_metas=[_GROUP_D_SCHEME],
            host_metas=[_GROUP_D_HOST],
            suite_xml=_GROUP_D_SUITE_XML,
        )
        run_fn = _fn_body(fortran, "HoistSuiteUpdate_ccpp_physics_run")
        assert "target update from(cpu_var" in run_fn
        assert "target update to(cpu_var" in run_fn
        assert "target enter data" not in run_fn
        assert "target exit data" not in run_fn


class TestOmpFinalizeAlongsidePerTimestepHoisting:
    """Group F equivalent: finalize can't anchor whole-sim scope alone, so a
    variable with a real per-timestep span plus an independent finalize
    touch still hoists the per-timestep span, leaving finalize on the
    legacy path -- for both the copyin/copy/copyout path and the update
    path."""

    def test_copy_var_hoists_per_timestep_finalize_touch_stays_legacy(
        self, run_host_match, ccpp_context
    ):
        fortran = _omp_fortran_output(
            run_host_match, ccpp_context,
            scheme_metas=[_GROUP_F_SCHEME],
            host_metas=[_GROUP_F_HOST],
            suite_xml=_GROUP_F_SUITE_XML,
        )
        initial_fn = _fn_body(fortran, "HoistSuiteFz_ccpp_physics_timestep_initial")
        run_fn = _fn_body(fortran, "HoistSuiteFz_ccpp_physics_run")
        finalize_fn = _fn_body(fortran, "HoistSuiteFz_ccpp_physics_finalize")

        assert "target enter data" in initial_fn
        assert "fz_var" in initial_fn
        assert "target exit data" in run_fn
        assert "fz_var" in run_fn
        # finalize's own touch is independent of the hoisted span: full
        # legacy structured transfer, no target enter/exit data.
        assert "map(tofrom:fz_var" in finalize_fn
        assert _no_omp_data_directive_line_mentions(finalize_fn, "fz_var")

    def test_update_var_hoists_per_timestep_finalize_touch_stays_legacy(
        self, run_host_match, ccpp_context
    ):
        fortran = _omp_fortran_output(
            run_host_match, ccpp_context,
            scheme_metas=[_GROUP_F_UPD_SCHEME],
            host_metas=[_GROUP_F_UPD_HOST],
            suite_xml=_GROUP_F_UPD_SUITE_XML,
        )
        initial_fn = _fn_body(fortran, "HoistSuiteFzUpd_ccpp_physics_timestep_initial")
        run_fn = _fn_body(fortran, "HoistSuiteFzUpd_ccpp_physics_run")
        finalize_fn = _fn_body(fortran, "HoistSuiteFzUpd_ccpp_physics_finalize")

        assert "target update from(fz_upd_var" in initial_fn
        assert "target update to(fz_upd_var" not in initial_fn
        assert "target update to(fz_upd_var" in run_fn
        assert "target update from(fz_upd_var" not in run_fn
        # finalize's own touch is independent of the hoisted span: full
        # legacy per-call from+to pair, right at its own call site.
        assert "target update from(fz_upd_var" in finalize_fn
        assert "target update to(fz_upd_var" in finalize_fn
