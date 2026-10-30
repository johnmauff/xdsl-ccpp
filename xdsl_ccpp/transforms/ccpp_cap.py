import re
from dataclasses import dataclass

from xdsl.context import Context
from xdsl.dialects import arith, builtin, func, llvm, memref, scf
from xdsl.dialects.builtin import (
    DYNAMIC_INDEX,
    IndexType,
    IntegerAttr,
    StringAttr,
    UnitAttr,
    i1,
    i8,
)
from xdsl.ir import Block, Region
from xdsl.passes import ModulePass
from xdsl.pattern_rewriter import InsertPoint
from xdsl.rewriter import Rewriter
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects import ccpp
from xdsl_ccpp.dialects.ccpp_utils import (
    AccExitDataOp,
    AllocateOp,
    AssignOp,
    CallExprOp,
    DerivedType,
    HostVarRefOp,
    IndexExprOp,
    SetStringOp,
    StrCmpOp,
    StringLiteralExprOp,
    TrimOp,
    ValueExprOp,
)
from xdsl_ccpp.transforms.capgen_api import generate_capgen_api_wrappers
from xdsl_ccpp.transforms.constituent_cap import (
    _collect_constituent_info,
    _generate_constituent_api,
)
from xdsl_ccpp.transforms.lifecycle_cap import _generate_lifecycle_fn
from xdsl_ccpp.transforms.run_dispatch import (
    _generate_run_fn,
    _generate_suite_part_list_fn,
)
from xdsl_ccpp.transforms.util.cap_shared import (
    FRAMEWORK_STD_NAME_TO_CAP_VAR,
    SUITE_ARG_NAME,
    SUITE_FN_INFIX,
    _build_host_var_map,
    _build_no_suite_matched_false_ops,
    _collect_ddt_use_stubs,
    _get_suite_lifecycle_ret_info,
    _iter_schemes,
    _rank_of,
    _resolve_lifecycle_table_name,
    _scf_if,
    CapVarRef,
    arg_attr_values,
    derive_camel_case_name,
    fixed_interface_fn,
    framework_cap_var_ref,
    iter_arg_tables,
    resolve_capscratch_cap_var_name,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    BuildMetaDataDescriptions,
    BuildSchemeDescription,
    CCPPType,
    XMLSubcycle,
    collect_ddt_source_modules,
)
from xdsl_ccpp.transforms.util.ir_utils import find_ccpp_module
from xdsl_ccpp.transforms.util.typing import TypeConversions
from xdsl_ccpp.util.ccpp_conventions import (
    CCPP_ERRMSG_LEN,
    CCPP_ERRMSG_LOCAL,
    CCPP_ERRFLG_LOCAL,
    CCPP_ERROR_CODE,
    CCPP_ERROR_MESSAGE,
    CCPP_ERROR_STD_NAMES,
    CCPP_HORIZ_DIM_STD_NAME,
    CCPP_INSTANCE_NUMBER_STD_NAME,
    CCPP_LOOP_EXTENT_STD_NAME,
    CCPP_NUMBER_OF_INSTANCES_STD_NAME,
    CCPP_VERT_DIM_STD_NAME,
    name_local,
)


def _collect_public_suite_functions(ops):
    """Scan all named ModuleOps in ops and return a map of public function info.

    Returns:
        dict mapping function_name → (module_name, output_types,
        input_types, input_names, input_arg_attrs); input_arg_attrs holds
        each argument's suite_arg_attrs as plain values, and input_names
        come from them (SUITE_ARG_NAME) where recorded, else from the
        block arguments' name hints.
    """
    public_fns = {}
    for op in ops:
        if not (isa(op, builtin.ModuleOp) and op.sym_name is not None):
            continue
        mod_name = op.sym_name.data
        for child in op.body.block.ops:
            if (
                isa(child, func.FuncOp)
                and not child.is_declaration
                and child.sym_visibility is not None
                and child.sym_visibility.data == "public"
            ):
                attrs = arg_attr_values(child)
                public_fns[child.sym_name.data] = (
                    mod_name,
                    list(child.function_type.outputs),
                    list(child.function_type.inputs),
                    [a.get(SUITE_ARG_NAME, arg.name_hint)
                     for a, arg in zip(attrs, child.body.block.args)],
                    attrs,
                )
    return public_fns






@dataclass
class _CVArgInfo:
    """Per-bare-name info collected while scanning one group's schemes, for
    the CapScratch/framework-var promotion decision in _build_cap_var_map.

    Consolidates 5 previously-separate parallel dicts (all keyed by the
    same bare arg name, all populated in the same scan loop, always read
    back together at the same call sites below) into one dict of these.
    std_name/dim_names/
    ownership_kind keep "first occurrence wins" semantics (None means "not
    yet seen"); is_constituent/is_advected/needs_gpu are True once any occurrence sets
    them (never reset).
    """

    std_name: "str | None" = None
    dim_names: "list | None" = None
    is_constituent: bool = False
    is_advected: bool = False
    ownership_kind: object = None
    needs_gpu: bool = False


