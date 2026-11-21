"""Suite-owned (framework) variables: references, allocation scheduling and module-scope storage."""

from __future__ import annotations

from xdsl.dialects import arith, memref

from xdsl_ccpp.dialects import ccpp_utils
from xdsl_ccpp.dialects.ccpp_utils import (
    ClearStringOp,
    LazyAllocOp,
    MetadataLiteralExprOp,
    RankReducingSliceOp,
    VarRefExprOp,
)
from xdsl_ccpp.transforms.util.typing import TypeConversions
from xdsl_ccpp.util.ccpp_conventions import (
    CCPP_HORIZ_DIM_STD_NAME,
    CCPP_LOOP_BEGIN_STD_NAME,
    CCPP_LOOP_END_STD_NAME,
    CCPP_LOOP_EXTENT_STD_NAME,
)
from xdsl_ccpp.util.errors import warn_once
from xdsl_ccpp.transforms.suitecap.block_args import (
    _alias_canonical_data_ops,
    _std_key,
)
from xdsl_ccpp.transforms.suitecap.records import (
    _PendingAlloc,
)


class SuiteOwnedMixin:
    """Suite-owned (framework) variables: references, allocation scheduling and module-scope storage."""

    def generateVariableInitialisations(self, data_ops):
        """Emit ops that zero-initialise errflg and clear errmsg at subroutine entry."""
        err_const = arith.ConstantOp.from_int_and_width(0, 32)
        store_op = memref.StoreOp.get(err_const, data_ops["errflg"], [])
        clear_errmsg = ClearStringOp(data_ops["errmsg"])
        return [err_const, store_op, clear_errmsg]

    def _resolve_and_splice_pending_allocs(
        self, scheme_name, ctx, resolved_producers, pending_allocs,
        already_scheduled_allocs,
    ) -> list:
        """Retry pending_allocs keyed to scheme_name after its call ops are
        emitted; returns the LazyAllocOps to splice in right after them.
        Mutates pending_allocs/already_scheduled_allocs.
        """
        ops: list = []
        if scheme_name not in pending_allocs:
            return ops
        for _pending in pending_allocs.pop(scheme_name):
            _dim_var_refs, _still_pending = self._resolve_alloc_dim_var_refs(
                _pending.alloc_dim_names, ctx.all_args, ctx.data_ops,
                ctx.framework_ref_ops, ctx.suite_use_stubs, ctx.arg_tables,
                resolved_producers, package_scoped=ctx.package_scoped,
            )
            if _still_pending is not None:
                # Dimension produced by a later scheme; re-register under it.
                pending_allocs.setdefault(_still_pending, []).append(_pending)
            elif _dim_var_refs:
                ops.append(
                    LazyAllocOp(
                        var_name=_pending.var_name,
                        dim_var_refs=_dim_var_refs,
                        init_value_op=(
                            MetadataLiteralExprOp(_pending.init_value)
                            if _pending.init_value is not None else None
                        ),
                        needs_device_residency=_pending.needs_device_residency,
                        is_run_local=_pending.is_run_local,
                    )
                )
                if already_scheduled_allocs is not None:
                    already_scheduled_allocs.add(_pending.std_key)
            else:
                # Unresolvable dimension: warn at generation time.
                _dim_desc = ", ".join(str(d) for d in _pending.alloc_dim_names)
                warn_once(
                    f"cannot resolve allocation dimensions for"
                    f" '{_pending.var_name}'"
                    f" (std_name='{_pending.std_key}', dims=({_dim_desc}))"
                    f" after scheme '{scheme_name}' ran"
                    f" -- no allocate() will be generated.",
                )
        return ops

    def _build_framework_var_ref(
        self, fw_arg, fw_std_key, all_args, data_ops, framework_ref_ops,
        suite_model, column_range,
    ) -> tuple:
        """Build fw_arg's HostVarRefOp and register it in data_ops (under its
        bare name and the suite model's canonical local_name). In physics
        mode, an array with a horizontal first dimension is sliced to the
        current chunk via an all-'R' RankReducingSliceOp.

        Mutates framework_ref_ops/data_ops. Returns (var_name, suite_entry).
        """
        _scheme_dims = fw_arg.getAttr("dimensions") if fw_arg.hasAttr("dimensions") else 0

        if suite_model is not None:
            _entry = suite_model.get(fw_std_key)
            _rank = _entry.rank if _entry is not None else _scheme_dims
        else:
            _rank = _scheme_dims

        var_type = TypeConversions.convert(
            fw_arg.getAttr("type"),
            fw_arg.getAttr("kind") if fw_arg.hasAttr("kind") else None,
            _rank,
        )
        _suite_entry = suite_model.get(fw_std_key) if suite_model else None
        _var_name = (
            _suite_entry.local_name
            if _suite_entry is not None
            else fw_arg.name
        )
        ref_op = ccpp_utils.HostVarRefOp(_var_name, "", var_type)
        ref_op.res.name_hint = _var_name
        framework_ref_ops.append(ref_op)
        data_ops[fw_arg.name] = ref_op
        if _var_name != fw_arg.name:
            data_ops[_var_name] = ref_op

        _horiz_std_names = {
            CCPP_HORIZ_DIM_STD_NAME, CCPP_LOOP_EXTENT_STD_NAME,
            CCPP_LOOP_BEGIN_STD_NAME, CCPP_LOOP_END_STD_NAME,
        }
        _has_horiz_first_dim = False
        _sentry = None
        if suite_model is not None:
            _sentry = suite_model.get(fw_std_key)
            if _sentry is not None and _sentry.alloc_dim_std_names:
                _has_horiz_first_dim = (
                    _sentry.alloc_dim_std_names[0].lower() in _horiz_std_names
                )
        _dims = _rank
        if column_range and _dims >= 1 and _has_horiz_first_dim:
            _col_begin_ssa = next(
                (data_ops[a.name] for a in all_args.values()
                 if a.hasAttr("standard_name")
                 and a.getAttr("standard_name").lower() == CCPP_LOOP_BEGIN_STD_NAME
                 and a.name in data_ops),
                data_ops.get("col_start"),
            )
            _col_end_ssa = next(
                (data_ops[a.name] for a in all_args.values()
                 if a.hasAttr("standard_name")
                 and a.getAttr("standard_name").lower() == CCPP_LOOP_END_STD_NAME
                 and a.name in data_ops),
                data_ops.get("col_end"),
            )
            if _col_begin_ssa is not None and _col_end_ssa is not None:
                lowers = [_col_begin_ssa]
                uppers = [_col_end_ssa]
                # For rank>1: resolve extra dims (e.g. vertical_layer_dimension → pver)
                # via standard_name lookup in all_args. Lower bound is always 1.
                # An extent no scheme here takes as an argument is the array's
                # own (size()): passing the whole array would hand the scheme
                # every column instead of the current ones.
                _extra_std_names = (
                    _sentry.alloc_dim_std_names[1:]
                    if _sentry is not None and _sentry.alloc_dim_std_names
                    else []
                )
                _one_const = None
                for _idx, _extra_std in enumerate(_extra_std_names, start=2):
                    _dim_ssa = next(
                        (data_ops[a.name] for a in all_args.values()
                         if a.hasAttr("standard_name")
                         and a.getAttr("standard_name").lower() == _extra_std.lower()
                         and a.name in data_ops),
                        None,
                    )
                    if _dim_ssa is None:
                        _size_ref = ccpp_utils.CapVarRefOp(
                            None,
                            memref.MemRefType(TypeConversions.getBaseType("integer"), []),
                            target_op=ccpp_utils.CallExprOp("size", [
                                VarRefExprOp(_var_name),
                                arith.ConstantOp.from_int_and_width(_idx, 32),
                            ]),
                        )
                        framework_ref_ops.append(_size_ref)
                        _dim_ssa = _size_ref.res
                    if _one_const is None:
                        _one_const = arith.ConstantOp.from_int_and_width(1, 32)
                        framework_ref_ops.append(_one_const)
                    lowers.append(_one_const.result)
                    uppers.append(_dim_ssa)
                # Rank-preserving section = all-'R' RankReducingSliceOp
                # (see print_ftn.py's CCPPRankReducingSliceOp case).
                section = RankReducingSliceOp(
                    ref_op.res, dim_pattern="R" * len(lowers),
                    range_lowers=lowers, range_uppers=uppers,
                    scalar_indices=[],
                )
                framework_ref_ops.append(section)
                data_ops[fw_arg.name] = section

        return _var_name, _suite_entry

    # Phases that run repeatedly; arrays dimensioned by a SuiteOwned scalar
    # produced here must be allocated per call, not lazily at module scope.
    _REPEATING_PHASES = frozenset({"_run", "_timestep_init", "_timestep_final"})

    @staticmethod
    def _is_run_local_var(entry, suite_model):
        """True when a SuiteOwned array should be a LOCAL allocatable in _run.

        That is, when any allocation dimension is a SuiteOwned scalar produced
        in a repeating phase (e.g. nday in rrtmgp_pre_timestep_init). A
        module-level lazy alloc would lock in the first-call size; matches
        capgen-v1 (local allocatable, allocated and deallocated per call).
        """
        for dim_std_name in entry.alloc_dim_std_names:
            dim_entry = suite_model.get(dim_std_name.lower())
            if (dim_entry is not None
                    and dim_entry.producing_phase in
                        SuiteOwnedMixin._REPEATING_PHASES
                    and dim_entry.rank == 0):
                return True
        return False

    def _maybe_schedule_framework_var_alloc(
        self, fw_arg, fw_std_key, var_name, suite_entry, is_alloc_phase,
        suite_model, all_args, data_ops, framework_ref_ops, suite_use_stubs,
        arg_tables, already_scheduled_allocs, pending_allocs, lazy_alloc_ops,
        pending_only=False, package_scoped=False,
    ) -> None:
        """Decide whether and how fw_arg is allocated in this phase: skip if
        the scheme self-allocates, else allocate now or defer via
        pending_allocs. No-op unless is_alloc_phase.
        Mutates lazy_alloc_ops/pending_allocs/already_scheduled_allocs.

        pending_only -- only use the deferred path (for _register, so that
        resolvable allocations are left to _init).
        """
        if not is_alloc_phase:
            return
        if fw_arg.hasAttr("allocatable"):
            # An `allocatable, intent(out)` dummy is allocated by the scheme
            # itself (e.g. examples/advection/dlc_liq.F90); the suite must
            # not pre-allocate it. Exception: a var with a horizontal
            # dimension is passed as an array section, which can't bind to
            # an allocatable dummy, so the cap must allocate it.
            _dim_names = (fw_arg.getAttr("dim_names")
                          if fw_arg.hasAttr("dim_names") else [])
            # dim_names are raw (not normalized), so check both forms.
            _has_horiz_dim = any(
                d.lower() in (CCPP_HORIZ_DIM_STD_NAME, CCPP_LOOP_EXTENT_STD_NAME)
                for d in _dim_names
            )
            if not _has_horiz_dim:
                return

        _alloc_dim_names = (
            suite_model.alloc_dims(fw_std_key)
            if suite_model is not None
            else (fw_arg.getAttr("dim_names")
                  if fw_arg.hasAttr("dim_names") else [])
        )
        if not _alloc_dim_names:
            # Scalar or DDT: nothing to allocate (and no spurious warning).
            return
        _is_run_local = (
            suite_entry is not None
            and suite_model is not None
            and self._is_run_local_var(suite_entry, suite_model)
        )
        dim_var_refs, _pending_producer = self._resolve_alloc_dim_var_refs(
            _alloc_dim_names, all_args, data_ops, framework_ref_ops,
            suite_use_stubs, arg_tables, frozenset(), package_scoped=package_scoped,
        )

        if _pending_producer is not None:
            pending_allocs.setdefault(_pending_producer, []).append(
                _PendingAlloc(
                    var_name=var_name,
                    std_key=fw_std_key,
                    alloc_dim_names=list(_alloc_dim_names),
                    init_value=(
                        fw_arg.getAttr("default_value")
                        if fw_arg.hasAttr("default_value") else None
                    ),
                    needs_device_residency=(
                        suite_entry.needs_device_residency
                        if suite_entry is not None else False
                    ),
                    producer_scheme=_pending_producer,
                    is_run_local=_is_run_local,
                )
            )
        elif dim_var_refs and not pending_only:
            init_val = (
                fw_arg.getAttr("default_value")
                if fw_arg.hasAttr("default_value")
                else None
            )
            lazy_alloc_ops.append(
                LazyAllocOp(
                    var_name=var_name,
                    dim_var_refs=dim_var_refs,
                    init_value_op=(
                        MetadataLiteralExprOp(init_val) if init_val is not None else None
                    ),
                    needs_device_residency=(
                        suite_entry.needs_device_residency
                        if suite_entry is not None
                        else False
                    ),
                    is_run_local=_is_run_local,
                )
            )
            if already_scheduled_allocs is not None:
                already_scheduled_allocs.add(fw_std_key)
        else:
            # Unresolvable dimensions: warn at generation time.
            _alloc_dim_desc = ", ".join(str(d) for d in _alloc_dim_names)
            warn_once(
                f"cannot resolve allocation dimensions for "
                f"'{var_name}' (std_name='{fw_std_key}', dims=({_alloc_dim_desc}))"
                f" -- no allocate() will be generated; this will likely cause a"
                f" Fortran runtime error.",
            )

    def _sweep_suite_owned_var_allocations(
        self, suite_model, all_args, data_ops, framework_ref_ops, suite_use_stubs,
        arg_tables, already_scheduled_allocs, pending_allocs, lazy_alloc_ops,
        deferred_warnings=None, package_scoped=False,
    ) -> None:
        """Schedule allocations for suite-owned vars not yet allocated by the
        framework_vars loop (e.g. examples/constituents_dim's cwork/awork,
        whose dimension only resolves once _run-phase args are in scope).

        deferred_warnings -- optional list; unresolvable-dim entries are
        appended as (local_name, standard_name, dim_desc) for the caller to
        emit after all phases. When None, warnings are emitted immediately.

        Mutates lazy_alloc_ops/pending_allocs/already_scheduled_allocs.
        """
        already_allocated = {op.var_name.data for op in lazy_alloc_ops}
        # Also exclude vars already deferred, to avoid a duplicate LazyAllocOp.
        already_allocated |= {
            p.var_name for _plist in pending_allocs.values() for p in _plist
        }
        for entry in suite_model.suite_owned_vars():
            if not suite_model.needs_allocation(entry.standard_name):
                continue
            if entry.local_name in already_allocated:
                continue
            if entry.allocatable:
                # Self-allocated by its first-writer scheme (same guard as
                # _maybe_schedule_framework_var_alloc).
                continue
            dim_var_refs, _pending_producer = self._resolve_alloc_dim_var_refs(
                entry.alloc_dim_std_names, all_args, data_ops, framework_ref_ops,
                suite_use_stubs, arg_tables, frozenset(), package_scoped=package_scoped,
            )
            if _pending_producer is not None:
                pending_allocs.setdefault(_pending_producer, []).append(
                    _PendingAlloc(
                        var_name=entry.local_name,
                        std_key=entry.standard_name,
                        alloc_dim_names=list(entry.alloc_dim_std_names),
                        init_value=None,
                        needs_device_residency=entry.needs_device_residency,
                        producer_scheme=_pending_producer,
                    )
                )
            elif dim_var_refs:
                lazy_alloc_ops.append(
                    LazyAllocOp(
                        var_name=entry.local_name,
                        dim_var_refs=dim_var_refs,
                        needs_device_residency=entry.needs_device_residency,
                    )
                )
                if already_scheduled_allocs is not None:
                    already_scheduled_allocs.add(entry.standard_name)
            else:
                # Unresolvable here; a later phase may still allocate it, so
                # defer the warning when the caller supplies a list.
                _dim_desc = ", ".join(str(d) for d in entry.alloc_dim_std_names)
                if deferred_warnings is not None:
                    deferred_warnings.append(
                        (entry.local_name, entry.standard_name, _dim_desc)
                    )
                else:
                    warn_once(
                        f"cannot resolve allocation dimensions for"
                        f" '{entry.local_name}'"
                        f" (std_name='{entry.standard_name}', dims=({_dim_desc}))"
                        f" during suite-owned var sweep"
                        f" -- no allocate() will be generated.",
                    )

    def _build_framework_refs(
        self,
        framework_vars,
        all_args,
        data_ops,
        suite_use_stubs,
        suite_model,
        tgt_subroutine_postfix,
        column_range,
        arg_tables,
        already_scheduled_allocs=None,
        deferred_warnings=None,
        package_scoped=False,
    ):
        """Build HostVarRefOps and LazyAllocOps for framework-managed vars.

        already_scheduled_allocs -- optional set, shared across a suite's
        phase calls, of std_keys already given a successful LazyAllocOp by
        an earlier _init/_register call (by either the framework_vars loop
        or the suite-owned sweep).

        deferred_warnings -- forwarded to _sweep_suite_owned_var_allocations.

        Mutates data_ops, suite_use_stubs and already_scheduled_allocs.
        Returns (framework_ref_ops, lazy_alloc_ops, pending_allocs), where
        pending_allocs maps producer_scheme -> list[_PendingAlloc] for vars
        dimensioned by a same-phase scheme output; _build_call_ops splices
        them in after the producer's call.
        """
        framework_ref_ops = []
        lazy_alloc_ops = []
        pending_allocs: dict = {}
        # In _run-like phases, expose SuiteOwned scalars from earlier phases
        # (module variables absent from all_args, e.g. nlayp from _init) as
        # dimension bounds. Skipped in _init/_register, where future-phase
        # scalars would resolve as 0-valued; scalars in the current all_args
        # are skipped so allocation waits for their producer.
        if suite_model is not None and tgt_subroutine_postfix not in ("_init", "_register"):
            _current_std_names = {
                a.getAttr("standard_name").lower()
                for a in all_args.values()
                if a.hasAttr("standard_name")
            }
            for _so_entry in suite_model.suite_owned_vars():
                if _so_entry.rank != 0:
                    continue  # only scalar dimension bounds needed here
                _so_key = _so_entry.standard_name.lower()
                if _so_key in _current_std_names:
                    continue  # in the current phase's all_args; don't bypass
                if _so_entry.local_name in data_ops:
                    continue  # already in scope (e.g. a block argument)
                _so_type = TypeConversions.convert(_so_entry.fortran_type,
                                                   _so_entry.kind, 0)
                _so_ref = ccpp_utils.HostVarRefOp(_so_entry.local_name, "", _so_type)
                _so_ref.res.name_hint = _so_entry.local_name
                framework_ref_ops.append(_so_ref)
                data_ops[_so_entry.local_name] = _so_ref
                data_ops[("std_name", _so_key)] = _so_ref
        if framework_vars:
            for fw_arg in framework_vars.values():
                _fw_std_key = _std_key(fw_arg)
                _var_name, _suite_entry = self._build_framework_var_ref(
                    fw_arg, _fw_std_key, all_args, data_ops, framework_ref_ops,
                    suite_model, column_range,
                )

                _already_scheduled = (
                    already_scheduled_allocs is not None
                    and _fw_std_key in already_scheduled_allocs
                )
                _is_alloc_phase = (
                    tgt_subroutine_postfix in ("_init", "_register")
                    or (column_range and not _already_scheduled)
                )
                # _register only allocates pending-producer vars; the rest go in _init.
                _pending_only = tgt_subroutine_postfix == "_register"
                self._maybe_schedule_framework_var_alloc(
                    fw_arg, _fw_std_key, _var_name, _suite_entry, _is_alloc_phase,
                    suite_model, all_args, data_ops, framework_ref_ops,
                    suite_use_stubs, arg_tables, already_scheduled_allocs,
                    pending_allocs, lazy_alloc_ops, pending_only=_pending_only,
                    package_scoped=package_scoped,
                )

                # Tuple key by standard_name (set last, so it mirrors any slice).
                # generateSchemeSubroutineCallOps prefers it because two schemes
                # may use the same local name for different variables.
                data_ops[("std_name", _fw_std_key)] = data_ops[fw_arg.name]

        if suite_model is not None and tgt_subroutine_postfix == "_init":
            self._sweep_suite_owned_var_allocations(
                suite_model, all_args, data_ops, framework_ref_ops, suite_use_stubs,
                arg_tables, already_scheduled_allocs, pending_allocs, lazy_alloc_ops,
                deferred_warnings=deferred_warnings, package_scoped=package_scoped,
            )

        _alias_canonical_data_ops(arg_tables, all_args, data_ops)

        return framework_ref_ops, lazy_alloc_ops, pending_allocs
