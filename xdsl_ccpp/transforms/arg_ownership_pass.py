from dataclasses import dataclass

from xdsl.context import Context
from xdsl.dialects import builtin
from xdsl.passes import ModulePass
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects import ccpp
from xdsl_ccpp.dialects.ccpp import TableTypeKind
from xdsl_ccpp.transforms.util.cap_shared import (
    _build_host_var_map,
    _collect_host_block_std_names,
    classify_arg_ownership,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import BuildMetaDataDescriptions
from xdsl_ccpp.transforms.util.ir_utils import find_ccpp_module


@dataclass(frozen=True)
class ArgOwnershipPass(ModulePass):
    """Annotate every SCHEME ccpp.arg op with its ownership_kind (see
    ArgOwnershipKind in ccpp.py) -- does the cap own this arg, or does its
    data come from outside?

    Phase 7, Stage 2 ("dual-build, don't switch consumers") of the full IR
    unification plan in ccpp_cap_refactor_plan.md: computes the same
    ownership decision suite_cap.py's _is_framework_managed and
    ccpp_cap.py's _build_cap_var_map each independently (re-)compute today,
    durable on the arg itself, alongside those existing mechanisms -- neither
    is switched to read this yet, so this pass has no observable effect on
    generated output.

    Pipeline position: must run after generate-host-match (needs
    model_var_name to be set to recognize HostMatched args) and before
    generate-suite-cap (the whole point is computing this before any suite's
    subroutine signature exists). Harmless to run even without host
    metadata -- HostMatched simply never triggers, matching how
    generate-host-match itself is conditional on host files being provided.
    """

    name = "generate-arg-ownership"

    def apply(self, ctx: Context, op: builtin.ModuleOp) -> None:
        ccpp_mod = find_ccpp_module(op.body.block.ops)
        if ccpp_mod is None:
            return

        bmdd = BuildMetaDataDescriptions()
        bmdd.traverse(ccpp_mod)
        meta_data = bmdd.meta_data

        host_var_map_lc = _build_host_var_map(meta_data, include_host=False)
        host_block_std_names = _collect_host_block_std_names(meta_data)

        for table_prop_op in ccpp_mod.body.ops:
            if not isa(table_prop_op, ccpp.TablePropertiesOp):
                continue
            if table_prop_op.table_type.data != TableTypeKind.Scheme:
                continue

            for arg_table_op in table_prop_op.body.ops:
                if not isa(arg_table_op, ccpp.ArgumentTableOp):
                    continue
                for arg_op in arg_table_op.body.ops:
                    if not isa(arg_op, ccpp.ArgumentOp):
                        continue
                    ownership = classify_arg_ownership(
                        arg_op, host_var_map_lc, host_block_std_names
                    )
                    arg_op.properties["ownership_kind"] = ownership.ownership_kind
