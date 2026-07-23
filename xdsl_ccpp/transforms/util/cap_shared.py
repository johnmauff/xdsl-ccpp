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
    """Yield all XMLScheme leaves from a group, descending recursively into
    (possibly nested) XMLSubcycle nodes.

    Shared by ccpp_cap.py and suite_cap.py's getSchemeNames -- previously two
    independent copies of the same flattening logic. Nested subcycles are a
    real pattern -- see examples/var_compat/var_compatibility_suite.xml
    (ported from NCAR ccpp-framework's feature/capgen-v1), which nests three
    levels deep in one branch.

    suite_variable_model.py has a third, deliberately separate copy (duck-typed
    via "loop_count" in child.attributes rather than this isinstance check) --
    not unified here because that module's own docstring commits to zero
    xDSL/MLIR imports, and importing this function would pull in this module's
    xDSL-dependent imports transitively. See the comment at its call site.
    """
    for child in group:
        if isinstance(child, XMLSubcycle):
            yield from _iter_schemes(child)
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


# Alternate short-form spellings accepted alongside each canonical lifecycle
# postfix, for schemes following the atmospheric_physics/kessler_update
# convention (e.g. cld_ice.meta's bare "cld_ice_final" table). Single
# definition shared by lifecycle_cap.py's dispatch-lookup and suite_cap.py's
# arg-table lookup, so the two can't silently diverge on which alias forms
# they accept.
LIFECYCLE_POSTFIX_ALIASES: dict[str, str] = {
    "_timestep_initialize": "_timestep_init",
    "_timestep_finalize": "_timestep_final",
    "_finalize": "_final",
}

