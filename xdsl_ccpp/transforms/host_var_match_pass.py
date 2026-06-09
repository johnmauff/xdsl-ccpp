from dataclasses import dataclass
from typing import ClassVar

from xdsl.context import Context
from xdsl.dialects import builtin
from xdsl.dialects.builtin import StringAttr
from xdsl.passes import ModulePass
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects import ccpp
from xdsl_ccpp.dialects.ccpp import TableTypeKind


@dataclass(frozen=True)
class HostVariableMatchPass(ModulePass):
    """Annotate scheme ccpp.arg ops with their matched host model variable.

    Builds a standard_name → (local_var_name, module_name, memory_space) index
    from HOST and MODULE metadata, then walks all SCHEME argument tables and
    sets host_var_name, host_module_name, and model_var_memory_space on each
    arg op whose standard_name appears in the index.

    The memory_space value ('host' or 'device') on the matched model variable
    is propagated as model_var_memory_space so downstream GPU passes can
    determine the correct OpenACC clause without re-querying the model metadata.

    Required scheme arguments with no host model match are collected and reported
    together as a ValueError rather than failing on the first mismatch.

    Naming note: 'host_var_name' and 'host_module_name' refer to the host MODEL
    (the atmospheric model that calls CCPP), not CPU host memory.
    'model_var_memory_space' is used where ambiguity with OpenACC's 'host'
    memory space would otherwise arise.

    Pipeline position: generate-meta-cap → generate-host-match → generate-suite-cap
    """

    name = "generate-host-match"

    # Standard names managed by the CCPP framework itself, or derived/computed
    # by the generated cap rather than provided directly as a named model variable.
    _CCPP_INTERNAL: ClassVar[frozenset] = frozenset([
        "ccpp_error_message",
        "ccpp_error_code",
        # Computed by suite_cap.py as (col_end - col_start + 1) rather than
        # provided directly by the host model as a named variable.
        "horizontal_loop_extent",
    ])

    def _find_ccpp_module(self, ops):
        for op in ops:
            if (
                isa(op, builtin.ModuleOp)
                and op.sym_name is not None
                and op.sym_name.data == "ccpp"
            ):
                return op
        return None

    def apply(self, ctx: Context, op: builtin.ModuleOp) -> None:
        ccpp_mod = self._find_ccpp_module(op.body.block.ops)
        if ccpp_mod is None:
            return

        # ── Step 1: build model variable index ────────────────────────────
        # standard_name → (local_var_name, module_name, memory_space|None)
        # 'memory_space' here is the OpenACC sense: 'host' (CPU) or 'device' (GPU).
        model_var_index = {}

        for table_prop_op in ccpp_mod.body.ops:
            if not isa(table_prop_op, ccpp.TablePropertiesOp):
                continue
            if table_prop_op.table_type.data not in (
                TableTypeKind.Module, TableTypeKind.Host
            ):
                continue
            for arg_table_op in table_prop_op.body.ops:
                if not isa(arg_table_op, ccpp.ArgumentTableOp):
                    continue
                for arg_op in arg_table_op.body.ops:
                    if not isa(arg_op, ccpp.ArgumentOp):
                        continue
                    if arg_op.standard_name is not None:
                        memory_space = (
                            arg_op.memory_space.data
                            if arg_op.memory_space is not None
                            else None
                        )
                        model_var_index[arg_op.standard_name.data] = (
                            arg_op.arg_name.data,
                            table_prop_op.table_name.data,
                            memory_space,
                        )

        # ── Step 2: match scheme arguments to model variables ──────────────
        errors = []

        for table_prop_op in ccpp_mod.body.ops:
            if not isa(table_prop_op, ccpp.TablePropertiesOp):
                continue
            if table_prop_op.table_type.data != TableTypeKind.Scheme:
                continue
            scheme_name = table_prop_op.table_name.data

            for arg_table_op in table_prop_op.body.ops:
                if not isa(arg_table_op, ccpp.ArgumentTableOp):
                    continue
                for arg_op in arg_table_op.body.ops:
                    if not isa(arg_op, ccpp.ArgumentOp):
                        continue
                    if arg_op.standard_name is None:
                        continue
                    std_name = arg_op.standard_name.data
                    if std_name in self._CCPP_INTERNAL:
                        continue

                    if std_name in model_var_index:
                        local_name, module_name, model_memory_space = (
                            model_var_index[std_name]
                        )
                        arg_op.properties["host_var_name"]    = StringAttr(local_name)
                        arg_op.properties["host_module_name"] = StringAttr(module_name)
                        # Propagate model's memory space so GPU passes can
                        # determine the correct OpenACC clause without a
                        # second lookup.  Only set when the model variable
                        # carries an explicit memory_space annotation.
                        if model_memory_space is not None:
                            arg_op.properties["model_var_memory_space"] = (
                                StringAttr(model_memory_space)
                            )
                    elif arg_op.optional is None:
                        errors.append(
                            f"  Scheme '{scheme_name}': argument "
                            f"'{arg_op.arg_name.data}' "
                            f"(standard_name='{std_name}') has no matching "
                            f"host model variable"
                        )

        if errors:
            raise ValueError(
                "Host model variable matching failed:\n" + "\n".join(errors)
            )
