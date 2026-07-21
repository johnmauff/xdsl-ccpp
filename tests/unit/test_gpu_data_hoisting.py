"""Unit tests for cross-function OpenACC data hoisting in GPUCcppCapPass.

Before this feature, every lifecycle dispatcher independently opened and
closed its own structured `!$acc data copyin/copy/copyout ... end data`
region around its own suite-callee call -- so a variable used across e.g.
both `_run` and `_timestep_final` was transferred fresh on every single
call, even though both happen back-to-back within one timestep. Confirmed
this session with examples/kessler: `cpair` (device/host, intent=in) is
referenced by both `kessler_run`'s table and `kessler_update_timestep_final`'s
table.

These tests cover the fix: for each host variable, GPUCcppCapPass now
computes the actual earliest/latest lifecycle phase it's used in (not a
hardcoded anchor) and emits a single `!$acc enter data`/`exit data` pair
spanning that range, with `present()` at any phase strictly in between,
instead of re-transferring on every call.
"""

from io import StringIO

from xdsl.context import Context
from xdsl.dialects.builtin import ModuleOp
from xdsl.universe import Universe

from tests.unit.helpers import CCPP_MANDATORY_ARGS, minimal_suite_xml
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


def _fortran_output(run_host_match, ccpp_context, scheme_metas, host_metas, suite_xml) -> str:
    """Run the full pipeline, including both GPU passes, through the Fortran
    printer and return the combined output (all files concatenated)."""
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
    body = fortran.split(f"subroutine {fn_name}")[1]
    return body.split(f"end subroutine {fn_name}")[0]


def _var_in_clause(body: str, clause: str, var_name: str) -> bool:
    """True if var_name appears inside a `clause(...)` argument list anywhere
    in body, e.g. clause="present" matches `present(always_present,
    three_phase)` even when var_name isn't the first name listed -- multiple
    present-clause vars at the same call site are combined into one clause,
    so a plain `f"{clause}({var_name}"` substring check only works when
    var_name happens to be listed first."""
    for line in body.splitlines():
        if f"{clause}(" not in line:
            continue
        after = line.split(f"{clause}(", 1)[1]
        args = after.split(")", 1)[0]
        names = [n.strip() for n in args.split(",")]
        if var_name in names:
            return True
    return False


def _no_data_directive_line_mentions(body: str, var_name: str) -> bool:
    """True if no `!$acc enter data`/`exit data` line in body references
    var_name -- unlike a whole-body substring check, this doesn't false-
    positive when var_name is legitimately hoisted on an unrelated line
    (e.g. another variable's enter/exit data in the same function body)."""
    for line in body.splitlines():
        stripped = line.strip()
        if ("enter data" in stripped or "exit data" in stripped) and var_name in stripped:
            return False
    return True


def _no_acc_directive_line_mentions(body: str, var_name: str) -> bool:
    """True if no `!$acc ...` line in body references var_name at all --
    unlike a whole-body substring check, this doesn't false-positive on the
    variable's legitimate appearance as a plain call argument (e.g. a
    hoisted "update" variable's passthrough phase, where it's still passed
    to the scheme call but gets no directive of any kind)."""
    for line in body.splitlines():
        stripped = line.strip()
        if "!$acc" in stripped and var_name in stripped:
            return False
    return True


def _device_arg(std_name: str, intent: str = "in") -> str:
    return f"""\
  standard_name = {std_name}
  long_name = test device var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  memory_space = device
  intent = {intent}
"""


def _host_module_meta(module_name: str, host_vars_meta: str) -> str:
    return f"""\
[ccpp-table-properties]
  name = {module_name}
  type = module
[ccpp-arg-table]
  name = {module_name}
  type = module
{host_vars_meta}
"""


def _host_var_block(local_name: str, std_name: str, device: bool = False) -> str:
    lines = f"""\
[ {local_name} ]
  standard_name = {std_name}
  long_name = test host var
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_dimension, vertical_layer_dimension)
"""
    if device:
        lines += "  memory_space = device\n"
    return lines


