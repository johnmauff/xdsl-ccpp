from dataclasses import dataclass

from xdsl.context import Context
from xdsl.dialects import arith, builtin, func, llvm, memref, scf
from xdsl.dialects.builtin import ArrayAttr, DictionaryAttr, StringAttr, i8
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
from xdsl_ccpp.dialects.ccpp_utils import KeywordCallOp
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    BuildMetaDataDescriptions,
    BuildSchemeDescription,
    CCPPArgument,
)
from xdsl_ccpp.transforms.util.typing import TypeConversions
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

    def __init__(self, suite_descriptions, meta_data, meta_fn_sigs, top_level_module):
        self.suite_descriptions = suite_descriptions
        self.meta_data = meta_data
        self.meta_fn_sigs = meta_fn_sigs
        self.top_level_module = top_level_module

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
            if intent == "out" or intent == "inout":
                if not is_overridden:
                    val = data_ops[arg.name]
                    expected_out_type = (
                        callee_out_types[out_idx]
                        if out_idx < len(callee_out_types)
                        else (
                            val.type
                            if isinstance(val, SSAValue)
                            else val.results[0].type
                        )
                    )
                    out_types.append(expected_out_type)
                    out_names.append(arg.name)
                    out_tracking.append(val)
                out_idx += 1

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

            # Collect unique args across all schemes, preserving first-seen order
            for scheme_name in arg_tables:
                for fn_arg in arg_tables[scheme_name].getFunctionArguments():
                    if fn_arg.name in all_args:
                        assert fn_arg.getAttr("type") == all_args[fn_arg.name].getAttr(
                            "type"
                        )
                    else:
                        all_args[fn_arg.name] = fn_arg

        # in/inout args become block arguments (input parameters to the cap subroutine).
        # out-only scalar args are allocated locally; out array args also become block
        # arguments because the host always owns the array buffer and we cannot
        # allocate a dynamic memref without knowing the extents at compile time.
        def _has_dims(a):
            return a.hasAttr("dimensions") and a.getAttr("dimensions") > 0

        input_arg_list = [
            a
            for a in all_args.values()
            if a.getAttr("intent") in ("in", "inout") or _has_dims(a)
        ]
        output_arg_list = [
            a
            for a in all_args.values()
            if a.getAttr("intent") == "out" and not _has_dims(a)
        ]

        loop_ext_aliases: set = set()
        if physics_mode and any(a.name == "ncol" for a in input_arg_list):
            ncol_meta = next(a for a in input_arg_list if a.name == "ncol")
            ncol_idx = next(i for i, a in enumerate(input_arg_list) if a.name == "ncol")

            # Collect other args sharing ncol's standard_name (e.g. 'nbox' in
            # temp_adjust_run also has standard_name = horizontal_loop_extent).
            # These are aliases for the column count and should not become block args.
            ncol_std_name = (
                ncol_meta.getAttr("standard_name")
                if ncol_meta.hasAttr("standard_name")
                else None
            )
            loop_ext_aliases = {
                a.name
                for a in input_arg_list
                if a.name != "ncol"
                and ncol_std_name
                and a.hasAttr("standard_name")
                and a.getAttr("standard_name") == ncol_std_name
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

        input_arg_types = [
            TypeConversions.convert(
                a.getAttr("type"),
                a.getAttr("kind") if a.hasAttr("kind") else None,
                a.getAttr("dimensions") if a.hasAttr("dimensions") else 0,
            )
            for a in input_arg_list
        ]

        new_block = Block(arg_types=input_arg_types)

        data_ops = {}
        # Map each input argument name to its block argument SSA value
        for idx, fn_arg in enumerate(input_arg_list):
            new_block.args[idx].name_hint = fn_arg.name
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

        call_ops = []
        fn_sigs = {}
        if tgt_subroutine_postfix is not None:
            # Emit a guarded call for each scheme that has this entry point (in suite order)
            for scheme_name in arg_tables:
                full_name = scheme_name + tgt_subroutine_postfix
                assert full_name in self.meta_fn_sigs
                call_ops += self.generateSchemeSubroutineCallOps(
                    full_name,
                    arg_tables[scheme_name],
                    data_ops,
                    scheme_overrides.get(scheme_name, {}),
                )
                if full_name not in fn_sigs:
                    fn_sigs[full_name] = self.meta_fn_sigs[full_name]

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

        fn_sigs = self.clone_func_defs(list(fn_sigs_by_name.values()))

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

        scheme_mod = builtin.ModuleOp(
            [ccpp_suite_state_global] + string_const_globals + generated_fns + fn_sigs,
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

        PatternRewriteWalker(
            GreedyRewritePatternApplier(
                [
                    GenerateSuiteSubroutine(
                        scheme_descriptions, meta_data_descriptions, meta_fn_sigs, op
                    ),
                ]
            ),
            apply_recursively=False,
        ).rewrite_module(op)
