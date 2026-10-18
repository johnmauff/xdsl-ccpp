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

Runtime library note: as of this pass, xdsl_ccpp/framework_src/
ccpp_capture_mod.F90 does not exist yet (a separate, planned PR) -- the
calls this pass emits are already the final, intended call text (not a
placeholder syntax needing a later rewrite), just not yet backed by a
real, compiling module. --capture-scheme is opt-in and no example enables
it today, so this has no effect on any existing build.
"""

from dataclasses import dataclass

from xdsl.context import Context
from xdsl.dialects import builtin
from xdsl.passes import ModulePass
from xdsl.rewriter import InsertPoint, Rewriter

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
from xdsl_ccpp.transforms.util.ir_utils import find_ccpp_module
from xdsl_ccpp.util.ccpp_conventions import CCPP_ERROR_STD_NAMES, CCPP_KIND_PHYS

# {integer, logical, real(kind_phys)} x {rank 0..3} -- see module docstring
# for why this is the real, deliberately narrow v1 scope, not an
# open-ended type system. "real" is handled separately below (its code
# additionally requires kind == CCPP_KIND_PHYS); character and any
# DDT/derived type (anything not in this map and not "real") are excluded
# simply by never matching a code here.
_TYPE_CODE = {"integer": "int", "logical": "log"}
_MAX_SUPPORTED_RANK = 3


def _capture_proc_name(arg_type: "str | None", kind: "str | None", rank: int) -> "str | None":
    """Return the concrete ccpp_capture_mod procedure name for this
    argument's (type, kind, rank), or None if unsupported (caller must
    skip, not guess)."""
    if rank > _MAX_SUPPORTED_RANK:
        return None
    if arg_type == "real":
        if kind != CCPP_KIND_PHYS:
            return None
        type_code = "r8"
    elif arg_type in _TYPE_CODE:
        type_code = _TYPE_CODE[arg_type]
    else:
        return None
    return f"ccpp_capture_{type_code}_{rank}d"


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

    def apply(self, ctx: Context, op: builtin.ModuleOp) -> None:
        if not self.scheme:
            return

        ccpp_mod = find_ccpp_module(op.body.block.ops)
        meta_data = {}
        if ccpp_mod is not None:
            bmdd = BuildMetaDataDescriptions()
            bmdd.traverse(ccpp_mod)
            meta_data = bmdd.meta_data

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
                proc_name = _capture_proc_name(arg_type, kind, rank)
                if proc_name is None:
                    continue
                expr_text = _expr_text(value)
                if expr_text is None:
                    continue

                if intent in ("in", "inout"):
                    self._insert_capture(
                        value, expr_text, proc_name, table_name, param_name, intent,
                        "before", param_name in device_names, call_op,
                    )
                if intent in ("out", "inout"):
                    self._insert_capture(
                        value, expr_text, proc_name, table_name, param_name, intent,
                        "after", param_name in device_names, call_op,
                    )

    def _insert_capture(
        self, value, expr_text, proc_name, table_name, param_name, intent,
        timing, is_device, call_op,
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
        Rewriter.insert_op(
            RawFortranLinesOp(f'call {proc_name}("{tag}", {expr_text})'),
            capture_anchor,
        )
