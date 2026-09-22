"""GPU residency debug-print diagnostics -- opt-in only, never emitted
unless xdsl_ccpp's own --gpu-debug-prints CLI flag is passed (see
ccpp_dsl.py). Added to debug a persistent "PRESENT clause was not found on
device" runtime failure that survived several source-level fixes to the
actual GPU data-movement directives: rather than keep hand-editing
generated Fortran with one-off diagnostic prints (fragile, wiped by
regeneration, not reusable), this gives xdsl_ccpp a real, reusable
mechanism for answering "is this variable/slice actually present and the
right size on the device" directly from a run, for any future GPU
residency bug too.

All diagnostics print from *inside* the `!$acc parallel` region itself
(confirmed working in practice, not just theoretically -- nvfortran
supports a `write`/`print` statement inside an OpenACC compute region), so
no host-scratch-and-copy-back indirection is needed: the value printed is
read directly on the device, at the exact point the region executes.

Three diagnostics:
1. Array size diagnostics: for every existing `AccUpdateSelfOp`/
   `AccUpdateDeviceOp`/`AccEnterDataOp` (copyin)/`AccDataBeginOp` (copy/
   copyin/copyout) already in the generated IR -- i.e. every op that
   ESTABLISHES device residency -- insert a diagnostic right after it
   printing that array's per-dimension `size(...)` from inside a
   `present(...)` region -- confirms whether the *whole* array is actually
   registered on the device at the size expected at that exact point in
   the call sequence. Deliberately excludes `AccExitDataOp`/`AccDataEndOp`
   (which REMOVE a device mapping): testing presence right after one of
   those is a guaranteed false-positive crash regardless of whether
   anything is actually wrong -- confirmed the hard way against a real
   CAM-SIMA build (phys_tend%dTdt_total is genuinely, correctly exit-data'd
   at that point; this pass's own diagnostic was the only thing testing it
   afterward).
2. Scalar diagnostics: for every module-scope scalar (`ModuleVarOp` with
   rank 0), one diagnostic at the top of each GPU-call-bearing lifecycle
   function, printing its host value alongside a device-read value --
   catches the general class of bug where a module-scope scalar's value is
   undefined/stale on the device (missing `declare create`/`update
   device`), independent of this specific crash.
3. Scheme-call slice diagnostics: for every array-section argument (e.g.
   `exner(col_start:col_end, 1:nz)`) passed directly to a scheme call --
   the actual shape of the motivating "PRESENT clause not found: pk" crash,
   which is a *slice*, not a bare whole-array reference like (1) covers --
   insert a diagnostic right before the call testing `present()` of that
   exact slice expression, printing its per-dimension size and the runtime
   value of every named bound the slice uses (e.g. col_start/col_end/nz),
   all read from inside the same region.
"""

from dataclasses import dataclass

from xdsl.context import Context
from xdsl.dialects import arith, builtin, func, scf
from xdsl.passes import ModulePass
from xdsl.rewriter import InsertPoint, Rewriter
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects.ccpp_utils import (
    AccDataBeginOp,
    AccEnterDataOp,
    AccUpdateDeviceOp,
    AccUpdateSelfOp,
    ArraySectionOp,
    GPUDebugPrintOp,
    HostVarRefOp,
    KeywordCallOp,
    ModuleVarOp,
)
from xdsl_ccpp.transforms.util.cap_shared import _bare, split_scheme_table_name
from xdsl_ccpp.transforms.util.ccpp_descriptors import BuildMetaDataDescriptions
from xdsl_ccpp.transforms.util.ir_utils import find_ccpp_module
from xdsl_ccpp.util.ccpp_conventions import CCPP_KIND_PHYS

# Same set of "does this function actually contain scheme calls / GPU-
# relevant lifecycle code" markers suite_cap.py's own
# _GPU_CALL_BEARING_FN_MARKERS and gpu_data_pass.py's apply() already use --
# kept as a separate local copy rather than imported, since this module is
# purely an optional debug aid and shouldn't create a hard dependency
# between it and either of those files' own internal constants.
_GPU_CALL_BEARING_FN_MARKERS = (
    "_physics",
    "_timestep_init_",
    "_timestep_final_",
    "_init_",
    "_final_",
)