# Ordered (longest/most-specific first) so a longer suffix is never shadowed
# by a shorter one it contains as a trailing substring:
#   - '_timestep_finalize' before '_finalize' ('foo_timestep_finalize' ends
#     with both).
#   - '_timestep_init'/'_timestep_final' before '_init'/'_finalize'/'_final'
#     ('foo_timestep_init' ends with both '_timestep_init' and '_init';
#     'foo_timestep_final' ends with both '_timestep_final' and '_final').
# Canonical spellings ('_timestep_initialize'/'_timestep_finalize') come from
# ccpp_cap.py's lifecycle_specs; the short-form aliases ('_timestep_init'/
# '_timestep_final'/'_final') come from LIFECYCLE_POSTFIX_ALIASES above, for
# schemes following the atmospheric_physics/kessler_update convention.
_PHASE_SUFFIXES = (
    ("_timestep_initialize", "timestep_initial"),
    ("_timestep_finalize",   "timestep_final"),
    ("_timestep_init",       "timestep_initial"),
    ("_timestep_final",      "timestep_final"),
    ("_run",                 "run"),
    ("_init",                "initialize"),
    ("_finalize",            "finalize"),
    ("_final",               "finalize"),
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


def find_diverged_suite_vars(scheme_names, meta_data) -> frozenset:
    """Return the set of host-var names (model_var_name values) for which
    different schemes in `scheme_names` genuinely disagree about GPU
    residency treatment -- one wants `present` (scheme declares
    memory_space=device against a device-resident host var), another wants
    `update` (scheme leaves memory_space unset against that same
    device-resident host var).

    `model_var_memory_space` is a single, host-declared attribute -- the
    same value for every scheme referencing that host var, since it's
    propagated from the host's own metadata by generate-host-match, not the
    scheme's. `present` requires model=device; `copyin`/`copy`/`copyout`
    require model=host. These are mutually exclusive, so a host var can
    only ever diverge between present and update (both require
    model=device) -- never between either of those and the copy-family
    (which requires model=host). Divergence is therefore purely a question
    of whether every contributing scheme's own `memory_space` declaration
    agrees for a given model=device host var.

    Shared by GPUCcppCapPass (which excludes diverged vars from its
    whole-suite, cross-phase hoisting entirely -- see
    gpu_ccpp_cap_pass.py's _analyze_one_suite) and GPUDataPass (which routes
    them to per-scheme-call handling instead -- see gpu_data_pass.py), so
    the two passes can never disagree about which vars are diverged.
    """
    by_host_var: dict = {}  # host_var -> category ("present" | "update") -> set[scheme_name]

    for scheme_name in scheme_names:
        props = meta_data.get(scheme_name)
        if props is None:
            continue
        for table_name, table in props.arg_tables.items():
            if split_scheme_table_name(table_name) is None:
                continue
            for arg in table.getFunctionArguments():
                if not arg.hasAttr("model_var_name"):
                    continue
                model_space = (
                    arg.getAttr("model_var_memory_space")
                    if arg.hasAttr("model_var_memory_space")
                    else "host"
                )
                if model_space != "device":
                    continue
                scheme_space = (
                    arg.getAttr("memory_space") if arg.hasAttr("memory_space") else "host"
                )
                category = "present" if scheme_space == "device" else "update"
                host_var = arg.getAttr("model_var_name")
                by_host_var.setdefault(host_var, {}).setdefault(category, set()).add(scheme_name)

    return frozenset(
        host_var for host_var, categories in by_host_var.items() if len(categories) > 1
    )


def resolve_capscratch_cap_var_name(std_name: str, is_constituent: bool) -> "str | None":
    """Resolve a CapScratch-classified arg's standard_name to the shared
    cap-module-scope array it's backed by, or None if it isn't backed by one
    of the two known shared constituent arrays.

    Two cases: a direct match to FRAMEWORK_STD_NAME_TO_CAP_VAR (const/
    const_tend's own standard names, ccpp_constituents/
    ccpp_constituent_tendencies, mapping directly to
    lc_constituent_array/lc_const_tend); or a constituent-tendency scratch
    var (constituent=True, standard_name starting with tendency_of_, e.g.
    cld_liq_tend) -- a Fortran pointer slice into lc_const_tend, not a
    separately-allocated array, but backed by the same shared memory for
    residency purposes.

    Single source of truth for this resolution, shared by ccpp_cap.py's
    _build_cap_var_map (building the array/allocate mechanics) and this
    module's find_diverged_capscratch_vars (detecting per-scheme residency
    disagreement for the same shared array) -- so the two can never
    disagree about which cap var a given arg resolves to.
    """
    std_name = std_name.lower()
    if std_name in FRAMEWORK_STD_NAME_TO_CAP_VAR:
        return FRAMEWORK_STD_NAME_TO_CAP_VAR[std_name]
    if is_constituent and std_name.startswith("tendency_of_"):
        return "lc_const_tend"
    return None


def find_diverged_capscratch_vars(scheme_names, meta_data) -> frozenset:
    """Return the set of cap var names (e.g. lc_const_tend,
    lc_constituent_array) for which different schemes in scheme_names
    genuinely disagree about GPU residency treatment -- one scheme declares
    memory_space=device on its own CapScratch-classified occurrence
    (wants present), another does not (wants update), for an arg resolving
    to the same shared cap var via resolve_capscratch_cap_var_name.

    Mirrors find_diverged_suite_vars exactly, substituting the CapScratch
    cap-var identity in place of a host-matched model_var_name/
    model_var_memory_space pair: since CapScratch args have no host match at
    all, there's no host-declared "model_var_memory_space" to consult --
    whether the shared array is device-resident at all is instead the OR
    across every contributing scheme's own memory_space declaration (the
    same computation ccpp_cap.py's _build_cap_var_map already performs for
    residency establishment). A cap var only shows up here when that OR is
    true (at least one scheme wants device) AND at least one other
    contributing scheme does not -- a genuine disagreement, not just "no
    one asked for residency".

    Consumed by gpu_data_pass.py, which routes these to per-scheme-call
    update self/update device handling instead of the blanket
    enter-once/exit-once whole-suite residency treatment every occurrence
    would otherwise get lumped into.
    """
    by_cap_var: dict = {}  # cap_var_name -> category ("present" | "update") -> set[scheme_name]

    for scheme_name in scheme_names:
        props = meta_data.get(scheme_name)
        if props is None:
            continue
        for table_name, table in props.arg_tables.items():
            if split_scheme_table_name(table_name) is None:
                continue
            for arg in table.getFunctionArguments():
                if (
                    not arg.hasAttr("ownership_kind")
                    or arg.getAttr("ownership_kind") != ArgOwnershipKind.CapScratch
                ):
                    continue
                if not arg.hasAttr("standard_name"):
                    continue
                cap_var = resolve_capscratch_cap_var_name(
                    arg.getAttr("standard_name"), arg.hasAttr("constituent")
                )
                if cap_var is None:
                    continue
                scheme_space = (
                    arg.getAttr("memory_space") if arg.hasAttr("memory_space") else "host"
                )
                category = "present" if scheme_space == "device" else "update"
                by_cap_var.setdefault(cap_var, {}).setdefault(category, set()).add(scheme_name)

    return frozenset(
        cap_var for cap_var, categories in by_cap_var.items() if len(categories) > 1
    )


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


def _build_ddt_resolution_maps(meta_data) -> "tuple[dict, dict]":
    """Build (ddt_instance_map, ddt_parent_map) from host/module/DDT metadata.

    ddt_instance_map: DDT type/table name -> (instance_var_name, table_name)
        for the module-level variable of that DDT type (e.g.
        "physics_state" -> ("phys_state", "physics_module")).
    ddt_parent_map: DDT type/table name -> [(member_var_name, parent_ddt_type), ...]
        for nested DDTs (a DDT type that is itself a member of another DDT).

    Pure read of meta_data -- no IR ops created, no side effects. Shared by
    run_dispatch.py (resolving a DDT member's actual Fortran instance
    variable when building its HostVarRefOp) and gpu_ccpp_cap_pass.py
    (resolving the same instance variable so its lifetime-tracking dicts key
    on the same identity a HostVarRefOp actually carries -- see
    _resolve_host_var_key below).
    """
    ddt_type_names = {
        tbl_name
        for tbl_name, props in meta_data.items()
        if props.getAttr("type") == CCPPType.DDT
    }
    ddt_instance_map: dict = {}
    for tbl_name, props in meta_data.items():
        if props.getAttr("type") not in (CCPPType.MODULE, CCPPType.HOST):
            continue
        if tbl_name not in props.arg_tables:
            continue
        for var in props.getArgTable(tbl_name).getFunctionArguments():
            if var.hasAttr("type"):
                var_type = var.getAttr("type")
                if var_type in ddt_type_names:
                    ddt_instance_map[var_type] = (var.name, tbl_name)

    ddt_parent_map: dict = {}
    for tbl_name, props in meta_data.items():
        if props.getAttr("type") != CCPPType.DDT:
            continue
        if tbl_name not in props.arg_tables:
            continue
        for var in props.getArgTable(tbl_name).getFunctionArguments():
            if var.hasAttr("type"):
                child_type = var.getAttr("type")
                if child_type in ddt_type_names:
                    ddt_parent_map.setdefault(child_type, []).append(
                        (var.name, tbl_name)
                    )

    return ddt_instance_map, ddt_parent_map


def _resolve_ddt_access_path(
    ddt_type_name: str,
    ddt_instance_map: dict,
    ddt_parent_map: dict,
    _depth: int = 0,
) -> "tuple[str, str, str] | None":
    """Resolve a DDT type name to (instance_var, instance_module, path_prefix).

    For a type that has a direct module-level instance, path_prefix is "".
    For a nested DDT — e.g. type B is a member of type A, and A has a
    module-level instance — path_prefix is "b_member%" so the full Fortran
    accessor becomes ``instance_var%path_prefix%leaf_member``
    (e.g. ``phys_state%rad%temperature``).

    Returns None when no reachable module-level instance exists.
    The depth limit guards against circular DDT type definitions.
    """
    if _depth > 8:
        return None
    if ddt_type_name in ddt_instance_map:
        instance_var, instance_module = ddt_instance_map[ddt_type_name]
        return instance_var, instance_module, ""
    for member_var_name, parent_ddt_type in ddt_parent_map.get(ddt_type_name, []):
        result = _resolve_ddt_access_path(
            parent_ddt_type, ddt_instance_map, ddt_parent_map, _depth + 1
        )
        if result is not None:
            instance_var, instance_module, parent_prefix = result
            return instance_var, instance_module, parent_prefix + member_var_name + "%"
    return None


def _resolve_member_subscripts(member_name: str, host_var_map: dict) -> tuple:
    """Resolve standard_name tokens in a DDT member subscript to local var names.

    For 'q(:,:,index_of_water_vapor_specific_humidity)' with a host_var_map that
    maps the standard_name to ('index_qv', 'test_host_mod'), returns
    ('q(:,:,index_qv)', [('index_qv', 'test_host_mod')]).

    Bare colons and integer literals are passed through unchanged.
    """
    paren = member_name.find("(")
    if paren < 0:
        return member_name, []
    base = member_name[:paren]
    subscript = member_name[paren + 1: member_name.rfind(")")]
    resolved_tokens = []
    sub_vars = []
    for token in subscript.split(","):
        t = token.strip()
        if t == ":" or t.isdigit():
            resolved_tokens.append(t)
        else:
            t_lower = t.lower()
            if t_lower in host_var_map:
                local_name, module_name = host_var_map[t_lower]
                resolved_tokens.append(local_name)
                sub_vars.append((local_name, module_name))
            else:
                resolved_tokens.append(t)
    return f"{base}({', '.join(resolved_tokens)})", sub_vars


def _resolve_host_var_key(arg, ddt_instance_map: dict, ddt_parent_map: dict, host_var_map: dict) -> str:
    """Identity key for a host-matched ArgumentOp, matching exactly what the
    real HostVarRefOp built for the same host var carries.

    For a plain host var, this is just its bare model_var_name, unchanged.
    For a DDT member (model_var_is_ddt set), model_module_name is the DDT
    TYPE table's name, not the actual Fortran instance variable -- this
    resolves that type name to its module-level instance (following nested
    DDTs via _resolve_ddt_access_path) and any array-section subscript
    tokens (via _resolve_member_subscripts), returning
    "{instance_var}%{resolved_member}" -- exactly what run_dispatch.py's own
    HostVarRefOp construction produces (var_name=instance_var,
    member_name=resolved_member) and what print_ftn.py prints
    (var_name%member_name). Any code that needs to recognize "is this
    HostVarRefOp the same host var as this metadata arg" must compare
    against this key, not the bare model_var_name -- see
    gpu_ccpp_cap_pass.py's _ref_key, its IR-side counterpart.

    Falls back to the bare model_var_name if no module-level instance is
    reachable (matches run_dispatch.py's own soft-fail behavior for this
    case -- should not happen for an arg host_var_match_pass already
    accepted as DDT-matched).
    """
    host_var = arg.getAttr("model_var_name")
    if not arg.hasAttr("model_var_is_ddt"):
        return host_var
    ddt_type_name = arg.getAttr("model_module_name")
    result = _resolve_ddt_access_path(ddt_type_name, ddt_instance_map, ddt_parent_map)
    if result is None:
        return host_var
    instance_var, _instance_module, path_prefix = result
    resolved_member, _sub_vars = _resolve_member_subscripts(path_prefix + host_var, host_var_map)
    return f"{instance_var}%{resolved_member}"


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
            # Reads the durable ownership classification (generate-arg-
            # ownership) rather than re-deriving SuiteOwned-ness here.
            # Missing ownership_kind means the pipeline forgot
            # generate-arg-ownership -- raise rather than silently treating
            # the arg as not-framework-managed, which would let it leak into
            # the lifecycle return signature instead of failing obviously.
            if not fn_arg.hasAttr("ownership_kind"):
                raise ValueError(
                    f"Arg '{fn_arg.name}' in scheme '{scheme_name}' has no "
                    f"ownership_kind set. generate-arg-ownership "
                    f"(ArgOwnershipPass) must run before generate-suite-cap "
                    f"-- check the pass pipeline."
                )
            is_framework_managed = (
                fn_arg.getAttr("ownership_kind") == ArgOwnershipKind.SuiteOwned
            )
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
    identical set independently, at the same early point ownership
    classification runs, before any suite's subroutine signature exists.
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

    The single source of truth for this ownership question -- suite_cap.py's
    SuiteOwned gate and ccpp_cap.py's HostMatched/CapScratch/Block split
    (independently (re-)computed heuristics, prior to Phase 7 Stage 3) both
    now read the result of this classification instead. Computed purely from
    this arg's own properties plus module-wide, meta_data-only lookups
    (host_var_map_lc, host_block_std_names, FRAMEWORK_STD_NAME_TO_CAP_VAR,
    and the static CCPP_FRAMEWORK_STD_NAMES/CCPP_ERROR_STD_NAMES sets) -- no
    dependency on any suite's already-built subroutine signature.

    Operates on the real ccpp.ArgumentOp (typed property access: is_interstitial,
    arg_type, dimensions, advected, allocatable, model_var_name, standard_name),
    not the CCPPArgument descriptor's generic hasAttr/getAttr interface --
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
