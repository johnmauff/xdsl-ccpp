"""Shared helpers used across ccpp_cap.py, cpp_interop.py, lifecycle_cap.py,
constituent_cap.py, run_dispatch.py, and suite_cap.py.

A neutral leaf module with no dependency on any of the cap-generation files,
so those files can freely import from here without creating an import cycle
(ccpp_cap.py calls into lifecycle_cap.py/constituent_cap.py/run_dispatch.py
directly, and all of them need these same helpers, which previously lived in
ccpp_cap.py itself).
"""

from xdsl.dialects import arith, llvm, memref, scf
from xdsl.dialects.builtin import StringAttr, i8

from xdsl_ccpp.dialects.ccpp import ArgOwnershipKind, ArgOwnershipOp
from xdsl_ccpp.dialects.ccpp_utils import WriteErrMsgOp
from xdsl_ccpp.transforms.util.ccpp_descriptors import CCPPType, XMLSubcycle
from xdsl_ccpp.transforms.util.typing import TypeConversions
from xdsl_ccpp.util.ccpp_conventions import (
    CCPP_ERROR_STD_NAMES,
    CCPP_FRAMEWORK_STD_NAMES,
)

# Known framework arrays promoted to a fixed cap-owned module variable name,
# rather than a freshly-allocated scratch var. Used directly by both
# ccpp_cap.py's _build_cap_var_map and classify_arg_ownership below -- a
# single definition, not two independently-maintained copies, so the two
# heuristics can't silently diverge on this list.
FRAMEWORK_STD_NAME_TO_CAP_VAR: dict = {
    "ccpp_constituents": "lc_constituent_array",
    "ccpp_constituent_tendencies": "lc_const_tend",
}

_CCPP_CONSTITUENT_MOD = "ccpp_constituent_prop_mod"

_CONSTITUENT_DDT_NAME = "ccpp_constituent_properties_t"

_DDT_PRIMITIVE_TYPES = frozenset({"real", "integer", "character", "logical", "complex"})


def _collect_ddt_use_stubs(arg_tables_iterable, ddt_source_module: dict, seen: "set | None" = None) -> list:
    """Return llvm.GlobalOp USE-association stubs for each DDT type referenced
    by args in the given arg tables.

    arg_tables_iterable yields CCPPArgumentTable objects already flattened to
    whatever scope the caller needs (every scheme across every suite, or just
    one suite's schemes). seen, if given, is mutated in place so a caller can
    dedupe across multiple calls; a fresh set is used per call otherwise,
    matching both existing call sites' behavior.

    Shared by ccpp_cap.py (`_generate_ccpp_cap_module`, scans all of
    `meta_data`) and suite_cap.py (`GenerateSuiteSubroutine._build_ddt_use_stubs`,
    scans one suite's `scheme_entries`) -- previously two independent, byte-
    identical implementations of this logic.
    """
    if seen is None:
        seen = set()
    stubs = []
    for arg_table in arg_tables_iterable:
        for arg in arg_table.getFunctionArguments():
            if not arg.hasAttr("type"):
                continue
            arg_type = arg.getAttr("type")
            if arg_type in _DDT_PRIMITIVE_TYPES or arg_type in seen:
                continue
            mod = ddt_source_module.get(arg_type)
            if mod is None:
                continue
            seen.add(arg_type)
            stub = llvm.GlobalOp(
                llvm.LLVMArrayType.from_size_and_type(0, i8),
                arg_type,
                "internal",
            )
            stub.attributes["module"] = StringAttr(mod)
            stubs.append(stub)
    return stubs


def _rank_of(mlir_type) -> int:
    """Return the rank (number of dimensions) of an xDSL type, 0 if it has no shape.

    Shared by ccpp_cap.py (`_build_cap_var_map`, computing a scratch var's
    allocation rank) and run_dispatch.py (`_build_run_dispatch_chain`,
    computing a cap-var array-section's colon count) -- previously two
    independent copies of the same `len(list(t.shape.data)) if hasattr(t,
    "shape") else 0` expression, used at two adjacent stages of the same
    cap-var pipeline (allocating the scratch var vs. referencing it at a
    call site).
    """
    return len(list(mlir_type.shape.data)) if hasattr(mlir_type, "shape") else 0


