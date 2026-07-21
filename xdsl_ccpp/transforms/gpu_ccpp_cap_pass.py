from dataclasses import dataclass

from xdsl.context import Context
from xdsl.dialects import builtin, func, scf
from xdsl.passes import ModulePass
from xdsl.rewriter import InsertPoint, Rewriter
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects.ccpp_utils import (
    AccDataBeginOp,
    AccDataEndOp,
    AccEnterDataOp,
    AccExitDataOp,
    AccUpdateDeviceOp,
    AccUpdateSelfOp,
    ArraySectionOp,
    HostVarRefOp,
    OmpTargetDataBeginOp,
    OmpTargetDataEndOp,
    OmpTargetEnterDataOp,
    OmpTargetExitDataOp,
    OmpTargetUpdateFromOp,
    OmpTargetUpdateToOp,
    StrCmpOp,
)
from xdsl_ccpp.transforms.util.cap_shared import _iter_schemes, split_scheme_table_name
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    BuildMetaDataDescriptions,
    BuildSchemeDescription,
)
from xdsl_ccpp.transforms.util.ir_utils import find_ccpp_module

# Canonical execution order of the six lifecycle phases a scheme's arg
# tables can belong to (see cap_shared.split_scheme_table_name). register/
# initialize/finalize each run exactly once per simulation; timestep_initial/
# run/timestep_final each run once per timestep (always at the same count).
_PHASE_ORDER = (
    "register", "initialize", "timestep_initial", "run", "timestep_final", "finalize",
)
_PHASE_RANK = {p: i for i, p in enumerate(_PHASE_ORDER)}
_ONE_TIME_PHASES = frozenset({"register", "initialize", "finalize"})
_PER_TIMESTEP_PHASES = frozenset({"timestep_initial", "run", "timestep_final"})

# *_ccpp_physics_run is handled separately in apply() (substring match, not
# suffix) since its dispatch shape -- an outer per-suite IfOp wrapping a
# second, nested per-suite-part IfOp -- differs from these single-level
# dispatchers, so it isn't in this map.
_LIFECYCLE_FN_SUFFIX_TO_PHASE = {
    "_ccpp_physics_register": "register",
    "_ccpp_physics_initialize": "initialize",
    "_ccpp_physics_finalize": "finalize",
    "_ccpp_physics_timestep_initial": "timestep_initial",
    "_ccpp_physics_timestep_final": "timestep_final",
}


@dataclass(frozen=True)
class VarLifetime:
    """Resolved device-residency plan for one host variable within one suite.

    kind: "present" | "update" | "copyin" | "copy" | "copyout" -- the same
        clause vocabulary this pass has always used, now resolved per suite
        instead of globally across every suite in the module.
    phases_used: every lifecycle phase this variable is referenced in by any
        scheme belonging to this suite.
    entry_phase / exit_phase: where to insert the hoisted directive pair --
        AccEnterDataOp/AccExitDataOp for copyin/copy/copyout, or
        AccUpdateSelfOp/AccUpdateDeviceOp (fired once instead of per-call)
        for "update". Both None when hoisted is False.
    hoisted: True iff this variable should get the hoisted, once-per-suite
        treatment instead of the legacy per-call one. False for "present"
        variables (present() is a pure runtime assertion with no data
        movement to eliminate, and CCPP doesn't own a present-clause
        variable's residency -- the host model does -- so this is a
        permanent exclusion, not a phase-count one) and for variables used
        in only one phase (hoisting them would gain nothing and only adds
        unstructured pairing-correctness risk) -- both stay on the legacy
        per-call path, unchanged from before this feature. "update"
        variables are no longer permanently excluded (see _resolve_lifetime
        and _wrap_scheme_call) -- hoisting them assumes nothing outside this
        suite's own dispatch (e.g. the host model's own GPU-resident driver
        code) touches the variable's device copy between this suite's
        calls; see this pass's class docstring for that assumption.
    """

    kind: str
    phases_used: frozenset
    entry_phase: "str | None"
    exit_phase: "str | None"
    hoisted: bool


