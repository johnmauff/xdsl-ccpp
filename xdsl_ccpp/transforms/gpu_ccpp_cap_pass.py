from dataclasses import dataclass

from xdsl.context import Context
from xdsl.dialects import builtin, func, scf
from xdsl.passes import ModulePass
from xdsl.rewriter import InsertPoint, Rewriter
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects.ccpp_utils import (
    AccDataBeginOp,
    AccDataEndOp,
    AccUpdateDeviceOp,
    AccUpdateSelfOp,
    ArraySectionOp,
    HostVarRefOp,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    BuildMetaDataDescriptions,
    CCPPType,
)


@dataclass(frozen=True)
class GPUCcppCapPass(ModulePass):
    """Insert OpenACC data directives at the ccpp_cap level.

    Runs after generate-ccpp-cap and generate-host-match.  For each
    *_ccpp_physics_run subroutine, wraps the suite-part dispatch (inner
    scf.IfOp) with an !$acc data region using host model variable names.

    The OpenACC clause is chosen by comparing the scheme's declared memory
    space against the host model variable's declared memory space
    (propagated as model_var_memory_space by generate-host-match):

        scheme=device + model=device  → present(var)
            Both sides agree the variable lives on the GPU.  The host model
            is responsible for managing the device copy across timesteps.

        scheme=device + model=host    → copyin(var) copyout(var)
            Scheme wants GPU data but model keeps it on CPU.  The framework
            creates a temporary device copy for this call.

        scheme=host   + model=device  → !$acc update self(var) before call,
                                         !$acc update device(var) after call
            Scheme is CPU-only but model keeps data on GPU.  The framework
            copies data to CPU for the scheme and pushes it back afterwards.

        scheme=host   + model=host    → no directive (CPU path, default)

    Naming note: 'model_var_name' refers to the host MODEL variable name,
    not a CPU-memory variable.  'host'/'device' in memory_space follow
    OpenACC conventions (CPU vs GPU).

    Pipeline position: generate-ccpp-cap → generate-gpu-ccpp-cap → generate-kinds
    """

    name = "generate-gpu-ccpp-cap"

    def _find_ccpp_module(self, ops):
        for op in ops:
            if (
                isa(op, builtin.ModuleOp)
                and op.sym_name is not None
                and op.sym_name.data == "ccpp"
            ):
                return op
        return None

    def _build_model_var_clause_map(self, ccpp_mod):
        """Return a dict mapping host model variable name → OpenACC clause type.

        Walks all SCHEME metadata and uses the scheme's memory_space together
        with model_var_memory_space (propagated by generate-host-match) to
        determine which OpenACC clause each variable needs.

        Returns: {model_var_name: "present" | "copyin_copyout" | "skip"}
            "present"       — both scheme and model agree on device memory
            "copyin_copyout" — scheme wants device, model provides host memory
            "skip"          — scheme is host-only but model is on device
                              (Phase 2: requires acc update ops, not yet implemented)
        """
        bmdd = BuildMetaDataDescriptions()
        bmdd.traverse(ccpp_mod)

        clause_map = {}  # model_var_name → clause type

        for props in bmdd.meta_data.values():
            if props.getAttr("type") != CCPPType.SCHEME:
                continue
            for table in props.arg_tables.values():
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
                        clause_map[host_var] = "present"
                    elif scheme_space == "device" and model_space == "host":
                        clause_map[host_var] = "copyin_copyout"
                    elif scheme_space == "host" and model_space == "device":
                        clause_map[host_var] = "update"
                    # else: both host — no directive needed, don't add to map

        return clause_map

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

    def _resolve_array_refs(self, true_block, var_names, use_sections=True):
        """For each variable name in var_names, return the best SSA value to
        use in an !$acc update directive — preferring the ArraySectionOp result
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
            # use_sections=False: use bare ref (correct semantics for present)
            best = section_for_ref.get(op.res, op.res)
            refs.append(best)
        return refs

    def _process_run_fn(self, fn_op, clause_map):
        """Insert acc directives around and inside the suite-part dispatch.

        Data region directives (present, copyin/copyout) wrap the entire
        inner scf.IfOp from outside.  Update directives (acc update self/device)
        are inserted inside the inner scf.IfOp's true region, immediately
        before and after the suite physics func.CallOp.
        """
        if not fn_op.body.blocks:
            return

        for op in fn_op.body.blocks[0].ops:
            if not isa(op, scf.IfOp):
                continue
            if not op.true_region.blocks:
                continue

            true_block = op.true_region.blocks[0]

            inner_if, suite_call = self._find_inner_suite_part_if(true_block)
            if inner_if is None:
                continue

            # Classify HostVarRefOps in this block by OpenACC clause type
            present_vars    = []
            copyin_out_vars = []
            update_vars     = []

            for ref_op in true_block.ops:
                if not isa(ref_op, HostVarRefOp):
                    continue
                var_name = ref_op.var_name.data
                if var_name not in clause_map:
                    continue
                clause = clause_map[var_name]
                if clause == "present":
                    present_vars.append(var_name)
                elif clause == "copyin_copyout":
                    copyin_out_vars.append(var_name)
                elif clause == "update":
                    update_vars.append(var_name)

            # Data region directives wrap the entire inner scf.IfOp.
            # copyin/copyout: use array sections for efficiency
            #   e.g. copyin(temp_midpoints(col_start:col_end, 1:pver))
            # present: use base variable names — semantically correct because the
            #   host put the whole array on device, not just the active columns
            #   e.g. present(temp_interfaces)
            if present_vars or copyin_out_vars:
                copyin_refs  = self._resolve_array_refs(
                    true_block, set(copyin_out_vars), use_sections=True
                )
                present_refs = self._resolve_array_refs(
                    true_block, set(present_vars), use_sections=False
                )
                Rewriter.insert_op(
                    AccDataBeginOp(
                        copyin=copyin_refs,
                        copyout=copyin_refs,
                        present=present_refs,
                    ),
                    InsertPoint.before(inner_if),
                )
                Rewriter.insert_op(
                    AccDataEndOp(),
                    InsertPoint.after(inner_if),
                )

            # Update directives go inside the inner scf.IfOp's true region,
            # bracketing the actual suite physics call.
            # Use array section SSA values where available so the printer
            # emits the correct section notation, e.g.:
            #   !$acc update self(temp_midpoints(col_start:col_end, 1:pver))
            # rather than the whole array:
            #   !$acc update self(temp_midpoints)
            if update_vars and suite_call is not None:
                update_refs = self._resolve_array_refs(
                    true_block, update_vars
                )
                Rewriter.insert_op(
                    AccUpdateSelfOp(array_refs=update_refs),
                    InsertPoint.before(suite_call),
                )
                Rewriter.insert_op(
                    AccUpdateDeviceOp(array_refs=update_refs),
                    InsertPoint.after(suite_call),
                )

    def apply(self, ctx: Context, op: builtin.ModuleOp) -> None:
        ccpp_mod = self._find_ccpp_module(op.body.block.ops)
        if ccpp_mod is None:
            return

        clause_map = self._build_model_var_clause_map(ccpp_mod)
        if not clause_map:
            return

        for module_op in op.body.block.ops:
            if not (
                isa(module_op, builtin.ModuleOp)
                and module_op.sym_name is not None
                and module_op.sym_name.data.endswith("_ccpp_cap")
            ):
                continue
            for child in module_op.body.block.ops:
                if (
                    isa(child, func.FuncOp)
                    and not child.is_declaration
                    and "_ccpp_physics_run" in child.sym_name.data
                ):
                    self._process_run_fn(child, clause_map)
