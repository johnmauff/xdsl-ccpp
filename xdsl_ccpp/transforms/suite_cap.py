import re
from dataclasses import dataclass

from xdsl.context import Context
from xdsl.dialects import arith, builtin, func, llvm, memref, scf
from xdsl.dialects.builtin import (
    ArrayAttr,
    DictionaryAttr,
    MemRefType,
    StringAttr,
    i8,
    i32,
)
from xdsl.ir import Block, Region, SSAValue
from xdsl.passes import ModulePass
from xdsl.pattern_rewriter import (
    GreedyRewritePatternApplier,
    InsertPoint,
    PatternRewriter,
    PatternRewriteWalker,
    RewritePattern,
    op_type_rewrite_pattern,
)
from xdsl.rewriter import Rewriter
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects import ccpp, ccpp_utils
from xdsl_ccpp.dialects.ccpp import ArgOwnershipKind
from xdsl_ccpp.dialects.ccpp_utils import (
    ActiveCheckOp,
    ArraySectionOp,
    ClearStringOp,
    KeywordCallOp,
    KindCastOp,
    KindWriteBackOp,
    LazyAllocOp,
    ModuleVarOp,
    PresentCheckOp,
    PromotionLoopOp,
    RankReducingSliceOp,
    SafeDeallocOp,
    SubcycleLoopOp,
    UnitConvertOp,
    UnitWriteBackOp,
    VerticalFlipOp,
    VerticalFlipWriteBackOp,
)
from xdsl_ccpp.transforms.util.cap_shared import (
    LIFECYCLE_POSTFIX_ALIASES,
    _build_ddt_resolution_maps,
    _build_host_var_map,
    _collect_ddt_use_stubs,
    _host_table_names,
    _iter_schemes,
    _resolve_ddt_access_path,
    _resolve_member_subscripts,
    classify_host_table_vars,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    BuildMetaDataDescriptions,
    BuildSchemeDescription,
    CCPPArgument,
    XMLSubcycle,
    XMLSuite,
    collect_ddt_source_modules,
)
from xdsl_ccpp.transforms.util.ir_utils import build_host_var_index, find_ccpp_module
from xdsl_ccpp.transforms.util.suite_variable_model import SuiteVariableModel
from xdsl_ccpp.transforms.util.typing import TypeConversions
from xdsl_ccpp.util.ccpp_conventions import (
    CCPP_DEPRECATED_STD_NAMES,
    CCPP_ERRMSG_LEN,
    CCPP_ERROR_CODE,
    CCPP_ERROR_MESSAGE,
    CCPP_HORIZ_DIM_STD_NAME,
    CCPP_INSTANCE_NUMBER_STD_NAME,
    CCPP_KIND_PHYS,
    CCPP_LOOP_BEGIN_STD_NAME,
    CCPP_LOOP_END_STD_NAME,
    CCPP_LOOP_EXTENT_STD_NAME,
    CCPP_NUMBER_OF_INSTANCES_STD_NAME,
    CCPP_SUBCYCLE_UNKNOWN_LOOP_COUNT,
    UNIT_CONVERSIONS,
    dims_compatible,
    is_dispatch_scalar_std_name,
    is_vertical_dimension,
    normalize_units,
)
from xdsl_ccpp.util.visitor import Visitor

# CCPP lifecycle phase names (matching CCPP_STATE_MACH.transitions()'s
# capgen-v1 naming), keyed by (tgt_subroutine_postfix, physics_mode) as
# generateSubroutineCall is actually invoked with. physics_mode=True
# (the run/group-dispatch calls) always maps to "run" regardless of
# tgt_subroutine_postfix.
_PHASE_NAMES: dict = {
    ("_register", False): "register",
    ("_init", False): "initialize",
    ("_finalize", False): "finalize",
    ("_timestep_initialize", False): "timestep_initial",
    ("_timestep_finalize", False): "timestep_final",
}


def _normalize_std_name(name: str) -> str:
    """Map a deprecated CCPP standard name to its modern replacement (e.g.
    horizontal_loop_extent -> horizontal_dimension), else return it
    unchanged. Keeps --emit-resolved-vars output on the same modern naming
    convention regardless of which convention a given scheme's metadata
    still uses -- otherwise a consumer comparing against capgen-v1's own
    (already-normalized) output would see two different names for the same
    concept depending on which scheme happened to declare it.
    """
    return CCPP_DEPRECATED_STD_NAMES.get(name.lower(), name)


def _resolved_var_record(arg) -> "dict | None":
    """Extract a JSON-safe resolved-variable record from a descriptor/IR arg.

    Returns None for args with no standard_name (e.g. the synthetic
    col_start/col_end loop-bound scalars _classify_args introduces for
    physics_mode calls) -- capgen_v1_parity_backlog.md Stage 2 found these
    have no CCPP metadata identity, so a ResolvedVar-style consumer
    (write_init_files.py keys everything off standard_name) has nothing
    to do with them.
    """
    if not arg.hasAttr("standard_name"):
        return None
    dim_names = list(arg.getAttr("dim_names")) if arg.hasAttr("dim_names") else []
    return {
        "standard_name": _normalize_std_name(arg.getAttr("standard_name")),
        "intent": arg.getAttr("intent") if arg.hasAttr("intent") else None,
        "is_advected": arg.hasAttr("advected"),
        "is_constituent": arg.hasAttr("constituent"),
        # A scheme arg never carries 'protected' directly -- only the
        # matched host/module declaration does (model_var_is_protected,
        # set by HostVariableMatchPass). arg.hasAttr("protected") covers
        # the (currently unused-in-practice) case of a host/module arg
        # itself being passed through this same function directly.
        "is_protected": arg.hasAttr("protected") or arg.hasAttr("model_var_is_protected"),
        "is_optional": arg.hasAttr("optional"),
        "is_host_table_var": arg.hasAttr("model_var_is_host_table"),
        "model_var_name": arg.getAttr("model_var_name") if arg.hasAttr("model_var_name") else None,
        "model_module_name": arg.getAttr("model_module_name") if arg.hasAttr("model_module_name") else None,
        # Default to model_var_name/None, matching the plain (non-DDT)
        # case where there's nothing to distinguish -- _apply_ddt_chain
        # overwrites these three (import_name, call_expr, and
        # model_module_name itself) for a DDT member match, since
        # model_module_name there is the DDT *type* name, not a real
        # module, and needs resolving to the type's actual instance
        # variable before it means anything to a Fortran `use` statement.
        "import_name": arg.getAttr("model_var_name") if arg.hasAttr("model_var_name") else None,
        "call_expr": arg.getAttr("model_var_name") if arg.hasAttr("model_var_name") else None,
        "array_ref_dims": [],
        "dim_names": [_normalize_std_name(d) for d in dim_names],
        "ownership_kind": str(arg.getAttr("ownership_kind")) if arg.hasAttr("ownership_kind") else None,
    }


def _ddt_member_subscript_std_names(member_expr: str) -> list:
    """Extract the raw standard-name subscript tokens from a DDT member's
    array-section expression (e.g. "t(:,:,index_of_potential_temperature)"
    -> ["index_of_potential_temperature"]), before any local-name
    substitution.

    Mirrors cap_shared.py's own _resolve_member_subscripts tokenization,
    kept separate since that function resolves straight to local names via
    a host_var_map (right for building call_expr), but array_ref_dims
    needs the original standard names instead, for write_init_files.py's
    own resolve_by_standard_name recursion (_get_host_model_import) to
    pull in each index variable's own `use` import independently.
    """
    paren = member_expr.find("(")
    if paren < 0:
        return []
    subscript = member_expr[paren + 1: member_expr.rfind(")")]
    return [
        t for t in (tok.strip() for tok in subscript.split(","))
        if t and t != ":" and not t.isdigit()
    ]


def _apply_ddt_chain(record: dict, arg, ddt_resolution_maps) -> None:
    """Patch <record> in place for a DDT member match, resolving the DDT
    *type* name _resolved_var_record left in model_module_name into the
    real Fortran chain -- e.g. model_var_name="theta",
    model_module_name="physics_state" (the DDT type/table name, not a
    real module) becomes model_module_name="physics_types_ddt",
    import_name="phys_state", call_expr="phys_state%theta".

    No-op when <arg> isn't a DDT member match, or when
    <ddt_resolution_maps> is None (--emit-resolved-vars not requested --
    see GenerateSuiteSubroutine.__init__).  Also no-op (leaves the
    pre-patch defaults, matching run_dispatch.py's own soft-fail
    behavior for this case) if no reachable module-level instance exists
    for the DDT type -- should not happen for an arg host_var_match_pass
    already accepted as DDT-matched.

    When the resolved instance lives in a HOST-type table (e.g. a
    ccpp_t-style handle passed through the host's own caller-provided
    argument list, not use-associated), model_module_name/import_name are
    still populated with the real table/instance identity -- same as a
    plain, non-DDT host-table match already does elsewhere in this file --
    but is_host_table_var is also set, so a consumer that (per that same
    existing convention) already checks is_host_table_var before deciding
    whether `use <module>, only: <var>` is valid Fortran won't be misled
    into treating a caller-provided block argument as use-associable.
    Mirrors the same distinction run_dispatch.py's own real cap-generation
    path makes for this exact case (see that file's ArgSourceKind.Block
    branch and its own comment there).
    """
    if ddt_resolution_maps is None or not arg.hasAttr("model_var_is_ddt"):
        return
    ddt_instance_map, ddt_parent_map, ddt_host_var_map, host_table_names = ddt_resolution_maps
    ddt_type_name = record["model_module_name"]
    result = _resolve_ddt_access_path(ddt_type_name, ddt_instance_map, ddt_parent_map)
    if result is None:
        return
    instance_var, instance_module, path_prefix, _instance_array_dim = result
    member_expr = path_prefix + record["model_var_name"]
    resolved_member, _sub_vars = _resolve_member_subscripts(member_expr, ddt_host_var_map)
    record["model_module_name"] = instance_module
    record["import_name"] = instance_var
    record["call_expr"] = f"{instance_var}%{resolved_member}"
    record["array_ref_dims"] = _ddt_member_subscript_std_names(member_expr)
    if instance_module in host_table_names:
        record["is_host_table_var"] = True


def _write_resolved_vars(resolved_vars: dict, path: str, host_vars: dict = None) -> None:
    """Serialize per-phase resolved-variable records to JSON at *path*.

    Deduped by standard_name within each phase (keeping the first record
    seen) -- capgen-v1's own call_list(phase) is likewise one combined list
    per phase, not per-suite/per-group, and a suite with multiple groups
    active in the same phase (e.g. several physics groups all needing the
    same host variable in their own "run" dispatch) would otherwise produce
    duplicate entries for the same standard_name.

    <host_vars>, if given, is cap_shared.py's _build_host_var_map result
    (standard_name -> (local_name, table_name) over every HOST/MODULE
    table, not just names some suite call actually resolved) -- written out
    as a top-level "host_vars" key so a consumer's resolve_by_standard_name
    can look up *any* host-declared variable, not only ones that happen to
    also appear in some phase's own call list. Needed for e.g. a DDT
    member's array-section index variable (see _apply_ddt_chain's
    array_ref_dims), which is a real host variable but is never itself a
    scheme argument, so it would otherwise never appear anywhere in
    "phases".
    """
    import json

    deduped: dict = {}
    for phase_name, records in resolved_vars.items():
        seen: set = set()
        phase_list = []
        for record in records:
            sn = record["standard_name"]
            if sn in seen:
                continue
            seen.add(sn)
            phase_list.append(record)
        deduped[phase_name] = phase_list

    out = {"phases": deduped}
    if host_vars:
        out["host_vars"] = {
            std_name: list(entry) for std_name, entry in host_vars.items()
        }

    with open(path, "w") as f:
        json.dump(out, f, indent=2)


class GatherMetaFunctionSignatures(Visitor):
    """Collects all external func.FuncOp declarations from the ccpp module.

    These declarations represent the scheme subroutine signatures generated
    by the generate-meta-cap pass and are needed when building call sites.
    """

    def __init__(self):
        self.meta_functions = {}

    def traverse_func_op(self, func_op: func.FuncOp):
        # Only record external declarations, not definitions
        if func_op.is_declaration:
            self.meta_functions[func_op.sym_name.data] = func_op


@dataclass
class _ArgTableResult:
    scheme_entries: list
    arg_tables: dict
    scheme_overrides: dict
    actual_postfixes: dict
    all_args: dict
    suite_use_stubs: list
    divergent_std_keys: frozenset


@dataclass
class _ArgClassification:
    framework_vars: dict
    input_arg_list: list
    output_arg_list: list
    ncol_meta: "object | None"


@dataclass
class _BlockSignature:
    new_block: "object"
    input_arg_types: list
    data_ops: dict
    alloc_ops: dict
    kind_cast_ops: list
    kind_writeback_pairs: list
    unit_convert_ops: list
    unit_writeback_pairs: list


@dataclass
class _LifecycleFnsResult:
    generated_fns: list
    fn_sigs_by_name: dict
    suite_host_use_stubs: list
    check_strings_used: set
    state_strings_used: set


