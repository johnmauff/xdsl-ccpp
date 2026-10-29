from dataclasses import dataclass

from xdsl.context import Context
from xdsl.dialects import builtin, func, scf
from xdsl.passes import ModulePass
from xdsl.rewriter import InsertPoint, Rewriter
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects.ccpp import ArgOwnershipKind
from xdsl_ccpp.dialects.ccpp_utils import (
    AccDataBeginOp,
    AccDataEndOp,
    KeywordCallOp,
    OmpTargetDataBeginOp,
    OmpTargetDataEndOp,
)
from xdsl_ccpp.transforms.util.cap_shared import (
    directive_op,
    emit_coalesced_updates,
    find_diverged_capscratch_vars,
    find_diverged_suite_vars,
    fn_phase,
    FRAMEWORK_STD_NAME_TO_CAP_VAR,
    block_args_by_std,
    is_constituent_view_arg,
    resolve_capscratch_cap_var_name,
    split_scheme_table_name,
    suite_cap_suite_name,
    _bare,
    _iter_schemes,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    BuildMetaDataDescriptions,
    BuildSchemeDescription,
)
from xdsl_ccpp.transforms.util.ir_utils import find_ccpp_module


def _ref(std_names, arg_by_std):
    """The suite subroutine's block argument for the first of std_names it
    has, or None. Block arguments are identified by the standard names the
    suite cap records on the subroutine (suite_arg_attrs); a scheme arg
    with no block argument (e.g. a suite-owned module variable) has none."""
    return next((arg_by_std[s] for s in std_names if s in arg_by_std), None)


