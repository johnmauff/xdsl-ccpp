from xdsl.dialects import builtin
from xdsl.utils.hints import isa


def find_ccpp_module(ops):
    """Return the named @ccpp ModuleOp from the given op list, or None."""
    for op in ops:
        if (
            isa(op, builtin.ModuleOp)
            and op.sym_name is not None
            and op.sym_name.data == "ccpp"
        ):
            return op
    return None


def build_host_var_index(ccpp_mod):
    """Walk HOST/MODULE argument tables and return a standard_name
    (lowercased) -> (local_var_name, module_name, is_host_table, is_protected)
    index.

    A smaller, side-effect-free sibling of HostVariableMatchPass's own
    _build_model_var_index (host_var_match_pass.py) -- deliberately
    separate rather than reused directly, since that method also emits a
    CcppHandleOp as a side effect, which must only ever happen once (during
    the real generate-host-match pass), not on every reuse. This one is
    read-only.

    Used by generate-suite-cap's --emit-resolved-vars introspection to
    recover a host binding for framework-level identities (e.g.
    horizontal_dimension) that no scheme argument in a suite directly
    carries once physics-mode column-dispatch has synthesized
    col_start/col_end in its place (capgen_v1_parity_backlog.md Stage 7).
    DDT tables are intentionally excluded -- not needed for this lookup.
    """
    from xdsl_ccpp.dialects import ccpp
    from xdsl_ccpp.dialects.ccpp import TableTypeKind

    index: dict = {}
    for table_prop_op in ccpp_mod.body.ops:
        if not isa(table_prop_op, ccpp.TablePropertiesOp):
            continue
        if table_prop_op.table_type.data not in (
            TableTypeKind.Module, TableTypeKind.Host
        ):
            continue
        is_host_table = table_prop_op.table_type.data == TableTypeKind.Host
        for arg_table_op in table_prop_op.body.ops:
            if not isa(arg_table_op, ccpp.ArgumentTableOp):
                continue
            for arg_op in arg_table_op.body.ops:
                if not isa(arg_op, ccpp.ArgumentOp):
                    continue
                if arg_op.standard_name is not None:
                    # Direct assignment, not setdefault: on a duplicate
                    # standard_name across tables, the last one encountered
                    # wins, matching HostVariableMatchPass._build_model_var_index's
                    # own overwrite semantics exactly -- setdefault (first
                    # wins) would let this fallback index disagree with
                    # real host-match behavior if duplicates exist.
                    index[arg_op.standard_name.data.lower()] = (
                        arg_op.arg_name.data, table_prop_op.table_name.data,
                        is_host_table, arg_op.protected is not None,
                    )
                # end if
            # end for
        # end for
    # end for
    return index
