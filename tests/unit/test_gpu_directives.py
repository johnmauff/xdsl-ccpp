"""Unit tests for GPU data-directive insertion across all lifecycle phases.

generate-gpu-ccpp-cap (GPUCcppCapPass) and generate-gpu-data (GPUDataPass)
originally only ever processed the *_ccpp_physics_run / *_suite_physics
dispatch -- register/initialize/finalize/timestep_initial/timestep_final
never got !$acc data wrapping around their suite callee calls, even when a
scheme declared memory_space=device args on those entry points. These tests
cover the fix: every lifecycle phase should get the same treatment as run.

They also cover a latent bug found while writing these tests: GPUDataPass's
_get_device_args used to hardcode "<scheme>_run" as the argument table to
inspect regardless of which entry point was actually being called, so a
device-only (no host match) variable declared only on a non-run entry point
would silently get no directive at all (or, worse, pick up an unrelated
_run-entry argument list if one happened to exist).
"""

from io import StringIO

import pytest

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml
from xdsl_ccpp.backend.print_ftn import print_to_ftn
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.ccpp_cap import CCPPCAP
from xdsl_ccpp.transforms.gpu_ccpp_cap_pass import GPUCcppCapPass
from xdsl_ccpp.transforms.gpu_data_pass import GPUDataPass
from xdsl_ccpp.transforms.suite_cap import SuiteCAP

# ── metadata fixtures ─────────────────────────────────────────────────────────
#
# test_gpu_scheme declares:
#   - "hosted"   -- device-resident, host also keeps it on device (memory_space
#                   = device on both sides) -> should resolve to present().
#   - "hosted2"  -- device-resident, but the host keeps it on the CPU (no
#                   memory_space on the host side) -> should resolve to
#                   copyin/copy/copyout depending on intent.
#   - "scratch"  -- device-resident with NO host variable at all (optional, so
#                   HostVariableMatchPass doesn't reject it as unmatched) ->
#                   has no ccpp_cap-level host var name to hang a present()/
#                   copyin() on, so GPUCcppCapPass must leave it alone and
#                   GPUDataPass must wrap it at the suite_cap level instead.
#
# Each lifecycle entry point below is deliberately given a different subset
# of these three, so a bug that mixes up *which* entry point's argument list
# is being read (e.g. always reading "_run") would produce a directive with
# the wrong variable set -- or none at all, for entry points with no _run
# table to fall back to.

_SCHEME_META = f"""\
[ccpp-table-properties]
  name = test_gpu_scheme
  type = scheme
[ccpp-arg-table]
  name = test_gpu_scheme_register
  type = scheme
{CCPP_MANDATORY_ARGS}
[ccpp-arg-table]
  name = test_gpu_scheme_init
  type = scheme
[ hosted ]
  standard_name = test_hosted_var
  long_name = host-matched var kept resident on device by the host
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  memory_space = device
  intent = in
{CCPP_MANDATORY_ARGS}
[ccpp-arg-table]
  name = test_gpu_scheme_timestep_init
  type = scheme
[ scratch ]
  standard_name = test_scratch_var
  long_name = device-only scratch array with no host match
  units = none
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  memory_space = device
  intent = inout
  optional = .true.
{CCPP_MANDATORY_ARGS}
[ccpp-arg-table]
  name = test_gpu_scheme_timestep_final
  type = scheme
[ hosted2 ]
  standard_name = test_hosted_var2
  long_name = host-matched var kept on the CPU by the host
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  memory_space = device
  intent = in
{CCPP_MANDATORY_ARGS}
[ccpp-arg-table]
  name = test_gpu_scheme_finalize
  type = scheme
{CCPP_MANDATORY_ARGS}
[ccpp-arg-table]
  name = test_gpu_scheme_run
  type = scheme
[ hosted ]
  standard_name = test_hosted_var
  long_name = host-matched var kept resident on device by the host
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  memory_space = device
  intent = inout
{CCPP_MANDATORY_ARGS}
"""

