"""Suite and group phase subroutines: argument tables, signatures, state checks and assembly."""

from __future__ import annotations


from xdsl.dialects import arith, builtin, func, llvm, memref, scf
from xdsl.dialects.builtin import (
    ArrayAttr,
    StringAttr,
    i8,
)
from xdsl.ir import Region

from xdsl_ccpp.dialects import ccpp_utils
from xdsl_ccpp.dialects.ccpp import ArgOwnershipKind
from xdsl_ccpp.transforms.util.cap_shared import (
    FN_PHASE_ATTR,
    LIFECYCLE_POSTFIX_ALIASES,
    SUITE_FN_INFIX,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    CCPPArgument,
    XMLSuite,
)
from xdsl_ccpp.util.ccpp_conventions import (
    CCPP_LOOP_EXTENT_STD_NAME,
    normalize_units,
)
from xdsl_ccpp.transforms.suitecap.block_args import (
    _alloc_output_error_args,
    _apply_kind_and_unit_casts,
    _build_block_and_name_hints,
    _has_dims,
    _std_key,
    _tag_data_ops_by_std_name,
)
from xdsl_ccpp.transforms.suitecap.host_scalars import (
    _build_suite_state_lazy_alloc,
    _instance_arg_local_name,
    _number_of_instances_local_name,
    _synthesize_dynamic_loop_count_args,
    _synthesize_instance_number_arg,
    _synthesize_number_of_instances_arg,
    _synthesize_number_of_threads_arg,
    _synthesize_thread_number_arg,
)
from xdsl_ccpp.transforms.suitecap.records import (
    _ArgClassification,
    _ArgTableResult,
    _BlockSignature,
    _LifecycleFnsResult,
)
from xdsl_ccpp.transforms.suitecap.resolved_vars import (
    _PHASE_NAMES,
    _apply_ddt_chain,
    _resolved_var_record,
)


# Phase tags (cap_shared.FN_PHASE_ATTR) for the suite-level and per-group
# functions, keyed by the scheme entry-point postfix each one calls.
_SUITE_PHASE_TAGS = {"_register": "suite_register", "_init": "suite_initialize",
                     "_finalize": "suite_finalize"}
_GROUP_PHASE_TAGS = {"_init": "group_init", "_run": "run",
                     "_timestep_initialize": "timestep_init",
                     "_timestep_finalize": "timestep_final", "_finalize": "group_final"}

