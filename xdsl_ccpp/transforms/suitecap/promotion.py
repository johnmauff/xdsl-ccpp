"""Rank promotion: loops over a promoted dimension around scheme calls."""

from __future__ import annotations


from xdsl.dialects import arith, llvm, memref
from xdsl.dialects.builtin import (
    MemRefType,
    StringAttr,
    i8,
)
from xdsl.ir import SSAValue

from xdsl_ccpp.dialects import ccpp_utils
from xdsl_ccpp.dialects.ccpp import ArgOwnershipKind
from xdsl_ccpp.dialects.ccpp_utils import (
    PresentCheckOp,
    PromotionLoopOp,
    RankReducingSliceOp,
)
from xdsl_ccpp.transforms.util.typing import TypeConversions
from xdsl_ccpp.util.ccpp_conventions import (
    CCPP_HORIZ_DIM_STD_NAME,
    CCPP_LOOP_EXTENT_STD_NAME,
    dims_compatible,
)
from xdsl_ccpp.transforms.suitecap.block_args import (
    _find_producer_scheme,
    _std_key,
)


class PromotionMixin:
    """Rank promotion: loops over a promoted dimension around scheme calls."""

    def _scheme_has_promoted_args(self, arg_table) -> bool:
        """Return True if any argument in arg_table is marked is_promoted."""
        for arg in arg_table.getFunctionArguments():
            if arg.hasAttr("is_promoted"):
                return True
        return False

    def _find_loop_upper_bound(self, promoted_dim: str, all_args, data_ops,
                               framework_ref_ops=None, suite_use_stubs=None):
        """Find the SSA value to use as the promotion loop's upper bound.

        Lookup order: integer scheme args in all_args; then MODULE-type host
        tables (creating a HostVarRefOp + USE stub); then size() of an
        in-scope array with a matching dim_names entry. HOST-type tables are
        deliberately not scanned: their vars are never use-associated.
        """
        # Exact match first: dims_compatible treats layer and interface
        # dimensions as compatible, but their sizes differ.
        for arg in all_args.values():
            if (
                arg.hasAttr("standard_name")
                and arg.getAttr("standard_name") == promoted_dim
                and arg.getAttr("type") == "integer"
                and arg.name in data_ops
            ):
                return data_ops[arg.name]
        # Compatible fallback: catches horizontal dim aliases (e.g.
        # horizontal_loop_extent matching horizontal_dimension).
        for arg in all_args.values():
            if (
                arg.hasAttr("standard_name")
                and dims_compatible(arg.getAttr("standard_name"), promoted_dim)
                and arg.getAttr("type") == "integer"
                and arg.name in data_ops
            ):
                return data_ops[arg.name]

        # Not found in scheme args — try MODULE-type host tables.
        from xdsl_ccpp.transforms.util.ccpp_descriptors import CCPPType
        from xdsl_ccpp.transforms.util.typing import TypeConversions
        # Exact match pass first (same reason as above).
        for tbl_name, props in self.meta_data.items():
            if props.getAttr("type") != CCPPType.MODULE:
                continue
            if tbl_name not in props.arg_tables:
                continue
            for var in props.getArgTable(tbl_name).getFunctionArguments():
                if (var.hasAttr("standard_name")
                        and var.getAttr("standard_name") == promoted_dim
                        and var.getAttr("type") == "integer"):
                    if var.name in data_ops:
                        return data_ops[var.name]
                    int_type = TypeConversions.getBaseType("integer")
                    ref = ccpp_utils.HostVarRefOp(var.name, tbl_name,
                                                  memref.MemRefType(int_type, []))
                    ref.res.name_hint = var.name
                    data_ops[var.name] = ref
                    if framework_ref_ops is not None:
                        framework_ref_ops.append(ref)
                    if suite_use_stubs is not None:
                        stub = llvm.GlobalOp(
                            llvm.LLVMArrayType.from_size_and_type(1, i8),
                            var.name, "external",
                        )
                        # Mirrors _build_fn_signatures's module-name resolution.
                        module_name = (
                            props.getAttr("source_module")
                            if props.hasAttr("source_module") else tbl_name
                        )
                        stub.attributes["module"] = StringAttr(module_name)
                        suite_use_stubs.append(stub)
                    return data_ops[var.name]
        # Compatible fallback pass for MODULE tables.
        for tbl_name, props in self.meta_data.items():
            if props.getAttr("type") != CCPPType.MODULE:
                continue
            if tbl_name not in props.arg_tables:
                continue
            for var in props.getArgTable(tbl_name).getFunctionArguments():
                if (var.hasAttr("standard_name")
                        and dims_compatible(var.getAttr("standard_name"), promoted_dim)
                        and var.getAttr("type") == "integer"):
                    if var.name in data_ops:
                        return data_ops[var.name]
                    int_type = TypeConversions.getBaseType("integer")
                    ref = ccpp_utils.HostVarRefOp(var.name, tbl_name,
                                                  memref.MemRefType(int_type, []))
                    ref.res.name_hint = var.name
                    data_ops[var.name] = ref
                    if framework_ref_ops is not None:
                        framework_ref_ops.append(ref)
                    if suite_use_stubs is not None:
                        stub = llvm.GlobalOp(
                            llvm.LLVMArrayType.from_size_and_type(1, i8),
                            var.name, "external",
                        )
                        module_name = (
                            props.getAttr("source_module")
                            if props.hasAttr("source_module") else tbl_name
                        )
                        stub.attributes["module"] = StringAttr(module_name)
                        suite_use_stubs.append(stub)
                    return data_ops[var.name]

        # Derive from an in-scope array's shape. SuiteOwned arrays are
        # excluded: they may not be allocated yet (or may match themselves,
        # giving a self-referential size()).
        for arg in all_args.values():
            if not arg.hasAttr("dim_names") or arg.name not in data_ops:
                continue
            if arg.getAttr("ownership_kind") == ArgOwnershipKind.SuiteOwned:
                continue
            for idx, dim_name in enumerate(arg.getAttr("dim_names"), start=1):
                if dims_compatible(dim_name, promoted_dim):
                    int_type = TypeConversions.getBaseType("integer")
                    size_ref = ccpp_utils.CapVarRefOp(
                        f"size({arg.name}, {idx})",
                        memref.MemRefType(int_type, []),
                    )
                    if framework_ref_ops is not None:
                        framework_ref_ops.append(size_ref)
                    return size_ref.res
        return None

    def _resolve_alloc_dim_var_refs(
        self, alloc_dim_names, all_args, data_ops, framework_ref_ops,
        suite_use_stubs, arg_tables, resolved_producers,
    ) -> tuple:
        """Resolve each of alloc_dim_names to an SSA upper bound for an allocation.

        Returns (dim_var_refs, pending_producer_scheme). The producer is set
        when a dimension is a same-phase SuiteOwned intent(out) var -- or, in
        a package cap, any var a scheme of the segment writes before it is
        read (declared intent(out)), including dummy arguments the segment
        returns -- whose producing scheme hasn't been called yet; the caller
        retries after emitting that call. An unresolvable dimension returns ([], None) so
        the allocation is deferred rather than emitted with the wrong rank.
        """
        dim_var_refs = []
        for dim_std_name in alloc_dim_names:
            alloc_dim = (
                CCPP_HORIZ_DIM_STD_NAME
                if dim_std_name.lower() == CCPP_LOOP_EXTENT_STD_NAME
                else dim_std_name
            )
            matching = next(
                (a for a in all_args.values()
                 if a.hasAttr("standard_name")
                 and dims_compatible(a.getAttr("standard_name"), alloc_dim)),
                None,
            )
            if matching is not None and (
                # A package cap's segment returns what its schemes write first.
                matching.getAttr("declared_intent") == "out"
                if getattr(self, "generating_package_cap", False)
                and matching.hasAttr("declared_intent")
                else matching.getAttr("ownership_kind") == ArgOwnershipKind.SuiteOwned
                and matching.getAttr("intent") == "out"
            ):
                producer = _find_producer_scheme(matching, arg_tables)
                if producer is not None and producer not in resolved_producers:
                    return [], producer
            if matching and matching.name in data_ops:
                dim_var_refs.append(data_ops[matching.name])
            else:
                ssa = self._find_loop_upper_bound(
                    alloc_dim, all_args, data_ops,
                    framework_ref_ops=framework_ref_ops,
                    suite_use_stubs=suite_use_stubs,
                )
                if ssa is not None:
                    dim_var_refs.append(ssa)
                else:
                    # Dimension var produced in a prior phase (e.g. _init)
                    # lives in data_ops under its std_name tag.
                    fw_ref = data_ops.get(("std_name", alloc_dim.lower()))
                    if fw_ref is not None:
                        dim_var_refs.append(fw_ref)
                    else:
                        return [], None
        return dim_var_refs, None

    def _build_promoted_call_ops(
        self,
        subroutine_name,
        arg_table,
        data_ops,
        loop_var_memref,
        overrides=None,
        ncol_ref=None,
    ):
        """Build scheme call ops for a promoted scheme inside the loop body.

        Promoted args are replaced by a RankReducingSliceOp for the current
        level. ncol_ref is the column count used as the upper bound of
        block-arg column slices; data_ops["ncol"] isn't populated under the
        horizontal_dimension convention.
        """
        promoted_data_ops = dict(data_ops)  # shallow copy to override promoted args

        # Optional+promoted slices go only in PresentCheckOp's with_body;
        # shared slices are emitted before any guard.
        shared_slice_ops: list = []
        opt_slice_ops: dict[str, object] = {}  # arg_name -> RankReducingSliceOp

        def _get_lbound_one():
            # Lazily create (and cache) a constant-1 alloca for block-arg
            # lower bounds; it may not have been created elsewhere.
            if "ccpp_lbound_one" not in data_ops:
                _ib = TypeConversions.getBaseType("integer")
                _alloc = memref.AllocaOp.get(_ib, shape=[])
                _alloc.memref.name_hint = "ccpp_lbound_one"
                _const = arith.ConstantOp.from_int_and_width(1, 32)
                _store = memref.StoreOp.get(_const, _alloc, [])
                shared_slice_ops.extend([_alloc, _const, _store])
                data_ops["ccpp_lbound_one"] = _alloc
            return data_ops["ccpp_lbound_one"]

        for arg in arg_table.getFunctionArguments():
            needs_slice = arg.hasAttr("is_promoted")
            # Also slice interstitial vars allocated at higher rank than the
            # scheme declares.
            if not needs_slice and arg.hasAttr("is_interstitial") and arg.name in data_ops:
                val = data_ops[arg.name]
                actual_type = val.type if isinstance(val, SSAValue) else val.results[0].type
                if isinstance(actual_type, MemRefType):
                    actual_rank = len(actual_type.shape.data)
                    scheme_rank = arg.getAttr("dimensions") if arg.hasAttr("dimensions") else 0
                    needs_slice = (actual_rank > scheme_rank > 0)
            if not needs_slice:
                continue
            if arg.name not in data_ops:
                continue
            # Pattern: 'R' = range (col_start:col_end), 'S' = scalar (loop var index).
            pattern = ""
            range_lowers = []
            range_uppers = []
            scalar_indices_list = []

            if arg.hasAttr("is_promoted"):
                dim_names = arg.getAttr("dim_names") if arg.hasAttr("dim_names") else []
                val = data_ops[arg.name]
                # Module-level vars span the full domain (col_start:col_end);
                # block args are 1-based sections (1:ncol).
                is_module_var = not isinstance(val, SSAValue)
                for dim in dim_names:
                    pattern += "R"
                    if is_module_var:
                        range_lowers.append(data_ops.get("col_start", loop_var_memref))
                        range_uppers.append(data_ops.get("col_end", loop_var_memref))
                    else:
                        range_lowers.append(_get_lbound_one())
                        range_uppers.append(
                            ncol_ref if ncol_ref is not None
                            else data_ops.get("ncol", loop_var_memref)
                        )
                pattern += "S"
                scalar_indices_list.append(loop_var_memref)
            else:
                scheme_rank = arg.getAttr("dimensions") if arg.hasAttr("dimensions") else 0
                val = data_ops[arg.name]
                actual_type = val.type if isinstance(val, SSAValue) else val.results[0].type
                actual_rank = len(actual_type.shape.data) if isinstance(actual_type, MemRefType) else scheme_rank
                for _ in range(scheme_rank):
                    pattern += "R"
                    range_lowers.append(data_ops.get("col_start", loop_var_memref))
                    range_uppers.append(data_ops.get("col_end", loop_var_memref))
                for _ in range(actual_rank - scheme_rank):
                    pattern += "S"
                    scalar_indices_list.append(loop_var_memref)

            if pattern and ("S" in pattern):
                slice_op = RankReducingSliceOp(
                    source=data_ops[arg.name],
                    dim_pattern=pattern,
                    range_lowers=range_lowers,
                    range_uppers=range_uppers,
                    scalar_indices=scalar_indices_list,
                )
                promoted_data_ops[arg.name] = slice_op
                # generateSchemeSubroutineCallOps prefers the std_name-tagged
                # entry, so keep it in sync with the slice.
                promoted_data_ops[("std_name", _std_key(arg))] = slice_op
                is_opt_promoted = arg.hasAttr("optional") and arg.hasAttr("is_promoted")
                if is_opt_promoted:
                    opt_slice_ops[arg.name] = slice_op
                else:
                    shared_slice_ops.append(slice_op)

        optional_promoted_names = [
            arg.name
            for arg in arg_table.getFunctionArguments()
            if arg.hasAttr("optional") and arg.hasAttr("is_promoted")
        ]

        if not optional_promoted_names:
            call_ops = self.generateSchemeSubroutineCallOps(
                subroutine_name, arg_table, promoted_data_ops, overrides or {}
            )
            return shared_slice_ops + call_ops

        optional_promoted_set = set(optional_promoted_names)

        with_call_ops = self.generateSchemeSubroutineCallOps(
            subroutine_name, arg_table, promoted_data_ops, overrides or {}
        )
        with_body_ops = list(opt_slice_ops.values()) + with_call_ops

        without_call_ops = self.generateSchemeSubroutineCallOps(
            subroutine_name, arg_table, promoted_data_ops, overrides or {},
            exclude_args=optional_promoted_set,
        )

        # All optional promoted args are guarded as a group by the first one.
        # TODO: handle each independently for full generality.
        guard_name = optional_promoted_names[0]
        present_op = PresentCheckOp(guard_name, with_body_ops, without_call_ops)
        return shared_slice_ops + [present_op]

    def _flush_promoted(self, ctx, cur_pdim, cur_pgroup, fn_sigs) -> list:
        """Emit cur_pgroup's calls, wrapped in a PromotionLoopOp if the upper bound resolves.

        Mutates fn_sigs in place.
        """
        if not cur_pgroup:
            return []
        upper_bound_ref = (
            self._find_loop_upper_bound(
                cur_pdim, ctx.all_args, ctx.data_ops,
                framework_ref_ops=ctx.framework_ref_ops,
                suite_use_stubs=ctx.suite_use_stubs,
            )
            if cur_pdim
            else None
        )
        if upper_bound_ref is None:
            ops = []
            for sn, tbl in cur_pgroup:
                full_name = sn + ctx.actual_postfixes.get(sn, ctx.tgt_subroutine_postfix)
                ops += self.generateSchemeSubroutineCallOps(
                    full_name, tbl, ctx.data_ops, ctx.scheme_overrides.get(sn, {}),
                    divergent_std_keys=ctx.divergent_std_keys,
                )
                if full_name not in fn_sigs:
                    fn_sigs[full_name] = self.meta_fn_sigs[full_name]
            return ops
        lv_alloc = memref.AllocaOp.get(
            TypeConversions.getBaseType("integer"), shape=[]
        )
        lv_alloc.memref.name_hint = "vertical_layer_index"
        ncol_ref = self._find_loop_upper_bound(
            CCPP_HORIZ_DIM_STD_NAME, ctx.all_args, ctx.data_ops,
            framework_ref_ops=ctx.framework_ref_ops,
            suite_use_stubs=ctx.suite_use_stubs,
        )
        body_list: list = []
        for sn, tbl in cur_pgroup:
            full_name = sn + ctx.actual_postfixes.get(sn, ctx.tgt_subroutine_postfix)
            body_list += self._build_promoted_call_ops(
                full_name, tbl, ctx.data_ops, lv_alloc.memref,
                ctx.scheme_overrides.get(sn, {}),
                ncol_ref=ncol_ref,
            )
            if full_name not in fn_sigs:
                fn_sigs[full_name] = self.meta_fn_sigs[full_name]
        return [lv_alloc, PromotionLoopOp(
            loop_var=lv_alloc.memref,
            upper_bound=upper_bound_ref,
            body_ops=body_list,
        )]
