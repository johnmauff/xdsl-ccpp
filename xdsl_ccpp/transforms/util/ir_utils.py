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
