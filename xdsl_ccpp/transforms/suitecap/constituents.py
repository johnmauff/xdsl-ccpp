"""Constituent handling in the suite cap: advected classification, sync ops and index lookup."""

from __future__ import annotations


from xdsl.dialects import func, memref
from xdsl.pattern_rewriter import (
    InsertPoint,
)
from xdsl.rewriter import Rewriter
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects.ccpp_utils import (
    ConstituentIndexLookupOp,
    ConstituentSyncOp,
    NullifyPointerOp,
    PointerSliceAssignOp,
)
from xdsl_ccpp.transforms.constituent_cap import _collect_constituent_info


class ConstituentsMixin:
    """Constituent handling in the suite cap: advected classification, sync ops and index lookup."""

    @staticmethod
    def _classify_call_sequence_by_q(call_sequence, arg_tables):
        """Split call_sequence items into three groups by ccpp_constituents usage.

        Returns (pre_q, modify_q, readonly_q) where:
          pre_q      -- schemes that don't use ccpp_constituents
          modify_q   -- schemes with ccpp_constituents intent=inout/out (e.g. qneg)
          readonly_q -- schemes with ccpp_constituents intent=in (e.g. geopotential_temp)

        Subcycle items are placed in pre_q (conservative).
        """
        Q_STD = "ccpp_constituents"
        pre_q = []
        modify_q = []
        readonly_q = []
        for item in call_sequence:
            if item[0] != "scheme":
                pre_q.append(item)
                continue
            _, scheme_name, _ = item
            if scheme_name not in arg_tables:
                pre_q.append(item)
                continue
            uses_q = False
            modifies_q = False
            for arg in arg_tables[scheme_name].getFunctionArguments():
                if arg.hasAttr("standard_name") and arg.getAttr("standard_name") == Q_STD:
                    uses_q = True
                    intent = arg.getAttr("intent") if arg.hasAttr("intent") else "in"
                    if intent in ("inout", "out"):
                        modifies_q = True
            if modifies_q:
                modify_q.append(item)
            elif uses_q:
                readonly_q.append(item)
            else:
                pre_q.append(item)
        return pre_q, modify_q, readonly_q

    @staticmethod
    def _fixed_advected_std_names(meta_data) -> set:
        """Std names of fixed-advected constituents pointer-aliased into ccpp_constituents.

        The "pointer" half of _classify_fixed_advected_std_names. Must stay in
        sync with _build_module_vars, _sweep_suite_owned_var_allocations,
        _maybe_schedule_framework_var_alloc and _inject_safe_deallocs, which
        special-case these vars.
        """
        pointer_names, _value_copy_names = (
            ConstituentsMixin._classify_fixed_advected_std_names(meta_data)
        )
        return pointer_names

    @staticmethod
    def _classify_fixed_advected_std_names(meta_data) -> tuple:
        """Partition fixed-advected constituent std_names into (pointer_names, value_copy_names).

        Both are empty unless some scheme declares a ccpp_constituents arg
        (`advected=.true.` alone is also used without one).

        pointer_names -- referenced only by "_run" tables; aliased directly
        into const(:,:,idx) with no backing memory (safe because the
        constituent array is only available in _run).

        value_copy_names -- referenced by _run AND another phase (e.g.
        examples/advection's cld_ice_array); these need real backing memory
        and get an extract/writeback ConstituentSyncOp pair around _run.

        Names never referenced by _run are in neither set.
        """
        from xdsl_ccpp.transforms.util.ccpp_descriptors import CCPPType

        _, fixed_adv, _ = _collect_constituent_info(meta_data)
        if not fixed_adv:
            return set(), set()
        has_const_array = any(
            props.getAttr("type") == CCPPType.SCHEME
            and any(
                fn_arg.hasAttr("standard_name")
                and fn_arg.getAttr("standard_name").lower() == "ccpp_constituents"
                for arg_table in props.arg_tables.values()
                for fn_arg in arg_table.getFunctionArguments()
            )
            for props in meta_data.values()
        )
        if not has_const_array:
            return set(), set()
        run_referenced = set()
        other_referenced = set()
        for props in meta_data.values():
            if props.getAttr("type") != CCPPType.SCHEME:
                continue
            for table_name, arg_table in props.arg_tables.items():
                target = run_referenced if table_name.endswith("_run") else other_referenced
                for fn_arg in arg_table.getFunctionArguments():
                    if fn_arg.hasAttr("standard_name"):
                        target.add(fn_arg.getAttr("standard_name").lower())
        all_fixed = {std_name for std_name, *_ in fixed_adv}
        pointer_names = (all_fixed & run_referenced) - other_referenced
        value_copy_names = all_fixed & run_referenced & other_referenced
        return pointer_names, value_copy_names

    def _build_constituent_sync_ops(self, suite_model, data_ops, input_arg_list):
        """Build pointer-association ops for advected module-level constituent vars.

        Returns (assign_ops, nullify_ops). pointer_names entries are
        pointer-associated to const(:,:,lc_const_indices(idx)) at the start
        of _run and nullified at the end. Matches capgen-v1's array-section
        aliasing (host_cap.py::add_constituent_vars); value-copying would go
        stale when several schemes modify the constituent array in place.
        value_copy_names entries get an extract/writeback ConstituentSyncOp
        pair instead.

        Returns ([], []) when there is no constituent array argument or no
        advected constituent is suite-owned for this group.
        """
        pointer_names, value_copy_names = self._classify_fixed_advected_std_names(
            self.meta_data
        )
        if not pointer_names and not value_copy_names:
            return [], []
        _, fixed_adv, _ = _collect_constituent_info(self.meta_data)

        # Fortran dummy-argument name of the 3D constituent array.
        q_ref = data_ops.get(("std_name", "ccpp_constituents"))
        if q_ref is None:
            return [], []
        q_local = getattr(q_ref, "name_hint", None) or ""
        # Strip __in/__alloc/__opt suffixes (see _hint_for / _printed_name).
        for sfx in ("__alloc", "__opt", "__in"):
            if q_local.endswith(sfx):
                q_local = q_local[: -len(sfx)]
                break
        if not q_local:
            return [], []

        assign_ops = []
        nullify_ops = []
        for const_idx, (std_name, _units, _default_val, _local_name) in enumerate(
            fixed_adv, start=1
        ):
            # const_idx is 1-based over the FULL fixed_adv list, matching
            # lc_const_indices in constituent_cap.py.
            entry = suite_model.get(std_name)
            if entry is None:
                continue  # not suite-owned for this group; skip
            var_local = entry.local_name
            if std_name in pointer_names:
                assign_ops.append(PointerSliceAssignOp(
                    ptr_name=var_local,
                    array_name=q_local,
                    index_var=f"lc_const_indices({const_idx})",
                ))
                nullify_ops.append(NullifyPointerOp(var_local))
            elif std_name in value_copy_names:
                assign_ops.append(ConstituentSyncOp(
                    var_name=var_local,
                    q_name=q_local,
                    ncol_name="ncol",
                    constituent_idx=const_idx,
                    direction="extract",
                ))
                nullify_ops.append(ConstituentSyncOp(
                    var_name=var_local,
                    q_name=q_local,
                    ncol_name="ncol",
                    constituent_idx=const_idx,
                    direction="writeback",
                ))
        return assign_ops, nullify_ops

    @staticmethod
    def _inject_constituent_index_lookup(generated_fns, std_name_attrs):
        """Inject ConstituentIndexLookupOp at the top of each group-phase _init_ FuncOp.

        Populates lc_const_indices at runtime, independent of registration order.
        """
        for fn in generated_fns:
            if not isa(fn, func.FuncOp) or fn.is_declaration:
                continue
            if "_init_" not in fn.sym_name.data:
                continue
            if not fn.body.blocks:
                continue
            block = fn.body.blocks[0]
            first_op = next(iter(block.ops), None)
            if first_op is None:
                continue
            # Error-code var name varies; intent(out) args are leading AllocaOps.
            err_var = "errflg"
            for bop in block.ops:
                if not isa(bop, memref.AllocaOp):
                    break
                hint = bop.memref.name_hint or ""
                if "err" in hint.lower() and "msg" not in hint.lower() and hint:
                    err_var = hint
                    break
            Rewriter.insert_op(
                ConstituentIndexLookupOp(std_names=std_name_attrs, err_var_name=err_var),
                InsertPoint.before(first_op),
            )