def _ftn_scalar_type_str(base_type: str, kind) -> str:
    """Fortran type string for a scratch scalar matching a real/integer
    ModuleVarOp's own declared type -- only these two base_types are ever
    passed in (see apply()'s own filter)."""
    if base_type == "real":
        k = kind.data if kind is not None else CCPP_KIND_PHYS
        return f"real(kind={k})"
    return "integer"


def _expr_text(value) -> "str | None":
    """Return the literal Fortran expression a value resolves to, or None
    if it can't be determined confidently -- callers must skip
    instrumenting anything this returns None for, since emitting a
    guessed/synthetic name as literal source text would produce an
    undefined-identifier compile error, not a diagnostic.

    Handles the specific shapes this pass actually encounters:
    - HostVarRefOp results (gpu_ccpp_cap_pass.py's whole-suite hoisting and
      suite_cap.py's SuiteOwned residency injection both construct
      references this way -- the real name lives in the defining op's own
      var_name property, not on the SSA value's name_hint, which
      HostVarRefOp's constructor never sets). When the op's member_name
      attribute is set, the reference is a DDT member access
      (var_name%member_name, e.g. phys_state%exner) -- print_ftn.py's own
      CCPPHostVarRefOp case resolves it exactly this way; omitting this
      produced invalid Fortran (a bare "phys_state" used as if it were an
      array) the first time this function shipped without it. When
      index_expr is also set (multi-instance host arrays), the reference
      is var_name(index_expr)%member_name.
    - Plain block arguments (dummy args of the enclosing FuncOp), which do
      carry a real name_hint (same convention gpu_data_pass.py's
      arg_by_name already relies on).
    - arith.ConstantOp results (a literal bound like the "1" in "1:nz"),
      rendered as the literal integer text.
    - ArraySectionOp results (a slice, e.g. "exner(col_start:col_end,
      1:nz)"), rendered recursively from its own source/lowers/uppers.
    """
    owner = value.owner
    if isa(owner, HostVarRefOp):
        member = owner.attributes.get("member_name")
        index_expr = owner.attributes.get("index_expr")
        base_name = (
            f"{owner.var_name.data}({index_expr.data})"
            if index_expr is not None
            else owner.var_name.data
        )
        return f"{base_name}%{member.data}" if member is not None else base_name
    if isa(owner, arith.ConstantOp):
        return str(owner.value.value.data)
    if isa(owner, ArraySectionOp):
        source_text = _expr_text(owner.source)
        if source_text is None:
            return None
        bounds = []
        for lower, upper in zip(owner.lowers, owner.uppers):
            lower_text = _expr_text(lower)
            upper_text = _expr_text(upper)
            if lower_text is None or upper_text is None:
                return None
            bounds.append(f"{lower_text}:{upper_text}")
        return f"{source_text}({', '.join(bounds)})"
    if value.name_hint is not None:
        return _bare(value.name_hint)
    return None


def _named_bounds(value, seen: set) -> list:
    """Collect every named (non-literal) bound expression referenced by an
    ArraySectionOp chain, in encounter order, de-duplicated -- these are
    the col_start/col_end/nz-style scalars worth printing alongside a
    slice's size, since they're exactly what determines the slice itself.
    """
    owner = value.owner
    if not isa(owner, ArraySectionOp):
        return []
    names = []
    for bound in list(owner.lowers) + list(owner.uppers):
        if isa(bound.owner, arith.ConstantOp):
            continue
        text = _expr_text(bound)
        if text is not None and text not in seen:
            seen.add(text)
            names.append(text)
    return names


def _array_rank(ref) -> int:
    return len(ref.type.shape.data)


def _find_call_in_if(if_op):
    """Return the scheme call inside an error-guarded scf.IfOp, or None --
    mirrors gpu_data_pass.py's own _find_call_in_if exactly (kept as a
    separate local copy for the same reason as the marker tuple above)."""
    if not if_op.true_region.blocks:
        return None
    for op in if_op.true_region.blocks[0].ops:
        if isa(op, func.CallOp) or isa(op, KeywordCallOp):
            return op
    return None


def _call_args(call_op):
    if isa(call_op, KeywordCallOp):
        return list(call_op.args)
    return list(call_op.arguments)


def _callee_name(call_op) -> str:
    if isa(call_op, KeywordCallOp):
        return call_op.callee.data
    return call_op.callee.root_reference.data


