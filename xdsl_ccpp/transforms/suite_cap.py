from dataclasses import dataclass

from xdsl.context import Context
from xdsl.dialects import arith, builtin, memref
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
from xdsl_ccpp.transforms.util.cap_shared import (
    SUITE_CAP_ATTR,
    _build_ddt_resolution_maps,
    _build_host_var_map,
    _host_table_names,
    build_ncol_compute_ops,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    BuildMetaDataDescriptions,
    BuildSchemeDescription,
    collect_ddt_source_modules,
)
from xdsl_ccpp.transforms.util.ir_utils import build_host_var_index, find_ccpp_module
from xdsl_ccpp.transforms.util.suite_variable_model import SuiteVariableModel
from xdsl_ccpp.transforms.util.typing import TypeConversions
from xdsl_ccpp.transforms.suitecap.package_cap import generate_package_caps
from xdsl_ccpp.transforms.suitecap.call_sequence import CallSequenceMixin
from xdsl_ccpp.transforms.suitecap.promotion import PromotionMixin
from xdsl_ccpp.transforms.suitecap.suite_owned import SuiteOwnedMixin
from xdsl_ccpp.transforms.suitecap.phase_functions import PhaseFunctionsMixin
from xdsl_ccpp.transforms.suitecap.module_assembly import ModuleAssemblyMixin
from xdsl_ccpp.transforms.suitecap.gpu import SuiteOwnedGpuMixin
from xdsl_ccpp.transforms.suitecap.block_args import (
    _std_key,
)
from xdsl_ccpp.transforms.suitecap.records import (
    GatherMetaFunctionSignatures,
)
from xdsl_ccpp.transforms.suitecap.resolved_vars import (
    _write_resolved_vars,
)


class GenerateSuiteSubroutine(CallSequenceMixin, PromotionMixin, SuiteOwnedMixin, PhaseFunctionsMixin, ModuleAssemblyMixin, SuiteOwnedGpuMixin, RewritePattern):
    """Rewrites each ccpp.SuiteOp into a named ModuleOp containing the five
    CCPP cap subroutines: initialize, finalize, physics, timestep_initial, and
    timestep_final.  Each subroutine guards scheme calls behind an errflg check
    and manages the ccpp_suite_state lifecycle string.
    """

    def __init__(self, suite_descriptions, meta_data, meta_fn_sigs, top_level_module,
                 ddt_source_module=None,
                 host_var_index=None, ddt_resolution_maps=None, debug_sync=False):
        self.suite_descriptions = suite_descriptions
        self.meta_data = meta_data
        self.meta_fn_sigs = meta_fn_sigs
        self.top_level_module = top_level_module
        # Debug-only; see _inject_suite_owned_gpu_update.
        self.debug_sync = debug_sync
        # Maps DDT type name → Fortran module that defines it (from source_module attr).
        self.ddt_source_module: dict[str, str] = ddt_source_module or {}
        # standard_name -> (local_var_name, module_name, is_host_table, is_protected);
        # only used by --emit-resolved-vars (e.g. host binding for ncol_meta),
        # never by Fortran cap generation.
        self.host_var_index: dict = host_var_index or {}
        # (ddt_instance_map, ddt_parent_map, ddt_host_var_map, host_table_names)
        # for resolving DDT member matches; only used by --emit-resolved-vars
        # (cap generation resolves DDT chains via run_dispatch.py).
        self.ddt_resolution_maps = ddt_resolution_maps
        # Per-phase resolved-variable records from generateSubroutineCall,
        # accumulated across suites/groups; deduped when serialized.
        self.resolved_vars: dict = {}

    @staticmethod
    def _build_ncol_compute_ops(column_range, data_ops, ncol_meta) -> list:
        """Compute ncol = col_end - col_start + 1 and lbound_one; mutates data_ops."""
        if not (column_range and "col_start" in data_ops and "col_end" in data_ops):
            return []
        ncol_ops, ncol_alloc = build_ncol_compute_ops(
            data_ops["col_start"], data_ops["col_end"]
        )
        data_ops["ncol"] = ncol_alloc
        if ncol_meta.name != "ncol":
            data_ops[ncol_meta.name] = ncol_alloc
        # Also under its standard name, as every scheme arg is
        # (block_args._tag_data_ops_by_std_name): ncol replaces the
        # horizontal_loop_extent argument, which has no block argument.
        if ncol_meta.hasAttr("standard_name"):
            data_ops[("std_name", ncol_meta.getAttr("standard_name").lower())] = ncol_alloc
        _ib = TypeConversions.getBaseType("integer")
        lbound_one_alloc = memref.AllocaOp.get(_ib, shape=[])
        lbound_one_alloc.memref.name_hint = "ccpp_lbound_one"
        lbound_one_const = arith.ConstantOp.from_int_and_width(1, 32)
        lbound_one_store = memref.StoreOp.get(lbound_one_const, lbound_one_alloc, [])
        data_ops["ccpp_lbound_one"] = lbound_one_alloc
        return [
            *ncol_ops,
            lbound_one_alloc,
            lbound_one_const,
            lbound_one_store,
        ]

    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: ccpp.SuiteOp, rewriter: PatternRewriter):
        """Generate the complete cap module for one ccpp.SuiteOp."""
        suite_description = self.suite_descriptions[op.suite_name.data]
        suite_model = SuiteVariableModel(suite_description, self.meta_data, _std_key)

        _lc = self._generate_lifecycle_fns(suite_description, suite_model)
        generated_fns = _lc.generated_fns
        fn_sigs_by_name = _lc.fn_sigs_by_name
        suite_host_use_stubs = _lc.suite_host_use_stubs

        scheme_entries = self.getSchemeNames(suite_description)
        suite_lifecycle_schemes = [
            s for s in (suite_description.init_scheme, suite_description.final_scheme) if s
        ]
        fn_sigs = self._build_fn_signatures(fn_sigs_by_name, scheme_entries, suite_lifecycle_schemes)
        type_import_globals = self._build_ddt_use_stubs(scheme_entries)

        all_strings_used = _lc.check_strings_used | _lc.state_strings_used
        ccpp_suite_state_global, string_const_globals = self._build_state_globals(all_strings_used)

        allocatable_mod_vars, interstitial_var_names, run_local_entries = (
            self._build_module_vars(suite_model)
        )
        if allocatable_mod_vars:
            self._inject_safe_deallocs(generated_fns, allocatable_mod_vars, interstitial_var_names)
        if run_local_entries:
            self._inject_run_local_var_handling(generated_fns, run_local_entries)
        self._inject_suite_owned_gpu_update(
            generated_fns, suite_model, self.meta_data, debug_sync=self.debug_sync
        )
        self._inject_suite_owned_gpu_exit(generated_fns, suite_model)

        seen_stubs: set = set()
        deduped_stubs = []
        for stub in suite_host_use_stubs:
            key = (stub.sym_name.data,
                   stub.attributes.get("module").data if stub.attributes.get("module") else "")
            if key not in seen_stubs:
                seen_stubs.add(key)
                deduped_stubs.append(stub)

        scheme_mod = builtin.ModuleOp(
            [ccpp_suite_state_global] + string_const_globals
            + type_import_globals + deduped_stubs + allocatable_mod_vars + generated_fns + fn_sigs,
            sym_name=builtin.StringAttr(op.suite_name.data + "_cap"),
        )
        scheme_mod.attributes[SUITE_CAP_ATTR] = builtin.StringAttr(op.suite_name.data)
        rewriter.insert_op(scheme_mod, InsertPoint.at_start(self.top_level_module.body.block))


