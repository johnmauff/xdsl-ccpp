from dataclasses import dataclass

from xdsl.context import Context
from xdsl.dialects import arith, builtin, func, llvm, memref, scf
from xdsl.dialects.builtin import ArrayAttr, DictionaryAttr, MemRefType, StringAttr, i8
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
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects import ccpp, ccpp_utils
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
    UnitConvertOp,
    UnitWriteBackOp,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    BuildMetaDataDescriptions,
    BuildSchemeDescription,
    CCPPArgument,
    XMLSuite,
    collect_ddt_source_modules,
)
from xdsl_ccpp.transforms.util.suite_variable_model import SuiteVariableModel
from xdsl_ccpp.transforms.util.typing import TypeConversions
from xdsl_ccpp.util.ccpp_conventions import (
    CCPP_KIND_PHYS,
    CCPP_LOOP_BEGIN_STD_NAME,
    CCPP_LOOP_END_STD_NAME,
    CCPP_LOOP_EXTENT_STD_NAME,
    CCPP_HORIZ_DIM_STD_NAME,
    UNIT_CONVERSIONS,
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


class GenerateSuiteSubroutine(RewritePattern):
    """Rewrites each ccpp.SuiteOp into a named ModuleOp containing the five
    CCPP cap subroutines: initialize, finalize, physics, timestep_initial, and
    timestep_final.  Each subroutine guards scheme calls behind an errflg check
    and manages the ccpp_suite_state lifecycle string.
    """

    def __init__(self, suite_descriptions, meta_data, meta_fn_sigs, top_level_module,
                 ddt_source_module=None):
        self.suite_descriptions = suite_descriptions
        self.meta_data = meta_data
        self.meta_fn_sigs = meta_fn_sigs
        self.top_level_module = top_level_module
        # Maps DDT type name → Fortran module that defines it (from source_module attr).
        self.ddt_source_module: dict[str, str] = ddt_source_module or {}

    def getSchemeNames(self, suite_description):
        """Return a flat list of (scheme_name, overrides) pairs from all groups.

        ``overrides`` is a plain ``{arg_name: literal_str}`` dict, empty when
        the scheme was not called with keyword argument overrides.
        """
        result = []
        for group in suite_description:
            for scheme in group:
                result.append(
                    (
                        scheme.attributes["name"],
                        scheme.attributes.get("arg_overrides", {}),
                    )
                )
        return result

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
                and arg.getAttr("standard_name").lower() == promoted_dim.lower()
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
                        and var.getAttr("standard_name").lower() == promoted_dim.lower()
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
        store = llvm.StoreOp(loaded, addr_dst)
        return [addr_src, loaded, addr_dst, store]

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

        scheme_entries = self.getSchemeNames(suite_description)
        arg_tables = {}
        scheme_overrides: dict[str, dict[str, str]] = {}
        all_args = {}
        suite_use_stubs: list = []  # llvm.GlobalOps for host-module USE statements
        if tgt_subroutine_postfix is not None:
            # Fetch the argument table for each scheme's target subroutine;
            # schemes that don't have this entry point (e.g. no _finalize) are skipped.
            # First occurrence wins for duplicate scheme names.
            for scheme_name, overrides in scheme_entries:
                table = self.getArgumentTable(
                    scheme_name, scheme_name + tgt_subroutine_postfix
                )
                if table is not None and scheme_name not in arg_tables:
                    arg_tables[scheme_name] = table
                    scheme_overrides[scheme_name] = overrides

            # Collect unique args across all schemes, keyed by standard_name.
            # When two schemes use different local names for the same standard_name
            # (e.g. 'temp' and 'temp_layer' for potential_temperature), the first-seen
            # CCPPArgument is canonical — its local name drives the block arg declaration.
            for scheme_name in arg_tables:
                for fn_arg in arg_tables[scheme_name].getFunctionArguments():
                    std_key = self._std_key(fn_arg)
                    if std_key in all_args:
                        assert fn_arg.getAttr("type") == all_args[std_key].getAttr("type")
                    else:
                        all_args[std_key] = fn_arg

        # in/inout args become block arguments (input parameters to the cap subroutine).
        # out-only scalar args are allocated locally; out array args also become block
        # arguments because the host always owns the array buffer and we cannot
        # allocate a dynamic memref without knowing the extents at compile time.
        #
        # Exception: framework-managed real arrays (advected, allocatable) are
        # declared as module-level allocatables and managed by the suite cap itself.
        # They are excluded from the block argument list and handled separately.
        def _has_dims(a):
            return a.hasAttr("dimensions") and a.getAttr("dimensions") > 0

        def _is_framework_managed(a):
            """True for suite-cap-owned variables: interstitials of any type,
            and advected/allocatable real arrays.

            is_interstitial is checked first so integer (and DDT) interstitials
            are not accidentally excluded by the 'real only' guard below.
            """
            # Interstitials of any type — real, integer, or DDT
            if a.hasAttr("is_interstitial"):
                return True
            # Advected/allocatable framework arrays — real only
            if a.getAttr("type") != "real":
                return False
            if not _has_dims(a):
                return False
            return a.hasAttr("advected") or a.hasAttr("allocatable")

        # Separate framework-managed args from regular args
        framework_vars = {
            a.name: a
            for a in all_args.values()
            if _is_framework_managed(a)
        }

        input_arg_list = [
            a
            for a in all_args.values()
            if (a.getAttr("intent") in ("in", "inout") or _has_dims(a))
            and a.name not in framework_vars
        ]
        output_arg_list = [
            a
            for a in all_args.values()
            if a.getAttr("intent") == "out" and not _has_dims(a)
            and a.name not in framework_vars
        ]

        # With standard_name keying, all_args has exactly one entry per standard_name.
        # Look up the loop-extent arg directly — no aliases to filter.
        ncol_meta_entry = all_args.get(CCPP_LOOP_EXTENT_STD_NAME)
        _has_loop_extent = ncol_meta_entry is not None
        if physics_mode and _has_loop_extent:
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

        def _arg_dims(a):
            """Return the dimension count to use for the block arg type.

            For promoted args, use scheme_rank + 1 so the suite physics
            subroutine receives the full host 2D array (e.g. temp_layer(:,:))
            rather than the scheme's 1D slice declaration (temp_layer(:)).
            """
            base = a.getAttr("dimensions") if a.hasAttr("dimensions") else 0
            if a.hasAttr("is_promoted"):
                # One extra dimension per promoted level (currently always 1)
                return base + 1
            return base

        def _block_arg_kind(a):
            """Return the kind to use for the suite function block arg.

            For kind-mismatched args the host provides the value in its own
            kind, so the block arg is declared in the HOST kind.  The suite
            function body then creates a temp in the SCHEME kind and converts.
            """
            if a.hasAttr("model_var_kind_mismatch"):
                return a.getAttr("model_var_kind_mismatch").split(":")[1]
            return a.getAttr("kind") if a.hasAttr("kind") else None

        input_arg_types = [
            TypeConversions.convert(a.getAttr("type"), _block_arg_kind(a), _arg_dims(a))
            for a in input_arg_list
        ]

        new_block = Block(arg_types=input_arg_types)

        data_ops = {}
        # Map each input argument name to its block argument SSA value.
        # Allocatable args get a __alloc suffix on the name_hint so the printer
        # can add the ALLOCATABLE attribute to the Fortran declaration.
        # Optional args get a __opt suffix so the printer adds the OPTIONAL attribute.
        for idx, fn_arg in enumerate(input_arg_list):
            hint = fn_arg.name
            if fn_arg.hasAttr("allocatable"):
                hint = fn_arg.name + "__alloc"
            elif fn_arg.hasAttr("optional"):
                hint = fn_arg.name + "__opt"
            elif (_has_dims(fn_arg)
                  and fn_arg.getAttr("intent") == "in"
                  and not fn_arg.hasAttr("model_var_unit_mismatch")):
                # Array args that are truly intent(in) get __in so the printer
                # emits intent(in) rather than the default intent(inout).
                # Exclude unit-mismatched args: UnitConvertOp modifies them
                # in-place (e.g. ps = ps * 0.01) so they must be intent(inout).
                hint = fn_arg.name + "__in"
            new_block.args[idx].name_hint = hint
            data_ops[fn_arg.name] = new_block.args[idx]

        # For kind-mismatched args: create a KindCastOp that converts the block
        # arg (host kind) to a local temp (scheme kind).  The scheme call will
        # use the temp; inout/out args get a write-back after the call.
        kind_cast_ops: list = []
        kind_writeback_pairs: list = []  # (block_arg_ssa, cast_res, host_kind)
        for idx, fn_arg in enumerate(input_arg_list):
            if not fn_arg.hasAttr("model_var_kind_mismatch"):
                continue
            scheme_kind, host_kind = fn_arg.getAttr("model_var_kind_mismatch").split(":")
            block_arg_ssa = new_block.args[idx]
            scheme_type = TypeConversions.convert(
                fn_arg.getAttr("type"), scheme_kind, _arg_dims(fn_arg)
            )
            cast_op = KindCastOp(block_arg_ssa, scheme_kind, scheme_type)
            cast_op.res.name_hint = f"{fn_arg.name}_kind_cast"
            kind_cast_ops.append(cast_op)
            data_ops[fn_arg.name] = cast_op  # scheme call uses the temp

            intent = fn_arg.getAttr("intent") if fn_arg.hasAttr("intent") else "in"
            if intent in ("inout", "out"):
                kind_writeback_pairs.append((cast_op.res, block_arg_ssa, host_kind))

        # Unit conversion — same pattern as kind conversion.
        # For inout/in: pre-convert host units → scheme units before the call.
        # For out:      just allocate a temp (scheme writes into it); no pre-convert.
        # Write-back:   convert scheme units → host units after the call (inout/out).
        # Must be built here (before call_ops) so data_ops is updated in time.
        unit_convert_ops: list = []
        unit_writeback_pairs: list = []  # (conv_res, orig_dest, to_host_expr)
        for idx, fn_arg in enumerate(input_arg_list):
            if not fn_arg.hasAttr("model_var_unit_mismatch"):
                continue
            scheme_units, host_units = fn_arg.getAttr("model_var_unit_mismatch").split(":", 1)
            to_scheme_expr, to_host_expr = UNIT_CONVERSIONS[(scheme_units, host_units)]

            block_arg_ssa = new_block.args[idx]
            arg_type = TypeConversions.convert(
                fn_arg.getAttr("type"),
                fn_arg.getAttr("kind") if fn_arg.hasAttr("kind") else None,
                _arg_dims(fn_arg),
            )

            intent = fn_arg.getAttr("intent") if fn_arg.hasAttr("intent") else "in"
            # Pass empty string for intent=out so only the allocation is emitted
            pre_expr = "" if intent == "out" else to_scheme_expr

            conv_op = UnitConvertOp(block_arg_ssa, pre_expr, arg_type)
            conv_op.res.name_hint = f"{fn_arg.name}_unit_conv"
            unit_convert_ops.append(conv_op)
            data_ops[fn_arg.name] = conv_op

            if intent in ("inout", "out"):
                unit_writeback_pairs.append((conv_op.res, block_arg_ssa, to_host_expr))

        alloc_ops = {}
        # Allocate local storage for each output-only argument
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

        # errflg and errmsg must always be present regardless of whether scheme
        # functions are called (e.g. when tgt_subroutine_postfix is None)
        if "errflg" not in data_ops:
            alloc_op = memref.AllocaOp.get(
                TypeConversions.getBaseType("integer"), shape=[]
            )
            alloc_op.memref.name_hint = "errflg"
            alloc_ops["errflg"] = alloc_op
            data_ops["errflg"] = alloc_op
        if "errmsg" not in data_ops:
            alloc_op = memref.AllocaOp.get(
                TypeConversions.getBaseType("character"), shape=[512]
            )
            alloc_op.memref.name_hint = "errmsg"
            alloc_ops["errmsg"] = alloc_op
            data_ops["errmsg"] = alloc_op

        ncol_compute_ops = []
        # The synthetic col_start/col_end args always carry these names — the host
        # provides loop bounds under horizontal_loop_begin/end standard names and
        # _make_col_arg above fixes the local names to col_start/col_end.
        if physics_mode and "col_start" in data_ops and "col_end" in data_ops:
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
            # Also map the original ncol_meta arg name in case it differs from "ncol"
            # (e.g. 'nbox' when processing a single group whose only loop-extent arg
            # was renamed to col_start/col_end in input_arg_list).
            if ncol_meta.name != "ncol":
                data_ops[ncol_meta.name] = ncol_alloc
            # Pre-create a lower-bound-1 alloca for use in promoted scheme slices.
            # Block-arg arrays (e.g. temp_layer) are 1-based within the physics
            # function, so RankReducingSliceOp needs a constant 1 as the lower
            # bound.  It must live at function scope so the Fortran printer can
            # declare it before use inside the promotion loop.
            from xdsl_ccpp.transforms.util.typing import TypeConversions as _TC
            _ib = _TC.getBaseType("integer")
            lbound_one_alloc = memref.AllocaOp.get(_ib, shape=[])
            lbound_one_alloc.memref.name_hint = "ccpp_lbound_one"
            lbound_one_const = arith.ConstantOp.from_int_and_width(1, 32)
            lbound_one_store = memref.StoreOp.get(lbound_one_const, lbound_one_alloc, [])
            data_ops["ccpp_lbound_one"] = lbound_one_alloc
            ncol_compute_ops = [
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

        initialisation_ops = self.generateVariableInitialisations(data_ops)

        # Add framework-managed real arrays (advected/allocatable) to data_ops
        # as module-local variable references.  These variables are declared as
        # module-level allocatables by match_and_rewrite and are accessible in
        # all contained subroutines without being passed as arguments.
        # Refs are added in ALL lifecycle phases so scheme calls can find them.
        # When suite_model is provided, allocation is emitted in non-physics
        # (initialize) mode using full-domain dimensions.  In physics mode,
        # suite-owned arrays are never re-allocated.
        framework_ref_ops = []
        lazy_alloc_ops = []
        if framework_vars:
            for fw_arg in framework_vars.values():
                _fw_std_key = self._std_key(fw_arg)
                _scheme_dims = fw_arg.getAttr("dimensions") if fw_arg.hasAttr("dimensions") else 0

                # Determine the rank of the module-level variable.
                # SuiteVariableModel is authoritative; fall back to the scheme's
                # own declared rank when no model is provided.
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
                # Use the canonical suite-owned name (from the first writer) so the
                # Fortran emits the correct module variable name.  e.g. 'temp_inc'
                # in a _timestep_initialize scheme maps to module var 'temp_inc_set'.
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

                # In physics mode, apply (col_start:col_end) ArraySectionOp for
                # 1D vars whose first allocation dimension is horizontal.  Skip vars
                # dimensioned by non-horizontal dims (e.g. promote_pcnst(number_of_tracers))
                # and 2D+ vars (they are handled by RankReducingSliceOp in promotion loops).
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

                # Only emit LazyAllocOp in init/register phases — suite-owned vars  Finalize, timestep,
                # and physics functions must not re-allocate — suite-owned vars are
                # already live from initialize.
                _is_alloc_phase = tgt_subroutine_postfix in ("_init", "_register")
                if _is_alloc_phase:
                    # Resolve dimension SSA values from data_ops via standard names,
                    # mapping horizontal_loop_extent → horizontal_dimension for allocation.
                    _alloc_dim_names = (
                        suite_model.alloc_dims(_fw_std_key)
                        if suite_model is not None
                        else (fw_arg.getAttr("dim_names")
                              if fw_arg.hasAttr("dim_names") else [])
                    )
                    dim_var_refs = []
                    for dim_std_name in _alloc_dim_names:
                        # Map horizontal_loop_extent → horizontal_dimension for allocation
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
                            # Try host MODULE tables (e.g. horizontal_dimension declared
                            # in a host module but not in any scheme arg table)
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

        # In non-physics (initialize) mode with a suite model, allocate ALL
        # suite-owned array variables, even those not referenced in this
        # function's arg tables.  This ensures that vars first written in _run
        # (e.g. to_promote) are allocated before any physics call.
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
                    # Try current arg tables first
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

        # Populate data_ops aliases so scheme calls using non-canonical local names
        # (e.g. 'nbox' when canonical is 'ncol', 'temp_layer' when canonical is 'temp')
        # resolve correctly.  This must run after ncol_alloc is set.
        if tgt_subroutine_postfix is not None:
            for _scheme_name in arg_tables:
                for _fn_arg in arg_tables[_scheme_name].getFunctionArguments():
                    _sk = self._std_key(_fn_arg)
                    _canonical = all_args.get(_sk)
                    if _canonical is not None and _fn_arg.name != _canonical.name:
                        if _fn_arg.name not in data_ops and _canonical.name in data_ops:
                            data_ops[_fn_arg.name] = data_ops[_canonical.name]

        call_ops = []
        fn_sigs = {}
        if tgt_subroutine_postfix is not None:
            # Determine which schemes are promoted (have is_promoted args).
            # Consecutive promoted schemes sharing the same promoted_dim are
            # grouped into a single loop for cache efficiency.
            non_promoted_calls: list = []
            promoted_groups: list = []  # list of (promoted_dim, [(scheme_name, arg_table)])
            current_group_dim: str | None = None
            current_group: list = []

            for scheme_name in arg_tables:
                tbl = arg_tables[scheme_name]
                if physics_mode and self._scheme_has_promoted_args(tbl):
                    # Find the promoted dimension for this scheme
                    pdim = next(
                        (
                            arg.getAttr("promoted_dim").lower()
                            for arg in tbl.getFunctionArguments()
                            if arg.hasAttr("is_promoted")
                            and arg.hasAttr("promoted_dim")
                        ),
                        None,
                    )
                    if pdim == current_group_dim:
                        current_group.append((scheme_name, tbl))
                    else:
                        if current_group:
                            promoted_groups.append((current_group_dim, current_group))
                        current_group = [(scheme_name, tbl)]
                        current_group_dim = pdim
                else:
                    # Non-promoted: flush any open group, then add directly
                    if current_group:
                        promoted_groups.append((current_group_dim, current_group))
                        current_group = []
                        current_group_dim = None
                    non_promoted_calls.append((scheme_name, tbl))

            if current_group:
                promoted_groups.append((current_group_dim, current_group))

            # Emit non-promoted scheme calls as before
            for scheme_name, tbl in non_promoted_calls:
                full_name = scheme_name + tgt_subroutine_postfix
                assert full_name in self.meta_fn_sigs
                call_ops += self.generateSchemeSubroutineCallOps(
                    full_name, tbl, data_ops,
                    scheme_overrides.get(scheme_name, {}),
                )
                if full_name not in fn_sigs:
                    fn_sigs[full_name] = self.meta_fn_sigs[full_name]

            # Emit one merged promotion loop per group of promoted schemes
            for group_dim, group_schemes in promoted_groups:
                # Find the loop upper bound from an existing integer arg
                upper_bound_ref = (
                    self._find_loop_upper_bound(group_dim, all_args, data_ops,
                                                framework_ref_ops=framework_ref_ops,
                                                suite_use_stubs=suite_use_stubs)
                    if group_dim
                    else None
                )
                if upper_bound_ref is None:
                    # Fallback: no explicit integer arg for this dimension —
                    # emit promoted calls without a loop (TODO: look up host module)
                    for scheme_name, tbl in group_schemes:
                        full_name = scheme_name + tgt_subroutine_postfix
                        assert full_name in self.meta_fn_sigs
                        call_ops += self.generateSchemeSubroutineCallOps(
                            full_name, tbl, data_ops,
                            scheme_overrides.get(scheme_name, {}),
                        )
                        if full_name not in fn_sigs:
                            fn_sigs[full_name] = self.meta_fn_sigs[full_name]
                    continue

                # Declare the loop index variable (alloca, type=integer)
                loop_var_alloc = memref.AllocaOp.get(
                    TypeConversions.getBaseType("integer"), shape=[]
                )
                loop_var_alloc.memref.name_hint = "vertical_layer_index"

                # Build body ops: scheme calls with RankReducingSliceOp refs
                body_ops_list: list = []
                for scheme_name, tbl in group_schemes:
                    full_name = scheme_name + tgt_subroutine_postfix
                    assert full_name in self.meta_fn_sigs
                    body_ops_list += self._build_promoted_call_ops(
                        full_name, tbl, data_ops,
                        loop_var_alloc.memref,   # pass the alloca memref
                        scheme_overrides.get(scheme_name, {}),
                    )
                    if full_name not in fn_sigs:
                        fn_sigs[full_name] = self.meta_fn_sigs[full_name]

                # PromotionLoopOp takes the alloca and the upper bound memref
                loop_op = PromotionLoopOp(
                    loop_var=loop_var_alloc.memref,
                    upper_bound=upper_bound_ref,   # the memref, printer reads name
                    body_ops=body_ops_list,
                )
                call_ops += [loop_var_alloc, loop_op]

        # Scalar inout block args are returned so the caller receives the updated value.
        # Array inout args are modified in-place through the host's buffer, so they
        # do not need to be returned — the host observes the changes directly.
        inout_return_vals = [
            data_ops[a.name]
            for a in input_arg_list
            if a.getAttr("intent") == "inout" and not _has_dims(a)
        ]
        alloc_return_vals = list(alloc_ops.values())

        errmsg_fn_name = (
            suite_description.attributes["name"] + generated_subroutine_posfix
        )
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
        new_func = func.FuncOp(
            suite_description.attributes["name"]
            + "_suite"
            + generated_subroutine_posfix,
            new_fn_type,
            body,
            visibility="public",
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

    @op_type_rewrite_pattern
    def match_and_rewrite(self, op: ccpp.SuiteOp, rewriter: PatternRewriter):
        """Generate the complete cap module for one ccpp.SuiteOp.

        For each of the five lifecycle subroutines (initialize, finalize,
        physics, timestep_initial, timestep_final) a func.FuncOp is built via
        generateSubroutineCall.  String constant globals and the mutable
        ccpp_suite_state global are created once and shared across all five.
        The resulting ops are wrapped in a named builtin.ModuleOp and inserted
        at the top level.
        """
        suite_description = self.suite_descriptions[op.suite_name.data]

        # Build SuiteVariableModel early — it is needed by all generateSubroutineCall
        # invocations to determine module-level ranks and allocation dimensions.
        suite_model = SuiteVariableModel(suite_description, self.meta_data, self._std_key)

        # Each tuple describes one cap subroutine:
        # (scheme postfix to call, generated name postfix, state to write, state to check)
        subroutine_specs = [
            ("_register", "_register", None, None),
            ("_init", "_initialize", "initialized", "uninitialized"),
            ("_finalize", "_finalize", "uninitialized", "initialized"),
            ("_timestep_initialize", "_timestep_initial", "in_time_step", "initialized"),
            ("_timestep_finalize", "_timestep_final", "initialized", "in_time_step"),
        ]

        generated_fns = []
        fn_sigs_by_name = {}
        check_strings_used = set()
        state_strings_used = set()

        suite_host_use_stubs: list = []  # host-module USE stubs needed by per-group fns

        # Generate one FuncOp per subroutine spec and accumulate unique string values
        for tgt_postfix, gen_postfix, state_string, check_string in subroutine_specs:
            fn, sigs, stubs = self.generateSubroutineCall(
                suite_description,
                tgt_postfix,
                gen_postfix,
                state_string=state_string,
                check_string=check_string,
                physics_mode=(tgt_postfix == "_run"),
                suite_model=suite_model,
            )
            generated_fns.append(fn)
            suite_host_use_stubs.extend(stubs)
            # Deduplicate scheme function signatures by name
            for sig in sigs:
                fn_sigs_by_name[sig.sym_name.data] = sig
            if check_string is not None:
                check_strings_used.add(check_string)
            if state_string is not None:
                state_strings_used.add(state_string)

        # Generate one physics function per XML group.
        for group in suite_description:
            group_name = group.attributes["name"]
            group_suite = XMLSuite(
                suite_description.attributes["name"],
                suite_description.attributes["version"],
            )
            group_suite.addChild(group)

            fn, sigs, stubs = self.generateSubroutineCall(
                group_suite,
                "_run",
                f"_{group_name}",
                state_string=None,
                check_string="in_time_step",
                physics_mode=True,
                group_name=group_name,
                suite_model=suite_model,
            )
            generated_fns.append(fn)
            suite_host_use_stubs.extend(stubs)
            for sig in sigs:
                fn_sigs_by_name[sig.sym_name.data] = sig
            check_strings_used.add("in_time_step")

        # Build a mapping from subroutine name → scheme module name so the
        # printer can emit 'use hello_scheme, only: hello_scheme_run' etc.
        # By CCPP convention the module name matches the scheme base name.
        scheme_entries = self.getSchemeNames(suite_description)
        sub_to_module: dict[str, str] = {}
        for scheme_name, _ in scheme_entries:
            for postfix in ("_run", "_init", "_finalize",
                            "_register", "_timestep_initialize", "_timestep_finalize",
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
            fn_sigs.append(cloned)

        # Emit USE-association stubs for DDT types referenced by scheme args.
        # The printer turns these into 'use <module>, only: <type_name>' lines.
        seen_type_imports: set[str] = set()
        type_import_globals = []
        primitive_types = {"real", "integer", "character", "logical", "complex"}
        for scheme_name, _ in scheme_entries:
            if scheme_name not in self.meta_data:
                continue
            for arg_table in self.meta_data[scheme_name].arg_tables.values():
                for arg in arg_table.getFunctionArguments():
                    if not arg.hasAttr("type"):
                        continue
                    arg_type = arg.getAttr("type")
                    if arg_type in primitive_types:
                        continue
                    if arg_type in seen_type_imports:
                        continue
                    mod = self.ddt_source_module.get(arg_type)
                    if mod is None:
                        continue
                    seen_type_imports.add(arg_type)
                    stub = llvm.GlobalOp(
                        llvm.LLVMArrayType.from_size_and_type(0, i8),
                        arg_type,
                        "internal",
                    )
                    stub.attributes["module"] = StringAttr(mod)
                    type_import_globals.append(stub)

        # Mutable global holding the current lifecycle state of the suite
        ccpp_suite_state_global = llvm.GlobalOp(
            llvm.LLVMArrayType.from_size_and_type(16, i8),
            "ccpp_suite_state",
            "internal",
            value=StringAttr("uninitialized"),
        )

        # One read-only global per unique state string (shared by check and assign ops)
        all_strings_used = check_strings_used | state_strings_used
        string_const_globals = [
            self.generateStringConstantGlobal(s) for s in sorted(all_strings_used)
        ]

        # Generate module-level declarations for all suite-owned variables.
        # interstitial_var_names is kept for SafeDeallocOp filtering below.
        # suite_model was already built above (before the subroutine_specs loop).
        interstitial_var_names: set[str] = set()  # lowercase
        allocatable_mod_vars = []
        for entry in suite_model.suite_owned_vars():
            if entry.is_ddt:
                # DDT interstitials (e.g. vmr_type) are declared at suite cap
                # module scope as non-allocatable scalars.  The suite functions
                # access them directly by name; the top-level cap never sees them.
                # Fortran derived-type declarations require type(...) syntax.
                allocatable_mod_vars.append(
                    ModuleVarOp(entry.local_name, f"type({entry.fortran_type})", rank=0)
                )
                interstitial_var_names.add(entry.local_name.lower())
                continue
            if entry.fortran_type == "real":
                kind = entry.kind if entry.kind else CCPP_KIND_PHYS
                ftn_type = f"real(kind={kind})"
            elif entry.fortran_type == "integer":
                ftn_type = "integer"
            else:
                ftn_type = entry.fortran_type
            allocatable_mod_vars.append(
                ModuleVarOp(entry.local_name, ftn_type, entry.rank)
            )
            interstitial_var_names.add(entry.local_name.lower())

        # SafeDeallocOp for each framework var goes into _timestep_final.
        # Inject them by patching the generated _timestep_final FuncOp's body.
        if allocatable_mod_vars:
            for fn in generated_fns:
                if not isa(fn, func.FuncOp):
                    continue
                if "_timestep_final" not in fn.sym_name.data:
                    continue
                if not fn.body.blocks:
                    continue
                block = fn.body.blocks[0]
                # Insert SafeDeallocOp before the ReturnOp
                ret_op = None
                for bop in block.ops:
                    if isa(bop, func.ReturnOp):
                        ret_op = bop
                        break
                if ret_op is not None:
                    from xdsl.rewriter import Rewriter, InsertPoint as IP
                    for var_decl in allocatable_mod_vars:
                        # Only deallocate arrays (rank>0); scalars are not allocatable.
                        # Skip is_interstitial vars — they persist from _init across
                        # all timesteps and should only be freed at _finalize.
                        if var_decl.rank.value.data > 0 and \
                                var_decl.var_name.data.lower() not in interstitial_var_names:
                            Rewriter.insert_op(
                                SafeDeallocOp(var_decl.var_name.data),
                                IP.before(ret_op),
                            )

        # Dedup host-module USE stubs (same var from multiple groups)
        seen_stubs: set = set()
        deduped_stubs = []
        for stub in suite_host_use_stubs:
            key = (stub.sym_name.data, stub.attributes.get("module").data
                   if stub.attributes.get("module") else "")
            if key not in seen_stubs:
                seen_stubs.add(key)
                deduped_stubs.append(stub)

        scheme_mod = builtin.ModuleOp(
            [ccpp_suite_state_global] + string_const_globals
            + type_import_globals + deduped_stubs + allocatable_mod_vars + generated_fns + fn_sigs,
            sym_name=builtin.StringAttr(op.suite_name.data + "_cap"),
        )

        rewriter.insert_op(
            scheme_mod, InsertPoint.at_start(self.top_level_module.body.block)
        )


@dataclass(frozen=True)
class SuiteCAP(ModulePass):
    """MLIR pass that generates CCPP cap subroutines from ccpp.SuiteOp nodes.

    Traverses the top-level module looking for the named 'ccpp' sub-module,
    collects metadata and scheme descriptions from it, then rewrites each
    ccpp.SuiteOp into a self-contained ModuleOp containing the five lifecycle
    cap subroutines.
    """

    name = "generate-suite-cap"

    def find_ccpp_module(self, ops):
        """Return the named 'ccpp' ModuleOp from the given op list, or None."""
        for op in ops:
            if (
                isa(op, builtin.ModuleOp)
                and op.sym_name is not None
                and op.sym_name.data == "ccpp"
            ):
                return op
        return None

    def apply(self, ctx: Context, op: builtin.ModuleOp) -> None:
        ccpp_mod = self.find_ccpp_module(op.body.block.ops)
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

        PatternRewriteWalker(
            GreedyRewritePatternApplier(
                [
                    GenerateSuiteSubroutine(
                        scheme_descriptions, meta_data_descriptions, meta_fn_sigs, op,
                        ddt_source_module=ddt_source_module,
                    ),
                ]
            ),
            apply_recursively=False,
        ).rewrite_module(op)