# ── Group A: single suite, two schemes, per-timestep hoisting ────────────────
#
# scheme_a declares only a _run entry; scheme_b declares _timestep_initial,
# _run (implicitly via not appearing there), and _timestep_final entries --
# spread across two schemes so the cross-scheme union (already exercised by
# the pre-existing clause_map logic) is also exercised for phase tracking.
#
#   cross_var      -- scheme_a's _run + scheme_b's _timestep_final only.
#                      Mirrors the real kessler cpair shape: entry=run,
#                      exit=timestep_final, spanning two different schemes.
#   three_phase    -- scheme_b's _timestep_initial + _run + _timestep_final.
#                      entry=timestep_initial, exit=timestep_final,
#                      present() passthrough at run.
#   single_phase   -- scheme_a's _run only. Degenerate: stays on the legacy
#                      AccDataBeginOp/AccDataEndOp path, no enter/exit-data.
#   always_present -- scheme_a's _init + _run, memory_space=device on BOTH
#                      scheme and host sides -> present() throughout, must
#                      NOT get enter/exit-data despite spanning two phases
#                      (present-clause vars are excluded from hoisting
#                      entirely -- the host model owns their residency, not
#                      this framework).

_GROUP_A_SCHEME_A = f"""\
[ccpp-table-properties]
  name = hoist_scheme_a
  type = scheme
[ccpp-arg-table]
  name = hoist_scheme_a_init
  type = scheme
[ always_present ]
{_device_arg("test_always_present_var")}
{CCPP_MANDATORY_ARGS}
[ccpp-arg-table]
  name = hoist_scheme_a_run
  type = scheme
[ cross_var ]
{_device_arg("test_cross_var")}
[ single_phase ]
{_device_arg("test_single_phase_var")}
[ always_present ]
{_device_arg("test_always_present_var")}
{CCPP_MANDATORY_ARGS}
"""

_GROUP_A_SCHEME_B = f"""\
[ccpp-table-properties]
  name = hoist_scheme_b
  type = scheme
[ccpp-arg-table]
  name = hoist_scheme_b_timestep_init
  type = scheme
[ three_phase ]
{_device_arg("test_three_phase_var", intent="inout")}
{CCPP_MANDATORY_ARGS}
[ccpp-arg-table]
  name = hoist_scheme_b_run
  type = scheme
[ three_phase ]
{_device_arg("test_three_phase_var", intent="inout")}
{CCPP_MANDATORY_ARGS}
[ccpp-arg-table]
  name = hoist_scheme_b_timestep_final
  type = scheme
[ cross_var ]
{_device_arg("test_cross_var")}
[ three_phase ]
{_device_arg("test_three_phase_var", intent="out")}
{CCPP_MANDATORY_ARGS}
"""

_GROUP_A_HOST = _host_module_meta(
    "hoist_host_a",
    _host_var_block("cross_var", "test_cross_var")
    + _host_var_block("three_phase", "test_three_phase_var")
    + _host_var_block("single_phase", "test_single_phase_var")
    + _host_var_block("always_present", "test_always_present_var", device=True),
)

_GROUP_A_SUITE_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<suite name="hoist_suite_a" version="1.0">
  <group name="physics">
    <scheme>hoist_scheme_a</scheme>
    <scheme>hoist_scheme_b</scheme>
  </group>