def _build_cap_var_map(
    meta_data, suite_descriptions, public_fns, instance_local_name: "str | None" = None,
) -> "tuple[dict, dict, list, dict]":
    """Build cap_var_map: interstitial DDT values returned from lifecycle.

    These need module-level storage in the cap so they persist between calls.
    Pre-populates cap_var_map for framework-managed arrays (ccpp_constituents,
    ccpp_constituent_tendencies) and scheme-scratch arrays with no host
    metadata match (e.g. tendency_of_cloud_liquid_dry_mixing_ratio) -- both
    are allocated at cap module scope so they never appear as physics_run
    block arguments.

    instance_local_name -- real capgen-v1's multi-instance model:
    when set, every cap var name this function resolves for a
    framework-mapped or scratch constituent array (lc_all_constituents,
    lc_constituent_array, lc_const_tend, or a scheme's own
    tendency_of_-scratch var) is wrapped as
    lc_instances(<instance_local_name>)%<name> -- matching
    constituent_cap.py's own per-instance bundle type -- instead of the
    bare module-var name (CapVarRef.instance).

    The HostMatched/CapScratch/Block membership decision below now reads
    the durable ownership classification (from generate-arg-ownership)
    instead of re-deriving it by re-scanning the suite's already-built
    public signature (public_fns) against host/framework/error
    standard-name exclusion sets. public_fns is still used to know
    *which* args are actually on the group's dummy signature at all
    (that population itself is suite_cap.py's own job) and to build the
    scratch-var's concrete allocation shape (rank, dims): that
    type-dependent construction stays here, downstream of both the
    classification and suite_cap.py's own concrete xDSL types.

    CapScratch GPU residency: memory_space=device on a CapScratch arg means
    xdsl_ccpp itself should establish device residency for whichever
    cap-module-scope array that arg resolves to -- unlike HostMatched
    present/update residency (backlog item scoped to HostMatched only),
    CapScratch args are pure framework-owned scratch memory with no host
    model to defer to. Tracked as a simple OR across every occurrence (any
    scheme/group asking for it is enough), same fix shape as
    suite_variable_model.py's Case 4 for SuiteOwned vars -- not gated by
    "first occurrence wins" the way the rest of this function's std_name
    dedup is, since memory_space is exactly the one thing that can
    legitimately differ per occurrence.

    Returns:
        (cap_var_map, host_var_map_lc, scratch_var_list, framework_var_residency):
          - cap_var_map: standard_name -> (CapVarRef, mlir_type, fortran_type_str)
          - host_var_map_lc: standard_name -> (var_name, table_name), MODULE tables only
          - scratch_var_list: [(var_name, rank, alloc_dim_std_names, const_std_name_or_None,
            needs_device_residency, base_cap_var_or_None)] -- one entry per
            distinct CapScratch scratch var (excluding ones that resolve
            directly to a shared framework var). A constituent view has
            const_std_name set and base_cap_var lc_constituent_array (a
            host-bound advected arg) or lc_const_tend (a tendency).
          - framework_var_residency: cap var name (e.g. "lc_constituent_array",
            "lc_const_tend") -> True if any contributing occurrence (direct
            framework-mapped arg, or a constituent-tendency scratch var
            resolving into it) asked for memory_space=device
    """
    cap_var_map: dict = {}
    # MODULE only: write-back targets (like num_model_times) live in MODULE
    # tables.  HOST-type tables are caller-provided interfaces, not modules.
    # Still returned for callers (e.g. run_dispatch.py's Host resolution);
    # no longer consulted for the CapScratch/Block decision below, which
    # ownership_kind already accounts for.
    host_var_map_lc = _build_host_var_map(meta_data, include_host=False)

    def _cv_ref(name: str) -> CapVarRef:
        """cap_var_map's reference to a cap var (a component of
        lc_instances(instance) when multi-instance) -- NOT used for
        framework_var_residency/scratch_var_list, which stay keyed/valued by
        the bare name; constituent_cap.py applies its own identical
        wrapping when it consumes those."""
        return CapVarRef(name, instance_local_name)

    scratch_var_list: list = []
    scratch_var_index: dict = {}  # std_name -> index into scratch_var_list
    framework_var_residency: dict = {}  # cap var name -> True
    # (suite-callee infix, scheme table postfix) per group phase. Only
    # constituent views (host-bound advected args) are taken from the phases
    # other than _run: they reach schemes the same way in every phase.
    _group_phases_cv = [
        ("_", "_run"),
        ("_init_", "_init"),
        ("_timestep_init_", "_timestep_initialize"),
        ("_timestep_final_", "_timestep_finalize"),
        ("_final_", "_finalize"),
    ]
    for _sn_cv, _sd_cv in suite_descriptions.items():
        for _grp_cv in _sd_cv:
            _grp_name_cv = _grp_cv.attributes["name"]
            _grp_schemes = [_s.attributes["name"] for _s in _iter_schemes(_grp_cv)]
            for _infix_cv, _postfix_cv in _group_phases_cv:
                _callee_cv = _sn_cv + SUITE_FN_INFIX + _infix_cv + _grp_name_cv
                if _callee_cv not in public_fns:
                    continue
                _, _, _ci_types, _ci_names, _ = public_fns[_callee_cv]
                _arg_info_cv: dict[str, _CVArgInfo] = {}
                for _scheme_cv in _grp_schemes:
                    _tbl_cv = _resolve_lifecycle_table_name(_scheme_cv, meta_data, _postfix_cv)
                    if _tbl_cv is None:
                        continue
                    for _fa_cv in meta_data[_scheme_cv].getArgTable(_tbl_cv).getFunctionArguments():
                        _info_cv = _arg_info_cv.setdefault(_fa_cv.name, _CVArgInfo())
                        if _info_cv.std_name is None and _fa_cv.hasAttr("standard_name"):
                            _info_cv.std_name = _fa_cv.getAttr("standard_name").lower()
                        if _info_cv.dim_names is None and _fa_cv.hasAttr("dim_names"):
                            _info_cv.dim_names = _fa_cv.getAttr("dim_names")
                        if _fa_cv.hasAttr("constituent"):
                            _info_cv.is_constituent = True
                        if _fa_cv.hasAttr("advected"):
                            _info_cv.is_advected = True
                        if _info_cv.ownership_kind is None and _fa_cv.hasAttr("ownership_kind"):
                            _info_cv.ownership_kind = _fa_cv.getAttr("ownership_kind")
                        if _fa_cv.hasAttr("memory_space") and _fa_cv.getAttr("memory_space") == "device":
                            _info_cv.needs_gpu = True
                for _an_cv, _at_cv in zip(_ci_names, _ci_types):
                    _info_cv = _arg_info_cv.get(_an_cv)
                    # Anything not classified CapScratch (HostMatched, Block, or
                    # unclassified) has nothing to promote here -- this single
                    # check replaces the old _matched_cv / CCPP_FRAMEWORK_STD_NAMES
                    # / CCPP_ERROR_STD_NAMES / host_block_std / host_var_map_lc
                    # exclusion-set checks, all folded into ownership_kind already.
                    if _info_cv is None or _info_cv.ownership_kind != ccpp.ArgOwnershipKind.CapScratch:
                        continue
                    if _postfix_cv != "_run" and not _info_cv.is_advected:
                        continue
                    _std_cv = _info_cv.std_name
                    if not _std_cv:
                        continue
                    _needs_gpu_cv = _info_cv.needs_gpu
                    _resolved_cap_var_cv = resolve_capscratch_cap_var_name(
                        _std_cv, _info_cv.is_constituent, _info_cv.is_advected
                    )
                    if _std_cv in FRAMEWORK_STD_NAME_TO_CAP_VAR:
                        if _std_cv not in cap_var_map:
                            cap_var_map[_std_cv] = (
                                framework_cap_var_ref(_std_cv, instance_local_name), None, None,
                            )
                        if _needs_gpu_cv and _resolved_cap_var_cv is not None:
                            framework_var_residency[_resolved_cap_var_cv] = True
                        continue
                    if _std_cv not in scratch_var_index:
                        # Unique per standard name: two schemes may use one
                        # local name for different variables.
                        _lc_cv = f"lc_{_an_cv}"
                        _taken_cv = {e[0] for e in scratch_var_list}
                        _n_cv = 1
                        while _lc_cv in _taken_cv:
                            _n_cv += 1
                            _lc_cv = f"lc_{_an_cv}{_n_cv}"
                        _rank_cv = _rank_of(_at_cv)
                        _dims_cv = _info_cv.dim_names or []
                        _alloc_cv = tuple(_d.lower() for _d in _dims_cv) or (
                            CCPP_HORIZ_DIM_STD_NAME, CCPP_VERT_DIM_STD_NAME,
                        )
                        # A constituent view (a host-bound advected arg, or a
                        # constituent tendency) is a pointer slice into its base
                        # array (_resolved_cap_var_cv), selected by the
                        # constituent's standard name; anything else is a
                        # separately allocated array.
                        if _resolved_cap_var_cv == "lc_const_tend":
                            _const_std_name = _std_cv[len("tendency_of_"):]
                        elif _resolved_cap_var_cv == "lc_constituent_array":
                            _const_std_name = _std_cv
                        else:
                            _const_std_name = None
                        cap_var_map[_std_cv] = (_cv_ref(_lc_cv), None, None)
                        scratch_var_index[_std_cv] = len(scratch_var_list)
                        scratch_var_list.append(
                            [_lc_cv, _rank_cv, _alloc_cv, _const_std_name, _needs_gpu_cv,
                             _resolved_cap_var_cv]
                        )
                        # A tendency view makes lc_const_tend (physics-owned)
                        # device-resident. A constituent view does not: the
                        # host model updates the constituents on the host, so
                        # their device copies are made around the scheme
                        # calls (generate-gpu-data), not for the cap's life.
                        if _const_std_name and _needs_gpu_cv and _resolved_cap_var_cv == "lc_const_tend":
                            framework_var_residency[_resolved_cap_var_cv] = True
                    elif _needs_gpu_cv:
                        # Repeat occurrence of an already-seen scratch var (e.g.
                        # referenced again from a later group/suite/phase) -- OR
                        # this occurrence's own memory_space into the existing
                        # entry instead of silently discarding it, same as the
                        # framework-mapped branch above.
                        _entry_cv = scratch_var_list[scratch_var_index[_std_cv]]
                        _entry_cv[4] = True
                        if _entry_cv[3] and _entry_cv[5] == "lc_const_tend":
                            framework_var_residency[_entry_cv[5]] = True

    # Built as mutable lists above (to allow in-place OR-updates on repeat
    # occurrences); returned as tuples to preserve the established
    # "scratch_var_list is a list of tuples" contract callers rely on.
    return cap_var_map, host_var_map_lc, [tuple(e) for e in scratch_var_list], framework_var_residency


