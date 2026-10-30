"""Scheme call sequence: subcycles, active gating and the scheme call ops themselves."""

from __future__ import annotations


from xdsl.dialects import arith, builtin, llvm, memref, scf
from xdsl.dialects.builtin import (
    ArrayAttr,
    IntegerAttr,
    StringAttr,
    i8,
)
from xdsl.ir import SSAValue

from xdsl_ccpp.dialects import ccpp_utils
from xdsl_ccpp.dialects.ccpp_utils import (
    ActiveCheckOp,
    KeywordArgExprOp,
    KeywordCallOp,
    KindCastOp,
    KindWriteBackOp,
    MetadataLiteralExprOp,
    SubcycleLoopOp,
    UnitConvertOp,
    UnitWriteBackOp,
    VarRefExprOp,
    VerticalFlipOp,
    VerticalFlipWriteBackOp,
)
from xdsl_ccpp.transforms.util.cap_shared import (
    _iter_schemes,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    XMLSubcycle,
)
from xdsl_ccpp.transforms.util.typing import TypeConversions
from xdsl_ccpp.util.ccpp_conventions import (
    CCPP_ERROR_CODE,
    CCPP_ERROR_MESSAGE,
    CCPP_SUBCYCLE_UNKNOWN_LOOP_COUNT,
    UNIT_CONVERSIONS,
)
from xdsl_ccpp.transforms.suitecap.active import (
    _resolve_active_condition,
)
from xdsl_ccpp.transforms.suitecap.block_args import (
    _arg_dims,
    _std_key,
    _vertical_dim_index,
)
from xdsl_ccpp.transforms.suitecap.records import (
    _CallSeqContext,
    _raise_unresolved_pending_allocs_error,
)