class GenerateSuiteSubroutine(RewritePattern):
    """Rewrites each ccpp.SuiteOp into a named ModuleOp containing the five
    CCPP cap subroutines: initialize, finalize, physics, timestep_initial, and
    timestep_final.  Each subroutine guards scheme calls behind an errflg check
    and manages the ccpp_suite_state lifecycle string.
    """

    def __init__(self, suite_descriptions, meta_data, meta_fn_sigs, top_level_module,
                 ddt_source_module=None,
                 host_var_index=None, ddt_resolution_maps=None):
        self.suite_descriptions = suite_descriptions
        self.meta_data = meta_data
        self.meta_fn_sigs = meta_fn_sigs
        self.top_level_module = top_level_module
        # Maps DDT type name → Fortran module that defines it (from source_module attr).
        self.ddt_source_module: dict[str, str] = ddt_source_module or {}
        # standard_name -> (local_var_name, module_name, is_host_table, is_protected) over HOST/MODULE
        # tables (util/ir_utils.py's build_host_var_index) -- used only by
        # the --emit-resolved-vars introspection path (generateSubroutineCall)
        # to recover a host binding for framework-level identities like
        # horizontal_dimension that ncol_meta itself was never host-matched
        # against (capgen_v1_parity_backlog.md Stage 7). Not used by, and
        # has no effect on, actual Fortran cap generation.
        self.host_var_index: dict = host_var_index or {}
        # (ddt_instance_map, ddt_parent_map, ddt_host_var_map,
        # host_table_names) from cap_shared.py's _build_ddt_resolution_maps/
        # _build_host_var_map/_host_table_names -- the same DDT-chain
        # resolution real cap generation already uses (run_dispatch.py,
        # gpu_ccpp_cap_pass.py) to turn a DDT member match
        # (model_var_is_ddt set, model_module_name holding the DDT *type*
        # name rather than a real Fortran module) into the actual dotted
        # Fortran reference. Reused here, read-only, only by the
        # --emit-resolved-vars introspection path (generateSubroutineCall)
        # -- not used by, and has no effect on, actual Fortran cap
        # generation, which resolves this independently via run_dispatch.py.
        self.ddt_resolution_maps = ddt_resolution_maps
        # Per-phase resolved-variable records (capgen_v1_parity_backlog.md
        # Stage 3), populated by generateSubroutineCall. Scoped to this
        # instance (one per SuiteCAP.apply() call), not global state --
        # appended across every ccpp.SuiteOp/group this instance processes,
        # deduped by standard_name at serialization time in SuiteCAP.apply().
        self.resolved_vars: dict = {}

    def getSchemeNames(self, suite_description):
        """Return a flat list of (scheme_name, overrides) pairs from all groups.

        Flattens through XMLSubcycle nodes so the result is always a plain
        sequence of scheme entries regardless of subcycle structure.
        ``overrides`` is a plain ``{arg_name: literal_str}`` dict, empty when
        the scheme was not called with keyword argument overrides.
        """
        return [
            (scheme.attributes["name"], scheme.attributes.get("arg_overrides", {}))
            for group in suite_description
            for scheme in _iter_schemes(group)
        ]

    def _build_call_sequence_items(self, node):
        """Recursively build the ordered item list for one group/subcycle's
        direct children.

        Each element is one of:
          ``('scheme',   scheme_name, overrides)``                              — flat call
          ``('subcycle', loop_count, is_literal, [item, item, ...])``           — subcycle block

        A subcycle's own item list uses this same shape recursively, so a
        nested `XMLSubcycle` child (a `<subcycle>` inside another
        `<subcycle>`) becomes a nested ``('subcycle', ...)`` item, to
        arbitrary depth, rather than a flat scheme list -- e.g.
        examples/var_compat/var_compatibility_suite.xml, which nests three
        levels deep in one branch. Shared by `getCallSequence` (called once
        per group) and itself (called recursively per nested subcycle).
        """
        items = []
        for child in node:
            if isinstance(child, XMLSubcycle):
                items.append((
                    "subcycle", child.attributes["loop_count"],
                    child.attributes["is_literal"],
                    self._build_call_sequence_items(child),
                ))
            else:
                items.append((
                    "scheme", child.attributes["name"],
                    child.attributes.get("arg_overrides", {}),
                ))
        return items

    def getCallSequence(self, suite_description):
        """Return the ordered call sequence, preserving subcycle boundaries.

        See `_build_call_sequence_items` for the item shape.
        """
        sequence = []
        for group in suite_description:
            sequence.extend(self._build_call_sequence_items(group))
        return sequence

    def _scheme_has_promoted_args(self, arg_table) -> bool:
        """Return True if any argument in arg_table is marked is_promoted."""
        for arg in arg_table.getFunctionArguments():
            if arg.hasAttr("is_promoted"):
                return True
        return False

    @staticmethod
    def _std_key(arg) -> str:
        """Return the standard_name (lowercase) if set, otherwise the local arg name."""
        if arg.hasAttr("standard_name"):
            return arg.getAttr("standard_name").lower()
        return arg.name

    @staticmethod
    def _vertical_dim_index(fn_arg) -> "int | None":
        """Return the 1-based Fortran dimension index of fn_arg's vertical
        (layer) dimension, or None if it has no recognized one.

        dim_names (set by BuildSchemeDescription from the ArgumentOp's own
        dim_names property) preserves the scheme's own declared dimension
        order, so this is per-scheme -- correct even if two schemes sharing
        a standard_name order their dimensions differently.
        """
        if not fn_arg.hasAttr("dim_names"):
            return None
        for idx, dim_name in enumerate(fn_arg.getAttr("dim_names")):
            if is_vertical_dimension(dim_name):
                return idx + 1
        return None

    def _find_loop_upper_bound(self, promoted_dim: str, all_args, data_ops,
                               framework_ref_ops=None, suite_use_stubs=None):
        """Find the SSA value to use as the promotion loop's upper bound.

        First searches all_args (current group's scheme args) for an integer
        with the matching standard_name.  If not found — e.g. when a per-group
        function needs 'vertical_layer_dimension' but no scheme in the group
        declares it explicitly — falls back to scanning MODULE-type host tables
        in self.meta_data.  On a hit it creates a HostVarRefOp, registers it in
        data_ops, and appends it to framework_ref_ops so the Fortran printer sees
        the variable before any scheme calls.

        A third fallback derives the size from an already in-scope array's own
        declared dim_names, when promoted_dim is never any scheme's own arg
        AND never declared in a MODULE-type table -- e.g.
        examples/constituents_dim's qbase (dims=horizontal_dimension,
        vertical_layer_dimension): neither dimension is ever a scheme's own
        arg, and host_data.meta declares them but is type=host, which is
        deliberately excluded from the second fallback above (HOST-type vars
        are never use-associated anywhere in this codebase -- see
        host_block_std_names/is_host_table -- so extending that scan to
        HOST-type tables would be inconsistent with every other treatment of
        them, and outright wrong for a HOST-type table with no real backing
        Fortran module at all, e.g. examples/constituents_dim's own
        test_host.meta). coupler_flux/qtend are both already in-scope
        arguments dimensioned by (horizontal_dimension,
        number_of_ccpp_constituents)/(horizontal_dimension,
        vertical_layer_dimension) respectively; size() on either gives
        exactly the value the host itself allocated it with, using values
        already threaded into this call, not a new argument or a cross-
        module reference.
        """
        for arg in all_args.values():
            if (
                arg.hasAttr("standard_name")
                and dims_compatible(arg.getAttr("standard_name"), promoted_dim)
                and arg.getAttr("type") == "integer"
                and arg.name in data_ops
            ):
                return data_ops[arg.name]

        # Not found in scheme args — try MODULE-type host tables.
        from xdsl_ccpp.transforms.util.ccpp_descriptors import CCPPType
        from xdsl_ccpp.transforms.util.typing import TypeConversions
        for tbl_name, props in self.meta_data.items():
            if props.getAttr("type") != CCPPType.MODULE:
                continue
            if tbl_name not in props.arg_tables:
                continue
            for var in props.getArgTable(tbl_name).getFunctionArguments():
                if (var.hasAttr("standard_name")
                        and dims_compatible(var.getAttr("standard_name"), promoted_dim)
                        and var.getAttr("type") == "integer"):
                    # Reuse existing SSA if this dim var is already in data_ops
                    # (e.g. previously added by a prior LazyAllocOp dim lookup).
                    if var.name in data_ops:
                        return data_ops[var.name]
                    # Create a new HostVarRefOp + USE stub.
                    int_type = TypeConversions.getBaseType("integer")
                    ref = ccpp_utils.HostVarRefOp(var.name, tbl_name,
                                                  memref.MemRefType(int_type, []))
                    ref.res.name_hint = var.name
                    data_ops[var.name] = ref
                    if framework_ref_ops is not None:
                        framework_ref_ops.append(ref)
                    if suite_use_stubs is not None:
                        stub = llvm.GlobalOp(
                            llvm.LLVMArrayType.from_size_and_type(1, i8),
                            var.name, "external",
                        )
                        stub.attributes["module"] = StringAttr(tbl_name)
                        suite_use_stubs.append(stub)
                    return data_ops[var.name]

        # Still not found — derive it from an already in-scope array's own
        # shape instead of requiring a dedicated scalar dimension arg.
        # Excludes SuiteOwned candidates: those are guaranteed-allocated by
        # the *end* of this same _build_framework_refs pass, not necessarily
        # by the time THIS specific var's own dim lookup runs within it (a
        # SuiteOwned var can even match itself here, since data_ops[fw_arg.name]
        # is set to its own HostVarRefOp before its allocation dims are
        # resolved -- confirmed the hard way: qbase's own vertical_layer_
        # dimension entry matched qbase itself, producing a self-referential
        # size(qbase, 2) on an array not yet allocated).
        for arg in all_args.values():
            if not arg.hasAttr("dim_names") or arg.name not in data_ops:
                continue
            if arg.getAttr("ownership_kind") == ArgOwnershipKind.SuiteOwned:
                continue
            for idx, dim_name in enumerate(arg.getAttr("dim_names"), start=1):
                if dims_compatible(dim_name, promoted_dim):
                    int_type = TypeConversions.getBaseType("integer")
                    size_ref = ccpp_utils.CapVarRefOp(
                        f"size({arg.name}, {idx})",
                        memref.MemRefType(int_type, []),
                    )
                    if framework_ref_ops is not None:
                        framework_ref_ops.append(size_ref)
                    return size_ref.res
        return None

    def _resolve_host_only_std_name(self, std_name: str):
        """Find a host-declared arg with this exact standard_name, scanning
        every non-scheme table in self.meta_data (module, host, or ddt --
        unlike _find_loop_upper_bound's fallback above, which only scans
        MODULE-type tables for a different case, a promotion loop's upper
        bound). Used for a subcycle's own dynamic loop-count standard_name
        when no scheme anywhere declares a matching arg of its own, so it
        never enters all_args through the ordinary scheme-arg host-matching
        path the way e.g. scheme_order_in_suite does (several schemes'
        own .meta files declare that one as their own arg; nothing declares
        num_subcycles_for_effr as its own arg anywhere in examples/var_compat).
        """
        from xdsl_ccpp.transforms.util.ccpp_descriptors import CCPPType
        for tbl_name, props in self.meta_data.items():
            if props.getAttr("type") == CCPPType.SCHEME:
                continue
            if tbl_name not in props.arg_tables:
                continue
            for var in props.getArgTable(tbl_name).getFunctionArguments():
                if (var.hasAttr("standard_name")
                        and var.getAttr("standard_name").lower() == std_name.lower()):
                    return var
        return None

    def _synthesize_dynamic_loop_count_args(self, suite_description, arg_tables, all_args) -> None:
        """Mutate all_args in place: for every subcycle in suite_description
        with a dynamic (non-literal) loop count whose standard_name has no
        matching scheme arg anywhere, synthesize a fresh HostMatched
        CCPPArgument for it -- named after the host's own local variable --
        so it becomes a genuine, correctly-declared dummy argument of the
        suite subroutine the same way any other host-matched value already
        does. Without this, _emit_subcycle would have nothing but the raw,
        undeclared standard_name to print as the Fortran do-loop bound.

        arg_tables is per-postfix (only schemes with an entry point matching
        the CURRENT tgt_subroutine_postfix, e.g. "_init" vs "_run" vs
        "_finalize"). A subcycle's loop count is only actually needed for
        postfixes where at least one of its own schemes (recursively) is in
        arg_tables -- matching _emit_subcycle_items's own "if sn in
        arg_tables" filter exactly -- so this only fires for the specific
        postfix that will actually emit a SubcycleLoopOp using it, not every
        lifecycle postfix the suite happens to have (register/finalize/
        timestep_initial/timestep_final have no subcycles of their own to
        emit at all, and must not gain an unused dummy argument here).

        Only called when physics_mode is True (see the caller in
        _build_arg_tables): _emit_subcycle itself only ever emits a
        SubcycleLoopOp under that same condition (its own "if _lc_int > 1
        and physics_mode and body_ops" guard) -- a postfix like "_init" can
        still have every one of a subcycle's own schemes present in
        arg_tables (e.g. effr_calc has both a _run and an _init entry
        point), so the arg_tables-based check above isn't sufficient on its
        own to avoid adding an unused argument to non-physics postfixes.
        """
        def _subcycle_has_active_schemes(items) -> bool:
            for item in items:
                if item[0] == "scheme":
                    _, sn, _ = item
                    if sn in arg_tables:
                        return True
                else:
                    _, _, _, sub_items = item
                    if _subcycle_has_active_schemes(sub_items):
                        return True
            return False

        def _collect_dynamic_counts(items) -> set:
            counts: set = set()
            for item in items:
                if item[0] == "subcycle":
                    _, loop_count, is_literal, sub_items = item
                    if not is_literal and _subcycle_has_active_schemes(sub_items):
                        counts.add(loop_count)
                    counts |= _collect_dynamic_counts(sub_items)
            return counts

        call_sequence = self.getCallSequence(suite_description)
        for std_name in _collect_dynamic_counts(call_sequence):
            std_key = std_name.lower()
            if std_key in all_args:
                continue
            host_var = self._resolve_host_only_std_name(std_name)
            if host_var is None:
                continue
            new_arg = CCPPArgument(host_var.name)
            new_arg.setAttr("standard_name", std_name)
            new_arg.setAttr("type", host_var.getAttr("type"))
            new_arg.setAttr("intent", "in")
            if host_var.hasAttr("kind"):
                new_arg.setAttr("kind", host_var.getAttr("kind"))
            new_arg.setAttr("dimensions", 0)
            new_arg.setAttr("ownership_kind", ArgOwnershipKind.HostMatched)
            all_args[std_key] = new_arg

    def _is_multi_instance_host(self) -> bool:
        """True only when the host declares BOTH instance_number and
        number_of_instances.

        instance_number/number_of_instances are a single paired contract,
        not two independent optionals -- every multi-instance codepath
        (ccpp_suite_state's own allocatable-array declaration, the
        constituent-API lc_instances(:) bundle, both synthesis methods
        below) assumes both are present together. Checking only
        instance_number (this method's own predecessor, before this fix)
        let a host declaring just one of the two enable multi-instance
        wrapping with no matching allocation support elsewhere -- e.g.
        ccpp_suite_state declared allocatable but never actually allocated,
        since the lazy-alloc guard in generateSubroutineCall separately
        requires ninstances_local_name too. Caught by Copilot review on
        PR #77 (for the analogous ccpp_cap.py/constituent_cap.py/
        lifecycle_cap.py pairing); this is the same bug class in
        suite_cap.py's own, separate ccpp_suite_state gating.
        """
        return (
            self._resolve_host_only_std_name(CCPP_INSTANCE_NUMBER_STD_NAME) is not None
            and self._resolve_host_only_std_name(CCPP_NUMBER_OF_INSTANCES_STD_NAME) is not None
        )

    def _synthesize_instance_number_arg(self, all_args) -> None:
        """Mutate all_args in place: if the host declares an
        instance_number-standard-name scalar (real capgen-v1's
        multi-instance model, ccpp_cap_refactor_plan.md's "instances/
        instances_advection" entry) and no scheme's own entry point for
        this phase already provides one, synthesize a fresh HostMatched
        CCPPArgument for it -- named after the host's own local variable --
        exactly as _synthesize_dynamic_loop_count_args already does for a
        subcycle's dynamic loop count.

        Real capgen-v1 treats instance_number as a fixed CCPP-protocol
        argument present on *every* lifecycle call (register/init/
        finalize/timestep_init/timestep_final/run), regardless of whether
        any particular scheme's own entry point for that phase happens to
        declare it -- e.g. examples/instances' own schemes declare
        instance_number only on their _run entry point, never on
        _register/_init/_finalize, yet the driver calls
        ccpp_register(..., instance=ins, ...) for every instance the same
        way real capgen-v1's own driver does.

        Without this, a multi-instance suite's register/init/finalize/
        timestep_init/timestep_final subroutines have no way to know which
        instance's own ccpp_suite_state entry to check/set -- see
        generateStateCheckOps/generateStateAssignment -- which is exactly
        the bug a real ctest failure exposed on examples/instances: every
        instance shared one scalar ccpp_suite_state, so registering
        instance 2 saw instance 1's own already-'initialized' state and
        errored.

        Called for every phase, not just physics_mode (unlike
        _synthesize_dynamic_loop_count_args) -- and is a no-op unless the
        host declares BOTH instance_number and number_of_instances (see
        _is_multi_instance_host), so ordinary (non-multi-instance) suites,
        and hosts declaring only one of the pair, are entirely unaffected.
        """
        std_key = CCPP_INSTANCE_NUMBER_STD_NAME.lower()
        if std_key in all_args:
            return
        if not self._is_multi_instance_host():
            return
        host_var = self._resolve_host_only_std_name(CCPP_INSTANCE_NUMBER_STD_NAME)
        new_arg = CCPPArgument(host_var.name)
        new_arg.setAttr("standard_name", CCPP_INSTANCE_NUMBER_STD_NAME)
        new_arg.setAttr("type", host_var.getAttr("type"))
        new_arg.setAttr("intent", "in")
        if host_var.hasAttr("kind"):
            new_arg.setAttr("kind", host_var.getAttr("kind"))
        new_arg.setAttr("dimensions", 0)
        new_arg.setAttr("ownership_kind", ArgOwnershipKind.HostMatched)
        all_args[std_key] = new_arg

    def _synthesize_number_of_instances_arg(self, all_args) -> None:
        """Mutate all_args in place: companion to
        _synthesize_instance_number_arg, for number_of_instances.

        Threaded the same way real capgen-v1 threads it: as an ordinary
        caller-supplied dummy argument, never use-associated -- confirmed
        against examples/instances' own test_host.meta, a HOST-type table
        with no backing test_host.F90 module at all (the driver, main.F90,
        supplies the value directly; there is nothing to `use`). Its own
        block-arg SSA value sizes ccpp_suite_state's allocation -- see
        generateSubroutineCall's own instance_local_name/
        _build_suite_state_lazy_alloc wiring.

        A no-op unless the host declares BOTH names (see
        _is_multi_instance_host), exactly like _synthesize_instance_number_arg.
        """
        std_key = CCPP_NUMBER_OF_INSTANCES_STD_NAME.lower()
        if std_key in all_args:
            return
        if not self._is_multi_instance_host():
            return
        host_var = self._resolve_host_only_std_name(CCPP_NUMBER_OF_INSTANCES_STD_NAME)
        new_arg = CCPPArgument(host_var.name)
        new_arg.setAttr("standard_name", CCPP_NUMBER_OF_INSTANCES_STD_NAME)
        new_arg.setAttr("type", host_var.getAttr("type"))
        new_arg.setAttr("intent", "in")
        if host_var.hasAttr("kind"):
            new_arg.setAttr("kind", host_var.getAttr("kind"))
        new_arg.setAttr("dimensions", 0)
        new_arg.setAttr("ownership_kind", ArgOwnershipKind.HostMatched)
        all_args[std_key] = new_arg

    def _instance_arg_local_name(self, input_arg_list) -> "str | None":
        """Return the local Fortran name of input_arg_list's own
        instance_number-standard-name arg, or None if this subroutine's
        signature has none (a non-multi-instance suite)."""
        std_key = CCPP_INSTANCE_NUMBER_STD_NAME.lower()
        for a in input_arg_list:
            if self._std_key(a) == std_key:
                return a.name
        return None

    def _number_of_instances_local_name(self, input_arg_list) -> "str | None":
        """Return the local Fortran name of input_arg_list's own
        number_of_instances-standard-name arg, or None if this
        subroutine's signature has none."""
        std_key = CCPP_NUMBER_OF_INSTANCES_STD_NAME.lower()
        for a in input_arg_list:
            if self._std_key(a) == std_key:
                return a.name
        return None

    @staticmethod
    def _build_suite_state_lazy_alloc(ninstances_ssa) -> "LazyAllocOp":
        """Return a LazyAllocOp allocating ccpp_suite_state -- dimensioned
        by ninstances_ssa (this call's own already-in-scope
        number_of_instances dummy arg -- see
        _synthesize_number_of_instances_arg/
        _number_of_instances_local_name, resolved from data_ops by the
        caller) and initialized to 'uninitialized' -- on first use.

        number_of_instances is a genuine runtime HOST-declared scalar in
        real capgen-v1's own model (confirmed against
        ccpp-framework-fresh/capgen/generator/suite_cap.py), not a
        compile-time constant, so ccpp_suite_state can only become a
        correctly-sized array via a real Fortran ALLOCATE at runtime --
        reusing the same guarded "if (.not. allocated(...))" LazyAllocOp
        idiom already used for SuiteOwned/framework arrays (see
        _build_framework_refs), rather than inventing a second mechanism.
        Threaded as an ordinary dummy argument, not use-associated --
        examples/instances' own test_host.meta is a HOST-type table with
        no backing test_host.F90 module at all, so there is nothing to
        `use`; ninstances_ssa is already the right SSA value precisely
        because _synthesize_number_of_instances_arg put it in the block's
        own arg list.
        """
        return LazyAllocOp(
            var_name="ccpp_suite_state",
            kind_name="character",
            dim_var_refs=[ninstances_ssa],
            init_value="'uninitialized'",
        )

    def _build_promoted_call_ops(
        self,
        subroutine_name,
        arg_table,
        data_ops,
        loop_var_memref,
        overrides=None,
        ncol_ref=None,
    ):
        """Build scheme call ops for a promoted scheme inside the loop body.

        For arguments marked is_promoted, replaces the raw 2D data_ops value
        with a RankReducingSliceOp that slices out the current level.
        The dim_pattern is constructed from the promoted_dim annotation.

        ncol_ref is the resolved column-count SSA value (the caller looks it
        up via _find_loop_upper_bound against CCPP_HORIZ_DIM_STD_NAME) used
        as the range upper bound for block-arg column slices. Under the
        legacy horizontal_loop_extent mechanism this used to be reliably
        available as data_ops["ncol"] (synthesized by _build_ncol_compute_ops
        whenever a scheme declared col_start/col_end directly); under the
        horizontal_dimension convention that key is never populated, so
        falling back to data_ops.get("ncol", loop_var_memref) would silently
        substitute the promotion loop's own index variable as the column
        upper bound -- wrong, and easy to miss since it still produces valid-
        looking Fortran.
        """
        promoted_data_ops = dict(data_ops)  # shallow copy to override promoted args

        # Separate slice ops by whether the source arg is optional+promoted.
        # Optional-promoted slices live only in the with_body of PresentCheckOp.
        # Shared slices are emitted unconditionally before any guard.
        shared_slice_ops: list = []
        opt_slice_ops: dict[str, object] = {}  # arg_name -> RankReducingSliceOp

        def _get_lbound_one():
            # Lazily create (and cache in data_ops for reuse) a constant-1
            # alloca for block-arg lower bounds. Under the legacy
            # horizontal_loop_extent mechanism this was always pre-created by
            # _build_ncol_compute_ops, but that only fires when a scheme
            # declares col_start/col_end directly -- under the
            # horizontal_dimension convention col_start/col_end are resolved
            # elsewhere (run_dispatch.py), so it may not exist yet here.
            if "ccpp_lbound_one" not in data_ops:
                _ib = TypeConversions.getBaseType("integer")
                _alloc = memref.AllocaOp.get(_ib, shape=[])
                _alloc.memref.name_hint = "ccpp_lbound_one"
                _const = arith.ConstantOp.from_int_and_width(1, 32)
                _store = memref.StoreOp.get(_const, _alloc, [])
                shared_slice_ops.extend([_alloc, _const, _store])
                data_ops["ccpp_lbound_one"] = _alloc
            return data_ops["ccpp_lbound_one"]

        for arg in arg_table.getFunctionArguments():
            needs_slice = arg.hasAttr("is_promoted")
            # Also slice interstitial vars where the module-level allocation rank
            # exceeds the scheme's declared rank (e.g. to_promote allocated 2D but
            # the consuming scheme expects 1D).
            if not needs_slice and arg.hasAttr("is_interstitial") and arg.name in data_ops:
                val = data_ops[arg.name]
                actual_type = val.type if isinstance(val, SSAValue) else val.results[0].type
                if isinstance(actual_type, MemRefType):
                    actual_rank = len(actual_type.shape.data)
                    scheme_rank = arg.getAttr("dimensions") if arg.hasAttr("dimensions") else 0
                    needs_slice = (actual_rank > scheme_rank > 0)
            if not needs_slice:
                continue
            if arg.name not in data_ops:
                continue
            # Build the dimension pattern.
            # For is_promoted args: use dim_names + promoted_dim annotation.
            # For interstitial rank-mismatch: infer pattern from actual vs scheme rank.
            # Pattern: 'R' = range (col_start:col_end), 'S' = scalar (loop var index).
            pattern = ""
            range_lowers = []
            range_uppers = []
            scalar_indices_list = []

            if arg.hasAttr("is_promoted"):
                dim_names = arg.getAttr("dim_names") if arg.hasAttr("dim_names") else []
                val = data_ops[arg.name]
                # Module-level vars (HostVarRefOp, ArraySectionOp) live in the full
                # domain — slice with col_start:col_end.
                # Block args are 1-based within the function (passed as sections from
                # the host) — slice with 1:ncol instead.
                is_module_var = not isinstance(val, SSAValue)
                # For block args, use the pre-created ccpp_lbound_one alloca
                # (set up in generateSubroutineCall at function scope so the
                # Fortran printer can declare it before the promotion loop).
                for dim in dim_names:
                    pattern += "R"
                    if is_module_var:
                        range_lowers.append(data_ops.get("col_start", loop_var_memref))
                        range_uppers.append(data_ops.get("col_end", loop_var_memref))
                    else:
                        range_lowers.append(_get_lbound_one())
                        range_uppers.append(
                            ncol_ref if ncol_ref is not None
                            else data_ops.get("ncol", loop_var_memref)
                        )
                # Promoted dimension(s) appended as scalar index
                pattern += "S"
                scalar_indices_list.append(loop_var_memref)
            else:
                # Interstitial rank mismatch: scheme_rank 'R' dims + extra 'S' dims
                scheme_rank = arg.getAttr("dimensions") if arg.hasAttr("dimensions") else 0
                val = data_ops[arg.name]
                actual_type = val.type if isinstance(val, SSAValue) else val.results[0].type
                actual_rank = len(actual_type.shape.data) if isinstance(actual_type, MemRefType) else scheme_rank
                for _ in range(scheme_rank):
                    pattern += "R"
                    range_lowers.append(data_ops.get("col_start", loop_var_memref))
                    range_uppers.append(data_ops.get("col_end", loop_var_memref))
                for _ in range(actual_rank - scheme_rank):
                    pattern += "S"
                    scalar_indices_list.append(loop_var_memref)

            if pattern and ("S" in pattern):
                slice_op = RankReducingSliceOp(
                    source=data_ops[arg.name],
                    dim_pattern=pattern,
                    range_lowers=range_lowers,
                    range_uppers=range_uppers,
                    scalar_indices=scalar_indices_list,
                )
                promoted_data_ops[arg.name] = slice_op
                # Keep the standard_name-tagged entry (see _build_framework_refs)
                # in sync with this arg's own bare-name entry in THIS local
                # copy -- generateSchemeSubroutineCallOps prefers the tagged
                # entry, and without this it would still resolve to the
                # pre-slice value inherited from the shallow copy above.
                promoted_data_ops[("std_name", self._std_key(arg))] = slice_op
                is_opt_promoted = arg.hasAttr("optional") and arg.hasAttr("is_promoted")
                if is_opt_promoted:
                    opt_slice_ops[arg.name] = slice_op
                else:
                    shared_slice_ops.append(slice_op)

        # Identify optional promoted args — these require a present() guard.
        optional_promoted_names = [
            arg.name
            for arg in arg_table.getFunctionArguments()
            if arg.hasAttr("optional") and arg.hasAttr("is_promoted")
        ]

        if not optional_promoted_names:
            # No optional promoted args — emit a single call (non-optional path).
            call_ops = self.generateSchemeSubroutineCallOps(
                subroutine_name, arg_table, promoted_data_ops, overrides or {}
            )
            return shared_slice_ops + call_ops

        optional_promoted_set = set(optional_promoted_names)

        # with_body: slice ops for optional args + call including all optional args
        with_call_ops = self.generateSchemeSubroutineCallOps(
            subroutine_name, arg_table, promoted_data_ops, overrides or {}
        )
        with_body_ops = list(opt_slice_ops.values()) + with_call_ops

        # without_body: call omitting all optional promoted args
        without_call_ops = self.generateSchemeSubroutineCallOps(
            subroutine_name, arg_table, promoted_data_ops, overrides or {},
            exclude_args=optional_promoted_set,
        )

        # Use the first optional promoted arg as the guard name (bare Fortran name).
        # All optional promoted args in a single scheme are treated as a group.
        # TODO: handle each independently for full generality.
        guard_name = optional_promoted_names[0]
        present_op = PresentCheckOp(guard_name, with_body_ops, without_call_ops)
        return shared_slice_ops + [present_op]

    _ACTIVE_EXPR_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

    def _active_expr_var_indexes(self) -> dict:
        """Return use_associated_index for resolving 'active = <expr>'
        property text: standard_name.lower() -> (local_name, table_name,
        ftn_type).

        Covers every MODULE-type var (always use-associated in this
        codebase) *and* every 'state'-classified HOST-type var -- real
        host-owned data with its own backing Fortran module (Stage 2a of
        the vocabulary-resolution redesign, ccpp_cap_refactor_plan.md:
        resolved the same way MODULE-type vars already are, via a USE stub,
        rather than threaded as a dummy argument the way every HOST-type
        var used to be regardless of classification).

        'dispatch_scalar'-classified HOST-type vars (the fixed
        CCPP-protocol set -- loop bounds, error handling) are deliberately
        excluded: they have no backing Fortran module to use-associate
        from, and no example anywhere gates an optional arg on one (nor
        does it make semantic sense to -- a loop bound or error code isn't
        the kind of thing a scheme's optionality would depend on).
        _resolve_active_condition raises a clear error if one is ever
        referenced in an 'active =' expression rather than silently
        threading an untested dummy-argument workaround for a case that
        has never actually occurred (Stage 3 of the redesign -- see
        ccpp_cap_refactor_plan.md).
        """
        from xdsl_ccpp.transforms.util.ccpp_descriptors import CCPPType

        host_classification = classify_host_table_vars(self.meta_data)
        use_associated_index: dict = {}
        for tbl_name, props in self.meta_data.items():
            tbl_type = props.getAttr("type")
            if tbl_type not in (CCPPType.MODULE, CCPPType.HOST):
                continue
            if tbl_name not in props.arg_tables:
                continue
            for var in props.getArgTable(tbl_name).getFunctionArguments():
                if not var.hasAttr("standard_name"):
                    continue
                std_name = var.getAttr("standard_name").lower()
                if tbl_type == CCPPType.MODULE or host_classification.get(std_name) == "state":
                    use_associated_index[std_name] = (var.name, tbl_name, var.getAttr("type"))
        return use_associated_index

    def _active_expr_ddt_member_indexes(self) -> dict:
        """Return standard_name.lower() -> (member_local_name, ddt_type_name)
        for every member of every DDT-type table.

        Companion to _active_expr_var_indexes: an 'active = <expr>' token
        may reference a DDT member instead of a plain MODULE/HOST-state var
        -- e.g. examples/instances' own data_array_opt, gated on
        flag_for_opt_array, a member of the instance_type DDT (real
        capgen-v1's multi-instance model: instance_type's own module-level
        instance, instance_data, is a HOST-owned array of DDT, one entry
        per model instance -- see cap_shared.py's own
        _build_ddt_resolution_maps). _resolve_active_condition uses this to
        resolve such a token via the exact same DDT-access-path machinery
        run_dispatch.py's own DDT-member resolution already uses.
        """
        from xdsl_ccpp.transforms.util.ccpp_descriptors import CCPPType

        ddt_member_index: dict = {}
        for tbl_name, props in self.meta_data.items():
            if props.getAttr("type") != CCPPType.DDT:
                continue
            if tbl_name not in props.arg_tables:
                continue
            for var in props.getArgTable(tbl_name).getFunctionArguments():
                if not var.hasAttr("standard_name"):
                    continue
                ddt_member_index[var.getAttr("standard_name").lower()] = (var.name, tbl_name)
        return ddt_member_index

    def _resolve_active_condition(
        self, raw_expr: str, suite_use_stubs: list, arg_table=None,
    ) -> str:
        """Resolve a host/module var's 'active = <expr>' property text into
        an expression that's actually valid Fortran at the suite-cap call
        site, emitting whatever USE stub(s) a use-associated reference needs.

        The raw property text (e.g. "(flag_indicating_cloud_microphysics_
        has_graupel)") is written in *standard-name* space -- CCPP's own
        convention for this property, matching how default_value/dimension
        expressions work: identifier-like tokens are standard-name
        references to be resolved at the point of use, not pre-baked local
        Fortran names. Printing it verbatim (the first cut of this fix)
        compiles as a reference to an undeclared symbol the moment the real
        local name differs from the standard name -- confirmed by gfortran
        in CI on examples/var_compat and examples/nested_suite's own
        flag_indicating_cloud_microphysics_has_graupel -> has_graupel case.

        A MODULE-type reference, or a 'state'-classified HOST-type reference
        (Stage 2a of the vocabulary-resolution redesign -- e.g. opt_arg's
        own flag_for_opt_arg, data.meta's type=host but genuinely
        host-owned state), resolves to its own local name and emits a USE
        stub for it. A 'dispatch_scalar'-classified HOST-type reference
        (loop bounds, error handling) raises rather than being silently
        supported -- see _active_expr_var_indexes.

        A DDT-member reference (e.g. examples/instances' own
        flag_for_opt_array, a member of the instance_type DDT -- see
        _active_expr_ddt_member_indexes) resolves via the same
        _resolve_ddt_access_path machinery run_dispatch.py's own DDT-member
        resolution uses. When the DDT's own module-level instance is itself
        a HOST-owned array of model instances (real capgen-v1's
        multi-instance model, ccpp_cap_refactor_plan.md's "instances/
        instances_advection" entry), <arg_table> -- the calling scheme's
        own _run table -- must have a sibling instance_number-standard-name
        arg to index by; this raises a clear error rather than silently
        emitting an unindexed (and therefore wrong) reference if it
        doesn't, matching the dispatch_scalar case's own philosophy. Found
        via a real gfortran CI failure on examples/instances: printing the
        bare standard-name text verbatim compiled fine for opt_arg's own
        flag_for_opt_arg only by coincidence (its local name happens to
        equal its standard name) -- this DDT-member case never worked, it
        was simply never exercised until this example's active-gated
        data_array_opt.

        A token that doesn't resolve to any known standard_name is left
        as-is (assumed to be a Fortran keyword/operator, e.g. '.and.'/'.not.').
        """
        use_associated_index = self._active_expr_var_indexes()
        ddt_member_index = self._active_expr_ddt_member_indexes()

        def _resolve_ddt_member(std_name: str, member_local_name: str, ddt_type_name: str) -> str:
            ddt_instance_map, ddt_parent_map = _build_ddt_resolution_maps(self.meta_data)
            result = _resolve_ddt_access_path(ddt_type_name, ddt_instance_map, ddt_parent_map)
            if result is None:
                raise ValueError(
                    f"'active = {raw_expr}' references {std_name!r}, a member "
                    f"of DDT type {ddt_type_name!r} with no reachable "
                    f"module-level instance -- cannot resolve to a real "
                    f"Fortran reference."
                )
            instance_var, instance_module, path_prefix, instance_array_dim = result
            member_ref = path_prefix + member_local_name
            if instance_array_dim is not None:
                index_local_name = None
                if arg_table is not None:
                    for arg in arg_table.getFunctionArguments():
                        if (
                            arg.hasAttr("standard_name")
                            and arg.getAttr("standard_name").lower()
                                == CCPP_INSTANCE_NUMBER_STD_NAME
                        ):
                            index_local_name = arg.name
                            break
                if index_local_name is None:
                    raise ValueError(
                        f"'active = {raw_expr}' references {std_name!r}, a "
                        f"member of {instance_var!r}, a HOST-owned array of "
                        f"model instances -- but this scheme's own call has "
                        f"no sibling {CCPP_INSTANCE_NUMBER_STD_NAME!r} arg to "
                        f"index it by, so there is no way to know which "
                        f"instance's value to test."
                    )
                base_name = f"{instance_var}({index_local_name})"
            else:
                base_name = instance_var
            if not any(
                isinstance(existing, llvm.GlobalOp)
                and existing.sym_name.data == instance_var
                and existing.attributes.get("module") == StringAttr(instance_module)
                for existing in suite_use_stubs
            ):
                stub = llvm.GlobalOp(
                    llvm.LLVMArrayType.from_size_and_type(1, i8),
                    instance_var, "external",
                )
                stub.attributes["module"] = StringAttr(instance_module)
                suite_use_stubs.append(stub)
            return f"{base_name}%{member_ref}"

        def _substitute(match: "re.Match") -> str:
            token = match.group(0)
            std_name = token.lower()
            entry = use_associated_index.get(std_name)
            if entry is not None:
                local_name, module_name, _ftn_type = entry
                already_stubbed = any(
                    isinstance(existing, llvm.GlobalOp)
                    and existing.sym_name.data == local_name
                    and existing.attributes.get("module") == StringAttr(module_name)
                    for existing in suite_use_stubs
                )
                if not already_stubbed:
                    stub = llvm.GlobalOp(
                        llvm.LLVMArrayType.from_size_and_type(1, i8),
                        local_name, "external",
                    )
                    stub.attributes["module"] = StringAttr(module_name)
                    suite_use_stubs.append(stub)
                return local_name
            ddt_entry = ddt_member_index.get(std_name)
            if ddt_entry is not None:
                member_local_name, ddt_type_name = ddt_entry
                return _resolve_ddt_member(std_name, member_local_name, ddt_type_name)
            if is_dispatch_scalar_std_name(std_name):
                raise ValueError(
                    f"'active = {raw_expr}' references {std_name!r}, a CCPP "
                    f"dispatch-scalar standard name (loop bounds/error "
                    f"handling) with no backing Fortran module to "
                    f"use-associate from. Gating an optional arg's presence "
                    f"on one isn't supported -- no example does this, and it "
                    f"has no clear Fortran realization. Give the host a "
                    f"real state variable to gate on instead."
                )
            return token

        return self._ACTIVE_EXPR_TOKEN_RE.sub(_substitute, raw_expr)

    def _build_active_gated_call_ops(
        self, subroutine_name, arg_table, data_ops, overrides=None,
        divergent_std_keys: frozenset = frozenset(), *, suite_use_stubs: list,
    ):
        """Build scheme call ops for a non-promoted (flat) scheme call,
        gating any optional arg whose matched host var carries an 'active'
        Fortran logical expression (model_var_active_expr, set by
        HostVariableMatchPass from the host/module declaration's own
        'active' property) behind an ActiveCheckOp -- so its allocation/
        unit-conversion/marshaling and the call itself only execute when
        that host-side expression is true.

        This is the flat-call counterpart to _build_promoted_call_ops's own
        PresentCheckOp guard: that one tests Fortran's present() intrinsic
        for optional args inside a rank-reduction promotion loop; this one
        tests an arbitrary named host condition for optional args with no
        promotion involved -- the two mechanisms answer different questions
        ("did the caller pass this?" vs "is this host variable currently
        active?") and are not interchangeable, even though both gate an
        'optional' arg.

        A scheme's own optional args can be gated by more than one distinct
        condition -- confirmed real, not hypothetical: examples/var_compat's
        effr_calc_run has effrg_in/ncg_in gated by 'has_graupel' and
        nci_out/effri_out independently gated by 'has_ice'. Treating every
        active-gated arg as one group under a single shared condition (this
        function's first cut) silently mis-gated whichever condition wasn't
        picked -- e.g. with has_graupel picked, nci_out/effri_out would be
        computed even when has_ice is false, and dropped even when has_ice
        is true and has_graupel is false. Each distinct condition gets its
        own ActiveCheckOp instead, nested so every combination of the N
        conditions' truth values reaches the one call variant with exactly
        the right args included (2**N leaf calls) -- N is the number of
        *distinct* conditions on one scheme, not the number of gated args,
        and stays small in practice (2 today).
        """
        active_gated_names: dict = {}  # raw condition_expr -> [arg_name, ...]
        for arg in arg_table.getFunctionArguments():
            if arg.hasAttr("optional") and arg.hasAttr("model_var_active_expr"):
                active_gated_names.setdefault(
                    arg.getAttr("model_var_active_expr"), []
                ).append(arg.name)

        if not active_gated_names:
            return self.generateSchemeSubroutineCallOps(
                subroutine_name, arg_table, data_ops, overrides or {},
                divergent_std_keys=divergent_std_keys,
            )

        raw_conditions = list(active_gated_names)
        resolved_conditions: dict[int, str] = {}

        def _build_leaf(excluded_names: frozenset) -> list:
            if excluded_names:
                return self.generateSchemeSubroutineCallOps(
                    subroutine_name, arg_table, data_ops, overrides or {},
                    exclude_args=excluded_names,
                    divergent_std_keys=divergent_std_keys,
                )
            return self.generateSchemeSubroutineCallOps(
                subroutine_name, arg_table, data_ops, overrides or {},
                divergent_std_keys=divergent_std_keys,
            )

        def _build_level(level: int, excluded_names: frozenset) -> list:
            if level == len(raw_conditions):
                return _build_leaf(excluded_names)
            raw_condition_expr = raw_conditions[level]
            if level not in resolved_conditions:
                resolved_conditions[level] = self._resolve_active_condition(
                    raw_condition_expr, suite_use_stubs, arg_table
                )
            condition_expr = resolved_conditions[level]
            with_ops = _build_level(level + 1, excluded_names)
            without_ops = _build_level(
                level + 1,
                excluded_names | frozenset(active_gated_names[raw_condition_expr]),
            )
            return [ActiveCheckOp(condition_expr, with_ops, without_ops)]

        return _build_level(0, frozenset())

    def getArgumentTable(self, scheme_name, subroutine_name):
        """Look up the argument table for a specific scheme subroutine.

        Returns None if the scheme has no entry for subroutine_name (optional
        entry points such as _finalize may be absent).
        """
        if scheme_name not in self.meta_data:
            raise ValueError(
                f"No metadata found for scheme '{scheme_name}'. "
                f"Did you include its .meta file in --scheme-files?\n"
                f"Known schemes: {sorted(self.meta_data.keys())}"
            )
        arg_tables = self.meta_data[scheme_name].arg_tables
        return arg_tables.get(subroutine_name)

    def _build_suite_lifecycle_call_ops(
        self, scheme_name, entry_postfix, data_ops, fn_sigs, suite_use_stubs,
    ):
        """Build the guarded call for a suite-level ``<init>``/``<final>`` scheme
        hook (v2.0 SDF schema): a single scheme's own init/final phase, called
        once per suite lifecycle -- not part of any group, so it needs its own
        independent argument resolution rather than the whole-suite all_args/
        data_ops pipeline every group-scheme call already goes through.

        Mirrors capgen-v1's own suite-level ``<init>``/``<final>`` handling
        (``suite_resolver.py``'s ``_resolve_one_call``, ``suite_cap.py``'s
        ``_emit_one_call``): resolved like an ordinary scheme call, with
        errmsg/errflg shared with the enclosing subroutine and every other
        argument resolved directly against its own HostVariableMatchPass-
        annotated ``model_var_name``/``model_module_name`` (the same host
        match every other scheme arg already went through -- just consumed
        directly here instead of via the suite-wide ``all_args`` pipeline,
        since this scheme is never part of any group's own call sequence).

        *fn_sigs* is mutated in place with this call's own signature (mirrors
        ``_build_call_ops``'s own ``fn_sigs`` accumulation) so the generated
        module gets a proper external declaration/``use`` stub for it.
        *suite_use_stubs* is mutated in place with a ``use <module>, only:
        <var>`` stub per host-matched arg (mirrors ``_find_loop_upper_bound``'s
        own stub construction) -- duplicates across the init/final calls are
        fine, deduplicated later by ``match_and_rewrite``'s own
        ``seen_stubs``/``deduped_stubs`` pass.

        Returns an empty list if *scheme_name* is falsy (no hook declared).
        """
        if not scheme_name:
            return []

        subroutine_name = scheme_name + entry_postfix
        arg_table = self.getArgumentTable(scheme_name, subroutine_name)
        if arg_table is None:
            phase = entry_postfix.strip("_")
            raise ValueError(
                f"Suite declares <{phase}>{scheme_name}</{phase}> but scheme "
                f"'{scheme_name}' has no '{entry_postfix}' phase in its metadata."
            )

        local_data_ops = {}
        host_ref_ops = []
        for fn_arg in arg_table.getFunctionArguments():
            std_name = fn_arg.getAttr("standard_name") if fn_arg.hasAttr("standard_name") else None
            if std_name == CCPP_ERROR_MESSAGE:
                local_data_ops[fn_arg.name] = data_ops["errmsg"]
            elif std_name == CCPP_ERROR_CODE:
                local_data_ops[fn_arg.name] = data_ops["errflg"]
            elif fn_arg.hasAttr("model_var_name"):
                model_var_name = fn_arg.getAttr("model_var_name")
                model_module_name = fn_arg.getAttr("model_module_name")
                ref_op = ccpp_utils.HostVarRefOp(
                    model_var_name,
                    model_module_name,
                    TypeConversions.getBaseType(fn_arg.getAttr("type")),
                )
                host_ref_ops.append(ref_op)
                local_data_ops[fn_arg.name] = ref_op.res
                stub = llvm.GlobalOp(
                    llvm.LLVMArrayType.from_size_and_type(1, i8),
                    model_var_name, "external",
                )
                stub.attributes["module"] = StringAttr(model_module_name)
                suite_use_stubs.append(stub)
            else:
                raise ValueError(
                    f"Suite-level <{entry_postfix.strip('_')}> scheme "
                    f"'{scheme_name}' has arg '{fn_arg.name}' (standard_name "
                    f"'{std_name}') with no host match -- suite-level init/final "
                    "hooks currently only support plain host-module-matched "
                    "scalar args, not DDT members or cap-owned scratch values."
                )

        call_ops = self.generateSchemeSubroutineCallOps(
            subroutine_name, arg_table, local_data_ops,
        )
        if subroutine_name not in fn_sigs:
            fn_sigs[subroutine_name] = self.meta_fn_sigs[subroutine_name]
        return host_ref_ops + call_ops

    def generateVariableCreation(self, scheme_names, arg_tables):
        """Allocate a memref for every unique argument across all schemes.

        Where the same argument name appears in multiple schemes its type must
        match; only one allocation is created.
        """
        args_required = {}
        # Collect unique args across all schemes, asserting type consistency
        for scheme_name in scheme_names:
            arg_table = arg_tables[scheme_name]
            for fn_arg in arg_table.getFunctionArguments():
                if fn_arg.name in args_required:
                    assert fn_arg.getAttr("type") == args_required[fn_arg.name].getAttr(
                        "type"
                    )
                else:
                    args_required[fn_arg.name] = fn_arg

        alloc_ops = {}
        # Create one AllocaOp per unique argument
        for arg in args_required.values():
            arg_type = arg.getAttr("type")
            data_shape = []
            if arg_type == "character":
                data_shape.append(int(arg.getAttr("kind").split("=")[1]))

            alloc_ops[arg.name] = memref.AllocaOp.get(
                TypeConversions.getBaseType(arg_type), shape=data_shape
            )
        return alloc_ops

    def generateVariableInitialisations(self, data_ops):
        """Emit ops that zero-initialise errflg and clear errmsg at subroutine entry."""
        err_const = arith.ConstantOp.from_int_and_width(0, 32)
        store_op = memref.StoreOp.get(err_const, data_ops["errflg"], [])
        clear_errmsg = ClearStringOp(data_ops["errmsg"])
        return [err_const, store_op, clear_errmsg]

    def generateSchemeSubroutineCallOps(
        self, subroutine_name, arg_table, data_ops, overrides=None,
        exclude_args=frozenset(), divergent_std_keys: frozenset = frozenset(),
    ):
        """Build the IR for a single scheme subroutine call guarded by errflg.

        Constructs the call op, copies out-arg results back to their storage
        locations, then wraps everything in an scf.if that only executes when
        errflg is zero (i.e. no prior error has occurred).

        When the suite cap's local variable type does not match the callee's
        declared parameter type (e.g. the suite holds a 2-D array but the
        scheme expects 1-D), an UnrealizedConversionCastOp is inserted as a
        type annotation so xDSL verification passes.  The Fortran printer looks
        through these casts and emits the underlying variable name.

        Always emits a KeywordCallOp (Fortran keyword/name=value call syntax),
        never a plain positional func.CallOp -- the callee's own .meta
        arg-table declaration order is not guaranteed to match its real .F90
        subroutine's physical dummy-argument order (nothing enforces that
        invariant, and real CCPP schemes have never been required to honor
        it), so calling by name is the only generally-correct option. When
        *overrides* is non-empty, overridden arguments are additionally
        omitted from the SSA operand/result lists and carried as compile-time
        literals in the op instead.

        divergent_std_keys are standard_names where two or more schemes
        sharing the name declare a genuinely different kind or units from
        each other (see _build_arg_tables); for these, the shared value in
        data_ops stays in the host's own native representation always, and
        this specific call independently marshals to its own known kind/unit
        mismatch (already annotated per-scheme by HostVariableMatchPass),
        converting immediately before the call and writing back immediately
        after -- see _apply_divergent_marshaling below.
        """
        if overrides is None:
            overrides = {}

        # Only apply overrides whose names actually appear in this arg table;
        # the same override dict may be shared across entry points (_run, _init,
        # _finalize) and not every entry point has the same arguments.
        arg_names_in_table = {arg.name for arg in arg_table.getFunctionArguments()}
        overrides = {k: v for k, v in overrides.items() if k in arg_names_in_table}

        # Retrieve the callee's declared input types to detect mismatches.
        # Only the inputs side is needed: every argument (in/inout/out alike)
        # is passed by reference through in_ssa/in_names below (see the
        # "Fortran passes ALL arguments by reference" comment further down),
        # so the call always has zero actual SSA results -- there is no
        # callee-output-types side to track.
        callee = self.meta_fn_sigs.get(subroutine_name)
        callee_in_types = list(callee.function_type.inputs) if callee else []

        in_ssa = []
        in_names = []
        cast_ops = []  # casts inserted before the call inside the if-body
        divergent_writeback_ops = []  # write-backs inserted after the call
        in_idx = 0

        def _apply_divergent_marshaling(arg, val):
            """Adapt val (the shared, host-native value) to this specific
            scheme's own known kind/unit mismatch and vertical-layer
            (top_at_one) convention, for a cross-scheme divergent
            standard_name. Appends the forward cast(s) to cast_ops and
            schedules the matching write-back(s) -- applied in reverse
            order, since e.g. a kind cast followed by a unit convert must
            be undone unit-first, kind-second -- into
            divergent_writeback_ops. Returns the value to pass to the call.

            A vertical flip is type/kind-invariant (it only reorders array
            elements along one axis), so it composes with the kind/unit
            steps in either order without changing the final result;
            applied last here purely for a stable, deterministic order.
            """
            if self._std_key(arg) not in divergent_std_keys:
                return val
            intent = arg.getAttr("intent") if arg.hasAttr("intent") else "in"
            chain: list = []  # (kind/unit/flip, result_ssa, source_ssa, param)
            cur = val
            if arg.hasAttr("model_var_kind_mismatch") and arg.getAttr("type") != "character":
                scheme_kind, host_kind = arg.getAttr("model_var_kind_mismatch").split(":")
                scheme_type = TypeConversions.convert(
                    arg.getAttr("type"), scheme_kind, self._arg_dims(arg)
                )
                cast_op = KindCastOp(cur, scheme_kind, scheme_type)
                cast_op.res.name_hint = f"{arg.name}_kind_cast"
                cast_ops.append(cast_op)
                chain.append(("kind", cast_op.res, cur, host_kind))
                cur = cast_op.res
            if arg.hasAttr("model_var_unit_mismatch"):
                scheme_units, host_units = arg.getAttr("model_var_unit_mismatch").split(":", 1)
                to_scheme_expr, to_host_expr = UNIT_CONVERSIONS[(scheme_units, host_units)]
                arg_type = TypeConversions.convert(
                    arg.getAttr("type"),
                    arg.getAttr("kind") if arg.hasAttr("kind") else None,
                    self._arg_dims(arg),
                )
                pre_expr = "" if intent == "out" else to_scheme_expr
                conv_op = UnitConvertOp(cur, pre_expr, arg_type)
                conv_op.res.name_hint = f"{arg.name}_unit_conv"
                cast_ops.append(conv_op)
                chain.append(("unit", conv_op.res, cur, to_host_expr))
                cur = conv_op.res
            if arg.hasAttr("top_at_one"):
                vert_dim = self._vertical_dim_index(arg)
                if vert_dim is not None:
                    flip_op = VerticalFlipOp(cur, vert_dim, cur.type)
                    flip_op.res.name_hint = f"{arg.name}_vert_flip"
                    cast_ops.append(flip_op)
                    chain.append(("flip", flip_op.res, cur, vert_dim))
                    cur = flip_op.res
            if intent in ("inout", "out"):
                for kind_or_unit, result_ssa, source_ssa, param in reversed(chain):
                    if kind_or_unit == "kind":
                        divergent_writeback_ops.append(
                            KindWriteBackOp(result_ssa, source_ssa, param)
                        )
                    elif kind_or_unit == "unit":
                        divergent_writeback_ops.append(
                            UnitWriteBackOp(result_ssa, source_ssa, param)
                        )
                    else:
                        divergent_writeback_ops.append(
                            VerticalFlipWriteBackOp(result_ssa, source_ssa, param)
                        )
            return cur

        # Classify each argument as an input, output, or both (inout).
        # Fortran passes ALL arguments by reference, including intent(out) --
        # treating out args as return values would break positional order
        # when scalars and arrays are interspersed -- so "in"/"inout"/"out"
        # are all marshaled identically here, by reference.
        for arg in arg_table.getFunctionArguments():
            intent = arg.getAttr("intent")
            is_overridden = arg.name in overrides
            is_excluded = arg.name in exclude_args
            if intent in ("in", "inout", "out"):
                if not is_overridden and not is_excluded:
                    # Prefer the standard_name-tagged entry over the bare
                    # arg-name one: two different schemes in this group can
                    # independently pick the same local arg name for two
                    # logically different SuiteOwned variables (see
                    # _build_framework_refs), making the bare-name entry
                    # genuinely ambiguous in that case. Every arg still has a
                    # bare-name entry regardless (block args and non-tagged
                    # framework refs alike), so the fallback always resolves.
                    val = data_ops.get(("std_name", self._std_key(arg)), data_ops[arg.name])
                    val = _apply_divergent_marshaling(arg, val)
                    actual_type = (
                        val.type if isinstance(val, SSAValue) else val.results[0].type
                    )
                    expected_type = (
                        callee_in_types[in_idx]
                        if in_idx < len(callee_in_types)
                        else actual_type
                    )
                    if actual_type != expected_type:
                        cast = builtin.UnrealizedConversionCastOp(
                            operands=[[val]], result_types=[[expected_type]]
                        )
                        cast_ops.append(cast)
                        in_ssa.append(cast.results[0])
                    else:
                        in_ssa.append(val)
                    in_names.append(arg.name)
                in_idx += 1

        # Always call by keyword (name=value), never positionally: this
        # scheme's own .meta arg-table declaration order is just a parallel,
        # independently-authored description of its real .F90 subroutine's
        # dummy-argument order -- CCPP has never required the two to match
        # (real capgen-v1 always calls by keyword for exactly this reason),
        # and nothing here verifies they do. A positional func.CallOp would
        # silently misorder the call the moment a scheme's own .meta happens
        # to declare arguments in a different order than its real Fortran
        # signature -- confirmed to actually happen (examples/chunked_data's
        # chunked_data_scheme.meta declares errmsg/errflg before data_array;
        # its own .F90 declares data_array first), producing a Fortran
        # argument type mismatch at compile time. Keyword calls make the
        # .meta declaration order irrelevant to correctness, matching what
        # real CCPP schemes have always been able to assume.
        # No result_names/out_types: every argument (in/inout/out alike) is
        # already passed by reference above, so this call never has actual
        # SSA results to track or copy back -- see the comment on
        # callee_in_types above.
        call_op = KeywordCallOp(
            subroutine_name,
            ArrayAttr([StringAttr(n) for n in in_names]),
            ArrayAttr([]),
            DictionaryAttr({k: StringAttr(v) for k, v in overrides.items()}),
            in_ssa,
            [],
        )

        # Guard the call: only execute when errflg == 0
        err_const_comp = arith.ConstantOp.from_int_and_width(0, 32)
        load_op = memref.LoadOp.get(data_ops["errflg"], [])
        cmp = arith.CmpiOp(load_op, err_const_comp, 0)
        conditional_op = scf.IfOp(
            cmp, [],
            cast_ops + [call_op] + divergent_writeback_ops + [scf.YieldOp()],
        )

        return [err_const_comp, cmp, load_op, conditional_op]

    def generateStringConstantGlobal(self, string: str) -> llvm.GlobalOp:
        """Create an internal LLVM global holding a 16-byte string constant."""
        return llvm.GlobalOp(
            llvm.LLVMArrayType.from_size_and_type(16, i8),
            "const_" + string,
            "internal",
            constant=True,
            value=StringAttr(string),
        )

    def generateStateCheckOps(
        self, check_string: str, data_ops, fn_name: str | None = None,
        instance_local_name: str | None = None,
    ):
        """Emit ops that compare ccpp_suite_state against check_string.

        If the state does not match the expected value, errflg is set to 1
        and, when fn_name is provided, an error message is written into errmsg.
        The comparison uses ccpp_utils.StrCmpOp (lowered later by the
        lower-ccpp-utils pass) and an XOrI to negate the equality result.

        instance_local_name -- for a multi-instance suite, the local
        Fortran name of this call's own instance_number-standard-name arg
        (see _synthesize_instance_number_arg); tags the ccpp_suite_state
        AddressOfOp with ccpp_instance_ref so print_ftn.py prints
        ccpp_suite_state(<instance_local_name>), not the bare shared name.
        """
        arr_type = llvm.LLVMArrayType.from_size_and_type(16, i8)

        # Load the expected state constant and the current runtime state
        addr_const = llvm.AddressOfOp("const_" + check_string, llvm.LLVMPointerType())
        loaded_const = llvm.LoadOp(addr_const, arr_type)
        addr_state = llvm.AddressOfOp("ccpp_suite_state", llvm.LLVMPointerType())
        if instance_local_name is not None:
            addr_state.attributes["ccpp_instance_ref"] = StringAttr(instance_local_name)
        loaded_state = llvm.LoadOp(addr_state, arr_type)

        strcmp_op = ccpp_utils.StrCmpOp(loaded_const, loaded_state, len(check_string))

        # strcmp returns 1 if equal; negate to get mismatch flag for scf.if
        one_i1 = arith.ConstantOp.from_int_and_width(1, 1)
        mismatch = arith.XOrIOp(strcmp_op.res, one_i1.result)

        # Set errflg = 1 if the state does not match; optionally write errmsg
        one = arith.ConstantOp.from_int_and_width(1, 32)
        store = memref.StoreOp.get(one, data_ops["errflg"], [])
        if fn_name is not None:
            trim_state = ccpp_utils.TrimOp(loaded_state)
            write_err = ccpp_utils.WriteErrMsgOp(
                data_ops["errmsg"],
                trim_state.res,
                "Invalid initial CCPP state, '",
                f"' in {fn_name}",
            )
            true_ops = [trim_state, write_err, one, store, scf.YieldOp()]
        else:
            true_ops = [one, store, scf.YieldOp()]
        if_op = scf.IfOp(mismatch.result, [], true_ops)

        return [
            addr_const,
            loaded_const,
            addr_state,
            loaded_state,
            strcmp_op,
            one_i1,
            mismatch,
            if_op,
        ]

    def generateStateAssignment(
        self, state_string: str, instance_local_name: str | None = None
    ):
        """Emit ops that write state_string into the ccpp_suite_state global.

        instance_local_name -- see generateStateCheckOps's own docstring.
        """
        arr_type = llvm.LLVMArrayType.from_size_and_type(16, i8)
        # Load from the string constant global and store into ccpp_suite_state
        addr_src = llvm.AddressOfOp("const_" + state_string, llvm.LLVMPointerType())
        loaded = llvm.LoadOp(addr_src, arr_type)
        addr_dst = llvm.AddressOfOp("ccpp_suite_state", llvm.LLVMPointerType())
        if instance_local_name is not None:
            addr_dst.attributes["ccpp_instance_ref"] = StringAttr(instance_local_name)
        store = llvm.StoreOp(loaded, addr_dst)
        return [addr_src, loaded, addr_dst, store]

    @staticmethod
    def _has_dims(a) -> bool:
        return a.hasAttr("dimensions") and a.getAttr("dimensions") > 0

    @staticmethod
    def _arg_dims(a) -> int:
        """Return the dimension count to use for the block arg type.

        For promoted args, use scheme_rank + 1 so the suite physics
        subroutine receives the full host 2D array (e.g. temp_layer(:,:))
        rather than the scheme's 1D slice declaration (temp_layer(:)).
        """
        base = a.getAttr("dimensions") if a.hasAttr("dimensions") else 0
        if a.hasAttr("is_promoted"):
            return base + 1
        return base

    @staticmethod
    def _block_arg_kind(a):
        """Return the kind to use for the suite function block arg.

        For kind-mismatched args the host provides the value in its own
        kind, so the block arg is declared in the HOST kind.  The suite
        function body then creates a temp in the SCHEME kind and converts.
        """
        if a.hasAttr("model_var_kind_mismatch"):
            return a.getAttr("model_var_kind_mismatch").split(":")[1]
        return a.getAttr("kind") if a.hasAttr("kind") else None

    def _build_block_signature(
        self, input_arg_list, output_arg_list, divergent_std_keys: frozenset = frozenset(),
    ) -> "_BlockSignature":
        """Build the Block, populate data_ops from block args, and apply kind/unit casts.

        divergent_std_keys are standard_names where two or more schemes sharing
        the name declare a genuinely different kind or units from each other
        (see _build_arg_tables). For these, the suite-boundary conversion below
        is skipped entirely -- the dummy argument stays in the host's own
        native representation for the whole function body, and each
        individual scheme call marshals to its own kind/units independently
        (see generateSchemeSubroutineCallOps). Converting once here, to
        whichever scheme happened to become canonical, would be wrong for
        every other scheme sharing the name.
        """
        input_arg_types = [
            TypeConversions.convert(a.getAttr("type"), self._block_arg_kind(a), self._arg_dims(a))
            for a in input_arg_list
        ]

        new_block = Block(arg_types=input_arg_types)

        def _hint_for(fn_arg, base_name: str) -> str:
            if fn_arg.hasAttr("allocatable"):
                return base_name + "__alloc"
            if fn_arg.hasAttr("optional"):
                return base_name + "__opt"
            if self._has_dims(fn_arg) and fn_arg.getAttr("intent") == "in":
                # Array args that are truly intent(in) get __in so the printer
                # emits intent(in) rather than the default intent(inout).
                # Unit-mismatched args are now converted into a local copy so
                # the host's array is never modified — intent(in) is correct.
                return base_name + "__in"
            return base_name

        def _printed_name(hint: str) -> str:
            # print_ftn.py strips this exact __alloc/__opt/__in suffix before
            # emitting the Fortran identifier (see its input_names comprehension),
            # so collision detection must compare on this stripped form -- e.g. a
            # scalar "x" and an array intent(in) "x" have different hints ("x" vs
            # "x__in") but print as the same duplicate dummy-argument name.
            if hint.endswith("__alloc"):
                return hint[: -len("__alloc")]
            if hint.endswith("__opt"):
                return hint[: -len("__opt")]
            if hint.endswith("__in"):
                return hint[: -len("__in")]
            return hint

        # input_arg_list comes from all_args.values() (a dict keyed by
        # std_key), so every entry here is a genuinely distinct standard_name.
        # Compute each arg's default hint (its own scheme's local name, exactly
        # as before) first, unchanged for the common case. Only when two
        # different standard_names' schemes independently chose the same
        # local name -- a real collision, e.g. examples/var_compat's four
        # schemes all using "scalar_var" for four unrelated standard_names --
        # fall back to the host-matched canonical name (model_var_name) for
        # just those colliding entries, since the host routinely already
        # gives each standard_name a distinct name for this exact reason
        # (var_compat's own host table: scalar_var/scalar_varA/scalar_varB/
        # scalar_varC). Every non-colliding arg keeps its original name,
        # byte-identical to before this existed.
        default_hints = [_hint_for(fn_arg, fn_arg.name) for fn_arg in input_arg_list]
        collision_counts: dict[str, int] = {}
        for h in default_hints:
            printed = _printed_name(h)
            collision_counts[printed] = collision_counts.get(printed, 0) + 1

        data_ops = {}
        printed_seen: dict[str, str] = {}  # printed dummy-arg name -> the fn_arg.name that claimed it
        for idx, fn_arg in enumerate(input_arg_list):
            hint = default_hints[idx]
            printed = _printed_name(hint)
            if collision_counts[printed] > 1:
                if not fn_arg.hasAttr("model_var_name"):
                    raise ValueError(
                        f"Suite dummy-argument name collision on {printed!r}: "
                        f"scheme argument {fn_arg.name!r} shares this local name "
                        f"with another, unrelated standard_name, and has no "
                        f"host-matched canonical name (model_var_name) to "
                        f"disambiguate with. Give the host a distinct local "
                        f"name for this standard_name, or rename one of the "
                        f"colliding schemes' arguments."
                    )
                hint = _hint_for(fn_arg, fn_arg.getAttr("model_var_name"))
                printed = _printed_name(hint)
                if printed in printed_seen:
                    raise ValueError(
                        f"Suite dummy-argument name collision: both "
                        f"{printed_seen[printed]!r} and {fn_arg.name!r} (different "
                        f"standard_names) resolve to the same dummy-argument "
                        f"name {printed!r} even after preferring model_var_name. "
                        f"Give the host a distinct local name for one of these "
                        f"standard_names."
                    )
            printed_seen[printed] = fn_arg.name
            new_block.args[idx].name_hint = hint
            data_ops[fn_arg.name] = new_block.args[idx]

        # Index-keyed (not name-keyed) record of each input arg's current
        # resolved SSA value, updated alongside data_ops[fn_arg.name] below
        # by the kind-cast/unit-cast loops. Needed because data_ops is keyed
        # by fn_arg.name, which -- for the very args this collision handling
        # exists for -- is NOT unique across entries (that's the collision);
        # tracking by position instead means a later entry's write can never
        # clobber an earlier entry's value, unlike the name-keyed dict.
        final_values: list = [new_block.args[idx] for idx in range(len(input_arg_list))]

        kind_cast_ops: list = []
        kind_writeback_pairs: list = []
        for idx, fn_arg in enumerate(input_arg_list):
            if self._std_key(fn_arg) in divergent_std_keys:
                continue
            if not fn_arg.hasAttr("model_var_kind_mismatch"):
                continue
            # Character length mismatches are resolved by declaring the block arg
            # with the host's concrete length — no runtime KindCastOp required.
            if fn_arg.getAttr("type") == "character":
                continue
            scheme_kind, host_kind = fn_arg.getAttr("model_var_kind_mismatch").split(":")
            block_arg_ssa = new_block.args[idx]
            scheme_type = TypeConversions.convert(
                fn_arg.getAttr("type"), scheme_kind, self._arg_dims(fn_arg)
            )
            cast_op = KindCastOp(block_arg_ssa, scheme_kind, scheme_type)
            cast_op.res.name_hint = f"{fn_arg.name}_kind_cast"
            kind_cast_ops.append(cast_op)
            data_ops[fn_arg.name] = cast_op.res
            final_values[idx] = cast_op.res

            intent = fn_arg.getAttr("intent") if fn_arg.hasAttr("intent") else "in"
            if intent in ("inout", "out"):
                kind_writeback_pairs.append((cast_op.res, block_arg_ssa, host_kind))

        unit_convert_ops: list = []
        unit_writeback_pairs: list = []
        for idx, fn_arg in enumerate(input_arg_list):
            if self._std_key(fn_arg) in divergent_std_keys:
                continue
            if not fn_arg.hasAttr("model_var_unit_mismatch"):
                continue
            scheme_units, host_units = fn_arg.getAttr("model_var_unit_mismatch").split(":", 1)
            to_scheme_expr, to_host_expr = UNIT_CONVERSIONS[(scheme_units, host_units)]

            block_arg_ssa = new_block.args[idx]
            arg_type = TypeConversions.convert(
                fn_arg.getAttr("type"),
                fn_arg.getAttr("kind") if fn_arg.hasAttr("kind") else None,
                self._arg_dims(fn_arg),
            )

            intent = fn_arg.getAttr("intent") if fn_arg.hasAttr("intent") else "in"
            pre_expr = "" if intent == "out" else to_scheme_expr

            conv_op = UnitConvertOp(block_arg_ssa, pre_expr, arg_type)
            conv_op.res.name_hint = f"{fn_arg.name}_unit_conv"
            unit_convert_ops.append(conv_op)
            data_ops[fn_arg.name] = conv_op.res
            final_values[idx] = conv_op.res

            if intent in ("inout", "out"):
                unit_writeback_pairs.append((conv_op.res, block_arg_ssa, to_host_expr))

        alloc_ops = {}
        # Track by standard_name, not by fn_arg.name -- a scheme is free to
        # name its error-handling args anything (e.g. "errcode" instead of
        # "errflg", as examples/constituents_dim's schemes do); only the
        # standard_name (ccpp_error_code/ccpp_error_message) is authoritative
        # for "is this already covered." Checking the literal string
        # "errflg"/"errmsg" against data_ops below would otherwise miss a
        # same-meaning-different-name entry already in output_arg_list and
        # add a second, spurious allocation for the same error value --
        # producing an extra, unintended return value in this function's
        # signature (return_types is built from alloc_ops right below).
        has_errflg_std = False
        has_errmsg_std = False
        for fn_arg in output_arg_list:
            arg_type = fn_arg.getAttr("type")
            kind = fn_arg.getAttr("kind") if fn_arg.hasAttr("kind") else None
            full_type = TypeConversions.convert(arg_type, kind, 0)
            alloc_op = memref.AllocaOp.get(
                full_type.element_type, shape=list(full_type.shape.data)
            )
            alloc_op.memref.name_hint = fn_arg.name
            alloc_ops[fn_arg.name] = alloc_op
            data_ops[fn_arg.name] = alloc_op
            std_name = (
                fn_arg.getAttr("standard_name").lower()
                if fn_arg.hasAttr("standard_name") else None
            )
            if std_name == CCPP_ERROR_CODE:
                has_errflg_std = True
                data_ops["errflg"] = alloc_op  # canonical internal alias
            elif std_name == CCPP_ERROR_MESSAGE:
                has_errmsg_std = True
                data_ops["errmsg"] = alloc_op  # canonical internal alias

        if not has_errflg_std:
            alloc_op = memref.AllocaOp.get(
                TypeConversions.getBaseType("integer"), shape=[]
            )
            alloc_op.memref.name_hint = "errflg"
            alloc_ops["errflg"] = alloc_op
            data_ops["errflg"] = alloc_op
        if not has_errmsg_std:
            alloc_op = memref.AllocaOp.get(
                TypeConversions.getBaseType("character"), shape=[CCPP_ERRMSG_LEN]
            )
            alloc_op.memref.name_hint = "errmsg"
            alloc_ops["errmsg"] = alloc_op
            data_ops["errmsg"] = alloc_op

        # Also register every input arg under the ("std_name", ...) tagged key
        # that generateSchemeSubroutineCallOps already prefers when resolving
        # a scheme's own call arguments (see its "val = data_ops.get(
        # ('std_name', ...), data_ops[arg.name])" lookups). Sourced from
        # final_values (index-keyed) rather than data_ops[fn_arg.name]
        # (name-keyed): for exactly the args this collision handling exists
        # for, fn_arg.name is NOT unique across entries (that's the
        # collision), so data_ops[fn_arg.name] itself only ever holds
        # whichever entry was processed last -- reading from it here would
        # silently tag every colliding std_name with that same last value.
        # Purely additive for the common, non-colliding case (same value
        # data_ops[arg.name] already holds) -- but without it, two different
        # standard_names whose schemes independently chose the same local
        # arg name would ALSO collide on the bare-name key, so every scheme
        # sharing that bare name would be called with the same wrong value
        # regardless of which standard_name it actually declared -- not just
        # a naming cosmetic, a real wrong-value bug.
        for idx, fn_arg in enumerate(input_arg_list):
            data_ops[("std_name", self._std_key(fn_arg))] = final_values[idx]

        return _BlockSignature(
            new_block=new_block,
            input_arg_types=input_arg_types,
            data_ops=data_ops,
            alloc_ops=alloc_ops,
            kind_cast_ops=kind_cast_ops,
            kind_writeback_pairs=kind_writeback_pairs,
            unit_convert_ops=unit_convert_ops,
            unit_writeback_pairs=unit_writeback_pairs,
        )

    def _classify_args(self, all_args, physics_mode) -> "_ArgClassification":
        """Partition all_args into framework-managed, input, and output lists.

        When physics_mode is True and the loop-extent arg is present, replaces
        that arg in input_arg_list with synthetic col_start/col_end scalars.
        Returns the final lists and the ncol_meta arg (or None).
        """
        # Reads the durable ownership classification (generate-arg-ownership)
        # rather than re-deriving SuiteOwned-ness here. Missing ownership_kind
        # means the pipeline forgot generate-arg-ownership -- raise rather
        # than silently treating every arg as not-SuiteOwned, which would
        # produce a wrong-but-plausible suite signature instead of an
        # obvious failure.
        missing = [a.name for a in all_args.values() if not a.hasAttr("ownership_kind")]
        if missing:
            raise ValueError(
                f"Arg(s) {sorted(missing)} have no ownership_kind set. "
                f"generate-arg-ownership (ArgOwnershipPass) must run before "
                f"generate-suite-cap -- check the pass pipeline."
            )
        # Keyed by standard_name (matching all_args's own keying), not by
        # bare arg name -- two different schemes in the same group can
        # independently pick the same local arg name for two logically
        # different SuiteOwned variables (e.g. both naming a scalar "tcld"),
        # and keying by bare name here would silently collide the two
        # entries into one, dropping the other from framework_vars/
        # _build_framework_refs entirely.
        framework_vars = {
            self._std_key(a): a
            for a in all_args.values()
            if a.getAttr("ownership_kind") == ArgOwnershipKind.SuiteOwned
        }
        input_arg_list = [
            a
            for a in all_args.values()
            if (a.getAttr("intent") in ("in", "inout") or self._has_dims(a))
            and self._std_key(a) not in framework_vars
        ]
        output_arg_list = [
            a
            for a in all_args.values()
            if a.getAttr("intent") == "out" and not self._has_dims(a)
            and self._std_key(a) not in framework_vars
        ]

        ncol_meta = None
        ncol_meta_entry = all_args.get(CCPP_LOOP_EXTENT_STD_NAME)
        if physics_mode and ncol_meta_entry is not None:
            ncol_meta = ncol_meta_entry
            ncol_idx = next(
                i for i, a in enumerate(input_arg_list)
                if a is ncol_meta
            )

            def _make_col_arg(name):
                a = CCPPArgument(name)
                a.setAttr("type", ncol_meta.getAttr("type"))
                a.setAttr("intent", "in")
                if ncol_meta.hasAttr("kind"):
                    a.setAttr("kind", ncol_meta.getAttr("kind"))
                a.setAttr("dimensions", 0)
                return a

            input_arg_list = (
                input_arg_list[:ncol_idx]
                + [_make_col_arg("col_start"), _make_col_arg("col_end")]
                + input_arg_list[ncol_idx + 1:]
            )

        return _ArgClassification(
            framework_vars=framework_vars,
            input_arg_list=input_arg_list,
            output_arg_list=output_arg_list,
            ncol_meta=ncol_meta,
        )

    def _build_arg_tables(
        self, suite_description, tgt_subroutine_postfix, physics_mode: bool = False,
    ) -> "_ArgTableResult":
        """Build argument tables, overrides, and canonical arg map for all schemes."""
        scheme_entries = self.getSchemeNames(suite_description)
        arg_tables = {}
        scheme_overrides: dict[str, dict[str, str]] = {}
        actual_postfixes: dict[str, str] = {}
        all_args = {}
        suite_use_stubs: list = []
        if tgt_subroutine_postfix is not None:
            _postfix_candidates = [tgt_subroutine_postfix]
            if tgt_subroutine_postfix in LIFECYCLE_POSTFIX_ALIASES:
                _postfix_candidates.append(LIFECYCLE_POSTFIX_ALIASES[tgt_subroutine_postfix])
            for scheme_name, overrides in scheme_entries:
                for _candidate in _postfix_candidates:
                    table = self.getArgumentTable(
                        scheme_name, scheme_name + _candidate
                    )
                    if table is not None and scheme_name not in arg_tables:
                        arg_tables[scheme_name] = table
                        scheme_overrides[scheme_name] = overrides
                        actual_postfixes[scheme_name] = _candidate
                        break

            for scheme_name in arg_tables:
                for fn_arg in arg_tables[scheme_name].getFunctionArguments():
                    std_key = self._std_key(fn_arg)
                    if std_key in all_args:
                        assert fn_arg.getAttr("type") == all_args[std_key].getAttr("type")
                    else:
                        all_args[std_key] = fn_arg

            if physics_mode:
                self._synthesize_dynamic_loop_count_args(suite_description, arg_tables, all_args)
            self._synthesize_instance_number_arg(all_args)
            self._synthesize_number_of_instances_arg(all_args)

        # Two or more schemes sharing a standard_name can each independently
        # declare a genuinely different kind, units, or vertical-layer
        # convention (top_at_one) for it -- not just different from the
        # host, but different from each other (e.g. examples/var_compat:
        # effr_pre/effr_post declare the rain-particle radius in meters,
        # effr_calc/effr_diag declare the same standard_name in
        # micrometers with top_at_one = True). all_args above only ever
        # keeps ONE scheme's declaration per standard_name (whichever came
        # first), so a suite-boundary conversion decision based on that
        # single entry is wrong for every other scheme sharing the name.
        # Flag these standard_names so the block signature and
        # call-building code can switch to per-call marshaling for just
        # these entries, leaving every other, agreeing standard_name
        # completely unaffected.
        signatures_seen: dict[str, set] = {}
        for scheme_name in arg_tables:
            for fn_arg in arg_tables[scheme_name].getFunctionArguments():
                if fn_arg.getAttr("type") != "real":
                    continue
                std_key = self._std_key(fn_arg)
                kind = fn_arg.getAttr("kind") if fn_arg.hasAttr("kind") else None
                units = normalize_units(
                    fn_arg.getAttr("units") if fn_arg.hasAttr("units") else None
                )
                top_at_one = fn_arg.hasAttr("top_at_one")
                signatures_seen.setdefault(std_key, set()).add((kind, units, top_at_one))
        divergent_std_keys = frozenset(
            std_key for std_key, sigs in signatures_seen.items() if len(sigs) > 1
        )

        return _ArgTableResult(
            scheme_entries=scheme_entries,
            arg_tables=arg_tables,
            scheme_overrides=scheme_overrides,
            actual_postfixes=actual_postfixes,
            all_args=all_args,
            suite_use_stubs=suite_use_stubs,
            divergent_std_keys=divergent_std_keys,
        )

    def _assemble_func(
        self,
        suite_description,
        generated_subroutine_posfix,
        check_string,
        state_string,
        input_arg_list,
        input_arg_types,
        new_block,
        data_ops,
        alloc_ops,
        kind_cast_ops,
        kind_writeback_pairs,
        unit_convert_ops,
        unit_writeback_pairs,
        call_ops,
        initialisation_ops,
        ncol_compute_ops,
        framework_ref_ops,
        lazy_alloc_ops,
        suite_lifecycle_call_ops=(),
        instance_local_name: str | None = None,
    ):
        """Assemble all op lists into the body block and return the FuncOp.

        suite_lifecycle_call_ops -- the suite-level <init>/<final> scheme
        hook's own guarded call (see _build_suite_lifecycle_call_ops),
        empty unless this suite declares one AND this is its "_init"/
        "_finalize" subroutine. Placed after the ordinary call_ops (mirrors
        capgen-v1's own placement: after group-scheme init/finalize calls)
        and before state_ops (before the suite-state transition).

        instance_local_name -- see generateStateCheckOps's own docstring;
        forwarded to both the check and the assignment so a multi-instance
        suite's ccpp_suite_state access is indexed by this call's own
        instance.
        """
        # Use the ORIGINAL block arg (by position), not data_ops[a.name] --
        # for a scalar arg with a kind or unit mismatch, data_ops[a.name] has
        # been reassigned to the suite-boundary conversion temp (see
        # _build_block_signature's kind_cast_ops/unit_convert_ops loops), not
        # the original block arg. The write-back ops already restore the
        # original block arg's own value correctly; ReturnOp's job here is
        # only to mark, by identity, which block args the printer should
        # declare intent(inout) (it scans this list for exactly that -- see
        # print_ftn.py). Returning the conversion temp instead would make the
        # printer declare the arg intent(in), which is invalid Fortran the
        # moment the write-back later assigns into it.
        inout_return_vals = [
            new_block.args[idx]
            for idx, a in enumerate(input_arg_list)
            if a.getAttr("intent") == "inout" and not self._has_dims(a)
        ]
        alloc_return_vals = list(alloc_ops.values())

        errmsg_fn_name = suite_description.attributes["name"] + generated_subroutine_posfix
        check_ops = (
            self.generateStateCheckOps(
                check_string, data_ops, errmsg_fn_name, instance_local_name
            )
            if check_string is not None
            else []
        )
        state_ops = (
            self.generateStateAssignment(state_string, instance_local_name)
            if state_string is not None
            else []
        )

        kind_writeback_ops = [
            KindWriteBackOp(conv_res, orig_dest, orig_kind)
            for conv_res, orig_dest, orig_kind in kind_writeback_pairs
        ]
        unit_writeback_ops = [
            UnitWriteBackOp(conv_res, orig_dest, to_host)
            for conv_res, orig_dest, to_host in unit_writeback_pairs
        ]

        body_ops = (
            alloc_return_vals
            + initialisation_ops
            + ncol_compute_ops
            + framework_ref_ops
            + lazy_alloc_ops
            + kind_cast_ops
            + unit_convert_ops
            + check_ops
            + call_ops
            + kind_writeback_ops
            + unit_writeback_ops
            + list(suite_lifecycle_call_ops)
            + state_ops
            + [func.ReturnOp(*inout_return_vals, *alloc_return_vals)]
        )

        new_block.add_ops(body_ops)
        body = Region()
        body.add_block(new_block)

        return_types = [v.type for v in inout_return_vals] + [
            o.results[0].type for o in alloc_return_vals
        ]
        new_fn_type = builtin.FunctionType.from_lists(input_arg_types, return_types)
        return func.FuncOp(
            suite_description.attributes["name"] + "_suite" + generated_subroutine_posfix,
            new_fn_type,
            body,
            visibility="public",
        )

    def _build_call_ops(
        self,
        suite_description,
        tgt_subroutine_postfix,
        physics_mode,
        all_args,
        data_ops,
        framework_ref_ops,
        suite_use_stubs,
        actual_postfixes,
        arg_tables,
        scheme_overrides,
        divergent_std_keys: frozenset = frozenset(),
    ):
        """Build scheme call ops and collect fn_sigs for all items in the call sequence."""
        call_ops = []
        fn_sigs = {}
        if tgt_subroutine_postfix is None:
            return call_ops, fn_sigs

        call_sequence = self.getCallSequence(suite_description)

        def _flush_promoted(cur_pdim, cur_pgroup):
            if not cur_pgroup:
                return []
            upper_bound_ref = (
                self._find_loop_upper_bound(
                    cur_pdim, all_args, data_ops,
                    framework_ref_ops=framework_ref_ops,
                    suite_use_stubs=suite_use_stubs,
                )
                if cur_pdim
                else None
            )
            if upper_bound_ref is None:
                ops = []
                for sn, tbl in cur_pgroup:
                    full_name = sn + actual_postfixes.get(sn, tgt_subroutine_postfix)
                    ops += self.generateSchemeSubroutineCallOps(
                        full_name, tbl, data_ops, scheme_overrides.get(sn, {}),
                        divergent_std_keys=divergent_std_keys,
                    )
                    if full_name not in fn_sigs:
                        fn_sigs[full_name] = self.meta_fn_sigs[full_name]
                return ops
            lv_alloc = memref.AllocaOp.get(
                TypeConversions.getBaseType("integer"), shape=[]
            )
            lv_alloc.memref.name_hint = "vertical_layer_index"
            ncol_ref = self._find_loop_upper_bound(
                CCPP_HORIZ_DIM_STD_NAME, all_args, data_ops,
                framework_ref_ops=framework_ref_ops,
                suite_use_stubs=suite_use_stubs,
            )
            body_list: list = []
            for sn, tbl in cur_pgroup:
                full_name = sn + actual_postfixes.get(sn, tgt_subroutine_postfix)
                body_list += self._build_promoted_call_ops(
                    full_name, tbl, data_ops, lv_alloc.memref,
                    scheme_overrides.get(sn, {}),
                    ncol_ref=ncol_ref,
                )
                if full_name not in fn_sigs:
                    fn_sigs[full_name] = self.meta_fn_sigs[full_name]
            return [lv_alloc, PromotionLoopOp(
                loop_var=lv_alloc.memref,
                upper_bound=upper_bound_ref,
                body_ops=body_list,
            )]

        def _emit_ordered_list(scheme_list):
            """Emit call ops for (scheme_name, tbl) pairs in order.

            Consecutive promoted schemes sharing the same promoted_dim are
            grouped into a single PromotionLoopOp.
            """
            result: list = []
            cur_pdim: str | None = None
            cur_pgroup: list = []
            for sn, tbl in scheme_list:
                full_name = sn + actual_postfixes.get(sn, tgt_subroutine_postfix)
                assert full_name in self.meta_fn_sigs
                if full_name not in fn_sigs:
                    fn_sigs[full_name] = self.meta_fn_sigs[full_name]
                if physics_mode and self._scheme_has_promoted_args(tbl):
                    pdim = next(
                        (
                            arg.getAttr("promoted_dim").lower()
                            for arg in tbl.getFunctionArguments()
                            if arg.hasAttr("is_promoted")
                            and arg.hasAttr("promoted_dim")
                        ),
                        None,
                    )
                    if pdim == cur_pdim:
                        cur_pgroup.append((sn, tbl))
                    else:
                        result += _flush_promoted(cur_pdim, cur_pgroup)
                        cur_pgroup = [(sn, tbl)]
                        cur_pdim = pdim
                else:
                    result += _flush_promoted(cur_pdim, cur_pgroup)
                    cur_pgroup = []
                    cur_pdim = None
                    result += self._build_active_gated_call_ops(
                        full_name, tbl, data_ops, scheme_overrides.get(sn, {}),
                        divergent_std_keys=divergent_std_keys,
                        suite_use_stubs=suite_use_stubs,
                    )
            result += _flush_promoted(cur_pdim, cur_pgroup)
            return result

        def _emit_subcycle_items(items):
            """Build call ops for one subcycle's own children.

            Consecutive flat scheme siblings are grouped into a single
            _emit_ordered_list call each (preserving the original
            whole-subcycle-body promotion-loop coalescing for the common,
            non-nested case), and a nested subcycle item recurses via
            _emit_subcycle -- so grouping never crosses a nested-subcycle
            boundary, and a nested subcycle's own body is built the same way
            as this one's, to arbitrary depth.
            """
            result: list = []
            pending: list = []
            for sub_item in items:
                if sub_item[0] == "scheme":
                    _, sn, _ = sub_item
                    if sn in arg_tables:
                        pending.append((sn, arg_tables[sn]))
                else:
                    if pending:
                        result += _emit_ordered_list(pending)
                        pending = []
                    _, nested_loop_count, nested_is_literal, nested_items = sub_item
                    result += _emit_subcycle(nested_loop_count, nested_is_literal, nested_items)
            if pending:
                result += _emit_ordered_list(pending)
            return result

        # Every subcycle's own loop-count alloca is hoisted here rather than
        # embedded next to its SubcycleLoopOp -- print_ftn.py's declaration
        # collection (_print_fn's local_allocas) only scans the function's
        # top-level block, not recursively into nested bodies, so a nested
        # subcycle's own alloca would otherwise sit inside its parent
        # SubcycleLoopOp's body region and never get declared at all (an
        # AllocaOp is a pure declaration with no Fortran statement of its own
        # -- see print_ftn.py's case memref.AllocaOp(): pass -- so where it
        # physically sits in the IR doesn't affect the generated code, only
        # whether print_ftn.py's declaration scan can find it). This mirrors
        # exactly where a single (non-nested) subcycle's alloca already lived
        # before nesting was supported: as a top-level sibling of its
        # SubcycleLoopOp, never inside another loop's body.
        hoisted_allocas: list = []

        def _emit_subcycle(loop_count, is_literal, items):
            body_ops = _emit_subcycle_items(items)
            _lc_int = (int(loop_count) if is_literal
                       else CCPP_SUBCYCLE_UNKNOWN_LOOP_COUNT)
            if _lc_int > 1 and physics_mode and body_ops:
                sc_alloc = memref.AllocaOp.get(
                    TypeConversions.getBaseType("integer"), shape=[]
                )
                sc_alloc.memref.name_hint = "ccpp_loop_cnt"
                hoisted_allocas.append(sc_alloc)
                # A non-literal loop_count is a CCPP standard_name, not a
                # Fortran identifier -- resolve it to the matching arg's own
                # dummy-argument name (all_args, keyed by std_key) before
                # printing, whether that arg arrived through the ordinary
                # scheme-arg host-matching path or through
                # _synthesize_dynamic_loop_count_args (for a standard_name no
                # scheme declares its own arg for, e.g. examples/var_compat's
                # num_subcycles_for_effr). Printing the raw standard_name
                # directly is not valid Fortran and would not compile.
                printed_loop_count = loop_count
                if not is_literal:
                    resolved = all_args.get(loop_count.lower())
                    if resolved is None:
                        raise ValueError(
                            f"Subcycle loop count {loop_count!r} is not a "
                            f"literal integer and has no matching "
                            f"host-declared variable anywhere -- give the "
                            f"host a variable with this standard_name, or "
                            f"make the subcycle's loop count a literal "
                            f"integer."
                        )
                    printed_loop_count = resolved.name
                return [SubcycleLoopOp(
                    loop_count=printed_loop_count,
                    loop_var=sc_alloc.memref,
                    body_ops=body_ops,
                    is_literal=is_literal,
                )]
            return body_ops

        for item in call_sequence:
            if item[0] == "scheme":
                _, scheme_name, _ = item
                if scheme_name not in arg_tables:
                    continue
                call_ops += _emit_ordered_list(
                    [(scheme_name, arg_tables[scheme_name])]
                )
            elif item[0] == "subcycle":
                _, loop_count, is_literal, subcycle_items = item
                call_ops += _emit_subcycle(loop_count, is_literal, subcycle_items)

        return hoisted_allocas + call_ops, fn_sigs

    def _build_framework_refs(
        self,
        framework_vars,
        all_args,
        data_ops,
        suite_use_stubs,
        suite_model,
        tgt_subroutine_postfix,
        physics_mode,
        arg_tables,
        already_scheduled_allocs=None,
    ):
        """Build HostVarRefOps and LazyAllocOps for framework-managed vars.

        already_scheduled_allocs -- optional set, shared across every phase
        call for one suite (see _generate_lifecycle_fns), of std_keys that
        have already been given a *successful* LazyAllocOp (dim_var_refs
        resolved) by an earlier _init/_register phase call -- covers both
        the framework_vars loop below and the suite_model.suite_owned_vars()
        sweep further down, since either can be the one that actually
        allocates a given var (e.g. examples/capgen's to_promote/
        promote_pcnst/temp_calc are only ever reached via the suite_model
        sweep, never via framework_vars, since no _init/_register table of
        their own producing scheme declares them).

        Lets a var whose allocation dimension can ONLY be resolved once
        physics_mode's own _run-phase args are in scope -- e.g.
        examples/constituents_dim's cwork/awork, dimensioned by
        number_of_ccpp_constituents, which is never host/module-declared
        (that's the whole point of that example) and so can never resolve
        via _find_loop_upper_bound during _init/_register at all, only
        during _run where n_const is one of the phase's own scheme args --
        still get allocated, without _run also emitting a second, redundant
        LazyAllocOp for a var _init/_register already successfully covered.

        Mutates data_ops, suite_use_stubs, and already_scheduled_allocs as
        side effects. Returns (framework_ref_ops, lazy_alloc_ops).
        """
        framework_ref_ops = []
        lazy_alloc_ops = []
        if framework_vars:
            for fw_arg in framework_vars.values():
                _fw_std_key = self._std_key(fw_arg)
                _scheme_dims = fw_arg.getAttr("dimensions") if fw_arg.hasAttr("dimensions") else 0

                if suite_model is not None:
                    _entry = suite_model.get(_fw_std_key)
                    _rank = _entry.rank if _entry is not None else _scheme_dims
                else:
                    _rank = _scheme_dims

                var_type = TypeConversions.convert(
                    fw_arg.getAttr("type"),
                    fw_arg.getAttr("kind") if fw_arg.hasAttr("kind") else None,
                    _rank,
                )
                _suite_entry = suite_model.get(_fw_std_key) if suite_model else None
                _var_name = (
                    _suite_entry.local_name
                    if _suite_entry is not None
                    else fw_arg.name
                )
                ref_op = ccpp_utils.HostVarRefOp(_var_name, "", var_type)
                ref_op.res.name_hint = _var_name
                framework_ref_ops.append(ref_op)
                data_ops[fw_arg.name] = ref_op
                if _var_name != fw_arg.name:
                    data_ops[_var_name] = ref_op

                _horiz_std_names = {
                    CCPP_HORIZ_DIM_STD_NAME, CCPP_LOOP_EXTENT_STD_NAME,
                    CCPP_LOOP_BEGIN_STD_NAME, CCPP_LOOP_END_STD_NAME,
                }
                _has_horiz_first_dim = False
                if suite_model is not None:
                    _sentry = suite_model.get(_fw_std_key)
                    if _sentry is not None and _sentry.alloc_dim_std_names:
                        _has_horiz_first_dim = (
                            _sentry.alloc_dim_std_names[0].lower() in _horiz_std_names
                        )
                _dims = _rank
                if physics_mode and _dims == 1 and _has_horiz_first_dim:
                    _col_begin_ssa = next(
                        (data_ops[a.name] for a in all_args.values()
                         if a.hasAttr("standard_name")
                         and a.getAttr("standard_name").lower() == CCPP_LOOP_BEGIN_STD_NAME
                         and a.name in data_ops),
                        data_ops.get("col_start"),
                    )
                    _col_end_ssa = next(
                        (data_ops[a.name] for a in all_args.values()
                         if a.hasAttr("standard_name")
                         and a.getAttr("standard_name").lower() == CCPP_LOOP_END_STD_NAME
                         and a.name in data_ops),
                        data_ops.get("col_end"),
                    )
                    if _col_begin_ssa is not None and _col_end_ssa is not None:
                        section = ArraySectionOp(
                            ref_op.res,
                            [_col_begin_ssa],
                            [_col_end_ssa],
                        )
                        framework_ref_ops.append(section)
                        data_ops[fw_arg.name] = section

                _already_scheduled = (
                    already_scheduled_allocs is not None
                    and _fw_std_key in already_scheduled_allocs
                )
                _is_alloc_phase = (
                    tgt_subroutine_postfix in ("_init", "_register")
                    or (physics_mode and not _already_scheduled)
                )
                if _is_alloc_phase:
                    _alloc_dim_names = (
                        suite_model.alloc_dims(_fw_std_key)
                        if suite_model is not None
                        else (fw_arg.getAttr("dim_names")
                              if fw_arg.hasAttr("dim_names") else [])
                    )
                    dim_var_refs = []
                    for dim_std_name in _alloc_dim_names:
                        alloc_dim = (
                            CCPP_HORIZ_DIM_STD_NAME
                            if dim_std_name.lower() == CCPP_LOOP_EXTENT_STD_NAME
                            else dim_std_name
                        )
                        matching = next(
                            (a for a in all_args.values()
                             if a.hasAttr("standard_name")
                             and dims_compatible(a.getAttr("standard_name"), alloc_dim)),
                            None,
                        )
                        if matching and matching.name in data_ops:
                            dim_var_refs.append(data_ops[matching.name])
                        else:
                            ssa = self._find_loop_upper_bound(
                                alloc_dim, all_args, data_ops,
                                framework_ref_ops=framework_ref_ops,
                                suite_use_stubs=suite_use_stubs,
                            )
                            if ssa is not None:
                                dim_var_refs.append(ssa)

                    if dim_var_refs:
                        kind = fw_arg.getAttr("kind") if fw_arg.hasAttr("kind") else CCPP_KIND_PHYS
                        init_val = (
                            fw_arg.getAttr("default_value")
                            if fw_arg.hasAttr("default_value")
                            else None
                        )
                        lazy_alloc_ops.append(
                            LazyAllocOp(
                                var_name=_var_name,
                                kind_name=kind,
                                dim_var_refs=dim_var_refs,
                                init_value=init_val,
                                needs_device_residency=(
                                    _suite_entry.needs_device_residency
                                    if _suite_entry is not None
                                    else False
                                ),
                            )
                        )
                        if already_scheduled_allocs is not None:
                            already_scheduled_allocs.add(_fw_std_key)

                # Tagged (never a plain string, so it can't collide with any
                # bare-name key already in data_ops) entry keyed by this arg's
                # own standard_name, set at the *end* of this arg's processing
                # so it mirrors whatever data_ops[fw_arg.name] ends up being
                # (e.g. the ArraySectionOp-sliced value above, not the plain
                # ref_op it started as). generateSchemeSubroutineCallOps
                # prefers this when building THIS scheme's own call, since two
                # different schemes in the same group can independently pick
                # the same local arg name (e.g. both naming a scalar "tcld")
                # for two logically different SuiteOwned variables -- the
                # bare-name entry is genuinely ambiguous in that case, sharing
                # whichever scheme's ref_op was built last, but each scheme's
                # own standard_name is never ambiguous.
                data_ops[("std_name", _fw_std_key)] = data_ops[fw_arg.name]

        if suite_model is not None and tgt_subroutine_postfix in ("_init", "_register"):
            already_allocated = {op.var_name.data for op in lazy_alloc_ops}
            for entry in suite_model.suite_owned_vars():
                if not suite_model.needs_allocation(entry.standard_name):
                    continue
                if entry.local_name in already_allocated:
                    continue
                dim_var_refs = []
                for dim_std_name in entry.alloc_dim_std_names:
                    alloc_dim = (
                        CCPP_HORIZ_DIM_STD_NAME
                        if dim_std_name.lower() == CCPP_LOOP_EXTENT_STD_NAME
                        else dim_std_name
                    )
                    matching = next(
                        (a for a in all_args.values()
                         if a.hasAttr("standard_name")
                         and a.getAttr("standard_name").lower() == alloc_dim.lower()),
                        None,
                    )
                    if matching and matching.name in data_ops:
                        dim_var_refs.append(data_ops[matching.name])
                    else:
                        ssa = self._find_loop_upper_bound(
                            alloc_dim, all_args, data_ops,
                            framework_ref_ops=framework_ref_ops,
                            suite_use_stubs=suite_use_stubs,
                        )
                        if ssa is not None:
                            dim_var_refs.append(ssa)
                if dim_var_refs:
                    kind = entry.kind if entry.kind else CCPP_KIND_PHYS
                    lazy_alloc_ops.append(
                        LazyAllocOp(
                            var_name=entry.local_name,
                            kind_name=kind,
                            dim_var_refs=dim_var_refs,
                            init_value=None,
                            needs_device_residency=entry.needs_device_residency,
                        )
                    )
                    if already_scheduled_allocs is not None:
                        already_scheduled_allocs.add(entry.standard_name)

        if tgt_subroutine_postfix is not None:
            for _scheme_name in arg_tables:
                for _fn_arg in arg_tables[_scheme_name].getFunctionArguments():
                    _sk = self._std_key(_fn_arg)
                    _canonical = all_args.get(_sk)
                    if _canonical is not None and _fn_arg.name != _canonical.name:
                        if _fn_arg.name not in data_ops and _canonical.name in data_ops:
                            data_ops[_fn_arg.name] = data_ops[_canonical.name]

        return framework_ref_ops, lazy_alloc_ops

    @staticmethod
    def _build_ncol_compute_ops(physics_mode, data_ops, ncol_meta) -> list:
        """Compute ncol = col_end - col_start + 1 and lbound_one; mutates data_ops."""
        if not (physics_mode and "col_start" in data_ops and "col_end" in data_ops):
            return []
        ncol_alloc = memref.AllocaOp.get(
            TypeConversions.getBaseType("integer"), shape=[]
        )
        ncol_alloc.memref.name_hint = "ncol"
        load_col_start = memref.LoadOp.get(data_ops["col_start"], [])
        load_col_end = memref.LoadOp.get(data_ops["col_end"], [])
        sub_op = arith.SubiOp(load_col_end, load_col_start)
        one_const = arith.ConstantOp.from_int_and_width(1, 32)
        add_op = arith.AddiOp(sub_op, one_const)
        store_ncol = memref.StoreOp.get(add_op, ncol_alloc, [])
        data_ops["ncol"] = ncol_alloc
        if ncol_meta.name != "ncol":
            data_ops[ncol_meta.name] = ncol_alloc
        _ib = TypeConversions.getBaseType("integer")
        lbound_one_alloc = memref.AllocaOp.get(_ib, shape=[])
        lbound_one_alloc.memref.name_hint = "ccpp_lbound_one"
        lbound_one_const = arith.ConstantOp.from_int_and_width(1, 32)
        lbound_one_store = memref.StoreOp.get(lbound_one_const, lbound_one_alloc, [])
        data_ops["ccpp_lbound_one"] = lbound_one_alloc
        return [
            ncol_alloc,
            load_col_start,
            load_col_end,
            sub_op,
            one_const,
            add_op,
            store_ncol,
            lbound_one_alloc,
            lbound_one_const,
            lbound_one_store,
        ]

    def generateSubroutineCall(
        self,
        suite_description,
        tgt_subroutine_postfix,
        generated_subroutine_posfix=None,
        state_string: str | None = None,
        check_string: str | None = None,
        physics_mode: bool = False,
        group_name: str = "",
        suite_model=None,
        already_scheduled_allocs=None,
    ):
        """Build a single cap subroutine as a func.FuncOp.

        tgt_subroutine_postfix  -- suffix appended to each scheme name to form
                                   the called function (e.g. "_init"). None
                                   means no scheme calls are emitted.
        generated_subroutine_posfix -- suffix used for the generated function
                                   name (e.g. "_initialize"). Defaults to
                                   tgt_subroutine_postfix when not supplied.
        state_string            -- if set, write this value into ccpp_suite_state
                                   at the end of the subroutine.
        check_string            -- if set, verify ccpp_suite_state equals this
                                   value at the start of the subroutine.
        already_scheduled_allocs -- optional set shared by every phase call
                                   for one suite (see _generate_lifecycle_fns);
                                   forwarded to _build_framework_refs so a
                                   _run-only-resolvable framework var still
                                   gets a LazyAllocOp without duplicating one
                                   an earlier _init/_register call already
                                   made.
        """
        if generated_subroutine_posfix is None:
            assert tgt_subroutine_postfix is not None
            generated_subroutine_posfix = tgt_subroutine_postfix

        _tables = self._build_arg_tables(suite_description, tgt_subroutine_postfix, physics_mode)
        scheme_entries = _tables.scheme_entries
        arg_tables = _tables.arg_tables
        scheme_overrides = _tables.scheme_overrides
        actual_postfixes = _tables.actual_postfixes
        all_args = _tables.all_args
        suite_use_stubs = _tables.suite_use_stubs
        divergent_std_keys = _tables.divergent_std_keys

        _cls = self._classify_args(all_args, physics_mode)
        framework_vars = _cls.framework_vars
        input_arg_list = _cls.input_arg_list
        output_arg_list = _cls.output_arg_list
        ncol_meta = _cls.ncol_meta

        phase_name = "run" if physics_mode else _PHASE_NAMES.get((tgt_subroutine_postfix, False))
        if phase_name is not None:
            records = self.resolved_vars.setdefault(phase_name, [])
            for arg in (*framework_vars.values(), *input_arg_list, *output_arg_list):
                record = _resolved_var_record(arg)
                if record is not None:
                    _apply_ddt_chain(record, arg, self.ddt_resolution_maps)
                    records.append(record)
            # ncol_meta is the *original* loop-extent arg (real
            # standard_name intact) that _classify_args replaces in
            # input_arg_list with nameless synthetic col_start/col_end
            # scalars for physics_mode dispatch -- included here so the
            # loop-extent variable's identity isn't lost entirely
            # (capgen_v1_parity_backlog.md Stage 4 found it otherwise
            # silently disappears, since _resolved_var_record filters out
            # the nameless col_start/col_end args that replace it). Unlike
            # framework_vars/input_arg_list/output_arg_list, ncol_meta was
            # never itself run through HostVariableMatchPass (that pass
            # runs before this synthesis exists), so its model_var_name is
            # always None here even when the host directly declares the
            # normalized identity (e.g. horizontal_dimension) -- real
            # capgen-v1 resolves this via its own VarLoopSubst mechanism.
            # capgen_v1_parity_backlog.md Stage 7 confirmed this blocked
            # every CAM-SIMA fixture using the (still-valid, still-
            # supported) horizontal_loop_extent column-chunking convention.
            # Fixed here, not in HostVariableMatchPass itself: a fallback
            # lookup against host_var_index (built once per SuiteCAP.apply()
            # from the same HOST/MODULE tables that pass already indexes),
            # keyed by the *normalized* standard name _resolved_var_record
            # just computed -- scoped to ncol_meta specifically, not
            # framework_vars/input_arg_list/output_arg_list, since those
            # can be legitimately host-unmatched by design (e.g. CapScratch
            # vars), where forcing a host match would be wrong.
            if ncol_meta is not None:
                ncol_record = _resolved_var_record(ncol_meta)
                if ncol_record is not None:
                    if ncol_record["model_var_name"] is None:
                        host_match = self.host_var_index.get(
                            ncol_record["standard_name"].lower()
                        )
                        if host_match is not None:
                            ncol_record["model_var_name"] = host_match[0]
                            ncol_record["model_module_name"] = host_match[1]
                            ncol_record["is_host_table_var"] = host_match[2]
                            ncol_record["is_protected"] = ncol_record["is_protected"] or host_match[3]
                        # end if
                    # end if
                    records.append(ncol_record)
                # end if
            # end if

        _sig = self._build_block_signature(
            input_arg_list, output_arg_list, divergent_std_keys=divergent_std_keys,
        )
        new_block = _sig.new_block
        input_arg_types = _sig.input_arg_types
        data_ops = _sig.data_ops
        alloc_ops = _sig.alloc_ops
        kind_cast_ops = _sig.kind_cast_ops
        kind_writeback_pairs = _sig.kind_writeback_pairs
        unit_convert_ops = _sig.unit_convert_ops
        unit_writeback_pairs = _sig.unit_writeback_pairs

        ncol_compute_ops = self._build_ncol_compute_ops(physics_mode, data_ops, ncol_meta)

        initialisation_ops = self.generateVariableInitialisations(data_ops)

        framework_ref_ops, lazy_alloc_ops = self._build_framework_refs(
            framework_vars=framework_vars,
            all_args=all_args,
            data_ops=data_ops,
            suite_use_stubs=suite_use_stubs,
            suite_model=suite_model,
            tgt_subroutine_postfix=tgt_subroutine_postfix,
            physics_mode=physics_mode,
            arg_tables=arg_tables,
            already_scheduled_allocs=already_scheduled_allocs,
        )

        call_ops, fn_sigs = self._build_call_ops(
            suite_description=suite_description,
            tgt_subroutine_postfix=tgt_subroutine_postfix,
            physics_mode=physics_mode,
            all_args=all_args,
            data_ops=data_ops,
            framework_ref_ops=framework_ref_ops,
            suite_use_stubs=suite_use_stubs,
            actual_postfixes=actual_postfixes,
            arg_tables=arg_tables,
            scheme_overrides=scheme_overrides,
            divergent_std_keys=divergent_std_keys,
        )

        # Multi-instance suite (real capgen-v1's model, ccpp_cap_refactor_
        # plan.md's "instances/instances_advection" entry): this call's own
        # instance_number-standard-name arg indexes ccpp_suite_state, which
        # must itself be allocated -- and sized by number_of_instances --
        # before the check/assignment ops below read/write it. Only needed
        # on phases that actually touch ccpp_suite_state (every non-run
        # lifecycle phase except _register, which never checks/assigns
        # state at all, plus each physics group's _run) -- see
        # subroutine_specs in _generate_lifecycle_fns.
        #
        # instance_local_name here can come from a SCHEME's own explicit
        # arg-table declaration (e.g. a physics scheme's _run entry point
        # declaring instance_number itself), not only from
        # _synthesize_instance_number_arg -- so it is NOT already
        # guaranteed paired with ninstances_local_name the way
        # _is_multi_instance_host's callers are. Drop it back to None
        # whenever ninstances_local_name is absent, else
        # generateStateCheckOps/generateStateAssignment below would index
        # ccpp_suite_state(instance) into what _build_state_globals
        # correctly declared as a plain (non-array) scalar in that case --
        # invalid Fortran. Same paired-contract bug class as Copilot's
        # PR #77 review; found via this file's own regression test.
        instance_local_name = self._instance_arg_local_name(input_arg_list)
        ninstances_local_name = self._number_of_instances_local_name(input_arg_list)
        if ninstances_local_name is None:
            instance_local_name = None
        if (
            instance_local_name is not None
            and ninstances_local_name is not None
            and (check_string is not None or state_string is not None)
        ):
            lazy_alloc_ops.append(
                self._build_suite_state_lazy_alloc(data_ops[ninstances_local_name])
            )

        # Suite-level <init>/<final> scheme hook (v2.0 SDF schema): note the
        # entry-point postfix is "_init"/"_final" here, NOT tgt_subroutine_
        # postfix's own "_init"/"_finalize" -- confirmed against the real
        # upstream example (suite_lifecycle.F90 declares suite_lifecycle_init/
        # suite_lifecycle_final, matching the <init>/<final> tag names
        # themselves, not this codebase's own group-scheme "_finalize"
        # convention).
        suite_lifecycle_call_ops = []
        if tgt_subroutine_postfix == "_init":
            suite_lifecycle_call_ops = self._build_suite_lifecycle_call_ops(
                suite_description.init_scheme, "_init", data_ops, fn_sigs, suite_use_stubs,
            )
        elif tgt_subroutine_postfix == "_finalize":
            suite_lifecycle_call_ops = self._build_suite_lifecycle_call_ops(
                suite_description.final_scheme, "_final", data_ops, fn_sigs, suite_use_stubs,
            )

        new_func = self._assemble_func(
            suite_description=suite_description,
            generated_subroutine_posfix=generated_subroutine_posfix,
            check_string=check_string,
            state_string=state_string,
            input_arg_list=input_arg_list,
            input_arg_types=input_arg_types,
            new_block=new_block,
            data_ops=data_ops,
            alloc_ops=alloc_ops,
            kind_cast_ops=kind_cast_ops,
            kind_writeback_pairs=kind_writeback_pairs,
            unit_convert_ops=unit_convert_ops,
            unit_writeback_pairs=unit_writeback_pairs,
            call_ops=call_ops,
            initialisation_ops=initialisation_ops,
            ncol_compute_ops=ncol_compute_ops,
            framework_ref_ops=framework_ref_ops,
            lazy_alloc_ops=lazy_alloc_ops,
            suite_lifecycle_call_ops=suite_lifecycle_call_ops,
            instance_local_name=instance_local_name,
        )
        return new_func, list(fn_sigs.values()), suite_use_stubs

    def clone_func_defs(self, func_defs):
        """Create private external declarations for a list of scheme FuncOps.

        These stubs are placed in the generated module so that the IR remains
        self-contained and verifiable before linking against the real scheme
        object files.
        """
        return [
            func.FuncOp.external(
                fd.sym_name.data, fd.function_type.inputs, fd.function_type.outputs
            )
            for fd in func_defs
        ]

    def _generate_lifecycle_fns(self, suite_description, suite_model) -> "_LifecycleFnsResult":
        """Generate FuncOps for the five fixed lifecycle specs plus one per physics group."""
        subroutine_specs = [
            ("_register",            "_register",         None,            None),
            ("_init",                "_initialize",       "initialized",   "uninitialized"),
            ("_finalize",            "_finalize",         "uninitialized", "initialized"),
            ("_timestep_initialize", "_timestep_initial", "in_time_step",  "initialized"),
            ("_timestep_finalize",   "_timestep_final",   "initialized",   "in_time_step"),
        ]

        generated_fns: list = []
        fn_sigs_by_name: dict = {}
        suite_host_use_stubs: list = []
        check_strings_used: set = set()
        state_strings_used: set = set()
        # Shared across every phase call below (register/init/finalize/
        # timestep_*, then one per physics group) so a framework var already
        # successfully allocated during _init/_register -- the common case,
        # covering both the framework_vars loop and the suite_model sweep in
        # _build_framework_refs -- doesn't also get a second, redundant
        # LazyAllocOp in every physics group's _run body too. Scoped to this
        # one suite (fresh set per _generate_lifecycle_fns call, i.e. per
        # ccpp.SuiteOp), not shared across suites, since the same
        # standard_name in a different suite is a different module-scoped
        # variable.
        scheduled_allocs: set = set()

        for tgt_postfix, gen_postfix, state_string, check_string in subroutine_specs:
            fn, sigs, stubs = self.generateSubroutineCall(
                suite_description, tgt_postfix, gen_postfix,
                state_string=state_string, check_string=check_string,
                physics_mode=(tgt_postfix == "_run"), suite_model=suite_model,
                already_scheduled_allocs=scheduled_allocs,
            )
            generated_fns.append(fn)
            suite_host_use_stubs.extend(stubs)
            for sig in sigs:
                fn_sigs_by_name[sig.sym_name.data] = sig
            if check_string is not None:
                check_strings_used.add(check_string)
            if state_string is not None:
                state_strings_used.add(state_string)

        for group in suite_description:
            group_name = group.attributes["name"]
            group_suite = XMLSuite(
                suite_description.attributes["name"],
                suite_description.attributes["version"],
            )
            group_suite.addChild(group)
            fn, sigs, stubs = self.generateSubroutineCall(
                group_suite, "_run", f"_{group_name}",
                state_string=None, check_string="in_time_step",
                physics_mode=True, group_name=group_name, suite_model=suite_model,
                already_scheduled_allocs=scheduled_allocs,
            )
            generated_fns.append(fn)
            suite_host_use_stubs.extend(stubs)
            for sig in sigs:
                fn_sigs_by_name[sig.sym_name.data] = sig
            check_strings_used.add("in_time_step")

        return _LifecycleFnsResult(
            generated_fns=generated_fns,
            fn_sigs_by_name=fn_sigs_by_name,
            suite_host_use_stubs=suite_host_use_stubs,
            check_strings_used=check_strings_used,
            state_strings_used=state_strings_used,
        )

    def _build_fn_signatures(
        self, fn_sigs_by_name: dict, scheme_entries: list, extra_scheme_names: "list | None" = None,
    ) -> list:
        """Clone collected scheme function signatures, annotating each with its module name.

        extra_scheme_names -- schemes referenced outside any group's own
        call sequence (currently just a suite-level <init>/<final> hook, if
        declared) that still need a module_name -> use-stub mapping here.
        """
        sub_to_module: dict[str, str] = {}
        all_scheme_names = [s for s, _ in scheme_entries] + list(extra_scheme_names or [])
        for scheme_name in all_scheme_names:
            for postfix in ("_run", "_init", "_finalize", "_final", "_register",
                            "_timestep_initialize", "_timestep_finalize",
                            "_timestep_init", "_timestep_final"):
                sub_to_module[scheme_name + postfix] = scheme_name

        fn_sigs = []
        for fd in fn_sigs_by_name.values():
            cloned = func.FuncOp.external(
                fd.sym_name.data, fd.function_type.inputs, fd.function_type.outputs
            )
            module_name = sub_to_module.get(fd.sym_name.data)
            if module_name:
                cloned.attributes["module"] = StringAttr(module_name)
                meta = self.meta_data.get(module_name)
                if meta is not None and meta.hasAttr("language"):
                    cloned.attributes["language"] = StringAttr(meta.getAttr("language"))
                    # Stamp arg names and intents so the printer can emit a
                    # BIND(C) interface block without re-reading the meta files.
                    arg_table = meta.arg_tables.get(fd.sym_name.data)
                    if arg_table is not None:
                        args = list(arg_table.getFunctionArguments())
                        cloned.attributes["arg_names"] = ArrayAttr(
                            [StringAttr(a.name) for a in args]
                        )
                        cloned.attributes["arg_intents"] = ArrayAttr(
                            [StringAttr(a.getAttr("intent") if a.hasAttr("intent") else "in")
                             for a in args]
                        )
            fn_sigs.append(cloned)
        return fn_sigs

    def _build_ddt_use_stubs(self, scheme_entries: list) -> list:
        """Return llvm.GlobalOp USE-stubs for each DDT type referenced by scheme args."""
        arg_tables_iterable = (
            arg_table
            for scheme_name, _ in scheme_entries
            if scheme_name in self.meta_data
            for arg_table in self.meta_data[scheme_name].arg_tables.values()
        )
        return _collect_ddt_use_stubs(arg_tables_iterable, self.ddt_source_module)

    def _build_state_globals(self, all_strings_used: set):
        """Return the mutable ccpp_suite_state global and one read-only global per state string.

        For a multi-instance suite (host declares BOTH instance_number and
        number_of_instances -- see _is_multi_instance_host; real capgen-v1's
        multi-instance model, ccpp_cap_refactor_plan.md's "instances/
        instances_advection" entry), ccpp_suite_state must hold one entry
        per model instance, not a single shared scalar -- else two
        instances collide on the same state (the real ctest failure on
        examples/instances this fixes). number_of_instances is itself a
        runtime HOST-declared scalar, not a compile-time constant, so the
        array is declared allocatable/deferred-shape here and actually
        sized+allocated lazily on first use -- see
        _build_suite_state_lazy_alloc, wired into generateSubroutineCall.

        Gated on _is_multi_instance_host (both names), not just
        instance_number alone -- a host declaring only instance_number
        would otherwise get an allocatable ccpp_suite_state that the lazy
        alloc guard (which separately requires ninstances_local_name) can
        never actually allocate. Same bug class as Copilot's PR #77
        review; this is suite_cap.py's own instance of it.
        """
        ccpp_suite_state_global = llvm.GlobalOp(
            llvm.LLVMArrayType.from_size_and_type(16, i8),
            "ccpp_suite_state",
            "internal",
            value=StringAttr("uninitialized"),
        )
        if self._is_multi_instance_host():
            ccpp_suite_state_global.attributes["allocatable"] = StringAttr("1")
        string_const_globals = [
            self.generateStringConstantGlobal(s) for s in sorted(all_strings_used)
        ]
        return ccpp_suite_state_global, string_const_globals

    def _build_module_vars(self, suite_model):
        """Return (allocatable_mod_vars, interstitial_var_names) for suite-owned variables."""
        interstitial_var_names: set[str] = set()
        allocatable_mod_vars = []
        for entry in suite_model.suite_owned_vars():
            if entry.is_ddt:
                # DDT interstitials are module-scope non-allocatable scalars; require
                # type(...) syntax in Fortran.
                allocatable_mod_vars.append(
                    ModuleVarOp(entry.local_name, "type", ddt_name=entry.fortran_type, rank=0)
                )
                interstitial_var_names.add(entry.local_name.lower())
                continue
            if entry.fortran_type == "real":
                kind = entry.kind if entry.kind else CCPP_KIND_PHYS
                allocatable_mod_vars.append(
                    ModuleVarOp(entry.local_name, "real", kind=kind, rank=entry.rank)
                )
            elif entry.fortran_type == "integer":
                allocatable_mod_vars.append(
                    ModuleVarOp(entry.local_name, "integer", rank=entry.rank)
                )
            else:
                allocatable_mod_vars.append(
                    ModuleVarOp(entry.local_name, entry.fortran_type,
                                kind=entry.kind if entry.kind else None, rank=entry.rank)
                )
            interstitial_var_names.add(entry.local_name.lower())
        return allocatable_mod_vars, interstitial_var_names

    @staticmethod
    def _inject_safe_deallocs(generated_fns, allocatable_mod_vars, interstitial_var_names):
        """Inject SafeDeallocOps for allocatable arrays before the return of _timestep_final."""
        for fn in generated_fns:
            if not isa(fn, func.FuncOp):
                continue
            if "_timestep_final" not in fn.sym_name.data:
                continue
            if not fn.body.blocks:
                continue
            block = fn.body.blocks[0]
            ret_op = next((bop for bop in block.ops if isa(bop, func.ReturnOp)), None)
            if ret_op is None:
                continue
            for var_decl in allocatable_mod_vars:
                # Only arrays (rank > 0); skip interstitials that persist until _finalize.
                if var_decl.rank.value.data > 0 and \
                        var_decl.var_name.data.lower() not in interstitial_var_names:
                    Rewriter.insert_op(SafeDeallocOp(var_decl.var_name.data),
                                       InsertPoint.before(ret_op))

    @staticmethod
    def _inject_suite_owned_gpu_exit(generated_fns, suite_model):
        """Emit AccExitDataOp for every SuiteOwned var whose enter-data-create
        actually fired (SuiteOwned residency backlog item), in the true
        _finalize function -- not _timestep_final, where
        _inject_safe_deallocs's own SafeDeallocOps (if any ever fire) live.
        These arrays are never deallocated in practice (confirmed: no
        `deallocate` appears anywhere in generated output for this project's
        real examples), so they persist for the whole simulation -- the same
        whole-sim scope GPUCcppCapPass already uses for HostMatched vars
        (entry at register/initialize, exit at finalize).

        Deliberately keyed off which LazyAllocOps actually got
        needs_device_residency set in the *generated IR* (scanned here),
        not off suite_model's static classification alone: a SuiteOwned
        var's allocation dimensions aren't always resolvable outside
        physics_mode (e.g. an arg declared with horizontal_loop_extent
        rather than horizontal_dimension -- confirmed via examples/
        helloworld's own temp_layer), in which case _build_framework_refs
        never actually emits a LazyAllocOp for it in _register/_init at
        all. Emitting an exit-data-delete for such a var would be an
        unmatched, invalid exit-data call with no corresponding enter --
        enter and exit must stay balanced.
        """
        resident_var_names: set = set()
        for fn in generated_fns:
            if not isa(fn, func.FuncOp) or not fn.body.blocks:
                continue
            for block_op in fn.body.blocks[0].ops:
                if (
                    isa(block_op, LazyAllocOp)
                    and block_op.needs_device_residency is not None
                    and bool(block_op.needs_device_residency.value.data)
                ):
                    resident_var_names.add(block_op.var_name.data)

        if not resident_var_names:
            return

        entries_by_name = {e.local_name: e for e in suite_model.suite_owned_vars()}

        for fn in generated_fns:
            if not isa(fn, func.FuncOp):
                continue
            if not fn.sym_name.data.endswith("_suite_finalize"):
                continue
            if not fn.body.blocks:
                continue
            block = fn.body.blocks[0]
            ret_op = next((bop for bop in block.ops if isa(bop, func.ReturnOp)), None)
            if ret_op is None:
                continue
            for var_name in sorted(resident_var_names):
                entry = entries_by_name.get(var_name)
                if entry is None:
                    continue
                var_type = TypeConversions.convert(
                    entry.fortran_type, entry.kind if entry.kind else None, entry.rank
                )
                ref_op = ccpp_utils.HostVarRefOp(entry.local_name, "", var_type)
                Rewriter.insert_op(ref_op, InsertPoint.before(ret_op))
                Rewriter.insert_op(
                    ccpp_utils.AccExitDataOp(delete=[ref_op.res]),
                    InsertPoint.before(ret_op),
                )

    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: ccpp.SuiteOp, rewriter: PatternRewriter):
        """Generate the complete cap module for one ccpp.SuiteOp."""
        suite_description = self.suite_descriptions[op.suite_name.data]
        suite_model = SuiteVariableModel(suite_description, self.meta_data, self._std_key)

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

        allocatable_mod_vars, interstitial_var_names = self._build_module_vars(suite_model)
        if allocatable_mod_vars:
            self._inject_safe_deallocs(generated_fns, allocatable_mod_vars, interstitial_var_names)
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
    each CCPP lifecycle phase (capgen_v1_parity_backlog.md Stage 3's native
    introspection artifact -- host-model consumers like a
    write_init_files.py-equivalent read this instead of any capgen-v1 object).

    Not a flag of this pass directly in normal use: supplied via
    ``--emit-resolved-vars`` on the ``ccpp_xdsl`` CLI (``ccpp_dsl.py``'s
    ``ccppMain``), which threads it into this ``generate-suite-cap`` pass
    parameter when building the ``ccpp_opt -p`` pipeline string.
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

        # Only needed by generateSubroutineCall's --emit-resolved-vars
        # fallback lookup (ncol_meta) -- building it unconditionally would
        # add a full HOST/MODULE table traversal to every normal cap
        # generation run, even when nobody asked for resolved-vars output.
        host_var_index = build_host_var_index(ccpp_mod) if self.emit_resolved_vars else {}

        # Same reasoning: only needed by the --emit-resolved-vars DDT-member
        # chain resolution (_apply_ddt_chain). Real cap generation resolves
        # DDT chains independently via run_dispatch.py, which builds its own
        # copy of these maps from the same (cheap, pure) cap_shared.py
        # functions when it actually needs them.
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
        )
        PatternRewriteWalker(
            GreedyRewritePatternApplier([generator]),
            apply_recursively=False,
        ).rewrite_module(op)

        if self.emit_resolved_vars:
            _write_resolved_vars(
                generator.resolved_vars, self.emit_resolved_vars, host_vars=ddt_host_var_map,
            )