def _inject_capscratch_gpu_exit(
    all_definitions, finalize_fn_name, framework_var_residency, scratch_var_list,
    instance_local_name: "str | None" = None,
):
    """Emit AccExitDataOp for CapScratch cap-module arrays whose enter-data copyin

    actually fired (CapScratch GPU residency backlog item), in the generated
    ``ccpp_final`` function.

    Unlike suite_cap.py's ``_inject_suite_owned_gpu_exit`` (per-suite
    ``_suite_finalize``), these arrays (``lc_constituent_array``,
    ``lc_const_tend``, and any generic CapScratch scratch array) are
    module-global, not suite-scoped -- the exit is unconditional, in the
    combined cap's own finalize function, not gated on any suite dispatch
    branch. Constituent-tendency scratch vars (``const_std_name`` set) are
    Fortran pointer slices into ``lc_const_tend`` -- already covered via
    ``framework_var_residency["lc_const_tend"]`` -- so only generic scratch
    vars need their own entry here.

    instance_local_name -- set for a multi-instance cap, whose arrays are
    components of lc_instances(<instance>) (constituent_cap.py), the same
    reference the matching AccEnterDataOp in initialize_constituents uses;
    the finalize function must then take that instance argument.
    """
    resident: dict = {
        name: 3 for name, needed in framework_var_residency.items() if needed
    }
    for lc_name, rank, _alloc_dims, cst_std, needs_gpu, _base in scratch_var_list:
        if needs_gpu and not cst_std:
            resident[lc_name] = rank

    if not resident:
        return

    for fn in all_definitions:
        if not isa(fn, func.FuncOp) or fn.sym_name.data != finalize_fn_name:
            continue
        if not fn.body.blocks:
            continue
        block = fn.body.blocks[0]
        ret_op = next((bop for bop in block.ops if isa(bop, func.ReturnOp)), None)
        if ret_op is None:
            continue
        if instance_local_name is not None and instance_local_name not in (
            a.get(SUITE_ARG_NAME) for a in arg_attr_values(fn)
        ):
            raise ValueError(
                f"{finalize_fn_name} has no '{instance_local_name}' argument "
                f"to select the lc_instances entry whose device-resident "
                f"arrays it must exit-data."
            )
        for var_name in sorted(resident):
            var_type = TypeConversions.convert("real", "kind_phys", resident[var_name])
            if instance_local_name is not None:
                ref_op = HostVarRefOp("lc_instances", "", var_type,
                                      member_path=var_name, index_expr=instance_local_name)
            else:
                ref_op = HostVarRefOp(var_name, "", var_type)
            Rewriter.insert_op(ref_op, InsertPoint.before(ret_op))
            Rewriter.insert_op(
                AccExitDataOp(delete=[ref_op.res]), InsertPoint.before(ret_op)
            )
        break


# Standard names truly internal to the framework for
# _build_suite_variables_fn's own variable-list purposes
# (horizontal_loop_extent only) -- the constituent array names are real
# physics arrays and must still appear in the list.
_SUITE_VARS_INTERNAL_STD_NAMES = frozenset({CCPP_LOOP_EXTENT_STD_NAME})

# Fortran-keyword/relational-operator tokens that can appear inside an
# `active = (...)` expression but are never themselves a referenced
# standard_name -- see _add_active_expr_referenced_names.
_ACTIVE_EXPR_KEYWORDS = frozenset({
    "and", "or", "not", "eqv", "neqv", "true", "false",
    # Fortran's dotted relational operators (.eq., .ne., .lt., .le., .gt.,
    # .ge.) tokenize as bare words once the surrounding dots are stripped
    # by the regex in _add_active_expr_referenced_names -- without these,
    # e.g. "active = (x .gt. 0)" would misidentify "gt" as a referenced
    # standard_name.
    "eq", "ne", "lt", "le", "gt", "ge",
})


def _collect_interstitial_and_unit_mismatch_names(ccpp_mod, scheme_names, host_std_names):
    """_build_suite_variables_fn Pass 1a/1b: collect every standard_name
    marked ``is_interstitial`` on any occurrence across this suite's own
    scheme tables, plus every ``state_variable=true`` standard_name where
    some scheme in the suite declares different units than the host.

    Pass 1a: host_var_match_pass marks the CONSUMER (_run) but not the
    PRODUCER (_init), so the full set is needed to exclude both sides of an
    intra-suite interstitial (e.g. tcld).

    Pass 1b: when a unit mismatch exists, the suite cap converts the value
    in-place (e.g. Pa->hPa) -- the host should not treat the returned value
    as a meaningful physics output.

    Returns (interstitial_std_names, state_var_unit_mismatch).
    """
    interstitial_std_names: set = set()
    state_var_unit_mismatch: set = set()
    for _tbl_op, arg_table_op in iter_arg_tables(
        ccpp_mod, table_type="scheme", table_name_in=scheme_names
    ):
        for arg_op in arg_table_op.body.ops:
            if not isa(arg_op, ccpp.ArgumentOp):
                continue
            if arg_op.properties.get("is_interstitial") is not None:
                sn_prop = arg_op.properties.get("standard_name")
                if sn_prop is not None:
                    interstitial_std_names.add(sn_prop.data.lower())
            if arg_op.properties.get("state_variable") is not None:
                sn_prop = arg_op.properties.get("standard_name")
                if sn_prop is not None:
                    _sn = sn_prop.data.lower()
                    _su = arg_op.properties.get("units")
                    _su_str = _su.data.lower() if _su is not None else None
                    _hu = host_std_names.get(_sn)
                    if (_su_str is not None and _hu is not None
                            and _su_str != _hu):
                        state_var_unit_mismatch.add(_sn)
    return interstitial_std_names, state_var_unit_mismatch