def _assert_call_arg_count_matches_signature(
    suite_callee: str, call_args: list, callee_input_names: list, callee_input_types: list
) -> None:
    """Raise ValueError if the generated call-arg count doesn't match the
    callee's declared input signature.

    Shared by lifecycle_cap.py and run_dispatch.py -- previously two
    independent copies of the same check-and-raise, with wording that had
    already started to diverge (run_dispatch.py's copy included a
    "Generated args:" debug line lifecycle_cap.py's didn't -- both now get
    it, since it's strictly more useful for debugging a mismatch and no test
    checks this exact string).
    """
    if len(call_args) != len(callee_input_types):
        raise ValueError(
            f"Signature mismatch for '{suite_callee}': "
            f"generated {len(call_args)} input arg(s) but callee expects "
            f"{len(callee_input_types)}.\n"
            f"  Callee inputs:   {callee_input_names}\n"
            f"  Generated args:  {[str(a) for a in call_args]}"
        )


def _iter_schemes(group):
    """Yield all XMLScheme leaves from a group, descending into XMLSubcycle nodes.

    Shared by ccpp_cap.py and suite_cap.py's getSchemeNames -- previously two
    independent copies of the same flattening logic, each only exercising the
    one-level-deep subcycle case (nested subcycles are untested repo-wide --
    see the refactor plan's backlog).

    suite_variable_model.py has a third, deliberately separate copy (duck-typed
    via "loop_count" in child.attributes rather than this isinstance check) --
    not unified here because that module's own docstring commits to zero
    xDSL/MLIR imports, and importing this function would pull in this module's
    xDSL-dependent imports transitively. See the comment at its call site.
    """
    for child in group:
        if isinstance(child, XMLSubcycle):
            yield from child
        else:
            yield child


def _build_no_suite_matched_false_ops(errmsg_dest, trim_suite_name_res, errflg_dest) -> list:
    """Build the innermost false-branch ops for the "no suite matched" fallback.

    Sets errmsg to "No suite named <name> found" and errflg to 1. Shared by
    run_dispatch.py (two call sites: _build_run_chain_preamble and
    _generate_suite_part_list_fn) and lifecycle_cap.py (one call site) --
    previously three independent copies of the same error sequence, which is
    exactly the failure shape that let a Phase 3a review fix land on two
    copies and miss the third (a one-word text fix applied to run_dispatch.py's
    two copies, initially missing lifecycle_cap.py's).
    """
    write_err = WriteErrMsgOp(
        errmsg_dest, trim_suite_name_res, "No suite named ", " found"
    )
    one_err = arith.ConstantOp.from_int_and_width(1, 32)
    store_errflg_err = memref.StoreOp.get(one_err, errflg_dest, [])
    return [write_err, one_err, store_errflg_err, scf.YieldOp()]


def _bare(name: str) -> str:
    """Strip __alloc, __opt, or __in suffix from an arg name hint to get the bare Fortran name."""
    if name.endswith("__alloc"):
        return name[:-7]
    if name.endswith("__opt"):
        return name[:-5]
    if name.endswith("__in"):
        return name[:-4]
    return name


# Ordered (longest/most-specific first) so a longer suffix is never shadowed
# by a shorter one it contains as a trailing substring:
#   - '_timestep_finalize' before '_finalize' ('foo_timestep_finalize' ends
#     with both).
#   - '_timestep_init'/'_timestep_final' before '_init'/'_finalize'
#     ('foo_timestep_init' ends with both '_timestep_init' and '_init').
# Canonical spellings ('_timestep_initialize'/'_timestep_finalize') come from
# ccpp_cap.py's lifecycle_specs; the short-form aliases ('_timestep_init'/
# '_timestep_final') come from lifecycle_cap.py's _lc_postfix_aliases, for
# schemes following the atmospheric_physics/kessler_update convention.
_PHASE_SUFFIXES = (
    ("_timestep_initialize", "timestep_initial"),
    ("_timestep_finalize",   "timestep_final"),
    ("_timestep_init",       "timestep_initial"),
    ("_timestep_final",      "timestep_final"),
    ("_run",                 "run"),
    ("_init",                "initialize"),
    ("_finalize",            "finalize"),
    ("_register",            "register"),
)