</suite>
"""


def _group_a_fortran(run_host_match, ccpp_context) -> str:
    return _fortran_output(
        run_host_match, ccpp_context,
        scheme_metas=[_GROUP_A_SCHEME_A, _GROUP_A_SCHEME_B],
        host_metas=[_GROUP_A_HOST],
        suite_xml=_GROUP_A_SUITE_XML,
    )


class TestPerTimestepHoisting:
    """Group A: real cpair-shaped hoisting across two schemes in one suite."""

    def test_cross_scheme_var_enters_at_run_exits_at_timestep_final(
        self, run_host_match, ccpp_context
    ):
        fortran = _group_a_fortran(run_host_match, ccpp_context)
        run_fn = _fn_body(fortran, "HoistSuiteA_ccpp_physics_run")
        final_fn = _fn_body(fortran, "HoistSuiteA_ccpp_physics_timestep_final")

        assert "enter data" in run_fn
        assert "copyin(cross_var" in run_fn
        assert "exit data" in final_fn
        assert "cross_var" in final_fn
        # The old per-call re-transfer must be gone: timestep_final must not
        # ALSO independently copyin cross_var via the legacy structured path.
        assert "copyin(cross_var" not in final_fn

    def test_three_phase_var_hoists_with_passthrough_present_at_run(
        self, run_host_match, ccpp_context
    ):
        fortran = _group_a_fortran(run_host_match, ccpp_context)
        initial_fn = _fn_body(fortran, "HoistSuiteA_ccpp_physics_timestep_initial")
        run_fn = _fn_body(fortran, "HoistSuiteA_ccpp_physics_run")
        final_fn = _fn_body(fortran, "HoistSuiteA_ccpp_physics_timestep_final")

        assert "enter data" in initial_fn
        assert "three_phase" in initial_fn
        assert _var_in_clause(run_fn, "present", "three_phase")
        assert "exit data" in final_fn
        assert "three_phase" in final_fn
        # No re-transfer at the passthrough phase.
        assert "copyin(three_phase" not in run_fn
        assert "copy(three_phase" not in run_fn

    def test_single_phase_var_stays_on_legacy_path(self, run_host_match, ccpp_context):
        """Used only in _run -- hoisting would gain nothing, so this must
        stay on the original AccDataBeginOp/AccDataEndOp structured region,
        with no enter/exit-data anywhere referencing it."""
        fortran = _group_a_fortran(run_host_match, ccpp_context)
        run_fn = _fn_body(fortran, "HoistSuiteA_ccpp_physics_run")

        assert "copy(single_phase" in run_fn or "copyin(single_phase" in run_fn
        for fn_name in (
            "HoistSuiteA_ccpp_physics_run",
            "HoistSuiteA_ccpp_physics_initialize",
            "HoistSuiteA_ccpp_physics_finalize",
        ):
            body = _fn_body(fortran, fn_name)
            assert _no_data_directive_line_mentions(body, "single_phase")

    def test_present_clause_var_excluded_from_hoisting(self, run_host_match, ccpp_context):
        """always_present spans _init and _run (two phases) but is a
        present-clause variable (scheme=device + model=device) -- it must
        stay plain present() at both, with NO enter/exit-data, since CCPP
        doesn't own its residency (the host model does)."""
        fortran = _group_a_fortran(run_host_match, ccpp_context)
        init_fn = _fn_body(fortran, "HoistSuiteA_ccpp_physics_initialize")
        run_fn = _fn_body(fortran, "HoistSuiteA_ccpp_physics_run")

        assert "present(always_present" in init_fn
        assert "present(always_present" in run_fn
        for fn_name in ("HoistSuiteA_ccpp_physics_initialize", "HoistSuiteA_ccpp_physics_run"):
            body = _fn_body(fortran, fn_name)
            assert _no_data_directive_line_mentions(body, "always_present")


# ── Group B: whole-simulation scope edge cases ────────────────────────────────
#
#   wholesim_init_run -- used in _init and _run only (no _finalize
#                        reference at all). Exercises the synthesized
#                        HostVarRefOp path: exit is forced to finalize even
#                        though finalize's own schemes never touch it.
#   register_only     -- used only in _register. Exercises that the entry
#                        anchor is the actual earliest one-time phase used
#                        (register), not hardcoded to initialize.

_GROUP_B_SCHEME = f"""\
[ccpp-table-properties]
  name = hoist_scheme_wholesim
  type = scheme
[ccpp-arg-table]
  name = hoist_scheme_wholesim_register
  type = scheme
[ register_only ]
{_device_arg("test_register_only_var")}
{CCPP_MANDATORY_ARGS}
[ccpp-arg-table]
  name = hoist_scheme_wholesim_init
  type = scheme
[ wholesim_init_run ]
{_device_arg("test_wholesim_init_run_var")}
{CCPP_MANDATORY_ARGS}
[ccpp-arg-table]
  name = hoist_scheme_wholesim_run
  type = scheme
[ wholesim_init_run ]
{_device_arg("test_wholesim_init_run_var", intent="inout")}
{CCPP_MANDATORY_ARGS}
"""

