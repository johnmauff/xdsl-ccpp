from dataclasses import dataclass

from xdsl.context import Context
from xdsl.dialects import builtin
from xdsl.passes import ModulePass
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects import ccpp
from xdsl_ccpp.dialects.ccpp_utils import KindDefOp


@dataclass(frozen=True)
class GenerateKinds(ModulePass):
    """Pass that generates a @ccpp_kinds named module from ccpp.kinds metadata.

    Runs after ``generate-ccpp-cap``.  Looks for a ``ccpp.kinds`` op inside the
    ``@ccpp`` named module (placed there by ``generate-meta-kinds``).  For each
    ``ccpp.kind`` child op it creates a ``ccpp_utils.kind_def`` op and places
    all of them into a new named module ``@ccpp_kinds``, which is appended to
    the top-level IR.

    If no ``ccpp.kinds`` op is present the pass is a no-op and no ``@ccpp_kinds``
    module is created.

    Pipeline position: generate-ccpp-cap → **generate-kinds** → strip-ccpp
    """

    name = "generate-kinds"

    def apply(self, ctx: Context, op: builtin.ModuleOp) -> None:
        # Locate the @ccpp named module
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

        # Find the ccpp.kinds op (inserted by generate-meta-kinds)
        kinds_op = None
        for inner_op in ccpp_module.body.ops:
            if isa(inner_op, ccpp.KindsOp):
                kinds_op = inner_op
                break

        if kinds_op is None:
            return

        # Build one ccpp_utils.kind_def op per ccpp.kind child
        kind_def_ops = [
            KindDefOp(kind_op.kind_name.data, kind_op.kind_value.data, kind_op.kind_module.data)
            for kind_op in kinds_op.body.ops
            if isa(kind_op, ccpp.KindOp)
        ]

        # Create the @ccpp_kinds named module and append it to the top-level IR
        ccpp_kinds_mod = builtin.ModuleOp(
            kind_def_ops, sym_name=builtin.StringAttr("ccpp_kinds")
        )
        op.body.block.add_op(ccpp_kinds_mod)
