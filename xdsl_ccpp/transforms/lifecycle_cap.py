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
    _build_host_var_map,
    _build_no_suite_matched_false_ops,
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

    For lifecycle functions that have no host inputs (timestep_initial/final),
    ``entry_postfix`` is None and the call passes no input arguments.

    For initialize/finalize, ``entry_postfix`` is ``"_init"`` / ``"_finalize"``.
    The callee's input args are looked up in the scheme entry-point metadata and
    resolved against host module variables, mirroring what ``_generate_run_fn``
    does for the physics call.

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

    ccpp_info_type = kwargs.get("ccpp_info_type")
    ccpp_info_module = kwargs.get("ccpp_info_module")
    ccpp_t_type = kwargs.get("ccpp_t_type")
    ccpp_t_var_name = kwargs.get("ccpp_t_var_name", "ccpp_data")

    if ccpp_info_type is not None:
        # ccpp_info_t pattern: single inout arg bundles errmsg/errflg.
        # Use HostVarRefOps (member access) in place of AllocaOps so the
        # printer emits ccpp_info%errmsg / ccpp_info%errflg everywhere.
        new_block = Block(arg_types=[suite_name_type, ccpp_info_type])
        new_block.args[0].name_hint = "suite_name"
        new_block.args[1].name_hint = "ccpp_info"
        errmsg_alloc = HostVarRefOp(
            "ccpp_info", ccpp_info_module, errmsg_type, member_name="errmsg"
        )
        errflg_alloc = HostVarRefOp(
            "ccpp_info", ccpp_info_module, errflg_type, member_name="errflg"
        )
    elif ccpp_t_type is not None:
        # ccpp_t pattern: ccpp_data is threaded as intent(inout); errmsg/errflg
        # are still local allocas returned as intent(out) to the host.
        new_block = Block(arg_types=[suite_name_type, ccpp_t_type])
        new_block.args[0].name_hint = "suite_name"
        new_block.args[1].name_hint = ccpp_t_var_name
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
        new_block = Block(arg_types=[suite_name_type])
        new_block.args[0].name_hint = "suite_name"

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

    if ccpp_info_type is not None:
        ret_op = func.ReturnOp(new_block.args[1])  # return ccpp_info as inout
        fn_type = builtin.FunctionType.from_lists(
            [suite_name_type, ccpp_info_type],
            [ccpp_info_type],
        )
    elif ccpp_t_type is not None:
        ret_op = func.ReturnOp(new_block.args[1], errmsg_alloc, errflg_alloc)
        fn_type = builtin.FunctionType.from_lists(
            [suite_name_type, ccpp_t_type],
            [ccpp_t_type, errmsg_type, errflg_type],
        )
    else:
        ret_op = func.ReturnOp(errmsg_alloc, errflg_alloc)
        fn_type = builtin.FunctionType.from_lists(
            [suite_name_type],
            [errmsg_type, errflg_type],
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

