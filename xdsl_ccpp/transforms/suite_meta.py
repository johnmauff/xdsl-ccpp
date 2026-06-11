from dataclasses import dataclass

from xdsl.context import Context
from xdsl.dialects import builtin, func
from xdsl.passes import ModulePass
from xdsl.pattern_rewriter import (
    GreedyRewritePatternApplier,
    InsertPoint,
    PatternRewriter,
    PatternRewriteWalker,
    RewritePattern,
    op_type_rewrite_pattern,
)

from xdsl_ccpp.dialects import ccpp
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    BuildMetaDataDescriptions,
    CCPPType,
)
from xdsl_ccpp.transforms.util.typing import TypeConversions


class MoveCCPPIntoDedicatedModule(RewritePattern):
    """Base class for patterns that relocate CCPP ops into a dedicated module.

    The `generate-meta-cap` pass consolidates all CCPP dialect ops (suites and
    metadata) into a single named ``'ccpp'`` module so that subsequent analysis
    (e.g. `BuildMetaDataDescriptions`) has a single, predictable location to
    traverse.  Subclasses specialise this for each CCPP op type.
    """

    def __init__(self, dedicated_module):
        # Hold a reference to the target module so matched ops can be moved into it
        self.dedicated_module = dedicated_module


class MoveSuiteOpIntoDedicatedModule(MoveCCPPIntoDedicatedModule):
    """Detaches a `ccpp.SuiteOp` from its current parent and appends it to the
    dedicated 'ccpp' module."""

    def __init__(self, dedicated_module):
        super().__init__(dedicated_module)

    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: ccpp.SuiteOp, rewriter: PatternRewriter):
        # Detach the op from wherever it currently lives, then re-insert at the
        # end of the ccpp module's body block
        op.detach()
        rewriter.insert_op(op, InsertPoint.at_end(self.dedicated_module.body.block))


class MoveTablePropertiesOpIntoDedicatedModule(MoveCCPPIntoDedicatedModule):
    """Detaches a `ccpp.TablePropertiesOp` from its current parent and appends it
    to the dedicated 'ccpp' module."""

    def __init__(self, dedicated_module):
        super().__init__(dedicated_module)

    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: ccpp.TablePropertiesOp, rewriter: PatternRewriter):
        # Detach from current location and move to the end of the ccpp module
        op.detach()
        rewriter.insert_op(op, InsertPoint.at_end(self.dedicated_module.body.blocks[0]))


@dataclass(frozen=True)
class MetaCAP(ModulePass):
    """Pass that processes CCPP metadata and generates external function declarations.

    This is the first transform in the CCPP pipeline.  It performs two actions:

    1. **Consolidation**: All `ccpp.SuiteOp` and `ccpp.TablePropertiesOp` nodes are
       moved from the top-level module into a freshly created named module called
       ``'ccpp'``.  This keeps all CCPP dialect IR in one place and separates it
       from the generated cap code that will be built by `generate-suite-cap`.

    2. **Declaration generation**: The metadata in each `ccpp.ArgumentTableOp` is
       inspected and a `func.FuncOp` *external declaration* is emitted for every
       argument table (e.g. ``hello_scheme_run``, ``hello_scheme_init``,
       ``hello_scheme_finalize``).  These declarations define the Fortran-level
       calling interface for each physics scheme entry point, and are later called
       by the suite cap subroutines.

    Pipeline position: **generate-meta-cap** → generate-suite-cap → strip-ccpp → ftn
    """

    name = "generate-meta-cap"

    def generate_function_signature(self, arg_table):
        """Build an external `func.FuncOp` declaration from a CCPP argument table.

        Each argument in the table contributes to either the input or output list
        depending on its ``intent`` attribute:

        - ``intent = in``    → input only
        - ``intent = out``   → output only
        - ``intent = inout`` → both input and output
        - (no intent)        → treated as ``inout`` by convention

        Args:
            arg_table: A `CCPPArgumentTable` descriptor for one scheme entry point.

        Returns:
            An external `func.FuncOp` with the matching MLIR type signature.
        """
        in_args = []
        out_args = []

        # Classify each metadata argument into in/out lists based on its intent
        for fn_arg in arg_table.getFunctionArguments():
            arg_type = TypeConversions.convert(
                fn_arg.getAttr("type"),
                fn_arg.getAttr("kind") if fn_arg.hasAttr("kind") else None,
                fn_arg.getAttr("dimensions") if fn_arg.hasAttr("dimensions") else 0,
            )
            if fn_arg.hasAttr("intent"):
                if fn_arg.getAttr("intent") == "in":
                    in_args.append(arg_type)
                elif fn_arg.getAttr("intent") == "out":
                    out_args.append(arg_type)
                elif fn_arg.getAttr("intent") == "inout":
                    # inout: passed by reference in Fortran — the callee reads and
                    # modifies the argument in-place through the reference.
                    # Only appears in the input list; no separate return value needed.
                    in_args.append(arg_type)
                else:
                    raise AssertionError(
                        f"Unexpected intent: {fn_arg.getAttr('intent')}"
                    )
            else:
                # No intent specified — treat as inout: passed by reference, in-place.
                in_args.append(arg_type)

        return func.FuncOp.external(arg_table.getAttr("name"), in_args, out_args)

    def apply(self, ctx: Context, op: builtin.ModuleOp) -> None:
        # Create the dedicated 'ccpp' module that will hold all CCPP dialect ops
        mod = builtin.ModuleOp([], sym_name=builtin.StringAttr("ccpp"))

        # Move all suite and metadata ops into the dedicated module
        PatternRewriteWalker(
            GreedyRewritePatternApplier(
                [
                    MoveSuiteOpIntoDedicatedModule(mod),
                    MoveTablePropertiesOpIntoDedicatedModule(mod),
                ]
            ),
            apply_recursively=False,
        ).rewrite_module(op)

        # Build Python descriptor objects from the CCPP IR now inside the module
        bmdd = BuildMetaDataDescriptions()
        bmdd.traverse(mod)
        meta_data_descriptions = bmdd.meta_data

        # Generate one external func declaration per argument table (scheme entry points only)
        ops = []
        for prop in meta_data_descriptions.values():
            if prop.getAttr("type") != CCPPType.SCHEME:
                continue
            for table in prop.arg_tables.values():
                ops.append(self.generate_function_signature(table))

        # Append the declarations to the ccpp module, then attach it to the top level
        mod.body.block.add_ops(ops)
        op.body.block.add_op(mod)