def split_scheme_table_name(table_name: str) -> "tuple[str, str] | None":
    """Split a scheme argument-table name into (scheme_base_name, phase).

    e.g. 'kessler_update_timestep_final' -> ('kessler_update', 'timestep_final')
         'hello_scheme_run'              -> ('hello_scheme', 'run')

    phase is one of 'register'/'initialize'/'finalize'/'timestep_initial'/
    'run'/'timestep_final' -- the same six lifecycle phases ccpp_cap.py's
    lifecycle_specs generates a dispatcher for. Returns None if table_name
    doesn't end with any known lifecycle suffix.
    """
    for suffix, phase in _PHASE_SUFFIXES:
        if table_name.endswith(suffix):
            return table_name[: -len(suffix)], phase
    return None


def _build_host_var_map(meta_data, include_host: bool = True) -> dict:
    """Build a standard_name → (var_name, table_name) map from host metadata.

    Args:
        meta_data:    descriptor dict from BuildMetaDataDescriptions.
        include_host: when True (default) includes both MODULE and HOST type
                      tables.  When False, only MODULE type tables are scanned.
                      HOST-type variables are ephemeral values passed directly
                      by the host caller; MODULE-type variables are accessible
                      via USE statements.

    Returns:
        dict mapping lowercase standard_name → (local_var_name, table_name).
    """
    table_types = (
        (CCPPType.MODULE, CCPPType.HOST) if include_host else (CCPPType.MODULE,)
    )
    result: dict = {}
    for tbl_name, props in meta_data.items():
        if props.getAttr("type") not in table_types:
            continue
        if tbl_name not in props.arg_tables:
            continue
        for var in props.getArgTable(tbl_name).getFunctionArguments():
            if var.hasAttr("standard_name"):
                result[var.getAttr("standard_name").lower()] = (var.name, tbl_name)
    return result


def _is_framework_managed(a) -> bool:
    """True for suite-cap-owned variables: interstitials of any type,
    and advected/allocatable real arrays."""
    if a.hasAttr("is_interstitial"):
        return True
    if a.getAttr("type") != "real":
        return False
    if not (a.hasAttr("dimensions") and a.getAttr("dimensions") > 0):
        return False
    return a.hasAttr("advected") or a.hasAttr("allocatable")


def _get_suite_lifecycle_ret_info(scheme_names, meta_data, table_postfix):
    """Return [(mlir_type, arg_name, standard_name)] for intent=out scalar args.

    Applies the same filters as suite_cap.py's ``output_arg_list`` so the
    returned types match the actual FuncOp return signature generated by the
    suite cap:
    - intent=out only
    - Scalar (dimensions = 0 or absent) — array outs are block args, not returns
    - Not allocatable — those become __alloc block args
    - Not interstitial — framework-managed vars are not suite cap outputs
    """
    all_out_args = {}
    for scheme_name in scheme_names:
        table_name = scheme_name + table_postfix
        if scheme_name not in meta_data:
            continue
        if table_name not in meta_data[scheme_name].arg_tables:
            continue
        arg_table = meta_data[scheme_name].getArgTable(table_name)
        for fn_arg in arg_table.getFunctionArguments():
            has_dims = fn_arg.hasAttr("dimensions") and fn_arg.getAttr("dimensions") > 0
            # _is_framework_managed's array-shaped branch requires dims > 0,
            # which the `not has_dims` filter below already excludes here — so
            # for every arg that can reach that filter, this call reduces to
            # exactly the is_interstitial check it used to hand-roll.
            is_framework_managed = _is_framework_managed(fn_arg)
            # Deduplicate by standard_name so different local names for the
            # same logical arg (e.g. errflg vs errcode for ccpp_error_code)
            # don't produce duplicate return types.
            _dedup_key = (
                fn_arg.getAttr("standard_name").lower()
                if fn_arg.hasAttr("standard_name")
                else fn_arg.name
            )
            if (
                fn_arg.getAttr("intent") == "out"
                and _dedup_key not in all_out_args
                and not has_dims
                and not fn_arg.hasAttr("allocatable")
                and not is_framework_managed
            ):
                all_out_args[_dedup_key] = fn_arg

    result = []
    for arg in all_out_args.values():
        mlir_type = TypeConversions.convert(
            arg.getAttr("type"),
            arg.getAttr("kind") if arg.hasAttr("kind") else None,
            0,
        )
        raw = arg.getAttr("standard_name") if arg.hasAttr("standard_name") else None
        std_name = raw.lower() if raw else None
        result.append((mlir_type, arg.name, std_name))
    return result


