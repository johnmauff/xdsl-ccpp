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
    OmpTargetDataBeginOp,
    OmpTargetDataEndOp,
    OmpTargetUpdateFromOp,
    OmpTargetUpdateToOp,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    BuildMetaDataDescriptions,
    CCPPType,
)
from xdsl_ccpp.transforms.util.ir_utils import find_ccpp_module


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

        scheme=device + model=host    → copy(var)
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

    # GPU directive backend: "acc" for OpenACC, "omp" for OpenMP target offload.
    # Usage: generate-gpu-ccpp-cap            (default: OpenACC)
    #        generate-gpu-ccpp-cap{directive=omp}  (OpenMP target)
    directive: str = "acc"

    def _build_model_var_clause_map(self, ccpp_mod):
        """Return a dict mapping host model variable name → OpenACC clause type.

        Walks all SCHEME metadata and uses the scheme's memory_space, the host
        model variable's memory_space, and the argument's intent to determine
        which OpenACC clause each variable needs.

        Returns: {model_var_name: "present" | "copyin" | "copy" | "copyout" | "update"}
            "present"  — both sides agree on device; host manages the device copy
            "copyin"   — scheme=device, model=host, intent=in: host→device only
            "copy"     — scheme=device, model=host, intent=inout: both directions
            "copyout"  — scheme=device, model=host, intent=out: device→host only
            "update"   — scheme=host, model=device: acc update self/device around call
        """
        bmdd = BuildMetaDataDescriptions()
        bmdd.traverse(ccpp_mod)

        # Track per host-variable whether any scheme reads or writes it on device.
        # A variable may appear in multiple scheme entry points with different
        # intents (e.g. theta is intent(inout) in kessler_run but intent(in)
        # in kessler_update_run).  We take the union across all entry points:
        #   any read  (in  or inout) → needs_in
        #   any write (out or inout) → needs_out
        # Then: both → copy(); read only → copyin(); write only → copyout()
        needs_in:  dict = {}  # host_var → bool
        needs_out: dict = {}  # host_var → bool
        present_vars: set = set()
        update_vars:  set = set()

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
                        present_vars.add(host_var)
                    elif scheme_space == "device" and model_space == "host":
                        intent = arg.getAttr("intent") if arg.hasAttr("intent") else "inout"
                        reads  = intent in ("in",  "inout")
                        writes = intent in ("out", "inout")
                        needs_in[host_var]  = needs_in.get(host_var,  False) or reads
                        needs_out[host_var] = needs_out.get(host_var, False) or writes
                    elif scheme_space == "host" and model_space == "device":
                        update_vars.add(host_var)
                    # else: both host — no directive needed

        clause_map = {}
        for host_var in present_vars:
            clause_map[host_var] = "present"
        for host_var in update_vars:
            clause_map[host_var] = "update"
        for host_var, r in needs_in.items():
            w = needs_out.get(host_var, False)
            if r and w:
                clause_map[host_var] = "copy"
            elif r:
                clause_map[host_var] = "copyin"
            else:
                clause_map[host_var] = "copyout"

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
            present_vars  = []
            copyin_vars   = []
            copy_vars     = []
            copyout_vars  = []
            update_vars   = []

            for ref_op in true_block.ops:
                if not isa(ref_op, HostVarRefOp):
                    continue
                var_name = ref_op.var_name.data
                if var_name not in clause_map:
                    continue
                clause = clause_map[var_name]
                if clause == "present":
                    present_vars.append(var_name)
                elif clause == "copyin":
                    copyin_vars.append(var_name)
                elif clause == "copy":
                    copy_vars.append(var_name)
                elif clause == "copyout":
                    copyout_vars.append(var_name)
                elif clause == "update":
                    update_vars.append(var_name)

            # Data region directives go inside the inner scf.IfOp's true
            # region, immediately around the suite physics call.  This way the
            # acc/omp data region only opens once the suite-part comparison is
            # already known to be true — no wasted data movement on the wrong
            # suite part.
            # copy/copyin/copyout/tofrom: use array sections for efficiency.
            # present / alloc: use base variable names — the host put the
            #   whole array on device, not just the active columns.
            if present_vars or copyin_vars or copy_vars or copyout_vars:
                copy_refs    = self._resolve_array_refs(true_block, set(copy_vars),    use_sections=True)
                copyin_refs  = self._resolve_array_refs(true_block, set(copyin_vars),  use_sections=True)
                copyout_refs = self._resolve_array_refs(true_block, set(copyout_vars), use_sections=True)
                base_refs    = self._resolve_array_refs(true_block, set(present_vars), use_sections=False)
                if self.directive == "omp":
                    # OMP uses map(tofrom:) for copy and map(to:) for copyin,
                    # map(from:) for copyout; map(alloc:) for present.
                    Rewriter.insert_op(
                        OmpTargetDataBeginOp(
                            tofrom=copy_refs + copyin_refs + copyout_refs,
                            alloc=base_refs,
                        ),
                        InsertPoint.before(suite_call),
                    )
                    Rewriter.insert_op(
                        OmpTargetDataEndOp(),
                        InsertPoint.after(suite_call),
                    )
                else:  # acc (default)
                    Rewriter.insert_op(
                        AccDataBeginOp(
                            copy=copy_refs,
                            copyin=copyin_refs,
                            copyout=copyout_refs,
                            present=base_refs,
                        ),
                        InsertPoint.before(suite_call),
                    )
                    Rewriter.insert_op(
                        AccDataEndOp(),
                        InsertPoint.after(suite_call),
                    )

            # Update directives go inside the inner scf.IfOp's true region,
            # bracketing the actual suite physics call.
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
