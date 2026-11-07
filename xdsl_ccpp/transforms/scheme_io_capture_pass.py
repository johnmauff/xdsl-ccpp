"""Scheme I/O capture -- opt-in only, never emitted unless xdsl_ccpp's own
--capture-scheme CLI flag is passed (see ccpp_dsl.py).

scheme-io-capture (BACKLOG.md), design proposal at CHANGELOG.md's
"scheme-io-capture: scheme I/O capture + generated per-scheme unit tests"
section. Not a debugging aid and not compared against CAM's own
history-file output: the real goal is data-driven, scheme-level
regression tests built from realistic, captured atmospheric states,
independent of a full CAM build/run. Captures every (supported) input/
output argument of a chosen scheme (optionally restricted to some
lifecycle phases, `phase` = "initialize,run") to one NetCDF file per call (scheme-io-capture-netcdf:
<table>_<n>.nc, see ccpp_capture_mod.F90), by inserting calls into the
ccpp_capture_mod runtime Fortran library immediately before and after
the scheme's own call:
  - before: ccpp_capture_begin(table, 'before'), one
    ccpp_capture(name, value, standard_name, units, dim_names) per
    intent in/inout argument (group `in`), ccpp_capture_end().
  - after: the same with 'after' for intent out/inout (group `out`).
Each "before" block also records the capture's label (e.g. the CAM-SIMA
case name, --capture-label) and the generator version
(ccpp_capture_set_info), and the host's current_timestep_number when it
has one (ccpp_capture_attribute). With --capture-test-driver-dir, it starts
with ccpp_capture_set_dir(<that dir>) (the runtime appends /<label>), so the run writes its files
under the generated drivers, one subdirectory per label
(CCPP_CAPTURE_DIR in the run's environment overrides it).

Call-site discovery reuses cap_shared.iter_scheme_call_sites -- the same
machinery gpu_debug_print_pass.py's own Part C uses (extracted there
2026-10-17 specifically because this pass needed the identical logic).
This pass differs from that one in what it inserts (a capture call per
argument, not a diagnostic print) and where (every supported intent in/
out/inout argument, not just sliced device-resident ones).

Scope: {integer, logical, real(kind_phys)} x {rank 0..3}, plus character
scalars and rank-1 arrays -- in practice the cross product that appears
in CCPP metadata. Derived types listed in _DDT_CAPTURES (the constituent
properties, ccpp_constituent_prop_ptr_t) are captured by their own
procedure as a subgroup and rebuilt, not compared, in a driver.
Everything else (other derived types, any other real kind) is silently
skipped, not a hard error -- a scheme mixing supported and unsupported
arguments should still get the supported ones captured.
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
also emit a standalone `test_<table_name>.F90` program that replays
*every* real call a captured fixture contains for that phase -- not just
the first (scheme-io-capture-multi-timestep). A real multi-task CAM-SIMA
run routinely calls one scheme several times (once per chunk/timestep),
and a run-once replay was silently ignoring that captured data. The
generated driver loops `call_count = 1, 2, 3, ...`, opening each call's
file (ccpp_capture_open_call, whose `found` signals "no more captured
calls") and stopping there, calling the real scheme subroutine with each
call's own inputs (group `in`) and
comparing its outputs against that same call's captured 'after' snapshot
-- not against a fresh calculation. Declarations and the call's own keyword
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

Device residency (scheme-io-capture-gpu-residency): a generated driver is
a standalone program, with none of the surrounding suite-level device
residency a real cap can lean on -- so when --directive was set at
cap-generation time, _build_test_driver_params marks every
memory_space=device argument (TestDriverParam.is_device, via the same
cap_shared._device_arg_names lookup apply()'s own per-argument capture
loop already uses for this same call site) and the driver
(capture_driver_ir) wraps the real scheme call with its own `!$acc enter data`/
`!$omp target enter data` beforehand and the matching exit-data after --
without this, a real scheme's own `!$acc ... present(...)` checks (e.g.
kessler_run's) would abort the moment the driver tries to call it under
`-acc`. Without --directive the driver still uses OpenACC data
directives (inside #ifdef USE_GPU), for the memory_space=device
arguments and for `driver_device_args`: the arguments the scheme's own
OpenACC requires on the device (present, default(present)), which
ccpp_dsl reads from the .F90 when .meta says nothing. That list reaches
only the driver; the cap gets no directives without --directive.

The driver's own real-valued comparison tolerance defaults to zero
(bit for bit) but is overridable per invocation via
--capture-tolerance (scheme-io-capture-tolerance-config) -- uniform
across every real-valued comparison in the generated driver, no
per-variable override in v1. Threaded through as a quoted string in the
pass-pipeline spec (see ccpp_dsl.py's own comment on why: a bare
scientific-notation literal with no "." in it, e.g. "1e-08", trips the
pipeline parser's own int-vs-float NUMBER-token ambiguity) and re-parsed
with float() here, and becomes a real constant of kind kind_phys in the
driver's IR.

This file interprets CCPP metadata only (_driver_param_category,
_resolve_array_dims, _build_test_driver_params); the resolved
TestDriverParam lists go to capture_driver_ir.build_test_driver, which
builds the driver as IR (a ProgramOp, scheme-io-capture-driver-as-ir)
that print_ftn prints like any other unit -- no Fortran text is written
here or there.
"""

import functools
import os
import subprocess
from dataclasses import dataclass

from xdsl.context import Context
from xdsl.dialects import builtin, func, llvm
from xdsl.dialects.builtin import StringAttr, UnrealizedConversionCastOp, i1, i8, i32
from xdsl.passes import ModulePass
from xdsl.rewriter import InsertPoint, Rewriter
from xdsl.utils.hints import isa

