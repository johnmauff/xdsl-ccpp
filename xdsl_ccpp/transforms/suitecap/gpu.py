"""GPU residency of suite-owned variables: exit-data and update injection."""

from __future__ import annotations


from xdsl.dialects import func, scf
from xdsl.pattern_rewriter import (
    InsertPoint,
)
from xdsl.rewriter import Rewriter
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects import ccpp_utils
from xdsl_ccpp.dialects.ccpp_utils import (
    KeywordCallOp,
    LazyAllocOp,
)
from xdsl_ccpp.transforms.util.cap_shared import (
    SUITE_FN_INFIX,
    emit_coalesced_updates,
    find_diverged_suite_owned_vars,
    split_scheme_table_name,
)
from xdsl_ccpp.transforms.util.typing import TypeConversions


class SuiteOwnedGpuMixin:
    """GPU residency of suite-owned variables: exit-data and update injection."""

    @staticmethod
    def _inject_suite_owned_gpu_exit(generated_fns, suite_model):
        """Emit AccExitDataOp in _finalize for every SuiteOwned var whose enter-data-create fired.

        These arrays live for the whole simulation (same scope GPUCcppCapPass
        uses for HostMatched vars), so exit belongs in _finalize, not
        _timestep_final. Keyed off LazyAllocOps with needs_device_residency in
        the generated IR, not suite_model alone: a var whose allocation was
        never emitted has no enter data, and an unmatched exit is invalid.
        """
        resident_var_names: set = set()
        for fn in generated_fns:
            if not isa(fn, func.FuncOp) or not fn.body.blocks:
                continue
            for block_op in fn.body.blocks[0].ops:
                if (
                    isa(block_op, LazyAllocOp)
                    and block_op.needs_device_residency is not None
                    and bool(block_op.needs_device_residency.value.data)
                ):
                    resident_var_names.add(block_op.var_name.data)

        if not resident_var_names:
            return

        entries_by_name = {e.local_name: e for e in suite_model.suite_owned_vars()}

        for fn in generated_fns:
            if not isa(fn, func.FuncOp):
                continue
            if not fn.sym_name.data.endswith(f"{SUITE_FN_INFIX}_finalize"):
                continue
            if not fn.body.blocks:
                continue
            block = fn.body.blocks[0]
            ret_op = next((bop for bop in block.ops if isa(bop, func.ReturnOp)), None)
            if ret_op is None:
                continue
            for var_name in sorted(resident_var_names):
                entry = entries_by_name.get(var_name)
                if entry is None:
                    continue
                var_type = TypeConversions.convert(
                    entry.fortran_type, entry.kind if entry.kind else None, entry.rank
                )
                ref_op = ccpp_utils.HostVarRefOp(entry.local_name, "", var_type)
                Rewriter.insert_op(ref_op, InsertPoint.before(ret_op))
                Rewriter.insert_op(
                    ccpp_utils.AccExitDataOp(delete=[ref_op.res]),
                    InsertPoint.before(ret_op),
                )

    # Functions containing error-guarded scheme calls; keep in sync with
    # GPUDataPass.apply() (gpu_data_pass.py).
    _GPU_CALL_BEARING_FN_MARKERS = (
        f"{SUITE_FN_INFIX}_physics",
        f"{SUITE_FN_INFIX}_timestep_init_",
        f"{SUITE_FN_INFIX}_timestep_final_",
        f"{SUITE_FN_INFIX}_init_",
        f"{SUITE_FN_INFIX}_final_",
    )

    @staticmethod
    def _build_suite_owned_debug_sync_touches(calls, suite_model, meta_data):
        """Build debug-sync touches for each device-side write of a SuiteOwned var.

        Mirrors GPUDataPass._build_debug_sync_touches for SuiteOwned vars.
        Touches are "produced" (update self after the call only). Keyed by
        (std_name, id(call_op)) so each producing call gets its own sync,
        while vars written by the same call share one `update self(...)`.
        SuiteOwned vars are module-scope, so a fresh HostVarRefOp is
        inserted before each call.
        """
        entries_by_std = {
            e.standard_name: e
            for e in suite_model.suite_owned_vars()
            if e.needs_device_residency
        }
        if not entries_by_std:
            return {}

        debug_sync_touches: dict = {}
        for call_op, scheme_name, table_name in calls:
            if scheme_name not in meta_data or table_name not in meta_data[scheme_name].arg_tables:
                continue
            for arg in meta_data[scheme_name].arg_tables[table_name].getFunctionArguments():
                if not arg.hasAttr("standard_name"):
                    continue
                std_name = arg.getAttr("standard_name").lower()
                entry = entries_by_std.get(std_name)
                if entry is None:
                    continue
                if not arg.hasAttr("memory_space") or arg.getAttr("memory_space") != "device":
                    continue
                intent = arg.getAttr("intent") if arg.hasAttr("intent") else None
                if intent not in ("out", "inout"):
                    continue
                var_type = TypeConversions.convert(
                    entry.fortran_type, entry.kind if entry.kind else None, entry.rank
                )
                ref_op = ccpp_utils.HostVarRefOp(entry.local_name, "", var_type)
                Rewriter.insert_op(ref_op, InsertPoint.before(call_op))
                key = ("debug_sync", std_name, id(call_op))
                debug_sync_touches[key] = (ref_op.res, [(call_op, "produced")])
        return debug_sync_touches

    @staticmethod
    def _inject_suite_owned_gpu_update(generated_fns, suite_model, meta_data, debug_sync=False):
        """Emit `!$acc update self/device(...)` for SuiteOwned vars whose residency need flips.

        E.g. a host-only scheme writes a scratch array (exner, theta) that a
        later memory_space=device scheme consumes, or the reverse
        (cap_shared.find_diverged_suite_owned_vars). The one-time
        `enter data create` only allocates device memory and never moves
        data, so without an update at each flip the consumer reads stale data.

        Emission is delegated to cap_shared.emit_coalesced_updates (shared
        with GPUDataPass), which groups vars syncing at the same call. One
        HostVarRefOp per var per function is inserted before its first
        touching call, dominating all later uses.

        debug_sync (debug-only): also add "produced" touches for every
        device-resident SuiteOwned var (_build_suite_owned_debug_sync_touches).
        """
        diverged_std_names = find_diverged_suite_owned_vars(suite_model)
        if not diverged_std_names and not debug_sync:
            return

        entries_by_std = {
            e.standard_name: e
            for e in suite_model.suite_owned_vars()
            if e.standard_name in diverged_std_names
        }

        for fn in generated_fns:
            if not isa(fn, func.FuncOp) or fn.is_declaration or not fn.body.blocks:
                continue
            fn_name = fn.sym_name.data
            if not any(marker in fn_name for marker in SuiteOwnedGpuMixin._GPU_CALL_BEARING_FN_MARKERS):
                continue

            block = fn.body.blocks[0]
            calls = []  # ordered (scf.IfOp, scheme_name, table_name)
            for op in block.ops:
                if not isa(op, scf.IfOp) or not op.true_region.blocks:
                    continue
                call_op = next(
                    (
                        o for o in op.true_region.blocks[0].ops
                        if isa(o, func.CallOp) or isa(o, KeywordCallOp)
                    ),
                    None,
                )
                if call_op is None:
                    continue
                callee_name = (
                    call_op.callee.data if isa(call_op, KeywordCallOp)
                    else call_op.callee.root_reference.data
                )
                split = split_scheme_table_name(callee_name)
                if split is None:
                    continue
                calls.append((op, split[0], callee_name))

            if not calls:
                continue

            # touches: standard_name -> ordered [(scf.IfOp, category), ...];
            # "present" if the scheme declares memory_space=device, else "update"
            # (mirrors _get_diverged_args).
            touches: dict = {}
            for call_op, scheme_name, table_name in calls:
                if scheme_name not in meta_data or table_name not in meta_data[scheme_name].arg_tables:
                    continue
                for arg in meta_data[scheme_name].arg_tables[table_name].getFunctionArguments():
                    if not arg.hasAttr("standard_name"):
                        continue
                    std_name = arg.getAttr("standard_name").lower()
                    if std_name not in entries_by_std:
                        continue
                    scheme_space = (
                        arg.getAttr("memory_space") if arg.hasAttr("memory_space") else "host"
                    )
                    category = "present" if scheme_space == "device" else "update"
                    touches.setdefault(std_name, []).append((call_op, category))

            resolved: dict = {}
            for std_name, touch_list in touches.items():
                entry = entries_by_std[std_name]
                var_type = TypeConversions.convert(
                    entry.fortran_type, entry.kind if entry.kind else None, entry.rank
                )
                ref_op = ccpp_utils.HostVarRefOp(entry.local_name, "", var_type)
                Rewriter.insert_op(ref_op, InsertPoint.before(touch_list[0][0]))
                resolved[std_name] = (ref_op.res, touch_list)

            if debug_sync:
                resolved.update(
                    SuiteOwnedGpuMixin._build_suite_owned_debug_sync_touches(
                        calls, suite_model, meta_data
                    )
                )

            if resolved:
                emit_coalesced_updates("acc", resolved, lambda ref, call_op: None)