def _call_param_names(call_op, scheme_name, table_name, meta_data) -> "list[str] | None":
    """Return this call's own parameter names, one per operand in
    _call_args' order, or None if they can't be determined.

    KeywordCallOp already stores them (operand_names, positionally paired
    with .args). A plain func.CallOp has no such record, so fall back to
    the callee's own .meta table order -- valid only because Fortran
    positional call arguments must match the callee's declared parameter
    order exactly.
    """
    if isa(call_op, KeywordCallOp):
        return [n.data for n in call_op.operand_names]
    if scheme_name not in meta_data or table_name not in meta_data[scheme_name].arg_tables:
        return None
    return [
        arg.name
        for arg in meta_data[scheme_name].arg_tables[table_name].getFunctionArguments()
    ]


def _device_arg_names(scheme_name, table_name, meta_data) -> set:
    """Return the set of this scheme's own parameter names (as declared in
    its own .meta table) that are memory_space=device -- mirrors
    gpu_data_pass.py's own _get_device_args exactly, but returns just the
    name set since Part C only needs "is this device or not", not the host
    var mapping. Critical for correctness, not just precision: without this
    filter, Part C instrumented every array-section call argument
    regardless of whether it was ever supposed to be device-resident --
    including genuinely host-only/HostMatched variables (e.g. phys_state%T)
    whose real residency is scoped to GPUCcppCapPass's own narrower
    structured `!$acc data` region elsewhere. Testing presence of those
    outside that scope is a guaranteed false-positive crash, confirmed the
    hard way against a real CAM-SIMA build.
    """
    if scheme_name not in meta_data or table_name not in meta_data[scheme_name].arg_tables:
        return set()
    return {
        arg.name
        for arg in meta_data[scheme_name].arg_tables[table_name].getFunctionArguments()
        if arg.hasAttr("memory_space") and arg.getAttr("memory_space") == "device"
    }


