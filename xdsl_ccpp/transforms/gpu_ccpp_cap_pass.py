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
from xdsl_ccpp.transforms.util.cap_shared import (
    SUITE_FN_INFIX,
    _build_ddt_resolution_maps,
    _build_host_var_map,
    _iter_schemes,
    _resolve_host_var_key,
    directive_op,
    find_diverged_suite_vars,
    split_scheme_table_name,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    BuildMetaDataDescriptions,
    BuildSchemeDescription,
)
from xdsl_ccpp.transforms.util.ir_utils import find_ccpp_module

# Canonical execution order of the eight lifecycle phases a scheme's arg
# tables can belong to (see cap_shared.split_scheme_table_name). register/
# initialize/finalize each run exactly once per simulation; timestep_initial/
# run/timestep_final each run once per timestep (always at the same count).
# physics_initial/physics_final also run exactly once per
# simulation -- like register/initialize/finalize, NOT once per timestep --
# they just happen to have the same two-level, per-group dispatch SHAPE as
# run/timestep_initial/timestep_final (see _TWO_LEVEL_DISPATCH_PHASES),
# bracketing the whole timestep loop rather than running inside it (matching
# real capgen-v1's own ccpp_physics_init/ccpp_physics_final, and this
# codebase's own driver convention: physics_init right after ccpp_init/
# before the timestep loop, physics_final right after the loop/before
# ccpp_final).
_PHASE_ORDER = (
    "register", "initialize", "physics_initial", "timestep_initial", "run",
    "timestep_final", "physics_final", "finalize",
)
_PHASE_RANK = {p: i for i, p in enumerate(_PHASE_ORDER)}
_ONE_TIME_PHASES = frozenset({"register", "initialize", "physics_initial", "physics_final", "finalize"})
_PER_TIMESTEP_PHASES = frozenset({"timestep_initial", "run", "timestep_final"})

# ccpp_physics_run, ccpp_physics_timestep_init, ccpp_physics_timestep_final,
# ccpp_physics_init, and ccpp_physics_final are handled separately in
# apply() (substring match, not suffix, via _TWO_LEVEL_DISPATCH_PHASES)
# since their dispatch shape -- an outer per-suite IfOp wrapping a second,
# nested per-suite-part/group IfOp -- differs from these single-level
# dispatchers, so none of the five are in this map.
# ccpp_physics_timestep_init and ccpp_physics_timestep_final moved from
# flat, single-level dispatchers (matching this map's own shape) to the
# same two-level, per-group shape ccpp_physics_run already had;
# ccpp_physics_init/ccpp_physics_final were then added as net-new
# entries with that same shape (NOT a move -- ccpp_init/ccpp_final below
# are unchanged, still flat, still exist; see suite_cap.py's
# emit_scheme_calls for why they no longer emit scheme calls themselves).
# Names are bare (capgen-v1-style generic subroutine names, no host
# prefix, per the vocabulary-resolution redesign) -- matched with
# endswith rather than == purely for defensive robustness against a
# future prefix, not because one exists today.
_LIFECYCLE_FN_SUFFIX_TO_PHASE = {
    "ccpp_register": "register",
    "ccpp_init": "initialize",
    "ccpp_final": "finalize",
}