def _collect_host_block_std_names(meta_data) -> set:
    """Standard names declared in HOST-type (not MODULE-type) metadata tables --
    caller-provided-each-call values with no persisted host module storage, so
    they stay a genuine passthrough block argument rather than being promoted
    to a cap-owned module variable.

    Shared by ccpp_cap.py's _build_cap_var_map and classify_arg_ownership
    below -- previously computed inline only inside _build_cap_var_map; Stage 2
    of Phase 7 (full IR unification, see ccpp_cap_refactor_plan.md) needs the
    identical set independently, at the same early point _is_framework_managed
    already runs, before any suite's subroutine signature exists.
    """
    host_block_std: set = set()
    for tbl_name, props in meta_data.items():
        if props.getAttr("type") != CCPPType.HOST:
            continue
        if tbl_name not in props.arg_tables:
            continue
        for var in props.getArgTable(tbl_name).getFunctionArguments():
            if var.hasAttr("standard_name"):
                host_block_std.add(var.getAttr("standard_name").lower())
    return host_block_std


def classify_arg_ownership(arg_op, host_var_map_lc, host_block_std_names) -> ArgOwnershipOp:
    """Classify one ccpp.ArgumentOp into its ownership bucket (see
    ArgOwnershipKind in ccpp.py) -- does the cap own this arg, or does its
    data come from outside?

    Mirrors suite_cap.py's _is_framework_managed (the SuiteOwned gate) and
    ccpp_cap.py's _build_cap_var_map (the HostMatched/CapScratch/Block split),
    but computed purely from this arg's own properties plus module-wide,
    meta_data-only lookups (host_var_map_lc, host_block_std_names,
    FRAMEWORK_STD_NAME_TO_CAP_VAR, and the static CCPP_FRAMEWORK_STD_NAMES/
    CCPP_ERROR_STD_NAMES sets) -- no dependency on any suite's already-built
    subroutine signature, unlike _build_cap_var_map's current implementation
    (see the Phase 7 Stage 2 plan for why that dependency is an
    implementation artifact, not a real ordering requirement).

    Operates on the real ccpp.ArgumentOp (typed property access: is_interstitial,
    arg_type, dimensions, advected, allocatable, model_var_name, standard_name),
    not the CCPPArgument descriptor _is_framework_managed uses (hasAttr/getAttr) --
    the two representations expose the same underlying data differently.

    Returns a constructed, verified (verify() is called before returning)
    ArgOwnershipOp -- not inserted into the module. Callers
    (generate-arg-ownership) copy .ownership_kind onto the real
    ArgumentOp's own `ownership_kind` property, reusing the arg's existing
    `standard_name` rather than storing std_name a second time.
    """
    arg_name = arg_op.arg_name.data

    def _make(kind, std_name=None):
        ownership = ArgOwnershipOp(arg_name, kind, std_name=std_name)
        ownership.verify()
        return ownership

    is_suite_owned = arg_op.is_interstitial is not None or (
        arg_op.arg_type.data == "real"
        and arg_op.dimensions is not None
        and arg_op.dimensions.data > 0
        and (arg_op.advected is not None or arg_op.allocatable is not None)
    )
    if is_suite_owned:
        return _make(ArgOwnershipKind.SuiteOwned)

    std_name = arg_op.standard_name.data.lower() if arg_op.standard_name is not None else None

    if arg_op.model_var_name is not None:
        # HostVariableMatchPass only ever sets model_var_name when
        # standard_name is present (host_var_match_pass.py's match loop skips
        # any arg with no standard_name before it ever sets model_var_name),
        # so std_name is expected non-None here. Passed through as-is rather
        # than substituted -- if that invariant is ever broken elsewhere,
        # verify() should raise, not be silently masked by a wrong fallback.
        return _make(ArgOwnershipKind.HostMatched, std_name=std_name)

    if std_name is not None and std_name in FRAMEWORK_STD_NAME_TO_CAP_VAR:
        return _make(ArgOwnershipKind.CapScratch, std_name=std_name)

    if std_name is None or (
        std_name in CCPP_FRAMEWORK_STD_NAMES
        or std_name in CCPP_ERROR_STD_NAMES
        or std_name in host_block_std_names
        or std_name in host_var_map_lc
    ):
        return _make(ArgOwnershipKind.Block)

    return _make(ArgOwnershipKind.CapScratch, std_name=std_name)
