"""constituent-device-residency, stage 1: resolve-constituent-residency's
reader/writer rule, on examples/advection's real suite and metadata (the
constituents cld_liq_array / cld_ice_array are host-bound advected views
into lc_constituent_array).

device_capable is set by hand here, as derive_memory_space would for
schemes ported with present-or-copy clauses."""

from pathlib import Path

from xdsl.context import Context
from xdsl.dialects import arith, builtin, func
from xdsl.dialects.builtin import ModuleOp, UnitAttr

from xdsl_ccpp.dialects.ccpp import CCPP, ArgumentOp, ArgumentTableOp
from xdsl_ccpp.dialects.ccpp_utils import CCPPUtils
from xdsl_ccpp.frontend.ccpp_xml import XMLSuite, ccppXML, parse_meta_file
from xdsl_ccpp.transforms.arg_ownership_pass import ArgOwnershipPass
from xdsl_ccpp.transforms.constituent_residency_pass import (
    _is_constituent_arg,
    resolve_constituent_residency,
)
from xdsl_ccpp.transforms.host_var_match_pass import HostVariableMatchPass
from xdsl_ccpp.transforms.suite_meta import MetaCAP

_ROOT = Path(__file__).resolve().parents[2]
_EX = _ROOT / "examples" / "advection"
_SCHEMES = ["const_indices", "cld_liq", "apply_constituent_tendencies", "cld_ice", "cld_shadow"]
_HOSTS = ["test_host_data", "test_host_mod", "test_host"]


def _module():
    ctx = Context()
    for dialect in (builtin.Builtin, func.Func, arith.Arith, CCPP, CCPPUtils):
        ctx.load_dialect(dialect)
    frontend = ccppXML()
    ops = [frontend.build_suite_ir(XMLSuite(str(_EX / "cld_suite.xml")))]
    for name in _SCHEMES:
        for meta in parse_meta_file(str(_EX / f"{name}.meta"), True):
            ops.append(frontend.build_meta_ir(meta, source_module=name))
    for name in _HOSTS:
        for meta in parse_meta_file(str(_EX / f"{name}.meta"), False):
            ops.append(frontend.build_meta_ir(meta, source_module=name))
    module = ModuleOp(ops)
    for pass_cls in (MetaCAP, HostVariableMatchPass, ArgOwnershipPass):
        pass_cls().apply(ctx, module)
    return module


def _constituent_args(module):
    return [
        (table.table_name.data, arg)
        for table in module.walk() if isinstance(table, ArgumentTableOp)
        if table.table_type.data == "scheme"
        for arg in table.body.block.ops
        if isinstance(arg, ArgumentOp) and _is_constituent_arg(arg)
    ]


def _clear_memory_space(arg):
    arg.properties.pop("memory_space", None)


def test_advection_has_constituent_views():
    # A per-constituent view (cld_ice_run's) and the whole array
    # (apply_constituent_tendencies' const) both resolve to
    # lc_constituent_array; cld_liq_run takes only a tendency.
    names = {(t, a.arg_name.data) for t, a in _constituent_args(_module())}
    assert ("cld_ice_run", "cld_ice_array") in names
    assert ("apply_constituent_tendencies_run", "const") in names
    assert not any(t == "cld_liq_run" for t, _ in names)


def test_all_users_on_device_makes_them_device():
    module = _module()
    args = _constituent_args(module)
    for _, arg in args:
        _clear_memory_space(arg)
        arg.properties["device_capable"] = UnitAttr()
    report = resolve_constituent_residency(module)
    assert all(a.memory_space is not None and a.memory_space.data == "device" for _, a in args)
    assert len(report) == len(args)


def test_cpu_writer_keeps_them_host():
    module = _module()
    args = _constituent_args(module)
    writers = [a for _, a in args if a.intent is not None and a.intent.data in ("out", "inout")]
    assert writers
    for _, arg in args:
        _clear_memory_space(arg)
        arg.properties["device_capable"] = UnitAttr()
    writers[0].properties.pop("device_capable")  # one scheme writes on the CPU
    (line,) = resolve_constituent_residency(module)
    assert "stay host data" in line
    assert all(a.memory_space is None for _, a in args)


def test_cpu_reader_does_not_block():
    module = _module()
    args = _constituent_args(module)
    readers = [a for _, a in args if a.intent is not None and a.intent.data == "in"]
    for _, arg in args:
        _clear_memory_space(arg)
        if arg not in readers:
            arg.properties["device_capable"] = UnitAttr()
    resolve_constituent_residency(module)
    for _, arg in args:
        if arg in readers:
            assert arg.memory_space is None  # CPU readers stay host (synced)
        else:
            assert arg.memory_space.data == "device"


def test_nothing_device_capable_is_a_no_op():
    module = _module()
    args = _constituent_args(module)
    for _, arg in args:
        _clear_memory_space(arg)
    assert resolve_constituent_residency(module) == []
    assert all(a.memory_space is None for _, a in args)


# ── stage 2: per-step syncs in the host cap ──────────────────────────────────

