from dataclasses import dataclass

from xdsl.context import Context
from xdsl.dialects import builtin, func, scf
from xdsl.passes import ModulePass
from xdsl.rewriter import InsertPoint, Rewriter
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects.ccpp_utils import AccDataBeginOp, AccDataEndOp
from xdsl_ccpp.transforms.util.ccpp_descriptors import BuildMetaDataDescriptions


@dataclass(frozen=True)
class GPUDataPass(ModulePass):
    """Insert OpenACC data directives around GPU-capable scheme calls.

    Reads memory_space annotations from CCPP metadata and wraps consecutive
    GPU-capable scheme calls in !$acc data regions inside _physics subroutines.

    Limitations (simplified — no host variable matching):
    - Directives are inserted at the suite_cap level, not ccpp_cap level.
    - Always generates copyin+copyout (no 'present' optimisation).
    - Variable names are scheme-local, not host module names.
    """

    name = "generate-gpu-data"

    def _find_ccpp_module(self, ops):
        """Return the named @ccpp ModuleOp from the given op list, or None."""
        for op in ops:
            if (
                isa(op, builtin.ModuleOp)
                and op.sym_name is not None
                and op.sym_name.data == "ccpp"
            ):
                return op
        return None

    def _get_scheme_name(self, callee_name):
        """Strip lifecycle suffix to get the scheme base name.

        e.g. 'hello_scheme_run' → 'hello_scheme'
        Returns None if the name doesn't match a known suffix.
        """
        for suffix in ("_run", "_init", "_finalize",
                       "_timestep_init", "_timestep_final"):
            if callee_name.endswith(suffix):
                return callee_name[: -len(suffix)]
        return None

    def _get_device_args(self, scheme_name, meta_data):
        """Return the set of local variable names annotated memory_space=device
        in the scheme's _run argument table.
        """
        if scheme_name not in meta_data:
            return set()
        table_name = scheme_name + "_run"
        if table_name not in meta_data[scheme_name].arg_tables:
            return set()
        device_args = set()
        for arg in (
            meta_data[scheme_name].arg_tables[table_name].getFunctionArguments()
        ):
            if (
                arg.hasAttr("memory_space")
                and arg.getAttr("memory_space") == "device"
            ):
                device_args.add(arg.name)
        return device_args

    def _find_call_in_if(self, if_op):
        """Return the func.CallOp inside an error-guarded scf.IfOp, or None.

        suite_cap.py wraps each scheme call in an scf.IfOp that checks errflg.
        This method looks inside the true region of that guard to find the call.
        """
        if not if_op.true_region.blocks:
            return None
        for op in if_op.true_region.blocks[0].ops:
            if isa(op, func.CallOp):
                return op
        return None

    def _process_physics_fn(self, fn_op, meta_data):
        """Insert acc.data markers around GPU scheme calls in one subroutine.

        Finds all error-guarded scheme calls that have at least one
        device-resident argument, collects the union of their device variable
        names, and wraps the entire group in a single !$acc data region.

        This is the simplified single-region approach — one region per
        physics subroutine covering all GPU-capable calls together.
        """
        if not fn_op.body.blocks:
            return

        block = fn_op.body.blocks[0]

        # Collect (scf.IfOp, device_vars) for each GPU-capable scheme call
        gpu_calls = []
        for op in block.ops:
            if not isa(op, scf.IfOp):
                continue
            call_op = self._find_call_in_if(op)
            if call_op is None:
                continue
            scheme_name = self._get_scheme_name(
                call_op.callee.root_reference.data
            )
            if scheme_name is None:
                continue
            device_vars = self._get_device_args(scheme_name, meta_data)
            if device_vars:
                gpu_calls.append((op, device_vars))

        if not gpu_calls:
            return

        # Union of all device variables across the group.
        # Conservative: copyin and copyout the same set.
        # Refined once host variable matching is added.
        all_vars = set()
        for _, device_vars in gpu_calls:
            all_vars.update(device_vars)

        first_if = gpu_calls[0][0]
        last_if  = gpu_calls[-1][0]

        Rewriter.insert_op(
            AccDataBeginOp(copyin=sorted(all_vars), copyout=sorted(all_vars)),
            InsertPoint.before(first_if),
        )
        Rewriter.insert_op(
            AccDataEndOp(),
            InsertPoint.after(last_if),
        )

    def apply(self, ctx: Context, op: builtin.ModuleOp) -> None:
        ccpp_mod = self._find_ccpp_module(op.body.block.ops)
        if ccpp_mod is None:
            return

        # Build metadata descriptors to find memory_space annotations
        bmdd = BuildMetaDataDescriptions()
        bmdd.traverse(ccpp_mod)
        meta_data = bmdd.meta_data

        # Find all suite cap modules and process their _physics subroutines
        for module_op in op.body.block.ops:
            if not (
                isa(module_op, builtin.ModuleOp)
                and module_op.sym_name is not None
                and module_op.sym_name.data.endswith("_cap")
            ):
                continue
            for child in module_op.body.block.ops:
                if (
                    isa(child, func.FuncOp)
                    and not child.is_declaration
                    and "_suite_physics" in child.sym_name.data
                ):
                    self._process_physics_fn(child, meta_data)