@dataclass(frozen=True)
class GPUDebugPrintPass(ModulePass):
    """See module docstring. Registered as "generate-gpu-debug-prints";
    run after generate-gpu-data/generate-gpu-ccpp-cap/generate-suite-cap so
    it sees the final, fully-resolved set of data-movement ops, scheme
    calls, and module-var declarations, not an intermediate state.
    """

    name = "generate-gpu-debug-prints"

    def apply(self, ctx: Context, op: builtin.ModuleOp) -> None:
        # Needed only by Part C, to filter to genuinely memory_space=device
        # scheme arguments -- see _device_arg_names' own docstring for why
        # this matters for correctness, not just precision.
        ccpp_mod = find_ccpp_module(op.body.block.ops)
        meta_data = {}
        if ccpp_mod is not None:
            bmdd = BuildMetaDataDescriptions()
            bmdd.traverse(ccpp_mod)
            meta_data = bmdd.meta_data

        for module_op in op.body.block.ops:
            if not (
                isa(module_op, builtin.ModuleOp)
                and module_op.sym_name is not None
                and module_op.sym_name.data.endswith("_cap")
            ):
                continue

            scalar_entries = [
                child
                for child in module_op.body.block.ops
                if (
                    isa(child, ModuleVarOp)
                    and child.fixed_dim is None
                    and child.rank.value.data == 0
                    and child.base_type.data in ("real", "integer")
                )
            ]

            for fn in module_op.body.block.ops:
                if not (isa(fn, func.FuncOp) and not fn.is_declaration):
                    continue
                if not fn.body.blocks:
                    continue
                fn_name = fn.sym_name.data
                if not any(marker in fn_name for marker in _GPU_CALL_BEARING_FN_MARKERS):
                    continue
                block = fn.body.blocks[0]

                # --- Part B: scalar host-vs-device value diagnostics ---
                # One per module scalar, inserted at the very top of the
                # function.
                first_op = next(iter(block.ops), None)
                if first_op is not None:
                    for entry in scalar_entries:
                        name = entry.var_name.data
                        text = (
                            f"write(*,*) 'CCPPDBG scalar {name} host=', {name}\n"
                            f"!$acc parallel\n"
                            f"write(*,*) 'CCPPDBG scalar {name} device=', {name}\n"
                            f"!$acc end parallel"
                        )
                        Rewriter.insert_op(
                            GPUDebugPrintOp([], text),
                            InsertPoint.before(first_op),
                        )

                # --- Part A: array size diagnostics ---
                # Right after every data-movement op that ESTABLISHES
                # residency (never the bare create/delete/present operand
                # groups, which don't move anything -- and never
                # AccExitDataOp/AccDataEndOp, whose whole purpose is to
                # REMOVE a device mapping: testing presence right after one
                # of those is a guaranteed false-positive crash regardless
                # of whether anything is actually wrong, confirmed the hard
                # way against a real CAM-SIMA build -- phys_tend%dTdt_total
                # is genuinely, correctly exit-data'd here, and this pass's
                # own diagnostic was the only thing testing it afterward).
                # walk(), not block.ops: every one of these ops lives
                # inside at least one scf.IfOp guard (e.g.
                # ccpp_physics_run's suite-name/suite-part checks), never
                # directly in the function's own top-level block.
                for block_op in list(block.walk()):
                    array_refs = []
                    if isa(block_op, AccUpdateSelfOp) or isa(block_op, AccUpdateDeviceOp):
                        array_refs = list(block_op.arrays)
                    elif isa(block_op, AccEnterDataOp):
                        array_refs = list(block_op.copyin_arrays)
                    elif isa(block_op, AccDataBeginOp):
                        array_refs = (
                            list(block_op.copy_arrays)
                            + list(block_op.copyin_arrays)
                            + list(block_op.copyout_arrays)
                        )
                    if not array_refs:
                        continue

                    for ref in array_refs:
                        rank = _array_rank(ref)
                        if rank == 0:
                            continue
                        name = _expr_text(ref)
                        if name is None:
                            # Can't confidently resolve a literal Fortran
                            # identifier for this ref -- skip rather than
                            # emit an undefined-identifier reference.
                            continue
                        size_prints = ", ".join(
                            f"' dim{i + 1}=', size({name}, {i + 1})" for i in range(rank)
                        )
                        text = (
                            f"!$acc parallel present({name})\n"
                            f"write(*,*) 'CCPPDBG array {name} device size:', {size_prints}\n"
                            f"!$acc end parallel"
                        )
                        Rewriter.insert_op(
                            GPUDebugPrintOp([], text),
                            InsertPoint.after(block_op),
                        )

                # --- Part C: scheme-call slice diagnostics ---
                # The actual shape of the motivating crash: an array
                # SECTION (not a bare whole-array reference) passed
                # directly as a scheme call argument, e.g.
                # exner(col_start:col_end, 1:nz). Every scheme call is
                # wrapped in its own error-guarding scf.IfOp (suite_cap.py
                # convention) -- walk() finds them regardless of nesting.
                #
                # Restricted to arguments the CALLEE's own .meta actually
                # declares memory_space=device -- see _device_arg_names'
                # docstring: instrumenting every sliced argument
                # indiscriminately (including ordinary host-only/
                # HostMatched variables like phys_state%T, already handled
                # correctly by GPUCcppCapPass's own narrower-scoped
                # residency) produces guaranteed false-positive crashes,
                # not diagnostics.
                for if_op in list(block.walk()):
                    if not isa(if_op, scf.IfOp):
                        continue
                    call_op = _find_call_in_if(if_op)
                    if call_op is None:
                        continue
                    split = split_scheme_table_name(_callee_name(call_op))
                    if split is None:
                        continue
                    scheme_name, _phase = split
                    table_name = _callee_name(call_op)
                    device_names = _device_arg_names(scheme_name, table_name, meta_data)
                    if not device_names:
                        continue
                    param_names = _call_param_names(call_op, scheme_name, table_name, meta_data)
                    if param_names is None:
                        continue

                    for arg, param_name in zip(_call_args(call_op), param_names):
                        if param_name not in device_names:
                            continue
                        if not isa(arg.owner, ArraySectionOp):
                            continue
                        rank = _array_rank(arg)
                        if rank == 0:
                            continue
                        slice_text = _expr_text(arg)
                        if slice_text is None:
                            continue
                        named_bounds = _named_bounds(arg, set())
                        size_prints = ", ".join(
                            f"' dim{i + 1}=', size({slice_text}, {i + 1})"
                            for i in range(rank)
                        )
                        bound_prints = "".join(
                            f", ' {b}=', {b}" for b in named_bounds
                        )
                        text = (
                            f"!$acc parallel present({slice_text})\n"
                            f"write(*,*) 'CCPPDBG call-arg {slice_text} device size:', "
                            f"{size_prints}{bound_prints}\n"
                            f"!$acc end parallel"
                        )
                        Rewriter.insert_op(
                            GPUDebugPrintOp([], text),
                            InsertPoint.before(if_op),
                        )
