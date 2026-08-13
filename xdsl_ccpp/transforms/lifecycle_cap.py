"""Lifecycle-fn generation.

Extracted from ccpp_cap.py's CCPPCAP pass (Phase 2 of the restructuring plan):
builds init/run/finalize dispatch subroutines for a suite lifecycle phase.
Kept as a plain importable module (not a registered pass) per the phase plan
-- called directly from generate-ccpp-cap's final module assembly.
"""

from xdsl.dialects import arith, builtin, func, llvm, memref, scf
from xdsl.dialects.builtin import (
    DYNAMIC_INDEX,
    IndexType,
    IntegerAttr,
    StringAttr,
    i8,
)
from xdsl.ir import Block, Region

from xdsl_ccpp.dialects.ccpp_utils import (
    CapVarRefOp,
    DerivedType,
    HostVarRefOp,
    StrCmpOp,
    TrimOp,
)
from xdsl_ccpp.transforms.util.cap_shared import (
    _CCPP_CONSTITUENT_MOD,
    LIFECYCLE_POSTFIX_ALIASES,
    _assert_call_arg_count_matches_signature,
    _bare,
    _build_ddt_resolution_maps,
    _build_host_var_map,
    _build_no_suite_matched_false_ops,
    _resolve_ddt_access_path,
    _resolve_member_subscripts,
)
from xdsl_ccpp.util.ccpp_conventions import (
    CCPP_ERRMSG_LEN,
    CCPP_ERROR_CODE,
    CCPP_ERROR_MESSAGE,
)


