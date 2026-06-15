from dataclasses import dataclass

from xdsl.context import Context
from xdsl.dialects import builtin
from xdsl.passes import ModulePass
from xdsl.rewriter import InsertPoint, Rewriter
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects import ccpp
from xdsl_ccpp.util.ccpp_conventions import CCPP_KIND_TO_ISO


@dataclass(frozen=True)
class MetaKind(ModulePass):
    """Pass that discovers real kind parameters from CCPP metadata and records them.

    Runs after ``generate-meta-cap``, which has already consolidated all CCPP IR
    into the ``@ccpp`` named module.  This pass walks every ``ccpp.arg`` op inside
    that module and collects the unique kind names attached to ``real`` arguments
    (e.g. ``kind_phys``).

    If any are found, a single ``ccpp.kinds`` op is prepended to the ``@ccpp``
    module's body, containing one ``ccpp.kind`` op per unique kind name.  The
    kind ops appear in the order they were first encountered.

    If no real kinds are present, the ``@ccpp`` module is left unchanged.

    Pipeline position: generate-meta-cap → **generate-meta-kinds** → generate-suite-cap
    """

    name = "generate-meta-kinds"

    def apply(self, ctx: Context, op: builtin.ModuleOp) -> None:
        # Locate the @ccpp named module created by generate-meta-cap
        ccpp_module = None
        for inner_op in op.body.ops:
            if (
                isa(inner_op, builtin.ModuleOp)
                and inner_op.sym_name is not None
                and inner_op.sym_name.data == "ccpp"
            ):
                ccpp_module = inner_op
                break

        if ccpp_module is None:
            return

        # Collect unique real kind names in encounter order.
        # Use a dict as an ordered set (insertion-ordered since Python 3.7).
        kind_names: dict[str, None] = {}

        for table_prop_op in ccpp_module.body.ops:
            if not isa(table_prop_op, ccpp.TablePropertiesOp):
                continue
            for arg_table_op in table_prop_op.body.ops:
                if not isa(arg_table_op, ccpp.ArgumentTableOp):
                    continue
                for arg_op in arg_table_op.body.ops:
                    if not isa(arg_op, ccpp.ArgumentOp):
                        continue
                    # A real arg with a named kind qualifier (not a len= qualifier)
                    if (
                        arg_op.arg_type.data == "real"
                        and arg_op.kind is not None
                        and "len=" not in arg_op.kind.data
                    ):
                        kind_names[arg_op.kind.data] = None

        if not kind_names:
            return

        # Build one ccpp.kind op per unique kind name.
        # Known kind names are mapped to their ISO_FORTRAN_ENV equivalents;
        # unrecognised kinds fall back to using the kind name as the value.
        _KIND_VALUES = CCPP_KIND_TO_ISO
        kind_ops = [
            ccpp.KindOp(kind_name, _KIND_VALUES.get(kind_name, kind_name))
            for kind_name in kind_names
        ]

        kinds_op = ccpp.KindsOp(kind_ops)
        Rewriter.insert_op(kinds_op, InsertPoint.at_start(ccpp_module.body.block))