def _classify_scheme_args_io(
    ccpp_mod, scheme_names, host_std_names, protected_std_names,
    interstitial_std_names, state_var_unit_mismatch,
):
    """_build_suite_variables_fn Pass 2: build the input/output
    variable-name sets, and the set of standard_names referenced only as
    array dimensions, from every scheme arg in this suite.

    Filtering rules (applied per ArgumentOp):
    - Skip if standard_name belongs to ANY interstitial arg (producer or
      consumer)
    - Skip if standard_name is in _SUITE_VARS_INTERNAL_STD_NAMES
      (horizontal_loop_extent only)
    - Skip if standard_name is in protected_std_names (dimension params)
    - ccpp_error_code/ccpp_error_message always go to output-only
    - advected=.true. args go to both input and output regardless of intent
    - state_variable=true args go to both if scheme units == host units;
      if units differ (unit conversion needed), intent-based rules apply
    - All others go to input/output by declared intent

    Returns (input_vars, output_vars, all_dim_names).
    """
    input_vars: set = set()
    output_vars: set = set()
    all_dim_names: set = set()

    for _tbl_op, arg_table_op in iter_arg_tables(
        ccpp_mod, table_type="scheme", table_name_in=scheme_names
    ):
        for arg_op in arg_table_op.body.ops:
            if not isa(arg_op, ccpp.ArgumentOp):
                continue

            sn_prop = arg_op.properties.get("standard_name")
            if sn_prop is None:
                continue
            std_name = sn_prop.data.lower()

            # Collect dimension names for the post-scan sweep
            dim_names_prop = arg_op.properties.get("dim_names")
            if dim_names_prop is not None:
                for dn in dim_names_prop.data.split(","):
                    dn = dn.strip().lower()
                    # Skip bare colons and integer literals
                    if dn and dn[0].isalpha():
                        all_dim_names.add(dn)

            if std_name in interstitial_std_names:
                continue
            if std_name in _SUITE_VARS_INTERNAL_STD_NAMES:
                continue

            # An OPTIONAL CapScratch arg with no host match at all
            # and no recognized framework meaning (e.g.
            # var_compat's ncl_out/cloud_liquid_number_concentration
            # -- an optional intent=out array no host .meta
            # declares, resolved to a throwaway cap-owned scratch
            # variable) never actually reaches the host in either
            # direction, so it must not appear in the suite's
            # variable list at all. Recognized framework arrays
            # (ccpp_constituents, ccpp_constituent_tendencies --
            # also CapScratch, since no host ever declares them
            # either) are real physics arrays and must still
            # appear, so only exclude when std_name isn't one of
            # those known names.
            #
            # Require "optional" specifically (not just
            # CapScratch + unmatched): examples/advection's own
            # end-to-end FileCheck golden runs a deliberately
            # reduced pass list with no generate-host-match at
            # all (see DEVELOPERS.md's own caveat that these
            # manually-composed pass lists aren't a stand-in for
            # the real driver pipeline), so ownership_kind alone
            # is unreliable there -- e.g. cld_liq's tcld
            # (minimum_temperature_for_cloud_liquid, a genuine
            # intra-suite interstitial the real pipeline's
            # generate-host-match would mark and exclude via
            # interstitial_std_names instead) and cld_liq_tend
            # (tendency_of_cloud_liquid_dry_mixing_ratio,
            # constituent=True, _build_cap_var_map's own
            # docstring names this as an intentional CapScratch
            # example that must still appear here) both come out
            # CapScratch-and-unmatched in that reduced pipeline,
            # but neither is declared optional -- unlike
            # var_compat's ncl_out, which is. A mandatory
            # unmatched arg means the suite genuinely needs it
            # (interstitial, constituent, or otherwise); only an
            # optional one can be silently absent, which is
            # exactly what makes it safe to omit from this list.
            #
            # Also require host_std_names to be non-empty AND
            # missing this std_name -- e.g. a FileCheck-only
            # invocation with no --host-files at all (see
            # tests/filecheck/examples/end_to_end/
            # helloworld-xml.mlir, which deliberately omits
            # --host-files to exercise the scheme-only frontend
            # path) makes EVERY scheme var CapScratch regardless
            # of whether a real host would match it -- confirmed
            # via helloworld's own hello_world_mod.meta, which
            # genuinely does declare potential_temperature; only
            # this specific host-less invocation makes it look
            # unmatched. host_std_names (built from every
            # non-scheme table actually present in the module)
            # is empty in exactly that scenario, so guarding on
            # it non-empty distinguishes "no host files supplied
            # to this run" from "host files supplied, and this
            # var genuinely isn't in any of them" (var_compat's
            # real case).
            ownership_prop = arg_op.properties.get("ownership_kind")
            if (
                ownership_prop is not None
                and ownership_prop.data == ccpp.ArgOwnershipKind.CapScratch
                and std_name not in FRAMEWORK_STD_NAME_TO_CAP_VAR
                and arg_op.properties.get("optional") is not None
                and host_std_names
                and std_name not in host_std_names
            ):
                continue

            # Variables with a default_value that are not matched to a
            # host variable AND are not advected constituents are managed
            # internally by the cap and must not appear in the variable list.
            # Advected constituents (advected=true) have default_value as an
            # initial fill, but are still real physics arrays visible to the host.
            if (arg_op.properties.get("default_value") is not None
                    and arg_op.properties.get("model_var_name") is None
                    and arg_op.properties.get("advected") is None):
                continue

            # Error flags → output-only special case
            if std_name in CCPP_ERROR_STD_NAMES:
                output_vars.add(std_name)
                continue

            # intent: StringAttr when set
            intent_prop = arg_op.properties.get("intent")
            intent = intent_prop.data.lower() if intent_prop is not None else None

            if std_name in protected_std_names:
                # Protected vars are blocked from input, but a scheme
                # may still write one as output (e.g. constituent-index
                # arrays like test_banana_constituent_indices).
                if intent in ("out", "inout"):
                    output_vars.add(std_name)
                continue

            # Advected constituents go to both input and output.
            # state_variable=true args go to both ONLY when no scheme
            # in the suite uses different units than the host (unit
            # conversion would mean the suite cap rewrites the value
            # in-place, so the host should not treat the returned value
            # as a meaningful physics output in that case).
            if arg_op.properties.get("advected") is not None:
                input_vars.add(std_name)
                output_vars.add(std_name)
            elif arg_op.properties.get("state_variable") is not None:
                if std_name not in state_var_unit_mismatch:
                    input_vars.add(std_name)
                    output_vars.add(std_name)
                else:
                    if intent in ("in", "inout"):
                        input_vars.add(std_name)
                    if intent in ("out", "inout"):
                        output_vars.add(std_name)
            else:
                if intent in ("in", "inout"):
                    input_vars.add(std_name)
                if intent in ("out", "inout"):
                    output_vars.add(std_name)

    return input_vars, output_vars, all_dim_names


def _collect_dynamic_subcycle_std_names(nodes) -> set:
    """Recursively collect standard_names of dynamic (non-literal) subcycle
    loop counts within a group/subcycle node list.

    Helper for _add_dynamic_subcycle_input_names.
    """
    names: set = set()
    for child in nodes:
        if isinstance(child, XMLSubcycle):
            if not child.attributes["is_literal"]:
                names.add(child.attributes["loop_count"].lower())
            names |= _collect_dynamic_subcycle_std_names(child)
    return names


def _add_dynamic_subcycle_input_names(suite_desc, input_vars) -> None:
    """_build_suite_variables_fn Pass 2b: add dynamic (non-literal) subcycle
    loop-count standard names (e.g. var_compat's num_subcycles_for_effr) to
    input_vars, in place.

    These are suite-level values synthesized directly by suite_cap.py's
    _synthesize_dynamic_loop_count_args -- they never become a real
    scheme-table ArgumentOp anywhere (the synthesis only ever mutates
    suite_cap.py's own in-memory all_args dict, feeding that suite's
    generated subroutine signature), so _classify_scheme_args_io's own
    scheme-table scan can never discover them on its own. A host must
    genuinely supply this value regardless, so it belongs in the suite's
    own input/required variable list too.
    """
    for group in suite_desc:
        for dyn_std_name in _collect_dynamic_subcycle_std_names(group):
            if (
                dyn_std_name not in _SUITE_VARS_INTERNAL_STD_NAMES
                and dyn_std_name not in CCPP_ERROR_STD_NAMES
            ):
                input_vars.add(dyn_std_name)


def _add_active_expr_referenced_names(ccpp_mod, suite_descriptions, input_vars) -> None:
    """_build_suite_variables_fn Pass 2c: add standard_names referenced only
    inside an ``active = (...)`` conditional-presence expression on a
    HOST/MODULE/DDT variable to input_vars, in place.

    E.g. var_compat's test_host_data.meta declaring ``active = (flag_
    indicating_cloud_microphysics_has_ice)`` on the ``effri``/``nci`` DDT
    members. ``active`` is a real ArgumentOp property (ccpp.py) but no pass
    currently evaluates it as a conditional ("opt_arg's dead active
    property" backlog item) -- the flag it names is
    still a genuine value the host must supply, though, so it must appear in
    the suite's variable list even though it's never itself a scheme
    argument anywhere.

    Only scoped to modules with exactly one suite: this scan is
    host-metadata-wide (not filtered to tables this suite's own schemes
    actually match), which is only safe when there's just one suite in the
    module to attribute the match to. Confirmed via examples/capgen (the
    one example that generates two suites, ddt_suite and temp_suite, from a
    single invocation sharing one host_ftn/test_host_data.meta): that host
    file's own ``active = (index_of_water_vapor_specific_humidity > 0)``
    was incorrectly attributed to BOTH suites without this guard, even
    though nothing in temp_suite's own schemes ever references it. Properly
    scoping this to "tables the current suite's schemes actually match"
    would need a much larger cross-reference than this fix is scoped to
    justify -- skipping multi-suite modules entirely is the safe,
    conservative choice instead.
    """
    if len(suite_descriptions) != 1:
        return
    for _tbl_op, arg_table_op in iter_arg_tables(ccpp_mod):
        for arg_op in arg_table_op.body.ops:
            if not isa(arg_op, ccpp.ArgumentOp):
                continue
            active_prop = arg_op.properties.get("active")
            if active_prop is None:
                continue
            for tok in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", active_prop.data):
                tok_lower = tok.lower()
                if (tok_lower not in _ACTIVE_EXPR_KEYWORDS
                        and tok_lower not in _SUITE_VARS_INTERNAL_STD_NAMES
                        and tok_lower not in CCPP_ERROR_STD_NAMES):
                    input_vars.add(tok_lower)


def _add_dimension_only_names(
    all_dim_names, protected_std_names, interstitial_std_names,
    input_vars, output_vars,
) -> None:
    """_build_suite_variables_fn Pass 3: add dimension standard names not
    already covered by input_vars/output_vars to input_vars, in place.

    Picks up vars like number_of_ccpp_constituents that appear only as
    array dimension sizes, never as explicit scheme arguments.
    """
    for dim_name in all_dim_names:
        if (dim_name not in _SUITE_VARS_INTERNAL_STD_NAMES
                and dim_name not in protected_std_names
                and dim_name not in interstitial_std_names
                and dim_name not in input_vars
                and dim_name not in output_vars
                and dim_name not in CCPP_ERROR_STD_NAMES):
            input_vars.add(dim_name)


