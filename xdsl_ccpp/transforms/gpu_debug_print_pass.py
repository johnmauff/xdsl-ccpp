"""GPU residency diagnostics, emitted only with xdsl_ccpp's
--gpu-debug-prints flag (see ccpp_dsl.py). They answer "is this variable
or slice present on the device, at the expected size, at this point in the
call sequence" from a run. Each diagnostic is a PrintStmtOp inside an
AccParallelOp, so the value printed is read on the device (nvfortran
allows output statements in an OpenACC compute region).

1. Array sizes: after every op that establishes device residency
   (AccUpdateSelfOp/AccUpdateDeviceOp, AccEnterDataOp copyin,
   AccDataBeginOp copy/copyin/copyout), print each array's per-dimension
   size inside a present(...) region. Ops that remove a mapping
   (AccExitDataOp, AccDataEndOp) are excluded: a present() check after
   them fails even when nothing is wrong.
2. Module scalars: at the top of each GPU-call-bearing function, print
   every module-scope real/integer scalar's host value and device value,
   to catch a scalar missing from the device or stale there.
3. Sliced scheme arguments: before each scheme call, for every array
   section passed for an argument the scheme declares memory_space =
   device, print the section's size and the values of its named bounds
   (col_start, col_end, nz, ...) inside a present(...) region.
"""

from dataclasses import dataclass

from xdsl.context import Context
from xdsl.dialects import arith, builtin, func
from xdsl.passes import ModulePass
from xdsl.rewriter import InsertPoint, Rewriter
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects.ccpp_utils import (
    AccDataBeginOp,
    AccEnterDataOp,
    AccParallelOp,
    AccUpdateDeviceOp,
    AccUpdateSelfOp,
    CallExprOp,
    ExprTextLiteralOp,
    ModuleVarOp,
    PrintStmtOp,
    RankReducingSliceOp,
    StringLiteralExprOp,
    ValueExprOp,
    VarRefExprOp,
)
from xdsl_ccpp.transforms.util.cap_shared import (
    is_gpu_call_bearing_fn,
    iter_scheme_call_sites,
    _array_rank,
    _call_args,
    _call_param_names,
    _device_arg_names,
    _expr_text,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import BuildMetaDataDescriptions
from xdsl_ccpp.transforms.util.ir_utils import find_ccpp_module


def _size_items(ref, rank: int) -> list:
    """' dim<i>=', size(ref, i) for each dimension of ref."""
    items = []
    for i in range(1, rank + 1):
        items.append(StringLiteralExprOp(f" dim{i}="))
        items.append(CallExprOp("size", [
            ValueExprOp(ref), arith.ConstantOp.from_int_and_width(i, 32),
        ]))
    return items


def _named_bounds(slice_value) -> list:
    """The non-literal bounds and indices of a slice (col_start, col_end,
    nz, ...), in encounter order, one per name."""
    owner = slice_value.owner
    seen = set()
    bounds = []
    for bound in (
        list(owner.range_lowers) + list(owner.range_uppers) + list(owner.scalar_indices)
    ):
        if isa(bound.owner, arith.ConstantOp):
            continue
        key = _expr_text(bound)
        if key is not None and key not in seen:
            seen.add(key)
            bounds.append(bound)
    return bounds


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
                        host_print = PrintStmtOp([
                            StringLiteralExprOp(f"CCPPDBG scalar {name} host="),
                            VarRefExprOp(name),
                        ])
                        device_print = AccParallelOp([PrintStmtOp([
                            StringLiteralExprOp(f"CCPPDBG scalar {name} device="),
                            VarRefExprOp(name),
                        ])])
                        Rewriter.insert_op(
                            [host_print, device_print], InsertPoint.before(first_op),
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
                        if _expr_text(ref) is None:
                            # No definite Fortran name for this ref -- skip
                            # rather than emit an undefined identifier.
                            continue
                        diagnostic = AccParallelOp([PrintStmtOp([
                            ExprTextLiteralOp(
                                ValueExprOp(ref), prefix="CCPPDBG array ", suffix=" device size:",
                            ),
                            *_size_items(ref, rank),
                        ])], present=[ref])
                        Rewriter.insert_op(diagnostic, InsertPoint.after(block_op))

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
        for _if_op, call_op, scheme_name, _phase, table_name in iter_scheme_call_sites(op):
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
                if _expr_text(arg) is None:
                    continue
                bound_items = []
                for bound in _named_bounds(arg):
                    bound_items.append(
                        ExprTextLiteralOp(ValueExprOp(bound), prefix=" ", suffix="=")
                    )
                    bound_items.append(ValueExprOp(bound))
                diagnostic = AccParallelOp([PrintStmtOp([
                    ExprTextLiteralOp(
                        ValueExprOp(arg), prefix="CCPPDBG call-arg ", suffix=" device size:",
                    ),
                    *_size_items(arg, rank),
                    *bound_items,
                ])], present=[arg])
                # Before the call itself, inside its error guard: the slice
                # is defined there, but not necessarily before the guard.
                Rewriter.insert_op(diagnostic, InsertPoint.before(call_op))