class CallSequenceMixin:
    """Scheme call sequence: subcycles, active gating and the scheme call ops themselves."""

    def getSchemeNames(self, suite_description):
        """Return a flat list of (scheme_name, overrides) pairs from all groups,
        flattening through subcycles. ``overrides`` is ``{arg_name: literal_str}``.
        """
        return [
            (scheme.attributes["name"], scheme.attributes.get("arg_overrides", {}))
            for group in suite_description
            for scheme in _iter_schemes(group)
        ]

    def _build_call_sequence_items(self, node):
        """Recursively build the ordered item list for one group/subcycle's
        direct children.

        Each element is one of:
          ``('scheme',   scheme_name, overrides)``                              — flat call
          ``('subcycle', loop_count, is_literal, [item, item, ...])``           — subcycle block

        Nested subcycles become nested ``('subcycle', ...)`` items, to
        arbitrary depth.
        """
        items = []
        for child in node:
            if isinstance(child, XMLSubcycle):
                items.append((
                    "subcycle", child.attributes["loop_count"],
                    child.attributes["is_literal"],
                    self._build_call_sequence_items(child),
                ))
            else:
                items.append((
                    "scheme", child.attributes["name"],
                    child.attributes.get("arg_overrides", {}),
                ))
        return items

    def getCallSequence(self, suite_description):
        """Return the ordered call sequence, preserving subcycle boundaries.

        See `_build_call_sequence_items` for the item shape.
        """
        sequence = []
        for group in suite_description:
            sequence.extend(self._build_call_sequence_items(group))
        return sequence

    def _build_active_gated_call_ops(
        self, subroutine_name, arg_table, data_ops, overrides=None,
        divergent_std_keys: frozenset = frozenset(), *, suite_use_stubs: list,
    ):
        """Build scheme call ops for a flat (non-promoted) scheme call, gating
        each optional arg whose host var has an 'active' expression
        (model_var_active_expr) behind an ActiveCheckOp.

        Flat-call counterpart to _build_promoted_call_ops's PresentCheckOp
        (present() vs. a host condition; not interchangeable). Each distinct
        condition gets its own nested ActiveCheckOp (2**N leaf calls), since
        one scheme's optional args can depend on different conditions (e.g.
        examples/var_compat's effr_calc_run: has_graupel vs. has_ice).
        """
        active_gated_names: dict = {}  # raw active expression -> [arg_name, ...]
        for arg in arg_table.getFunctionArguments():
            if arg.hasAttr("optional") and arg.hasAttr("model_var_active_expr"):
                active_gated_names.setdefault(
                    arg.getAttr("model_var_active_expr"), []
                ).append(arg.name)

        if not active_gated_names:
            return self.generateSchemeSubroutineCallOps(
                subroutine_name, arg_table, data_ops, overrides or {},
                divergent_std_keys=divergent_std_keys,
            )

        raw_conditions = list(active_gated_names)

        def _build_leaf(excluded_names: frozenset) -> list:
            if excluded_names:
                return self.generateSchemeSubroutineCallOps(
                    subroutine_name, arg_table, data_ops, overrides or {},
                    exclude_args=excluded_names,
                    divergent_std_keys=divergent_std_keys,
                )
            return self.generateSchemeSubroutineCallOps(
                subroutine_name, arg_table, data_ops, overrides or {},
                divergent_std_keys=divergent_std_keys,
            )

        def _build_level(level: int, excluded_names: frozenset) -> list:
            if level == len(raw_conditions):
                return _build_leaf(excluded_names)
            raw_condition_expr = raw_conditions[level]
            # Built afresh for each ActiveCheckOp: a level below the first
            # appears once per branch above it, and an op has one parent.
            condition_op = _resolve_active_condition(
                self.meta_data, raw_condition_expr, suite_use_stubs, arg_table
            )
            with_ops = _build_level(level + 1, excluded_names)
            without_ops = _build_level(
                level + 1,
                excluded_names | frozenset(active_gated_names[raw_condition_expr]),
            )
            return [ActiveCheckOp(condition_op, with_ops, without_ops)]

        return _build_level(0, frozenset())

    def getArgumentTable(self, scheme_name, subroutine_name):
        """Look up the argument table for a specific scheme subroutine.

        Returns None if the scheme has no entry for subroutine_name (optional
        entry points such as _finalize may be absent).
        """
        if scheme_name not in self.meta_data:
            raise ValueError(
                f"No metadata found for scheme '{scheme_name}'. "
                f"Did you include its .meta file in --scheme-files?\n"
                f"Known schemes: {sorted(self.meta_data.keys())}"
            )
        arg_tables = self.meta_data[scheme_name].arg_tables
        return arg_tables.get(subroutine_name)

    def _build_suite_lifecycle_call_ops(
        self, scheme_name, entry_postfix, data_ops, fn_sigs, suite_use_stubs,
    ):
        """Build the guarded call for a suite-level ``<init>``/``<final>``
        scheme hook (v2.0 SDF schema), called once per suite lifecycle.

        Matches capgen-v1 (``suite_resolver.py``'s ``_resolve_one_call``):
        errmsg/errflg are shared with the enclosing subroutine; every other
        arg is resolved directly from its ``model_var_name``/
        ``model_module_name`` host match, since the scheme belongs to no group.

        Mutates *fn_sigs* (adds this call's signature) and *suite_use_stubs*
        (one USE stub per host-matched arg; duplicates are deduplicated later
        in ``match_and_rewrite``). Returns [] if *scheme_name* is falsy.
        """
        if not scheme_name:
            return []

        subroutine_name = scheme_name + entry_postfix
        arg_table = self.getArgumentTable(scheme_name, subroutine_name)
        if arg_table is None:
            phase = entry_postfix.strip("_")
            raise ValueError(
                f"Suite declares <{phase}>{scheme_name}</{phase}> but scheme "
                f"'{scheme_name}' has no '{entry_postfix}' phase in its metadata."
            )

        local_data_ops = {}
        host_ref_ops = []
        for fn_arg in arg_table.getFunctionArguments():
            std_name = fn_arg.getAttr("standard_name") if fn_arg.hasAttr("standard_name") else None
            if std_name == CCPP_ERROR_MESSAGE:
                local_data_ops[fn_arg.name] = data_ops["errmsg"]
            elif std_name == CCPP_ERROR_CODE:
                local_data_ops[fn_arg.name] = data_ops["errflg"]
            elif fn_arg.hasAttr("model_var_name"):
                model_var_name = fn_arg.getAttr("model_var_name")
                model_module_name = fn_arg.getAttr("model_module_name")
                ref_op = ccpp_utils.HostVarRefOp(
                    model_var_name,
                    model_module_name,
                    TypeConversions.getBaseType(fn_arg.getAttr("type")),
                )
                host_ref_ops.append(ref_op)
                local_data_ops[fn_arg.name] = ref_op.res
                stub = llvm.GlobalOp(
                    llvm.LLVMArrayType.from_size_and_type(1, i8),
                    model_var_name, "external",
                )
                stub.attributes["module"] = StringAttr(model_module_name)
                suite_use_stubs.append(stub)
            else:
                raise ValueError(
                    f"Suite-level <{entry_postfix.strip('_')}> scheme "
                    f"'{scheme_name}' has arg '{fn_arg.name}' (standard_name "
                    f"'{std_name}') with no host match -- suite-level init/final "
                    "hooks currently only support plain host-module-matched "
                    "scalar args, not DDT members or cap-owned scratch values."
                )

        call_ops = self.generateSchemeSubroutineCallOps(
            subroutine_name, arg_table, local_data_ops,
        )
        if subroutine_name not in fn_sigs:
            fn_sigs[subroutine_name] = self.meta_fn_sigs[subroutine_name]
        return host_ref_ops + call_ops

    def generateSchemeSubroutineCallOps(
        self, subroutine_name, arg_table, data_ops, overrides=None,
        exclude_args=frozenset(), divergent_std_keys: frozenset = frozenset(),
    ):
        """Build the IR for a single scheme subroutine call guarded by errflg.

        Wraps the call in an scf.if on errflg == 0. Where the cap's local type
        differs from the callee's declared type, an UnrealizedConversionCastOp
        is inserted (the Fortran printer looks through it).

        Always emits a KeywordCallOp (name=value syntax): .meta arg order
        need not match the .F90 dummy order. *overrides* are carried as
        compile-time literals instead of SSA operands.

        divergent_std_keys are standard_names whose schemes disagree on kind
        or units (see _build_arg_tables); for these, the host-native shared
        value is marshaled per call (see _apply_divergent_marshaling).
        """
        if overrides is None:
            overrides = {}

        # The override dict is shared across entry points; keep only this table's args.
        arg_names_in_table = {arg.name for arg in arg_table.getFunctionArguments()}
        overrides = {k: v for k, v in overrides.items() if k in arg_names_in_table}

        # Callee input types, to detect mismatches. All args are passed by
        # reference, so the call has no SSA results.
        callee = self.meta_fn_sigs.get(subroutine_name)
        callee_in_types = list(callee.function_type.inputs) if callee else []

        in_ssa = []
        in_names = []
        cast_ops = []  # casts inserted before the call inside the if-body
        divergent_writeback_ops = []  # write-backs inserted after the call
        in_idx = 0

        def _apply_divergent_marshaling(arg, val):
            """Adapt val (the shared, host-native value) to this scheme's
            kind/unit and vertical (top_at_one) convention for a divergent
            standard_name. Appends forward casts to cast_ops and write-backs,
            in reverse order, to divergent_writeback_ops. Returns the value
            to pass to the call.
            """
            if _std_key(arg) not in divergent_std_keys:
                return val
            intent = arg.getAttr("intent") if arg.hasAttr("intent") else "in"
            chain: list = []  # (kind/unit/flip, result_ssa, source_ssa, param)
            cur = val
            if arg.hasAttr("model_var_kind_mismatch") and arg.getAttr("type") != "character":
                scheme_kind, host_kind = arg.getAttr("model_var_kind_mismatch").split(":")
                scheme_type = TypeConversions.convert(
                    arg.getAttr("type"), scheme_kind, _arg_dims(arg)
                )
                cast_op = KindCastOp(cur, scheme_kind, scheme_type)
                cast_op.res.name_hint = f"{arg.name}_kind_cast"
                cast_ops.append(cast_op)
                chain.append(("kind", cast_op.res, cur, host_kind))
                cur = cast_op.res
            if arg.hasAttr("model_var_unit_mismatch"):
                scheme_units, host_units = arg.getAttr("model_var_unit_mismatch").split(":", 1)
                to_scheme, to_host = UNIT_CONVERSIONS[(scheme_units, host_units)]
                kind_str = arg.getAttr("kind") if arg.hasAttr("kind") else None
                arg_type = TypeConversions.convert(
                    arg.getAttr("type"), kind_str, _arg_dims(arg),
                )
                # intent(out): the scheme does not read the value, so no conversion in.
                conv_op = UnitConvertOp(cur, arg_type, *(() if intent == "out" else to_scheme))
                conv_op.res.name_hint = f"{arg.name}_unit_conv"
                cast_ops.append(conv_op)
                chain.append(("unit", conv_op.res, cur, to_host))
                cur = conv_op.res
            if arg.hasAttr("top_at_one"):
                vert_dim = _vertical_dim_index(arg)
                if vert_dim is not None:
                    flip_op = VerticalFlipOp(cur, vert_dim, cur.type)
                    flip_op.res.name_hint = f"{arg.name}_vert_flip"
                    cast_ops.append(flip_op)
                    chain.append(("flip", flip_op.res, cur, vert_dim))
                    cur = flip_op.res
            if intent in ("inout", "out"):
                for kind_or_unit, result_ssa, source_ssa, param in reversed(chain):
                    if kind_or_unit == "kind":
                        divergent_writeback_ops.append(
                            KindWriteBackOp(result_ssa, source_ssa, param)
                        )
                    elif kind_or_unit == "unit":
                        divergent_writeback_ops.append(
                            UnitWriteBackOp(result_ssa, source_ssa, *param)
                        )
                    else:
                        divergent_writeback_ops.append(
                            VerticalFlipWriteBackOp(result_ssa, source_ssa, param)
                        )
            return cur

        # Fortran passes ALL arguments by reference, so in/inout/out are
        # marshaled identically.
        for arg in arg_table.getFunctionArguments():
            intent = arg.getAttr("intent")
            if intent not in ("in", "inout", "out"):
                raise ValueError(
                    f"Argument '{arg.name}' has unrecognized intent "
                    f"'{intent}' (expected 'in', 'inout', or 'out') -- "
                    f"silently dropping it here would desync the "
                    f"positional in_idx counter below against the "
                    f"real callee signature."
                )
            is_overridden = arg.name in overrides
            is_excluded = arg.name in exclude_args
            if not is_overridden and not is_excluded:
                # Prefer the standard_name-tagged entry: bare names can be
                # ambiguous across schemes (see _build_framework_refs).
                val = data_ops.get(("std_name", _std_key(arg)), data_ops[arg.name])
                val = _apply_divergent_marshaling(arg, val)
                actual_type = (
                    val.type if isinstance(val, SSAValue) else val.results[0].type
                )
                expected_type = (
                    callee_in_types[in_idx]
                    if in_idx < len(callee_in_types)
                    else actual_type
                )
                if actual_type != expected_type:
                    cast = builtin.UnrealizedConversionCastOp(
                        operands=[[val]], result_types=[[expected_type]]
                    )
                    cast_ops.append(cast)
                    in_ssa.append(cast.results[0])
                else:
                    in_ssa.append(val)
                in_names.append(arg.name)
            in_idx += 1

        # Call by keyword: .meta arg order is not guaranteed to match the
        # .F90 dummy order (e.g. examples/chunked_data). Matches capgen-v1.
        call_op = KeywordCallOp(
            subroutine_name,
            ArrayAttr([StringAttr(n) for n in in_names]),
            ArrayAttr([]),
            in_ssa,
            [],
            # Overrides are literals of unknown type from the suite
            # definition, kept verbatim.
            override_ops=[
                KeywordArgExprOp(k, MetadataLiteralExprOp(v)) for k, v in (overrides or {}).items()
            ],
        )

        # Only execute when errflg == 0
        err_const_comp = arith.ConstantOp.from_int_and_width(0, 32)
        load_op = memref.LoadOp.get(data_ops["errflg"], [])
        cmp = arith.CmpiOp(load_op, err_const_comp, 0)
        conditional_op = scf.IfOp(
            cmp, [],
            cast_ops + [call_op] + divergent_writeback_ops + [scf.YieldOp()],
        )

        return [err_const_comp, load_op, cmp, conditional_op]

    def _emit_ordered_list(
        self, scheme_list, ctx, fn_sigs, resolved_producers, pending_allocs,
        already_scheduled_allocs,
    ) -> list:
        """Emit call ops for (scheme_name, tbl) pairs in order.

        Consecutive promoted schemes sharing the same promoted_dim are
        grouped into a single PromotionLoopOp.
        """
        result: list = []
        cur_pdim: str | None = None
        cur_pgroup: list = []
        for sn, tbl in scheme_list:
            full_name = sn + ctx.actual_postfixes.get(sn, ctx.tgt_subroutine_postfix)
            assert full_name in self.meta_fn_sigs
            if full_name not in fn_sigs:
                fn_sigs[full_name] = self.meta_fn_sigs[full_name]
            if ctx.physics_mode and self._scheme_has_promoted_args(tbl):
                pdim = next(
                    (
                        arg.getAttr("promoted_dim").lower()
                        for arg in tbl.getFunctionArguments()
                        if arg.hasAttr("is_promoted")
                        and arg.hasAttr("promoted_dim")
                    ),
                    None,
                )
                if pdim == cur_pdim:
                    cur_pgroup.append((sn, tbl))
                else:
                    result += self._flush_promoted(ctx, cur_pdim, cur_pgroup, fn_sigs)
                    cur_pgroup = [(sn, tbl)]
                    cur_pdim = pdim
            else:
                result += self._flush_promoted(ctx, cur_pdim, cur_pgroup, fn_sigs)
                cur_pgroup = []
                cur_pdim = None
                result += self._build_active_gated_call_ops(
                    full_name, tbl, ctx.data_ops, ctx.scheme_overrides.get(sn, {}),
                    divergent_std_keys=ctx.divergent_std_keys,
                    suite_use_stubs=ctx.suite_use_stubs,
                )
                resolved_producers.add(sn)
                result += self._resolve_and_splice_pending_allocs(
                    sn, ctx, resolved_producers, pending_allocs,
                    already_scheduled_allocs,
                )
        result += self._flush_promoted(ctx, cur_pdim, cur_pgroup, fn_sigs)
        return result

    def _emit_subcycle_items(
        self, items, ctx, fn_sigs, resolved_producers, pending_allocs,
        already_scheduled_allocs, hoisted_allocas,
    ) -> list:
        """Build call ops for one subcycle's children.

        Consecutive flat schemes are grouped into one _emit_ordered_list call
        (so promotion-loop coalescing works); nested subcycles recurse via
        _emit_subcycle, so grouping never crosses a nested boundary.
        """
        result: list = []
        pending: list = []
        for sub_item in items:
            if sub_item[0] == "scheme":
                _, sn, _ = sub_item
                if sn in ctx.arg_tables:
                    pending.append((sn, ctx.arg_tables[sn]))
            else:
                if pending:
                    result += self._emit_ordered_list(
                        pending, ctx, fn_sigs, resolved_producers,
                        pending_allocs, already_scheduled_allocs,
                    )
                    pending = []
                _, nested_loop_count, nested_is_literal, nested_items = sub_item
                result += self._emit_subcycle(
                    nested_loop_count, nested_is_literal, nested_items, ctx,
                    fn_sigs, resolved_producers, pending_allocs,
                    already_scheduled_allocs, hoisted_allocas,
                )
        if pending:
            result += self._emit_ordered_list(
                pending, ctx, fn_sigs, resolved_producers, pending_allocs,
                already_scheduled_allocs,
            )
        return result

    def _emit_subcycle(
        self, loop_count, is_literal, items, ctx, fn_sigs, resolved_producers,
        pending_allocs, already_scheduled_allocs, hoisted_allocas,
    ) -> list:
        body_ops = self._emit_subcycle_items(
            items, ctx, fn_sigs, resolved_producers, pending_allocs,
            already_scheduled_allocs, hoisted_allocas,
        )
        _lc_int = (int(loop_count) if is_literal
                   else CCPP_SUBCYCLE_UNKNOWN_LOOP_COUNT)
        # Subcycles only loop the _run phase (matches capgen-v1); physics_mode
        # alone is also true for the other group-scoped phases.
        if (_lc_int > 1 and ctx.physics_mode and body_ops
                and ctx.tgt_subroutine_postfix == "_run"):
            sc_alloc = memref.AllocaOp.get(
                TypeConversions.getBaseType("integer"), shape=[]
            )
            sc_alloc.memref.name_hint = "ccpp_loop_cnt"
            hoisted_allocas.append(sc_alloc)
            # A non-literal loop_count is a standard_name; resolve it to the
            # matching arg's local name (possibly synthesized by
            # _synthesize_dynamic_loop_count_args).
            printed_loop_count = loop_count
            if not is_literal:
                resolved = ctx.all_args.get(loop_count.lower())
                if resolved is None:
                    raise ValueError(
                        f"Subcycle loop count {loop_count!r} is not a "
                        f"literal integer and has no matching "
                        f"host-declared variable anywhere -- give the "
                        f"host a variable with this standard_name, or "
                        f"make the subcycle's loop count a literal "
                        f"integer."
                    )
                printed_loop_count = resolved.name
            loop_count_op = (
                arith.ConstantOp(IntegerAttr.from_int_and_width(int(printed_loop_count), 32))
                if is_literal
                else VarRefExprOp(printed_loop_count)
            )
            return [SubcycleLoopOp(
                loop_count_op=loop_count_op,
                loop_var=sc_alloc.memref,
                body_ops=body_ops,
                is_literal=is_literal,
            )]
        return body_ops

    def _build_call_ops(
        self,
        suite_description,
        tgt_subroutine_postfix,
        physics_mode,
        all_args,
        data_ops,
        framework_ref_ops,
        suite_use_stubs,
        actual_postfixes,
        arg_tables,
        scheme_overrides,
        divergent_std_keys: frozenset = frozenset(),
        pending_allocs: dict = None,
        already_scheduled_allocs=None,
        call_sequence_items=None,
    ):
        """Build scheme call ops and collect fn_sigs for all items in the call sequence.

        pending_allocs -- producer_scheme -> list[_PendingAlloc] from
        _build_framework_refs. Each entry's LazyAllocOp is spliced in right
        after its producer's call ops; entries still unresolved at the end
        raise an error rather than emitting wrong-order Fortran.
        """
        call_ops = []
        fn_sigs = {}
        pending_allocs = pending_allocs or {}
        resolved_producers: set = set()
        if tgt_subroutine_postfix is None:
            return call_ops, fn_sigs

        call_sequence = (
            call_sequence_items
            if call_sequence_items is not None
            else self.getCallSequence(suite_description)
        )
        ctx = _CallSeqContext(
            all_args=all_args,
            data_ops=data_ops,
            framework_ref_ops=framework_ref_ops,
            suite_use_stubs=suite_use_stubs,
            actual_postfixes=actual_postfixes,
            tgt_subroutine_postfix=tgt_subroutine_postfix,
            physics_mode=physics_mode,
            scheme_overrides=scheme_overrides,
            divergent_std_keys=divergent_std_keys,
            arg_tables=arg_tables,
        )

        # Subcycle loop-count allocas are hoisted to the top level because
        # print_ftn.py's declaration scan doesn't recurse into nested bodies.
        hoisted_allocas: list = []

        for item in call_sequence:
            if item[0] == "scheme":
                _, scheme_name, _ = item
                if scheme_name not in arg_tables:
                    continue
                call_ops += self._emit_ordered_list(
                    [(scheme_name, arg_tables[scheme_name])], ctx, fn_sigs,
                    resolved_producers, pending_allocs, already_scheduled_allocs,
                )
            elif item[0] == "subcycle":
                _, loop_count, is_literal, subcycle_items = item
                call_ops += self._emit_subcycle(
                    loop_count, is_literal, subcycle_items, ctx, fn_sigs,
                    resolved_producers, pending_allocs, already_scheduled_allocs,
                    hoisted_allocas,
                )

        if pending_allocs:
            _raise_unresolved_pending_allocs_error(pending_allocs, tgt_subroutine_postfix)

        return hoisted_allocas + call_ops, fn_sigs