from xdsl_ccpp.backend.print_ftn import print_fortran_unit
from xdsl_ccpp.transforms.capture_driver_ir import (
    TestDriverParam,
    build_test_driver,
    is_call_only_phase,
)
from xdsl_ccpp.dialects import ccpp
from xdsl_ccpp.dialects.ccpp_utils import (
    CallExprOp,
    AccUpdateSelfOp,
    AssignOp,
    CallStatementOp,
    MemberAccessExprOp,
    OmpTargetUpdateFromOp,
    StringLiteralExprOp,
    ValueExprOp,
    VarRefExprOp,
)
from xdsl_ccpp.transforms.util.cap_shared import (
    _call_args,
    _call_param_names,
    _device_arg_names,
    _scf_if,
    directive_op,
    has_definite_name,
    iter_scheme_call_sites,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import BuildMetaDataDescriptions
from xdsl_ccpp.transforms.util.ir_utils import build_host_var_index, find_ccpp_module
from xdsl_ccpp.util.ccpp_conventions import CCPP_ERROR_STD_NAMES, CCPP_KIND_PHYS
from xdsl_ccpp.util.errors import warn_once

# Default absolute tolerance used by every generated driver's real-valued
# comparisons, when --capture-tolerance isn't given (scheme-io-capture-
# tolerance-config): zero, so a replay is a bit-for-bit check (a ported
# scheme is expected to reproduce its capture exactly); --capture-tolerance
# or CCPP_CAPTURE_TOLERANCE at run time loosens it deliberately.
_TEST_DRIVER_TOLERANCE = 0.0

# CCPP standard name for "is this the MPI root/master task" -- CAM-SIMA
# exposes this via spmd_utils.F90's `masterproc`, already a widely-used
# real convention (dozens of real schemes consume it), unlike `mpi_rank`
# (also host-exposed, but not currently consumed by any real scheme).
# Used to guard every inserted capture call so only one task ever writes
# a given call's file -- confirmed directly against a real 24-task
# CAM-SIMA build that without this guard, every task races to write the
# same filename and corrupts it (a captured `ncol` decoded to garbage).
# Resolved once per `apply()` call via the host's own metadata (not a
# new MPI dependency in ccpp_capture_mod.F90 itself, which stays exactly
# as minimal as before); when the host doesn't declare this standard
# name at all (e.g. the standalone examples/kessler, which is
# single-task), the guard is simply omitted and every capture call runs
# unconditionally, which is already correct there.
_MPI_ROOT_STD_NAME = "flag_for_mpi_root"

# The host's log unit (scheme-io-capture-log-unit). Captured like any other
# integer, but the captured value is the host's own open unit (CAM's is a
# newunit= number such as -15), which is not open in a standalone test
# driver: the driver passes standard output instead and never compares it.
_LOG_UNIT_STD_NAME = "log_output_unit"

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


@dataclass(frozen=True)
class _DdtCapture:
    """How one derived type is captured (scheme-io-capture-ddt-args):
    `write` (module `module`) writes an argument of the type as subgroup
    in/<name> of the capture file, `read` rebuilds it in a generated
    driver; `type_module` declares the type. Only intent(in) arguments of
    rank `rank`: a derived type is rebuilt, never compared."""

    rank: int
    write: str
    read: str
    module: str
    type_module: str


# Derived types the capture handles, by type name. Others are skipped.
_DDT_CAPTURES = {
    "ccpp_constituent_prop_ptr_t": _DdtCapture(
        rank=1,
        write="ccpp_capture_constituents",
        read="ccpp_capture_read_constituents",
        module="ccpp_capture_constituents_mod",
        type_module="ccpp_constituent_prop_mod",
    ),
}


@functools.lru_cache(maxsize=None)
def parse_ddt_layouts(text: "str | None") -> dict:
    """The `ddt_layouts` option: "type@module=comp:base:rank:alloc,...;..."
    (ccpp_dsl, module_dependency_resolver.capture_layout) as {type:
    (module, ((comp, base, rank, allocatable), ...))}."""
    layouts: dict = {}
    for item in (text or "").split(";"):
        head, _, comps = item.strip().partition("=")
        type_name, _, module = head.partition("@")
        if not type_name or not module:
            continue
        components = []
        for comp in comps.split(","):
            name, base, rank, alloc = comp.split(":")
            components.append((name, base, int(rank), alloc == "1"))
        layouts[type_name.lower()] = (module, tuple(components))
    return layouts


def format_ddt_layouts(layouts) -> str:
    """parse_ddt_layouts' inverse, for CaptureLayouts."""
    return ";".join(
        f"{layout.type_name}@{layout.module}=" + ",".join(
            f"{name}:{base}:{rank}:{int(alloc)}" for name, base, rank, alloc in layout.components)
        for layout in layouts)


def _ddt_layout(arg, layouts: "dict | None") -> "tuple | None":
    """The (module, components) layout recording a derived-type argument
    component by component (scheme-io-capture-ddt-args): its type is in
    *layouts*, it is a scalar and has an intent."""
    if not layouts:
        return None
    arg_type = arg.getAttr("type") if arg.hasAttr("type") else None
    layout = layouts.get((arg_type or "").lower())
    if layout is None:
        return None
    rank = arg.getAttr("dimensions") if arg.hasAttr("dimensions") else 0
    intent = arg.getAttr("intent") if arg.hasAttr("intent") else None
    if rank != 0 or intent not in ("in", "out", "inout"):
        return None
    return layout


def _ddt_capture(arg) -> "_DdtCapture | None":
    """The _DDT_CAPTURES entry for a capturable derived-type argument:
    its type is in the table, its rank matches and it is intent(in)."""
    arg_type = arg.getAttr("type") if arg.hasAttr("type") else None
    handler = _DDT_CAPTURES.get(arg_type)
    if handler is None:
        return None
    rank = arg.getAttr("dimensions") if arg.hasAttr("dimensions") else 0
    intent = arg.getAttr("intent") if arg.hasAttr("intent") else None
    if rank != handler.rank or intent != "in":
        return None
    return handler
# Character values: scalars and rank-1 arrays (scheme-io-capture-netcdf).
_MAX_CHARACTER_RANK = 1

# ccpp_capture_mod procedures a capture call site uses.
_CAPTURE_PROCEDURES = (
    "ccpp_capture_set_info", "ccpp_capture_begin", "ccpp_capture", "ccpp_capture_end",
)
# Called first in each "before" block when a driver directory is set, so the
# run writes its files under it (CCPP_CAPTURE_DIR still wins).
_SET_DIR_PROCEDURE = "ccpp_capture_set_dir"
# Writes a global attribute: the host's timestep number, when it has one.
_ATTRIBUTE_PROCEDURE = "ccpp_capture_attribute"
_STEP_STD_NAME = "current_timestep_number"

# The run's constituent table (scheme-io-capture-constituent-index-table):
# the host cap's constituent-properties array (_CONSTITUENT_PROPS_VAR, which
# it hands to ccpp_scheme_utils for ccpp_constituent_index lookups) is
# captured once, when the cap fills it, as call 1 of this table, subgroup
# in/<_CONSTITUENT_TABLE_ARG>. Every test driver restores it into
# ccpp_scheme_utils before replaying (ccpp_capture_restore_constituents).
_CONSTITUENT_TABLE = "ccpp_constituents"
_CONSTITUENT_TABLE_ARG = "constituents"
_CONSTITUENT_PROPS_VAR = "lc_const_props"


@functools.lru_cache(maxsize=1)
def _generator_version() -> str:
    """'xdsl_ccpp <version>', plus the commit of a git checkout (local
    state only), for the ccpp_generator attribute of each capture file."""
    from importlib import metadata

    try:
        text = f"xdsl_ccpp {metadata.version('xdsl-ccpp')}"
    except metadata.PackageNotFoundError:
        text = "xdsl_ccpp"
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True, text=True, timeout=10, check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        commit = ""
    return f"{text} ({commit})" if commit else text


# Real kinds captured by default: kind_phys only (see _phys_real_kinds).
_PHYS_REAL_KINDS = frozenset({CCPP_KIND_PHYS})


def _phys_real_kinds(ccpp_mod) -> "frozenset[str]":
    """The real kinds the capture handles as kind_phys
    (scheme-io-capture-real-kinds), from the @ccpp module's `ccpp.kinds`
    (generate-meta-kinds): kind_phys, any kind with kind_phys's
    iso_fortran_env value (e.g. r8 => REAL64), and any kind a metadata
    kind_spec imports from a module (e.g. PUMAS's pumas_r8 =>
    pumas_kinds:kind_r8). A kind_spec kind's value is not known here: the
    capture calls are generic over kind_phys, so if it differs, a capture
    build (never a normal one) stops at compile time with no matching
    specific procedure."""
    kinds = {CCPP_KIND_PHYS}
    if ccpp_mod is None:
        return frozenset(kinds)
    kind_ops = [op for op in ccpp_mod.walk() if isinstance(op, ccpp.KindOp)]
    values = {
        op.kind_name.data: (op.kind_value.data, op.kind_module.data) for op in kind_ops
    }
    phys = values.get(CCPP_KIND_PHYS)
    for name, (value, module) in values.items():
        if module.lower() != "iso_fortran_env":
            kinds.add(name)
        elif phys is not None and phys[1].lower() == "iso_fortran_env" and value == phys[0]:
            kinds.add(name)
    return frozenset(kinds)


def _is_capture_supported(
    arg_type: "str | None", kind: "str | None", rank: int,
    real_kinds: "frozenset[str]" = _PHYS_REAL_KINDS,
) -> bool:
    """True iff this argument's (type, kind, rank) is within v1's capture
    scope -- {integer, logical, real of a kind in *real_kinds*} x
    {rank 0..3}; *real_kinds* are kind_phys and the kinds equal to it
    (_phys_real_kinds). The
    emitted capture call always uses ccpp_capture_mod's generic
    `ccpp_capture` name (Fortran's own overload resolution picks the
    right concrete procedure from the argument's static type and rank;
    there's exactly one real-kind member per rank, kind_phys, which a real
    of an equal kind resolves to) -- this function only gates whether to capture at all,
    it no longer needs to name a concrete procedure itself."""
    if arg_type == "character":
        return rank <= _MAX_CHARACTER_RANK
    if rank > _MAX_SUPPORTED_RANK:
        return False
    if arg_type == "real":
        return kind in real_kinds
    return arg_type in _TYPE_CODE


# Fortran's intrinsic types; any other metadata `type` is a derived type.
_INTRINSIC_TYPES = frozenset({"integer", "real", "logical", "character", "complex"})


def _driver_param_category(arg, real_kinds: "frozenset[str]" = _PHYS_REAL_KINDS,
                           layouts: "dict | None" = None) -> str:
    """Classify one real call argument for test-driver generation:
    "optional" (omit from the generated call entirely), "error_arg"
    (errmsg/errflg -- always declared and passed, never compared),
    "unverified" (mandatory but outside this pass's v1 capture type scope
    -- still declared and passed so the call compiles, never compared),
    "log_unit" (the host's log unit -- the driver passes its own standard
    output unit, never the captured value, and never compares it),
    or "in"/"out"/"inout" (a real captured argument -- matches exactly
    what apply()'s own per-argument capture loop would do for it)."""
    if arg.hasAttr("optional"):
        return "optional"
    std_name = arg.getAttr("standard_name") if arg.hasAttr("standard_name") else None
    if std_name in CCPP_ERROR_STD_NAMES:
        return "error_arg"
    if std_name == _LOG_UNIT_STD_NAME:
        return "log_unit"
    intent = arg.getAttr("intent") if arg.hasAttr("intent") else None
    if intent not in ("in", "out", "inout"):
        return "unverified"
    arg_type = arg.getAttr("type") if arg.hasAttr("type") else None
    kind = arg.getAttr("kind") if arg.hasAttr("kind") else None
    rank = arg.getAttr("dimensions") if arg.hasAttr("dimensions") else 0
    if (not _is_capture_supported(arg_type, kind, rank, real_kinds)
            and _ddt_capture(arg) is None and _ddt_layout(arg, layouts) is None):
        return "unverified"
    return intent


def _has_top_level_symbol(module_op, name: str) -> bool:
    """Whether *module_op* already declares symbol *name* at its top level:
    one pass instance runs per --capture-scheme entry, and all of them
    declare the same capture procedures and mpi-root flag."""
    for op in module_op.body.block.ops:
        sym = op.properties.get("sym_name")
        if sym is not None and sym.data == name:
            return True
    return False


def _attr_text(arg, name: str) -> str:
    """A metadata argument's attribute as text, "" when absent."""
    return str(arg.getAttr(name)) if arg.hasAttr(name) else ""


def _capture_dim_names(arg) -> "list[str]":
    """The capture file's dimension names for an array argument: its
    metadata dimensions (standard names), a `lower:upper` range named by
    its upper bound (as _resolve_array_dims does). [] for a scalar or when
    the metadata has none (the runtime then names them <var>_dim<i>)."""
    if not arg.hasAttr("dim_names"):
        return []
    names = []
    for raw in arg.getAttr("dim_names"):
        name = raw.strip()
        if ":" in name:
            name = name.split(":")[-1].strip()
        names.append(name)
    return names


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


def _constituent_props_assignment(op) -> "AssignOp | None":
    """The host cap's `lc_const_props = ...` (constituent_cap.py's
    register-constituents subroutine; a member of lc_instances(i) in a
    multi-instance cap), or None."""
    for candidate in op.walk():
        if not isa(candidate, AssignOp):
            continue
        lhs = candidate.lhs.block.first_op
        if isa(lhs, VarRefExprOp) and lhs.var_name.data == _CONSTITUENT_PROPS_VAR:
            return candidate
        if isa(lhs, MemberAccessExprOp) and lhs.member.data == _CONSTITUENT_PROPS_VAR:
            return candidate
    return None


def _captures_constituent_table(op) -> bool:
    """Whether a capture of the constituent table is already in *op*."""
    for candidate in op.walk():
        if not isa(candidate, CallStatementOp) or candidate.callee.data != "ccpp_capture_begin":
            continue
        first = candidate.arg_exprs[0].block.first_op
        if isa(first, StringLiteralExprOp) and first.text.data == _CONSTITUENT_TABLE:
            return True
    return False


def _uncast(value):
    """The value a chain of one-input type casts converts (a fixed-length
    character variable passed to a character(len=*) dummy), or value."""
    while isa(value.owner, UnrealizedConversionCastOp) and len(value.owner.inputs) == 1:
        value = value.owner.inputs[0]
    return value


def _callee_module(call_op, table_name: str, default: str) -> str:
    """The Fortran module of the scheme subroutine `table_name`, from its
    declaration in call_op's enclosing module (the cap's `use <module>,
    only: <table>`). Several schemes can share one module (CAM-SIMA's
    state_converters), so the scheme name is only the fallback."""
    module_op = _enclosing_module(call_op)
    if module_op is not None:
        for op in module_op.body.block.ops:
            sym = op.properties.get("sym_name")
            module = op.attributes.get("module")
            if sym is not None and sym.data == table_name and module is not None:
                return module.data
    return default


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
    param_names: list, args_by_name: dict, device_names: "set[str]",
    real_kinds: "frozenset[str]" = _PHYS_REAL_KINDS,
    layouts: "dict | None" = None,
) -> "tuple[list[TestDriverParam] | None, str]":
    """Resolve CCPP metadata for one real scheme call site into the
    TestDriverParam list capture_driver_ir.build_test_driver needs -- all CCPP-specific
    interpretation (intent, optionality, dim_names resolution) happens
    here, not in the printer. Returns (params, ""), or (None, reason) --
    the caller skips this phase and reports the reason
    (scheme-io-capture-skip-message) -- if an uncaptured array argument's
    dimensions can't be resolved, or if nothing in this call site is
    captured and it needs an argument the driver cannot supply itself. A phase with nothing captured whose
    arguments are all driver-supplied (errmsg/errflg, the log unit) is
    returned as a call-only phase (print_ftn.is_call_only_phase,
    scheme-io-capture-uncaptured-phases): e.g. an `_init` that only sets
    module state the `_run` replay reads.

    `device_names` (scheme-io-capture-gpu-residency) is the identical
    cap_shared._device_arg_names lookup apply()'s own per-argument loop
    already computes for this same call site, reused here (not
    re-derived) -- a param's own `is_device` flag is just membership in
    this set, and print_ftn.py uses it to decide whether the driver needs
    to establish/tear down a device copy of that argument around the call.
    """
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
            return None, f"argument '{pname}' has no metadata"
        category = _driver_param_category(arg, real_kinds, layouts)
        if category == "optional":
            continue

        arg_type = arg.getAttr("type") if arg.hasAttr("type") else None
        kind = arg.getAttr("kind") if arg.hasAttr("kind") else None
        rank = arg.getAttr("dimensions") if arg.hasAttr("dimensions") else 0

        # A captured array is sized from the capture file; only an array
        # the driver passes through uncaptured needs its size from other
        # arguments.
        dims = None
        if category == "unverified" and rank > 0:
            dims = _resolve_array_dims(arg, std_name_to_param)
            if dims is None:
                return None, _unresolved_dims_reason(pname, arg, std_name_to_param)
        handler = _ddt_capture(arg)
        layout = _ddt_layout(arg, layouts)
        if (handler is None and layout is None and arg_type is not None
                and arg_type.lower() not in _INTRINSIC_TYPES):
            # The capture does not record it, so the driver could only pass
            # an undefined object (scheme-io-capture-ddt-args).
            return None, (
                f"argument '{pname}' is of derived type {arg_type}, which the "
                f"capture does not record (scheme-io-capture-ddt-args)"
            )

        if category in ("in", "out", "inout"):
            any_captured = True

        params.append(TestDriverParam(
            pname, category, arg_type, kind, rank, dims,
            pname in device_names and handler is None and layout is None,
            ddt_read=handler.read if handler else None,
            ddt_read_module=handler.module if handler else None,
            type_module=(handler.type_module if handler else
                         layout[0] if layout else None),
            components=layout[1] if layout else (),
        ))

    if not any_captured and not is_call_only_phase(params):
        needed = next(p for p in params if p.category not in ("error_arg", "log_unit"))
        return None, (
            f"nothing in it is captured, and the driver cannot supply argument "
            f"'{needed.name}' ({_type_text(args_by_name[needed.name])})"
        )
    return params, ""


