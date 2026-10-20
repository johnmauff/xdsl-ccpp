from dataclasses import dataclass

from xdsl.context import Context
from xdsl.dialects import builtin
from xdsl.passes import ModulePass
from xdsl.pattern_rewriter import (
    PatternRewriter,
    PatternRewriteWalker,
    RewritePattern,
    op_type_rewrite_pattern,
)
from xdsl.rewriter import InsertPoint

from xdsl_ccpp.dialects.ccpp import CompositeOp


class InlineComposite(RewritePattern):
    """Replace a `ccpp.composite` with its body, in place.

    The composite's scheme calls, subcycles and nested composites move into the
    enclosing group, subcycle or composite at the composite's position, so the
    call order is unchanged.  Nested composites are inlined in turn by the
    walker's recursive application.
    """

    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: CompositeOp, rewriter: PatternRewriter):
        rewriter.inline_block(op.body.block, InsertPoint.before(op))
        rewriter.erase_op(op)


@dataclass(frozen=True)
class FlattenComposites(ModulePass):
    """Pass that lowers composite schemes by inlining them into their callers.

    composite-scheme Stage 2 (composite_scheme_plan.md §11, S2-1): composites
    are recorded in the IR, then flattened before every other pass, so the
    generated code is identical to the equivalent flat suite.  A module without
    composites is left unchanged.
    """

    name = "flatten-composites"

    def apply(self, ctx: Context, op: builtin.ModuleOp) -> None:
        PatternRewriteWalker(InlineComposite()).rewrite_module(op)