def _render_suite_variables_subroutine(suite_vars) -> func.FuncOp:
    """Build ccpp_physics_suite_variables from the per-suite (input, output,
    required) variable-name lists computed by _build_suite_variables_fn's
    passes.

    Its interface is fixed (hosts call it with errmsg/errflg positionally,
    before the optional input_vars/output_vars), so it is a
    fixed_interface_fn: errmsg/errflg are intent(out) block arguments, not
    returned values -- those would be printed after all the inputs."""
    suite_var_name_len = 36  # character length matching cm=36 in test driver

    char_base = TypeConversions.getBaseType("character")
    char_type = memref.MemRefType(char_base, [DYNAMIC_INDEX])
    logical_type = memref.MemRefType(i1, [])
    args = [
        ("suite_name", char_type, "in", ()),
        ("var_list", memref.MemRefType(char_type, []), "out", ()),
        ("errmsg", memref.MemRefType(char_base, [CCPP_ERRMSG_LEN]), "out", ()),
        ("errflg", memref.MemRefType(TypeConversions.getBaseType("integer"), []), "out", ()),
        ("input_vars", logical_type, "in", ("optional",)),
        ("output_vars", logical_type, "in", ("optional",)),
    ]
    do_input = memref.AllocaOp.get(i1, shape=[])
    name_local(do_input, "do_input")
    do_output = memref.AllocaOp.get(i1, shape=[])
    name_local(do_output, "do_output")

    def _const(value: int, width: int = 32):
        return arith.ConstantOp(IntegerAttr.from_int_and_width(value, width))

    def _flag(alloca):
        return ValueExprOp(alloca.memref, result_type=i1)

    def _not(cond):
        return arith.XOrIOp(cond, _const(1, 1))

    def _body(block_args) -> list:
        suite_name, var_list, errmsg, errflg, input_vars, output_vars = block_args

        def _var_list_ops(names: list) -> list:
            """allocate(var_list(n)) and one var_list(j) = '<name>' per name."""
            ops: list = [AllocateOp("var_list", dim_ops=[_const(len(names))])]
            for j, v in enumerate(names):
                ops.append(AssignOp(
                    lhs_op=IndexExprOp(ValueExprOp(var_list), [_const(j + 1)]),
                    rhs_op=StringLiteralExprOp(f"{v:<{suite_var_name_len}}"),
                ))
            return ops

        ops: list = [
            AssignOp(lhs_op=ValueExprOp(errflg), rhs_op=_const(0)),
            AssignOp(lhs_op=ValueExprOp(errmsg), rhs_op=StringLiteralExprOp("")),
            AssignOp(lhs_op=ValueExprOp(do_input.memref), rhs_op=_const(1, 1)),
            AssignOp(lhs_op=ValueExprOp(do_output.memref), rhs_op=_const(1, 1)),
        ]
        for flag, arg in ((do_input, input_vars), (do_output, output_vars)):
            ops += _scf_if(
                CallExprOp("present", [ValueExprOp(arg)], result_type=i1),
                [AssignOp(lhs_op=ValueExprOp(flag.memref), rhs_op=ValueExprOp(arg))],
            )

        # One branch per suite, built inside-out: the innermost else is the
        # "no suite matched" error, as in the dispatchers (run_dispatch.py).
        trim_suite_name = TrimOp(suite_name)
        current_false_ops = _build_no_suite_matched_false_ops(
            errmsg, trim_suite_name.res, errflg,
        )[:-1]
        for suite, (in_v, out_v, req_v) in reversed(list(suite_vars.items())):
            # input only / output only / required
            selected = _scf_if(
                arith.AndIOp(_flag(do_input), _not(_flag(do_output))),
                _var_list_ops(in_v),
                _scf_if(
                    arith.AndIOp(_not(_flag(do_input)), _flag(do_output)),
                    _var_list_ops(out_v),
                    _var_list_ops(req_v),
                ),
            )
            strcmp_op = StrCmpOp(trim_suite_name.res, literal=suite)
            current_false_ops = [
                strcmp_op,
                scf.IfOp(strcmp_op.res, [], [*selected, scf.YieldOp()],
                         [*current_false_ops, scf.YieldOp()]),
            ]
        return [*ops, trim_suite_name, *current_false_ops]

    return fixed_interface_fn(
        "ccpp_physics_suite_variables", args, _body, locals_=[do_input, do_output],
    )


