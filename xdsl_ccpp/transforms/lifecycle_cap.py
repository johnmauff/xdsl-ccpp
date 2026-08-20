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
    LazyAllocOp,
    StrCmpOp,
    TrimOp,
)
from xdsl_ccpp.transforms.util.cap_shared import (
    _CCPP_CONSTITUENT_MOD,
    FRAMEWORK_STD_NAME_TO_CAP_VAR,
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
    # phases genuinely need (i.e. a real, scheme-declared dummy argument of
    # that phase's own entry point -- e.g. examples/opt_arg's
    # timestep_init/timestep_final genuinely need nx/var/opt_var/opt_var_2
    # from data.meta's HOST-type table), so they can be exposed as real
    # dummy arguments on this wrapper's own signature (mirroring
    # _generate_run_fn's own pattern for the physics/_run phase) instead of
    # falling back to an uninitialized local placeholder (the confirmed
    # examples/opt_arg bug this pre-scan fixed: timestep_initial/
    # timestep_final declared local, never-allocated
    # lc_nx/lc_var/lc_opt_var/lc_opt_var_2 and passed those into the suite
    # callee). This pre-scan is unaffected by the vocabulary-resolution
    # redesign's Stage 2a (ccpp_cap_refactor_plan.md): that stage moved
    # HOST-type vars referenced *only* inside an 'active = <expr>' property
    # (never a real scheme argument) to use-association inside suite_cap.py's
    # own generated function -- this pre-scan only ever concerns itself with
    # vars that ARE one of these phases' own genuinely scheme-declared
    # arguments, a case the redesign hasn't touched. Must run before
    # new_block is constructed below, since the extra args have to be part
    # of its arg_types from the start.
    # ccpp_info_t is itself declared in a HOST-type table (that's how the
    # caller detected it in the first place), so it'd otherwise also satisfy
    # the "HOST-exclusive" test just below and get duplicated as a second,
    # redundant block argument alongside the dedicated handling it already
    # gets a few lines down.
    _ccpp_info_type_for_scan = kwargs.get("ccpp_info_type")

    # Real capgen-v1's multi-instance model (ccpp_cap_refactor_plan.md's
    # "instances/instances_advection" entry, task #35): a scheme's own
    # _register-phase dynamically-registered constituent output (e.g.
    # dyn_const) is referenced below via a dedicated CapVarRefOp branch,
    # keyed purely by matching constituent_cap.py's own bare naming
    # convention (lc_<bare>) -- see that branch's own comment. Multi-
    # instance moves constituent_cap.py's own module var for each of these
    # into a per-instance bundle-type component
    # (lc_instances(instance)%lc_<bare>), so that branch needs to know
    # instance_local_name too, to build the matching reference text -- and
    # ninstances_local_name, to size a guarded lazy-allocate of
    # lc_instances itself: this branch fires inside ccpp_register, which
    # the driver always calls BEFORE test_host_ccpp_register_constituents
    # (the entry point constituent_cap.py's own lazy-alloc lives in) --
    # confirmed the hard way in real CI, a SIGSEGV: indexing
    # lc_instances(instance) here, before anything has ever allocated
    # lc_instances at all, is undefined behavior, not merely an
    # unallocated-component read.
    instance_local_name = kwargs.get("instance_local_name")
    ninstances_local_name = kwargs.get("ninstances_local_name")
    # Paired contract, not two independent optionals -- the dyn_const branch
    # below gates its own lc_instances(instance)%... reference and
    # LazyAllocOp on instance_local_name alone; without ninstances_local_name
    # too, that LazyAllocOp's own allocate(lc_instances(ninstances)) would
    # get a literal "None" spliced into generated Fortran. ccpp_cap.py's own
    # resolution site normalizes both to None together, but assert the
    # invariant here too, matching this codebase's existing
    # _assert_call_arg_count_matches_signature precedent. Caught by Copilot
    # review on PR #77.
    assert (instance_local_name is None) == (ninstances_local_name is None), (
        "instance_local_name and ninstances_local_name must both be set or "
        "both be None -- got "
        f"instance_local_name={instance_local_name!r}, "
        f"ninstances_local_name={ninstances_local_name!r}"
    )
    _lc_instances_alloc_emitted = False

    host_var_map_all = _build_host_var_map(meta_data, include_host=True)
    # Inverted (local var name -> standard_name) fallback for callee args no
    # scheme's own entry-point metadata declares at all for THIS phase --
    # e.g. instance_number/number_of_instances (real capgen-v1's
    # multi-instance model, ccpp_cap_refactor_plan.md's "instances/
    # instances_advection" entry): suite_cap.py's
    # _synthesize_instance_number_arg/_synthesize_number_of_instances_arg
    # add them straight to the suite callee's own signature for every
    # lifecycle phase, not because any scheme's _init/_finalize/
    # _timestep_init/_timestep_final entry point declares them (only _run
    # ever does, and only instance_number at that) -- so _std_name_of below
    # never has an entry for them, even though the callee's real signature
    # now requires a value. Mirrors run_dispatch.py's own HOST/MODULE/DDT
    # table name-matching fallback for the identical problem on the _run
    # side (_build_per_suite_run_info).
    name_to_std_all: dict = {v: k for k, (v, _m) in host_var_map_all.items()}
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
            _std_name = _std_name_of.get(_bare_name) or name_to_std_all.get(_bare_name)
            if (
                _std_name
                and _std_name in host_var_map_all
                and _std_name not in host_var_map
                and _bare_name not in extra_host_args
                and not (_ccpp_info_type_for_scan is not None and _std_name == "host_standard_ccpp_type")
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
        # {bare_arg_name → intent} from the same scan -- needed to gate the
        # cap_var_map input-resolution branch below (task #60) to genuine
        # intent(in)/intent(inout) reads only. An intent(out)-only arg (e.g.
        # environ_conditions_init's own "o3"/"hno3" outputs, real examples
        # in examples/ddthost) just needs a fresh writable local, exactly as
        # before -- it must not be redirected to whatever cap_var_map's
        # standard_name lookup happens to return, since that's this suite's
        # OWN unrelated cap-var namespace and can collide by std_name with a
        # completely different call's own output-only arg (confirmed via a
        # real regression while verifying this fix: environ_conditions's
        # "ozone"/"nitric_acid" outputs got wrongly rewired to a same-named,
        # unrelated cap_var_map entry).
        intent_of: dict = {}
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
                        if bare not in intent_of:
                            intent_of[bare] = (
                                fn_arg.getAttr("intent") if fn_arg.hasAttr("intent") else "in"
                            )
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
                    instance_var, instance_module, path_prefix, _instance_array_dim = result
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
                std_name
                and std_name in FRAMEWORK_STD_NAME_TO_CAP_VAR
                and std_name in _cap_var_map
                and intent_of.get(bare, "in") in ("in", "inout")
            ):
                # A well-known framework array (ccpp_constituents,
                # ccpp_constituent_tendencies, ...) needed as a genuine READ
                # (intent in/inout) on this lifecycle phase -- mirrors
                # run_dispatch.py's own CapVar resolution for the "_run"
                # dispatch (_build_per_suite_run_info's `std_name in
                # cap_var_map` check). Without this branch, such an arg fell
                # through to the "not host-matched" local-alloca fallback
                # below and silently read an uninitialized value -- the same
                # bug class the opt_arg pre-scan (extra_host_arg_index,
                # above) already fixed for HOST-type-table args. Task #60.
                #
                # Deliberately narrower than "any std_name in cap_var_map":
                # cap_var_map ALSO accumulates plain CapScratch scratch vars
                # (ccpp_cap.py's own scratch_var_list branch) keyed only by
                # standard_name, and standard_name is NOT a reliable identity
                # there -- two unrelated schemes' own unmatched args can
                # share one standard_name by pure coincidence, each meaning
                # a fresh, call-scoped value with no cross-call relationship
                # at all. Confirmed via a real regression while verifying
                # this fix: examples/ddthost's own make_ddt_run declares an
                # intent(in) "vmr" (standard_name volume_mixing_ratio_ddt,
                # no host match) that lands in cap_var_map as a scratch var;
                # a same-named, but semantically unrelated, intent(in) "vmr"
                # on make_ddt_timestep_final was wrongly redirected to that
                # scratch entry instead of getting its own fresh local (the
                # correct, pre-existing behavior). FRAMEWORK_STD_NAME_TO_CAP_VAR's
                # names are the one case where "same standard_name" IS a real
                # identity guarantee -- they always denote the one shared,
                # always-declared framework array, by design.
                # Also gated to in/inout only -- an intent(out)-only arg just
                # needs a fresh writable local (see intent_of's own comment
                # above).
                var_name, var_type, _ftn = _cap_var_map[std_name]
                cap_ref = CapVarRefOp(var_name, var_type or arg_type)
                true_branch_pre_ops.append(cap_ref)
                call_inputs.append(cap_ref.res)
            elif (
                ccpp_info_type is not None
                and std_name == "host_standard_ccpp_type"
            ):
                # The ccpp_info_t block arg IS the CCPP framework handle — pass
                # it directly to callees that expect host_standard_ccpp_type.
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
                    #
                    # Real capgen-v1's multi-instance model (task #35):
                    # when the host is multi-instance, constituent_cap.py
                    # moves this same array from a bare module var into a
                    # per-instance bundle-type component
                    # (lc_instances(instance)%lc_<bare>) -- this reference
                    # must match that exactly, or it's a reference to a
                    # symbol that no longer exists (confirmed the hard way
                    # in real CI: "has no IMPLICIT type").
                    _lc_name = f"lc_{bare}"
                    cap_ref_name = (
                        f"lc_instances({instance_local_name})%{_lc_name}"
                        if instance_local_name is not None
                        else _lc_name
                    )
                    if (
                        instance_local_name is not None
                        and not _lc_instances_alloc_emitted
                        and ninstances_local_name in extra_host_arg_index
                    ):
                        # lc_instances must be allocated before this
                        # reference is even formed (indexing an
                        # unallocated array is undefined behavior, not
                        # merely an unallocated-component read) -- and
                        # ccpp_register (this branch only ever fires for a
                        # _register-phase call) is the first lifecycle
                        # call the driver makes, running BEFORE
                        # constituent_cap.py's own register_constituents
                        # (where lc_instances is normally lazily
                        # allocated) ever gets a chance to. Confirmed the
                        # hard way in real CI: a SIGSEGV inside
                        # cld_suite_suite_register. Guarded exactly like
                        # every other LazyAllocOp use, and only emitted
                        # once per function even if multiple schemes each
                        # have their own dynamic-array output (e.g.
                        # examples/advection's dyn_const/dyn_const_ice).
                        hoisted_alloc_ops.append(
                            LazyAllocOp(
                                var_name="lc_instances",
                                kind_name="type",
                                dim_var_refs=[
                                    new_block.args[extra_host_arg_index[ninstances_local_name]]
                                ],
                            )
                        )
                        _lc_instances_alloc_emitted = True
                    cap_ref = CapVarRefOp(cap_ref_name, arg_type)
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
    # func.ReturnOp -- same reasoning as the ccpp_info_t block arg just above
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