@dataclass(frozen=True)
class SuiteCAP(ModulePass):
    """MLIR pass that generates CCPP cap subroutines from ccpp.SuiteOp nodes.

    Traverses the top-level module looking for the named 'ccpp' sub-module,
    collects metadata and scheme descriptions from it, then rewrites each
    ccpp.SuiteOp into a self-contained ModuleOp containing the five lifecycle
    cap subroutines.
    """

    name = "generate-suite-cap"

    emit_resolved_vars: "str | None" = None
    """Optional path: write a JSON file of the resolved variables required at
    each CCPP lifecycle phase (a native introspection artifact --
    host-model consumers like a
    write_init_files.py-equivalent read this instead of any capgen-v1 object).

    Not a flag of this pass directly in normal use: supplied via
    ``--emit-resolved-vars`` on the ``ccpp_xdsl`` CLI (``ccpp_dsl.py``'s
    ``ccppMain``), which threads it into this ``generate-suite-cap`` pass
    parameter when building the ``ccpp_opt -p`` pipeline string.
    """

    debug_sync: bool = False
    """Debug-only: when set, also emit an `update self(...)` immediately
    after every scheme call that writes (intent out/inout) a
    memory_space=device SuiteOwned var, regardless of divergence status --
    see _inject_suite_owned_gpu_update/_build_suite_owned_debug_sync_touches.
    Supplied via ``--gpu-debug-sync`` on the ``ccpp_xdsl`` CLI, the same way
    ``emit_resolved_vars`` above is threaded in.
    """

    def apply(self, ctx: Context, op: builtin.ModuleOp) -> None:
        ccpp_mod = find_ccpp_module(op.body.block.ops)
        assert ccpp_mod is not None

        # Build Python descriptor objects from the CCPP metadata IR
        bmdd = BuildMetaDataDescriptions()
        bmdd.traverse(ccpp_mod)
        meta_data_descriptions = bmdd.meta_data

        # Collect the function signatures already declared in the ccpp module
        meta_fn_sig = GatherMetaFunctionSignatures()
        meta_fn_sig.traverse(ccpp_mod)
        meta_fn_sigs = meta_fn_sig.meta_functions

        # Build a map from suite name to its SuiteOp descriptor
        bsd = BuildSchemeDescription()
        bsd.traverse(ccpp_mod)
        scheme_descriptions = bsd.schemes

        # Build DDT-type-name → Fortran-module-name map (shared utility).
        ddt_source_module = collect_ddt_source_modules(ccpp_mod)

        # Only needed for --emit-resolved-vars; skip the table traversal otherwise.
        host_var_index = build_host_var_index(ccpp_mod) if self.emit_resolved_vars else {}

        # Likewise only for --emit-resolved-vars (_apply_ddt_chain).
        ddt_resolution_maps = None
        if self.emit_resolved_vars:
            ddt_instance_map, ddt_parent_map = _build_ddt_resolution_maps(meta_data_descriptions)
            ddt_host_var_map = _build_host_var_map(meta_data_descriptions)
            host_table_names = _host_table_names(meta_data_descriptions)
            ddt_resolution_maps = (ddt_instance_map, ddt_parent_map, ddt_host_var_map, host_table_names)

        generator = GenerateSuiteSubroutine(
            scheme_descriptions, meta_data_descriptions, meta_fn_sigs, op,
            ddt_source_module=ddt_source_module,
            host_var_index=host_var_index,
            ddt_resolution_maps=ddt_resolution_maps,
            debug_sync=self.debug_sync,
        )
        PatternRewriteWalker(
            GreedyRewritePatternApplier([generator]),
            apply_recursively=False,
        ).rewrite_module(op)
        generate_package_caps(generator, op)

        if self.emit_resolved_vars:
            _write_resolved_vars(
                generator.resolved_vars, self.emit_resolved_vars, host_vars=ddt_host_var_map,
            )