@dataclass(frozen=True)
class GPUDataPass(ModulePass):
    """Insert OpenACC data directives around GPU-capable scheme calls.

    Reads memory_space and model_var_name annotations from CCPP metadata
    (populated by generate-host-match) and wraps consecutive GPU-capable
    scheme calls in !$acc data regions inside the suite-level _physics,
    _register, _initialize, _finalize, _timestep_initial, and
    _timestep_final subroutines.

    Directives are inserted at the suite_cap level using scheme-local variable
    names, which are the variables in scope at that level.  The model_var_name
    mapping is available for each device-resident argument and will be used
    when directives are moved to the ccpp_cap level in future work.

    Also handles GPU/OpenACC backlog item (b): host vars where different
    schemes in the same suite genuinely disagree about present-vs-update
    treatment (see cap_shared.find_diverged_suite_vars) are excluded
    entirely from GPUCcppCapPass's whole-suite, cross-phase hoisting (see
    gpu_ccpp_cap_pass.py's _analyze_one_suite) -- this pass is the only
    place they get any GPU treatment, routed per individual scheme call
    instead (_process_diverged_host_vars). This works at the suite_cap
    level specifically because each scheme call here receives host vars as
    plain, already-resolved block arguments -- no HostVarRefOp, no DDT-
    member path to resolve (that happened upstream, building the actual
    call to this suite's dispatch function) -- so it works correctly for
    DDT-member host vars too, unlike GPUCcppCapPass's HostVarRefOp-based
    lookup (backlog gap #5).

    Remaining limitation:
    - Host-less scratch vars always generate copy (no 'present'
      optimisation yet).
    """

    name = "generate-gpu-data"

    # GPU directive backend: "acc" for OpenACC, "omp" for OpenMP target offload.
    directive: str = "acc"

    # Debug-only: when set, also emit an `update self(...)` immediately
    # after every scheme call that writes (intent out/inout) a
    # memory_space=device HostMatched or CapScratch arg, regardless of
    # divergence status -- see _build_debug_sync_touches. Mirrors host
    # memory to the just-computed device value moments after it's
    # produced, so a device-blind host-memory debugger (e.g. dropsonde)
    # reads a live, correct value instead of a stale/uninitialized one.
    debug_sync: bool = False

    def _get_scheme_name(self, callee_name):
        """Strip lifecycle suffix to get the scheme base name.

        e.g. 'hello_scheme_run' → 'hello_scheme'
        Returns None if the name doesn't match a known suffix.

        Thin wrapper over cap_shared.split_scheme_table_name, which also
        reports which of the six lifecycle phases the suffix identifies --
        gpu_ccpp_cap_pass.py's cross-function hoisting analysis needs that
        phase, so the suffix table itself lives there now as the single
        shared source of truth (see that function's docstring for the
        precedence-ordering rationale) rather than being duplicated here.
        """
        split = split_scheme_table_name(callee_name)
        return split[0] if split is not None else None

    def _get_device_args(self, scheme_name, table_name, meta_data):
        """Return a dict mapping scheme-local name → (host variable name,
        standard name) for
        all device-resident arguments in the scheme's <table_name> argument
        table -- the specific lifecycle entry point actually being called
        (e.g. '<scheme>_timestep_final'), NOT always '<scheme>_run'.  A
        scheme's device-arg set can differ per entry point, so reusing the
        _run table for every call would silently use the wrong argument
        list (or miss the call entirely when the scheme has no _run entry).

        The host variable name comes from the model_var_name annotation set by
        generate-host-match.  It is None when no host match was found (e.g.
        a device-resident scratch array local to the scheme).
        """
        if scheme_name not in meta_data:
            return {}
        if table_name not in meta_data[scheme_name].arg_tables:
            return {}
        device_args = {}
        for arg in (
            meta_data[scheme_name].arg_tables[table_name].getFunctionArguments()
        ):
            if (
                arg.hasAttr("memory_space")
                and arg.getAttr("memory_space") == "device"
            ):
                host_var = (
                    arg.getAttr("model_var_name")
                    if arg.hasAttr("model_var_name")
                    else None
                )
                device_args[arg.name] = (host_var, arg.getAttr("standard_name").lower() if arg.hasAttr("standard_name") else None)
        return device_args

    def _find_call_in_if(self, if_op):
        """Return the scheme call inside an error-guarded scf.IfOp, or None.

        suite_cap.py wraps each scheme call in an scf.IfOp that checks errflg.
        This method looks inside the true region of that guard to find the
        call -- either a plain func.CallOp, or a KeywordCallOp (emitted
        instead whenever the scheme call has any keyword/literal-override
        arguments, e.g. an optional arg -- see suite_cap.py's
        generateSchemeSubroutineCallOps). Missing the KeywordCallOp case
        would silently skip every scheme call involving an optional or
        overridden argument.
        """
        if not if_op.true_region.blocks:
            return None
        for op in if_op.true_region.blocks[0].ops:
            if isa(op, func.CallOp) or isa(op, KeywordCallOp):
                return op
        return None

    def _callee_name(self, call_op):
        """Return the called subroutine name for either call op variety."""
        if isa(call_op, KeywordCallOp):
            return call_op.callee.data
        return call_op.callee.root_reference.data

    def _get_diverged_args(self, scheme_name, table_name, meta_data, diverged_vars):
        """Return {local_name: (category, host_var, standard name)} for every arg in this
        scheme's <table_name> argument table whose model_var_name is in
        diverged_vars.

        category is "present" if this scheme declares memory_space=device
        for the arg, "update" otherwise -- a pure per-arg computation, since
        model_var_memory_space (the host's own declaration) is already
        known to be "device" for every var in diverged_vars (see
        cap_shared.find_diverged_suite_vars). Unlike _get_device_args, this
        scans every host-matched arg, not only device-declared ones -- the
        "update" side of a divergence is exactly a scheme that does NOT
        declare device for a var the host keeps device-resident, so it
        would never show up in _get_device_args's device-only scan.
        """
        if scheme_name not in meta_data or table_name not in meta_data[scheme_name].arg_tables:
            return {}
        result = {}
        for arg in meta_data[scheme_name].arg_tables[table_name].getFunctionArguments():
            if not arg.hasAttr("model_var_name"):
                continue
            host_var = arg.getAttr("model_var_name")
            if host_var not in diverged_vars:
                continue
            scheme_space = (
                arg.getAttr("memory_space") if arg.hasAttr("memory_space") else "host"
            )
            category = "present" if scheme_space == "device" else "update"
            result[arg.name] = (category, host_var, arg.getAttr("standard_name").lower() if arg.hasAttr("standard_name") else None)
        return result

    def _get_diverged_capscratch_args(self, scheme_name, table_name, meta_data, diverged_capscratch_vars):
        """Return {local_name: (category, cap_var_name, is_direct, standard name)} for
        every arg in this scheme's <table_name> argument table that is
        CapScratch-classified and resolves (via
        cap_shared.resolve_capscratch_cap_var_name) to a cap var name in
        diverged_capscratch_vars.

        Mirrors _get_diverged_args, substituting the CapScratch cap-var
        identity (no host match at all) for the host-matched model_var_name
        identity. category is "present" if this scheme declares
        memory_space=device for the arg, "update" otherwise -- the "update"
        side is exactly a scheme sharing the same shared array (e.g.
        apply_constituent_tendencies_run's const_tend) that does NOT
        declare device, even though the array is device-resident overall
        because some other contributing scheme does.

        is_direct is True when this arg's own standard_name is a direct
        FRAMEWORK_STD_NAME_TO_CAP_VAR match (const/const_tend -- the actual
        shared array itself), False when it resolved via the constituent-
        tendency scratch-var path (e.g. cld_liq_tend -- a Fortran pointer
        slice of the shared array, covering only one constituent's data).
        Callers must prefer a direct reference when picking which local
        name's SSA value to sync: an update self/device must cover the
        whole shared array (every constituent, since a host-only consumer
        like apply_constituent_tendencies_run reads/writes all of them),
        not just whichever single constituent a producer scheme's own
        scratch-var alias happens to slice.
        """
        if scheme_name not in meta_data or table_name not in meta_data[scheme_name].arg_tables:
            return {}
        result = {}
        for arg in meta_data[scheme_name].arg_tables[table_name].getFunctionArguments():
            if (
                not arg.hasAttr("ownership_kind")
                or arg.getAttr("ownership_kind") != ArgOwnershipKind.CapScratch
            ):
                continue
            if not arg.hasAttr("standard_name") or is_constituent_view_arg(arg):
                continue
            std_name = arg.getAttr("standard_name")
            cap_var = resolve_capscratch_cap_var_name(
                std_name, arg.hasAttr("constituent"), arg.hasAttr("advected")
            )
            if cap_var is None or cap_var not in diverged_capscratch_vars:
                continue
            scheme_space = (
                arg.getAttr("memory_space") if arg.hasAttr("memory_space") else "host"
            )
            category = "present" if scheme_space == "device" else "update"
            is_direct = std_name.lower() in FRAMEWORK_STD_NAME_TO_CAP_VAR
            result[arg.name] = (category, cap_var, is_direct, std_name.lower())
        return result

    def _get_producing_device_args(self, scheme_name, table_name, meta_data):
        """Return {local_name: (identity, standard name)} for every arg in this scheme's
        <table_name> argument table that writes (intent out/inout) a
        memory_space=device value, regardless of divergence status --
        sibling to _get_device_args (unfiltered by intent, used for the
        hostless-scratch blanket region) and _get_diverged_args (filtered
        by divergence instead of intent).

        identity is ("host", model_var_name) for a HostMatched arg, or
        ("capscratch", cap_var) for a CapScratch arg that resolves (via
        cap_shared.resolve_capscratch_cap_var_name) to a shared cap-owned
        array -- the same two identity shapes _process_diverged_host_vars/
        _process_diverged_capscratch_vars already key their own touches
        dicts by. An arg with neither (a hostless scratch var, already
        covered by the blanket copyin/copyout region in _process_physics_fn)
        has no stable cross-call identity to key on and is skipped -- out
        of scope for debug-sync, matching this pass's existing HostMatched/
        CapScratch-only scope for per-call routing.
        """
        if scheme_name not in meta_data or table_name not in meta_data[scheme_name].arg_tables:
            return {}
        result = {}
        for arg in meta_data[scheme_name].arg_tables[table_name].getFunctionArguments():
            if not arg.hasAttr("memory_space") or arg.getAttr("memory_space") != "device":
                continue
            intent = arg.getAttr("intent") if arg.hasAttr("intent") else None
            if intent not in ("out", "inout"):
                continue
            if is_constituent_view_arg(arg):
                # Its per-call copy() region already copies it back.
                continue
            if arg.hasAttr("model_var_name"):
                identity = ("host", arg.getAttr("model_var_name"))
            elif (
                arg.hasAttr("ownership_kind")
                and arg.getAttr("ownership_kind") == ArgOwnershipKind.CapScratch
                and arg.hasAttr("standard_name")
            ):
                cap_var = resolve_capscratch_cap_var_name(
                    arg.getAttr("standard_name"), arg.hasAttr("constituent"),
                    arg.hasAttr("advected"),
                )
                if cap_var is None:
                    continue
                identity = ("capscratch", cap_var)
            else:
                continue
            result[arg.name] = (identity, arg.getAttr("standard_name").lower() if arg.hasAttr("standard_name") else None)
        return result

    def _build_debug_sync_touches(self, calls, meta_data, arg_by_std):
        """Build (identity, call)-keyed debug-sync touches for every
        producing (intent out/inout) memory_space=device arg in this
        function -- HostMatched and CapScratch alike, regardless of
        divergence status.

        Each touch is classified "produced" (not "update") --
        cap_shared.emit_coalesced_updates treats this as its own,
        self-after-only sync at that one call, never a self-before/
        device-after pair the way a genuine "update" run would (there is
        nothing to pull in before the device has computed anything, and
        no host-side write to push back afterward). Keying each entry by
        (identity, id(call_op)) instead of just identity means every
        producing call gets its own single-call touch: the same var
        written by two different calls is never merged into one run
        spanning both (which would hide one call's own intermediate value
        from a host-memory debugger reading in between), but two
        different vars written by the SAME call DO share that call and
        get grouped into one `update self(...)` call for free, via
        emit_coalesced_updates' own per-call grouping for "produced"
        touches.

        The block argument to sync is found by the args' standard names.
        """
        touches: dict = {}  # identity -> [(call_op, standard name), ...]
        for call_op, scheme_name, table_name in calls:
            for identity, std in self._get_producing_device_args(
                scheme_name, table_name, meta_data
            ).values():
                touches.setdefault(identity, []).append((call_op, std))

        debug_sync_touches: dict = {}
        for identity, touch_list in touches.items():
            ref = _ref((std for _, std in touch_list), arg_by_std)
            if ref is None:
                continue
            for call_op, _ in touch_list:
                key = ("debug_sync", identity, id(call_op))
                debug_sync_touches[key] = (ref, [(call_op, "produced")])
        return debug_sync_touches

    def _emit_present(self, ref, call_op):
        """Wrap a single call in its own present()-only data region.

        present() is a pure runtime assertion, no data movement -- emitted
        individually per touching call rather than coalesced across a run
        (unlike the update self/device runs cap_shared.emit_coalesced_updates
        emits): repeating it is free, and coalescing it across multiple
        calls would risk producing improperly-nested
        (criss-crossing) !$acc data regions if another diverged var's own
        present run happens to overlap without nesting inside this one.
        """
        Rewriter.insert_op(
            directive_op(self.directive, AccDataBeginOp, {"present": [ref]}, OmpTargetDataBeginOp, {"alloc": [ref]}),
            InsertPoint.before(call_op),
        )
        Rewriter.insert_op(
            directive_op(self.directive, AccDataEndOp, {}, OmpTargetDataEndOp, {}),
            InsertPoint.after(call_op),
        )

    def _get_device_constituent_views(self, scheme_name, table_name, meta_data):
        """Return {local_name: standard_name} for the memory_space=device
        constituent views (cap_shared.is_constituent_view_arg) in this
        scheme's <table_name> argument table."""
        if scheme_name not in meta_data or table_name not in meta_data[scheme_name].arg_tables:
            return {}
        return {
            arg.name: arg.getAttr("standard_name").lower()
            for arg in meta_data[scheme_name].arg_tables[table_name].getFunctionArguments()
            if is_constituent_view_arg(arg)
            and arg.hasAttr("memory_space")
            and arg.getAttr("memory_space") == "device"
        }

    def _emit_constituent_view_copies(self, calls, meta_data, arg_by_std):
        """Wrap each call that takes a device constituent view in its own
        copy() region over those views.

        The constituents are updated on the host between device calls (by
        the host model, host-side schemes and tendency appliers writing
        through other views of the same memory), so a device copy is never
        kept across calls: each call copies its views in and back out.
        Keeping lc_constituent_array resident with explicit update syncs
        instead is backlog item constituent-device-residency.

        Called after the blanket hostless region is built, so these
        per-call regions nest inside it.
        """
        for call_op, scheme_name, table_name in calls:
            views = self._get_device_constituent_views(scheme_name, table_name, meta_data)
            refs = []
            for std_name in sorted(set(views.values())):
                ref = arg_by_std.get(std_name)
                if ref is not None and ref not in refs:
                    refs.append(ref)
            if not refs:
                continue
            Rewriter.insert_op(
                directive_op(self.directive, AccDataBeginOp, {"copy": refs}, OmpTargetDataBeginOp, {"tofrom": refs}),
                InsertPoint.before(call_op),
            )
            Rewriter.insert_op(
                directive_op(self.directive, AccDataEndOp, {}, OmpTargetDataEndOp, {}),
                InsertPoint.after(call_op),
            )

    def _process_diverged_host_vars(self, calls, meta_data, diverged_vars, arg_by_std):
        """Route present/update clauses per individual scheme call for host
        vars in `diverged_vars` (backlog item (b)) -- these get no
        VarLifetime at the ccpp_cap level (gpu_ccpp_cap_pass.py excludes
        them entirely), so this is the only place they get any GPU
        treatment at all.

        For each such host var, walk every call that references it (in
        order) and split into maximal runs of consecutive equal
        classification -- a differently-classified touch for the same var
        breaks the run, since an interleaved present-classified call
        genuinely needs the device copy synced (via the surrounding
        update run's boundary) before it executes; blindly hoisting an
        update sync across it would leave that present call observing a
        stale device copy. present touches are still emitted individually
        within a "run" (see _emit_present) since coalescing them has no
        correctness or performance upside; only update runs are actually
        coalesced -- and, across every diverged host/CapScratch var in
        this function, grouped into a shared call whenever their run
        boundaries coincide (see cap_shared.emit_coalesced_updates, called
        once per function from _process_physics_fn with both this
        method's and _process_diverged_capscratch_vars' resolved touches
        merged together).

        Returns the resolved touches dict (not yet emitted) -- see
        _process_physics_fn for why: this is merged with
        _process_diverged_capscratch_vars' own resolved dict before a
        single emit_coalesced_updates call, so a host var and a
        CapScratch var sharing a run boundary end up in the same
        update self/device call.

        The block argument to sync is the one with the args' standard name.
        """
        touches: dict = {}  # host_var -> ordered [(op, category, standard name), ...]
        for call_op, scheme_name, table_name in calls:
            for category, host_var, std in self._get_diverged_args(
                scheme_name, table_name, meta_data, diverged_vars
            ).values():
                touches.setdefault(host_var, []).append((call_op, category, std))

        resolved: dict = {}
        for host_var, touch_list in touches.items():
            ref = _ref((std for _, _, std in touch_list), arg_by_std)
            resolved[host_var] = (ref, [(call_op, category) for call_op, category, _ in touch_list])
        return resolved

    def _process_diverged_capscratch_vars(self, calls, meta_data, diverged_capscratch_vars, arg_by_std):
        """Route present/update clauses per individual scheme call for
        CapScratch cap vars in `diverged_capscratch_vars` -- the CapScratch
        counterpart of _process_diverged_host_vars, for shared cap-owned
        arrays (e.g. lc_const_tend, backing both const_tend and the
        cld_liq_tend pointer alias) instead of host-matched variables.

        Unlike the host-var case, there is no host-declared
        model_var_memory_space to consult for "is this array device-
        resident at all" -- that's instead the OR across every contributing
        scheme's own memory_space declaration (see
        cap_shared.find_diverged_capscratch_vars), already reflected in
        which cap vars land in diverged_capscratch_vars at all.

        Ref resolution differs from _process_diverged_host_vars in one
        important way: a constituent-tendency scratch-var alias (e.g.
        cld_liq_tend) is a Fortran pointer slice covering only ONE
        constituent's data, not the whole shared array -- syncing just
        that slice would silently drop every other constituent's data an
        update self/device is supposed to cover (e.g.
        apply_constituent_tendencies_run reads/writes ALL constituents).
        So, unlike the host-var case where any touching local name is
        equally valid, this prefers a "direct" touch (the arg whose own
        standard_name is the actual shared array, e.g. const/const_tend --
        see _get_diverged_capscratch_args's is_direct) when picking which
        block argument to sync, falling back to any touch only if no direct
        one exists for this cap var.

        Returns the resolved touches dict (not yet emitted) -- see
        _process_diverged_host_vars' docstring and _process_physics_fn for
        why emission is deferred to a single, merged
        cap_shared.emit_coalesced_updates call.
        """
        touches: dict = {}  # cap_var_name -> ordered [(op, category, standard name, is_direct), ...]
        for call_op, scheme_name, table_name in calls:
            for category, cap_var, is_direct, std in self._get_diverged_capscratch_args(
                scheme_name, table_name, meta_data, diverged_capscratch_vars
            ).values():
                touches.setdefault(cap_var, []).append((call_op, category, std, is_direct))

        resolved: dict = {}
        for cap_var, touch_list in touches.items():
            ref = _ref((std for _, _, std, is_direct in touch_list if is_direct), arg_by_std)
            if ref is None:
                ref = _ref((std for _, _, std, _ in touch_list), arg_by_std)
            resolved[cap_var] = (
                ref, [(call_op, category) for call_op, category, _, _ in touch_list]
            )
        return resolved

    def _process_physics_fn(
        self, fn_op, meta_data, diverged_vars=frozenset(), diverged_capscratch_vars=frozenset()
    ):
        """Insert acc.data markers around GPU scheme calls in one subroutine.

        Finds all error-guarded scheme calls, in order, then:
        - hostless scratch args (no host match at all): collects the union
          of their device variable names across every GPU-capable call and
          wraps the entire group in a single !$acc data region (unchanged
          from before this feature -- see the block below) -- except any
          arg whose CapScratch cap var is in diverged_capscratch_vars,
          which is excluded here and routed per individual scheme call
          instead (see _process_diverged_capscratch_vars) to avoid double-
          handling the same shared array two different ways.
        - diverged host vars (backlog item (b)): routed per individual
          scheme call instead -- see _process_diverged_host_vars.
        - diverged CapScratch cap vars: routed per individual scheme call
          instead -- see _process_diverged_capscratch_vars.
        """
        if not fn_op.body.blocks:
            return

        block = fn_op.body.blocks[0]

        # Collect every GPU-capable call in this function, in order, with its
        # scheme/table identity -- shared by both the hostless-scratch path
        # below and the diverged-host-var routing.
        calls = []  # list of (scf.IfOp, scheme_name, table_name)
        for op in block.ops:
            if not isa(op, scf.IfOp):
                continue
            call_op = self._find_call_in_if(op)
            if call_op is None:
                continue
            callee_name = self._callee_name(call_op)
            scheme_name = self._get_scheme_name(callee_name)
            if scheme_name is None:
                continue
            calls.append((op, scheme_name, callee_name))

        if not calls:
            return

        # At the suite_cap level the variables are function block arguments —
        # assumed-shape arrays that already represent the active column slice.
        # No further subsectioning is needed; just pass the block arg SSA values.
        # A scheme arg's block argument is the one with its standard name
        # (suite_arg_attrs); local names are not unique across schemes.
        arg_by_std = block_args_by_std(fn_op)

        # --- hostless scratch vars: unchanged single-region approach ---
        gpu_calls = []  # (scf.IfOp, scheme_name, table_name, device_vars) for calls with >=1 device arg
        for op, scheme_name, table_name in calls:
            device_vars = self._get_device_args(scheme_name, table_name, meta_data)
            if device_vars:
                gpu_calls.append((op, scheme_name, table_name, device_vars))

        if gpu_calls:
            # Only emit suite_cap level directives for variables that have NO
            # host variable match. Variables with a host match are handled at
            # the ccpp_cap level by GPUCcppCapPass (unified vars) or by
            # _process_diverged_host_vars below (diverged vars). Emitting
            # directives here too would create nested !$acc data regions
            # with redundant data movement.
            refs = set()
            for _, scheme_name, table_name, device_vars in gpu_calls:
                diverged_local_names = (
                    self._get_diverged_capscratch_args(
                        scheme_name, table_name, meta_data, diverged_capscratch_vars
                    )
                    if diverged_capscratch_vars
                    else {}
                )
                view_names = self._get_device_constituent_views(
                    scheme_name, table_name, meta_data
                )
                # A suite-owned arg (a suite-cap module variable with its own
                # residency, suite_owned.py) has no block argument, so no ref.
                for local_name, (host_var, std) in device_vars.items():
                    if (
                        host_var is None
                        and local_name not in diverged_local_names
                        and local_name not in view_names
                        and std in arg_by_std
                    ):
                        refs.add(arg_by_std[std])

            if refs:
                first_if = gpu_calls[0][0]
                last_if  = gpu_calls[-1][0]
                copyin_refs = sorted(refs, key=lambda a: _bare(a.name_hint or ""))
                if copyin_refs:
                    if self.directive == "omp":
                        Rewriter.insert_op(
                            OmpTargetDataBeginOp(tofrom=copyin_refs),
                            InsertPoint.before(first_if),
                        )
                        Rewriter.insert_op(
                            OmpTargetDataEndOp(),
                            InsertPoint.after(last_if),
                        )
                    else:  # acc (default)
                        # copy(), not copyin() + copyout() of the same
                        # vars: a var may appear in only one data clause.
                        Rewriter.insert_op(
                            AccDataBeginOp(copy=copyin_refs),
                            InsertPoint.before(first_if),
                        )
                        Rewriter.insert_op(
                            AccDataEndOp(),
                            InsertPoint.after(last_if),
                        )

        # --- device constituent views: a copy() region per call ---
        self._emit_constituent_view_copies(calls, meta_data, arg_by_std)

        # --- diverged host vars + CapScratch cap vars: per-scheme-call
        # routing, merged into one resolved-touches dict so a host var and
        # a CapScratch var sharing the same run boundary are coalesced
        # into a single update self/device call (see
        # cap_shared.emit_coalesced_updates). Keys are namespaced by kind
        # since a host_var name and a cap_var name could otherwise collide.
        merged_touches: dict = {}
        if diverged_vars:
            for host_var, entry in self._process_diverged_host_vars(
                calls, meta_data, diverged_vars, arg_by_std
            ).items():
                merged_touches[("host", host_var)] = entry
        if diverged_capscratch_vars:
            for cap_var, entry in self._process_diverged_capscratch_vars(
                calls, meta_data, diverged_capscratch_vars, arg_by_std
            ).items():
                merged_touches[("capscratch", cap_var)] = entry
        if self.debug_sync:
            merged_touches.update(
                self._build_debug_sync_touches(calls, meta_data, arg_by_std)
            )
        if merged_touches:
            emit_coalesced_updates(self.directive, merged_touches, self._emit_present)

    def apply(self, ctx: Context, op: builtin.ModuleOp) -> None:
        ccpp_mod = find_ccpp_module(op.body.block.ops)
        if ccpp_mod is None:
            return

        # Build metadata descriptors to find memory_space annotations
        bmdd = BuildMetaDataDescriptions()
        bmdd.traverse(ccpp_mod)
        meta_data = bmdd.meta_data

        # Suite -> scheme membership, needed to compute each suite's
        # diverged host vars (backlog item (b)) -- same descriptor
        # BuildSchemeDescription already builds for SuiteCAP/GPUCcppCapPass.
        bsd = BuildSchemeDescription()
        bsd.traverse(ccpp_mod)

        # Find all suite cap modules and process their _physics subroutines,
        # plus the register/initialize/finalize/timestep_initial/
        # timestep_final lifecycle subroutines built alongside them —
        # schemes with memory_space=device args on those entry points need
        # the same data-region treatment _suite_physics already gets.
        for module_op in op.body.block.ops:
            if not isa(module_op, builtin.ModuleOp):
                continue
            # Each suite-cap module is tagged with its suite's name. Compute
            # its diverged host vars once per module, reused across every
            # lifecycle/physics function inside it.
            suite_name = suite_cap_suite_name(module_op)
            if suite_name is None:
                continue
            suite_desc = bsd.schemes.get(suite_name)
            diverged_vars = frozenset()
            diverged_capscratch_vars = frozenset()
            if suite_desc is not None:
                scheme_names = {
                    scheme.attributes["name"]
                    for group in suite_desc
                    for scheme in _iter_schemes(group)
                }
                diverged_vars = find_diverged_suite_vars(scheme_names, meta_data)
                diverged_capscratch_vars = find_diverged_capscratch_vars(scheme_names, meta_data)

            for child in module_op.body.block.ops:
                if not (isa(child, func.FuncOp) and not child.is_declaration):
                    continue
                if fn_phase(child) is not None:
                    self._process_physics_fn(
                        child, meta_data, diverged_vars, diverged_capscratch_vars
                    )