_GROUP_B_HOST = _host_module_meta(
    "hoist_host_wholesim",
    _host_var_block("register_only", "test_register_only_var")
    + _host_var_block("wholesim_init_run", "test_wholesim_init_run_var"),
)

_GROUP_B_SUITE_XML = minimal_suite_xml("hoist_scheme_wholesim", suite_name="hoist_suite_wholesim")


def _group_b_fortran(run_host_match, ccpp_context) -> str:
    return _fortran_output(
        run_host_match, ccpp_context,
        scheme_metas=[_GROUP_B_SCHEME],
        host_metas=[_GROUP_B_HOST],
        suite_xml=_GROUP_B_SUITE_XML,
    )


class TestWholeSimulationScope:
    """Group B: register/initialize/finalize-anchored hoisting."""

    def test_init_run_only_var_exits_at_finalize_via_synthesized_ref(
        self, run_host_match, ccpp_context
    ):
        """wholesim_init_run has no natural argument in _finalize's own
        scheme tables, so this specifically exercises the module-wide donor
        scan + cloned HostVarRefOp path."""
        fortran = _group_b_fortran(run_host_match, ccpp_context)
        init_fn = _fn_body(fortran, "HoistSuiteWholesim_ccpp_physics_initialize")
        run_fn = _fn_body(fortran, "HoistSuiteWholesim_ccpp_physics_run")
        finalize_fn = _fn_body(fortran, "HoistSuiteWholesim_ccpp_physics_finalize")

        assert "enter data" in init_fn
        assert "wholesim_init_run" in init_fn
        assert "present(wholesim_init_run" in run_fn
        assert "exit data" in finalize_fn
        assert "wholesim_init_run" in finalize_fn

    def test_register_only_var_entry_anchor_is_register_not_initialize(
        self, run_host_match, ccpp_context
    ):
        """Falsifies a naively-hardcoded 'always enter at initialize' rule:
        a variable whose only one-time-phase usage is _register must enter
        at register, since register runs before initialize."""
        fortran = _group_b_fortran(run_host_match, ccpp_context)
        register_fn = _fn_body(fortran, "HoistSuiteWholesim_ccpp_physics_register")
        init_fn = _fn_body(fortran, "HoistSuiteWholesim_ccpp_physics_initialize")

        assert "enter data" in register_fn
        assert "register_only" in register_fn
        assert _no_data_directive_line_mentions(init_fn, "register_only")


# ── Group C: multi-suite scoping ──────────────────────────────────────────────
#
# Two independent suites dispatched from one generated cap module (mirroring
# examples/capgen's two-suite CAPS_SUITES pattern). Suite A's scheme uses a
# host var only in _run; suite B's unrelated scheme happens to declare a
# same-named host var with memory_space=device in its own _init table. Suite
# A's usage must NOT be pulled into whole-sim scope by suite B's usage --
# each suite's lifetime analysis must be scoped to its own schemes only.

_GROUP_C_SCHEME_SUITE_A = f"""\
[ccpp-table-properties]
  name = hoist_scheme_suite_a
  type = scheme
[ccpp-arg-table]
  name = hoist_scheme_suite_a_run
  type = scheme
[ shared_var ]
{_device_arg("test_shared_var")}
{CCPP_MANDATORY_ARGS}
"""

_GROUP_C_SCHEME_SUITE_B = f"""\
[ccpp-table-properties]
  name = hoist_scheme_suite_b
  type = scheme
[ccpp-arg-table]
  name = hoist_scheme_suite_b_init
  type = scheme
[ shared_var ]
{_device_arg("test_shared_var")}
{CCPP_MANDATORY_ARGS}
"""

