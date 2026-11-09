"""resolve-constituent-residency (constituent-device-residency, stage 1):
decide whether the constituent array is device data, from how the suite's
schemes use it.

The constituents reach schemes as the whole array (ccpp_constituents ->
lc_constituent_array) and as per-constituent views (host-bound advected
arguments, pointer slices into lc_constituent_array). Under rule (a)
(derive_memory_space) nothing anchors them: schemes ported with
present-or-copy clauses are "either" (device_capable), so the constituents
stay host data and every such scheme copies them in and out on each call.

Reader/writer rule (decided 2026-11-02): the constituents become device
data when no CPU scheme writes them -- every scheme argument resolving to
lc_constituent_array with intent out/inout is device or device_capable.
Then every device_capable constituent argument gets memory_space =
device, and the existing machinery takes over: lc_constituent_array is
made resident (ccpp_cap framework_var_residency), CPU readers of the
whole array get update self (find_diverged_capscratch_vars), and the
views' per-call copy regions find the data present. If a CPU scheme
writes the constituents, nothing changes (per-call copies, correct), and
--verbose 2 says why.

Copy-clause residency (acc-copy-residency, decided 2026-11-08): every other
device_capable scheme argument (not a constituent) gets memory_space =
device as well, so a scheme ported with present-or-copy clauses alone makes
its variables device data, as present() does; the cap then syncs them
around CPU schemes. Arguments the scheme also uses in host code were never
marked device_capable (fparser2_to_meta ACC_HOST). Arguments the API caller
passes in each call (Block arguments, HOST/CONTROL-table matches, members
of a DDT with no module instance, such as qmin) are not promoted: the cap
never makes them resident.

Runs after generate-arg-ownership (it needs the CapScratch classification
of the views) and before generate-suite-cap; only with --directive acc
(with omp, derive_memory_space already makes every "either" device).
Reads and sets CCPP metadata only.
"""

from __future__ import annotations

import sys

from xdsl.context import Context
from xdsl.dialects import builtin
from xdsl.dialects.builtin import StringAttr
from xdsl.passes import ModulePass
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects import ccpp
from xdsl_ccpp.dialects.ccpp import TableTypeKind
from xdsl_ccpp.transforms.util.cap_shared import (
    _build_ddt_resolution_maps,
    _collect_host_block_std_names,
    _iter_schemes,
    _resolve_ddt_access_path,
    iter_arg_tables,
    resolve_capscratch_cap_var_name,
    split_scheme_table_name,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    BuildMetaDataDescriptions,
    BuildSchemeDescription,
    CCPPType,
)
from xdsl_ccpp.transforms.util.ir_utils import find_ccpp_module
from xdsl_ccpp.util.ccpp_conventions import verbosity

CONSTITUENT_ARRAY = "lc_constituent_array"


def _is_constituent_arg(arg_op: ccpp.ArgumentOp) -> bool:
    """True for a scheme argument backed by lc_constituent_array: the whole
    array or a per-constituent view."""
    if arg_op.ownership_kind is None or arg_op.standard_name is None:
        return False
    if arg_op.ownership_kind.data != ccpp.ArgOwnershipKind.CapScratch:
        return False
    return resolve_capscratch_cap_var_name(
        arg_op.standard_name.data, arg_op.constituent is not None,
        arg_op.advected is not None,
    ) == CONSTITUENT_ARRAY


def _cap_cannot_anchor(arg_op: ccpp.ArgumentOp, meta) -> bool:
    """True for an argument whose data the cap cannot make resident because
    the API caller passes it in on each call: ownership Block, a match in a
    HOST/CONTROL table, or a member of a DDT with no module-level instance
    the cap can USE (e.g. qmin = the constituent object's vars_minvalue,
    an argument of ccpp_physics_run). Promoting such an argument to device
    would leave the cap's present()/update clauses pointing at data that is
    not on the device (xdsl71gpu hb_vdiff: "data in update host clause was
    not found on device: qmincg"), so the scheme keeps copying it itself."""
    host_block_std, meta_data, ddt_instance_map, ddt_parent_map = meta
    if arg_op.ownership_kind is None:
        return False
    kind = arg_op.ownership_kind.data
    if kind == ccpp.ArgOwnershipKind.Block:
        return True
    if kind != ccpp.ArgOwnershipKind.HostMatched:
        return False
    if (
        arg_op.standard_name is not None
        and arg_op.standard_name.data.lower() in host_block_std
    ):
        return True
    table = arg_op.model_module_name.data if arg_op.model_module_name else None
    props = meta_data.get(table) if table else None
    if props is None or props.getAttr("type") != CCPPType.DDT:
        return False
    resolved = _resolve_ddt_access_path(table, ddt_instance_map, ddt_parent_map)
    if resolved is None:
        return True
    instance_module = resolved[1]
    return (
        instance_module in meta_data
        and meta_data[instance_module].getAttr("type") in (CCPPType.HOST, CCPPType.CONTROL)
    )