def _type_text(arg) -> str:
    """An argument's metadata type for a message, e.g. `real, kind
    pumas_r8, rank 2`."""
    parts = [_attr_text(arg, "type") or "unknown type"]
    if _attr_text(arg, "kind"):
        parts.append(f"kind {_attr_text(arg, 'kind')}")
    rank = arg.getAttr("dimensions") if arg.hasAttr("dimensions") else 0
    if rank:
        parts.append(f"rank {rank}")
    return ", ".join(parts)


def _unresolved_dims_reason(pname: str, arg, std_name_to_param: dict) -> str:
    """Why _resolve_array_dims failed for an uncaptured array argument."""
    names = [n.strip() for n in arg.getAttr("dim_names")] if arg.hasAttr("dim_names") else []
    missing = [
        n for n in names
        if std_name_to_param.get(n.split(":")[-1].strip()) is None
    ]
    where = (
        f"its dimension '{missing[0]}' is not an argument of the call"
        if missing else "its dimensions are unknown"
    )
    return (
        f"argument '{pname}' ({_type_text(arg)}) is outside the capture's type "
        f"scope, so the driver must size it from the other arguments, but {where}"
    )


@dataclass(frozen=True)
class SchemeIOCapturePass(ModulePass):
    """See module docstring. Registered as "generate-scheme-io-capture";
    run at the same point generate-gpu-debug-prints does (after
    generate-gpu-data/generate-gpu-ccpp-cap/generate-suite-cap), since
    real KeywordCallOps for every scheme call only exist by then.

    One pass instance captures exactly one scheme (optionally restricted
    to the comma-separated lifecycle phases in `phase`) -- ccpp_dsl.py appends a separate pass
    instance per --capture-scheme entry when more than one is given,
    rather than packing a list into a single instance's params.
    """

    name = "generate-scheme-io-capture"

    scheme: str = ""
    phase: str = ""
    directive: "str | None" = None
    test_driver_dir: "str | None" = None
    # The capture's label (e.g. the CAM-SIMA case name): written into each
    # file, and with test_driver_dir the files go to <test_driver_dir>/<label>.
    label: "str | None" = None
    # A string, not a float: ccpp_dsl.py passes this through the
    # pass-pipeline spec as a quoted string specifically to dodge that
    # parser's own int-vs-float NUMBER-token ambiguity for an exponent
    # literal with no "." in it (e.g. "1e-08") -- re-parsed with float()
    # at the one place it's actually used (_maybe_emit_test_driver).
    tolerance: "str | None" = None
    # "table:arg,..." -- without --directive, the arguments the scheme's own
    # OpenACC requires on the device (ccpp_dsl, from the source check).
    # Used only for the generated test driver's enter/exit data: the cap
    # gets no directives without --directive.
    driver_device_args: "str | None" = None
    # scheme-io-capture-module-state-setup: "scheme:phase,..." -- other
    # schemes' phases that set module state this scheme reads; the test
    # driver replays their captured calls first, not compared (ccpp_dsl
    # captures them too).
    setup: "str | None" = None
    # "setup": an instance capturing a phase only for other schemes'
    # drivers -- no driver, no report of its own.
    role: str = ""
    # scheme-io-capture-ddt-args: derived types recorded component by
    # component (parse_ddt_layouts), from ccpp_dsl's reading of their
    # Fortran definitions.
    ddt_layouts: "str | None" = None

    def _setup_phases(self) -> "set[tuple[str, str]]":
        pairs = set()
        for item in (self.setup or "").split(","):
            scheme, _, phase = item.strip().partition(":")
            if scheme and phase:
                pairs.add((scheme, phase))
        return pairs

    def _driver_device_names(self, table_name: str) -> "set[str]":
        names = set()
        for item in (self.driver_device_args or "").split(","):
            table, _, arg = item.strip().partition(":")
            if arg and table.lower() == table_name.lower():
                names.add(arg.lower())
        return names

    def apply(self, ctx: Context, op: builtin.ModuleOp) -> None:
        if not self.scheme:
            return

        ccpp_mod = find_ccpp_module(op.body.block.ops)
        meta_data = {}
        real_kinds = _PHYS_REAL_KINDS
        mpi_root_ref = None
        step_ref = None
        if ccpp_mod is not None:
            real_kinds = _phys_real_kinds(ccpp_mod)
            bmdd = BuildMetaDataDescriptions()
            bmdd.traverse(ccpp_mod)
            meta_data = bmdd.meta_data
            host_var_index = build_host_var_index(ccpp_mod)
            entry = host_var_index.get(_MPI_ROOT_STD_NAME)
            if entry is not None:
                mpi_root_ref = (entry[0], entry[1])  # (var_name, module_name)
            entry = host_var_index.get(_STEP_STD_NAME)
            if entry is not None:
                step_ref = (entry[0], entry[1])

        # Tracks which enclosing suite-cap modules already have which
        # `use <module>, only: <name>` declarations inserted -- a capture
        # call (a CallStatementOp, below) has no `use`
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
        # {table_name: reason} for phases left out of the driver.
        skipped: dict = {}
        captured_any = False
        setup_phases = self._setup_phases()
        layouts = parse_ddt_layouts(self.ddt_layouts)
        setup_tables: dict = {}  # in suite order: {table_name: (params, module)}

        for if_op, call_op, scheme_name, phase, table_name in iter_scheme_call_sites(op):
            if (scheme_name, phase) in setup_phases and self.test_driver_dir:
                self._add_setup_table(call_op, scheme_name, table_name, meta_data,
                                      real_kinds, setup_tables, skipped)
            if scheme_name != self.scheme:
                continue
            if self.phase and phase not in self.phase.split(","):
                continue
            if scheme_name not in meta_data or table_name not in meta_data[scheme_name].arg_tables:
                continue

            arg_table = meta_data[scheme_name].arg_tables[table_name]
            args_by_name = {a.name: a for a in arg_table.getFunctionArguments()}
            device_names = _device_arg_names(scheme_name, table_name, meta_data)
            param_names = _call_param_names(call_op, scheme_name, table_name, meta_data)
            if param_names is None:
                continue

            # (value, param name, metadata arg, device-resident?) captured
            # before / after the call.
            before: list = []
            after: list = []
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
                handler = _ddt_capture(arg)
                layout = _ddt_layout(arg, layouts)
                if (not _is_capture_supported(arg_type, kind, rank, real_kinds)
                        and handler is None and layout is None):
                    continue
                # A character(len=*) argument arrives through a cast of the
                # fixed-length variable; capture that variable.
                value = _uncast(value)
                # Only definite references can be captured.
                if not has_definite_name(value):
                    continue
                if handler is not None:
                    self._ensure_decl(call_op, handler.write, handler.module, declared_decls)
                if layout is not None:
                    for procedure in ("ccpp_capture_begin_ddt", "ccpp_capture_end_ddt"):
                        self._ensure_decl(call_op, procedure, "ccpp_capture_mod", declared_decls)

                # A derived type lives on the host: no device sync.
                entry = (value, param_name, arg,
                         param_name in device_names and handler is None and layout is None)
                if intent in ("in", "inout"):
                    before.append(entry)
                if intent in ("out", "inout"):
                    after.append(entry)

            if before or after:
                captured_any = True
                self._ensure_capture_decl(call_op, declared_decls, step_ref is not None)
                for ref in (mpi_root_ref, step_ref):
                    if ref is not None:
                        self._ensure_host_var_decl(call_op, ref[0], ref[1], declared_decls)
                mpi_root_var = mpi_root_ref[0] if mpi_root_ref is not None else None
                step_var = step_ref[0] if step_ref is not None else None
                self._insert_captures(table_name, "before", before, call_op, mpi_root_var, step_var)
                self._insert_captures(table_name, "after", after, call_op, mpi_root_var)
                data_dir = self._data_dir()
                if data_dir:
                    # The model cannot create it; it must exist before the run.
                    os.makedirs(data_dir, exist_ok=True)

            if self.test_driver_dir and table_name not in captured_tables:
                driver_device = device_names | {
                    p for p in param_names if p.lower() in self._driver_device_names(table_name)
                }
                params, reason = _build_test_driver_params(
                    param_names, args_by_name, driver_device, real_kinds, layouts,
                )
                if params is None:
                    skipped[table_name] = reason
                else:
                    module = _callee_module(call_op, table_name, scheme_name)
                    captured_tables[table_name] = (phase, params, module)

        if captured_any:
            self._capture_constituent_table(op, mpi_root_ref, declared_decls)

        # A driver needs at least one compared phase; call-only phases
        # (scheme-io-capture-uncaptured-phases) only set up for those.
        if self.test_driver_dir and self.role != "setup":
            if any(
                not is_call_only_phase(params)
                for _phase, params, _module in captured_tables.values()
            ):
                self._maybe_emit_test_driver(self.scheme, captured_tables, setup_tables)
                self._report_skipped(skipped)
            else:
                # No driver: one an earlier generation wrote is stale (and
                # would get a CMake fragment).
                stale = os.path.join(self.test_driver_dir, f"test_{self.scheme}.F90")
                if os.path.exists(stale):
                    os.remove(stale)
                if skipped:
                    self._report_skipped(skipped, f"no test_{self.scheme}.F90 written")
                elif captured_tables:
                    self._report_skipped({}, (
                        f"no test_{self.scheme}.F90 written: its phases have nothing "
                        f"captured, so there is nothing to compare"
                    ))

    def _report_skipped(self, skipped: dict, no_driver: "str | None" = None) -> None:
        """scheme-io-capture-skip-message: warn about each phase left out of
        the test driver, and list them in test_<scheme>.skipped next to the
        drivers (removed when nothing is skipped). The file is what the user
        sees: in CAM-SIMA the warnings appear only in the case.build output
        (generation runs in buildnml), not in atm.bldlog. *no_driver* says
        why no driver was written at all."""
        path = os.path.join(self.test_driver_dir, f"test_{self.scheme}.skipped")
        if not skipped and no_driver is None:
            if os.path.exists(path):
                os.remove(path)
            return
        lines = []
        for table_name, reason in skipped.items():
            warn_once(f"scheme I/O capture: {table_name} left out of the test driver: {reason}")
            lines.append(f"{table_name}: {reason}")
        if no_driver is not None:
            warn_once(f"scheme I/O capture: {self.scheme}: {no_driver}")
            lines.append(f"{self.scheme}: {no_driver}")
        os.makedirs(self.test_driver_dir, exist_ok=True)
        with open(path, "w") as f:
            f.write(
                f"# Generated by xdsl_ccpp: phases of {self.scheme} left out of "
                f"test_{self.scheme}.F90, and why.\n"
            )
            f.write("\n".join(lines) + "\n")

    def _capture_constituent_table(self, op, mpi_root_ref, declared_decls: set) -> None:
        """Capture the host cap's constituent-properties array once, right
        after the cap fills it at constituent registration
        (scheme-io-capture-constituent-index-table): schemes look
        constituents up by standard name (ccpp_constituent_index), which a
        test driver can only answer with the run's table. Inserted by the
        first pass instance only (one per --capture-scheme entry); nothing
        when the cap has no constituent table (no constituent API)."""
        assign = _constituent_props_assignment(op)
        if assign is None or _captures_constituent_table(op):
            return
        for procedure in ("ccpp_capture_begin", "ccpp_capture_end") + (
            (_SET_DIR_PROCEDURE,) if self.test_driver_dir else ()
        ) + ("ccpp_capture_set_info",):
            self._ensure_decl(assign, procedure, "ccpp_capture_mod", declared_decls)
        handler = _DDT_CAPTURES["ccpp_constituent_prop_ptr_t"]
        self._ensure_decl(assign, handler.write, handler.module, declared_decls)
        if mpi_root_ref is not None:
            self._ensure_host_var_decl(assign, mpi_root_ref[0], mpi_root_ref[1], declared_decls)

        writes = self._preamble_ops() + [
            CallStatementOp("ccpp_capture_begin", arg_ops=[
                StringLiteralExprOp(_CONSTITUENT_TABLE), StringLiteralExprOp("before"),
            ]),
            CallStatementOp(handler.write, arg_ops=[
                StringLiteralExprOp(_CONSTITUENT_TABLE_ARG),
                assign.lhs.block.first_op.clone(),
            ]),
            CallStatementOp("ccpp_capture_end", arg_ops=[]),
        ]
        if mpi_root_ref is not None:
            writes = _scf_if(VarRefExprOp(mpi_root_ref[0], result_type=i1), writes)
        anchor = InsertPoint.after(assign)
        for new_op in writes:
            Rewriter.insert_op(new_op, anchor)
            anchor = InsertPoint.after(new_op)
        data_dir = self._data_dir()
        if data_dir:
            os.makedirs(data_dir, exist_ok=True)

    def _preamble_ops(self) -> list:
        """The calls that start a capture file: ccpp_capture_set_dir (with
        a driver directory: the runtime appends the label, from
        ccpp_capture_set_info, which keeps each literal short) and
        ccpp_capture_set_info(label, generator)."""
        ops = []
        if self.test_driver_dir:
            ops.append(CallStatementOp(
                _SET_DIR_PROCEDURE,
                arg_ops=[StringLiteralExprOp(os.path.abspath(self.test_driver_dir))],
            ))
        ops.append(CallStatementOp("ccpp_capture_set_info", arg_ops=[
            StringLiteralExprOp(self.label or ""),
            StringLiteralExprOp(_generator_version()),
        ]))
        return ops

    def _data_dir(self) -> "str | None":
        """Where the run writes its files unless CCPP_CAPTURE_DIR is set:
        <test_driver_dir>/<label>, or test_driver_dir without a label;
        None without a driver directory (the run's working directory)."""
        if not self.test_driver_dir:
            return None
        driver_dir = os.path.abspath(self.test_driver_dir)
        return os.path.join(driver_dir, self.label) if self.label else driver_dir

    def _ensure_capture_decl(self, call_op, declared_decls: set, with_attribute: bool = False) -> None:
        """Insert declaration FuncOps for the ccpp_capture_mod procedures a
        capture call site uses (_CAPTURE_PROCEDURES), at the top level of call_op's enclosing
        suite-cap module -- exactly the same construction
        run_dispatch.py/lifecycle_cap.py use for a real scheme callee
        declaration (func.FuncOp.external + a `module` attribute), which
        is what print_ftn.py's _print_module reads to generate this
        module's own `use ccpp_capture_mod, only: ccpp_capture` line.
        Without this, a capture call (a CallStatementOp) has no `use`
        statement backing it at all, and the module-mangled
        symbol ccpp_capture_mod actually compiles to is unresolvable at
        link time. Idempotent per module (declared_decls, keyed by
        (module id, "ccpp_capture")) -- every capture call in a module
        shares the one generic name, so this only ever needs inserting
        once there, not once per call.
        """
        module_op = _enclosing_module(call_op)
        if module_op is None:
            return
        procedures = _CAPTURE_PROCEDURES
        if self.test_driver_dir:
            procedures = (_SET_DIR_PROCEDURE,) + procedures
        if with_attribute:
            procedures = procedures + (_ATTRIBUTE_PROCEDURE,)
        for procedure in procedures:
            self._ensure_decl(call_op, procedure, "ccpp_capture_mod", declared_decls)

    def _ensure_decl(self, call_op, procedure: str, module: str, declared_decls: set) -> None:
        """Declare `procedure` of `module` once at the top level of
        call_op's enclosing module (see _ensure_capture_decl)."""
        module_op = _enclosing_module(call_op)
        if module_op is None:
            return
        key = (id(module_op), procedure)
        if key in declared_decls:
            return
        declared_decls.add(key)
        if _has_top_level_symbol(module_op, procedure):
            return  # declared by another --capture-scheme instance
        decl = func.FuncOp.external(procedure, [], [])
        decl.attributes["module"] = StringAttr(module)
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
        if _has_top_level_symbol(module_op, var_name):
            return  # declared by another --capture-scheme instance
        glob = llvm.GlobalOp(
            llvm.LLVMArrayType.from_size_and_type(1, i8),
            var_name, "external",
        )
        glob.attributes["module"] = StringAttr(module)
        Rewriter.insert_op(glob, InsertPoint.at_end(module_op.body.block))

    def _add_setup_table(self, call_op, scheme_name, table_name, meta_data, real_kinds,
                         setup_tables: dict, skipped: dict) -> None:
        """Add another scheme's call site that sets module state this
        scheme reads (scheme-io-capture-module-state-setup) to
        *setup_tables*, or why it cannot be replayed to *skipped*."""
        if table_name in setup_tables or scheme_name not in meta_data:
            return
        arg_tables = meta_data[scheme_name].arg_tables
        if table_name not in arg_tables:
            return
        args_by_name = {a.name: a for a in arg_tables[table_name].getFunctionArguments()}
        param_names = _call_param_names(call_op, scheme_name, table_name, meta_data)
        if param_names is None:
            return
        device = _device_arg_names(scheme_name, table_name, meta_data) | {
            p for p in param_names if p.lower() in self._driver_device_names(table_name)
        }
        params, reason = _build_test_driver_params(param_names, args_by_name, device, real_kinds,
                                                   parse_ddt_layouts(self.ddt_layouts))
        if params is None:
            skipped[table_name] = (
                f"not replayed before the scheme's phases, so module state it sets "
                f"is unset in the replay: {reason}"
            )
        else:
            setup_tables[table_name] = (params, _callee_module(call_op, table_name, scheme_name))

    def _maybe_emit_test_driver(self, scheme_name, captured_tables: dict,
                                setup_tables: "dict | None" = None) -> None:
        """Write test_<scheme_name>.F90 into self.test_driver_dir, covering
        every phase in `captured_tables` ({table_name: (phase, params,
        module)}, module being the scheme subroutine's Fortran module)
        as ONE driver, in CCPP lifecycle order -- not one isolated driver
        per phase. This matters for correctness, not just convenience:
        confirmed directly against a real kessler build that a run-only
        driver for kessler_run spuriously fails every comparison, because
        kessler_run reads module-private state (lv/pref/rhoqr) that only
        a separate kessler_init call sets -- replaying a scheme's phases
        together, in order, is what makes the comparison meaningful.

        Builds the driver as IR (capture_driver_ir.build_test_driver) and
        prints it with print_ftn.print_fortran_unit. Not a hard pipeline failure on any
        problem (unresolvable array dims, an unwritable directory): this
        is a developer convenience on top of the real capture calls
        above, which have already been inserted into the IR by this point
        regardless of what happens here.
        """
        ordered = sorted(
            captured_tables.items(),
            key=lambda item: _LIFECYCLE_PHASE_ORDER.get(item[1][0], len(_LIFECYCLE_PHASE_ORDER)),
        )
        phase_tables = [
            (table_name, params, module) for table_name, (_phase, params, module) in ordered
        ]
        tolerance = float(self.tolerance) if self.tolerance is not None else _TEST_DRIVER_TOLERANCE
        # The driver always carries device data directives (OpenACC unless
        # --directive says otherwise), inside #ifdef USE_GPU: one driver
        # replays a capture on CPU and, built with OpenACC, on GPU.
        program = build_test_driver(
            scheme_name, phase_tables, tolerance, self.directive or "acc",
            [(table, params, module)
             for table, (params, module) in (setup_tables or {}).items()],
        )
        os.makedirs(self.test_driver_dir, exist_ok=True)
        out_path = os.path.join(self.test_driver_dir, f"test_{scheme_name}.F90")
        with open(out_path, "w") as f:
            print_fortran_unit(program, f)

    @staticmethod
    def _component_captures(value, param_name, arg, components) -> list:
        """A derived-type argument recorded component by component
        (scheme-io-capture-ddt-args): its components in sub-group
        <param_name>, an allocatable one only when allocated."""
        ops = [CallStatementOp("ccpp_capture_begin_ddt",
                               arg_ops=[StringLiteralExprOp(param_name)])]
        for comp, _base, _rank, allocatable in components:
            member = lambda c=comp: MemberAccessExprOp(ValueExprOp(value), c)
            capture = CallStatementOp("ccpp_capture", arg_ops=[
                StringLiteralExprOp(comp),
                member(),
                StringLiteralExprOp(_attr_text(arg, "standard_name")),
                StringLiteralExprOp(""),
                StringLiteralExprOp(""),
            ])
            if allocatable:
                ops += _scf_if(CallExprOp("allocated", [member()], result_type=i1), [capture])
            else:
                ops.append(capture)
        ops.append(CallStatementOp("ccpp_capture_end_ddt", arg_ops=[]))
        return ops

    def _insert_captures(self, table_name, timing, entries, call_op, mpi_root_var, step_var=None) -> None:
        """Insert one file's worth of capture calls immediately before
        (timing="before") or after (timing="after") call_op:

            [sync, ...]                          -- device-resident values
            if (<mpi_root_var>) then             -- when the host has one
              call ccpp_capture_set_dir(driver dir)  -- "before", with a driver dir
              call ccpp_capture_set_info(label, generator)  -- "before"
              call ccpp_capture_begin(table, timing)
              call ccpp_capture_attribute('current_timestep_number', <step>)
                                                   -- "before", when the host has one
              call ccpp_capture(name, value, standard_name, units, dim_names)
              ...
              call ccpp_capture_end()
            end if

        Emitted even with no entries: "before" opens the call's file (and
        counts the call), "after" reopens it. A device-resident value is
        synced to the host first (cap_shared.directive_op, as GPUDataPass's
        debug_sync does); the sync is not guarded -- every task copies its
        own device data, only the file write is root-only (a real 24-task
        CAM-SIMA build corrupted shared capture files without the guard).
        """
        syncs = []
        if self.directive:
            device_values = [value for value, _, _, is_device in entries if is_device]
            if device_values:
                syncs.append(directive_op(
                    self.directive,
                    AccUpdateSelfOp, {"array_refs": device_values},
                    OmpTargetUpdateFromOp, {"array_refs": device_values},
                ))
        writes = self._preamble_ops() if timing == "before" else []
        writes.append(CallStatementOp(
            "ccpp_capture_begin",
            arg_ops=[StringLiteralExprOp(table_name), StringLiteralExprOp(timing)],
        ))
        if step_var is not None and timing == "before":
            writes.append(CallStatementOp(_ATTRIBUTE_PROCEDURE, arg_ops=[
                StringLiteralExprOp(_STEP_STD_NAME),
                VarRefExprOp(step_var, result_type=i32),
            ]))
        for value, param_name, arg, _ in entries:
            handler = _ddt_capture(arg)
            if handler is not None:
                writes.append(CallStatementOp(handler.write, arg_ops=[
                    StringLiteralExprOp(param_name), ValueExprOp(value),
                ]))
                continue
            layout = _ddt_layout(arg, parse_ddt_layouts(self.ddt_layouts))
            if layout is not None:
                writes += self._component_captures(value, param_name, arg, layout[1])
                continue
            writes.append(CallStatementOp("ccpp_capture", arg_ops=[
                StringLiteralExprOp(param_name),
                ValueExprOp(value),
                StringLiteralExprOp(_attr_text(arg, "standard_name")),
                StringLiteralExprOp(_attr_text(arg, "units")),
                StringLiteralExprOp(",".join(_capture_dim_names(arg))),
            ]))
        writes.append(CallStatementOp("ccpp_capture_end", arg_ops=[]))
        if mpi_root_var is not None:
            writes = _scf_if(VarRefExprOp(mpi_root_var, result_type=i1), writes)

        anchor = InsertPoint.before(call_op) if timing == "before" else InsertPoint.after(call_op)
        for op in syncs + writes:
            Rewriter.insert_op(op, anchor)
            anchor = InsertPoint.after(op)