class PhaseFunctionsMixin:
    """Suite and group phase subroutines: argument tables, signatures, state checks and assembly."""

    def generateStringConstantGlobal(self, string: str) -> llvm.GlobalOp:
        """Create an internal LLVM global holding a 16-byte string constant."""
        return llvm.GlobalOp(
            llvm.LLVMArrayType.from_size_and_type(16, i8),
            "const_" + string,
            "internal",
            constant=True,
            value=StringAttr(string),
        )

    def generateStateCheckOps(
        self, check_string: str, data_ops, fn_name: str | None = None,
        instance_local_name: str | None = None,
    ):
        """Emit ops that compare ccpp_suite_state against check_string.

        On mismatch errflg is set to 1 and, if fn_name is given, errmsg is
        written.

        instance_local_name -- for a multi-instance suite, the local name of
        the instance_number arg; print_ftn.py then prints
        ccpp_suite_state(<instance_local_name>).
        """
        arr_type = llvm.LLVMArrayType.from_size_and_type(16, i8)

        # Load the expected state constant and the current runtime state
        addr_const = llvm.AddressOfOp("const_" + check_string, llvm.LLVMPointerType())
        loaded_const = llvm.LoadOp(addr_const, arr_type)
        addr_state = llvm.AddressOfOp("ccpp_suite_state", llvm.LLVMPointerType())
        if instance_local_name is not None:
            addr_state.attributes["ccpp_instance_ref"] = StringAttr(instance_local_name)
        loaded_state = llvm.LoadOp(addr_state, arr_type)

        strcmp_op = ccpp_utils.StrCmpOp(loaded_const, loaded_state, len(check_string))

        # strcmp returns 1 if equal; negate to get mismatch flag for scf.if
        one_i1 = arith.ConstantOp.from_int_and_width(1, 1)
        mismatch = arith.XOrIOp(strcmp_op.res, one_i1.result)

        # Set errflg = 1 if the state does not match; optionally write errmsg
        one = arith.ConstantOp.from_int_and_width(1, 32)
        store = memref.StoreOp.get(one, data_ops["errflg"], [])
        if fn_name is not None:
            trim_state = ccpp_utils.TrimOp(loaded_state)
            write_err = ccpp_utils.WriteErrMsgOp(
                data_ops["errmsg"],
                trim_state.res,
                "Invalid initial CCPP state, '",
                f"' in {fn_name}",
            )
            true_ops = [trim_state, write_err, one, store, scf.YieldOp()]
        else:
            true_ops = [one, store, scf.YieldOp()]
        if_op = scf.IfOp(mismatch.result, [], true_ops)

        return [
            addr_const,
            loaded_const,
            addr_state,
            loaded_state,
            strcmp_op,
            one_i1,
            mismatch,
            if_op,
        ]

    def generateStateAssignment(
        self, state_string: str, instance_local_name: str | None = None
    ):
        """Emit ops that write state_string into the ccpp_suite_state global.

        instance_local_name -- see generateStateCheckOps.
        """
        arr_type = llvm.LLVMArrayType.from_size_and_type(16, i8)
        # Load from the string constant global and store into ccpp_suite_state
        addr_src = llvm.AddressOfOp("const_" + state_string, llvm.LLVMPointerType())
        loaded = llvm.LoadOp(addr_src, arr_type)
        addr_dst = llvm.AddressOfOp("ccpp_suite_state", llvm.LLVMPointerType())
        if instance_local_name is not None:
            addr_dst.attributes["ccpp_instance_ref"] = StringAttr(instance_local_name)
        store = llvm.StoreOp(loaded, addr_dst)
        return [addr_src, loaded, addr_dst, store]

    def _build_block_signature(
        self, input_arg_list, output_arg_list, divergent_std_keys: frozenset = frozenset(),
    ) -> "_BlockSignature":
        """Build the Block, populate data_ops from block args, and apply kind/unit casts.

        divergent_std_keys are standard_names whose schemes disagree on kind
        or units (see _build_arg_tables). These skip the suite-boundary
        conversion; each scheme call marshals independently instead (see
        generateSchemeSubroutineCallOps).
        """
        new_block, input_arg_types, data_ops, final_values = _build_block_and_name_hints(
            input_arg_list
        )
        kind_cast_ops, unit_convert_ops, writeback_ops = _apply_kind_and_unit_casts(
            input_arg_list, new_block, data_ops, final_values, divergent_std_keys,
        )
        alloc_ops = _alloc_output_error_args(output_arg_list, data_ops)
        _tag_data_ops_by_std_name(input_arg_list, final_values, data_ops)

        return _BlockSignature(
            new_block=new_block,
            input_arg_types=input_arg_types,
            data_ops=data_ops,
            alloc_ops=alloc_ops,
            kind_cast_ops=kind_cast_ops,
            unit_convert_ops=unit_convert_ops,
            writeback_ops=writeback_ops,
        )

    def _classify_args(self, all_args, physics_mode) -> "_ArgClassification":
        """Partition all_args into framework-managed, input, and output lists.

        When physics_mode is True and the loop-extent arg is present, replaces
        that arg in input_arg_list with synthetic col_start/col_end scalars.
        Returns the final lists and the ncol_meta arg (or None).
        """
        # Missing ownership_kind means generate-arg-ownership didn't run;
        # fail loudly rather than emit a plausible-but-wrong signature.
        missing = [a.name for a in all_args.values() if not a.hasAttr("ownership_kind")]
        if missing:
            raise ValueError(
                f"Arg(s) {sorted(missing)} have no ownership_kind set. "
                f"generate-arg-ownership (ArgOwnershipPass) must run before "
                f"generate-suite-cap -- check the pass pipeline."
            )
        # Keyed by standard_name, not local name: two schemes may use the
        # same local name for different SuiteOwned variables.
        framework_vars = {
            _std_key(a): a
            for a in all_args.values()
            if a.getAttr("ownership_kind") == ArgOwnershipKind.SuiteOwned
        }
        input_arg_list = [
            a
            for a in all_args.values()
            if (a.getAttr("intent") in ("in", "inout") or _has_dims(a))
            and _std_key(a) not in framework_vars
        ]
        output_arg_list = [
            a
            for a in all_args.values()
            if a.getAttr("intent") == "out" and not _has_dims(a)
            and _std_key(a) not in framework_vars
        ]

        ncol_meta = None
        ncol_meta_entry = all_args.get(CCPP_LOOP_EXTENT_STD_NAME)
        if physics_mode and ncol_meta_entry is not None:
            ncol_meta = ncol_meta_entry
            ncol_idx = next(
                i for i, a in enumerate(input_arg_list)
                if a is ncol_meta
            )

            def _make_col_arg(name):
                a = CCPPArgument(name)
                a.setAttr("type", ncol_meta.getAttr("type"))
                a.setAttr("intent", "in")
                if ncol_meta.hasAttr("kind"):
                    a.setAttr("kind", ncol_meta.getAttr("kind"))
                a.setAttr("dimensions", 0)
                return a

            input_arg_list = (
                input_arg_list[:ncol_idx]
                + [_make_col_arg("col_start"), _make_col_arg("col_end")]
                + input_arg_list[ncol_idx + 1:]
            )

        return _ArgClassification(
            framework_vars=framework_vars,
            input_arg_list=input_arg_list,
            output_arg_list=output_arg_list,
            ncol_meta=ncol_meta,
        )

    def _build_arg_tables(
        self, suite_description, tgt_subroutine_postfix, physics_mode: bool = False,
        emit_scheme_calls: bool = True,
    ) -> "_ArgTableResult":
        """Build argument tables, overrides, and canonical arg map for all schemes.

        emit_scheme_calls -- see generateSubroutineCall. False skips only the
        scheme-table scan (and loop-count synthesis); host scalars such as
        instance_number are still synthesized, since the phase signature
        needs them even with zero scheme calls.
        """
        scheme_entries = self.getSchemeNames(suite_description)
        arg_tables = {}
        scheme_overrides: dict[str, dict[str, str]] = {}
        actual_postfixes: dict[str, str] = {}
        all_args = {}
        suite_use_stubs: list = []
        if tgt_subroutine_postfix is not None:
            if emit_scheme_calls:
                _postfix_candidates = [tgt_subroutine_postfix]
                if tgt_subroutine_postfix in LIFECYCLE_POSTFIX_ALIASES:
                    _postfix_candidates.append(LIFECYCLE_POSTFIX_ALIASES[tgt_subroutine_postfix])
                for scheme_name, overrides in scheme_entries:
                    for _candidate in _postfix_candidates:
                        table = self.getArgumentTable(
                            scheme_name, scheme_name + _candidate
                        )
                        if table is not None and scheme_name not in arg_tables:
                            arg_tables[scheme_name] = table
                            scheme_overrides[scheme_name] = overrides
                            actual_postfixes[scheme_name] = _candidate
                            break

                for scheme_name in arg_tables:
                    for fn_arg in arg_tables[scheme_name].getFunctionArguments():
                        std_key = _std_key(fn_arg)
                        if std_key in all_args:
                            assert fn_arg.getAttr("type") == all_args[std_key].getAttr("type")
                            # Any two different intents combine to 'inout'.
                            cur = all_args[std_key].getAttr("intent")
                            new = fn_arg.getAttr("intent")
                            if new != cur:
                                all_args[std_key].setAttr("intent", "inout")
                        else:
                            all_args[std_key] = fn_arg

                # Matches _emit_subcycle's "_run"-only gate; other phases
                # would get an unused dummy argument.
                if physics_mode and tgt_subroutine_postfix == "_run":
                    _synthesize_dynamic_loop_count_args(
                        self.meta_data, self.getCallSequence(suite_description),
                        arg_tables, all_args,
                    )
            _synthesize_instance_number_arg(self.meta_data, all_args)
            _synthesize_number_of_instances_arg(self.meta_data, all_args)
            _synthesize_thread_number_arg(self.meta_data, all_args)
            _synthesize_number_of_threads_arg(self.meta_data, all_args)

        # Schemes sharing a standard_name may disagree with each other on
        # kind, units or top_at_one, but all_args keeps only the first
        # declaration. Flag such names for per-call marshaling instead of a
        # single suite-boundary conversion.
        signatures_seen: dict[str, set] = {}
        for scheme_name in arg_tables:
            for fn_arg in arg_tables[scheme_name].getFunctionArguments():
                if fn_arg.getAttr("type") != "real":
                    continue
                std_key = _std_key(fn_arg)
                kind = fn_arg.getAttr("kind") if fn_arg.hasAttr("kind") else None
                units = normalize_units(
                    fn_arg.getAttr("units") if fn_arg.hasAttr("units") else None
                )
                top_at_one = fn_arg.hasAttr("top_at_one")
                signatures_seen.setdefault(std_key, set()).add((kind, units, top_at_one))
        divergent_std_keys = frozenset(
            std_key for std_key, sigs in signatures_seen.items() if len(sigs) > 1
        )

        return _ArgTableResult(
            scheme_entries=scheme_entries,
            arg_tables=arg_tables,
            scheme_overrides=scheme_overrides,
            actual_postfixes=actual_postfixes,
            all_args=all_args,
            suite_use_stubs=suite_use_stubs,
            divergent_std_keys=divergent_std_keys,
        )

    def _assemble_func(
        self,
        suite_description,
        generated_subroutine_posfix,
        check_string,
        state_string,
        input_arg_list,
        input_arg_types,
        new_block,
        data_ops,
        alloc_ops,
        kind_cast_ops,
        unit_convert_ops,
        writeback_ops,
        call_ops,
        initialisation_ops,
        ncol_compute_ops,
        framework_ref_ops,
        lazy_alloc_ops,
        suite_lifecycle_call_ops=(),
        instance_local_name: str | None = None,
        constituent_extract_ops=(),
        constituent_writeback_ops=(),
    ):
        """Assemble all op lists into the body block and return the FuncOp.

        suite_lifecycle_call_ops -- the suite-level <init>/<final> hook call
        (see _build_suite_lifecycle_call_ops); placed after call_ops and
        before the state transition, matching capgen-v1.

        instance_local_name -- see generateStateCheckOps.
        """
        # Return the ORIGINAL block args, not data_ops (which may hold a
        # kind/unit conversion temp): print_ftn.py uses ReturnOp operands to
        # decide which args to declare intent(inout).
        inout_return_vals = [
            new_block.args[idx]
            for idx, a in enumerate(input_arg_list)
            if a.getAttr("intent") == "inout" and not _has_dims(a)
        ]
        alloc_return_vals = list(alloc_ops.values())

        errmsg_fn_name = suite_description.attributes["name"] + generated_subroutine_posfix
        check_ops = (
            self.generateStateCheckOps(
                check_string, data_ops, errmsg_fn_name, instance_local_name
            )
            if check_string is not None
            else []
        )
        state_ops = (
            self.generateStateAssignment(state_string, instance_local_name)
            if state_string is not None
            else []
        )

        body_ops = (
            alloc_return_vals
            + initialisation_ops
            + ncol_compute_ops
            + framework_ref_ops
            + lazy_alloc_ops
            + kind_cast_ops
            + unit_convert_ops
            + check_ops
            + list(constituent_extract_ops)
            + call_ops
            + list(constituent_writeback_ops)
            + writeback_ops
            + list(suite_lifecycle_call_ops)
            + state_ops
            + [func.ReturnOp(*inout_return_vals, *alloc_return_vals)]
        )

        new_block.add_ops(body_ops)
        body = Region()
        body.add_block(new_block)

        return_types = [v.type for v in inout_return_vals] + [
            o.results[0].type for o in alloc_return_vals
        ]
        new_fn_type = builtin.FunctionType.from_lists(input_arg_types, return_types)
        return func.FuncOp(
            suite_description.attributes["name"] + SUITE_FN_INFIX + generated_subroutine_posfix,
            new_fn_type,
            body,
            visibility="public",
        )

    def _record_resolved_vars_for_phase(
        self, tgt_subroutine_postfix, physics_mode,
        framework_vars, input_arg_list, output_arg_list, ncol_meta,
    ) -> None:
        """--emit-resolved-vars: append this phase's resolved-variable
        records to self.resolved_vars.

        Bucketed by tgt_subroutine_postfix; only physics_mode "_run" maps to
        "run", so group-scoped non-run phases keep their own phase name.
        """
        if physics_mode and tgt_subroutine_postfix == "_run":
            phase_name = "run"
        else:
            phase_name = _PHASE_NAMES.get((tgt_subroutine_postfix, False))
        if phase_name is None:
            return
        records = self.resolved_vars.setdefault(phase_name, [])
        for arg in (*framework_vars.values(), *input_arg_list, *output_arg_list):
            record = _resolved_var_record(arg)
            if record is not None:
                _apply_ddt_chain(record, arg, self.ddt_resolution_maps)
                records.append(record)
        # ncol_meta is the original loop-extent arg that _classify_args
        # replaced with nameless col_start/col_end; record it explicitly.
        # It was never host-matched, so fall back to host_var_index by its
        # normalized standard name (capgen-v1 uses VarLoopSubst). Scoped to
        # ncol_meta: other args may be host-unmatched by design.
        if ncol_meta is not None:
            ncol_record = _resolved_var_record(ncol_meta)
            if ncol_record is not None:
                if ncol_record["model_var_name"] is None:
                    host_match = self.host_var_index.get(
                        ncol_record["standard_name"].lower()
                    )
                    if host_match is not None:
                        ncol_record["model_var_name"] = host_match[0]
                        ncol_record["model_module_name"] = host_match[1]
                        ncol_record["is_host_table_var"] = host_match[2]
                        ncol_record["is_protected"] = ncol_record["is_protected"] or host_match[3]
                records.append(ncol_record)

    def generateSubroutineCall(
        self,
        suite_description,
        tgt_subroutine_postfix,
        generated_subroutine_posfix=None,
        state_string: str | None = None,
        check_string: str | None = None,
        physics_mode: bool = False,
        group_name: str = "",
        suite_model=None,
        already_scheduled_allocs=None,
        deferred_warnings=None,
        emit_scheme_calls: bool = True,
    ):
        """Build a single cap subroutine as a func.FuncOp.

        tgt_subroutine_postfix  -- suffix appended to each scheme name to form
                                   the called function (e.g. "_init"); also
                                   the phase identity, even when
                                   emit_scheme_calls=False.
        generated_subroutine_posfix -- suffix used for the generated function
                                   name (e.g. "_initialize"). Defaults to
                                   tgt_subroutine_postfix when not supplied.
        state_string            -- if set, write this value into ccpp_suite_state
                                   at the end of the subroutine.
        check_string            -- if set, verify ccpp_suite_state equals this
                                   value at the start of the subroutine.
        already_scheduled_allocs -- set shared by every phase call for one
                                   suite, so a framework var gets at most
                                   one LazyAllocOp (see _build_framework_refs).
        emit_scheme_calls       -- False for the flat suite _init/_finalize,
                                   which (as in capgen-v1) only do framework
                                   setup; scheme _init/_finalize calls happen
                                   in the group-scoped phases instead.
        """
        if generated_subroutine_posfix is None:
            assert tgt_subroutine_postfix is not None
            generated_subroutine_posfix = tgt_subroutine_postfix

        _tables = self._build_arg_tables(
            suite_description, tgt_subroutine_postfix, physics_mode,
            emit_scheme_calls=emit_scheme_calls,
        )
        scheme_entries = _tables.scheme_entries
        arg_tables = _tables.arg_tables
        scheme_overrides = _tables.scheme_overrides
        actual_postfixes = _tables.actual_postfixes
        all_args = _tables.all_args
        suite_use_stubs = _tables.suite_use_stubs
        divergent_std_keys = _tables.divergent_std_keys

        _cls = self._classify_args(all_args, physics_mode)
        framework_vars = _cls.framework_vars
        input_arg_list = _cls.input_arg_list
        output_arg_list = _cls.output_arg_list
        ncol_meta = _cls.ncol_meta

        self._record_resolved_vars_for_phase(
            tgt_subroutine_postfix, physics_mode,
            framework_vars, input_arg_list, output_arg_list, ncol_meta,
        )

        _sig = self._build_block_signature(
            input_arg_list, output_arg_list, divergent_std_keys=divergent_std_keys,
        )
        new_block = _sig.new_block
        input_arg_types = _sig.input_arg_types
        data_ops = _sig.data_ops
        alloc_ops = _sig.alloc_ops
        kind_cast_ops = _sig.kind_cast_ops
        unit_convert_ops = _sig.unit_convert_ops
        writeback_ops = _sig.writeback_ops

        ncol_compute_ops = self._build_ncol_compute_ops(physics_mode, data_ops, ncol_meta)

        initialisation_ops = self.generateVariableInitialisations(data_ops)

        framework_ref_ops, lazy_alloc_ops, pending_allocs = self._build_framework_refs(
            framework_vars=framework_vars,
            all_args=all_args,
            data_ops=data_ops,
            suite_use_stubs=suite_use_stubs,
            suite_model=suite_model,
            tgt_subroutine_postfix=tgt_subroutine_postfix,
            physics_mode=physics_mode,
            arg_tables=arg_tables,
            already_scheduled_allocs=already_scheduled_allocs,
            deferred_warnings=deferred_warnings,
        )

        # _run only: point suite-owned constituent vars at slices of the host
        # constituent array before the scheme calls and nullify them after.
        # The pointers alias live memory, so no re-sync is needed in between
        # (matches capgen-v1's array-section aliasing).
        constituent_extract_ops = []
        constituent_writeback_ops = []
        if physics_mode and tgt_subroutine_postfix == "_run" and suite_model is not None:
            constituent_extract_ops, constituent_writeback_ops = \
                self._build_constituent_sync_ops(suite_model, data_ops, input_arg_list)

        _bco_kwargs = dict(
            suite_description=suite_description,
            tgt_subroutine_postfix=tgt_subroutine_postfix,
            physics_mode=physics_mode,
            all_args=all_args,
            data_ops=data_ops,
            framework_ref_ops=framework_ref_ops,
            suite_use_stubs=suite_use_stubs,
            actual_postfixes=actual_postfixes,
            arg_tables=arg_tables,
            scheme_overrides=scheme_overrides,
            divergent_std_keys=divergent_std_keys,
            pending_allocs=pending_allocs,
            already_scheduled_allocs=already_scheduled_allocs,
        )
        call_ops, fn_sigs = self._build_call_ops(**_bco_kwargs)

        # Multi-instance: ccpp_suite_state(instance) must be allocated (sized
        # by number_of_instances) before phases that check/set state use it.
        # instance_number may come from a scheme's own arg table, so drop it
        # unless number_of_instances is also present; otherwise
        # ccpp_suite_state is a scalar (see _build_state_globals).
        instance_local_name = _instance_arg_local_name(input_arg_list)
        ninstances_local_name = _number_of_instances_local_name(input_arg_list)
        if ninstances_local_name is None:
            instance_local_name = None
        if (
            instance_local_name is not None
            and ninstances_local_name is not None
            and (check_string is not None or state_string is not None)
        ):
            lazy_alloc_ops.append(
                _build_suite_state_lazy_alloc(data_ops[ninstances_local_name])
            )

        # Suite-level <init>/<final> hook (v2.0 SDF): entry points use
        # "_init"/"_final" (the tag names), not "_finalize". Flat phases only
        # (not physics_mode), so the hook isn't called once per group.
        suite_lifecycle_call_ops = []
        if tgt_subroutine_postfix == "_init" and not physics_mode:
            suite_lifecycle_call_ops = self._build_suite_lifecycle_call_ops(
                suite_description.init_scheme, "_init", data_ops, fn_sigs, suite_use_stubs,
            )
        elif tgt_subroutine_postfix == "_finalize" and not physics_mode:
            suite_lifecycle_call_ops = self._build_suite_lifecycle_call_ops(
                suite_description.final_scheme, "_final", data_ops, fn_sigs, suite_use_stubs,
            )

        new_func = self._assemble_func(
            suite_description=suite_description,
            generated_subroutine_posfix=generated_subroutine_posfix,
            check_string=check_string,
            state_string=state_string,
            input_arg_list=input_arg_list,
            input_arg_types=input_arg_types,
            new_block=new_block,
            data_ops=data_ops,
            alloc_ops=alloc_ops,
            kind_cast_ops=kind_cast_ops,
            unit_convert_ops=unit_convert_ops,
            writeback_ops=writeback_ops,
            call_ops=call_ops,
            initialisation_ops=initialisation_ops,
            ncol_compute_ops=ncol_compute_ops,
            framework_ref_ops=framework_ref_ops,
            lazy_alloc_ops=lazy_alloc_ops,
            suite_lifecycle_call_ops=suite_lifecycle_call_ops,
            instance_local_name=instance_local_name,
            constituent_extract_ops=constituent_extract_ops,
            constituent_writeback_ops=constituent_writeback_ops,
        )
        return new_func, list(fn_sigs.values()), suite_use_stubs

    def clone_func_defs(self, func_defs):
        """Create private external declarations for a list of scheme FuncOps.

        Keeps the generated IR self-contained and verifiable before linking.
        """
        return [
            func.FuncOp.external(
                fd.sym_name.data, fd.function_type.inputs, fd.function_type.outputs
            )
            for fd in func_defs
        ]

    def _generate_lifecycle_fns(self, suite_description, suite_model) -> "_LifecycleFnsResult":
        """Generate FuncOps for the three fixed, flat lifecycle specs, plus
        one group-scoped _run, one group-scoped _timestep_initialize, and
        one group-scoped _timestep_finalize per physics group.

        Matches capgen-v1: the flat _init/_finalize own the
        "uninitialized" <-> "initialized" transitions, the group-scoped
        timestep phases own "initialized" <-> "in_time_step", and the
        group-scoped _run only checks "in_time_step".
        """
        # emit_scheme_calls=False for _init/_finalize: scheme _init/_finalize
        # calls are made per group (group_phase_specs), as in capgen-v1.
        subroutine_specs = [
            ("_register",            "_register",         None,            None,            True),
            ("_init",                "_initialize",       "initialized",   "uninitialized", False),
            ("_finalize",            "_finalize",         "uninitialized", "initialized",   False),
        ]

        generated_fns: list = []
        fn_sigs_by_name: dict = {}
        suite_host_use_stubs: list = []
        check_strings_used: set = set()
        state_strings_used: set = set()
        # Shared across all phases of this suite (not across suites) so each
        # framework var gets at most one LazyAllocOp.
        scheduled_allocs: set = set()
        # Deferred sweep warnings; emitted at the end only for vars no phase
        # managed to allocate.
        sweep_deferred_warnings: list = []

        for tgt_postfix, gen_postfix, state_string, check_string, emit_scheme_calls in subroutine_specs:
            fn, sigs, stubs = self.generateSubroutineCall(
                suite_description, tgt_postfix, gen_postfix,
                state_string=state_string, check_string=check_string,
                physics_mode=(tgt_postfix == "_run"), suite_model=suite_model,
                already_scheduled_allocs=scheduled_allocs,
                deferred_warnings=sweep_deferred_warnings,
                emit_scheme_calls=emit_scheme_calls,
            )
            fn.attributes[FN_PHASE_ATTR] = StringAttr(_SUITE_PHASE_TAGS[tgt_postfix])
            generated_fns.append(fn)
            suite_host_use_stubs.extend(stubs)
            for sig in sigs:
                fn_sigs_by_name[sig.sym_name.data] = sig
            if check_string is not None:
                check_strings_used.add(check_string)
            if state_string is not None:
                state_strings_used.add(state_string)

        # Per-group phases: (tgt_postfix, generated-name prefix, state_string,
        # check_string). Each runs once per group, so no phase both checks and
        # sets state (a check+set would fail for the second group); the
        # timestep phases only set state, matching capgen-v1's lack of
        # group-level state checks. "_init"/"_finalize" carry the scheme
        # _init/_finalize calls the flat specs above skip.
        group_phase_specs = [
            ("_init",                "init_",           None,            "initialized"),
            ("_run",                 "",                None,            "in_time_step"),
            ("_timestep_initialize", "timestep_init_",  "in_time_step",  None),
            ("_timestep_finalize",   "timestep_final_",  "initialized",  None),
            ("_finalize",            "final_",          None,            "initialized"),
        ]

        for group in suite_description:
            group_name = group.attributes["name"]
            group_suite = XMLSuite(
                suite_description.attributes["name"],
                suite_description.attributes["version"],
            )
            group_suite.addChild(group)
            for tgt_postfix, gen_prefix, state_string, check_string in group_phase_specs:
                fn, sigs, stubs = self.generateSubroutineCall(
                    group_suite, tgt_postfix, f"_{gen_prefix}{group_name}",
                    state_string=state_string, check_string=check_string,
                    physics_mode=True, group_name=group_name, suite_model=suite_model,
                    already_scheduled_allocs=scheduled_allocs,
                    deferred_warnings=sweep_deferred_warnings,
                )
                fn.attributes[FN_PHASE_ATTR] = StringAttr(_GROUP_PHASE_TAGS[tgt_postfix])
                generated_fns.append(fn)
                suite_host_use_stubs.extend(stubs)
                for sig in sigs:
                    fn_sigs_by_name[sig.sym_name.data] = sig
                if check_string is not None:
                    check_strings_used.add(check_string)
                if state_string is not None:
                    state_strings_used.add(state_string)

        # Warn only for vars no phase managed to allocate.
        if sweep_deferred_warnings:
            import warnings
            for _local_name, _std_name, _dim_desc in sweep_deferred_warnings:
                if _std_name not in scheduled_allocs:
                    warnings.warn(
                        f"xdsl_ccpp: cannot resolve allocation dimensions for"
                        f" '{_local_name}'"
                        f" (std_name='{_std_name}', dims=({_dim_desc}))"
                        f" during suite-owned var sweep"
                        f" -- no allocate() will be generated.",
                        stacklevel=2,
                    )

        return _LifecycleFnsResult(
            generated_fns=generated_fns,
            fn_sigs_by_name=fn_sigs_by_name,
            suite_host_use_stubs=suite_host_use_stubs,
            check_strings_used=check_strings_used,
            state_strings_used=state_strings_used,
        )

    def _build_fn_signatures(
        self, fn_sigs_by_name: dict, scheme_entries: list, extra_scheme_names: "list | None" = None,
    ) -> list:
        """Clone collected scheme function signatures, annotating each with its module name.

        extra_scheme_names -- schemes outside any group's call sequence (e.g.
        a suite-level <init>/<final> hook) that still need a module mapping.
        """
        sub_to_module: dict[str, str] = {}
        sub_to_meta: dict[str, object] = {}
        all_scheme_names = [s for s, _ in scheme_entries] + list(extra_scheme_names or [])
        for scheme_name in all_scheme_names:
            # Prefer the frontend's source_module (shared-module or override
            # case); default to scheme_name.
            meta = self.meta_data.get(scheme_name)
            actual_module = (
                meta.getAttr("source_module")
                if meta is not None and meta.hasAttr("source_module")
                else scheme_name
            )
            for postfix in ("_run", "_init", "_finalize", "_final", "_register",
                            "_timestep_initialize", "_timestep_finalize",
                            "_timestep_init", "_timestep_final"):
                sub_to_module[scheme_name + postfix] = actual_module
                sub_to_meta[scheme_name + postfix] = meta

        fn_sigs = []
        for fd in fn_sigs_by_name.values():
            cloned = func.FuncOp.external(
                fd.sym_name.data, fd.function_type.inputs, fd.function_type.outputs
            )
            module_name = sub_to_module.get(fd.sym_name.data)
            if module_name:
                cloned.attributes["module"] = StringAttr(module_name)
                # Look up by scheme name: meta_data is keyed by table name,
                # not module name.
                meta = sub_to_meta.get(fd.sym_name.data)
                if meta is not None and meta.hasAttr("language"):
                    cloned.attributes["language"] = StringAttr(meta.getAttr("language"))
                    # Stamp arg names and intents so the printer can emit a
                    # BIND(C) interface block without re-reading the meta files.
                    arg_table = meta.arg_tables.get(fd.sym_name.data)
                    if arg_table is not None:
                        args = list(arg_table.getFunctionArguments())
                        cloned.attributes["arg_names"] = ArrayAttr(
                            [StringAttr(a.name) for a in args]
                        )
                        cloned.attributes["arg_intents"] = ArrayAttr(
                            [StringAttr(a.getAttr("intent") if a.hasAttr("intent") else "in")
                             for a in args]
                        )
            fn_sigs.append(cloned)
        return fn_sigs
