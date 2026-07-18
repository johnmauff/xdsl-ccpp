from dataclasses import dataclass

from xdsl.context import Context
from xdsl.dialects import arith, builtin, func, llvm, memref, scf
from xdsl.dialects.builtin import ArrayAttr, DictionaryAttr, IntegerAttr, MemRefType, StringAttr, i32, i8
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
from xdsl_ccpp.dialects.ccpp import CcppHandleOp
from xdsl_ccpp.dialects.ccpp_utils import (
    ArraySectionOp,
    ClearStringOp,
    KindCastOp,
    KindWriteBackOp,
    ModuleVarOp,
    KeywordCallOp,
    LazyAllocOp,
    PresentCheckOp,
    PromotionLoopOp,
    RankReducingSliceOp,
    SafeDeallocOp,
    SubcycleLoopOp,
    UnitConvertOp,
    UnitWriteBackOp,
)
from xdsl_ccpp.transforms.util.cap_shared import (
    _collect_ddt_use_stubs,
    _is_framework_managed,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    BuildMetaDataDescriptions,
    BuildSchemeDescription,
    CCPPArgument,
    XMLSubcycle,
    XMLSuite,
    collect_ddt_source_modules,
)
from xdsl_ccpp.transforms.util.ir_utils import find_ccpp_module
from xdsl_ccpp.transforms.util.suite_variable_model import SuiteVariableModel
from xdsl_ccpp.transforms.util.typing import TypeConversions
from xdsl_ccpp.util.ccpp_conventions import (
    CCPP_ERRMSG_LEN,
    CCPP_KIND_PHYS,
    CCPP_LOOP_BEGIN_STD_NAME,
    CCPP_LOOP_END_STD_NAME,
    CCPP_LOOP_EXTENT_STD_NAME,
    CCPP_HORIZ_DIM_STD_NAME,
    CCPP_NUM_INSTANCES,
    CCPP_SUBCYCLE_UNKNOWN_LOOP_COUNT,
    UNIT_CONVERSIONS,
    dims_compatible,
)
from xdsl_ccpp.util.visitor import Visitor


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
                 ddt_source_module=None, ccpp_handle=None, num_instances=CCPP_NUM_INSTANCES):
        self.suite_descriptions = suite_descriptions
        self.meta_data = meta_data
        self.meta_fn_sigs = meta_fn_sigs
        self.top_level_module = top_level_module
        # Maps DDT type name → Fortran module that defines it (from source_module attr).
        self.ddt_source_module: dict[str, str] = ddt_source_module or {}
        # (var_name, module_name) for the host's ccpp_t variable, or None.
        self.ccpp_handle: "tuple[str, str] | None" = ccpp_handle
        # Maximum number of simultaneous CCPP instances for the per-instance state array.
        self.num_instances: int = num_instances

    def getSchemeNames(self, suite_description):
        """Return a flat list of (scheme_name, overrides) pairs from all groups.

        Flattens through XMLSubcycle nodes so the result is always a plain
        sequence of scheme entries regardless of subcycle structure.
        ``overrides`` is a plain ``{arg_name: literal_str}`` dict, empty when
        the scheme was not called with keyword argument overrides.
        """
        result = []
        for group in suite_description:
            for child in group:
                if isinstance(child, XMLSubcycle):
                    for scheme in child:
                        result.append(
                            (
                                scheme.attributes["name"],
                                scheme.attributes.get("arg_overrides", {}),
                            )
                        )
                else:
                    result.append(
                        (
                            child.attributes["name"],
                            child.attributes.get("arg_overrides", {}),
                        )
                    )
        return result

    def getCallSequence(self, suite_description):
        """Return the ordered call sequence, preserving subcycle boundaries.

        Each element is one of:
          ``('scheme',   scheme_name, overrides)``                         — flat call
          ``('subcycle', loop_count, is_literal, [(scheme_name, overrides), ...])``  — subcycle block
        """
        sequence = []
        for group in suite_description:
            for child in group:
                if isinstance(child, XMLSubcycle):
                    schemes = [
                        (s.attributes["name"], s.attributes.get("arg_overrides", {}))
                        for s in child
                    ]
                    sequence.append(("subcycle", child.attributes["loop_count"],
                                     child.attributes["is_literal"], schemes))
                else:
                    sequence.append(
                        (
                            "scheme",
                            child.attributes["name"],
                            child.attributes.get("arg_overrides", {}),
                        )
                    )
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
        return None

    def _build_promoted_call_ops(
        self,
        subroutine_name,
        arg_table,
        data_ops,
        loop_var_memref,
        overrides=None,
    ):
        """Build scheme call ops for a promoted scheme inside the loop body.

        For arguments marked is_promoted, replaces the raw 2D data_ops value
        with a RankReducingSliceOp that slices out the current level.
        The dim_pattern is constructed from the promoted_dim annotation.
        """
        promoted_data_ops = dict(data_ops)  # shallow copy to override promoted args

        # Separate slice ops by whether the source arg is optional+promoted.
        # Optional-promoted slices live only in the with_body of PresentCheckOp.
        # Shared slices are emitted unconditionally before any guard.
        shared_slice_ops: list = []
        opt_slice_ops: dict[str, object] = {}  # arg_name -> RankReducingSliceOp

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
                        range_lowers.append(data_ops["ccpp_lbound_one"])
                        range_uppers.append(data_ops.get("ncol", loop_var_memref))
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
        exclude_args=frozenset(),
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

        When *overrides* is non-empty a KeywordCallOp is emitted instead of a
        plain func.CallOp; overridden arguments are omitted from the SSA
        operand/result lists and carried as compile-time literals in the op.
        """
        if overrides is None:
            overrides = {}

        # Only apply overrides whose names actually appear in this arg table;
        # the same override dict may be shared across entry points (_run, _init,
        # _finalize) and not every entry point has the same arguments.
        arg_names_in_table = {arg.name for arg in arg_table.getFunctionArguments()}
        overrides = {k: v for k, v in overrides.items() if k in arg_names_in_table}

        # Retrieve the callee's declared input/output types to detect mismatches.
        callee = self.meta_fn_sigs.get(subroutine_name)
        callee_in_types = list(callee.function_type.inputs) if callee else []
        callee_out_types = list(callee.function_type.outputs) if callee else []

        in_ssa = []
        in_names = []
        out_types = []
        out_names = []
        out_tracking = []
        cast_ops = []  # casts inserted before the call inside the if-body
        in_idx = 0
        out_idx = 0

        # Classify each argument as an input, output, or both (inout)
        for arg in arg_table.getFunctionArguments():
            intent = arg.getAttr("intent")
            is_overridden = arg.name in overrides
            is_excluded = arg.name in exclude_args
            if intent == "in" or intent == "inout":
                if not is_overridden and not is_excluded:
                    val = data_ops[arg.name]
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
            if intent == "out":
                # Fortran passes ALL arguments by reference, including intent(out).
                # Treating out args as return values breaks positional order when
                # scalars and arrays are interspersed. Pass everything by reference.
                if not is_overridden and not is_excluded:
                    val = data_ops[arg.name]
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

        assert len(out_types) == len(out_tracking)
        has_optional = any(
            arg.hasAttr("optional") for arg in arg_table.getFunctionArguments()
        )
        if overrides or has_optional:
            call_op = KeywordCallOp(
                subroutine_name,
                ArrayAttr([StringAttr(n) for n in in_names]),
                ArrayAttr([StringAttr(n) for n in out_names]),
                DictionaryAttr({k: StringAttr(v) for k, v in overrides.items()}),
                in_ssa,
                out_types,
            )
        else:
            call_op = func.CallOp(subroutine_name, in_ssa, out_types)

        # Copy each output result back to its storage location.
        # If the result type doesn't match the destination, cast back first.
        store_ops = []
        for idx, out_var in enumerate(out_tracking):
            dest_type = (
                out_var.type
                if isinstance(out_var, SSAValue)
                else out_var.results[0].type
            )
            result = call_op.results[idx]
            if result.type != dest_type:
                back_cast = builtin.UnrealizedConversionCastOp(
                    operands=[[result]], result_types=[[dest_type]]
                )
                store_ops.append(back_cast)
                store_ops.append(memref.CopyOp(back_cast.results[0], out_var))
            else:
                store_ops.append(memref.CopyOp(result, out_var))

        # Guard the call: only execute when errflg == 0
        err_const_comp = arith.ConstantOp.from_int_and_width(0, 32)
        load_op = memref.LoadOp.get(data_ops["errflg"], [])
        cmp = arith.CmpiOp(load_op, err_const_comp, 0)
        conditional_op = scf.IfOp(
            cmp, [], cast_ops + [call_op] + store_ops + [scf.YieldOp()]
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
        self, check_string: str, data_ops, fn_name: str | None = None
    ):
        """Emit ops that compare ccpp_suite_state against check_string.

        If the state does not match the expected value, errflg is set to 1
        and, when fn_name is provided, an error message is written into errmsg.
        The comparison uses ccpp_utils.StrCmpOp (lowered later by the
        lower-ccpp-utils pass) and an XOrI to negate the equality result.
        """
        arr_type = llvm.LLVMArrayType.from_size_and_type(16, i8)

        # Load the expected state constant and the current runtime state
        addr_const = llvm.AddressOfOp("const_" + check_string, llvm.LLVMPointerType())
        loaded_const = llvm.LoadOp(addr_const, arr_type)
        addr_state = llvm.AddressOfOp("ccpp_suite_state", llvm.LLVMPointerType())
        if self.ccpp_handle is not None:
            addr_state.attributes["ccpp_instance_ref"] = StringAttr(self.ccpp_handle[0])
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

    def generateStateAssignment(self, state_string: str):
        """Emit ops that write state_string into the ccpp_suite_state global."""
        arr_type = llvm.LLVMArrayType.from_size_and_type(16, i8)
        # Load from the string constant global and store into ccpp_suite_state
        addr_src = llvm.AddressOfOp("const_" + state_string, llvm.LLVMPointerType())
        loaded = llvm.LoadOp(addr_src, arr_type)
        addr_dst = llvm.AddressOfOp("ccpp_suite_state", llvm.LLVMPointerType())
        if self.ccpp_handle is not None:
            addr_dst.attributes["ccpp_instance_ref"] = StringAttr(self.ccpp_handle[0])
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

    def _build_block_signature(self, input_arg_list, output_arg_list) -> "_BlockSignature":
        """Build the Block, populate data_ops from block args, and apply kind/unit casts."""
        input_arg_types = [
            TypeConversions.convert(a.getAttr("type"), self._block_arg_kind(a), self._arg_dims(a))
            for a in input_arg_list
        ]
        if self.ccpp_handle is not None:
            _ccpp_t_type = memref.MemRefType(ccpp_utils.DerivedType("ccpp_t"), [])
            input_arg_types.append(_ccpp_t_type)

        new_block = Block(arg_types=input_arg_types)

        data_ops = {}
        for idx, fn_arg in enumerate(input_arg_list):
            hint = fn_arg.name
            if fn_arg.hasAttr("allocatable"):
                hint = fn_arg.name + "__alloc"
            elif fn_arg.hasAttr("optional"):
                hint = fn_arg.name + "__opt"
            elif (self._has_dims(fn_arg)
                  and fn_arg.getAttr("intent") == "in"):
                # Array args that are truly intent(in) get __in so the printer
                # emits intent(in) rather than the default intent(inout).
                # Unit-mismatched args are now converted into a local copy so
                # the host's array is never modified — intent(in) is correct.
                hint = fn_arg.name + "__in"
            new_block.args[idx].name_hint = hint
            data_ops[fn_arg.name] = new_block.args[idx]

        if self.ccpp_handle is not None:
            new_block.args[len(input_arg_list)].name_hint = self.ccpp_handle[0]

        kind_cast_ops: list = []
        kind_writeback_pairs: list = []
        for idx, fn_arg in enumerate(input_arg_list):
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
            data_ops[fn_arg.name] = cast_op

            intent = fn_arg.getAttr("intent") if fn_arg.hasAttr("intent") else "in"
            if intent in ("inout", "out"):
                kind_writeback_pairs.append((cast_op.res, block_arg_ssa, host_kind))

        unit_convert_ops: list = []
        unit_writeback_pairs: list = []
        for idx, fn_arg in enumerate(input_arg_list):
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
            data_ops[fn_arg.name] = conv_op

            if intent in ("inout", "out"):
                unit_writeback_pairs.append((conv_op.res, block_arg_ssa, to_host_expr))

        alloc_ops = {}
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

        if "errflg" not in data_ops:
            alloc_op = memref.AllocaOp.get(
                TypeConversions.getBaseType("integer"), shape=[]
            )
            alloc_op.memref.name_hint = "errflg"
            alloc_ops["errflg"] = alloc_op
            data_ops["errflg"] = alloc_op
        if "errmsg" not in data_ops:
            alloc_op = memref.AllocaOp.get(
                TypeConversions.getBaseType("character"), shape=[CCPP_ERRMSG_LEN]
            )
            alloc_op.memref.name_hint = "errmsg"
            alloc_ops["errmsg"] = alloc_op
            data_ops["errmsg"] = alloc_op

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
        framework_vars = {
            a.name: a
            for a in all_args.values()
            if _is_framework_managed(a)
        }
        input_arg_list = [
            a
            for a in all_args.values()
            if (a.getAttr("intent") in ("in", "inout") or self._has_dims(a))
            and a.name not in framework_vars
        ]
        output_arg_list = [
            a
            for a in all_args.values()
            if a.getAttr("intent") == "out" and not self._has_dims(a)
            and a.name not in framework_vars
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

    def _build_arg_tables(self, suite_description, tgt_subroutine_postfix) -> "_ArgTableResult":
        """Build argument tables, overrides, and canonical arg map for all schemes."""
        _POSTFIX_ALIASES: dict[str, str] = {
            "_timestep_initialize": "_timestep_init",
            "_timestep_finalize": "_timestep_final",
        }
        scheme_entries = self.getSchemeNames(suite_description)
        arg_tables = {}
        scheme_overrides: dict[str, dict[str, str]] = {}
        actual_postfixes: dict[str, str] = {}
        all_args = {}
        suite_use_stubs: list = []
        if tgt_subroutine_postfix is not None:
            _postfix_candidates = [tgt_subroutine_postfix]
            if tgt_subroutine_postfix in _POSTFIX_ALIASES:
                _postfix_candidates.append(_POSTFIX_ALIASES[tgt_subroutine_postfix])
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

        return _ArgTableResult(
            scheme_entries=scheme_entries,
            arg_tables=arg_tables,
            scheme_overrides=scheme_overrides,
            actual_postfixes=actual_postfixes,
            all_args=all_args,
            suite_use_stubs=suite_use_stubs,
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
    ):
        """Assemble all op lists into the body block and return the FuncOp."""
        inout_return_vals = [
            data_ops[a.name]
            for a in input_arg_list
            if a.getAttr("intent") == "inout" and not self._has_dims(a)
        ]
        if self.ccpp_handle is not None:
            inout_return_vals.append(new_block.args[len(input_arg_list)])
        alloc_return_vals = list(alloc_ops.values())

        errmsg_fn_name = suite_description.attributes["name"] + generated_subroutine_posfix
        check_ops = (
            self.generateStateCheckOps(check_string, data_ops, errmsg_fn_name)
            if check_string is not None
            else []
        )
        state_ops = (
            self.generateStateAssignment(state_string)
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
                    )
                    if full_name not in fn_sigs:
                        fn_sigs[full_name] = self.meta_fn_sigs[full_name]
                return ops
            lv_alloc = memref.AllocaOp.get(
                TypeConversions.getBaseType("integer"), shape=[]
            )
            lv_alloc.memref.name_hint = "vertical_layer_index"
            body_list: list = []
            for sn, tbl in cur_pgroup:
                full_name = sn + actual_postfixes.get(sn, tgt_subroutine_postfix)
                body_list += self._build_promoted_call_ops(
                    full_name, tbl, data_ops, lv_alloc.memref,
                    scheme_overrides.get(sn, {}),
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
                    result += self.generateSchemeSubroutineCallOps(
                        full_name, tbl, data_ops, scheme_overrides.get(sn, {}),
                    )
            result += _flush_promoted(cur_pdim, cur_pgroup)
            return result

        for item in call_sequence:
            if item[0] == "scheme":
                _, scheme_name, _ = item
                if scheme_name not in arg_tables:
                    continue
                call_ops += _emit_ordered_list(
                    [(scheme_name, arg_tables[scheme_name])]
                )
            elif item[0] == "subcycle":
                _, loop_count, is_literal, subcycle_scheme_list = item
                flat = [
                    (sn, arg_tables[sn])
                    for sn, _ in subcycle_scheme_list
                    if sn in arg_tables
                ]
                body_ops = _emit_ordered_list(flat)
                _lc_int = (int(loop_count) if is_literal
                           else CCPP_SUBCYCLE_UNKNOWN_LOOP_COUNT)
                if _lc_int > 1 and physics_mode and body_ops:
                    sc_alloc = memref.AllocaOp.get(
                        TypeConversions.getBaseType("integer"), shape=[]
                    )
                    sc_alloc.memref.name_hint = "ccpp_loop_cnt"
                    call_ops += [sc_alloc, SubcycleLoopOp(
                        loop_count=loop_count,
                        loop_var=sc_alloc.memref,
                        body_ops=body_ops,
                        is_literal=is_literal,
                    )]
                else:
                    call_ops += body_ops

        return call_ops, fn_sigs

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
    ):
        """Build HostVarRefOps and LazyAllocOps for framework-managed vars.

        Mutates data_ops and suite_use_stubs as side effects.
        Returns (framework_ref_ops, lazy_alloc_ops).
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

                _is_alloc_phase = tgt_subroutine_postfix in ("_init", "_register")
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
                                var_name=fw_arg.name,
                                kind_name=kind,
                                dim_var_refs=dim_var_refs,
                                init_value=init_val,
                            )
                        )

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
                        )
                    )

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
        """
        if generated_subroutine_posfix is None:
            assert tgt_subroutine_postfix is not None
            generated_subroutine_posfix = tgt_subroutine_postfix

        _tables = self._build_arg_tables(suite_description, tgt_subroutine_postfix)
        scheme_entries = _tables.scheme_entries
        arg_tables = _tables.arg_tables
        scheme_overrides = _tables.scheme_overrides
        actual_postfixes = _tables.actual_postfixes
        all_args = _tables.all_args
        suite_use_stubs = _tables.suite_use_stubs

        _cls = self._classify_args(all_args, physics_mode)
        framework_vars = _cls.framework_vars
        input_arg_list = _cls.input_arg_list
        output_arg_list = _cls.output_arg_list
        ncol_meta = _cls.ncol_meta

        _sig = self._build_block_signature(input_arg_list, output_arg_list)
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

        for tgt_postfix, gen_postfix, state_string, check_string in subroutine_specs:
            fn, sigs, stubs = self.generateSubroutineCall(
                suite_description, tgt_postfix, gen_postfix,
                state_string=state_string, check_string=check_string,
                physics_mode=(tgt_postfix == "_run"), suite_model=suite_model,
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

    def _build_fn_signatures(self, fn_sigs_by_name: dict, scheme_entries: list) -> list:
        """Clone collected scheme function signatures, annotating each with its module name."""
        sub_to_module: dict[str, str] = {}
        for scheme_name, _ in scheme_entries:
            for postfix in ("_run", "_init", "_finalize", "_register",
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
        """Return the mutable ccpp_suite_state global and one read-only global per state string."""
        ccpp_suite_state_global = llvm.GlobalOp(
            llvm.LLVMArrayType.from_size_and_type(16, i8),
            "ccpp_suite_state",
            "internal",
            value=StringAttr("uninitialized"),
        )
        if self.ccpp_handle is not None:
            ccpp_suite_state_global.attributes["dimension"] = StringAttr(
                str(self.num_instances)
            )
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
        fn_sigs = self._build_fn_signatures(fn_sigs_by_name, scheme_entries)
        type_import_globals = self._build_ddt_use_stubs(scheme_entries)

        all_strings_used = _lc.check_strings_used | _lc.state_strings_used
        ccpp_suite_state_global, string_const_globals = self._build_state_globals(all_strings_used)

        allocatable_mod_vars, interstitial_var_names = self._build_module_vars(suite_model)
        if allocatable_mod_vars:
            self._inject_safe_deallocs(generated_fns, allocatable_mod_vars, interstitial_var_names)

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

    num_instances: int = CCPP_NUM_INSTANCES
    """Maximum simultaneous CCPP instances; controls the per-instance state array size.

    Can also be supplied via ``--num-instances`` on the ``ccpp_xml`` frontend, which
    embeds the value as a ``ccpp.num_instances`` attribute on the top-level module.
    That attribute takes precedence over this field when both are present.
    """

    def apply(self, ctx: Context, op: builtin.ModuleOp) -> None:
        ccpp_mod = find_ccpp_module(op.body.block.ops)
        assert ccpp_mod is not None

        # Resolve num_instances: IR attribute from the frontend overrides the field default.
        num_instances = self.num_instances
        attr = op.attributes.get("ccpp.num_instances")
        if attr is not None and isa(attr, IntegerAttr):
            num_instances = attr.value.data

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

        ccpp_handle = None
        for _op in ccpp_mod.body.block.ops:
            if isa(_op, CcppHandleOp):
                ccpp_handle = (_op.var_name.data, _op.module_name.data)
                break

        PatternRewriteWalker(
            GreedyRewritePatternApplier(
                [
                    GenerateSuiteSubroutine(
                        scheme_descriptions, meta_data_descriptions, meta_fn_sigs, op,
                        ddt_source_module=ddt_source_module,
                        ccpp_handle=ccpp_handle,
                        num_instances=num_instances,
                    ),
                ]
            ),
            apply_recursively=False,
        ).rewrite_module(op)