# fn-name substring -> phase, for dispatchers with the two-level (suite_name
# then suite_part/group) shape -- see _collect_run_call_sites.
_TWO_LEVEL_DISPATCH_PHASES = {
    "ccpp_physics_run": "run",
    "ccpp_physics_timestep_init": "timestep_initial",
    "ccpp_physics_timestep_final": "timestep_final",
    "ccpp_physics_init": "physics_initial",
    "ccpp_physics_final": "physics_final",
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
    ccpp_physics_run, wraps the suite-part dispatch (inner scf.IfOp) with
    an !$acc data region using host model variable names. For each of the
    lifecycle dispatchers (ccpp_register/ccpp_init/ccpp_final/
    ccpp_physics_timestep_init/ccpp_physics_timestep_final -- bare,
    capgen-v1-style names since the vocabulary-resolution redesign),
    wraps the suite callee call
    inside each suite-name scf.IfOp the same way.

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
    deferred -- tracked as a GPU/OpenACC backlog item.

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
        ddt_instance_map, ddt_parent_map = _build_ddt_resolution_maps(bmdd.meta_data)
        host_var_map = _build_host_var_map(bmdd.meta_data, include_host=False)

        result = {}
        for suite_name, suite_desc in bsd.schemes.items():
            scheme_names = {
                scheme.attributes["name"]
                for group in suite_desc
                for scheme in _iter_schemes(group)
            }
            result[suite_name] = self._analyze_one_suite(
                scheme_names, bmdd.meta_data, ddt_instance_map, ddt_parent_map, host_var_map
            )
        return result

    def _analyze_one_suite(self, scheme_names, meta_data, ddt_instance_map, ddt_parent_map, host_var_map):
        """Same union math _build_model_var_clause_map (this pass's
        predecessor) always used -- any read/write across every scheme
        entry point that references a host var, per host var -- restricted
        to scheme_names, and additionally tracking which lifecycle phase
        each reference belongs to.

        Host vars where different schemes genuinely disagree about
        present-vs-update treatment (see cap_shared.find_diverged_suite_vars)
        are excluded entirely from present_vars/update_vars/copy-family here
        -- they get no VarLifetime, so _wrap_scheme_call does nothing for
        them at this (whole-suite) granularity. GPUDataPass routes their
        per-call present/update clauses instead, at the suite_cap level
        (backlog item (b)); gpu_ccpp_cap_pass.py's own
        _analyze_one_suite_residency separately establishes their
        entry/exit residency (enter/exit data), since excluding a diverged
        var from copy-family here would otherwise leave it with no
        entry/exit anchoring at all. This method's own model_space
        computation deliberately stays a bare per-arg read of
        model_var_memory_space (the host's own static declaration, NOT
        find_diverged_suite_vars's suite-scoped divergence union) --
        present/update/copy-family clause routing for a *non-diverged* var
        must keep reflecting what the host itself actually declares, not
        whether some other, unrelated scheme in this suite happens to also
        touch it.

        The diverged check itself stays keyed on the bare model_var_name
        (find_diverged_suite_vars's own convention, shared with GPUDataPass
        -- must not change). Everything downstream of that check keys on
        _resolve_host_var_key's resolved identity instead: for a plain host
        var this is the same bare name, but for a DDT member it's
        "instance_var%member_name" -- exactly what the real HostVarRefOp for
        that arg carries (see _ref_key), so present/update/copy directives
        can actually find their reference to attach to (backlog gap #5).
        """
        needs_in: dict = {}   # host_var -> bool
        needs_out: dict = {}  # host_var -> bool
        present_vars: set = set()
        update_vars: set = set()
        phases_used: dict = {}  # host_var -> set[phase]

        diverged = find_diverged_suite_vars(scheme_names, meta_data)

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

                    bare_host_var = arg.getAttr("model_var_name")
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

                    if bare_host_var in diverged:
                        continue

                    host_var = _resolve_host_var_key(
                        arg, ddt_instance_map, ddt_parent_map, host_var_map
                    )

                    if scheme_space == "device" and model_space == "device":
                        present_vars.add(host_var)
                    elif scheme_space == "device" and model_space == "host":
                        intent = arg.getAttr("intent") if arg.hasAttr("intent") else "inout"
                        reads  = intent in ("in",  "inout")
                        writes = intent in ("out", "inout")
                        needs_in[host_var]  = needs_in.get(host_var,  False) or reads
                        needs_out[host_var] = needs_out.get(host_var, False) or writes
                        phases_used.setdefault(host_var, set()).add(phase)
                    elif scheme_space == "host" and model_space == "device":
                        update_vars.add(host_var)
                        phases_used.setdefault(host_var, set()).add(phase)
                    # else: both host -- no directive needed

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

    # ---- Analysis: per-suite residency establishment (HostMatched present/ --
    # ---- update residency, distinct from clause routing above) --------------

    def _analyze_one_suite_residency(self, scheme_names, meta_data, ddt_instance_map, ddt_parent_map, host_var_map):
        """Return {host_var: VarLifetime} for every host var this suite
        treats as device-resident: the host's own static
        model_var_memory_space=="device" declaration (original behavior,
        unchanged), UNION the set of vars find_diverged_suite_vars reports
        as diverged for this suite.

        The diverged-var half of that union is what makes this method
        genuinely necessary rather than redundant: _analyze_one_suite
        excludes every diverged var from its own present_vars/update_vars/
        copy-family buckets entirely (their per-call present/update clauses
        are routed elsewhere, by GPUDataPass at the suite_cap level -- see
        that method's docstring) -- which would otherwise leave a diverged
        var with no entry/exit residency anchoring (enter/exit data) at
        all, even though it genuinely needs the device allocation
        established and torn down somewhere. This is deliberately NOT the
        broader "any scheme in this suite declares memory_space=device"
        union: a var with a single, self-consistent occurrence (one scheme
        wants device, the host doesn't declare it, nothing else touches it)
        is not diverged and is already fully and correctly handled by
        _analyze_one_suite's own copy-family bracket (per-call
        copyin/copy/copyout) -- adding residency on top of that would be
        pure redundancy, not a fix (confirmed by a real regression while
        building this: it produced a spurious `present()` region nested
        inside copy-family's own `copyin()` region for exactly this shape).

        Establishing device residency is a genuinely separate concern from
        clause routing: none of present()/update self/update device
        *allocate* anything (see this pass's class docstring), so whenever
        this union says a var is device-resident, CCPP needs to establish
        that residency itself (OpenACC's enter/exit-data are
        reference-counted, so this is safe even if a larger host model also
        manages the same var independently).

        Every returned VarLifetime is resolved via the same whole-sim/per-
        timestep anchor rules _resolve_lifetime already applies to copy-
        family vars -- including its degenerate (single-phase) case, which
        does NOT mean "no residency needed" here: _wrap_residency_directives
        treats a degenerate var exactly like copy-family's own "legacy_copy"
        vars, wrapping the one phase's call in a plain per-call copy()
        region every invocation (see this pass's docstring/plan history for
        why: a var used only at `_run` still needs residency established on
        every call, since register/initialize don't reference it at all).
        """
        diverged = find_diverged_suite_vars(scheme_names, meta_data)
        phases_used: dict = {}  # host_var -> set[phase]
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
                    bare_host_var = arg.getAttr("model_var_name")
                    model_space = (
                        arg.getAttr("model_var_memory_space")
                        if arg.hasAttr("model_var_memory_space")
                        else "host"
                    )
                    if model_space != "device" and bare_host_var not in diverged:
                        continue
                    host_var = _resolve_host_var_key(
                        arg, ddt_instance_map, ddt_parent_map, host_var_map
                    )
                    phases_used.setdefault(host_var, set()).add(phase)

        return {
            host_var: self._resolve_lifetime("residency", used)
            for host_var, used in phases_used.items()
        }

    def _analyze_suite_residency_lifetimes(self, ccpp_mod):
        """Return {suite_name: {host_var_name: VarLifetime}} for residency
        establishment -- mirrors _analyze_suite_var_lifetimes's per-suite
        scoping exactly (own BuildMetaDataDescriptions/BuildSchemeDescription
        traversal; the minor duplication is deliberate, lower risk than
        threading this through the existing, working method).
        """
        bmdd = BuildMetaDataDescriptions()
        bmdd.traverse(ccpp_mod)
        bsd = BuildSchemeDescription()
        bsd.traverse(ccpp_mod)
        ddt_instance_map, ddt_parent_map = _build_ddt_resolution_maps(bmdd.meta_data)
        host_var_map = _build_host_var_map(bmdd.meta_data, include_host=False)

        result = {}
        for suite_name, suite_desc in bsd.schemes.items():
            scheme_names = {
                scheme.attributes["name"]
                for group in suite_desc
                for scheme in _iter_schemes(group)
            }
            result[suite_name] = self._analyze_one_suite_residency(
                scheme_names, bmdd.meta_data, ddt_instance_map, ddt_parent_map, host_var_map
            )
        return result

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

    # Callee-name markers identifying a per-group suite-cap callee, checked
    # as substrings (the callee name's own trailing group-name segment
    # varies per suite XML, so an exact suffix can't be used). Each marker is
    # `SUITE_FN_INFIX` (currently "", previously "_suite") followed
    # by a fixed literal segment. f"{SUITE_FN_INFIX}_physics" is the
    # pre-existing run marker (relies on this codebase's own example suites
    # conventionally naming their run group "physics" -- narrow, but
    # pre-existing and out of scope to broaden here); the
    # f"{SUITE_FN_INFIX}_timestep_init_"-style markers are genuinely
    # group-name-independent, since that segment is fixed
    # regardless of the group's own name (suite_cap.py's
    # generated_subroutine_posfix always inserts it before the group name,
    # never depending on what the group is called).
    _SUITE_CALLEE_MARKERS = (
        f"{SUITE_FN_INFIX}_physics", f"{SUITE_FN_INFIX}_timestep_init_",
        f"{SUITE_FN_INFIX}_timestep_final_",
        f"{SUITE_FN_INFIX}_init_", f"{SUITE_FN_INFIX}_final_",
    )

    def _find_suite_part_ifs(self, true_block):
        """Yield (if_op, call_op) for every suite-part scf.IfOp in the
        else-if chain built by run_dispatch.py's _build_run_dispatch_chain/
        _build_one_suite_part_dispatch: the first-listed suite part (suite
        XML order) is the outermost scf.IfOp in true_block, and each
        subsequent suite part's own scf.IfOp is nested one level deeper in
        the previous one's false_region (built "from inside out", so the
        chain reads outer-to-inner in suite-XML/program order) -- confirmed
        directly against _build_one_suite_part_dispatch's
        `scf.IfOp(suite_part_eq.res, [], [...], part_inner_false)` and its
        caller's reverse iteration.

        A suite with only one part (the common case) yields exactly one
        (if_op, call_op) here, identical to what the old
        _find_inner_suite_part_if returned -- this generalizes it rather
        than changing behavior for that case.
        """
        block = true_block
        while True:
            found_if = next((op for op in block.ops if isa(op, scf.IfOp)), None)
            if found_if is None:
                return
            call_op = None
            if found_if.true_region.blocks:
                call_op = next(
                    (inner for inner in found_if.true_region.blocks[0].ops
                     if isa(inner, func.CallOp) and any(
                         marker in inner.callee.root_reference.data
                         for marker in self._SUITE_CALLEE_MARKERS
                     )),
                    None,
                )
            if call_op is not None:
                yield found_if, call_op
            if not found_if.false_region.blocks:
                return
            block = found_if.false_region.blocks[0]

    def _collect_run_call_sites(self, fn_op, phase="run"):
        """Yield (suite_name, phase, true_block, suite_call) for every
        suite-part call site of a two-level (suite_name -> suite_part/group)
        dispatcher -- ccpp_physics_run, or ccpp_physics_timestep_init now
        that it has the same per-group shape. A suite with more than one
        group (e.g. kessler's physics_before_coupler/physics_after_coupler)
        yields one tuple per group, in suite-XML/program order -- see
        _find_suite_part_ifs. true_block is always the shared, suite-level
        block (host var refs for every suite part are hoisted flat into it
        by run_dispatch.py's _build_one_suite_part_dispatch), so only
        suite_call varies across the tuples for one suite_name+phase.
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
            for _if_op, suite_call in self._find_suite_part_ifs(true_block):
                yield suite_name, phase, true_block, suite_call

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

    @staticmethod
    def _ref_key(op) -> str:
        """Identity key for a HostVarRefOp, matching _resolve_host_var_key's
        metadata-side key exactly: the bare var_name unchanged for a plain
        host var, or "var_name%member_name" when the op's member_name
        attribute is set (a DDT member) -- exactly what print_ftn.py prints
        as the Fortran reference. Every scan below that matches a
        HostVarRefOp against a lifetime/residency-lifetime/donor dict must
        use this, not op.var_name.data alone, or DDT members silently never
        match (backlog gap #5)."""
        member = op.attributes.get("member_name")
        return f"{op.var_name.data}%{member.data}" if member is not None else op.var_name.data

    def _ref_used_by_call(self, true_block, host_var, suite_call) -> bool:
        """True iff some HostVarRefOp for host_var in true_block is actually
        passed as an argument to suite_call (directly, or via its
        ArraySectionOp).

        When a suite has more than one suite-part call site (see
        _find_suite_part_ifs), true_block is the shared, suite-level block
        holding one HostVarRefOp instance per suite part -- name matching
        alone (_ref_key) can't tell which specific call a given ref
        instance belongs to, only whether the name appears *somewhere* in
        the shared block. Checking actual SSA use against suite_call.arguments
        is the precise way to attribute a ref to the call it was actually
        built for by run_dispatch.py's per-suite-part _build_host_var_refs.
        """
        call_args = set(suite_call.arguments)
        section_for_ref = {}
        for op in true_block.ops:
            if isa(op, ArraySectionOp):
                section_for_ref[op.source] = op.res
        for op in true_block.ops:
            if not isa(op, HostVarRefOp) or self._ref_key(op) != host_var:
                continue
            if op.res in call_args or section_for_ref.get(op.res) in call_args:
                return True
        return False

    def _resolve_phase_group_overrides(self, phase, group_calls, true_block, lifetimes):
        """For one (suite_name, phase) group of call sites sharing a phase
        name (group_calls, in suite-XML/program order), return
        {(id(suite_call), host_var): "exclude"|"passthrough"} overriding
        _role_at's phase-only role for every var whose attribution to a
        specific call site in the group is ambiguous.

        CCPP scheme metadata has no concept of suite-XML groups, only phase
        suffixes (_run, _timestep_initial, ...) -- see split_scheme_table_name
        -- so a var's entry_phase/exit_phase (or, for a non-hoisted var, its
        single "legacy" phase) is a phase *name*, which multiple suite-part
        call sites can share (e.g. kessler's physics_before_coupler and
        physics_after_coupler both dispatch under phase "run"). Two distinct
        problems follow from this, both confirmed against real generated
        code, both fixed here:

        1. true_block is the shared, suite-level block -- it holds one
           HostVarRefOp per suite part (run_dispatch.py's
           _build_host_var_refs is called once per suite part, all results
           flattened into the same list -- see _collect_run_call_sites).
           A var naturally used by only ONE call site in the group is still
           *visible* to every other call site's natural-ref loop (it just
           scans true_block.ops by name, not by attribution), so every
           other call site would independently re-classify and re-insert a
           directive for a var it never actually references -- confirmed on
           Derecho: `kessler_timestep_final_physics_after_coupler(errflg,
           errmsg)` (zero of cpairv/phys_state%T/zm/phis/dse as arguments)
           got its own spurious `!$acc exit data copyout(cpairv,
           phys_state%T, ...)` anyway, a second, premature exit-data for
           vars it has no relationship to, immediately crashing
           (cuMemcpyDtoHAsync CUDA_ERROR_INVALID_VALUE). Fixed by excluding
           (not even a present()-check) every call site NOT among the ones
           actually using the var, per _ref_used_by_call -- for every var,
           hoisted or not (a "legacy"/non-hoisted var used by only one
           suite part in the group has the exact same shared-block leak).
        2. A HOISTED var naturally used by MORE than one call site in the
           group still needs only its true first (entry) / true last (exit)
           touching call to actually get "enter"/"exit" -- every other
           touching call falls back to "passthrough" (a present()-check is
           still safe and appropriate there, same semantic as this pass's
           existing "phase strictly between entry and exit" passthrough --
           the var IS guaranteed already resident, just not established or
           torn down at this particular call).

        Returns {} whenever the group has at most one call site (the
        overwhelming common case) -- a guaranteed no-op, so every existing
        single-call-site-per-phase suite is completely unaffected.
        """
        overrides = {}
        if len(group_calls) <= 1:
            return overrides
        for host_var, lt in lifetimes.items():
            touching_ids = {
                id(sc) for sc in group_calls
                if self._ref_used_by_call(true_block, host_var, sc)
            }
            for sc in group_calls:
                if id(sc) not in touching_ids:
                    overrides[(id(sc), host_var)] = "exclude"
            if not lt.hoisted or len(touching_ids) <= 1:
                continue
            touching = [sc for sc in group_calls if id(sc) in touching_ids]
            if phase == lt.entry_phase:
                for sc in touching[1:]:
                    overrides[(id(sc), host_var)] = "passthrough"
            if phase == lt.exit_phase:
                for sc in touching[:-1]:
                    overrides[(id(sc), host_var)] = "passthrough"
        return overrides

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

        # For each variable, find its HostVarRefOp and resolve to the best SSA value.
        # A host var can have more than one HostVarRefOp in true_block (e.g. a
        # scheme argument bound to the same host var at two dummy-arg
        # positions) -- only the first is kept, so a directive clause never
        # lists the same variable twice (a duplicate copyout(x, x) causes a
        # runtime cuMemcpyDtoHAsync failure, not just redundant movement).
        refs = []
        seen_names = set()
        for op in true_block.ops:
            if not isa(op, HostVarRefOp):
                continue
            key = self._ref_key(op)
            if key not in var_names or key in seen_names:
                continue
            seen_names.add(key)
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
            if isa(op, HostVarRefOp):
                key = self._ref_key(op)
                if key not in donors:
                    member = op.attributes.get("member_name")
                    donors[key] = (
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

        var_name may be a composite "instance%member" key (see _ref_key) --
        splitting on the first "%" always recovers the true instance
        variable name, even for a nested-DDT member path (itself containing
        further "%" separators), since HostVarRefOp's own first positional
        arg must be the bare instance name, with the rest carried separately
        via member_name.
        """
        donor = donor_refs.get(var_name)
        if donor is None:
            return None
        module_name, res_type, member_name = donor
        instance_name = var_name.split("%", 1)[0]
        new_ref = HostVarRefOp(instance_name, module_name, res_type, member_name=member_name)
        Rewriter.insert_op(new_ref, InsertPoint.at_start(true_block))
        return new_ref.res

    def _directive_op(self, acc_cls, acc_kwargs: dict, omp_cls, omp_kwargs: dict):
        """Return the ACC or OMP op for one GPU directive role, chosen by
        self.directive -- see cap_shared.directive_op's own docstring for
        why this dispatch is centralized, shared with gpu_data_pass.py.
        """
        return directive_op(self.directive, acc_cls, acc_kwargs, omp_cls, omp_kwargs)

    def _wrap_scheme_call(
        self, true_block, suite_call, lifetimes, phase, donor_refs,
        role_overrides=None, is_first_call_in_phase_group=True,
    ):
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

        role_overrides ({(id(suite_call), host_var): "passthrough"}, from
        _resolve_phase_group_overrides) takes precedence over _role_at's
        phase-only role whenever this suite_call is one of more than one
        call site sharing `phase` within this suite -- see that method's
        docstring. Empty/None for every single-call-site-per-phase suite
        (the common case), which is a complete no-op here.

        is_first_call_in_phase_group gates the forced-anchor loop below: it
        must fire only once per (suite, phase) group, not once per call
        site now that a phase can have more than one -- see apply().
        """
        role_overrides = role_overrides or {}
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
            var_name = self._ref_key(ref_op)
            lt = lifetimes.get(var_name)
            if lt is None:
                continue
            seen_here.add(var_name)
            role = role_overrides.get((id(suite_call), var_name)) or self._role_at(lt, phase)
            if role == "exclude":
                # This call site doesn't naturally reference var_name at all
                # (see _resolve_phase_group_overrides) -- its visibility
                # here is an artifact of a *different* suite part's own
                # HostVarRefOp sharing this suite-level block. seen_here is
                # still marked above so the forced-anchor loop below (which
                # only fires for genuinely absent vars) doesn't try to
                # synthesize a second, redundant reference for it.
                continue
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

        # Forced anchors with no natural HostVarRefOp at this phase. Gated to
        # the phase group's first call site only: with more than one call
        # site sharing `phase` (see apply()), a var relying purely on
        # synthesis (no natural reference anywhere in the group) must still
        # get exactly one enter/exit pair for the group, not one per call
        # site -- any single, stable site works since there's no natural
        # occurrence to prefer, so "first in program order" is used.
        if is_first_call_in_phase_group:
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
            # OMP's map(to:...) is the enter-data equivalent of ACC's
            # copyin(...); map(alloc:...) of create(...).
            enter_op = self._directive_op(
                AccEnterDataOp, {"copyin": enter_copyin_refs, "create": enter_create_refs},
                OmpTargetEnterDataOp, {"to": enter_copyin_refs, "alloc": enter_create_refs},
            )
            Rewriter.insert_op(enter_op, enter_anchor)

        if exit_copyout or exit_delete:
            exit_copyout_refs = self._resolve_array_refs(true_block, set(exit_copyout), use_sections=False)
            exit_delete_refs  = self._resolve_array_refs(true_block, set(exit_delete),  use_sections=False)
            # OMP's map(from:...) is the exit-data equivalent of ACC's
            # copyout(...); map(release:...) of delete(...).
            exit_op = self._directive_op(
                AccExitDataOp, {"copyout": exit_copyout_refs, "delete": exit_delete_refs},
                OmpTargetExitDataOp, {"from_": exit_copyout_refs, "release": exit_delete_refs},
            )
            Rewriter.insert_op(exit_op, exit_anchor)

        # Hoisted "update" variables: a single sync pair per suite instead
        # of one per touching call site.
        if update_enter_vars:
            update_enter_refs = self._resolve_array_refs(true_block, update_enter_vars, use_sections=False)
            Rewriter.insert_op(
                self._directive_op(
                    AccUpdateSelfOp, {"array_refs": update_enter_refs},
                    OmpTargetUpdateFromOp, {"array_refs": update_enter_refs},
                ),
                enter_anchor,
            )

        if update_exit_vars:
            update_exit_refs = self._resolve_array_refs(true_block, update_exit_vars, use_sections=False)
            Rewriter.insert_op(
                self._directive_op(
                    AccUpdateDeviceOp, {"array_refs": update_exit_refs},
                    OmpTargetUpdateToOp, {"array_refs": update_exit_refs},
                ),
                exit_anchor,
            )

        # Update directives go inside the inner scf.IfOp's true region,
        # bracketing the actual suite physics call. This is the legacy
        # per-call path for degenerate/single-phase "update" variables --
        # still driven purely off lt.kind == "update", same as before this
        # feature existed.
        if update_vars and suite_call is not None:
            update_refs = self._resolve_array_refs(
                true_block, update_vars
            )
            Rewriter.insert_op(
                self._directive_op(
                    AccUpdateSelfOp, {"array_refs": update_refs},
                    OmpTargetUpdateFromOp, {"array_refs": update_refs},
                ),
                InsertPoint.before(suite_call),
            )
            Rewriter.insert_op(
                self._directive_op(
                    AccUpdateDeviceOp, {"array_refs": update_refs},
                    OmpTargetUpdateToOp, {"array_refs": update_refs},
                ),
                InsertPoint.after(suite_call),
            )

    def _wrap_residency_directives(
        self, true_block, suite_call, residency_lifetimes, phase, donor_refs,
        role_overrides=None, is_first_call_in_phase_group=True,
    ):
        """Establish/tear down device residency for HostMatched vars that
        need it (see _analyze_one_suite_residency), independently of and in
        addition to whatever _wrap_scheme_call already did for the same call
        site. Deliberately a separate, parallel pass rather than integrated
        into _wrap_scheme_call: lower risk than modifying that already-
        intricate method, at the cost of a var needing both residency and a
        present()/update assertion getting two adjacent directives at one
        call site instead of one merged one -- a real but minor verbosity/
        redundancy tradeoff, not a correctness one.

        role_overrides/is_first_call_in_phase_group: same meaning and same
        source (_resolve_phase_group_overrides, computed once per (suite,
        phase) group in apply()) as _wrap_scheme_call's own parameters of
        the same name -- see that method's docstring. This is exactly the
        mechanism that fixes the real crash this pair of parameters was
        added for: a suite-XML group boundary (e.g. kessler's
        physics_before_coupler/physics_after_coupler) that CCPP scheme
        metadata can't see, since both groups dispatch under the same bare
        phase name ("run").

        Only ever produces data-movement directives (copy/copyin/copyout; never
        create/delete/present/update) -- residency establishment doesn't have a
        "kind", every var here just needs the host's current value copied to
        the device once (entry) and copied back once (exit), reusing _role_at's
        generic hoisted/entry_phase/exit_phase classification unchanged:

          "enter"/"exit"  -> hoisted: AccEnterDataOp(copyin=...)/
                              AccExitDataOp(copyout=...) at the computed
                              anchors (OMP: OmpTargetEnterDataOp(to=...)/
                              OmpTargetExitDataOp(from_=...)).
          "legacy"/"unused" -> degenerate (single-phase): a plain structured
                              copy() region wrapping this one call, every
                              invocation (OMP: OmpTargetDataBeginOp(tofrom=...)/
                              OmpTargetDataEndOp()) -- NOT a no-op; see
                              _analyze_one_suite_residency's docstring for
                              why a var used only at `_run` still needs this.
          "passthrough"    -> nothing: the existing present()/update-self-
                              device logic (_wrap_scheme_call, unaffected by
                              this method) already handles per-call
                              correctness at phases strictly between entry
                              and exit.
        """
        if not residency_lifetimes:
            return

        role_overrides = role_overrides or {}
        enter_vars, exit_vars, legacy_vars = [], [], []

        seen_here = set()
        for ref_op in true_block.ops:
            if not isa(ref_op, HostVarRefOp):
                continue
            var_name = self._ref_key(ref_op)
            lt = residency_lifetimes.get(var_name)
            if lt is None:
                continue
            seen_here.add(var_name)
            role = role_overrides.get((id(suite_call), var_name)) or self._role_at(lt, phase)
            if role == "exclude":
                # See _wrap_scheme_call's identical branch: this call site
                # doesn't naturally reference var_name at all -- its
                # visibility here is an artifact of a different suite
                # part's own HostVarRefOp sharing this block.
                continue
            if role in ("legacy", "unused"):
                legacy_vars.append(var_name)
            elif role == "enter":
                enter_vars.append(var_name)
            elif role == "exit":
                exit_vars.append(var_name)
            # "passthrough": nothing to do.

        # See _wrap_scheme_call's identical gate for why this only fires at
        # the phase group's first call site.
        if is_first_call_in_phase_group:
            for var_name, lt in residency_lifetimes.items():
                if not lt.hoisted or var_name in seen_here:
                    continue
                if phase == lt.entry_phase:
                    if self._synthesize_ref(true_block, var_name, donor_refs) is not None:
                        enter_vars.append(var_name)
                elif phase == lt.exit_phase:
                    if self._synthesize_ref(true_block, var_name, donor_refs) is not None:
                        exit_vars.append(var_name)

        if legacy_vars:
            legacy_refs = self._resolve_array_refs(true_block, set(legacy_vars), use_sections=True)
            data_begin_op = self._directive_op(
                AccDataBeginOp, {"copy": legacy_refs},
                OmpTargetDataBeginOp, {"tofrom": legacy_refs},
            )
            data_end_op = self._directive_op(AccDataEndOp, {}, OmpTargetDataEndOp, {})
            Rewriter.insert_op(data_begin_op, InsertPoint.before(suite_call))
            Rewriter.insert_op(data_end_op, InsertPoint.after(suite_call))

        if enter_vars:
            enter_refs = self._resolve_array_refs(true_block, set(enter_vars), use_sections=False)
            Rewriter.insert_op(
                self._directive_op(
                    AccEnterDataOp, {"copyin": enter_refs},
                    OmpTargetEnterDataOp, {"to": enter_refs},
                ),
                InsertPoint.before(suite_call),
            )

        if exit_vars:
            exit_refs = self._resolve_array_refs(true_block, set(exit_vars), use_sections=False)
            Rewriter.insert_op(
                self._directive_op(
                    AccExitDataOp, {"copyout": exit_refs},
                    OmpTargetExitDataOp, {"from_": exit_refs},
                ),
                InsertPoint.after(suite_call),
            )

    def apply(self, ctx: Context, op: builtin.ModuleOp) -> None:
        ccpp_mod = find_ccpp_module(op.body.block.ops)
        if ccpp_mod is None:
            return

        suite_lifetimes = self._analyze_suite_var_lifetimes(ccpp_mod)
        suite_residency_lifetimes = self._analyze_suite_residency_lifetimes(ccpp_mod)
        if not any(suite_lifetimes.values()) and not any(suite_residency_lifetimes.values()):
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
                two_level_phase = next(
                    (p for suf, p in _TWO_LEVEL_DISPATCH_PHASES.items() if suf in fn_name),
                    None,
                )
                if two_level_phase is not None:
                    call_sites.extend(self._collect_run_call_sites(child, two_level_phase))
                else:
                    phase = next(
                        (p for suf, p in _LIFECYCLE_FN_SUFFIX_TO_PHASE.items()
                         if fn_name.endswith(suf)),
                        None,
                    )
                    if phase is not None:
                        call_sites.extend(self._collect_lifecycle_call_sites(child, phase))

        # Group call sites by (suite_name, phase): a suite with more than
        # one suite-XML group (e.g. kessler's physics_before_coupler/
        # physics_after_coupler) now yields more than one call site per
        # phase here (see _collect_run_call_sites/_find_suite_part_ifs).
        # CCPP scheme metadata has no concept of these groups -- a hoisted
        # var's entry_phase/exit_phase is a bare phase name shared by every
        # call site in the group -- so each group needs its own role
        # overrides (computed once, from both lifetime sources merged: the
        # two dicts never collide since both are keyed by
        # (id(suite_call), host_var) and mean the same thing) disambiguating
        # which specific call site is the true entry/exit anchor, plus a
        # marker for which call site is first (for forced-anchor synthesis,
        # which must fire once per group, not once per call site).
        phase_groups: dict = {}
        for suite_name, phase, true_block, suite_call in call_sites:
            phase_groups.setdefault((suite_name, phase), []).append((true_block, suite_call))

        role_overrides: dict = {}
        first_call_in_group: set = set()
        for (suite_name, phase), sites in phase_groups.items():
            first_call_in_group.add(id(sites[0][1]))
            group_true_block = sites[0][0]
            group_calls = [sc for _tb, sc in sites]
            for lifetimes_by_suite in (suite_lifetimes, suite_residency_lifetimes):
                lifetimes = lifetimes_by_suite.get(suite_name)
                if not lifetimes:
                    continue
                role_overrides.update(
                    self._resolve_phase_group_overrides(
                        phase, group_calls, group_true_block, lifetimes
                    )
                )

        for suite_name, phase, true_block, suite_call in call_sites:
            # Residency must be wrapped *before* _wrap_scheme_call: both
            # anchor new ops via InsertPoint.before/after(suite_call), and
            # whichever call runs second ends up closer to suite_call (each
            # insertion at "before X" lands between the previous insertion
            # and X). Residency needs to be outermost -- established before
            # any present()/update self assertion at the same call site
            # runs, torn down after it -- otherwise a var needing both (e.g.
            # a present-clause var that also needs hoisted residency at its
            # entry phase) gets `present(...)` emitted *before* the
            # `enter data copyin(...)` that's supposed to satisfy it: a real
            # "data in PRESENT clause was not found on device" bug, caught
            # by Copilot review on PR #37 and confirmed by inspecting the
            # actual generated order for exactly this case.
            is_first = id(suite_call) in first_call_in_group
            residency_lifetimes = suite_residency_lifetimes.get(suite_name)
            if residency_lifetimes:
                self._wrap_residency_directives(
                    true_block, suite_call, residency_lifetimes, phase, donor_refs,
                    role_overrides=role_overrides, is_first_call_in_phase_group=is_first,
                )
            lifetimes = suite_lifetimes.get(suite_name)
            if lifetimes:
                self._wrap_scheme_call(
                    true_block, suite_call, lifetimes, phase, donor_refs,
                    role_overrides=role_overrides, is_first_call_in_phase_group=is_first,
                )