_GROUP_C_HOST = _host_module_meta(
    "hoist_host_multi_suite",
    _host_var_block("shared_var", "test_shared_var"),
)

_GROUP_C_SUITE_A_XML = minimal_suite_xml("hoist_scheme_suite_a", suite_name="hoist_suite_multi_a")
_GROUP_C_SUITE_B_XML = minimal_suite_xml("hoist_scheme_suite_b", suite_name="hoist_suite_multi_b")


def _make_context() -> Context:
    ctx = Context()
    for name, factory in Universe.get_multiverse().all_dialects.items():
        ctx.register_dialect(name, factory)
    ctx.load_dialect(CCPP)
    ctx.load_dialect(CCPPUtils)
    return ctx


def _build_multi_suite_module(scheme_metas, host_metas, suite_xmls, tmp_path, ctx):
    """Same as conftest.py's _build_module, but accepts multiple suite XML
    strings, so more than one suite can be dispatched from one generated
    cap module -- conftest's run_host_match/build_module fixtures only take
    a single suite_xml, which can't express this without changing shared
    test infrastructure other tests depend on.
    """
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


class TestMultiSuiteScoping:
    """Group C: a variable's classification in one suite must not be
    influenced by an unrelated suite's usage of a same-named host var."""

    def test_suite_a_run_only_usage_stays_degenerate_despite_suite_b(self, tmp_path):
        ctx = _make_context()
        module = _build_multi_suite_module(
            scheme_metas=[_GROUP_C_SCHEME_SUITE_A, _GROUP_C_SCHEME_SUITE_B],
            host_metas=[_GROUP_C_HOST],
            suite_xmls=[_GROUP_C_SUITE_A_XML, _GROUP_C_SUITE_B_XML],
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

        run_fn = _fn_body(fortran, "HoistSuiteMultiA_ccpp_physics_run")
        # Suite A's own usage (run-only) must stay degenerate/legacy: plain
        # copyin/copy via the structured AccDataBeginOp path, no enter/exit
        # data forced by suite B's unrelated _init-phase usage of the same
        # variable name.
        assert "copy(shared_var" in run_fn or "copyin(shared_var" in run_fn
        assert _no_data_directive_line_mentions(run_fn, "shared_var")


# ── Group D: update-clause regression guard (single-phase, degenerate) ───────
#
# scheme=host + model=device (CPU-only scheme, host keeps data on GPU), used
# in only one phase -- degenerate, so it must stay on the legacy per-call
# AccUpdateSelfOp/AccUpdateDeviceOp path exactly as before hoisting was
# extended to cover "update" variables too (see Group E for the multi-phase
# hoisted case).

_GROUP_D_SCHEME = f"""\
[ccpp-table-properties]
  name = hoist_scheme_update
  type = scheme
[ccpp-arg-table]
  name = hoist_scheme_update_run
  type = scheme
[ cpu_var ]
  standard_name = test_cpu_only_var
  long_name = CPU-only scheme, host keeps this on GPU
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  intent = inout
{CCPP_MANDATORY_ARGS}
"""

_GROUP_D_HOST = _host_module_meta(
    "hoist_host_update",
    _host_var_block("cpu_var", "test_cpu_only_var", device=True),
)

_GROUP_D_SUITE_XML = minimal_suite_xml("hoist_scheme_update", suite_name="hoist_suite_update")


class TestUpdateClauseRegression:
    def test_update_self_device_unaffected_by_hoisting(self, run_host_match, ccpp_context):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            scheme_metas=[_GROUP_D_SCHEME],
            host_metas=[_GROUP_D_HOST],
            suite_xml=_GROUP_D_SUITE_XML,
        )
        run_fn = _fn_body(fortran, "HoistSuiteUpdate_ccpp_physics_run")
        assert "update self(cpu_var" in run_fn
        assert "update device(cpu_var" in run_fn
        assert "enter data" not in run_fn
        assert "exit data" not in run_fn