@dataclass(frozen=True)
class GPUCcppCapPass(ModulePass):
    """Insert OpenACC data directives at the ccpp_cap level.

    Runs after generate-ccpp-cap, generate-cpp-cap, and generate-host-match
    (see ccpp_dsl.py's _build_pipeline for the exact ordering). For
    *_ccpp_physics_run, wraps the suite-part dispatch (inner scf.IfOp) with
    an !$acc data region using host model variable names. For each of the
    lifecycle dispatchers (*_ccpp_physics_register/_initialize/_finalize/
    _timestep_initial/_timestep_final), wraps the suite callee call inside
    each suite-name scf.IfOp the same way.

    The OpenACC clause is chosen by comparing the scheme's declared memory
    space against the host model variable's declared memory space
    (propagated as model_var_memory_space by generate-host-match):

        scheme=device + model=device  -> present(var)
            Both sides agree the variable lives on the GPU. The host model
            is responsible for managing the device copy independently of
            this framework -- never hoisted (see below).

        scheme=device + model=host    -> copyin/copy/copyout(var)
            Scheme wants GPU data but model keeps it on CPU. The framework
            creates the device copy itself. This is the case cross-function
            hoisting applies to.

        scheme=host   + model=device  -> !$acc update self(var) before call,
                                         !$acc update device(var) after call
            Scheme is CPU-only but model keeps data on GPU. Hoisted the same
            way as copyin/copy/copyout (see below) -- fired once at the
            variable's computed entry/exit phase instead of on every call.

        scheme=host   + model=host    -> no directive (CPU path, default)

    Cross-function data hoisting (both ACC and OMP backends -- see directive
    below): for copyin/copy/copyout and update variables, instead of independently
    transferring/syncing the variable on every dispatcher call that touches
    it, this pass computes the actual earliest and latest lifecycle phase
    (of the six above) the variable is used in, within THIS suite
    specifically (not globally across every suite dispatched from the same
    module -- see _analyze_suite_var_lifetimes), and emits a single pair of
    directives spanning that range instead: unstructured `!$acc enter
    data`/`exit data` for copyin/copy/copyout, or a single `!$acc update
    self`/`update device` pair for update:

      - If `register` or `initialize` reference the variable, it gets
        whole-simulation scope: entry at the earliest of {register,
        initialize} actually used, exit always at `finalize` (the only
        phase guaranteed to run exactly once after every timestep, so the
        only safe exit anchor once entry is forced out of the
        once-per-timestep group -- register/initialize/finalize and
        timestep_initial/run/timestep_final are never mixed as an
        entry/exit pair, since enter_data/exit_data reference-counting
        requires both ends to run the same number of times; the same
        constraint is applied to the update self/device pair for
        consistency, even though it isn't itself reference-counted). This
        covers every phase the variable could be used in, `finalize`
        included, since `finalize` is always the exit.
      - Otherwise, entry/exit are the actual earliest/latest of
        {timestep_initial, run, timestep_final} the variable is used in
        (`finalize`-only usage, with no register/initialize usage either,
        can't anchor entry on its own -- see _resolve_lifetime -- so it
        falls to this per-timestep rule too). If entry == exit (used in at
        most one of the three), hoisting gains nothing, and the variable
        stays on the legacy path (VarLifetime.hoisted = False) for every
        phase it's used in. If the variable is *also* referenced at
        `finalize` on top of a genuine per-timestep span, that finalize
        touch falls outside the hoisted range (finalize can't be reached by
        stretching a per-timestep exit to cover it -- see the
        reference-counting note above) and stays on the legacy per-call
        path independently, while the per-timestep span is still hoisted
        (_role_at's "unused" role, folded into "legacy" by
        _wrap_scheme_call).

    Any phase strictly between entry and exit gets a plain present() clause
    for copyin/copy/copyout variables (pure runtime assertion, no data
    movement, safe to repeat) instead of re-transferring; update variables
    get nothing at all at those phases (no assertion applies -- the
    variable's host-side copy is simply assumed current between the entry
    and exit sync points; see the "update" hoisting assumption below).

    Hoisting an "update" variable assumes nothing outside this suite's own
    dispatch touches the variable's device copy between its entry and exit
    phase -- in particular, that no GPU-resident code the host model runs
    independently of CCPP (e.g. its own dynamics core) reads or writes that
    variable's device copy in between. This assumption is required because,
    unlike copyin/copy/copyout variables (pure CCPP-owned scratch device
    memory, invisible to anything outside this framework), the device
    allocation for an update variable is owned by the host model, not by
    CCPP -- so CCPP cannot itself verify the assumption holds. It is
    currently untested in practice: no example in this repo declares a host
    variable memory_space=device, so this path has zero real exercise today
    beyond its unit tests. Flagged as a real, accepted risk rather than
    deferred -- see ccpp_cap_refactor_plan.md's GPU/OpenACC backlog entry.

    Naming note: 'model_var_name' refers to the host MODEL variable name,
    not a CPU-memory variable. 'host'/'device' in memory_space follow
    OpenACC conventions (CPU vs GPU).

    Pipeline position: generate-ccpp-cap -> generate-gpu-ccpp-cap -> generate-kinds
    """

    name = "generate-gpu-ccpp-cap"

    # GPU directive backend: "acc" for OpenACC, "omp" for OpenMP target offload.
    # Usage: generate-gpu-ccpp-cap            (default: OpenACC)
    #        generate-gpu-ccpp-cap{directive=omp}  (OpenMP target)
    #
    # Cross-function hoisting applies to both backends -- OMP uses
    # OmpTargetEnterDataOp/OmpTargetExitDataOp (map(to:)/map(alloc:) and
    # map(from:)/map(release:)) and OmpTargetUpdateFromOp/OmpTargetUpdateToOp
    # where ACC uses AccEnterDataOp/AccExitDataOp and
    # AccUpdateSelfOp/AccUpdateDeviceOp. See _role_at/_wrap_scheme_call.
    directive: str = "acc"

    # ---- Analysis: per-suite variable lifetimes -----------------------------

    def _analyze_suite_var_lifetimes(self, ccpp_mod):
        """Return {suite_name: {host_var_name: VarLifetime}}.

        Scoped per suite (via BuildSchemeDescription's suite -> scheme
        membership, the same descriptor SuiteCAP itself already builds and
        leaves in the IR) rather than globally across every suite dispatched
        from the same module -- a real module can dispatch multiple suites
        (e.g. examples/capgen generates one cap module for both ddt_suite and
        temp_suite), and a variable's classification in one suite must not be
        influenced by an unrelated suite's usage of a same-named host var.
        """
        bmdd = BuildMetaDataDescriptions()
        bmdd.traverse(ccpp_mod)
        bsd = BuildSchemeDescription()
        bsd.traverse(ccpp_mod)

        result = {}
        for suite_name, suite_desc in bsd.schemes.items():
            scheme_names = {
                scheme.attributes["name"]
                for group in suite_desc
                for scheme in _iter_schemes(group)
            }
            result[suite_name] = self._analyze_one_suite(scheme_names, bmdd.meta_data)
        return result

    def _analyze_one_suite(self, scheme_names, meta_data):
        """Same union math _build_model_var_clause_map (this pass's
        predecessor) always used -- any read/write across every scheme
        entry point that references a host var, per host var -- restricted
        to scheme_names, and additionally tracking which lifecycle phase
        each reference belongs to.

        Also tracks, per host var, which scheme(s) contributed to each of
        the three top-level classification categories (present / update /
        copy-family), so genuine cross-scheme disagreement about a host
        var's residency treatment (e.g. one scheme wants present(), another
        wants update self/device, for the same var in the same suite) can be
        detected and reported instead of silently resolved by whichever of
        the three fixed-order lifetimes-construction loops below happens to
        run last for that var.
        """
        needs_in: dict = {}   # host_var -> bool
        needs_out: dict = {}  # host_var -> bool
        present_vars: set = set()
        update_vars: set = set()
        phases_used: dict = {}  # host_var -> set[phase]
        # host_var -> category -> set of contributing scheme names, where
        # category is one of "present", "update", "copy" -- used purely for
        # conflict detection/reporting, never for classification itself.
        contributors: dict = {}

        for scheme_name in scheme_names:
            props = meta_data.get(scheme_name)
            if props is None:
                continue
            for table_name, table in props.arg_tables.items():
                split = split_scheme_table_name(table_name)
                if split is None:
                    continue
                _, phase = split
                for arg in table.getFunctionArguments():
                    if not arg.hasAttr("model_var_name"):
                        continue

                    host_var = arg.getAttr("model_var_name")
                    scheme_space = (
                        arg.getAttr("memory_space")
                        if arg.hasAttr("memory_space")
                        else "host"
                    )
                    model_space = (
                        arg.getAttr("model_var_memory_space")
                        if arg.hasAttr("model_var_memory_space")
                        else "host"
                    )

                    if scheme_space == "device" and model_space == "device":
                        present_vars.add(host_var)
                        contributors.setdefault(host_var, {}).setdefault(
                            "present", set()
                        ).add(scheme_name)
                    elif scheme_space == "device" and model_space == "host":
                        intent = arg.getAttr("intent") if arg.hasAttr("intent") else "inout"
                        reads  = intent in ("in",  "inout")
                        writes = intent in ("out", "inout")
                        needs_in[host_var]  = needs_in.get(host_var,  False) or reads
                        needs_out[host_var] = needs_out.get(host_var, False) or writes
                        phases_used.setdefault(host_var, set()).add(phase)
                        contributors.setdefault(host_var, {}).setdefault(
                            "copy", set()
                        ).add(scheme_name)
                    elif scheme_space == "host" and model_space == "device":
                        update_vars.add(host_var)
                        phases_used.setdefault(host_var, set()).add(phase)
                        contributors.setdefault(host_var, {}).setdefault(
                            "update", set()
                        ).add(scheme_name)
                    # else: both host -- no directive needed

        self._check_no_clause_conflicts(contributors)

        lifetimes = {}
        for host_var in present_vars:
            lifetimes[host_var] = VarLifetime("present", frozenset(), None, None, False)
        for host_var in update_vars:
            lifetimes[host_var] = self._resolve_lifetime("update", phases_used.get(host_var, set()))
        for host_var, r in needs_in.items():
            w = needs_out.get(host_var, False)
            if r and w:
                kind = "copy"
            elif r:
                kind = "copyin"
            else:
                kind = "copyout"
            lifetimes[host_var] = self._resolve_lifetime(kind, phases_used.get(host_var, set()))
        return lifetimes

    @staticmethod
    def _check_no_clause_conflicts(contributors) -> None:
        """Raise if any host var was classified into more than one of the
        present/update/copy-family categories within the same suite (either
        across different schemes or across entry points) -- e.g. one scheme declares memory_space=device
        while the host is also device-resident (present), while another
        scheme in the same suite leaves memory_space unset for the same
        host var against the same device-resident host (update). Today's
        per-scheme-call granularity has no way to satisfy both schemes at
        once (backlog item (b)), so this is a hard configuration error, not
        a warning -- silently picking one and discarding the other (this
        pass's prior behavior) can emit a `present()` assertion the
        surrounding code never actually established, or vice versa.
        """
        for host_var, by_category in contributors.items():
            if len(by_category) <= 1:
                continue
            detail = ", ".join(
                f"{category} (from {', '.join(sorted(schemes))})"
                for category, schemes in sorted(by_category.items())
            )
            raise ValueError(
                f"Host variable '{host_var}' has conflicting GPU residency requirements "
                f"within the same suite: {detail}. Per-scheme-call clause routing is "
                f"not yet supported (see GPU/OpenACC backlog item (b) in "
                f"ccpp_cap_refactor_plan.md) -- give all involved scheme entry points "
                f"consistent memory_space declarations for '{host_var}'."
            )

    def _resolve_lifetime(self, kind, used) -> VarLifetime:
        """Apply the whole-sim vs per-timestep entry/exit anchor rules
        described in this pass's docstring to one host var's phase usage."""
        used = frozenset(used)
        one_time = used & _ONE_TIME_PHASES
        if one_time:
            # Whole-sim scope. Entry is the earliest of register/initialize
            # actually used -- never hardcoded to initialize, since a
            # variable whose only one-time-group usage is register would be
            # wrong to enter at initialize (register runs first). Exit is
            # always finalize (see class docstring for why).
            candidates = one_time - {"finalize"}
            if candidates:
                entry = min(candidates, key=_PHASE_RANK.__getitem__)
                return VarLifetime(kind, used, entry, "finalize", True)
            # Only finalize itself is used among the one-time phases (no
            # register/initialize usage) -- finalize can't anchor entry on
            # its own (that would make entry == exit, spanning nothing), so
            # whole-sim scope doesn't apply here. Fall through to check
            # whether the per-timestep phases alone still justify hoisting;
            # if they do, finalize remains a separate touch outside the
            # hoisted range, always on the legacy per-call path (_role_at
            # returns "unused" for it, which _wrap_scheme_call treats the
            # same as "legacy" -- see its classification loop).

        per_ts = used & _PER_TIMESTEP_PHASES
        if len(per_ts) <= 1:
            # Degenerate: used in at most one of timestep_initial/run/
            # timestep_final, and (if reached via the finalize-only
            # fallthrough above) nowhere else either -- no hoisting benefit,
            # stay on the legacy path for every phase used.
            return VarLifetime(kind, used, None, None, False)
        entry = min(per_ts, key=_PHASE_RANK.__getitem__)
        exit_ = max(per_ts, key=_PHASE_RANK.__getitem__)
        return VarLifetime(kind, used, entry, exit_, True)

    def _role_at(self, lifetime: VarLifetime, phase: str) -> str:
        """Classify one host var's role at one call site's phase.

        Returns "legacy" (present variables, always; degenerate/single-phase
        copyin/copy/copyout/update variables -- unchanged per-call
        AccDataBeginOp/AccDataEndOp or AccUpdateSelfOp/AccUpdateDeviceOp
        path), "enter", "exit", "passthrough" (copyin/copy/copyout only --
        present-only, no data movement, safe to repeat every phase strictly
        between entry and exit; hoisted "update" variables get nothing at
        the equivalent phases -- see _wrap_scheme_call), or "unused".

        "unused" arises specifically for a variable hoisted per-timestep
        (entry/exit within timestep_initial/run/timestep_final) that is
        *also* referenced at `finalize` -- finalize can't anchor whole-sim
        scope on its own (see _resolve_lifetime), so it's left outside the
        hoisted range entirely. _wrap_scheme_call treats "unused" exactly
        like "legacy": a full per-call transfer at that one phase,
        independent of the hoisted span elsewhere. This can only ever be
        `finalize` falling after a per-timestep exit, never a phase falling
        before an entry -- finalize is always last in canonical phase
        order, and whole-sim-scoped lifetimes (entry in
        {register, initialize}) already cover every phase up to their
        `finalize` exit via "enter"/"passthrough"/"exit", leaving no gap.
        """
        if not lifetime.hoisted:
            return "legacy"
        if phase == lifetime.entry_phase:
            return "enter"
        if phase == lifetime.exit_phase:
            return "exit"
        if _PHASE_RANK[lifetime.entry_phase] < _PHASE_RANK[phase] < _PHASE_RANK[lifetime.exit_phase]:
            return "passthrough"
        return "unused"

    # ---- Discovery: find every per-suite dispatch call site -----------------

    def _suite_name_of(self, if_op):
        """Recover the suite name a per-suite scf.IfOp dispatches on, from its
        StrCmpOp condition (StrCmpOp(trim_suite_name.res, literal=suite_name),
        built by run_dispatch.py/lifecycle_cap.py for every per-suite
        branch). None if the condition isn't a literal-mode StrCmpOp --
        unexpected shape, fail safe rather than crash.
        """
        owner = if_op.cond.owner
        if isa(owner, StrCmpOp) and owner.literal is not None:
            return owner.literal.data
        return None

    def _find_inner_suite_part_if(self, true_block):
        """Find the scf.IfOp in true_block whose true region contains a
        *_suite_physics func.CallOp.  Returns (if_op, call_op) or (None, None).
        """
        for op in true_block.ops:
            if not isa(op, scf.IfOp):
                continue
            if not op.true_region.blocks:
                continue
            for inner_op in op.true_region.blocks[0].ops:
                if (
                    isa(inner_op, func.CallOp)
                    and "_suite_physics" in inner_op.callee.root_reference.data
                ):
                    return op, inner_op
        return None, None

    def _collect_run_call_sites(self, fn_op):
        """Yield (suite_name, "run", true_block, suite_call) for every
        per-suite branch of a *_ccpp_physics_run dispatcher."""
        if not fn_op.body.blocks:
            return
        for op in fn_op.body.blocks[0].ops:
            if not isa(op, scf.IfOp) or not op.true_region.blocks:
                continue
            suite_name = self._suite_name_of(op)
            if suite_name is None:
                continue
            true_block = op.true_region.blocks[0]
            inner_if, suite_call = self._find_inner_suite_part_if(true_block)
            if inner_if is None:
                continue
            yield suite_name, "run", true_block, suite_call

    def _collect_lifecycle_call_sites(self, fn_op, phase):
        """Yield (suite_name, phase, true_block, suite_call) for every
        per-suite branch of a lifecycle dispatcher (register/initialize/
        finalize/timestep_initial/timestep_final), built by lifecycle_cap.py's
        _generate_lifecycle_fn -- one level of scf.IfOp per suite name, with
        the suite lifecycle callee called directly in its true region.
        """
        if not fn_op.body.blocks:
            return
        for op in fn_op.body.blocks[0].ops:
            if not isa(op, scf.IfOp) or not op.true_region.blocks:
                continue
            suite_name = self._suite_name_of(op)
            if suite_name is None:
                continue
            true_block = op.true_region.blocks[0]
            suite_call = None
            for inner_op in true_block.ops:
                if isa(inner_op, func.CallOp):
                    suite_call = inner_op
                    break
            if suite_call is None:
                continue
            yield suite_name, phase, true_block, suite_call

    def _resolve_array_refs(self, true_block, var_names, use_sections=True):
        """For each variable name in var_names, return the best SSA value to
        use in a data/update directive -- preferring the ArraySectionOp result
        (which carries the full section expression) over the bare HostVarRefOp
        result (which carries only the base variable name).

        For a 2D host array temp_midpoints(horizontal_dimension, vertical_layer_dimension),
        ccpp_cap.py generates:
            HostVarRefOp(temp_midpoints)  → %ref
            ArraySectionOp(%ref, col_start, col_end, 1, pver) → %section

        Passing %section to AccUpdateSelfOp causes the printer to emit:
            !$acc update self(temp_midpoints(col_start:col_end, 1:pver))

        Passing %ref would only emit:
            !$acc update self(temp_midpoints)

        For scalar variables with no ArraySectionOp, %ref is used directly.
        Hoisted enter/exit/passthrough references -- including hoisted
        "update" variables' single update self/device pair -- always use
        use_sections=False (called that way by _wrap_scheme_call).
        ArraySectionOp operands (e.g. col_start/col_end) are themselves
        function-scoped and can't be reused for a synthesized reference
        cloned into a different function's block, so hoisted transfers move
        the whole declared array rather than a per-call column subrange.
        """
        # Build map: HostVarRefOp.res → ArraySectionOp.res (if one exists)
        section_for_ref = {}
        if use_sections:
            for op in true_block.ops:
                if isa(op, ArraySectionOp):
                    section_for_ref[op.source] = op.res

        # For each variable, find its HostVarRefOp and resolve to the best SSA value
        refs = []
        for op in true_block.ops:
            if not isa(op, HostVarRefOp):
                continue
            if op.var_name.data not in var_names:
                continue
            # use_sections=True: prefer array section (efficiency for copyin/copyout/update)
            # use_sections=False: use bare ref (correct semantics for present/hoisted)
            best = section_for_ref.get(op.res, op.res)
            refs.append(best)
        return refs

    def _collect_donor_host_var_refs(self, top_module):
        """One-time module-wide scan: host var name -> (module_name, result
        type, member_name) for the first HostVarRefOp found anywhere.

        Used by _synthesize_ref to clone a reference into a phase's block
        where a hoisted variable has no natural scheme-arg reference -- the
        forced whole-sim entry/exit case, e.g. exit forced to 'finalize' for
        a variable finalize's own schemes never touch. SSA values can't cross
        function boundaries, so a fresh HostVarRefOp must be built; no new
        module-scope 'use' stub is needed since one already exists (the
        variable is referenced elsewhere in the same _ccpp_cap module by
        construction -- that's exactly why it's in phases_used at all).
        """
        donors = {}
        for op in top_module.walk():
            if isa(op, HostVarRefOp) and op.var_name.data not in donors:
                member = op.attributes.get("member_name")
                donors[op.var_name.data] = (
                    op.module_name,
                    op.res.type,
                    member.data if member is not None else None,
                )
        return donors

    def _synthesize_ref(self, true_block, var_name, donor_refs):
        """Clone a fresh HostVarRefOp for var_name into true_block, using a
        donor (module_name, type, member_name) triple found elsewhere in the
        module. Returns the new op's result, or None if no donor exists
        (shouldn't happen in practice -- would mean the variable was never
        referenced anywhere, contradicting it being in phases_used).
        """
        donor = donor_refs.get(var_name)
        if donor is None:
            return None
        module_name, res_type, member_name = donor
        new_ref = HostVarRefOp(var_name, module_name, res_type, member_name=member_name)
        Rewriter.insert_op(new_ref, InsertPoint.at_start(true_block))
        return new_ref.res

    def _wrap_scheme_call(self, true_block, suite_call, lifetimes, phase, donor_refs):
        """Classify every host var referenced in true_block (plus any
        hoisted var whose forced entry/exit anchor is this phase but has no
        natural reference here) by role, and insert the resulting
        enter-data/present-or-legacy-data/exit-data/update directives around
        suite_call.

        Insertion order when multiple roles co-occur at one call site:
        AccEnterDataOp (before) -> AccDataBeginOp (before, present/legacy
        vars) -> suite_call -> AccDataEndOp (after) -> AccExitDataOp (after).
        Hoisted "update" variables (kind == "update", hoisted == True) fire
        a single AccUpdateSelfOp/AccUpdateDeviceOp pair anchored the same way
        as AccEnterDataOp/AccExitDataOp (outside the structured data region,
        falling back to suite_call when no structured region exists at this
        call site) instead of the legacy per-call pair, which stays anchored
        directly to suite_call (innermost, unaffected). All of the above are
        legal to sequence this way since enter/exit-data and update self/
        device are unstructured (no scoping requirement relative to the
        structured data region or to each other -- they touch disjoint
        variables, since a variable's kind is mutually exclusive).
        """
        legacy_present, legacy_copyin, legacy_copy, legacy_copyout = [], [], [], []
        update_vars = []
        enter_copyin, enter_create = [], []
        exit_copyout, exit_delete = [], []
        update_enter_vars, update_exit_vars = [], []
        passthrough_present = []

        seen_here = set()
        for ref_op in true_block.ops:
            if not isa(ref_op, HostVarRefOp):
                continue
            var_name = ref_op.var_name.data
            lt = lifetimes.get(var_name)
            if lt is None:
                continue
            seen_here.add(var_name)
            role = self._role_at(lt, phase)
            if role in ("legacy", "unused"):
                # "unused" is a hoisted variable's independent finalize
                # touch falling outside its per-timestep entry/exit range
                # (see _role_at) -- treated identically to "legacy": a full
                # per-call transfer at this one phase only.
                if lt.kind == "present":
                    legacy_present.append(var_name)
                elif lt.kind == "update":
                    update_vars.append(var_name)
                elif lt.kind == "copyin":
                    legacy_copyin.append(var_name)
                elif lt.kind == "copy":
                    legacy_copy.append(var_name)
                elif lt.kind == "copyout":
                    legacy_copyout.append(var_name)
            elif role == "enter":
                if lt.kind == "update":
                    update_enter_vars.append(var_name)
                else:
                    (enter_copyin if lt.kind in ("copyin", "copy") else enter_create).append(var_name)
            elif role == "exit":
                if lt.kind == "update":
                    update_exit_vars.append(var_name)
                else:
                    (exit_copyout if lt.kind in ("copyout", "copy") else exit_delete).append(var_name)
            elif role == "passthrough":
                # Hoisted "update" variables get nothing at passthrough
                # phases -- no data movement or assertion applies (unlike
                # present(), there's no runtime check for "this host-side
                # copy is still current"), so this phase's call just uses
                # whatever the entry-phase update self left in host memory.
                if lt.kind != "update":
                    passthrough_present.append(var_name)
            # "unused" is folded into the "legacy" branch above -- see
            # _role_at's docstring for when it arises (a per-timestep-hoisted
            # variable's independent finalize touch).

        # Forced anchors with no natural HostVarRefOp at this phase.
        for var_name, lt in lifetimes.items():
            if not lt.hoisted or var_name in seen_here:
                continue
            if phase == lt.entry_phase:
                if self._synthesize_ref(true_block, var_name, donor_refs) is not None:
                    if lt.kind == "update":
                        update_enter_vars.append(var_name)
                    else:
                        (enter_copyin if lt.kind in ("copyin", "copy") else enter_create).append(var_name)
            elif phase == lt.exit_phase:
                if self._synthesize_ref(true_block, var_name, donor_refs) is not None:
                    if lt.kind == "update":
                        update_exit_vars.append(var_name)
                    else:
                        (exit_copyout if lt.kind in ("copyout", "copy") else exit_delete).append(var_name)

        # Data region directives go inside the inner scf.IfOp's true
        # region, immediately around the suite physics call.  This way the
        # acc/omp data region only opens once the suite-part comparison is
        # already known to be true — no wasted data movement on the wrong
        # suite part.
        # copy/copyin/copyout/tofrom: use array sections for efficiency.
        # present / alloc: use base variable names — the host put the
        #   whole array on device, not just the active columns.
        # data_begin_op/data_end_op are captured so the enter-data/exit-data
        # insertions below can anchor to them explicitly. InsertPoint.before/
        # after(suite_call) always targets suite_call itself regardless of
        # what's already been inserted around it, so anchoring every tier
        # directly to suite_call would let whichever tier's insertion code
        # runs last win the position closest to suite_call -- interleaving
        # AccEnterDataOp/AccExitDataOp inside the structured region instead
        # of outside it. Anchoring to the actual ops enforces the nesting
        # documented above regardless of insertion order.
        data_begin_op = None
        data_end_op = None
        present_names = legacy_present + passthrough_present
        if present_names or legacy_copy or legacy_copyin or legacy_copyout:
            copy_refs    = self._resolve_array_refs(true_block, set(legacy_copy),    use_sections=True)
            copyin_refs  = self._resolve_array_refs(true_block, set(legacy_copyin),  use_sections=True)
            copyout_refs = self._resolve_array_refs(true_block, set(legacy_copyout), use_sections=True)
            base_refs    = self._resolve_array_refs(true_block, set(present_names),  use_sections=False)
            if self.directive == "omp":
                # OMP uses map(tofrom:) for copy and map(to:) for copyin,
                # map(from:) for copyout; map(alloc:) for present.
                data_begin_op = OmpTargetDataBeginOp(
                    tofrom=copy_refs + copyin_refs + copyout_refs,
                    alloc=base_refs,
                )
                data_end_op = OmpTargetDataEndOp()
            else:  # acc (default)
                data_begin_op = AccDataBeginOp(
                    copy=copy_refs,
                    copyin=copyin_refs,
                    copyout=copyout_refs,
                    present=base_refs,
                )
                data_end_op = AccDataEndOp()
            Rewriter.insert_op(data_begin_op, InsertPoint.before(suite_call))
            Rewriter.insert_op(data_end_op, InsertPoint.after(suite_call))

        # Shared by AccEnterDataOp/AccExitDataOp and the hoisted update
        # self/device pair below -- both tiers sit outside the structured
        # data region (or directly at suite_call when no structured region
        # was emitted at this call site), for the same anchoring reason as
        # data_begin_op/data_end_op above.
        enter_anchor = (
            InsertPoint.before(data_begin_op)
            if data_begin_op is not None
            else InsertPoint.before(suite_call)
        )
        exit_anchor = (
            InsertPoint.after(data_end_op)
            if data_end_op is not None
            else InsertPoint.after(suite_call)
        )

        if enter_copyin or enter_create:
            enter_copyin_refs = self._resolve_array_refs(true_block, set(enter_copyin), use_sections=False)
            enter_create_refs = self._resolve_array_refs(true_block, set(enter_create), use_sections=False)
            if self.directive == "omp":
                # OMP's map(to:...) is the enter-data equivalent of ACC's
                # copyin(...); map(alloc:...) of create(...).
                enter_op = OmpTargetEnterDataOp(to=enter_copyin_refs, alloc=enter_create_refs)
            else:  # acc (default)
                enter_op = AccEnterDataOp(copyin=enter_copyin_refs, create=enter_create_refs)
            Rewriter.insert_op(enter_op, enter_anchor)

        if exit_copyout or exit_delete:
            exit_copyout_refs = self._resolve_array_refs(true_block, set(exit_copyout), use_sections=False)
            exit_delete_refs  = self._resolve_array_refs(true_block, set(exit_delete),  use_sections=False)
            if self.directive == "omp":
                # OMP's map(from:...) is the exit-data equivalent of ACC's
                # copyout(...); map(release:...) of delete(...).
                exit_op = OmpTargetExitDataOp(from_=exit_copyout_refs, release=exit_delete_refs)
            else:  # acc (default)
                exit_op = AccExitDataOp(copyout=exit_copyout_refs, delete=exit_delete_refs)
            Rewriter.insert_op(exit_op, exit_anchor)

        # Hoisted "update" variables: a single sync pair per suite instead
        # of one per touching call site.
        if update_enter_vars:
            update_enter_refs = self._resolve_array_refs(true_block, update_enter_vars, use_sections=False)
            if self.directive == "omp":
                Rewriter.insert_op(OmpTargetUpdateFromOp(array_refs=update_enter_refs), enter_anchor)
            else:  # acc (default)
                Rewriter.insert_op(AccUpdateSelfOp(array_refs=update_enter_refs), enter_anchor)

        if update_exit_vars:
            update_exit_refs = self._resolve_array_refs(true_block, update_exit_vars, use_sections=False)
            if self.directive == "omp":
                Rewriter.insert_op(OmpTargetUpdateToOp(array_refs=update_exit_refs), exit_anchor)
            else:  # acc (default)
                Rewriter.insert_op(AccUpdateDeviceOp(array_refs=update_exit_refs), exit_anchor)

        # Update directives go inside the inner scf.IfOp's true region,
        # bracketing the actual suite physics call. This is the legacy
        # per-call path for degenerate/single-phase "update" variables --
        # still driven purely off lt.kind == "update", same as before this
        # feature existed.
        if update_vars and suite_call is not None:
            update_refs = self._resolve_array_refs(
                true_block, update_vars
            )
            if self.directive == "omp":
                Rewriter.insert_op(
                    OmpTargetUpdateFromOp(array_refs=update_refs),
                    InsertPoint.before(suite_call),
                )
                Rewriter.insert_op(
                    OmpTargetUpdateToOp(array_refs=update_refs),
                    InsertPoint.after(suite_call),
                )
            else:  # acc (default)
                Rewriter.insert_op(
                    AccUpdateSelfOp(array_refs=update_refs),
                    InsertPoint.before(suite_call),
                )
                Rewriter.insert_op(
                    AccUpdateDeviceOp(array_refs=update_refs),
                    InsertPoint.after(suite_call),
                )

    def apply(self, ctx: Context, op: builtin.ModuleOp) -> None:
        ccpp_mod = find_ccpp_module(op.body.block.ops)
        if ccpp_mod is None:
            return

        suite_lifetimes = self._analyze_suite_var_lifetimes(ccpp_mod)
        if not any(suite_lifetimes.values()):
            return

        donor_refs = self._collect_donor_host_var_refs(op)

        call_sites = []
        for module_op in op.body.block.ops:
            if not (
                isa(module_op, builtin.ModuleOp)
                and module_op.sym_name is not None
                and module_op.sym_name.data.endswith("_ccpp_cap")
            ):
                continue
            for child in module_op.body.block.ops:
                if not (isa(child, func.FuncOp) and not child.is_declaration):
                    continue
                fn_name = child.sym_name.data
                if "_ccpp_physics_run" in fn_name:
                    call_sites.extend(self._collect_run_call_sites(child))
                else:
                    phase = next(
                        (p for suf, p in _LIFECYCLE_FN_SUFFIX_TO_PHASE.items()
                         if fn_name.endswith(suf)),
                        None,
                    )
                    if phase is not None:
                        call_sites.extend(self._collect_lifecycle_call_sites(child, phase))

        for suite_name, phase, true_block, suite_call in call_sites:
            lifetimes = suite_lifetimes.get(suite_name)
            if not lifetimes:
                continue
            self._wrap_scheme_call(true_block, suite_call, lifetimes, phase, donor_refs)
