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
    AccUpdateDeviceOp,
    AccUpdateSelfOp,
    KeywordCallOp,
    OmpTargetDataBeginOp,
    OmpTargetDataEndOp,
    OmpTargetUpdateFromOp,
    OmpTargetUpdateToOp,
)
from xdsl_ccpp.transforms.util.cap_shared import (
    FRAMEWORK_STD_NAME_TO_CAP_VAR,
    _bare,
    _iter_schemes,
    find_diverged_capscratch_vars,
    find_diverged_suite_vars,
    resolve_capscratch_cap_var_name,
    split_scheme_table_name,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    BuildMetaDataDescriptions,
    BuildSchemeDescription,
)
from xdsl_ccpp.transforms.util.ir_utils import find_ccpp_module


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
    - Host-less scratch vars always generate copyin+copyout (no 'present'
      optimisation yet).
    """

    name = "generate-gpu-data"

    # GPU directive backend: "acc" for OpenACC, "omp" for OpenMP target offload.
    directive: str = "acc"

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
        """Return a dict mapping scheme-local name → host variable name for
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
                device_args[arg.name] = host_var
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
        """Return {local_name: (category, host_var)} for every arg in this
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
            result[arg.name] = (category, host_var)
        return result

    def _get_diverged_capscratch_args(self, scheme_name, table_name, meta_data, diverged_capscratch_vars):
        """Return {local_name: (category, cap_var_name, is_direct)} for
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
            if not arg.hasAttr("standard_name"):
                continue
            std_name = arg.getAttr("standard_name")
            cap_var = resolve_capscratch_cap_var_name(std_name, arg.hasAttr("constituent"))
            if cap_var is None or cap_var not in diverged_capscratch_vars:
                continue
            scheme_space = (
                arg.getAttr("memory_space") if arg.hasAttr("memory_space") else "host"
            )
            category = "present" if scheme_space == "device" else "update"
            is_direct = std_name.lower() in FRAMEWORK_STD_NAME_TO_CAP_VAR
            result[arg.name] = (category, cap_var, is_direct)
        return result

    def _emit_present(self, ref, call_op):
        """Wrap a single call in its own present()-only data region.

        present() is a pure runtime assertion, no data movement -- emitted
        individually per touching call rather than coalesced across a run
        (unlike _emit_update below): repeating it is free, and coalescing
        it across multiple calls would risk producing improperly-nested
        (criss-crossing) !$acc data regions if another diverged var's own
        present run happens to overlap without nesting inside this one.
        """
        if self.directive == "omp":
            Rewriter.insert_op(OmpTargetDataBeginOp(alloc=[ref]), InsertPoint.before(call_op))
            Rewriter.insert_op(OmpTargetDataEndOp(), InsertPoint.after(call_op))
        else:
            Rewriter.insert_op(AccDataBeginOp(present=[ref]), InsertPoint.before(call_op))
            Rewriter.insert_op(AccDataEndOp(), InsertPoint.after(call_op))

    def _emit_update(self, ref, first_op, last_op):
        """Sync once before/after a whole run of consecutive update-only
        touches for one host var, instead of once per call."""
        if self.directive == "omp":
            Rewriter.insert_op(OmpTargetUpdateFromOp(array_refs=[ref]), InsertPoint.before(first_op))
            Rewriter.insert_op(OmpTargetUpdateToOp(array_refs=[ref]), InsertPoint.after(last_op))
        else:
            Rewriter.insert_op(AccUpdateSelfOp(array_refs=[ref]), InsertPoint.before(first_op))
            Rewriter.insert_op(AccUpdateDeviceOp(array_refs=[ref]), InsertPoint.after(last_op))

    def _process_diverged_host_vars(self, calls, meta_data, diverged_vars, arg_by_name):
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
        coalesced into one sync pair (see _emit_update).

        suite_cap.py unifies same-standard_name args from different
        schemes into a single shared function parameter, named after
        whichever scheme's own local arg name was encountered first when
        the suite cap was built (generateSchemeSubroutineCallOps) -- so a
        later-contributing scheme's own local name (e.g. "qv_b") is never
        itself a block-arg key; only the "winning" name is. Rather than
        reproduce that dedup-order logic here, resolve one canonical SSA
        reference per host var by trying every local name any contributing
        call used until one is found in arg_by_name -- since exactly one of
        them must be the real (shared) block argument, and Fortran call-by-
        reference means every call passing that host var passes the exact
        same value regardless of which local name it used to do so.
        """
        touches: dict = {}  # host_var -> ordered [(op, category, local_name), ...]
        for call_op, scheme_name, table_name in calls:
            for local_name, (category, host_var) in self._get_diverged_args(
                scheme_name, table_name, meta_data, diverged_vars
            ).items():
                touches.setdefault(host_var, []).append((call_op, category, local_name))

        resolved: dict = {}
        for host_var, touch_list in touches.items():
            ref = next(
                (arg_by_name[name] for _, _, name in touch_list if name in arg_by_name),
                None,
            )
            resolved[host_var] = (ref, [(call_op, category) for call_op, category, _ in touch_list])
        self._emit_diverged_touches(resolved)

    def _emit_diverged_touches(self, resolved_touches):
        """Shared run-coalescing core for _process_diverged_host_vars and
        _process_diverged_capscratch_vars: given {identity: (ref, ordered
        [(call_op, category), ...])} with ref already resolved by the
        caller (each caller has its own rules for picking the right SSA
        reference -- see their docstrings), split each identity's touches
        into maximal runs of consecutive equal classification (see
        _process_diverged_host_vars's docstring for why: an interleaved
        present-classified touch genuinely needs the device copy synced
        before it executes, so it breaks an update run rather than being
        absorbed into it).
        """
        for ref, touch_list in resolved_touches.values():
            if ref is None:
                continue

            update_run: list = []
            for call_op, category in touch_list:
                if category == "present":
                    self._emit_present(ref, call_op)
                    if update_run:
                        self._emit_update(ref, first_op=update_run[0], last_op=update_run[-1])
                        update_run = []
                else:  # update
                    update_run.append(call_op)
            if update_run:
                self._emit_update(ref, first_op=update_run[0], last_op=update_run[-1])

    def _process_diverged_capscratch_vars(self, calls, meta_data, diverged_capscratch_vars, arg_by_name):
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
        local name's SSA value to sync, falling back to any touch only if
        no direct one exists for this cap var.
        """
        touches: dict = {}  # cap_var_name -> ordered [(op, category, local_name, is_direct), ...]
        for call_op, scheme_name, table_name in calls:
            for local_name, (category, cap_var, is_direct) in self._get_diverged_capscratch_args(
                scheme_name, table_name, meta_data, diverged_capscratch_vars
            ).items():
                touches.setdefault(cap_var, []).append((call_op, category, local_name, is_direct))

        resolved: dict = {}
        for cap_var, touch_list in touches.items():
            ref = next(
                (
                    arg_by_name[name]
                    for _, _, name, is_direct in touch_list
                    if is_direct and name in arg_by_name
                ),
                None,
            )
            if ref is None:
                ref = next(
                    (arg_by_name[name] for _, _, name, _ in touch_list if name in arg_by_name),
                    None,
                )
            resolved[cap_var] = (
                ref, [(call_op, category) for call_op, category, _, _ in touch_list]
            )
        self._emit_diverged_touches(resolved)

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
        # Optional/allocatable args carry a __opt/__alloc suffix on their
        # block-arg name_hint (see suite_cap.py) that metadata names never
        # have -- bare both sides so a hostless optional/allocatable device
        # var isn't silently dropped.
        arg_by_name = {
            _bare(arg.name_hint): arg
            for arg in block.args
            if arg.name_hint is not None
        }

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
            all_local_vars = set()
            for _, scheme_name, table_name, device_vars in gpu_calls:
                diverged_local_names = (
                    self._get_diverged_capscratch_args(
                        scheme_name, table_name, meta_data, diverged_capscratch_vars
                    )
                    if diverged_capscratch_vars
                    else {}
                )
                for local_name, host_var in device_vars.items():
                    if host_var is None and local_name not in diverged_local_names:
                        all_local_vars.add(local_name)

            if all_local_vars:
                first_if = gpu_calls[0][0]
                last_if  = gpu_calls[-1][0]
                copyin_refs = [
                    arg_by_name[name]
                    for name in sorted(all_local_vars)
                    if name in arg_by_name
                ]
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
                        Rewriter.insert_op(
                            AccDataBeginOp(
                                copyin=copyin_refs,
                                copyout=copyin_refs,
                            ),
                            InsertPoint.before(first_if),
                        )
                        Rewriter.insert_op(
                            AccDataEndOp(),
                            InsertPoint.after(last_if),
                        )

        # --- diverged host vars: per-scheme-call routing (backlog item (b)) ---
        if diverged_vars:
            self._process_diverged_host_vars(calls, meta_data, diverged_vars, arg_by_name)

        # --- diverged CapScratch cap vars: per-scheme-call routing ---
        if diverged_capscratch_vars:
            self._process_diverged_capscratch_vars(
                calls, meta_data, diverged_capscratch_vars, arg_by_name
            )

    # Suffixes of the suite-level lifecycle subroutines built by
    # suite_cap.py (suite_name + "_suite" + generated_subroutine_posfix; see
    # ccpp_cap.py's lifecycle_specs for the matching callee_suffix values).
    # "_suite_physics" is handled separately below via substring match,
    # since per-group run callees are suffixed with the group name (e.g.
    # "_suite_physics1"), not an exact "_suite_physics" ending.
    _LIFECYCLE_SUITE_FN_SUFFIXES = (
        "_suite_register",
        "_suite_initialize",
        "_suite_finalize",
        "_suite_timestep_initial",
        "_suite_timestep_final",
    )

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
            if not (
                isa(module_op, builtin.ModuleOp)
                and module_op.sym_name is not None
                and module_op.sym_name.data.endswith("_cap")
            ):
                continue

            # Each <suite>_cap module corresponds to exactly one suite
            # (suite_cap.py names it suite_name + "_cap"). Compute its
            # diverged host vars once per module, reused across every
            # lifecycle/physics function inside it.
            suite_name = module_op.sym_name.data[: -len("_cap")]
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
                fn_name = child.sym_name.data
                if "_suite_physics" in fn_name or fn_name.endswith(
                    self._LIFECYCLE_SUITE_FN_SUFFIXES
                ):
                    self._process_physics_fn(
                        child, meta_data, diverged_vars, diverged_capscratch_vars
                    )