# ── Group E: hoisted update-clause vars (item 1(a)) ───────────────────────────
#
# scheme=host + model=device variables now get the same earliest/latest-phase
# hoisting as copyin/copy/copyout, just with a single AccUpdateSelfOp/
# AccUpdateDeviceOp pair instead of AccEnterDataOp/AccExitDataOp -- CCPP
# doesn't own this variable's device allocation (the host model does), it's
# only synchronizing a transient host-side copy. Hoisting this assumes
# nothing outside this suite's own dispatch touches the variable's device
# copy in between (see GPUCcppCapPass's class docstring).
#
#   three_phase_upd -- CPU-only schemes at _timestep_initial + _run +
#                      _timestep_final. entry=timestep_initial,
#                      exit=timestep_final, and _run (strictly between) must
#                      get NOTHING at all -- no update self/device, no
#                      present() (unlike copyin/copy/copyout's passthrough).
#   wholesim_upd    -- CPU-only schemes at _initialize + _run only (no
#                      _finalize reference). Exercises the synthesized-ref
#                      path (same mechanism Group B validated for
#                      copyin/copy/copyout) combined with the "update" kind
#                      dispatch -- exit forced to finalize via a cloned
#                      HostVarRefOp, emitting AccUpdateDeviceOp there.

_GROUP_E_SCHEME = f"""\
[ccpp-table-properties]
  name = hoist_scheme_upd
  type = scheme
[ccpp-arg-table]
  name = hoist_scheme_upd_timestep_init
  type = scheme
[ three_phase_upd ]
  standard_name = test_three_phase_upd_var
  long_name = CPU-only scheme, host keeps this on GPU
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  intent = inout
{CCPP_MANDATORY_ARGS}
[ccpp-arg-table]
  name = hoist_scheme_upd_run
  type = scheme
[ three_phase_upd ]
  standard_name = test_three_phase_upd_var
  long_name = CPU-only scheme, host keeps this on GPU
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  intent = inout
{CCPP_MANDATORY_ARGS}
[ccpp-arg-table]
  name = hoist_scheme_upd_timestep_final
  type = scheme
[ three_phase_upd ]
  standard_name = test_three_phase_upd_var
  long_name = CPU-only scheme, host keeps this on GPU
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  intent = inout
{CCPP_MANDATORY_ARGS}
"""

_GROUP_E_HOST = _host_module_meta(
    "hoist_host_upd",
    _host_var_block("three_phase_upd", "test_three_phase_upd_var", device=True),
)

_GROUP_E_SUITE_XML = minimal_suite_xml("hoist_scheme_upd", suite_name="hoist_suite_upd")


def _group_e_fortran(run_host_match, ccpp_context) -> str:
    return _fortran_output(
        run_host_match, ccpp_context,
        scheme_metas=[_GROUP_E_SCHEME],
        host_metas=[_GROUP_E_HOST],
        suite_xml=_GROUP_E_SUITE_XML,
    )


_GROUP_E_WHOLESIM_SCHEME = f"""\
[ccpp-table-properties]
  name = hoist_scheme_upd_wholesim
  type = scheme
[ccpp-arg-table]
  name = hoist_scheme_upd_wholesim_init
  type = scheme
[ wholesim_upd ]
  standard_name = test_wholesim_upd_var
  long_name = CPU-only scheme, host keeps this on GPU
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  intent = inout
{CCPP_MANDATORY_ARGS}
[ccpp-arg-table]
  name = hoist_scheme_upd_wholesim_run
  type = scheme
[ wholesim_upd ]
  standard_name = test_wholesim_upd_var
  long_name = CPU-only scheme, host keeps this on GPU
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  intent = inout
{CCPP_MANDATORY_ARGS}
"""

_GROUP_E_WHOLESIM_HOST = _host_module_meta(
    "hoist_host_upd_wholesim",
    _host_var_block("wholesim_upd", "test_wholesim_upd_var", device=True),
)

_GROUP_E_WHOLESIM_SUITE_XML = minimal_suite_xml(
    "hoist_scheme_upd_wholesim", suite_name="hoist_suite_upd_wholesim"
)