def _host_cap_fortran(make_device: bool) -> str:
    from io import StringIO

    from xdsl_ccpp.backend.print_ftn import print_to_ftn
    from xdsl_ccpp.transforms.ccpp_cap import CCPPCAP
    from xdsl_ccpp.transforms.generate_kinds import GenerateKinds
    from xdsl_ccpp.transforms.strip_ccpp import StripCCPP
    from xdsl_ccpp.transforms.suite_cap import SuiteCAP
    from xdsl_ccpp.transforms.suite_kinds import MetaKind

    module = _module()
    for _, arg in _constituent_args(module):
        _clear_memory_space(arg)
        if make_device:
            arg.properties["device_capable"] = UnitAttr()
    resolve_constituent_residency(module)
    ctx = Context()
    for dialect in (builtin.Builtin, func.Func, arith.Arith, CCPP, CCPPUtils):
        ctx.load_dialect(dialect)
    for pass_cls in (MetaKind, SuiteCAP, CCPPCAP, GenerateKinds, StripCCPP):
        pass_cls().apply(ctx, module)
    out = StringIO()
    print_to_ftn(module, out)
    return out.getvalue()


def _physics_run(fortran: str) -> list[str]:
    start = fortran.index("subroutine ccpp_physics_run(")
    end = fortran.index("end subroutine ccpp_physics_run", start)
    return [l.strip() for l in fortran[start:end].splitlines()]


def test_resident_constituents_synced_around_the_group_call():
    lines = _physics_run(_host_cap_fortran(make_device=True))
    call = next(i for i, l in enumerate(lines) if l.startswith("call ") and "cld_suite" in l)
    assert "!$acc update device(lc_constituent_array)" in lines[:call]
    assert "!$acc update self(lc_constituent_array)" in lines[call:]


def test_host_constituents_get_no_syncs():
    lines = _physics_run(_host_cap_fortran(make_device=False))
    assert not any("lc_constituent_array)" in l and "!$acc update" in l for l in lines)


# ── stage 3: CPU readers of a constituent view ───────────────────────────────

def _suite_cap_run(view_reader_on_cpu: bool, resident: bool = True) -> list[str]:
    """examples/advection's suite cap, physics run group, generated with
    --directive acc: apply_constituent_tendencies (twice) uses the whole
    array on the device; cld_ice_run reads its view cld_ice_array."""
    from io import StringIO

    from xdsl.dialects.builtin import StringAttr

    from xdsl_ccpp.backend.print_ftn import print_to_ftn
    from xdsl_ccpp.transforms.ccpp_cap import CCPPCAP
    from xdsl_ccpp.transforms.generate_kinds import GenerateKinds
    from xdsl_ccpp.transforms.gpu_data_pass import GPUDataPass
    from xdsl_ccpp.transforms.strip_ccpp import StripCCPP
    from xdsl_ccpp.transforms.suite_cap import SuiteCAP
    from xdsl_ccpp.transforms.suite_kinds import MetaKind

    module = _module()
    for table, arg in _constituent_args(module):
        _clear_memory_space(arg)
        if table == "apply_constituent_tendencies_run" and resident:
            arg.properties["memory_space"] = StringAttr("device")
        if table == "cld_ice_run":
            arg.properties["intent"] = StringAttr("in")
            if not view_reader_on_cpu:
                arg.properties["memory_space"] = StringAttr("device")
    ctx = Context()
    for dialect in (builtin.Builtin, func.Func, arith.Arith, CCPP, CCPPUtils):
        ctx.load_dialect(dialect)
    for pass_cls in (MetaKind, SuiteCAP):
        pass_cls().apply(ctx, module)
    GPUDataPass(directive="acc").apply(ctx, module)
    for pass_cls in (CCPPCAP, GenerateKinds, StripCCPP):
        pass_cls().apply(ctx, module)
    out = StringIO()
    print_to_ftn(module, out)
    text = out.getvalue()
    start = text.index("subroutine cld_suite_physics(")
    end = text.index("end subroutine cld_suite_physics", start)
    return [l.strip() for l in text[start:end].splitlines()]


def _between(lines, first_call, second_call):
    i = next(k for k, l in enumerate(lines) if l.startswith(f"call {first_call}"))
    j = next(k for k, l in enumerate(lines) if k > i and l.startswith(f"call {second_call}"))
    return lines[i:j]


def test_cpu_view_reader_after_device_write_gets_update_self():
    lines = _suite_cap_run(view_reader_on_cpu=True)
    gap = _between(lines, "apply_constituent_tendencies_run", "cld_ice_run")
    # The whole array, which covers the view.
    assert "!$acc update self(const)" in gap, gap
    # A reader pushes nothing back to the device.
    after = _between(lines, "cld_ice_run", "apply_constituent_tendencies_run")
    assert not any(l.startswith("!$acc update device(") for l in after), after


def test_device_view_user_needs_no_update():
    lines = _suite_cap_run(view_reader_on_cpu=False)
    gap = _between(lines, "apply_constituent_tendencies_run", "cld_ice_run")
    assert not any("!$acc update" in l for l in gap), gap


def test_view_reader_ignored_when_array_not_resident():
    # The constituents are host data: no sync of the array (const); the
    # example's own tendency syncs (const_tend) are unrelated.
    lines = _suite_cap_run(view_reader_on_cpu=True, resident=False)
    assert not any("!$acc update" in l and "(const)" in l for l in lines), lines