@dataclass(frozen=True)
class CCPPCAP(ModulePass):
    """MLIR pass that generates a single combined CCPP physics cap dispatcher module.

    Runs after generate-suite-cap.  For all suites found in the ccpp module,
    generates a single named ModuleOp containing lifecycle dispatcher subroutines
    that use nested if/else chains on ``suite_name`` to dispatch to the appropriate
    suite cap subroutine (generated by generate-suite-cap).

    Output is one ModuleOp (e.g. ``test_host_ccpp_cap``) inserted into the
    top-level module alongside the suite cap modules.
    """

    name = "generate-ccpp-cap"

    # Optional override for the CamelCase host name prefix applied to all
    # generated lifecycle subroutines.  When absent, the prefix is derived
    # automatically from the first suite name (e.g. hello_world_suite → HelloWorld).
    host_name: str = ""

    # When True, generated lifecycle and run subroutines in the ccpp_cap module
    # use BIND(C, name='...') and ISO_C_BINDING-typed arguments so they can be
    # called from C++ / Kokkos host models.
    bind_c: bool = False

    # When True, also generate original capgen's host API (<host>_ccpp_physics_*
    # wrappers and the capgen constituent routines, as CAM-SIMA calls them) on
    # top of the capgen-v1 API (--capgen-api, formerly --cam-host).
    capgen_api: bool = False


    def _derive_camel_case_name(self, suite_name: str) -> str:
        """Convert a snake_case suite name to CamelCase, stripping any
        '_suite' suffix. Thin wrapper -- see cap_shared.py's
        derive_camel_case_name for the real (shared) implementation."""
        return derive_camel_case_name(suite_name)

    def _build_suite_variables_fn(self, suite_descriptions, ccpp_mod,
                                   host_std_names, protected_std_names) -> func.FuncOp:
        """Build the ccpp_physics_suite_variables subroutine for all suites.

        Scans the MLIR IR directly (ArgumentOp properties) rather than going
        through the descriptor layer, avoiding subtle descriptor-build issues.

        For each suite, computes its (input, output, required) variable-name
        lists via a sequence of pass-specific module-level helpers -- see
        each one's own docstring for its filtering rules:
          1. _collect_interstitial_and_unit_mismatch_names (Pass 1a/1b)
          2. _classify_scheme_args_io (Pass 2)
          3. _add_dynamic_subcycle_input_names (Pass 2b)
          4. _add_active_expr_referenced_names (Pass 2c)
          5. _add_dimension_only_names (Pass 3)
        then delegates the final Fortran text generation, unioned across all
        suites, to _render_suite_variables_subroutine.
        """
        suite_vars: dict = {}
        for suite_name, suite_desc in suite_descriptions.items():
            # Collect the set of scheme names belonging to this suite
            scheme_names: set = set()
            for group in suite_desc:
                for scheme in _iter_schemes(group):
                    scheme_names.add(scheme.attributes["name"])

            interstitial_std_names, state_var_unit_mismatch = (
                _collect_interstitial_and_unit_mismatch_names(
                    ccpp_mod, scheme_names, host_std_names,
                )
            )
            input_vars, output_vars, all_dim_names = _classify_scheme_args_io(
                ccpp_mod, scheme_names, host_std_names, protected_std_names,
                interstitial_std_names, state_var_unit_mismatch,
            )
            _add_dynamic_subcycle_input_names(suite_desc, input_vars)
            _add_active_expr_referenced_names(ccpp_mod, suite_descriptions, input_vars)
            _add_dimension_only_names(
                all_dim_names, protected_std_names, interstitial_std_names,
                input_vars, output_vars,
            )

            required_vars = input_vars | output_vars
            suite_vars[suite_name] = (
                sorted(input_vars),
                sorted(output_vars),
                sorted(required_vars),
            )

        return _render_suite_variables_subroutine(suite_vars)


    def _generate_ccpp_cap_module(self, suite_descriptions, meta_data, public_fns,
                                   ddt_source_module=None, protected_std_names=None,
                                   host_std_names=None, ccpp_mod=None):
        """Build a single combined CCPP cap ModuleOp for all suites.

        Generates one module whose lifecycle subroutines use nested if/else chains
        to dispatch to the appropriate suite cap subroutine.
        """
        all_suite_names = list(suite_descriptions.keys())

        camel_name = (
            self.host_name
            if self.host_name
            else self._derive_camel_case_name(all_suite_names[0])
        )

        # Module name uses the same CamelCase prefix as the subroutine names
        # so that 'module HelloWorld_ccpp_cap' matches 'use HelloWorld_ccpp_cap'
        # in host model files.  --host-name can still override when needed.
        mod_name = camel_name + "_ccpp_cap"

        char_base = TypeConversions.getBaseType("character")
        int_base = TypeConversions.getBaseType("integer")
        suite_name_type = memref.MemRefType(char_base, [DYNAMIC_INDEX])
        errmsg_type = memref.MemRefType(char_base, [CCPP_ERRMSG_LEN])
        errflg_type = memref.MemRefType(int_base, [])

        common = dict(
            suite_name_type=suite_name_type,
            errmsg_type=errmsg_type,
            errflg_type=errflg_type,
            char_base=char_base,
            int_base=int_base,
            public_fns=public_fns,
        )

        # Stage 5 of the vocabulary-resolution redesign: bare,
        # capgen-v1-style generic subroutine names (fn_name below is used
        # as-is, not appended to camel_name/host_name) -- the module itself
        # (mod_name above) is still host-prefixed, exactly matching real
        # capgen-v1's own convention (module <host>_ccpp_cap disambiguates
        # multiple host integrations; the subroutines inside don't need to).
        # capgen-v1 itself has eight lifecycle entry points (splitting what
        # this codebase calls "initialize" into ccpp_init/ccpp_physics_init,
        # and "finalize" into ccpp_physics_final/ccpp_final) -- deliberately
        # out of scope here: renaming these six to their closest capgen-v1
        # name is a naming cleanup, not a rewrite of the lifecycle model
        # itself.
        lifecycle_specs = [
            ("ccpp_register", "_register", f"{SUITE_FN_INFIX}_register", None),
            # ccpp_init/ccpp_final: table_postfix=None, not
            # "_init"/"_finalize" -- those postfixes would make the
            # branch below scan every scheme's own _init/_finalize arg
            # table via _get_suite_lifecycle_ret_info, which still finds
            # real entries (schemes still declare those tables; they just
            # aren't called from here anymore -- see suite_cap.py's
            # emit_scheme_calls). That produced a real arg-count mismatch
            # against the callee's own (now scheme-call-free) signature --
            # confirmed via a real regression while verifying this stage
            # against examples/ddthost. None skips straight to the same
            # fallback branch used whenever no scheme has a matching table
            # (e.g. ccpp_register's own "_register" postfix commonly hits
            # this same fallback in practice): read the callee's ACTUAL
            # signature straight from public_fns, which can't drift out of
            # sync with what suite_cap.py really generated.
            ("ccpp_init", None, f"{SUITE_FN_INFIX}_initialize", None),
            ("ccpp_final", None, f"{SUITE_FN_INFIX}_finalize", None),
            # Per-group dispatch — each group calls its own suite cap function.
            # ccpp_physics_run: the original, unchanged entry (table_postfix
            # None here means "_run" via _generate_run_fn's own default).
            # ccpp_physics_timestep_init and ccpp_physics_timestep_final
            # moved from the flat/minimal-signature form to match real capgen-v1's own
            # group-scoped entry points (a breaking signature change: both
            # now take the full physics signature, not just
            # suite_name/errmsg/errflg).
            ("ccpp_physics_run", None, f"{SUITE_FN_INFIX}_", "__per_group__"),
            ("ccpp_physics_timestep_init", "_timestep_initialize", f"{SUITE_FN_INFIX}_timestep_init_", "__per_group__"),
            ("ccpp_physics_timestep_final", "_timestep_finalize", f"{SUITE_FN_INFIX}_timestep_final_", "__per_group__"),
            # ccpp_physics_init/ccpp_physics_final: net new entry points, not
            # moved/renamed from an existing one the way
            # ccpp_physics_timestep_init/ccpp_physics_timestep_final were
            # above -- ccpp_init/ccpp_final above are a separate, UNCHANGED
            # pair, still flat and still present (real capgen-v1's own suite-level
            # <suite>_init/<suite>_final are framework-setup-only). These
            # own the scheme-level _init/_finalize calls instead (matching
            # real capgen-v1's own group-scoped ccpp_physics_init/
            # ccpp_physics_final) -- see suite_cap.py's emit_scheme_calls
            # for why ccpp_init/ccpp_final no longer emit those calls.
            ("ccpp_physics_init", "_init", f"{SUITE_FN_INFIX}_init_", "__per_group__"),
            ("ccpp_physics_final", "_finalize", f"{SUITE_FN_INFIX}_final_", "__per_group__"),
        ]

        all_globals: list = []
        all_definitions: list = []
        all_declarations: list = []
        # Maps fn_suffix → (FuncOp, canonical_to_std) so the CAM wrapper builder
        # can resolve each dispatcher block arg to its standard_name (from metadata)
        # and map that to the appropriate CAM Fortran expression — without hardcoding
        # local variable names.  canonical_to_std is {} for flat lifecycle fns whose
        # args are always the fixed CCPP protocol set (suite_name, errmsg, errflg).
        lifecycle_fns: dict = {}
        # Shared across ALL function calls (lifecycle AND run) to avoid duplicate GlobalOps.
        # Both lifecycle and run functions can reference the same host variables (e.g.
        # a DDT instance used in the run function may also appear in lifecycle functions).
        shared_seen_host_globals: set = set()

        # Real capgen-v1's multi-instance model: resolved once
        # for the whole host (instance_number/number_of_instances are
        # HOST-declared scalars, not suite-scoped), same lookup shape as
        # suite_cap.py's own _resolve_host_only_std_name -- scans every
        # non-scheme table (module/host/ddt) for the standard name. None for
        # a non-multi-instance host, in which case every downstream
        # constituent-API/cap-var-map consumer below takes its original,
        # unchanged codepath.
        # instance_local_name/ninstances_local_name form one paired contract
        # -- every downstream consumer (cap_var_map's lc_instances(instance)%
        # wrapping, constituent_cap.py's lc_instances bundle/allocation,
        # lifecycle_cap.py's LazyAllocOp guard) assumes BOTH are set or
        # NEITHER is. A host declaring only one of the two standard names
        # (unusual, but nothing stops a .meta file from doing it) would
        # otherwise enable multi-instance wrapping with no matching
        # allocation/signature support -- e.g. a literal "None" spliced into
        # a generated Fortran signature, or a reference to lc_instances that
        # is never declared. Caught by Copilot review on PR #77; normalize
        # to the pair here, once, so every downstream site's own "is this
        # multi-instance" check (instance_local_name is not None) stays a
        # reliable proxy for "both names are present."
        _host_var_map_all_for_instance = _build_host_var_map(meta_data, include_host=True)
        _instance_match = _host_var_map_all_for_instance.get(CCPP_INSTANCE_NUMBER_STD_NAME)
        _ninstances_match = _host_var_map_all_for_instance.get(CCPP_NUMBER_OF_INSTANCES_STD_NAME)
        if _instance_match is not None and _ninstances_match is not None:
            instance_local_name = _instance_match[0]
            ninstances_local_name = _ninstances_match[0]
        else:
            instance_local_name = None
            ninstances_local_name = None

        cap_var_map, host_var_map_lc, scratch_var_list, framework_var_residency = _build_cap_var_map(
            meta_data, suite_descriptions, public_fns, instance_local_name=instance_local_name,
        )

        # Detect the ccpp_info_t pattern: a HOST or CONTROL table contains a
        # variable with standard_name = host_standard_ccpp_type (e.g.
        # ddthost). When present, lifecycle and run functions accept a
        # single ccpp_info_t inout arg that bundles errmsg/errflg and (for
        # run) col_start/col_end. CONTROL is included alongside HOST since
        # the bundling variable itself is exactly as synthesized/call-site
        # as its own members are.
        ccpp_info_type = None
        ccpp_info_module_name = None
        for _tbl, _props in meta_data.items():
            if _props.getAttr("type") not in (CCPPType.HOST, CCPPType.CONTROL):
                continue
            if _tbl not in _props.arg_tables:
                continue
            for _var in _props.getArgTable(_tbl).getFunctionArguments():
                if (
                    _var.hasAttr("standard_name")
                    and _var.getAttr("standard_name").lower() == "host_standard_ccpp_type"
                    and _var.hasAttr("type")
                ):
                    _ddt_type_name = _var.getAttr("type")
                    _src = (ddt_source_module or {}).get(_ddt_type_name)
                    if _src:
                        ccpp_info_type = memref.MemRefType(
                            DerivedType(_ddt_type_name), []
                        )
                        ccpp_info_module_name = _src
                        # The USE stub for ccpp_info_t is emitted by the DDT
                        # type loop below (it scans all arg table types).
                    break
            if ccpp_info_type is not None:
                break

        for fn_suffix, table_postfix, callee_suffix, suite_part in lifecycle_specs:
            if suite_part is not None:
                # Run function: one dispatch entry per XML group, all pointing to
                # the combined _suite_physics callee.  This correctly maps each
                # group name (e.g. 'physics1', 'physics2') to the same combined
                # function while keeping per-group state intact at module scope.
                suite_run_entries = []
                for suite_name, suite_desc in suite_descriptions.items():
                    for group in suite_desc:
                        group_name = group.attributes["name"]
                        # Per-group callee: e.g. temp_suite_physics1
                        suite_callee = suite_name + callee_suffix + group_name
                        if suite_callee not in public_fns:
                            continue
                        # Only this group's scheme names — matches the per-group callee's signature
                        group_scheme_names = [
                            scheme.attributes["name"] for scheme in _iter_schemes(group)
                        ]
                        suite_run_entries.append(
                            (suite_name, group_name, suite_callee, group_scheme_names)
                        )

                if not suite_run_entries:
                    continue

                cap_fn, decls, host_global_ops, non_host_std_to_canonical = _generate_run_fn(
                    fn_name=fn_suffix,
                    suite_run_entries=suite_run_entries,
                    meta_data=meta_data,
                    cap_var_map=cap_var_map,
                    seen_host_globals=shared_seen_host_globals,
                    ccpp_info_type=ccpp_info_type,
                    ccpp_info_module=ccpp_info_module_name,
                    phase_postfix=table_postfix or "_run",
                    **common,
                )
                all_globals.extend(host_global_ops)
                all_declarations.extend(decls)
                # Invert to canonical_arg_name → std_name for the CAM wrapper.
                # Add errmsg/errflg: they are always the last block args of run-style
                # fns but not tracked in non_host_std_to_canonical.
                _canonical_to_std = {v: k for k, v in non_host_std_to_canonical.items()}
                _canonical_to_std[CCPP_ERRMSG_LOCAL] = CCPP_ERROR_MESSAGE
                _canonical_to_std[CCPP_ERRFLG_LOCAL] = CCPP_ERROR_CODE
                _lc_fn_std_map = _canonical_to_std
            else:
                # Lifecycle function: collect per-suite callee info
                suite_entries = []
                for suite_name, suite_desc in suite_descriptions.items():
                    suite_callee = suite_name + callee_suffix
                    if suite_callee not in public_fns:
                        continue
                    scheme_names = [
                        scheme.attributes["name"]
                        for group in suite_desc
                        for scheme in _iter_schemes(group)
                    ]
                    if table_postfix is not None:
                        ret_info = _get_suite_lifecycle_ret_info(
                            scheme_names, meta_data, table_postfix
                        )
                        call_ret_types = [t for t, _n, _s in ret_info]
                        # If no scheme-level outputs (e.g. register when no scheme
                        # has a _register entry), fall back to the callee's signature
                        # so errmsg/errflg are included.
                        if not call_ret_types:
                            _, call_ret_types, _, _, _ = public_fns[suite_callee]
                            ret_info = [(t, None, None) for t in call_ret_types]
                    else:
                        _, call_ret_types, _, _, _ = public_fns[suite_callee]
                        ret_info = [(t, None, None) for t in call_ret_types]
                    # entry_postfix is the scheme-level entry point suffix
                    # (e.g. "_init" for initialize, "_finalize" for finalize,
                    # None for timestep functions that have no host inputs).
                    entry_postfix = table_postfix
                    suite_entries.append(
                        (suite_name, suite_callee, call_ret_types,
                         scheme_names, entry_postfix, ret_info)
                    )

                if not suite_entries:
                    continue

                cap_fn, decls, lc_host_ops = _generate_lifecycle_fn(
                    fn_name=fn_suffix,
                    suite_entries=suite_entries,
                    meta_data=meta_data,
                    seen_host_globals=shared_seen_host_globals,
                    cap_var_map=cap_var_map,
                    host_var_map_lc=host_var_map_lc,
                    ccpp_info_type=ccpp_info_type,
                    ccpp_info_module=ccpp_info_module_name,
                    instance_local_name=instance_local_name,
                    ninstances_local_name=ninstances_local_name,
                    **common,
                )
                all_globals.extend(lc_host_ops)
                all_declarations.extend(decls)
                # Flat lifecycle fns (ccpp_register, ccpp_init, ccpp_final) always
                # take (suite_name) and return (errmsg, errflg) — structurally fixed
                # by the CCPP protocol, no std_name mapping needed for CAM calls.
                _lc_fn_std_map = {}

            all_definitions.append(cap_fn)
            lifecycle_fns[fn_suffix] = (cap_fn, _lc_fn_std_map)
            if self.bind_c:
                cap_fn.attributes["bind_c"] = UnitAttr()

        # Generate ccpp_physics_suite_list listing ALL suite names.
        inner_char_type = memref.MemRefType(i8, [DYNAMIC_INDEX])
        allocatable_type = memref.MemRefType(inner_char_type, [])
        suite_list_block = Block(arg_types=[allocatable_type])
        suite_list_block.args[0].name_hint = "suites"

        body_ops = []
        for sn in all_suite_names:
            str_global_name = f"str_{sn}"
            str_len = len(sn)
            arr_type = llvm.LLVMArrayType.from_size_and_type(str_len, i8)

            all_globals.append(
                llvm.GlobalOp(
                    arr_type,
                    str_global_name,
                    "internal",
                    constant=True,
                    value=StringAttr(sn),
                )
            )

            str_len_const = arith.ConstantOp(
                IntegerAttr(str_len, IndexType()), IndexType()
            )
            str_alloc = memref.AllocOp([str_len_const.result], [], inner_char_type)
            addr_op = llvm.AddressOfOp(str_global_name, llvm.LLVMPointerType())
            load_op = llvm.LoadOp(addr_op, arr_type)
            set_str_op = SetStringOp(str_alloc.memref, load_op.dereferenced_value)
            store_ref_op = memref.StoreOp.get(
                str_alloc.memref, suite_list_block.args[0], []
            )
            body_ops.extend(
                [str_len_const, str_alloc, addr_op, load_op, set_str_op, store_ref_op]
            )

        suite_list_block.add_ops([*body_ops, func.ReturnOp()])
        suite_list_region = Region()
        suite_list_region.add_block(suite_list_block)
        suite_list_fn = func.FuncOp(
            "ccpp_physics_suite_list",
            builtin.FunctionType.from_lists([allocatable_type], []),
            suite_list_region,
            visibility="public",
        )
        all_definitions.append(suite_list_fn)

        # Generate ccpp_physics_suite_part_list — use actual XML group names per suite.
        suite_part_entries = [
            (sn, [grp.attributes["name"] for grp in suite_descriptions[sn]])
            for sn in all_suite_names
        ]

        suite_part_list_fn, part_global_ops = _generate_suite_part_list_fn(
            suite_part_entries=suite_part_entries,
            inner_char_type=inner_char_type,
            allocatable_type=allocatable_type,
            suite_name_type=suite_name_type,
            errmsg_type=errmsg_type,
            errflg_type=errflg_type,
            char_base=char_base,
            int_base=int_base,
        )
        all_globals.extend(part_global_ops)
        all_definitions.append(suite_part_list_fn)
        suite_vars_op = self._build_suite_variables_fn(
            suite_descriptions, ccpp_mod,
            host_std_names or {},
            protected_std_names or set(),
        )
        all_definitions.append(suite_vars_op)

        # Generate constituent registration API if any scheme has constituent arrays,
        # if there are cap-owned scratch arrays (framework-managed or scheme-scratch),
        # or if any scheme references number_of_ccpp_constituents at all -- that
        # standard_name resolves unconditionally to size(lc_all_constituents)
        # (FRAMEWORK_STD_NAME_TO_CAP_VAR, cap_shared.py), so lc_all_constituents
        # must exist whenever it could be referenced, even for a suite with no
        # dynamic registration or fixed-advected constituent of its own.
        # With --capgen-api the constituent API is always generated, as original
        # capgen does: CAM-SIMA (cam_comp.F90, phys_comp.F90, and
        # write_init_files.py's generated physics_inputs.F90) uses
        # <host>_constituents_array / <host>_model_const_properties for every
        # suite.
        dyn_names, fixed_adv, references_count = _collect_constituent_info(meta_data)
        needs_const_tend = (
            "ccpp_constituent_tendencies" in cap_var_map
            or any(sv[3] is not None for sv in scratch_var_list)
        )
        if dyn_names or fixed_adv or scratch_var_list or references_count or self.capgen_api:
            const_var_ops, const_api_op, const_global_stubs = _generate_constituent_api(
                camel_name, dyn_names, fixed_adv, scratch_vars=scratch_var_list,
                framework_var_residency=framework_var_residency,
                instance_local_name=instance_local_name,
                ninstances_local_name=ninstances_local_name,
                capgen_api=self.capgen_api,
                needs_const_tend=needs_const_tend,
                ddt_source_module=ddt_source_module,
            )
            for var_op in const_var_ops:
                _key = (var_op.var_name.data, "_cap_module_var")
                if _key not in shared_seen_host_globals:
                    shared_seen_host_globals.add(_key)
                    all_definitions.append(var_op)
            for stub in const_global_stubs:
                _key = (stub.sym_name.data,
                        stub.attributes.get("module", StringAttr("")).data)
                if _key not in shared_seen_host_globals:
                    shared_seen_host_globals.add(_key)
                    all_globals.append(stub)
            all_definitions.append(const_api_op)

        _inject_capscratch_gpu_exit(
            all_definitions, "ccpp_final",
            framework_var_residency, scratch_var_list,
            instance_local_name=instance_local_name,
        )

        # Emit USE-association stubs for DDT types used in any scheme across all suites.
        # Deduped against shared_seen_host_globals (same key shape as the
        # constituent-API stubs above) rather than a plain .extend(): the
        # constituent API's own stubs (emitted unconditionally above,
        # independent of whether any parsed arg is literally typed with the
        # DDT -- the generated constituent-registration code references it
        # regardless of that) and this generic per-arg-type scan can both
        # independently discover the same DDT (e.g.
        # ccpp_constituent_prop_ptr_t), and previously both added it without
        # checking the other's output, producing two GlobalOps with the same
        # symbol name -- a real "Redefinition of symbol" verification
        # failure whenever a suite both generates a host cap and uses
        # constituents.
        if ddt_source_module:
            _uses_constituents = bool(
                dyn_names or fixed_adv or scratch_var_list or references_count
            )
            arg_tables_iterable = (
                arg_table
                for props in meta_data.values()
                for arg_table in props.arg_tables.values()
            )
            for stub in _collect_ddt_use_stubs(arg_tables_iterable, ddt_source_module):
                _mod = stub.attributes.get("module", StringAttr("")).data
                if _mod == "ccpp_constituent_prop_mod" and not _uses_constituents:
                    continue
                _key = (stub.sym_name.data, _mod)
                if _key not in shared_seen_host_globals:
                    shared_seen_host_globals.add(_key)
                    all_globals.append(stub)

        # Original capgen's lifecycle wrappers (<host>_ccpp_physics_*), layered
        # on the capgen-v1 dispatchers the examples call (capgen_api.py).
        if self.capgen_api:
            _wrappers, _wrapper_globals = generate_capgen_api_wrappers(
                camel_name, suite_descriptions, public_fns, meta_data, lifecycle_fns,
                host_var_map_lc=host_var_map_lc,
            )
            for _g in _wrapper_globals:
                _key = (_g.sym_name.data,
                        _g.attributes.get("module", StringAttr("")).data)
                if _key not in shared_seen_host_globals:
                    shared_seen_host_globals.add(_key)
                    all_globals.append(_g)
            all_definitions.extend(_wrappers)

        module_ops = all_globals + all_definitions + all_declarations

        return builtin.ModuleOp(
            module_ops,
            sym_name=builtin.StringAttr(mod_name),
        )

    def apply(self, ctx: Context, op: builtin.ModuleOp) -> None:
        ccpp_mod = find_ccpp_module(op.body.block.ops)
        assert ccpp_mod is not None

        # Build Python descriptor objects from the CCPP metadata IR
        bmdd = BuildMetaDataDescriptions()
        bmdd.traverse(ccpp_mod)
        meta_data_descriptions = bmdd.meta_data

        # Build the suite hierarchy descriptors
        bsd = BuildSchemeDescription()
        bsd.traverse(ccpp_mod)
        suite_descriptions = bsd.schemes

        # Collect public functions from suite cap modules already in the IR
        public_fns = _collect_public_suite_functions(op.body.block.ops)

        # Build DDT-type-name → Fortran-module-name map (shared utility).
        ddt_source_module = collect_ddt_source_modules(ccpp_mod)

        # Build dict of ALL standard_names provided by the host model (from
        # non-scheme tables in the IR) mapped to their declared units.
        # Used in _build_suite_variables_fn to check for unit conversions on
        # state_variable args (a unit mismatch means the suite cap rewrites the
        # value in-place, so it should not be listed as an output variable).
        # Includes "control": a CONTROL-table var (e.g. col_start/col_end)
        # still has a declared units value, same as it did back when its
        # table was HOST-typed -- dropping it here would be a pure net loss
        # of information, not a correctness improvement.
        host_std_names: dict[str, str | None] = {}
        for _tbl_op, arg_table_op in iter_arg_tables(
            ccpp_mod, table_type=("module", "host", "ddt", "control")
        ):
            for arg_op in arg_table_op.body.ops:
                if not isa(arg_op, ccpp.ArgumentOp):
                    continue
                if arg_op.standard_name is not None:
                    _sn = arg_op.standard_name.data.lower()
                    _u = arg_op.properties.get("units")
                    host_std_names[_sn] = _u.data.lower() if _u is not None else None

        # Build set of protected host-variable standard_names.
        # Protected variables (e.g. vertical_layer_dimension, horizontal_dimension)
        # are framework-managed and excluded from ccpp_physics_suite_variables lists.
        # Includes "control": this is the actual mechanism that keeps
        # col_start/col_end (protected=True in their .meta declaration) out
        # of ccpp_physics_suite_variables() -- type-control-gap's Stage 2
        # .meta migration moved them from HOST to CONTROL, and omitting
        # "control" from this scan silently dropped that exclusion (a real
        # regression caught by the completed_ir/end_to_end FileCheck
        # goldens: horizontal_loop_begin/_end newly appeared in the
        # generated input_vars/output_vars var_list). CONTROL vars must
        # still never appear there, matching real capgen-v1.
        protected_std_names: set[str] = set()
        for _tbl_op, arg_table_op in iter_arg_tables(
            ccpp_mod, table_type=("module", "host", "ddt", "control")
        ):
            for arg_op in arg_table_op.body.ops:
                if not isa(arg_op, ccpp.ArgumentOp):
                    continue
                if (arg_op.properties.get("protected") is not None
                        and arg_op.standard_name is not None):
                    protected_std_names.add(
                        arg_op.standard_name.data.lower()
                    )

        # Generate ONE combined CCPP cap module for all suites
        cap_mod = self._generate_ccpp_cap_module(
            suite_descriptions, meta_data_descriptions, public_fns,
            ddt_source_module=ddt_source_module,
            protected_std_names=protected_std_names,
            host_std_names=host_std_names,
            ccpp_mod=ccpp_mod,
        )
        op.body.block.add_op(cap_mod)