_HOST_META = """\
[ccpp-table-properties]
  name = test_gpu_host
  type = module
[ccpp-arg-table]
  name = test_gpu_host
  type = module
[ hosted ]
  standard_name = test_hosted_var
  long_name = host var kept resident on device
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  memory_space = device
[ hosted2 ]
  standard_name = test_hosted_var2
  long_name = host var kept on the CPU
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
"""

_SUITE_XML = minimal_suite_xml("test_gpu_scheme", suite_name="test_gpu_suite")


def _fortran_output(run_host_match, ccpp_context) -> str:
    """Run the full pipeline, including both GPU passes, through the Fortran
    printer and return the combined output (all files concatenated)."""
    module = run_host_match(
        scheme_metas=[_SCHEME_META],
        host_metas=[_HOST_META],
        suite_xml=_SUITE_XML,
    )
    ArgOwnershipPass().apply(ccpp_context, module)
    SuiteCAP().apply(ccpp_context, module)
    GPUDataPass(directive="acc").apply(ccpp_context, module)
    CCPPCAP().apply(ccpp_context, module)
    GPUCcppCapPass(directive="acc").apply(ccpp_context, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


class TestGPUCcppCapLifecycleCoverage:
    """generate-gpu-ccpp-cap: every lifecycle dispatcher (not just _run) must
    wrap its suite callee call in an !$acc data region when the scheme
    declares memory_space=device args for that entry point."""

    def test_run_still_wraps_present_var(self, run_host_match, ccpp_context):
        """Regression guard: the pre-existing _ccpp_physics_run behavior is
        unaffected by refactoring _process_run_fn to share _wrap_scheme_call
        with the new lifecycle path."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        assert "TestGpu_ccpp_physics_run" in fortran
        run_fn = fortran.split("subroutine TestGpu_ccpp_physics_run")[1]
        run_fn = run_fn.split("end subroutine TestGpu_ccpp_physics_run")[0]
        assert "present(hosted" in run_fn

    def test_initialize_wraps_present_var(self, run_host_match, ccpp_context):
        """test_gpu_scheme_init declares 'hosted' (device+device -> present).
        Previously initialize was never scanned at all, so no directive of
        any kind would have appeared here."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        init_fn = fortran.split("subroutine TestGpu_ccpp_physics_initialize")[1]
        init_fn = init_fn.split("end subroutine TestGpu_ccpp_physics_initialize")[0]
        assert "present(hosted" in init_fn

    def test_timestep_final_wraps_copyin_var(self, run_host_match, ccpp_context):
        """test_gpu_scheme_timestep_final declares 'hosted2' (device scheme +
        host-resident model var, intent=in -> copyin). This is the exact
        shape of the original bug report: a device var declared only on a
        timestep_final entry point, with no directive ever generated."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        final_fn = fortran.split("subroutine TestGpu_ccpp_physics_timestep_final")[1]
        final_fn = final_fn.split("end subroutine TestGpu_ccpp_physics_timestep_final")[0]
        assert "copyin(hosted2" in final_fn

    def test_register_is_untouched_noop(self, run_host_match, ccpp_context):
        """No var in this fixture is referenced at the register phase (the
        earliest 'hosted' is used is 'initialize'), so register must not
        gain a spurious !$acc data region -- not even from residency
        establishment, whose entry anchor for 'hosted' is 'initialize'."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        body = fortran.split("subroutine TestGpu_ccpp_physics_register")[1]
        body = body.split("end subroutine TestGpu_ccpp_physics_register")[0]
        assert "!$acc" not in body

    def test_finalize_gets_synthesized_residency_exit_for_wholesim_var(
        self, run_host_match, ccpp_context
    ):
        """'hosted' (device+device, first used at 'initialize' -- a one-time
        phase) gets whole-simulation-scope residency established
        (_analyze_one_suite_residency): exit is always finalize, via a
        synthesized HostVarRefOp since finalize's own schemes never
        reference 'hosted' at all -- same mechanism already used for
        copy-family/update vars' whole-sim exit anchor. This is new,
        correct behavior (the fix for the reported "PRESENT clause was not
        found on device" runtime error), not a regression: finalize
        previously had no clause-routing reason to be touched, but it was
        never claimed to have no *residency* reason either."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        body = fortran.split("subroutine TestGpu_ccpp_physics_finalize")[1]
        body = body.split("end subroutine TestGpu_ccpp_physics_finalize")[0]
        assert "exit data copyout(hosted" in body

    def test_timestep_initial_has_no_ccpp_cap_directive_for_hostless_var(
        self, run_host_match, ccpp_context
    ):
        """'scratch' has no host match at all, so GPUCcppCapPass (which only
        knows host variable names) must not try to emit a present()/copyin()
        for it -- that's GPUDataPass's job, one level down. 'scratch' still
        legitimately appears here as the hoisted local alloca 'lc_scratch',
        so assert on the absence of an acc clause mentioning it specifically,
        not on the bare substring."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        initial_fn = fortran.split("subroutine TestGpu_ccpp_physics_timestep_initial")[1]
        initial_fn = initial_fn.split("end subroutine TestGpu_ccpp_physics_timestep_initial")[0]
        assert "!$acc" not in initial_fn
        for clause in ("present(scratch", "copyin(scratch", "copy(scratch", "copyout(scratch"):
            assert clause not in initial_fn


class TestGPUDataSuiteCapLifecycleCoverage:
    """generate-gpu-data: the suite_cap-level lifecycle subroutines must wrap
    a *hostless* device var, using that specific entry point's own argument
    table (not always '<scheme>_run')."""

    def test_timestep_initial_wraps_hostless_scratch_var(self, run_host_match, ccpp_context):
        """'scratch' is declared only on test_gpu_scheme_timestep_init, has no
        host match, and test_gpu_scheme has no '_run' table entry sharing
        that name -- so the old hardcoded '<scheme>_run' lookup would have
        found nothing here at all."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        suite_fn = fortran.split("subroutine test_gpu_suite_suite_timestep_initial")[1]
        suite_fn = suite_fn.split("end subroutine test_gpu_suite_suite_timestep_initial")[0]
        assert "copyin(scratch" in suite_fn or "copy(scratch" in suite_fn

    def test_run_hostvar_gets_no_suite_cap_directive(self, run_host_match, ccpp_context):
        """'hosted' has a host match, so it's handled entirely at the
        ccpp_cap level (GPUCcppCapPass) -- GPUDataPass must not also wrap it
        at the suite_cap level, which would create a redundant nested data
        region."""
        fortran = _fortran_output(run_host_match, ccpp_context)
        suite_fn = fortran.split("subroutine test_gpu_suite_suite_physics")[1]
        suite_fn = suite_fn.split("end subroutine test_gpu_suite_suite_physics")[0]
        assert "!$acc" not in suite_fn

    def test_finalize_and_register_are_untouched_noops(self, run_host_match, ccpp_context):
        fortran = _fortran_output(run_host_match, ccpp_context)
        for fn_name in (
            "test_gpu_suite_suite_register",
            "test_gpu_suite_suite_finalize",
        ):
            body = fortran.split(f"subroutine {fn_name}")[1]
            body = body.split(f"end subroutine {fn_name}")[0]
            assert "!$acc" not in body, f"unexpected acc directive in {fn_name}"


class TestGetSchemeName:
    """GPUDataPass._get_scheme_name must recognize both spellings of the
    per-timestep entry-point suffix. ccpp_cap.py's lifecycle_specs uses
    '_timestep_initialize'/'_timestep_finalize' as the canonical scheme-level
    postfix (e.g. examples/capgen/scheme/temp_set.meta's
    temp_set_timestep_initialize) with '_timestep_init'/'_timestep_final'
    accepted as an alias (lifecycle_cap.py's _lc_postfix_aliases, matching
    examples/kessler's kessler_update_timestep_init/_final). Missing either
    spelling here means calls using it are silently skipped -- no data
    region inserted, no error raised. Also covers the ordering hazard: a
    shorter suffix ('_init'/'_finalize'/'_timestep_init'/'_timestep_final')
    that happens to be a trailing substring of a longer one must not be
    checked first, or it strips the wrong length."""

    @pytest.mark.parametrize(
        "callee_name,expected",
        [
            ("temp_set_timestep_initialize", "temp_set"),
            ("temp_set_timestep_finalize", "temp_set"),
            ("kessler_update_timestep_init", "kessler_update"),
            ("kessler_update_timestep_final", "kessler_update"),
            ("hello_scheme_run", "hello_scheme"),
            ("hello_scheme_init", "hello_scheme"),
            ("hello_scheme_finalize", "hello_scheme"),
            ("hello_scheme_register", "hello_scheme"),
            ("unrelated_name", None),
        ],
    )
    def test_recognizes_both_timestep_spellings(self, callee_name, expected):
        assert GPUDataPass()._get_scheme_name(callee_name) == expected


# ── diverged-clause fixtures ───────────────────────────────────────────────────
#
# Two (or three) schemes in the *same* group/suite reference the same
# host-matched variable ("conflict_var") with genuinely incompatible
# memory_space declarations against the same device-resident host var:
# scheme_a wants present() (device scheme + device host), scheme_b wants
# update self/device (host scheme + device host). This is the real shape
# backlog item (b) describes -- and the exact scenario
# examples/advection_flat_host's qv was built to reproduce, just as a small
# synthetic fixture here instead of requiring the real example. Previously
# (backlog item (c)) this raised a hard error; it's now routed correctly
# instead -- see gpu_data_pass.py's _process_diverged_host_vars.

_CONFLICT_SCHEME_A = f"""\
[ccpp-table-properties]
  name = test_conflict_scheme_a
  type = scheme
[ccpp-arg-table]
  name = test_conflict_scheme_a_run
  type = scheme
[ qv_a ]
  standard_name = test_conflict_var
  long_name = wants present -- device scheme, device host
  units = kg kg-1
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  memory_space = device
  intent = inout
{CCPP_MANDATORY_ARGS}
"""

_CONFLICT_SCHEME_B = f"""\
[ccpp-table-properties]
  name = test_conflict_scheme_b
  type = scheme
[ccpp-arg-table]
  name = test_conflict_scheme_b_run
  type = scheme
[ qv_b ]
  standard_name = test_conflict_var
  long_name = wants update -- host scheme, device host
  units = kg kg-1
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  intent = inout
{CCPP_MANDATORY_ARGS}
"""

# A second "wants update" scheme, so two consecutive update-only calls (b
# then c, with a in between wanting present) exercise run-coalescing: only
# ONE update self/device pair should span scheme_b -> scheme_c, not two.
_CONFLICT_SCHEME_C = f"""\
[ccpp-table-properties]
  name = test_conflict_scheme_c
  type = scheme
[ccpp-arg-table]
  name = test_conflict_scheme_c_run
  type = scheme
[ qv_c ]
  standard_name = test_conflict_var
  long_name = also wants update -- host scheme, device host
  units = kg kg-1
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  intent = inout
{CCPP_MANDATORY_ARGS}
"""

_CONFLICT_HOST_META = """\
[ccpp-table-properties]
  name = test_conflict_host
  type = module
[ccpp-arg-table]
  name = test_conflict_host
  type = module
[ conflict_var ]
  standard_name = test_conflict_var
  long_name = host var kept resident on device
  units = kg kg-1
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  memory_space = device
"""

_CONFLICT_SUITE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_conflict_suite" version="1.0">
  <group name="physics">
    <scheme>test_conflict_scheme_a</scheme>
    <scheme>test_conflict_scheme_b</scheme>
  </group>
</suite>
"""

_CONFLICT_SUITE_XML_3 = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_conflict_suite" version="1.0">
  <group name="physics">
    <scheme>test_conflict_scheme_a</scheme>
    <scheme>test_conflict_scheme_b</scheme>
    <scheme>test_conflict_scheme_c</scheme>
  </group>
</suite>
"""


def _diverged_fortran_output(scheme_metas, suite_xml, run_host_match, ccpp_context) -> str:
    module = run_host_match(
        scheme_metas=scheme_metas,
        host_metas=[_CONFLICT_HOST_META],
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


class TestGPUDivergedClauseRouting:
    """Backlog item (b): host vars where different schemes in the same
    suite genuinely disagree about present-vs-update treatment get routed
    per individual scheme call (GPUDataPass, at the suite_cap level)
    instead of raising -- GPUCcppCapPass excludes them entirely from its
    whole-suite hoisting (gpu_ccpp_cap_pass.py's _analyze_one_suite).
    """

    def test_no_error_raised(self, run_host_match, ccpp_context):
        _diverged_fortran_output(
            [_CONFLICT_SCHEME_A, _CONFLICT_SCHEME_B], _CONFLICT_SUITE_XML,
            run_host_match, ccpp_context,
        )

    def test_present_scheme_gets_present_clause(self, run_host_match, ccpp_context):
        fortran = _diverged_fortran_output(
            [_CONFLICT_SCHEME_A, _CONFLICT_SCHEME_B], _CONFLICT_SUITE_XML,
            run_host_match, ccpp_context,
        )
        suite_fn = fortran.split("subroutine test_conflict_suite_suite_physics")[1]
        suite_fn = suite_fn.split("end subroutine test_conflict_suite_suite_physics")[0]
        assert "present(qv_a" in suite_fn

    def test_update_scheme_gets_update_clauses(self, run_host_match, ccpp_context):
        fortran = _diverged_fortran_output(
            [_CONFLICT_SCHEME_A, _CONFLICT_SCHEME_B], _CONFLICT_SUITE_XML,
            run_host_match, ccpp_context,
        )
        suite_fn = fortran.split("subroutine test_conflict_suite_suite_physics")[1]
        suite_fn = suite_fn.split("end subroutine test_conflict_suite_suite_physics")[0]
        assert "update self(qv_a" in suite_fn
        assert "update device(qv_a" in suite_fn

    def test_no_clause_directive_at_ccpp_cap_level(self, run_host_match, ccpp_context):
        """GPUCcppCapPass must not do per-call *clause routing* for this var
        -- it has no VarLifetime entry once excluded as diverged, so
        present()/update self/device are still entirely GPUDataPass's job
        (see test_present_scheme_gets_present_clause/
        test_update_scheme_gets_update_clauses above, both scoped to
        test_conflict_suite_suite_physics -- the suite_cap level).

        It *does* now get residency established at the ccpp_cap level
        (_analyze_one_suite_residency doesn't care about divergence, only
        whether model_var_memory_space=="device") -- see
        test_ccpp_cap_level_gets_residency_copy_region below. The two are
        deliberately independent."""
        fortran = _diverged_fortran_output(
            [_CONFLICT_SCHEME_A, _CONFLICT_SCHEME_B], _CONFLICT_SUITE_XML,
            run_host_match, ccpp_context,
        )
        run_fn = fortran.split("subroutine TestConflict_ccpp_physics_run")
        assert len(run_fn) > 1
        body = run_fn[1].split("end subroutine TestConflict_ccpp_physics_run")[0]
        assert "present(" not in body
        assert "update self(" not in body
        assert "update device(" not in body

    def test_ccpp_cap_level_gets_residency_copy_region(self, run_host_match, ccpp_context):
        """conflict_var is used only at the 'run' phase (degenerate, single-
        phase) in both schemes -- residency establishment wraps the whole
        suite-part dispatch call in a plain per-call copy() region at the
        ccpp_cap level, exactly like copy-family's own degenerate treatment,
        independent of the diverged present/update clause routing that still
        happens one level down in GPUDataPass."""
        fortran = _diverged_fortran_output(
            [_CONFLICT_SCHEME_A, _CONFLICT_SCHEME_B], _CONFLICT_SUITE_XML,
            run_host_match, ccpp_context,
        )
        run_fn = fortran.split("subroutine TestConflict_ccpp_physics_run")[1]
        run_fn = run_fn.split("end subroutine TestConflict_ccpp_physics_run")[0]
        assert "!$acc data copy(conflict_var" in run_fn
        assert "!$acc end data" in run_fn

    def test_consecutive_update_calls_coalesce_into_one_pair(self, run_host_match, ccpp_context):
        """scheme_b and scheme_c both want update, back-to-back after
        scheme_a's present call -- only ONE update self/device pair should
        span b->c, not one per call."""
        fortran = _diverged_fortran_output(
            [_CONFLICT_SCHEME_A, _CONFLICT_SCHEME_B, _CONFLICT_SCHEME_C],
            _CONFLICT_SUITE_XML_3, run_host_match, ccpp_context,
        )
        suite_fn = fortran.split("subroutine test_conflict_suite_suite_physics")[1]
        suite_fn = suite_fn.split("end subroutine test_conflict_suite_suite_physics")[0]
        assert suite_fn.count("update self(") == 1
        assert suite_fn.count("update device(") == 1
        # Exactly one present() pair too (scheme_a's own call only).
        assert suite_fn.count("present(") == 1


# ── DDT-member validation ───────────────────────────────────────────────────────
#
# examples/advection's real temp/qv are DDT members, not plain host vars --
# GPUCcppCapPass's HostVarRefOp-based lookup can't see them at all (backlog
# gap #5), but GPUDataPass's diverged-var routing operates on suite_cap's
# already-resolved plain block arguments, so it should work correctly for a
# DDT member too. Validated directly here rather than just asserted.

_DDT_TYPE = """\
[ccpp-table-properties]
  name = test_ddt_type
  type = ddt
[ccpp-arg-table]
  name = test_ddt_type
  type = ddt
[ qv_member ]
  standard_name = test_ddt_conflict_var
  units = kg kg-1
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
  memory_space = device
"""

_DDT_HOST_MOD = """\
[ccpp-table-properties]
  name = test_ddt_host_mod
  type = module
[ccpp-arg-table]
  name = test_ddt_host_mod
  type = module
[ phys_state ]
  standard_name = physics_state_instance
  type = test_ddt_type
  units = DDT
  dimensions = ()
"""

_DDT_CONFLICT_SCHEME_A = f"""\
[ccpp-table-properties]
  name = test_ddt_conflict_scheme_a
  type = scheme
[ccpp-arg-table]
  name = test_ddt_conflict_scheme_a_run
  type = scheme
[ qv_a ]
  standard_name = test_ddt_conflict_var
  units = kg kg-1
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  memory_space = device
  intent = inout
{CCPP_MANDATORY_ARGS}
"""

_DDT_CONFLICT_SCHEME_B = f"""\
[ccpp-table-properties]
  name = test_ddt_conflict_scheme_b
  type = scheme
[ccpp-arg-table]
  name = test_ddt_conflict_scheme_b_run
  type = scheme
[ qv_b ]
  standard_name = test_ddt_conflict_var
  units = kg kg-1
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  intent = inout
{CCPP_MANDATORY_ARGS}
"""

_DDT_CONFLICT_SUITE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="test_ddt_conflict_suite" version="1.0">
  <group name="physics">
    <scheme>test_ddt_conflict_scheme_a</scheme>
    <scheme>test_ddt_conflict_scheme_b</scheme>
  </group>
</suite>
"""


class TestGPUDivergedClauseRoutingDDTMember:
    """Same divergence scenario as TestGPUDivergedClauseRouting, but the
    host var is a DDT member (test_ddt_host_mod%phys_state%qv_member)
    instead of a plain module variable -- confirms the DDT-member side
    benefit concretely rather than just asserting it."""

    def test_routes_correctly_for_ddt_member(self, run_host_match, ccpp_context):
        module = run_host_match(
            scheme_metas=[_DDT_CONFLICT_SCHEME_A, _DDT_CONFLICT_SCHEME_B],
            host_metas=[_DDT_TYPE, _DDT_HOST_MOD],
            suite_xml=_DDT_CONFLICT_SUITE_XML,
        )
        ArgOwnershipPass().apply(ccpp_context, module)
        SuiteCAP().apply(ccpp_context, module)
        GPUDataPass(directive="acc").apply(ccpp_context, module)
        CCPPCAP().apply(ccpp_context, module)
        GPUCcppCapPass(directive="acc").apply(ccpp_context, module)
        out = StringIO()
        print_to_ftn(module, out)
        fortran = out.getvalue()

        suite_fn = fortran.split("subroutine test_ddt_conflict_suite_suite_physics")[1]
        suite_fn = suite_fn.split("end subroutine test_ddt_conflict_suite_suite_physics")[0]
        assert "present(qv_a" in suite_fn
        assert "update self(qv_a" in suite_fn
        assert "update device(qv_a" in suite_fn
