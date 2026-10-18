"""Scheme I/O capture -- opt-in only, never emitted unless xdsl_ccpp's own
--capture-scheme CLI flag is passed (see ccpp_dsl.py).

scheme-io-capture (BACKLOG.md), design proposal at CHANGELOG.md's
"scheme-io-capture: scheme I/O capture + generated per-scheme unit tests"
section. Not a debugging aid and not compared against CAM's own
history-file output: the real goal is data-driven, scheme-level
regression tests built from realistic, captured atmospheric states,
independent of a full CAM build/run. Captures every (supported) input/
output argument of a chosen scheme (optionally restricted to one
lifecycle phase) to disk, by inserting a call into the ccpp_capture_mod
runtime Fortran library immediately before/after the scheme's own call,
by intent:
  - intent=in:    one capture, immediately before the call.
  - intent=out:   one capture, immediately after the call.
  - intent=inout: both -- before and after are directly comparable.

Call-site discovery reuses cap_shared.iter_scheme_call_sites -- the same
machinery gpu_debug_print_pass.py's own Part C uses (extracted there
2026-10-17 specifically because this pass needed the identical logic).
This pass differs from that one in what it inserts (a capture call per
argument, not a diagnostic print) and where (every supported intent in/
out/inout argument, not just sliced device-resident ones).

v1 scope, deliberately narrow (see the design proposal's own reasoning):
only {integer, logical, real(kind_phys)} x {rank 0..3} are supported --
this is, in practice, the real cross product that appears in CCPP
metadata. Everything else (character, DDT/derived types, any other real
kind) is silently skipped, not a hard error -- a scheme mixing supported
and unsupported arguments should still get the supported ones captured.
Also skipped: errmsg/errflg (not physically meaningful to dump) and
`optional` arguments (deferred -- confirmed zero real occurrences in the
target corpus, see the design doc for the full reasoning).

Runtime library note: xdsl_ccpp/framework_src/ccpp_capture_mod.F90 (a
separate PR) provides the concrete ccpp_capture_*/ccpp_capture_read_*/
ccpp_capture_compare_* procedures this pass's emitted calls and the
generated test-driver programs below both depend on, each grouped under
one of three generic interfaces (ccpp_capture/ccpp_capture_read/
ccpp_capture_compare). Every call this pass emits uses the generic
`ccpp_capture` name, never a concrete one directly -- Fortran's own
overload resolution dispatches to the right concrete write procedure
from the captured value's static type and rank, which is exactly the
compile-time check `_is_capture_supported` already performs at the
Python/IR level, so there's never a mismatch between the two to worry
about. This also means only one `use ccpp_capture_mod, only: ccpp_capture`
declaration is ever needed per generated module (see
_ensure_capture_decl), not one per distinct (type, rank) combination
actually captured.

Generated test drivers (--capture-test-driver-dir, a third, independent
PR): for every matched call site, when a driver directory is configured,
also emit a standalone `test_<table_name>.F90` program that reads a
captured fixture back (call_count=1 -- the fixture's first, and normally
only, real capture, written by a separate process; see
ccpp_capture_mod.F90's own call_count semantics for why a driver can't
just omit it and rely on the peek default, which only makes sense within
the *writing* process), calls the real scheme subroutine with those
inputs, and compares its outputs against the captured 'after' snapshot --
not against a fresh calculation. Declarations and the call's own keyword
argument list are derived from the identical per-argument metadata this
pass already resolves for capture (a second consumer of it, not a
separate derivation): array dimensions are resolved via each array
argument's own `dim_names` (CCPP's own convention of naming a *different*
scalar argument's standard_name as a dimension bound -- e.g. `theta`'s
dimensions=(horizontal_dimension, vertical_layer_dimension) resolve to
whichever two arguments in the *same* arg table carry those exact
standard_name values, almost always `ncol`/`nz`-shaped scalars this pass
already also captures). A `optional` argument is simply omitted from the
driver's generated call (valid Fortran); an argument CCPP mandates but
this pass's own v1 type scope can't capture (e.g. a character
`scheme_name` output) is still declared and passed through so the call
compiles, just never compared. If any array argument's dimensions can't
be resolved this way, driver generation is skipped for that call site
entirely (logged, not a hard pipeline failure) rather than emitting a
driver that can't actually allocate its own arrays correctly.

Language-specific-knowledge boundary, same as everywhere else in this
codebase: this file interprets CCPP metadata only (_driver_param_category,
_resolve_array_dims, _build_test_driver_params) and never emits Fortran
syntax directly -- the resolved, Fortran-agnostic result
(print_ftn.TestDriverParam) is handed to
print_ftn.render_scheme_io_capture_test_driver, which is the one place
that knows how to render a declaration, an allocate statement, or the
driver's overall program structure as text. (The per-argument capture
calls apply() inserts directly into the IR, below, are a different case:
those go through RawFortranLinesOp, this dialect's own established escape
hatch for a short, already-final snippet inserted into the generated
cap's own IR tree -- not a full, hand-assembled program text.)
"""

