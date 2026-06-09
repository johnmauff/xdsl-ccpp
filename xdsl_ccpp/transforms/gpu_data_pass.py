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

    Reads memory_space and model_var_name annotations from CCPP metadata
    (populated by generate-host-match) and wraps consecutive GPU-capable
    scheme calls in !$acc data regions inside _physics subroutines.

    Directives are inserted at the suite_cap level using scheme-local variable
    names, which are the variables in scope at that level.  The model_var_name
    mapping is available for each device-resident argument and will be used
    when directives are moved to the ccpp_cap level in future work.

    Remaining limitation:
    - Always generates copyin+copyout (no 'present' optimisation yet).
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
        """Return a dict mapping scheme-local name → host variable name for
        all device-resident arguments in the scheme's _run argument table.

        The host variable name comes from the model_var_name annotation set by
        generate-host-match.  It is None when no host match was found (e.g.
        a device-resident scratch array local to the scheme).
        """
        if scheme_name not in meta_data:
            return {}
        table_name = scheme_name + "_run"
        if table_name not in meta_data[scheme_name].arg_tables:
            return {}
        device_args = {}
        for arg in (
            meta_data[scheme_name].arg_tables[table_name].getFunctionArguments()
        ):
            if (
                arg.hasAttr("memory_space")
                and arg.getAttr("memory_space") == "device"
            ):
                host_var = (
                    arg.getAttr("model_var_name")
                    if arg.hasAttr("model_var_name")
                    else None
                )
                device_args[arg.name] = host_var
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

        # Collect (scf.IfOp, device_vars) for each GPU-capable scheme call.
        # device_vars is a dict: scheme_local_name → model_var_name (or None)
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

        # Only emit suite_cap level directives for variables that have NO host
        # variable match.  Variables with a host match are handled at the
        # ccpp_cap level by GPUCcppCapPass, which uses the host variable name
        # directly.  Emitting directives at both levels would create nested
        # !$acc data regions with redundant data movement.
        all_local_vars = set()
        for _, device_vars in gpu_calls:
            for local_name, host_var in device_vars.items():
                if host_var is None:
                    all_local_vars.add(local_name)

        first_if = gpu_calls[0][0]
        last_if  = gpu_calls[-1][0]

        Rewriter.insert_op(
            AccDataBeginOp(
                copyin=sorted(all_local_vars),
                copyout=sorted(all_local_vars),
            ),
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