class TestUpdateClauseHoisting:
    """Group E: item 1(a) -- hoisting extended to scheme=host+model=device."""

    def test_three_phase_update_var_syncs_once_each_way_nothing_at_passthrough(
        self, run_host_match, ccpp_context
    ):
        fortran = _group_e_fortran(run_host_match, ccpp_context)
        initial_fn = _fn_body(fortran, "HoistSuiteUpd_ccpp_physics_timestep_initial")
        run_fn = _fn_body(fortran, "HoistSuiteUpd_ccpp_physics_run")
        final_fn = _fn_body(fortran, "HoistSuiteUpd_ccpp_physics_timestep_final")

        assert "update self(three_phase_upd" in initial_fn
        assert "update device(three_phase_upd" not in initial_fn
        assert "update device(three_phase_upd" in final_fn
        assert "update self(three_phase_upd" not in final_fn
        # No re-sync, no present(), nothing at all at the passthrough phase
        # -- the variable is still a plain call argument there (the CPU-only
        # scheme genuinely needs it), just with no ACC directive.
        assert _no_acc_directive_line_mentions(run_fn, "three_phase_upd")
        assert "enter data" not in initial_fn
        assert "exit data" not in final_fn

    def test_init_run_only_update_var_syncs_device_at_finalize_via_synthesized_ref(
        self, run_host_match, ccpp_context
    ):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            scheme_metas=[_GROUP_E_WHOLESIM_SCHEME],
            host_metas=[_GROUP_E_WHOLESIM_HOST],
            suite_xml=_GROUP_E_WHOLESIM_SUITE_XML,
        )
        init_fn = _fn_body(fortran, "HoistSuiteUpdWholesim_ccpp_physics_initialize")
        run_fn = _fn_body(fortran, "HoistSuiteUpdWholesim_ccpp_physics_run")
        finalize_fn = _fn_body(fortran, "HoistSuiteUpdWholesim_ccpp_physics_finalize")

        assert "update self(wholesim_upd" in init_fn
        assert "update device(wholesim_upd" not in init_fn
        assert _no_acc_directive_line_mentions(run_fn, "wholesim_upd")
        assert "update device(wholesim_upd" in finalize_fn
        assert "update self(wholesim_upd" not in finalize_fn


# ── Group F: per-timestep hoisting alongside an independent finalize touch ───
#
# A variable referenced across a genuine per-timestep span (timestep_initial
# + run) *and* independently at finalize -- finalize can't anchor
# whole-simulation scope on its own (see _resolve_lifetime: only
# register/initialize can), so this variable is per-timestep hoisted (entry
# at timestep_initial, exit at run) while its finalize touch falls outside
# that range and stays on the legacy per-call path independently (_role_at's
# "unused" role). Exercises both the copyin/copy/copyout path and the
# update path through the same "unused" fallback.

_GROUP_F_SCHEME = f"""\
[ccpp-table-properties]
  name = hoist_scheme_fz
  type = scheme
[ccpp-arg-table]
  name = hoist_scheme_fz_timestep_init
  type = scheme
[ fz_var ]
{_device_arg("test_fz_var", intent="inout")}
{CCPP_MANDATORY_ARGS}
[ccpp-arg-table]
  name = hoist_scheme_fz_run
  type = scheme
[ fz_var ]
{_device_arg("test_fz_var", intent="inout")}
{CCPP_MANDATORY_ARGS}
[ccpp-arg-table]
  name = hoist_scheme_fz_finalize
  type = scheme
[ fz_var ]
{_device_arg("test_fz_var", intent="inout")}
{CCPP_MANDATORY_ARGS}
"""

_GROUP_F_HOST = _host_module_meta(
    "hoist_host_fz",
    _host_var_block("fz_var", "test_fz_var"),
)

_GROUP_F_SUITE_XML = minimal_suite_xml("hoist_scheme_fz", suite_name="hoist_suite_fz")