import os
import sys
from dataclasses import dataclass

from xdsl.context import Context
from xdsl.dialects import builtin, func, llvm
from xdsl.dialects.builtin import StringAttr, i8
from xdsl.passes import ModulePass
from xdsl.rewriter import InsertPoint, Rewriter
from xdsl.utils.hints import isa

from xdsl_ccpp.backend.print_ftn import TestDriverParam, render_scheme_io_capture_test_driver
from xdsl_ccpp.dialects.ccpp_utils import (
    AccUpdateSelfOp,
    OmpTargetUpdateFromOp,
    RawFortranLinesOp,
)
from xdsl_ccpp.transforms.util.cap_shared import (
    _call_args,
    _call_param_names,
    _device_arg_names,
    _expr_text,
    directive_op,
    iter_scheme_call_sites,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import BuildMetaDataDescriptions
from xdsl_ccpp.transforms.util.ir_utils import build_host_var_index, find_ccpp_module
from xdsl_ccpp.util.ccpp_conventions import CCPP_ERROR_STD_NAMES, CCPP_KIND_PHYS

# Absolute tolerance used by every generated driver's real-valued
# comparisons -- a named Fortran PARAMETER in the generated source (not
# baked into each call site), so a human can tighten/loosen it later by
# editing one line of generated output without regenerating.
_TEST_DRIVER_TOLERANCE = "1.0e-10_kind_phys"

# CCPP standard name for "is this the MPI root/master task" -- CAM-SIMA
# exposes this via spmd_utils.F90's `masterproc`, already a widely-used
# real convention (dozens of real schemes consume it), unlike `mpi_rank`
# (also host-exposed, but not currently consumed by any real scheme).
# Used to guard every inserted capture call so only one task ever writes
# a given tag's file -- confirmed directly against a real 24-task
# CAM-SIMA build that without this guard, every task races to write the
# same filename and corrupts it (a captured `ncol` decoded to garbage).
# Resolved once per `apply()` call via the host's own metadata (not a
# new MPI dependency in ccpp_capture_mod.F90 itself, which stays exactly
# as minimal as before); when the host doesn't declare this standard
# name at all (e.g. the standalone examples/kessler, which is
# single-task), the guard is simply omitted and every capture call runs
# unconditionally, which is already correct there.
_MPI_ROOT_STD_NAME = "flag_for_mpi_root"

# Canonical CCPP lifecycle order -- used only to sequence a scheme's own
# captured phases within ONE generated test driver (see
# _maybe_emit_test_driver), not to filter or validate anything. An
# unrecognized phase (should not happen; cap_shared.split_scheme_table_name
# only ever returns one of these) sorts after every known one rather than
# raising, matching this module's general "degrade, don't crash" posture
# for anything related to the test-driver convenience feature.
_LIFECYCLE_PHASE_ORDER = {
    name: i
    for i, name in enumerate(
        ("register", "initialize", "timestep_initial", "run", "timestep_final", "finalize")
    )
}

# {integer, logical, real(kind_phys)} x {rank 0..3} -- see module docstring
# for why this is the real, deliberately narrow v1 scope, not an
# open-ended type system. "real" is handled separately below (its code
# additionally requires kind == CCPP_KIND_PHYS); character and any
# DDT/derived type (anything not in this set and not "real") are excluded
# simply by never matching a type here.
_TYPE_CODE = {"integer", "logical"}
_MAX_SUPPORTED_RANK = 3


def _is_capture_supported(arg_type: "str | None", kind: "str | None", rank: int) -> bool:
    """True iff this argument's (type, kind, rank) is within v1's capture
    scope -- {integer, logical, real(kind_phys)} x {rank 0..3}. The
    emitted capture call always uses ccpp_capture_mod's generic
    `ccpp_capture` name (Fortran's own overload resolution picks the
    right concrete procedure from the argument's static type and rank;
    there's exactly one real-kind member per rank since this function
    already rejects any kind but CCPP_KIND_PHYS, so there's no ambiguity
    to resolve) -- this function only gates whether to capture at all,
    it no longer needs to name a concrete procedure itself."""
    if rank > _MAX_SUPPORTED_RANK:
        return False
    if arg_type == "real":
        return kind == CCPP_KIND_PHYS
    return arg_type in _TYPE_CODE


def _driver_param_category(arg) -> str:
    """Classify one real call argument for test-driver generation:
    "optional" (omit from the generated call entirely), "error_arg"
    (errmsg/errflg -- always declared and passed, never compared),
    "unverified" (mandatory but outside this pass's v1 capture type scope
    -- still declared and passed so the call compiles, never compared),
    or "in"/"out"/"inout" (a real captured argument -- matches exactly
    what apply()'s own per-argument capture loop would do for it)."""
    if arg.hasAttr("optional"):
        return "optional"
    std_name = arg.getAttr("standard_name") if arg.hasAttr("standard_name") else None
    if std_name in CCPP_ERROR_STD_NAMES:
        return "error_arg"
    intent = arg.getAttr("intent") if arg.hasAttr("intent") else None
    if intent not in ("in", "out", "inout"):
        return "unverified"
    arg_type = arg.getAttr("type") if arg.hasAttr("type") else None
    kind = arg.getAttr("kind") if arg.hasAttr("kind") else None
    rank = arg.getAttr("dimensions") if arg.hasAttr("dimensions") else 0
    if not _is_capture_supported(arg_type, kind, rank):
        return "unverified"
    return intent


def _resolve_array_dims(arg, std_name_to_param: dict) -> "list[str] | None":
    """Resolve an array argument's own `dim_names` (CCPP standard-name
    dimension bounds) to the local parameter names, within the same arg
    table, that actually carry those standard names -- e.g. `theta`'s
    dim_names=["horizontal_dimension", "vertical_layer_dimension"]
    resolves to ["ncol", "nz"] when those are the two arguments whose own
    standard_name matches. A `lower:upper`-shaped dim_names entry (real,
    seen elsewhere in this codebase's dimension handling) uses only the
    upper bound -- the lower bound is never itself a resolvable argument
    name (e.g. `ccpp_constant_one`). Returns None if any dimension can't
    be resolved this way -- caller must then skip driver generation for
    this call site entirely, not guess a size.
    """
    if not arg.hasAttr("dim_names"):
        return None
    resolved = []
    for raw in arg.getAttr("dim_names"):
        name = raw.strip()
        if ":" in name:
            name = name.split(":")[-1].strip()
        if not name:
            return None
        local = std_name_to_param.get(name)
        if local is None:
            return None
        resolved.append(local)
    return resolved


def _enclosing_module(op) -> "builtin.ModuleOp | None":
    """Walk up from `op` to the nearest enclosing builtin.ModuleOp (the
    `_cap`-suffixed suite-cap module a capture call actually lives in) --
    needed so a declaration FuncOp carrying ccpp_capture_mod's own
    `module` attribute can be inserted at that module's top level, which
    is what print_ftn.py's _print_module reads to generate this module's
    `use ccpp_capture_mod, only: <proc>` lines (see _ensure_capture_decl).
    """
    cur = op.parent_op()
    while cur is not None and not isa(cur, builtin.ModuleOp):
        cur = cur.parent_op()
    return cur


def _build_test_driver_params(
    param_names: list, args_by_name: dict,
) -> "list[TestDriverParam] | None":
    """Resolve CCPP metadata for one real scheme call site into the
    plain, Fortran-agnostic TestDriverParam list print_ftn.py's
    render_scheme_io_capture_test_driver needs -- all CCPP-specific
    interpretation (intent, optionality, dim_names resolution) happens
    here, not in the printer. Returns None (caller skips emission, logs a
    note) if any array argument's dimensions can't be resolved, or if
    nothing in this call site is actually captured (a driver with no
    fixture-backed comparison would be a no-op test, not a regression
    test)."""
    std_name_to_param = {
        a.getAttr("standard_name"): pname
        for pname, a in args_by_name.items()
        if a.hasAttr("standard_name")
    }

    params: list[TestDriverParam] = []
    any_captured = False

    for pname in param_names:
        arg = args_by_name.get(pname)
        if arg is None:
            return None
        category = _driver_param_category(arg)
        if category == "optional":
            continue

        arg_type = arg.getAttr("type") if arg.hasAttr("type") else None
        kind = arg.getAttr("kind") if arg.hasAttr("kind") else None
        rank = arg.getAttr("dimensions") if arg.hasAttr("dimensions") else 0

        dims = None
        if category != "error_arg" and rank > 0:
            dims = _resolve_array_dims(arg, std_name_to_param)
            if dims is None:
                return None

        if category in ("in", "out", "inout"):
            any_captured = True

        params.append(TestDriverParam(pname, category, arg_type, kind, rank, dims))

    if not any_captured:
        return None
    return params


@dataclass(frozen=True)
class SchemeIOCapturePass(ModulePass):
    """See module docstring. Registered as "generate-scheme-io-capture";
    run at the same point generate-gpu-debug-prints does (after
    generate-gpu-data/generate-gpu-ccpp-cap/generate-suite-cap), since
    real KeywordCallOps for every scheme call only exist by then.

    One pass instance captures exactly one scheme (optionally restricted
    to one lifecycle phase) -- ccpp_dsl.py appends a separate pass
    instance per --capture-scheme entry when more than one is given,
    rather than packing a list into a single instance's params.
    """

    name = "generate-scheme-io-capture"

    scheme: str = ""
    phase: str = ""
    directive: "str | None" = None
    test_driver_dir: "str | None" = None

    def apply(self, ctx: Context, op: builtin.ModuleOp) -> None:
        if not self.scheme:
            return

        ccpp_mod = find_ccpp_module(op.body.block.ops)
        meta_data = {}
        mpi_root_ref = None
        if ccpp_mod is not None:
            bmdd = BuildMetaDataDescriptions()
            bmdd.traverse(ccpp_mod)
            meta_data = bmdd.meta_data
            host_var_index = build_host_var_index(ccpp_mod)
            entry = host_var_index.get(_MPI_ROOT_STD_NAME)
            if entry is not None:
                mpi_root_ref = (entry[0], entry[1])  # (var_name, module_name)

        # Tracks which enclosing suite-cap modules already have which
        # `use <module>, only: <name>` declarations inserted -- a capture
        # call's own raw text (RawFortranLinesOp, below) has no `use`
        # statement of its own, so without an explicit declaration the
        # enclosing module would never get one (see _ensure_capture_decl/
        # _ensure_host_var_decl). Keyed by (module_op id, name) since this
        # now tracks up to two distinct declarations per module: the
        # generic `ccpp_capture` name (always) and the host's mpi-root
        # flag (only when the host declares one). Both are idempotent per
        # module -- every capture call in a module shares the same
        # generic write name and the same mpi-root guard variable, so
        # neither needs inserting more than once there.
        declared_decls: set = set()

        # Accumulated across every matched call site (potentially several
        # phases of the same scheme, when self.phase == "" -- i.e. "every
        # phase"), keyed by table_name, so a single scheme-level test
        # driver can be emitted once, after the loop, covering every
        # captured phase -- not one driver per phase in isolation. See
        # _maybe_emit_test_driver's own docstring for why a single-phase
        # driver is not just a smaller version of this but can be
        # outright wrong (e.g. kessler_run depends on module state only
        # kessler_init, a separate phase, sets).
        captured_tables: dict = {}

        for if_op, call_op, scheme_name, phase, table_name in iter_scheme_call_sites(op):
            if scheme_name != self.scheme:
                continue
            if self.phase and phase != self.phase:
                continue
            if scheme_name not in meta_data or table_name not in meta_data[scheme_name].arg_tables:
                continue

            arg_table = meta_data[scheme_name].arg_tables[table_name]
            args_by_name = {a.name: a for a in arg_table.getFunctionArguments()}
            device_names = _device_arg_names(scheme_name, table_name, meta_data)
            param_names = _call_param_names(call_op, scheme_name, table_name, meta_data)
            if param_names is None:
                continue

            for value, param_name in zip(_call_args(call_op), param_names):
                arg = args_by_name.get(param_name)
                if arg is None:
                    continue
                if arg.hasAttr("optional"):
                    continue
                std_name = arg.getAttr("standard_name") if arg.hasAttr("standard_name") else None
                if std_name in CCPP_ERROR_STD_NAMES:
                    continue
                intent = arg.getAttr("intent") if arg.hasAttr("intent") else None
                if intent not in ("in", "out", "inout"):
                    continue
                arg_type = arg.getAttr("type") if arg.hasAttr("type") else None
                kind = arg.getAttr("kind") if arg.hasAttr("kind") else None
                rank = arg.getAttr("dimensions") if arg.hasAttr("dimensions") else 0
                if not _is_capture_supported(arg_type, kind, rank):
                    continue
                expr_text = _expr_text(value)
                if expr_text is None:
                    continue

                self._ensure_capture_decl(call_op, declared_decls)
                if mpi_root_ref is not None:
                    self._ensure_host_var_decl(call_op, mpi_root_ref[0], mpi_root_ref[1], declared_decls)
                mpi_root_var = mpi_root_ref[0] if mpi_root_ref is not None else None
                if intent in ("in", "inout"):
                    self._insert_capture(
                        value, expr_text, table_name, param_name, intent,
                        "before", param_name in device_names, call_op, mpi_root_var,
                    )
                if intent in ("out", "inout"):
                    self._insert_capture(
                        value, expr_text, table_name, param_name, intent,
                        "after", param_name in device_names, call_op, mpi_root_var,
                    )

            if self.test_driver_dir and table_name not in captured_tables:
                params = _build_test_driver_params(param_names, args_by_name)
                if params is None:
                    print(
                        f"generate-scheme-io-capture: skipping test-driver generation "
                        f"for {table_name} -- could not resolve one or more array "
                        f"dimensions, or nothing in this call site was actually captured.",
                        file=sys.stderr,
                    )
                else:
                    captured_tables[table_name] = (phase, params)

        if self.test_driver_dir and captured_tables:
            self._maybe_emit_test_driver(self.scheme, captured_tables)

    def _ensure_capture_decl(self, call_op, declared_decls: set) -> None:
        """Insert a declaration FuncOp for ccpp_capture_mod's generic
        `ccpp_capture` name, at the top level of call_op's enclosing
        suite-cap module -- exactly the same construction
        run_dispatch.py/lifecycle_cap.py use for a real scheme callee
        declaration (func.FuncOp.external + a `module` attribute), which
        is what print_ftn.py's _print_module reads to generate this
        module's own `use ccpp_capture_mod, only: ccpp_capture` line.
        Without this, a capture call's own raw text (RawFortranLinesOp)
        has no `use` statement backing it at all, and the module-mangled
        symbol ccpp_capture_mod actually compiles to is unresolvable at
        link time. Idempotent per module (declared_decls, keyed by
        (module id, "ccpp_capture")) -- every capture call in a module
        shares the one generic name, so this only ever needs inserting
        once there, not once per call.
        """
        module_op = _enclosing_module(call_op)
        if module_op is None:
            return
        key = (id(module_op), "ccpp_capture")
        if key in declared_decls:
            return
        declared_decls.add(key)
        decl = func.FuncOp.external("ccpp_capture", [], [])
        decl.attributes["module"] = StringAttr("ccpp_capture_mod")
        Rewriter.insert_op(decl, InsertPoint.at_end(module_op.body.block))

    def _ensure_host_var_decl(self, call_op, var_name: str, module: str, declared_decls: set) -> None:
        """Insert a declaration for a real host VARIABLE (not a callable),
        at the top level of call_op's enclosing suite-cap module -- the
        `llvm.GlobalOp` + `module` attribute construction real host-var
        references already use elsewhere (run_dispatch.py's own
        `hv_glob`), not func.FuncOp.external (that's for callable
        entities like ccpp_capture_mod's own procedures, see
        _ensure_capture_decl -- `masterproc` is a logical flag, not a
        subroutine/function, and print_ftn.py's _print_module reads
        `llvm.GlobalOp`'s own `module` attribute, not FuncOp's, to decide
        which `use <module>, only: <name>` lines to emit for a plain
        variable). Idempotent per (module, var_name) pair, same reasoning
        as _ensure_capture_decl.
        """
        module_op = _enclosing_module(call_op)
        if module_op is None:
            return
        key = (id(module_op), var_name)
        if key in declared_decls:
            return
        declared_decls.add(key)
        glob = llvm.GlobalOp(
            llvm.LLVMArrayType.from_size_and_type(1, i8),
            var_name, "external",
        )
        glob.attributes["module"] = StringAttr(module)
        Rewriter.insert_op(glob, InsertPoint.at_end(module_op.body.block))

    def _maybe_emit_test_driver(self, scheme_name, captured_tables: dict) -> None:
        """Write test_<scheme_name>.F90 into self.test_driver_dir, covering
        every phase in `captured_tables` ({table_name: (phase, params)})
        as ONE driver, in CCPP lifecycle order -- not one isolated driver
        per phase. This matters for correctness, not just convenience:
        confirmed directly against a real kessler build that a run-only
        driver for kessler_run spuriously fails every comparison, because
        kessler_run reads module-private state (lv/pref/rhoqr) that only
        a separate kessler_init call sets -- replaying a scheme's phases
        together, in order, is what makes the comparison meaningful.

        Hands the already-resolved TestDriverParam lists to print_ftn.py's
        render_scheme_io_capture_test_driver for the actual Fortran text
        -- this method and _build_test_driver_params never construct
        Fortran syntax themselves. Not a hard pipeline failure on any
        problem (unresolvable array dims, an unwritable directory): this
        is a developer convenience on top of the real capture calls
        above, which have already been inserted into the IR by this point
        regardless of what happens here.
        """
        ordered = sorted(
            captured_tables.items(),
            key=lambda item: _LIFECYCLE_PHASE_ORDER.get(item[1][0], len(_LIFECYCLE_PHASE_ORDER)),
        )
        phase_tables = [(table_name, params) for table_name, (_phase, params) in ordered]
        source = render_scheme_io_capture_test_driver(
            scheme_name, phase_tables, _TEST_DRIVER_TOLERANCE,
        )
        os.makedirs(self.test_driver_dir, exist_ok=True)
        out_path = os.path.join(self.test_driver_dir, f"test_{scheme_name}.F90")
        with open(out_path, "w") as f:
            f.write(source)

    def _insert_capture(
        self, value, expr_text, table_name, param_name, intent,
        timing, is_device, call_op, mpi_root_var,
    ) -> None:
        """Insert one capture call immediately before/after call_op
        (timing), syncing a device-resident argument to the host first if
        needed (same construction GPUDataPass's own debug_sync option
        uses -- cap_shared.directive_op -- reused rather than reinvented;
        not reusing any sync GPUDataPass may have already inserted
        elsewhere for an unrelated reason).

        Anchors are explicit, not "insert twice at the same InsertPoint",
        so the relative order of sync-then-capture is never ambiguous:
          timing="before": [sync?, capture, call_op]
          timing="after":  [call_op, sync?, capture]
        In both cases the sync (when present) always precedes the
        capture it's guarding, and the capture is always the op adjacent
        to call_op on the "before"/"after" side with no sync present.

        When `mpi_root_var` is given (the host's own mpi-root flag, e.g.
        `masterproc`), the capture call itself is wrapped in
        `if (<mpi_root_var>) then ... end if` -- confirmed necessary
        against a real 24-task CAM-SIMA build, where every task racing to
        write the same filename corrupted it. The device-sync above is
        deliberately left unguarded (every task still syncs its own
        device data to host): that's a pure per-task memory copy with no
        shared-file risk, so guarding it would only save a little work on
        non-root tasks, not fix a correctness problem. When
        `mpi_root_var` is None (the host declares no such standard name
        at all, e.g. the standalone examples/kessler), the call is
        unconditional, exactly as before this guard existed.
        """
        capture_anchor = (
            InsertPoint.before(call_op) if timing == "before" else InsertPoint.after(call_op)
        )
        if is_device and self.directive:
            sync_op = directive_op(
                self.directive,
                AccUpdateSelfOp, {"array_refs": [value]},
                OmpTargetUpdateFromOp, {"array_refs": [value]},
            )
            Rewriter.insert_op(sync_op, capture_anchor)
            capture_anchor = InsertPoint.after(sync_op)
        tag = f"{table_name}:{param_name}:{intent}:{timing}"
        call_text = f'call ccpp_capture("{tag}", {expr_text})'
        if mpi_root_var is not None:
            call_text = f"if ({mpi_root_var}) then\n  {call_text}\nend if"
        Rewriter.insert_op(RawFortranLinesOp(call_text), capture_anchor)
