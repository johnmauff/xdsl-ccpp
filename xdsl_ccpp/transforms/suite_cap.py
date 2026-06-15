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
    ModuleVarOp,
    KeywordCallOp,
    LazyAllocOp,
    PromotionLoopOp,
    RankReducingSliceOp,
    SafeDeallocOp,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    BuildMetaDataDescriptions,
    BuildSchemeDescription,
    CCPPArgument,
    collect_ddt_source_modules,
)
from xdsl_ccpp.transforms.util.typing import TypeConversions
from xdsl_ccpp.util.ccpp_conventions import (
    CCPP_KIND_PHYS,
    CCPP_LOOP_BEGIN_STD_NAME,
    CCPP_LOOP_END_STD_NAME,
    CCPP_LOOP_EXTENT_STD_NAME,
    CCPP_HORIZ_DIM_STD_NAME,
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

    def _find_loop_upper_bound(self, promoted_dim: str, all_args, data_ops):
        """Find the SSA value to use as the promotion loop's upper bound.

        Searches all_args for an integer argument whose standard_name matches
        promoted_dim (e.g. 'vertical_layer_dimension' → 'lev').  Returns the
        corresponding data_ops entry, or None if not found.
        """
        for arg in all_args.values():
            if (
                arg.hasAttr("standard_name")
                and arg.getAttr("standard_name").lower() == promoted_dim.lower()
                and arg.getAttr("type") == "integer"
                and arg.name in data_ops
            ):
                return data_ops[arg.name]
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

        rr_slice_ops = []
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
                for dim in dim_names:
                    pattern += "R"
                    range_lowers.append(data_ops.get("col_start", loop_var_memref))
                    range_uppers.append(data_ops.get("col_end", loop_var_memref))
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
                rr_slice_ops.append(slice_op)
                promoted_data_ops[arg.name] = slice_op

        call_ops = self.generateSchemeSubroutineCallOps(
            subroutine_name, arg_table, promoted_data_ops, overrides or {}
        )
        return rr_slice_ops + call_ops

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
        """Emit ops that zero-initialise errflg at the start of a subroutine."""
        err_const = arith.ConstantOp.from_int_and_width(0, 32)

        store_op = memref.StoreOp.get(err_const, data_ops["errflg"], [])

        return [err_const, store_op]

    def generateSchemeSubroutineCallOps(
        self, subroutine_name, arg_table, data_ops, overrides=None
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
            if intent == "in" or intent == "inout":
                if not is_overridden:
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
                if not is_overridden:
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
        if overrides:
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
        std_name_alias: dict = {}  # alias local name → canonical local name
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

            # Collect unique args across all schemes, preserving first-seen order.
            # Also build a standard_name alias map so that two args with the same
            # standard_name but different local names (e.g. 'temp' and 'temp_layer'
            # both for potential_temperature) share the same data_ops SSA value.
            # This avoids Fortran aliasing when the host passes the same actual
            # array to both positions.
            seen_std_names: dict = {}  # lowercase std_name → canonical local name
            std_name_alias: dict = {}  # alias local name → canonical local name
            for scheme_name in arg_tables:
                for fn_arg in arg_tables[scheme_name].getFunctionArguments():
                    std_name = (
                        fn_arg.getAttr("standard_name").lower()
                        if fn_arg.hasAttr("standard_name")
                        else None
                    )
                    if fn_arg.name in all_args:
                        assert fn_arg.getAttr("type") == all_args[fn_arg.name].getAttr(
                            "type"
                        )
                    else:
                        all_args[fn_arg.name] = fn_arg
                        if std_name:
                            if std_name in seen_std_names:
                                # Same standard_name, different local name — record alias
                                std_name_alias[fn_arg.name] = seen_std_names[std_name]
                            else:
                                seen_std_names[std_name] = fn_arg.name

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

        def _is_framework_managed_real(a):
            """True for advected/allocatable/interstitial real args the suite cap owns."""
            if a.getAttr("type") != "real":
                return False
            # Interstitial scalars (dimensions=0) are also framework-managed
            if a.hasAttr("is_interstitial"):
                return True
            if not _has_dims(a):
                return False
            return a.hasAttr("advected") or a.hasAttr("allocatable")

        # Separate framework-managed args from regular args
        framework_vars = {
            a.name: a
            for a in all_args.values()
            if _is_framework_managed_real(a)
        }

        input_arg_list = [
            a
            for a in all_args.values()
            if (a.getAttr("intent") in ("in", "inout") or _has_dims(a))
            and a.name not in framework_vars
            and a.name not in std_name_alias  # aliases share the canonical block arg
        ]
        output_arg_list = [
            a
            for a in all_args.values()
            if a.getAttr("intent") == "out" and not _has_dims(a)
            and a.name not in framework_vars
            and a.name not in std_name_alias
        ]

        loop_ext_aliases: set = set()
        # Find the column-count arg by standard_name, not local name — different
        # schemes use 'ncol', 'foo', 'nbox', etc. for horizontal_loop_extent.
        _has_loop_extent = any(
            a.hasAttr("standard_name")
            and a.getAttr("standard_name").lower() == CCPP_LOOP_EXTENT_STD_NAME
            for a in input_arg_list
        )
        if physics_mode and _has_loop_extent:
            ncol_meta = next(
                a for a in input_arg_list
                if a.hasAttr("standard_name")
                and a.getAttr("standard_name").lower() == CCPP_LOOP_EXTENT_STD_NAME
            )
            ncol_idx = next(
                i for i, a in enumerate(input_arg_list)
                if a.hasAttr("standard_name")
                and a.getAttr("standard_name").lower() == CCPP_LOOP_EXTENT_STD_NAME
            )

            # Collect other args with the same standard_name — all are aliases for
            # the column count and should not become separate block args.
            loop_ext_aliases = {
                a.name
                for a in input_arg_list
                if a.name != ncol_meta.name
                and a.hasAttr("standard_name")
                and a.getAttr("standard_name").lower() == CCPP_LOOP_EXTENT_STD_NAME
            }

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
                + [
                    a
                    for a in input_arg_list[ncol_idx + 1 :]
                    if a.name not in loop_ext_aliases
                ]
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

        input_arg_types = [
            TypeConversions.convert(
                a.getAttr("type"),
                a.getAttr("kind") if a.hasAttr("kind") else None,
                _arg_dims(a),
            )
            for a in input_arg_list
        ]

        new_block = Block(arg_types=input_arg_types)

        data_ops = {}
        # Map each input argument name to its block argument SSA value.
        # Allocatable args get a __alloc suffix on the name_hint so the printer
        # can add the ALLOCATABLE attribute to the Fortran declaration.
        for idx, fn_arg in enumerate(input_arg_list):
            hint = fn_arg.name
            if fn_arg.hasAttr("allocatable"):
                hint = fn_arg.name + "__alloc"
            new_block.args[idx].name_hint = hint
            data_ops[fn_arg.name] = new_block.args[idx]


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
            for alias in loop_ext_aliases:
                data_ops[alias] = ncol_alloc
            ncol_compute_ops = [
                ncol_alloc,
                load_col_start,
                load_col_end,
                sub_op,
                one_const,
                add_op,
                store_ncol,
            ]

        initialisation_ops = self.generateVariableInitialisations(data_ops)

        # Add framework-managed real arrays (advected/allocatable) to data_ops
        # as module-local variable references.  These variables are declared as
        # module-level allocatables by match_and_rewrite and are accessible in
        # all contained subroutines without being passed as arguments.
        # Refs are added in ALL lifecycle phases so scheme calls can find them.
        # Lazy allocation (ensuring storage exists) is only emitted in physics
        # mode where ncol/lev are already in scope.
        # TODO: for _initialize, allocate before _init calls using host module dims.
        framework_ref_ops = []
        lazy_alloc_ops = []
        if framework_vars:
            for fw_arg in framework_vars.values():
                var_type = TypeConversions.convert(
                    fw_arg.getAttr("type"),
                    fw_arg.getAttr("kind") if fw_arg.hasAttr("kind") else None,
                    fw_arg.getAttr("dimensions") if fw_arg.hasAttr("dimensions") else 0,
                )
                ref_op = ccpp_utils.HostVarRefOp(fw_arg.name, "", var_type)
                ref_op.res.name_hint = fw_arg.name
                framework_ref_ops.append(ref_op)
                data_ops[fw_arg.name] = ref_op

                # In physics mode, 1D framework arrays are allocated at horizontal_dimension
                # scope but schemes receive a horizontal_loop_extent slice (col_begin:col_end).
                # Locate the loop-begin/end SSA values by standard_name since the
                # local arg names differ across suites (cols/cole vs col_start/col_end).
                _dims = fw_arg.getAttr("dimensions") if fw_arg.hasAttr("dimensions") else 0
                if physics_mode and _dims == 1:
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

                # Resolve dimension SSA values from data_ops via standard names
                dim_names = fw_arg.getAttr("dim_names") if fw_arg.hasAttr("dim_names") else []
                dim_var_refs = []
                for dim_std_name in dim_names:
                    # Find the arg in all_args whose standard_name matches (case-insensitive)
                    matching = next(
                        (a for a in all_args.values()
                         if a.hasAttr("standard_name")
                         and a.getAttr("standard_name").lower() == dim_std_name.lower()),
                        None,
                    )
                    if matching and matching.name in data_ops:
                        dim_var_refs.append(data_ops[matching.name])

                # Emit lazy allocation whenever dimension SSA values are available
                # (in-scope args include nbox/ncol in both _init and _run).
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

        # Resolve standard_name aliases now that all data_ops entries are final
        # (ncol_compute_ops, errflg/errmsg, and framework refs are all set).
        for alias_name, canonical_name in std_name_alias.items():
            if alias_name not in data_ops and canonical_name in data_ops:
                data_ops[alias_name] = data_ops[canonical_name]

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
                    self._find_loop_upper_bound(group_dim, all_args, data_ops)
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

        body_ops = (
            alloc_return_vals
            + initialisation_ops
            + ncol_compute_ops
            + framework_ref_ops
            + lazy_alloc_ops
            + check_ops
            + call_ops
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

        return new_func, list(fn_sigs.values())

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

        # Each tuple describes one cap subroutine:
        # (scheme postfix to call, generated name postfix, state to write, state to check)
        subroutine_specs = [
            ("_init", "_initialize", "initialized", "uninitialized"),
            ("_finalize", "_finalize", "uninitialized", "initialized"),
            ("_run", "_physics", None, "in_time_step"),
            (None, "_timestep_initial", "in_time_step", "initialized"),
            (None, "_timestep_final", "initialized", "in_time_step"),
        ]

        generated_fns = []
        fn_sigs_by_name = {}
        check_strings_used = set()
        state_strings_used = set()

        # Generate one FuncOp per subroutine spec and accumulate unique string values
        for tgt_postfix, gen_postfix, state_string, check_string in subroutine_specs:
            fn, sigs = self.generateSubroutineCall(
                suite_description,
                tgt_postfix,
                gen_postfix,
                state_string=state_string,
                check_string=check_string,
                physics_mode=(tgt_postfix == "_run"),
            )
            generated_fns.append(fn)
            # Deduplicate scheme function signatures by name
            for sig in sigs:
                fn_sigs_by_name[sig.sym_name.data] = sig
            if check_string is not None:
                check_strings_used.add(check_string)
            if state_string is not None:
                state_strings_used.add(state_string)

        # Build a mapping from subroutine name → scheme module name so the
        # printer can emit 'use hello_scheme, only: hello_scheme_run' etc.
        # By CCPP convention the module name matches the scheme base name.
        scheme_entries = self.getSchemeNames(suite_description)
        sub_to_module: dict[str, str] = {}
        for scheme_name, _ in scheme_entries:
            for postfix in ("_run", "_init", "_finalize",
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

        # Collect all framework-managed real arrays across all schemes.
        # These need module-level allocatable declarations so all lifecycle
        # subroutines can access them.
        # Dedup is case-insensitive: Fortran is case-insensitive, so O3 and o3
        # are the same variable even when different schemes use different cases.
        seen_fw_vars: set[str] = set()  # lowercase keys
        allocatable_mod_vars = []
        # Track is_interstitial vars separately: they persist from _init through
        # all _run calls and must NOT be deallocated in _timestep_final (only
        # advected/allocatable vars get refreshed each timestep).
        interstitial_var_names: set[str] = set()  # lowercase
        for scheme_name, _ in scheme_entries:
            if scheme_name not in self.meta_data:
                continue
            # Iterate all entry-point tables (e.g. _run, _init, _finalize)
            for arg_table in self.meta_data[scheme_name].arg_tables.values():
                for arg in arg_table.getFunctionArguments():
                    if arg.name.lower() in seen_fw_vars:
                        continue
                    if arg.getAttr("type") != "real":
                        continue
                    is_fw = (
                        arg.hasAttr("advected")
                        or arg.hasAttr("allocatable")
                        or arg.hasAttr("is_interstitial")
                    )
                    if not is_fw:
                        continue
                    seen_fw_vars.add(arg.name.lower())
                    if arg.hasAttr("is_interstitial"):
                        interstitial_var_names.add(arg.name.lower())
                    kind = arg.getAttr("kind") if arg.hasAttr("kind") else CCPP_KIND_PHYS
                    rank = arg.getAttr("dimensions") if arg.hasAttr("dimensions") else 0
                    allocatable_mod_vars.append(
                        ModuleVarOp(arg.name, f"real(kind={kind})", rank)
                    )

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

        scheme_mod = builtin.ModuleOp(
            [ccpp_suite_state_global] + string_const_globals
            + type_import_globals + allocatable_mod_vars + generated_fns + fn_sigs,
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