_GROUP_F_UPD_SCHEME = f"""\
[ccpp-table-properties]
  name = hoist_scheme_fz_upd
  type = scheme
[ccpp-arg-table]
  name = hoist_scheme_fz_upd_timestep_init
  type = scheme
[ fz_upd_var ]
  standard_name = test_fz_upd_var
  long_name = CPU-only scheme, host keeps this on GPU
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  intent = inout
{CCPP_MANDATORY_ARGS}
[ccpp-arg-table]
  name = hoist_scheme_fz_upd_run
  type = scheme
[ fz_upd_var ]
  standard_name = test_fz_upd_var
  long_name = CPU-only scheme, host keeps this on GPU
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  intent = inout
{CCPP_MANDATORY_ARGS}
[ccpp-arg-table]
  name = hoist_scheme_fz_upd_finalize
  type = scheme
[ fz_upd_var ]
  standard_name = test_fz_upd_var
  long_name = CPU-only scheme, host keeps this on GPU
  units = K
  type = real | kind = kind_phys
  dimensions = (horizontal_loop_extent, vertical_layer_dimension)
  intent = inout
{CCPP_MANDATORY_ARGS}
"""

_GROUP_F_UPD_HOST = _host_module_meta(
    "hoist_host_fz_upd",
    _host_var_block("fz_upd_var", "test_fz_upd_var", device=True),
)

_GROUP_F_UPD_SUITE_XML = minimal_suite_xml("hoist_scheme_fz_upd", suite_name="hoist_suite_fz_upd")


class TestFinalizeAlongsidePerTimestepHoisting:
    """Group F: finalize can't anchor whole-sim scope alone, so a variable
    with a real per-timestep span plus an independent finalize touch still
    hoists the per-timestep span, leaving finalize on the legacy path."""

    def test_copy_var_hoists_per_timestep_finalize_touch_stays_legacy(
        self, run_host_match, ccpp_context
    ):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            scheme_metas=[_GROUP_F_SCHEME],
            host_metas=[_GROUP_F_HOST],
            suite_xml=_GROUP_F_SUITE_XML,
        )
        initial_fn = _fn_body(fortran, "HoistSuiteFz_ccpp_physics_timestep_initial")
        run_fn = _fn_body(fortran, "HoistSuiteFz_ccpp_physics_run")
        finalize_fn = _fn_body(fortran, "HoistSuiteFz_ccpp_physics_finalize")

        assert "enter data" in initial_fn
        assert "fz_var" in initial_fn
        assert "exit data" in run_fn
        assert "fz_var" in run_fn
        # finalize's own touch is independent of the hoisted span: full
        # legacy structured transfer, no enter/exit-data.
        assert "copy(fz_var" in finalize_fn or "copyin(fz_var" in finalize_fn or "copyout(fz_var" in finalize_fn
        assert _no_data_directive_line_mentions(finalize_fn, "fz_var")

    def test_update_var_hoists_per_timestep_finalize_touch_stays_legacy(
        self, run_host_match, ccpp_context
    ):
        fortran = _fortran_output(
            run_host_match, ccpp_context,
            scheme_metas=[_GROUP_F_UPD_SCHEME],
            host_metas=[_GROUP_F_UPD_HOST],
            suite_xml=_GROUP_F_UPD_SUITE_XML,
        )
        initial_fn = _fn_body(fortran, "HoistSuiteFzUpd_ccpp_physics_timestep_initial")
        run_fn = _fn_body(fortran, "HoistSuiteFzUpd_ccpp_physics_run")
        finalize_fn = _fn_body(fortran, "HoistSuiteFzUpd_ccpp_physics_finalize")

        assert "update self(fz_upd_var" in initial_fn
        assert "update device(fz_upd_var" not in initial_fn
        assert "update device(fz_upd_var" in run_fn
        assert "update self(fz_upd_var" not in run_fn
        # finalize's own touch is independent of the hoisted span: full
        # legacy per-call self+device pair, right at its own call site.
        assert "update self(fz_upd_var" in finalize_fn
        assert "update device(fz_upd_var" in finalize_fn
