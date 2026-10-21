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
from xdsl.dialects import builtin, func
from xdsl.passes import ModulePass
from xdsl.rewriter import InsertPoint, Rewriter
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects.ccpp_utils import (
    AccDataBeginOp,
    AccEnterDataOp,
    AccUpdateDeviceOp,
    AccUpdateSelfOp,
    GPUDebugPrintOp,
    ModuleVarOp,
    RankReducingSliceOp,
)
from xdsl_ccpp.transforms.util.cap_shared import (
    is_gpu_call_bearing_fn,
    iter_scheme_call_sites,
    _array_rank,
    _call_args,
    _call_param_names,
    _device_arg_names,
    _expr_text,
    _named_bounds,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import BuildMetaDataDescriptions
from xdsl_ccpp.transforms.util.ir_utils import find_ccpp_module
from xdsl_ccpp.util.ccpp_conventions import CCPP_KIND_PHYS

# _GPU_CALL_BEARING_FN_MARKERS, _expr_text, _array_rank, _device_arg_names,
# _named_bounds, _call_args, _call_param_names, and scheme-call-site
# discovery (iter_scheme_call_sites) all used to be local copies here,
# deliberately not imported from cap_shared.py (to avoid a hard dependency
# for what's "purely an optional debug aid"). Moved to cap_shared.py
# 2026-10-17 once a second real consumer (scheme_io_capture_pass.py)
# needed the identical logic -- cap_shared.py is already a neutral leaf
# module (no dependency on any cap-generation file), so centralizing there
# doesn't introduce the coupling the original comment was guarding
# against. See cap_shared.py's own "Scheme call-site discovery" section
# for the full extraction note.


def _ftn_scalar_type_str(base_type: str, kind) -> str:
    """Fortran type string for a scratch scalar matching a real/integer
    ModuleVarOp's own declared type -- only these two base_types are ever
    passed in (see apply()'s own filter)."""
    if base_type == "real":
        k = kind.data if kind is not None else CCPP_KIND_PHYS
        return f"real(kind={k})"
    return "integer"


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
                if not is_gpu_call_bearing_fn(module_op, fn):
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
        # The actual shape of the motivating crash: an array SECTION (not a
        # bare whole-array reference) passed directly as a scheme call
        # argument, e.g. exner(col_start:col_end, 1:nz). A separate,
        # independent top-level loop (not nested inside the Part A/B loop
        # above) since iter_scheme_call_sites does its own, equivalent
        # module/function walk internally -- no result from Part A/B is
        # needed here, so there's no reason to share one loop.
        #
        # Restricted to arguments the CALLEE's own .meta actually declares
        # memory_space=device -- see _device_arg_names' own docstring:
        # instrumenting every sliced argument indiscriminately (including
        # ordinary host-only/HostMatched variables like phys_state%T,
        # already handled correctly by GPUCcppCapPass's own narrower-scoped
        # residency) produces guaranteed false-positive crashes, not
        # diagnostics.
        for if_op, call_op, scheme_name, _phase, table_name in iter_scheme_call_sites(op):
            device_names = _device_arg_names(scheme_name, table_name, meta_data)
            if not device_names:
                continue
            param_names = _call_param_names(call_op, scheme_name, table_name, meta_data)
            if param_names is None:
                continue

            for arg, param_name in zip(_call_args(call_op), param_names):
                if param_name not in device_names:
                    continue
                if not isa(arg.owner, RankReducingSliceOp):
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
