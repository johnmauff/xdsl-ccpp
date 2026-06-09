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
    """Annotate scheme ccpp.arg ops with their matched host variable.

    Builds a standard_name → (local_var_name, module_name) index from
    HOST and MODULE metadata, then walks all SCHEME argument tables and
    sets host_var_name / host_module_name on each arg op whose standard_name
    appears in the index.

    Required scheme arguments with no host match are collected and reported
    together as a ValueError rather than failing on the first mismatch.

    Pipeline position: generate-meta-cap → generate-host-match → generate-suite-cap
    """

    name = "generate-host-match"

    # Standard names that are always provided by the CCPP framework itself,
    # or are derived/computed by the generated cap rather than passed directly
    # from a host module variable — skip matching these against host metadata.
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

        # ── Step 1: build host variable index ─────────────────────────────
        # standard_name → (local_var_name, module_name)
        host_index = {}

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
                        host_index[arg_op.standard_name.data] = (
                            arg_op.arg_name.data,
                            table_prop_op.table_name.data,
                        )

        # ── Step 2: match scheme arguments ────────────────────────────────
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

                    if std_name in host_index:
                        local_name, module_name = host_index[std_name]
                        arg_op.properties["host_var_name"]    = StringAttr(local_name)
                        arg_op.properties["host_module_name"] = StringAttr(module_name)
                    elif arg_op.optional is None:
                        errors.append(
                            f"  Scheme '{scheme_name}': argument "
                            f"'{arg_op.arg_name.data}' "
                            f"(standard_name='{std_name}') has no matching "
                            f"host variable"
                        )

        if errors:
            raise ValueError(
                "Host variable matching failed:\n" + "\n".join(errors)
            )