def _generate_lifecycle_fn(
    fn_name,
    suite_entries,
    suite_name_type,
    errmsg_type,
    errflg_type,
    char_base,
    int_base,
    public_fns,
    meta_data,
    seen_host_globals=None,
    cap_var_map=None,
    host_var_map_lc=None,
    **kwargs,
):
    """Build one combined CCPP cap lifecycle FuncOp dispatching over all suites.

    ``suite_entries`` is a list of
    ``(suite_name, suite_callee, call_ret_types, scheme_names, entry_postfix)``
    tuples.

    For initialize/finalize/timestep_initial/timestep_final, ``entry_postfix``
    is the scheme entry-point suffix (e.g. ``"_init"``, ``"_timestep_init"``).
    The callee's input args are looked up in the scheme entry-point metadata
    and resolved against host module variables, mirroring what
    ``_generate_run_fn`` does for the physics call -- most of these phases
    happen to need nothing beyond suite_name/errmsg/errflg, but that's a
    property of the schemes actually ported so far, not something this
    function assumes; when a phase's own scheme entry point genuinely needs
    a HOST-type-table variable (examples/opt_arg's timestep_init/
    timestep_final need nx/var/opt_var/opt_var_2), the pre-scan below
    exposes it as a real dummy argument on this wrapper's own signature.

    Returns ``(FuncOp, [external_decl_FuncOp, ...], [host_GlobalOp, ...])``.
    """
    for suite_name, suite_callee, _ret, _sn, _ep, _ri in suite_entries:
        assert suite_callee in public_fns, (
            f"Suite callee '{suite_callee}' not found among public suite cap "
            f"functions; available: {sorted(public_fns)}"
        )

    # MODULE only: lifecycle input arg lookups use USE statements, which only
    # work for MODULE-type tables.  HOST-type tables are caller-provided args
    # (not Fortran modules) so they must not generate USE stubs.
    host_var_map = _build_host_var_map(meta_data, include_host=False)
    ddt_instance_map, ddt_parent_map = _build_ddt_resolution_maps(meta_data)

    # Pre-scan: discover HOST-type-table args this dispatch's own scheme
    # phases genuinely need, so they can be exposed as real dummy arguments
    # on this wrapper's own signature (mirroring _generate_run_fn's own
    # pattern for the physics/_run phase) instead of falling back to an
    # uninitialized local placeholder (the confirmed examples/opt_arg bug:
    # timestep_initial/timestep_final declared local, never-allocated
    # lc_nx/lc_var/lc_opt_var/lc_opt_var_2 and passed those into the suite
    # callee, instead of nx/var/opt_var/opt_var_2 from data.meta's HOST-type
    # table). HOST-type table variables are deliberately never use-
    # associated anywhere in this codebase (see host_var_map's own comment
    # above) -- always passed as caller-supplied block arguments -- so a
    # lifecycle phase whose own scheme entry point needs one must receive it
    # the same way, not synthesize a disconnected local scratch value. Must
    # run before new_block is constructed below, since the extra args have
    # to be part of its arg_types from the start.
    # ccpp_info_t / ccpp_t are themselves declared in a HOST-type table
    # (that's how the caller detected them in the first place), so they'd
    # otherwise also satisfy the "HOST-exclusive" test just below and get
    # duplicated as a second, redundant block argument alongside the
    # dedicated handling each already gets a few lines down.
    _ccpp_info_type_for_scan = kwargs.get("ccpp_info_type")

    def _is_ccpp_t_type(_t) -> bool:
        return (
            hasattr(_t, "element_type")
            and hasattr(_t.element_type, "type_name")
            and _t.element_type.type_name.data == "ccpp_t"
        )

    host_var_map_all = _build_host_var_map(meta_data, include_host=True)
    extra_host_args: dict = {}  # bare_name -> (arg_type, intent)
    for _sn, _suite_callee, _ret, _scheme_names, _entry_postfix, _ri in suite_entries:
        if _entry_postfix is None:
            continue
        _, _, _callee_in_types, _callee_in_names = public_fns[_suite_callee]
        _lc_candidates = [_entry_postfix]
        if _entry_postfix in LIFECYCLE_POSTFIX_ALIASES:
            _lc_candidates.append(LIFECYCLE_POSTFIX_ALIASES[_entry_postfix])
        _std_name_of: dict = {}
        _intent_of: dict = {}
        for _scheme_name in _scheme_names:
            if _scheme_name not in meta_data:
                continue
            for _lc_cand in _lc_candidates:
                _entry_name = _scheme_name + _lc_cand
                if _entry_name not in meta_data[_scheme_name].arg_tables:
                    continue
                for _fn_arg in (
                    meta_data[_scheme_name].getArgTable(_entry_name).getFunctionArguments()
                ):
                    _bare_name = _bare(_fn_arg.name)
                    if _bare_name not in _std_name_of and _fn_arg.hasAttr("standard_name"):
                        _std_name_of[_bare_name] = _fn_arg.getAttr("standard_name").lower()
                        _intent_of[_bare_name] = (
                            _fn_arg.getAttr("intent") if _fn_arg.hasAttr("intent") else "in"
                        )
                break
        for _arg_name, _arg_type in zip(_callee_in_names, _callee_in_types):
            _bare_name = _bare(_arg_name)
            _std_name = _std_name_of.get(_bare_name)
            if _std_name is None and _bare_name.lower() in host_var_map_all:
                # Not any scheme's own declared arg -- suite_cap.py's own
                # active-gate pre-scan (_collect_active_gate_extra_args) can
                # synthesize an extra HOST-type-table arg on its callee's
                # signature that no scheme metadata ever declares (an
                # 'active = <flag>' reference, not a real scheme argument).
                # Falls back to treating the callee's own bare arg name as
                # the standard name directly -- true for both real cases so
                # far (data.meta's own flag_for_opt_arg/flag_indicating_
                # cloud_microphysics_has_graupel each declare bare name ==
                # standard_name), not a general guarantee.
                _std_name = _bare_name.lower()
            if (
                _std_name
                and _std_name in host_var_map_all
                and _std_name not in host_var_map
                and _bare_name not in extra_host_args
                and not (_ccpp_info_type_for_scan is not None and _std_name == "host_standard_ccpp_type")
                and not _is_ccpp_t_type(_arg_type)
            ):
                extra_host_args[_bare_name] = (_arg_type, _intent_of.get(_bare_name, "in"))
    extra_host_arg_names = list(extra_host_args.keys())
    extra_host_arg_types = [extra_host_args[n][0] for n in extra_host_arg_names]
    # Only inout/out extra args need to be threaded back out through
    # func.ReturnOp -- an intent(in) one is a pure passthrough, same as any
    # other input-only dummy argument.
    extra_host_arg_inout_names = [
        n for n in extra_host_arg_names if extra_host_args[n][1] != "in"
    ]

    ccpp_info_type = kwargs.get("ccpp_info_type")
    ccpp_info_module = kwargs.get("ccpp_info_module")
    ccpp_t_type = kwargs.get("ccpp_t_type")
    ccpp_t_var_name = kwargs.get("ccpp_t_var_name", "ccpp_data")

    if ccpp_info_type is not None:
        # ccpp_info_t pattern: single inout arg bundles errmsg/errflg.
        # Use HostVarRefOps (member access) in place of AllocaOps so the
        # printer emits ccpp_info%errmsg / ccpp_info%errflg everywhere.
        new_block = Block(arg_types=[suite_name_type, ccpp_info_type] + extra_host_arg_types)
        new_block.args[0].name_hint = "suite_name"
        new_block.args[1].name_hint = "ccpp_info"
        for _i, _n in enumerate(extra_host_arg_names):
            new_block.args[2 + _i].name_hint = _n + "__hostarg"
        errmsg_alloc = HostVarRefOp(
            "ccpp_info", ccpp_info_module, errmsg_type, member_name="errmsg"
        )
        errflg_alloc = HostVarRefOp(
            "ccpp_info", ccpp_info_module, errflg_type, member_name="errflg"
        )
    elif ccpp_t_type is not None:
        # ccpp_t pattern: ccpp_data is threaded as intent(inout); errmsg/errflg
        # are still local allocas returned as intent(out) to the host.
        new_block = Block(arg_types=[suite_name_type, ccpp_t_type] + extra_host_arg_types)
        new_block.args[0].name_hint = "suite_name"
        new_block.args[1].name_hint = ccpp_t_var_name
        for _i, _n in enumerate(extra_host_arg_names):
            new_block.args[2 + _i].name_hint = _n + "__hostarg"
        errmsg_alloc = memref.AllocaOp.get(char_base, shape=[CCPP_ERRMSG_LEN])
        errmsg_alloc.memref.name_hint = "errmsg"
        errflg_alloc = memref.AllocaOp.get(int_base, shape=[])
        errflg_alloc.memref.name_hint = "errflg"
    else:
        # capgen pattern: function returns errmsg/errflg as separate outputs.
        errmsg_alloc = memref.AllocaOp.get(char_base, shape=[CCPP_ERRMSG_LEN])
        errmsg_alloc.memref.name_hint = "errmsg"
        errflg_alloc = memref.AllocaOp.get(int_base, shape=[])
        errflg_alloc.memref.name_hint = "errflg"
        new_block = Block(arg_types=[suite_name_type] + extra_host_arg_types)
        new_block.args[0].name_hint = "suite_name"
        for _i, _n in enumerate(extra_host_arg_names):
            new_block.args[1 + _i].name_hint = _n + "__hostarg"

    # Extra HOST-table args are always appended last, regardless of which
    # branch above ran -- their block-arg index is just the tail of
    # new_block.args.
    extra_host_arg_index: dict = {
        n: len(new_block.args) - len(extra_host_arg_names) + i
        for i, n in enumerate(extra_host_arg_names)
    }

    err_const = arith.ConstantOp.from_int_and_width(0, 32)
    store_errflg = memref.StoreOp.get(err_const, errflg_alloc, [])
    trim_suite_name = TrimOp(new_block.args[0])

    # Innermost else: no suite matched
    current_false_ops = _build_no_suite_matched_false_ops(
        errmsg_alloc, trim_suite_name.res, errflg_alloc
    )

    all_host_global_ops: list = []
    # Use the shared set if provided to avoid duplicate GlobalOps across calls
    if seen_host_globals is None:
        seen_host_globals = set()
    decls = []
    # Placeholder allocas for unmatched args must be declared at function scope,
    # not inside IfOp branches. Collect them here and hoist to the main block.
    hoisted_alloc_ops: list = []

    _cap_var_map = cap_var_map or {}
    _host_var_map_lc = host_var_map_lc or {}

    for suite_name, suite_callee, call_ret_types, scheme_names, entry_postfix, ret_info \
            in reversed(suite_entries):
        _, _, callee_input_types, callee_input_names = public_fns[suite_callee]

        # Build {bare_arg_name → standard_name} from the scheme entry-point tables
        std_name_of: dict = {}
        # {bare_arg_name → (model_var_name, model_module_name)} for args
        # HostVariableMatchPass resolved to a DDT member (e.g. var_compat's
        # scheme_order, matched to phys_state%scheme_order) -- module-level
        # host vars are already handled below via host_var_map, but nothing
        # in this function previously resolved a DDT-member match at all, so
        # such an arg silently fell through to a fresh, uninitialized local
        # alloca instead (a real runtime bug: any inout scalar threaded this
        # way, like a scheme-call-order sanity counter, starts from garbage
        # instead of the host's actual persisted value).
        ddt_member_info: dict = {}
        if entry_postfix is not None:
            # atmospheric_physics uses _timestep_init/_timestep_final/_final;
            # accept all of LIFECYCLE_POSTFIX_ALIASES' short forms too.
            _lc_candidates = [entry_postfix]
            if entry_postfix in LIFECYCLE_POSTFIX_ALIASES:
                _lc_candidates.append(LIFECYCLE_POSTFIX_ALIASES[entry_postfix])
            for scheme_name in scheme_names:
                if scheme_name not in meta_data:
                    continue
                for _lc_cand in _lc_candidates:
                    entry_name = scheme_name + _lc_cand
                    if entry_name not in meta_data[scheme_name].arg_tables:
                        continue
                    for fn_arg in (
                        meta_data[scheme_name]
                        .getArgTable(entry_name)
                        .getFunctionArguments()
                    ):
                        # Strip __alloc/__opt suffix used for allocatable/optional name_hints
                        bare = _bare(fn_arg.name)
                        if bare not in std_name_of and fn_arg.hasAttr("standard_name"):
                            std_name_of[bare] = fn_arg.getAttr("standard_name").lower()
                        if (
                            bare not in ddt_member_info
                            and fn_arg.hasAttr("model_var_is_ddt")
                            and fn_arg.hasAttr("model_var_name")
                        ):
                            ddt_member_info[bare] = (
                                fn_arg.getAttr("model_var_name"),
                                fn_arg.getAttr("model_module_name"),
                            )
                    break  # found entry for this scheme; stop trying candidates

        # Resolve each input arg: host-mapped → HostVarRefOp, other → alloca
        true_branch_pre_ops: list = []
        call_inputs: list = []

        for arg_name, arg_type in zip(callee_input_names, callee_input_types):
            bare = _bare(arg_name)
            std_name = std_name_of.get(bare)

            if std_name and std_name in host_var_map:
                host_var_name, host_module_name = host_var_map[std_name]
                ref_op = HostVarRefOp(host_var_name, host_module_name, arg_type)
                true_branch_pre_ops.append(ref_op)
                call_inputs.append(ref_op.res)
                # Emit host global stub for USE statement generation
                key = (host_var_name, host_module_name)
                if key not in seen_host_globals:
                    seen_host_globals.add(key)
                    glob = llvm.GlobalOp(
                        llvm.LLVMArrayType.from_size_and_type(1, i8),
                        host_var_name,
                        "external",
                    )
                    glob.attributes["module"] = StringAttr(host_module_name)
                    all_host_global_ops.append(glob)
            elif bare in ddt_member_info:
                # Host-matched to a DDT member (e.g. var_compat's
                # scheme_order, resolved to phys_state%scheme_order) --
                # mirrors run_dispatch.py's own DdtMember resolution for the
                # "_run" dispatch. Follows parent DDTs for nested types
                # (A contains B contains x -> a%b%x), same as there.
                model_var_name, model_module_name = ddt_member_info[bare]
                result = _resolve_ddt_access_path(
                    model_module_name, ddt_instance_map, ddt_parent_map
                )
                if result is not None:
                    instance_var, instance_module, path_prefix = result
                    resolved_member, sub_vars = _resolve_member_subscripts(
                        path_prefix + model_var_name, host_var_map
                    )
                    ref_op = HostVarRefOp(
                        instance_var, instance_module, arg_type,
                        member_name=resolved_member,
                    )
                    true_branch_pre_ops.append(ref_op)
                    call_inputs.append(ref_op.res)
                    for local_name, module_name in sub_vars:
                        key = (local_name, module_name)
                        if key not in seen_host_globals:
                            seen_host_globals.add(key)
                            glob = llvm.GlobalOp(
                                llvm.LLVMArrayType.from_size_and_type(1, i8),
                                local_name, "external",
                            )
                            glob.attributes["module"] = StringAttr(module_name)
                            all_host_global_ops.append(glob)
                    key = (instance_var, instance_module)
                    if key not in seen_host_globals:
                        seen_host_globals.add(key)
                        glob = llvm.GlobalOp(
                            llvm.LLVMArrayType.from_size_and_type(1, i8),
                            instance_var, "external",
                        )
                        glob.attributes["module"] = StringAttr(instance_module)
                        all_host_global_ops.append(glob)
                else:
                    # No module-level instance reachable -- fall back to a
                    # fresh local rather than silently resolving nothing.
                    alloc_op = memref.AllocaOp.get(
                        arg_type.element_type, shape=list(arg_type.shape.data)
                    )
                    alloc_op.memref.name_hint = f"lc_{bare}"
                    true_branch_pre_ops.append(alloc_op)
                    call_inputs.append(alloc_op.memref)
            elif (
                ccpp_info_type is not None
                and std_name == "host_standard_ccpp_type"
            ):
                # The ccpp_info_t block arg IS the CCPP framework handle — pass
                # it directly to callees that expect host_standard_ccpp_type.
                call_inputs.append(new_block.args[1])
            elif (
                ccpp_t_type is not None
                and hasattr(arg_type, "element_type")
                and hasattr(arg_type.element_type, "type_name")
                and arg_type.element_type.type_name.data == "ccpp_t"
            ):
                # The ccpp_t block arg is passed directly to suite callees.
                call_inputs.append(new_block.args[1])
            elif bare in extra_host_arg_index:
                # Resolved by the pre-scan above to a HOST-type-table var this
                # phase's own scheme entry point genuinely needs -- passed
                # straight through as this wrapper's own dummy argument
                # (never use-associated, matching every other HOST-type
                # table reference in this codebase).
                call_inputs.append(new_block.args[extra_host_arg_index[bare]])
            else:
                # Not host-matched (e.g. optional arg or allocatable DDT arg).
                # Hoist the alloca to function scope so Fortran can declare it
                # at the top of the subroutine (not inside an IfOp branch).
                elem_type = arg_type.element_type
                shape = list(arg_type.shape.data)
                n_dyn = sum(1 for d in shape if d.data == DYNAMIC_INDEX)
                if (
                    isinstance(elem_type, DerivedType)
                    and elem_type.type_name.data == "ccpp_constituent_properties_t"
                    and n_dyn > 0
                ):
                    # Constituent-property arrays are declared at module scope
                    # via ModuleVarOp.  Reference them with CapVarRefOp so the
                    # allocated values persist after physics_register returns.
                    cap_ref = CapVarRefOp(f"lc_{bare}", arg_type)
                    hoisted_alloc_ops.append(cap_ref)
                    call_inputs.append(cap_ref.res)
                    _ddt_mod = _CCPP_CONSTITUENT_MOD
                    _key = (elem_type.type_name.data, _ddt_mod)
                    if _key not in seen_host_globals:
                        seen_host_globals.add(_key)
                        _g = llvm.GlobalOp(
                            llvm.LLVMArrayType.from_size_and_type(1, i8),
                            elem_type.type_name.data,
                            "external",
                        )
                        _g.attributes["module"] = StringAttr(_ddt_mod)
                        all_host_global_ops.append(_g)
                elif n_dyn > 0:
                    # Dynamic-dim alloca requires size operands per MLIR rules.
                    # Use zero index constants as placeholders — these are
                    # allocatable args whose storage is managed by the callee.
                    zero_idx = arith.ConstantOp(
                        IntegerAttr(0, IndexType()), IndexType()
                    )
                    alloc_op = memref.AllocaOp.get(
                        elem_type, shape=shape,
                        dynamic_sizes=[zero_idx.result] * n_dyn,
                    )
                    alloc_op.memref.name_hint = f"lc_{bare}__alloc"
                    hoisted_alloc_ops.append(zero_idx)
                    # Ensure the DDT type's module appears in the USE list.
                    _CCPP_DDT_MODS = {
                        "ccpp_constituent_properties_t": _CCPP_CONSTITUENT_MOD,
                    }
                    if isinstance(elem_type, DerivedType):
                        _ddt_mod = _CCPP_DDT_MODS.get(elem_type.type_name.data)
                        if _ddt_mod:
                            _key = (elem_type.type_name.data, _ddt_mod)
                            if _key not in seen_host_globals:
                                seen_host_globals.add(_key)
                                _g = llvm.GlobalOp(
                                    llvm.LLVMArrayType.from_size_and_type(1, i8),
                                    elem_type.type_name.data,
                                    "external",
                                )
                                _g.attributes["module"] = StringAttr(_ddt_mod)
                                all_host_global_ops.append(_g)
                    hoisted_alloc_ops.append(alloc_op)
                    call_inputs.append(alloc_op.memref)
                else:
                    alloc_op = memref.AllocaOp.get(elem_type, shape=shape)
                    alloc_op.memref.name_hint = f"lc_{bare}"
                    hoisted_alloc_ops.append(alloc_op)
                    call_inputs.append(alloc_op.memref)

        # ── Verify argument count matches callee signature ─────────────────
        _assert_call_arg_count_matches_signature(
            suite_callee, call_inputs, callee_input_names, callee_input_types
        )

        # Build the call, then handle each return value:
        #   errmsg/errflg  → copy to the function's errmsg/errflg allocas
        #   cap-owned DDT  → copy to the module-level cap variable
        #   host variable  → copy back to the host module variable
        call_op = func.CallOp(suite_callee, call_inputs, call_ret_types)
        copy_ops = []
        copy_pre_ops = []  # CapVarRefOps / HostVarRefOps placed before the call
        for idx, (ret_type, _arg_name, std_name) in enumerate(ret_info):
            result = call_op.results[idx]
            # Match errmsg/errflg by standard_name when available (init/finalize),
            # or fall back to type matching for timestep functions where
            # ret_info has std_name=None (built from call_ret_types only).
            if std_name == CCPP_ERROR_MESSAGE or (
                std_name is None and ret_type == errmsg_type
            ):
                copy_ops.append(memref.CopyOp(result, errmsg_alloc))
            elif std_name == CCPP_ERROR_CODE or (
                std_name is None and ret_type == errflg_type
            ):
                copy_ops.append(memref.CopyOp(result, errflg_alloc))
            elif std_name and std_name in _cap_var_map:
                # Cap-owned interstitial: copy to module-level var.
                # Use the SSA result type; cap_var_map may store None for
                # framework-managed and scratch vars whose type is only
                # known from the actual return value.
                var_name, var_type, _ftn = _cap_var_map[std_name]
                cap_ref = CapVarRefOp(var_name, var_type or ret_type)
                copy_pre_ops.append(cap_ref)
                copy_ops.append(memref.CopyOp(result, cap_ref.res))
            elif std_name and std_name in _host_var_map_lc:
                # Host variable: write result back to host module var
                hv_name, hv_module = _host_var_map_lc[std_name]
                hv_ref = HostVarRefOp(hv_name, hv_module, ret_type)
                copy_pre_ops.append(hv_ref)
                copy_ops.append(memref.CopyOp(result, hv_ref.res))
                key = (hv_name, hv_module)
                if key not in (seen_host_globals or set()):
                    if seen_host_globals is not None:
                        seen_host_globals.add(key)
                    hv_glob = llvm.GlobalOp(
                        llvm.LLVMArrayType.from_size_and_type(1, i8),
                        hv_name, "external",
                    )
                    hv_glob.attributes["module"] = StringAttr(hv_module)
                    all_host_global_ops.append(hv_glob)
            elif (
                ccpp_t_type is not None
                and hasattr(ret_type, "element_type")
                and hasattr(ret_type.element_type, "type_name")
                and ret_type.element_type.type_name.data == "ccpp_t"
            ):
                # ccpp_t is intent(inout) — mirror back to the block arg so
                # the printer's inout-echo detection fires and the arg is not
                # duplicated in the Fortran call argument list.
                copy_ops.append(memref.CopyOp(result, new_block.args[1]))

        # copy_pre_ops (CapVarRefOp/HostVarRefOp) must come BEFORE the call so
        # the printer registers their results in `variables` before _print_call
        # resolves the return-value destinations.
        strcmp_op = StrCmpOp(trim_suite_name.res, literal=suite_name)
        if_op = scf.IfOp(
            strcmp_op.res,
            [],
            true_branch_pre_ops + copy_pre_ops + [call_op] + copy_ops + [scf.YieldOp()],
            current_false_ops,
        )
        current_false_ops = [strcmp_op, if_op, scf.YieldOp()]

    main_chain_ops = current_false_ops[:-1]

    # inout/out extra HOST-table args must be echoed back through
    # func.ReturnOp -- same reasoning as the ccpp_t block arg just above
    # (print_ftn.py's inout-echo detection: a memref that is both a block
    # arg and a returned value prints as intent(inout), not duplicated in
    # the call argument list). They're memrefs already mutated in place by
    # the suite callee, so the returned value is the block arg itself, not
    # a separately computed one.
    extra_inout_vals = [new_block.args[extra_host_arg_index[n]] for n in extra_host_arg_inout_names]
    extra_inout_types = [extra_host_args[n][0] for n in extra_host_arg_inout_names]

    if ccpp_info_type is not None:
        ret_op = func.ReturnOp(new_block.args[1], *extra_inout_vals)  # return ccpp_info as inout
        fn_type = builtin.FunctionType.from_lists(
            [suite_name_type, ccpp_info_type] + extra_host_arg_types,
            [ccpp_info_type] + extra_inout_types,
        )
    elif ccpp_t_type is not None:
        ret_op = func.ReturnOp(new_block.args[1], errmsg_alloc, errflg_alloc, *extra_inout_vals)
        fn_type = builtin.FunctionType.from_lists(
            [suite_name_type, ccpp_t_type] + extra_host_arg_types,
            [ccpp_t_type, errmsg_type, errflg_type] + extra_inout_types,
        )
    else:
        ret_op = func.ReturnOp(errmsg_alloc, errflg_alloc, *extra_inout_vals)
        fn_type = builtin.FunctionType.from_lists(
            [suite_name_type] + extra_host_arg_types,
            [errmsg_type, errflg_type] + extra_inout_types,
        )

    new_block.add_ops(
        [
            errmsg_alloc,
            errflg_alloc,
            *hoisted_alloc_ops,   # placeholder allocas declared at function scope
            err_const,
            store_errflg,
            trim_suite_name,
            *main_chain_ops,
            ret_op,
        ]
    )

    body = Region()
    body.add_block(new_block)
    cap_fn = func.FuncOp(fn_name, fn_type, body, visibility="public")

    for suite_name, suite_callee, call_ret_types, scheme_names, entry_postfix, _ri \
            in suite_entries:
        callee_module, _, callee_input_types, _ = public_fns[suite_callee]
        decl = func.FuncOp.external(suite_callee, callee_input_types, call_ret_types)
        decl.attributes["module"] = StringAttr(callee_module)
        decls.append(decl)

    return cap_fn, decls, all_host_global_ops