def _on_device(arg_op: ccpp.ArgumentOp) -> bool:
    return arg_op.device_capable is not None or (
        arg_op.memory_space is not None and arg_op.memory_space.data == "device"
    )


def _writes(arg_op: ccpp.ArgumentOp) -> bool:
    return arg_op.intent is not None and arg_op.intent.data in ("out", "inout")


def resolve_constituent_residency(module: builtin.ModuleOp) -> list[str]:
    """Apply the reader/writer rule to *module*'s scheme arguments. Returns
    lines for --verbose 2 (what became device, or why nothing did)."""
    ccpp_mod = find_ccpp_module(module.body.block.ops)
    if ccpp_mod is None:
        return []
    # Only the schemes the suites call: a .meta file can describe more
    # (state_converters.meta holds conversions a suite may not use).
    # lc_constituent_array is one array for every suite in the module, so
    # the rule looks at all of them together.
    bsd = BuildSchemeDescription()
    bsd.traverse(ccpp_mod)
    called = {
        scheme.attributes["name"]
        for suite in bsd.schemes.values()
        for group in suite
        for scheme in _iter_schemes(group)
    }
    bmdd = BuildMetaDataDescriptions()
    bmdd.traverse(ccpp_mod)
    meta = (
        _collect_host_block_std_names(bmdd.meta_data),
        bmdd.meta_data,
        *_build_ddt_resolution_maps(bmdd.meta_data),
    )
    uses: list[tuple[str, ccpp.ArgumentOp]] = []
    report: list[str] = []
    for _props, table in iter_arg_tables(ccpp_mod, table_type=TableTypeKind.Scheme):
        split = split_scheme_table_name(table.table_name.data)
        if split is None or split[0] not in called:
            continue
        for arg_op in table.body.ops:
            if not isa(arg_op, ccpp.ArgumentOp):
                continue
            if _is_constituent_arg(arg_op):
                uses.append((table.table_name.data, arg_op))
            elif (
                arg_op.device_capable is not None
                and arg_op.memory_space is None
                and not _cap_cannot_anchor(arg_op, meta)
            ):
                arg_op.properties["memory_space"] = StringAttr("device")
                report.append(
                    f"{table.table_name.data}: '{arg_op.arg_name.data}' memory_space = "
                    "device (the scheme copies it itself; copy clauses anchor residency)"
                )
    capable = [(t, a) for t, a in uses if a.device_capable is not None and a.memory_space is None]
    if not capable:
        return report
    cpu_writers = sorted(
        f"{t}: '{a.arg_name.data}'" for t, a in uses if _writes(a) and not _on_device(a)
    )
    if cpu_writers:
        return report + [
            "constituents stay host data (written on the CPU by "
            + ", ".join(cpu_writers) + "); schemes copy them per call"
        ]
    for table_name, arg_op in capable:
        arg_op.properties["memory_space"] = StringAttr("device")
        report.append(
            f"{table_name}: '{arg_op.arg_name.data}' memory_space = device "
            "(constituents: no CPU scheme writes them)"
        )
    return report


class ConstituentResidencyPass(ModulePass):
    """See the module docstring."""

    name = "resolve-constituent-residency"

    def apply(self, ctx: Context, op: builtin.ModuleOp) -> None:
        report = resolve_constituent_residency(op)
        if report and verbosity() >= 2:
            print("device residency from copy clauses and constituents:", file=sys.stderr)
            for line in report:
                print(f"  {line}", file=sys.stderr)
