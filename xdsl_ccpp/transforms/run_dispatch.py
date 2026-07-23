"""Run-dispatch resolution and generation.

Extracted from ccpp_cap.py's CCPPCAP pass (Phase 3a of the restructuring plan,
mechanical move only -- no logic changes; promoting the _Run* dataclasses to
real IR ops is Phase 3b, done separately later once this move has been stable
for a while).

Builds the per-suite run-dispatch chain (resolve host/control/suite/constituent
data for each scheme call, generate the nested if/else dispatcher on
suite_name) and the suite-part-list query function. Kept as a plain
importable module (not a registered pass) per the phase plan, mirroring
lifecycle_cap.py/constituent_cap.py -- called directly from
generate-ccpp-cap's final module assembly via _generate_run_fn and
_generate_suite_part_list_fn.
"""

import sys
from dataclasses import dataclass

from xdsl.dialects import arith, builtin, func, llvm, memref, scf
from xdsl.dialects.builtin import (
    ArrayAttr,
    DictionaryAttr,
    IndexType,
    IntegerAttr,
    StringAttr,
    i8,
)
from xdsl.ir import Block, Region

from xdsl_ccpp.dialects.ccpp import ArgSourceKind, ResolvedArgOp
from xdsl_ccpp.dialects.ccpp_utils import (
    ArraySectionOp,
    CapVarRefOp,
    HostVarRefOp,
    KeywordCallOp,
    RowMajorConvertOp,
    RowMajorWriteBackOp,
    SetStringOp,
    StrCmpOp,
    TrimOp,
    WriteErrMsgOp,
)
from xdsl_ccpp.transforms.util.cap_shared import (
    _assert_call_arg_count_matches_signature,
    _bare,
    _build_ddt_resolution_maps,
    _build_host_var_map,
    _build_no_suite_matched_false_ops,
    _collect_host_block_std_names,
    _get_suite_lifecycle_ret_info,
    _rank_of,
    _resolve_ddt_access_path,
    _resolve_member_subscripts,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    CCPPType,
)
from xdsl_ccpp.transforms.util.typing import TypeConversions
from xdsl_ccpp.util.ccpp_conventions import (
    CCPP_ERROR_CODE,
    CCPP_ERROR_MESSAGE,
    CCPP_ERRMSG_LEN,
    CCPP_FRAMEWORK_STD_NAMES,
    CCPP_HORIZ_DIM_STD_NAME,
    CCPP_LOOP_BEGIN_STD_NAME,
    CCPP_LOOP_END_STD_NAME,
    CCPP_LOOP_EXTENT_STD_NAME,
)


@dataclass
class _RunMetadataMaps:
    """Lookup structures built from metadata for use in _generate_run_fn."""
    host_var_map: dict
    host_block_std_names: set
    constituent_std_names: set
    ddt_type_names: set
    ddt_instance_map: dict
    ddt_parent_map: dict


@dataclass
class _RunBlockSignature:
    """Block structure and SSA value mappings for the run dispatcher function."""
    new_block: "object"           # Block
    all_block_types: list
    block_arg_map: dict
    non_host_std_to_canonical: dict
    suite_name_arg: "object"      # BlockArgument
    suite_part_arg: "object"      # BlockArgument
    errmsg_arg: "object"          # SSAValue
    errflg_arg: "object"          # SSAValue
    col_start_ref: "object"       # HostVarRefOp | None
    col_end_ref: "object"         # HostVarRefOp | None
    errmsg_alloc: "object"        # HostVarRefOp | None
    errflg_alloc: "object"        # HostVarRefOp | None
    ccpp_info_block_arg: "object" # BlockArgument | None
    ccpp_data_block_arg: "object" # BlockArgument | None
    ccpp_info_type: "object"      # memref type or None
    ccpp_t_type: "object"         # memref type or None


@dataclass
class _RunChainPreamble:
    """Seed ops and grouping structures for the dispatch-chain construction."""
    err_const: "object"       # arith.ConstantOp — initialises errflg to 0
    store_errflg: "object"    # memref.StoreOp
    trim_suite_name: "object" # TrimOp
    current_false_ops: list   # innermost else: "no suite matched" error sequence
    all_decls: list           # accumulator for external FuncOp declarations
    per_suite_grouped: dict   # suite_name → [info, ...], preserving order


def _build_run_metadata_maps(meta_data) -> "_RunMetadataMaps":
    """Build all host/DDT lookup maps needed by _generate_run_fn.

    Pure read of meta_data — no IR ops created, no side effects.
    """
    host_var_map = _build_host_var_map(meta_data, include_host=False)
    host_block_std_names = _collect_host_block_std_names(meta_data)

    constituent_std_names: set = set()
    for _mod_name, props in meta_data.items():
        if props.getAttr("type") != CCPPType.SCHEME:
            continue
        for arg_tbl in props.arg_tables.values():
            for var in arg_tbl.getFunctionArguments():
                if var.hasAttr("constituent") and var.hasAttr("standard_name"):
                    constituent_std_names.add(var.getAttr("standard_name").lower())

    ddt_type_names = {
        tbl_name
        for tbl_name, props in meta_data.items()
        if props.getAttr("type") == CCPPType.DDT
    }
    ddt_instance_map, ddt_parent_map = _build_ddt_resolution_maps(meta_data)

    return _RunMetadataMaps(
        host_var_map=host_var_map,
        host_block_std_names=host_block_std_names,
        constituent_std_names=constituent_std_names,
        ddt_type_names=ddt_type_names,
        ddt_instance_map=ddt_instance_map,
        ddt_parent_map=ddt_parent_map,
    )

def _build_per_suite_run_info(
    suite_run_entries,
    public_fns: dict,
    meta_data,
    maps: "_RunMetadataMaps",
    cap_var_map,
    seen_host_globals: set,
) -> "tuple[list, list]":
    """Classify each suite run entry's args and build per-suite info dicts.

    For every (suite_name, suite_part, suite_callee, scheme_names) entry,
    resolves which callee args come from host module variables, DDT members,
    cap-owned vars, or caller block args.  Emits GlobalOp USE-statement stubs
    into seen_host_globals (mutated in-place — shared across lifecycle functions).

    Returns (per_suite, host_global_ops).
    """
    host_block_std_names = maps.host_block_std_names
    constituent_std_names = maps.constituent_std_names
    ddt_instance_map = maps.ddt_instance_map
    ddt_parent_map = maps.ddt_parent_map

    per_suite = []
    host_global_ops: list = []

    for suite_name, suite_part, suite_callee, scheme_names in suite_run_entries:
        (
            callee_module,
            callee_output_types,
            callee_input_types,
            callee_input_names,
        ) = public_fns[suite_callee]

        # Build {local_arg_name → standard_name} from the _run arg tables.
        std_name_of = {}
        for scheme_name in scheme_names:
            table_name = scheme_name + "_run"
            if scheme_name not in meta_data:
                continue
            if table_name not in meta_data[scheme_name].arg_tables:
                continue
            for fn_arg in (
                meta_data[scheme_name]
                .getArgTable(table_name)
                .getFunctionArguments()
            ):
                if fn_arg.name not in std_name_of and fn_arg.hasAttr(
                    "standard_name"
                ):
                    std_name_of[fn_arg.name] = fn_arg.getAttr("standard_name").lower()

        # Also check HOST and MODULE tables for suite-level args (like col_start/
        # col_end) that don't appear directly in any scheme _run table but are
        # part of the suite cap's signature for loop bounds / array sectioning.
        for callee_arg in callee_input_names:
            if _bare(callee_arg) in std_name_of:
                continue
            bare = _bare(callee_arg)
            for tbl_name, props in meta_data.items():
                if props.getAttr("type") not in (CCPPType.HOST, CCPPType.MODULE):
                    continue
                if tbl_name not in props.arg_tables:
                    continue
                for var in props.getArgTable(tbl_name).getFunctionArguments():
                    if var.name == bare and var.hasAttr("standard_name"):
                        std_name_of[bare] = var.getAttr("standard_name").lower()
                        break

        # Build local_name → (host_var, host_module, is_ddt) from the match pass
        # results stored in descriptor objects.  HostVariableMatchPass already
        # computed model_var_name / model_module_name for every matched scheme arg
        # and stored them as properties on the IR ops; BuildMetaDataDescriptions
        # copies those into the CCPPArgument descriptors via known_props.
        # Using this avoids re-deriving the same information from raw metadata.
        local_to_host_info: dict = {}
        for scheme_name in scheme_names:
            table_name = scheme_name + "_run"
            if scheme_name not in meta_data:
                continue
            if table_name not in meta_data[scheme_name].arg_tables:
                continue
            for fn_arg in (
                meta_data[scheme_name]
                .getArgTable(table_name)
                .getFunctionArguments()
            ):
                bare_name = _bare(fn_arg.name)
                if bare_name not in local_to_host_info and fn_arg.hasAttr(
                    "model_var_name"
                ):
                    local_to_host_info[bare_name] = (
                        fn_arg.getAttr("model_var_name"),
                        fn_arg.getAttr("model_module_name"),
                        fn_arg.hasAttr("model_var_is_ddt"),
                    )

        # Build bare_name → (dim_std_names, intent) for rank≥2 row_major args.
        # These will be transposed via RowMajorConvertOp in the dispatch chain.
        local_to_array_layout: dict = {}
        for scheme_name in scheme_names:
            table_name = scheme_name + "_run"
            if scheme_name not in meta_data:
                continue
            if table_name not in meta_data[scheme_name].arg_tables:
                continue
            for fn_arg in (
                meta_data[scheme_name]
                .getArgTable(table_name)
                .getFunctionArguments()
            ):
                bare_name = _bare(fn_arg.name)
                if (
                    bare_name not in local_to_array_layout
                    and fn_arg.hasAttr("model_var_array_layout")
                    and fn_arg.getAttr("model_var_array_layout") == "row_major"
                    and fn_arg.hasAttr("dim_names")
                    and fn_arg.hasAttr("dimensions")
                    and fn_arg.getAttr("dimensions") >= 2
                ):
                    local_to_array_layout[bare_name] = (
                        fn_arg.getAttr("dim_names"),
                        fn_arg.getAttr("intent") if fn_arg.hasAttr("intent") else "in",
                    )

        # Classify each callee input arg using match pass results as primary source.
        resolved_arg_ops = []
        for arg_name in callee_input_names:
            bare = _bare(arg_name)
            std_name = std_name_of.get(bare) or std_name_of.get(arg_name)

            if bare in local_to_host_info and not (
                std_name and std_name in host_block_std_names
            ):
                # local_to_host_info has a match, AND it is not a protected
                # HOST-type block arg (those are passed by the caller, not
                # accessed via a USE statement).
                host_var, host_mod, is_ddt = local_to_host_info[bare]
                if is_ddt:
                    # DDT member: model_module_name is the DDT table/type name.
                    # Resolve to a module-level instance, following parent DDTs
                    # for nested types (e.g. A contains B contains x → a%b%x).
                    ddt_type_name = host_mod
                    result = _resolve_ddt_access_path(
                        ddt_type_name, ddt_instance_map, ddt_parent_map
                    )
                    if result is not None:
                        instance_var, instance_module, path_prefix = result
                        full_member = path_prefix + host_var
                        # Skip DDT instances whose instance variable lives in a HOST-type
                        # table (e.g. ccpp_info_t accessed through 'ccpp' in test_host).
                        # HOST-type tables are caller-provided interfaces, not Fortran
                        # modules — their contents become block args, not USE stubs.
                        if (
                            instance_module in meta_data
                            and meta_data[instance_module].getAttr("type") == CCPPType.HOST
                        ):
                            resolved_arg_ops.append(
                                ResolvedArgOp(arg_name, ArgSourceKind.Block)
                            )
                        else:
                            resolved_arg_ops.append(
                                ResolvedArgOp(
                                    arg_name,
                                    ArgSourceKind.DdtMember,
                                    var_name=instance_var,
                                    module_name=instance_module,
                                    member_path=full_member,
                                )
                            )
                    else:
                        print(
                            f"Warning: '{suite_callee}' arg '{arg_name}' "
                            f"(standard_name='{std_name}') matched DDT type "
                            f"'{ddt_type_name}' but no module-level instance was "
                            f"found — treating as a host-caller block argument.",
                            file=sys.stderr,
                        )
                        resolved_arg_ops.append(
                            ResolvedArgOp(arg_name, ArgSourceKind.Block)
                        )
                else:
                    resolved_arg_ops.append(
                        ResolvedArgOp(
                            arg_name, ArgSourceKind.Host,
                            var_name=host_var, module_name=host_mod,
                        )
                    )
            elif std_name and cap_var_map and std_name in cap_var_map:
                # Cap-owned module variable (e.g. vmr interstitial DDT)
                resolved_arg_ops.append(
                    ResolvedArgOp(arg_name, ArgSourceKind.CapVar, std_name=std_name)
                )
            else:
                if std_name and std_name not in host_block_std_names \
                        and std_name not in CCPP_FRAMEWORK_STD_NAMES \
                        and std_name not in constituent_std_names \
                        and not arg_name.endswith("__opt"):
                    print(
                        f"Warning: '{suite_callee}' arg '{arg_name}' "
                        f"(standard_name='{std_name}') has no host variable "
                        f"match — treating as a host-caller block argument. "
                        f"Check that the host metadata provides this variable.",
                        file=sys.stderr,
                    )
                resolved_arg_ops.append(ResolvedArgOp(arg_name, ArgSourceKind.Block))

        non_host_args = [
            (callee_input_names[i], callee_input_types[i],
             std_name_of.get(_bare(callee_input_names[i]),
                             callee_input_names[i]))
            for i, op in enumerate(resolved_arg_ops)
            if op.source_kind.data == ArgSourceKind.Block
            # cap_var sources are cap-internal; don't expose as block args
        ]

        # Collect module-level host global stubs (shared across all suites).
        for i, (_arg_name, _arg_type) in enumerate(
            zip(callee_input_names, callee_input_types)
        ):
            op = resolved_arg_ops[i]
            if op.source_kind.data == ArgSourceKind.Host:
                stub_name, stub_module = op.var_name.data, op.module_name.data
            elif op.source_kind.data == ArgSourceKind.DdtMember:
                stub_name, stub_module = op.var_name.data, op.module_name.data
            elif op.source_kind.data == ArgSourceKind.CapVar:
                continue  # cap vars live in the same module, no USE needed
            else:
                continue
            key = (stub_name, stub_module)
            if key not in seen_host_globals:
                seen_host_globals.add(key)
                glob = llvm.GlobalOp(
                    llvm.LLVMArrayType.from_size_and_type(1, i8),
                    stub_name,
                    "external",
                )
                glob.attributes["module"] = StringAttr(stub_module)
                host_global_ops.append(glob)

        per_suite.append(
            {
                "suite_name": suite_name,
                "suite_part": suite_part,
                "suite_callee": suite_callee,
                "callee_module": callee_module,
                "callee_output_types": callee_output_types,
                "callee_input_types": callee_input_types,
                "callee_input_names": callee_input_names,
                "resolved_arg_ops": resolved_arg_ops,
                "non_host_args": non_host_args,
                "std_name_of": std_name_of,
                "scheme_names": scheme_names,
                "local_to_array_layout": local_to_array_layout,
            }
        )

    return per_suite, host_global_ops

def _build_run_block_signature(
    per_suite: list,
    meta_data,
    kwargs: dict,
    suite_name_type,
    suite_part_type,
    errmsg_type,
    errflg_type,
    int_base,
) -> "_RunBlockSignature":
    """Build the function block and all arg/SSA mappings for the run dispatcher.

    Computes the union of non-host args across all suites, filters out args
    provided by ccpp_info_t / ccpp_t framework types, constructs the Block with
    the correct arg-type list, and returns every SSA value needed by the
    dispatch chain and function assembly phases.
    """
    ccpp_info_type = kwargs.get("ccpp_info_type")
    ccpp_info_module = kwargs.get("ccpp_info_module")
    ccpp_t_type = kwargs.get("ccpp_t_type")
    ccpp_t_var_name = kwargs.get("ccpp_t_var_name", "ccpp_data")

    # ── Union of non-host args across all suites (ordered by first appearance) ──
    # Deduplicate by standard_name: different schemes may use different local
    # names for the same variable (e.g. 'cols'/'cole' vs 'col_start'/'col_end'
    # for horizontal_loop_begin/end).  Only the first-seen local name is kept.
    union_non_host_args: dict = {}  # canonical_arg_name → arg_type
    seen_non_host_std_names: dict = {}  # std_name → canonical_arg_name
    # Also build a rename map for per-suite block_arg_map construction below.
    non_host_std_to_canonical: dict = {}  # suite-level std_name → canonical name
    for info in per_suite:
        for arg_name, arg_type, std_name in info["non_host_args"]:
            if std_name and std_name in seen_non_host_std_names:
                # Same standard_name seen before — record the rename
                canonical = seen_non_host_std_names[std_name]
                non_host_std_to_canonical[std_name] = canonical
            elif arg_name not in union_non_host_args:
                union_non_host_args[arg_name] = arg_type
                if std_name:
                    seen_non_host_std_names[std_name] = arg_name
                    non_host_std_to_canonical[std_name] = arg_name

    # When the host uses the ccpp_info_t pattern, loop bounds (col_start/col_end)
    # come from ccpp_info%col_start/col_end — exclude them from the block args.
    if ccpp_info_type is not None:
        # Collect all member names of the ccpp_info_t DDT from meta_data.
        # These are fields provided by ccpp_info, not separate block args.
        _ccpp_ddt_name = ccpp_info_type.element_type.type_name.data
        _ccpp_member_names: set = set()
        _ccpp_member_std_names: set = {CCPP_LOOP_BEGIN_STD_NAME, CCPP_LOOP_END_STD_NAME}
        for _mn, _mp in meta_data.items():
            if _mn != _ccpp_ddt_name:
                continue
            if _mn not in _mp.arg_tables:
                continue
            for _mv in _mp.getArgTable(_mn).getFunctionArguments():
                _ccpp_member_names.add(_mv.name)
                if _mv.hasAttr("standard_name"):
                    _ccpp_member_std_names.add(_mv.getAttr("standard_name").lower())

        # Also collect canonical arg names for loop-begin/end std_names.
        _ccpp_provided_canonicals = {
            non_host_std_to_canonical[s]
            for s in _ccpp_member_std_names
            if s in non_host_std_to_canonical
        }
        # Filter: remove args whose arg_name matches a ccpp_info member OR
        # whose canonical name maps to a ccpp_info-provided std_name.
        union_non_host_args = {
            k: v for k, v in union_non_host_args.items()
            if k not in _ccpp_member_names and k not in _ccpp_provided_canonicals
        }

    if ccpp_t_type is not None and ccpp_t_var_name in union_non_host_args:
        # Remove the ccpp_t variable; it is threaded at a fixed position (args[2]).
        union_non_host_args = {
            k: v for k, v in union_non_host_args.items()
            if k != ccpp_t_var_name
        }

    n_non_host = len(union_non_host_args)

    if ccpp_info_type is not None:
        all_block_types = (
            [suite_name_type, suite_part_type, ccpp_info_type]
            + list(union_non_host_args.values())
        )
    elif ccpp_t_type is not None:
        all_block_types = (
            [suite_name_type, suite_part_type, ccpp_t_type]
            + list(union_non_host_args.values())
            + [errmsg_type, errflg_type]
        )
    else:
        all_block_types = (
            [suite_name_type, suite_part_type]
            + list(union_non_host_args.values())
            + [errmsg_type, errflg_type]
        )
    new_block = Block(arg_types=all_block_types)

    suite_name_arg = new_block.args[0]
    suite_name_arg.name_hint = "suite_name"
    suite_part_arg = new_block.args[1]

    ccpp_info_block_arg = None
    ccpp_data_block_arg = None
    col_start_ref = None
    col_end_ref = None
    errmsg_alloc = None
    errflg_alloc = None

    if ccpp_info_type is not None:
        ccpp_info_block_arg = new_block.args[2]
        ccpp_info_block_arg.name_hint = "ccpp_info"
        suite_part_arg.name_hint = "suite_part"

        block_arg_map = {}
        for i, arg_name in enumerate(union_non_host_args):
            ba = new_block.args[3 + i]
            ba.name_hint = arg_name
            block_arg_map[arg_name] = ba

        # Loop bounds from ccpp_info%col_start / col_end
        int_type = memref.MemRefType(int_base, [])
        col_start_ref = HostVarRefOp(
            "ccpp_info", ccpp_info_module, int_type, member_name="col_start"
        )
        col_end_ref = HostVarRefOp(
            "ccpp_info", ccpp_info_module, int_type, member_name="col_end"
        )
        col_begin_key = non_host_std_to_canonical.get(CCPP_LOOP_BEGIN_STD_NAME)
        col_end_key = non_host_std_to_canonical.get(CCPP_LOOP_END_STD_NAME)
        if col_begin_key:
            block_arg_map[col_begin_key] = col_start_ref.res
        if col_end_key:
            block_arg_map[col_end_key] = col_end_ref.res
        # Also map the ccpp_info_t member names directly so callee arg
        # lookup works even when the callee uses member names with no std_name.
        block_arg_map["col_start"] = col_start_ref.res
        block_arg_map["col_end"] = col_end_ref.res

        # errmsg/errflg from ccpp_info members (no separate block args)
        errmsg_alloc = HostVarRefOp(
            "ccpp_info", ccpp_info_module, errmsg_type, member_name="errmsg"
        )
        errflg_alloc = HostVarRefOp(
            "ccpp_info", ccpp_info_module, errflg_type, member_name="errflg"
        )
        errmsg_arg = errmsg_alloc.res
        errflg_arg = errflg_alloc.res
        # Map member names for errmsg/errflg so callee arg lookup works.
        block_arg_map["errmsg"] = errmsg_alloc.res
        block_arg_map["errflg"] = errflg_alloc.res
    elif ccpp_t_type is not None:
        # ccpp_t pattern: ccpp_data at args[2], non-host args follow, then errmsg/errflg.
        ccpp_data_block_arg = new_block.args[2]
        ccpp_data_block_arg.name_hint = ccpp_t_var_name
        suite_part_arg.name_hint = "suite_part"

        block_arg_map = {}
        for i, arg_name in enumerate(union_non_host_args):
            ba = new_block.args[3 + i]
            ba.name_hint = arg_name
            block_arg_map[arg_name] = ba
        block_arg_map[ccpp_t_var_name] = ccpp_data_block_arg

        errmsg_arg = new_block.args[3 + n_non_host]
        errmsg_arg.name_hint = "errmsg"
        errflg_arg = new_block.args[3 + n_non_host + 1]
        errflg_arg.name_hint = "errflg"
    else:
        suite_part_arg.name_hint = "suite_part"
        block_arg_map = {}
        for i, arg_name in enumerate(union_non_host_args):
            ba = new_block.args[2 + i]
            ba.name_hint = arg_name
            block_arg_map[arg_name] = ba

        errmsg_arg = new_block.args[2 + n_non_host]
        errmsg_arg.name_hint = "errmsg"
        errflg_arg = new_block.args[2 + n_non_host + 1]
        errflg_arg.name_hint = "errflg"

    return _RunBlockSignature(
        new_block=new_block,
        all_block_types=all_block_types,
        block_arg_map=block_arg_map,
        non_host_std_to_canonical=non_host_std_to_canonical,
        suite_name_arg=suite_name_arg,
        suite_part_arg=suite_part_arg,
        errmsg_arg=errmsg_arg,
        errflg_arg=errflg_arg,
        col_start_ref=col_start_ref,
        col_end_ref=col_end_ref,
        errmsg_alloc=errmsg_alloc,
        errflg_alloc=errflg_alloc,
        ccpp_info_block_arg=ccpp_info_block_arg,
        ccpp_data_block_arg=ccpp_data_block_arg,
        ccpp_info_type=ccpp_info_type,
        ccpp_t_type=ccpp_t_type,
    )

def _build_run_chain_preamble(
    per_suite: list,
    suite_name_arg,
    errmsg_arg,
    errflg_arg,
) -> "_RunChainPreamble":
    """Build the seed ops and grouping data for the if/else dispatch chain.

    Creates the errflg initialisation op, the suite-name trim, the innermost
    "no suite matched" error sequence (the seed for inside-out chain building),
    and groups per_suite entries by suite_name for the outer loop.

    Pure function — no side effects, no IR mutation beyond creating new ops.
    """
    err_const = arith.ConstantOp.from_int_and_width(0, 32)
    store_errflg = memref.StoreOp.get(err_const, errflg_arg, [])
    trim_suite_name = TrimOp(suite_name_arg)

    current_false_ops = _build_no_suite_matched_false_ops(
        errmsg_arg, trim_suite_name.res, errflg_arg
    )

    per_suite_grouped: dict = {}
    for _info in per_suite:
        _sn = _info["suite_name"]
        if _sn not in per_suite_grouped:
            per_suite_grouped[_sn] = []
        per_suite_grouped[_sn].append(_info)

    return _RunChainPreamble(
        err_const=err_const,
        store_errflg=store_errflg,
        trim_suite_name=trim_suite_name,
        current_false_ops=current_false_ops,
        all_decls=[],
        per_suite_grouped=per_suite_grouped,
    )

def _build_run_dispatch_chain(
    per_suite_grouped: dict,
    trim_suite_name,
    suite_part_arg,
    errmsg_arg,
    errflg_arg,
    errmsg_type,
    errflg_type,
    block_arg_map: dict,
    non_host_std_to_canonical: dict,
    host_var_map: dict,
    meta_data,
    cap_var_map,
    seen_host_globals: set,
    current_false_ops: list,
    ccpp_t_type,
    ccpp_data_block_arg,
) -> "tuple[list, list, list]":
    """Build the nested if/else dispatch chain over suite_name and suite_part.

    Iterates per_suite_grouped in reverse (inside-out IfOp construction) to
    produce the final chain of strcmp/IfOp pairs rooted at ``trim_suite_name``.
    Host variable refs and array sections are hoisted to the outer (suite_name)
    if-true region so that GPUCcppCapPass can find them for directive generation.

    seen_host_globals is mutated in place (shared deduplication set).

    Returns (main_chain_ops, decls, chain_global_ops):
      - main_chain_ops: inner ops for the main block (excluding trailing YieldOp)
      - decls: external FuncOp declarations for every suite callee
      - chain_global_ops: GlobalOp USE stubs emitted during chain construction
    """
    decls = []
    chain_global_ops = []

    for suite_name, suite_infos in reversed(list(per_suite_grouped.items())):
        # trim_suite_part is created once and shared across all parts of this suite.
        trim_suite_part = TrimOp(suite_part_arg)

        # Innermost false branch: no suite_part matched.
        write_part_err = WriteErrMsgOp(
            errmsg_arg, trim_suite_part.res,
            "No suite part named ", f" found in suite {suite_name}",
        )
        one_part_err = arith.ConstantOp.from_int_and_width(1, 32)
        store_part_err = memref.StoreOp.get(one_part_err, errflg_arg, [])
        part_inner_false = [write_part_err, one_part_err, store_part_err, scf.YieldOp()]

        # Collect host var refs and array section ops across all suite parts so
        # they can be placed in the outer (suite_name) if's true region.  This
        # makes them visible to GPUCcppCapPass, which looks for HostVarRefOps in
        # the outer true_block when building !$acc data directives.  SSA values
        # defined in the outer block are still accessible inside the inner if's
        # true region (dominance), so the suite physics call is unaffected.
        suite_host_refs: list = []
        suite_array_secs: list = []

        for info in reversed(suite_infos):
            suite_part = info["suite_part"]
            suite_callee = info["suite_callee"]
            callee_module = info["callee_module"]
            callee_output_types = info["callee_output_types"]
            callee_input_types = info["callee_input_types"]
            callee_input_names = info["callee_input_names"]
            resolved_arg_ops = info["resolved_arg_ops"]
            std_name_of = info["std_name_of"]
            scheme_names = info["scheme_names"]
            local_to_array_layout = info.get("local_to_array_layout", {})

            # ── Build standard_name → dim_names for cap_var sources ──────
            cap_var_std_to_dims: dict = {}
            for _sv_scheme in scheme_names:
                _sv_run_tbl = _sv_scheme + "_run"
                if _sv_scheme not in meta_data:
                    continue
                if _sv_run_tbl not in meta_data[_sv_scheme].arg_tables:
                    continue
                for _sv_fa in (
                    meta_data[_sv_scheme].getArgTable(_sv_run_tbl).getFunctionArguments()
                ):
                    if _sv_fa.hasAttr("standard_name") and _sv_fa.hasAttr("dim_names"):
                        _sv_sn = _sv_fa.getAttr("standard_name").lower()
                        if _sv_sn not in cap_var_std_to_dims:
                            cap_var_std_to_dims[_sv_sn] = _sv_fa.getAttr("dim_names")

            # ── HostVarRefOps ─────────────────────────────────────────────
            host_var_ref_ops = []
            host_var_ref_results = {}
            host_name_to_ref_result = {}

            for i, (arg_name, arg_type) in enumerate(
                zip(callee_input_names, callee_input_types)
            ):
                op = resolved_arg_ops[i]
                if op.source_kind.data == ArgSourceKind.Host:
                    host_var_name, host_module_name = op.var_name.data, op.module_name.data
                    ref_op = HostVarRefOp(host_var_name, host_module_name, arg_type)
                    host_var_ref_ops.append(ref_op)
                    host_var_ref_results[arg_name] = ref_op.res
                    host_name_to_ref_result[host_var_name] = ref_op.res
                elif op.source_kind.data == ArgSourceKind.DdtMember:
                    instance_var, instance_module, member_name = (
                        op.var_name.data, op.module_name.data, op.member_path.data
                    )
                    # Resolve std_name tokens in subscript to local variable names
                    resolved_member, sub_vars = _resolve_member_subscripts(
                        member_name, host_var_map
                    )
                    ref_op = HostVarRefOp(
                        instance_var, instance_module, arg_type,
                        member_name=resolved_member,
                    )
                    host_var_ref_ops.append(ref_op)
                    host_var_ref_results[arg_name] = ref_op.res
                    host_name_to_ref_result[f"{instance_var}%{resolved_member}"] = ref_op.res
                    # Emit USE stubs for subscript variables (already resolved to local names)
                    for local_name, module_name in sub_vars:
                        key = (local_name, module_name)
                        if key not in seen_host_globals:
                            seen_host_globals.add(key)
                            sv_glob = llvm.GlobalOp(
                                llvm.LLVMArrayType.from_size_and_type(1, i8),
                                local_name, "external",
                            )
                            sv_glob.attributes["module"] = StringAttr(module_name)
                            chain_global_ops.append(sv_glob)
                elif op.source_kind.data == ArgSourceKind.CapVar:
                    std_name_cv = op.std_name.data
                    cv_name, cv_type, _ftn = cap_var_map[std_name_cv]
                    _cv_dims = cap_var_std_to_dims.get(std_name_cv, [])
                    if _cv_dims and _cv_dims[0].lower() == CCPP_LOOP_EXTENT_STD_NAME:
                        _cv_rank = _rank_of(arg_type)
                        if _cv_rank > 0:
                            cv_name = f"{cv_name}({', '.join([':'] * _cv_rank)})"
                    cap_ref = CapVarRefOp(cv_name, arg_type)
                    host_var_ref_ops.append(cap_ref)
                    host_var_ref_results[arg_name] = cap_ref.res

            # ── ArraySectionOps ───────────────────────────────────────────
            array_section_pre_ops = []
            array_section_extra_ops = []
            array_section_main_ops = []
            one_const_for_sections = None

            for i, (arg_name, arg_type) in enumerate(
                zip(callee_input_names, callee_input_types)
            ):
                # Row-major rank≥2 arrays are handled by RowMajorConvertOp below;
                # skip ArraySectionOp for them so we don't double-slice.
                if _bare(arg_name) in local_to_array_layout:
                    continue
                op = resolved_arg_ops[i]
                if op.source_kind.data == ArgSourceKind.Host:
                    host_var_name, host_module_name = op.var_name.data, op.module_name.data
                    lookup_var, lookup_mod = host_var_name, host_module_name
                elif op.source_kind.data == ArgSourceKind.DdtMember:
                    instance_var, instance_module, member_name = (
                        op.var_name.data, op.module_name.data, op.member_path.data
                    )
                    # For nested paths like "b%x" or "b%x(ncol)", strip the
                    # chain prefix and any array subscripts to get the leaf
                    # member name for the var descriptor lookup.
                    leaf = member_name.rsplit("%", 1)[-1].split("(")[0]
                    lookup_var, lookup_mod = leaf, instance_module
                elif op.source_kind.data == ArgSourceKind.CapVar:
                    std_name_cv = op.std_name.data
                    _cv_dims = cap_var_std_to_dims.get(std_name_cv, [])
                    if not _cv_dims or _cv_dims[0].lower() != CCPP_LOOP_EXTENT_STD_NAME:
                        continue
                    col_begin_key = non_host_std_to_canonical.get(CCPP_LOOP_BEGIN_STD_NAME)
                    col_end_key   = non_host_std_to_canonical.get(CCPP_LOOP_END_STD_NAME)
                    if not col_begin_key or not col_end_key:
                        continue
                    if col_begin_key not in block_arg_map or col_end_key not in block_arg_map:
                        continue
                    section = ArraySectionOp(
                        host_var_ref_results[arg_name],
                        [block_arg_map[col_begin_key]],
                        [block_arg_map[col_end_key]],
                    )
                    array_section_main_ops.append(section)
                    host_var_ref_results[arg_name] = section.res
                    continue
                else:
                    continue

                # Look up the var descriptor; for DDT members, search the DDT table
                host_var_name = lookup_var
                host_module_name = lookup_mod
                try:
                    # Try the module table first, then DDT tables
                    if lookup_mod in meta_data and lookup_mod in meta_data[lookup_mod].arg_tables:
                        mod_arg_table = meta_data[lookup_mod].getArgTable(lookup_mod)
                        host_var_desc = mod_arg_table.getFunctionArgument(lookup_var)
                    else:
                        # DDT member: search all DDT tables for the member
                        raise AssertionError("not found in module, try DDT")
                except (KeyError, AssertionError):
                    # Try DDT tables
                    found = False
                    for tbl_name, props in meta_data.items():
                        if props.getAttr("type") != CCPPType.DDT:
                            continue
                        if tbl_name not in props.arg_tables:
                            continue
                        try:
                            host_var_desc = props.getArgTable(tbl_name).getFunctionArgument(lookup_var)
                            found = True
                            break
                        except (KeyError, AssertionError):
                            continue
                    if not found:
                        continue

                if not host_var_desc.hasAttr("dim_names"):
                    continue
                dim_names_list = host_var_desc.getAttr("dim_names")
                if not dim_names_list or dim_names_list[0].lower() != CCPP_HORIZ_DIM_STD_NAME:
                    continue

                # Find the canonical block arg names for loop begin/end via
                # standard_name, since different schemes use different local names.
                col_begin_key = non_host_std_to_canonical.get(CCPP_LOOP_BEGIN_STD_NAME)
                col_end_key   = non_host_std_to_canonical.get(CCPP_LOOP_END_STD_NAME)
                if not col_begin_key or not col_end_key:
                    continue
                if col_begin_key not in block_arg_map or col_end_key not in block_arg_map:
                    continue

                lowers = [block_arg_map[col_begin_key]]
                uppers = [block_arg_map[col_end_key]]

                valid = True
                for dim_std_name in dim_names_list[1:]:
                    dim_std_name = dim_std_name.lower()
                    if dim_std_name not in host_var_map:
                        valid = False
                        break
                    dim_var_name, dim_module_name = host_var_map[dim_std_name]

                    if dim_var_name in host_name_to_ref_result:
                        dim_upper_ref = host_name_to_ref_result[dim_var_name]
                    else:
                        dim_ref_op = HostVarRefOp(
                            dim_var_name,
                            dim_module_name,
                            TypeConversions.getBaseType("integer"),
                        )
                        array_section_extra_ops.append(dim_ref_op)
                        host_name_to_ref_result[dim_var_name] = dim_ref_op.res
                        dim_upper_ref = dim_ref_op.res

                        key = (dim_var_name, dim_module_name)
                        if key not in seen_host_globals:
                            seen_host_globals.add(key)
                            dim_glob = llvm.GlobalOp(
                                llvm.LLVMArrayType.from_size_and_type(1, i8),
                                dim_var_name,
                                "external",
                            )
                            dim_glob.attributes["module"] = StringAttr(dim_module_name)
                            chain_global_ops.append(dim_glob)

                    if one_const_for_sections is None:
                        one_const_for_sections = arith.ConstantOp.from_int_and_width(
                            1, 32
                        )
                        array_section_pre_ops.append(one_const_for_sections)

                    lowers.append(one_const_for_sections.result)
                    uppers.append(dim_upper_ref)

                if not valid or len(lowers) < 2:
                    continue

                section = ArraySectionOp(
                    host_var_ref_results[arg_name],
                    lowers,
                    uppers,
                )
                array_section_main_ops.append(section)
                host_var_ref_results[arg_name] = section.res

            array_section_ops = (
                array_section_pre_ops + array_section_extra_ops + array_section_main_ops
            )

            # ── RowMajorConvertOps (rank≥2 row_major host arrays) ─────────
            # Transpose row-major host arrays to column-major temps before
            # passing them to the suite.  ArraySectionOps are skipped for
            # these args (see check above) so host_var_ref_results[arg_name]
            # still holds the raw HostVarRefOp result at this point.
            row_major_convert_ops: list = []
            row_major_write_back_pairs: list = []  # (conv_op, host_ref_result)

            for i, (arg_name, arg_type) in enumerate(
                zip(callee_input_names, callee_input_types)
            ):
                op = resolved_arg_ops[i]
                if op.source_kind.data != ArgSourceKind.Host:
                    continue
                bare = _bare(arg_name)
                if bare not in local_to_array_layout:
                    continue

                dim_std_names, intent = local_to_array_layout[bare]
                dim_exprs: list = []
                valid = True
                for dim_sn in dim_std_names:
                    sn_lower = dim_sn.lower()
                    if sn_lower == CCPP_LOOP_EXTENT_STD_NAME:
                        # horizontal loop extent: express as col_end - col_start + 1
                        col_begin_key = non_host_std_to_canonical.get(CCPP_LOOP_BEGIN_STD_NAME)
                        col_end_key   = non_host_std_to_canonical.get(CCPP_LOOP_END_STD_NAME)
                        if (col_begin_key and col_end_key
                                and col_begin_key in block_arg_map
                                and col_end_key in block_arg_map):
                            dim_exprs.append(f"{col_end_key} - {col_begin_key} + 1")
                        else:
                            valid = False
                            break
                    else:
                        canonical = non_host_std_to_canonical.get(sn_lower)
                        if canonical:
                            dim_exprs.append(canonical)
                        elif sn_lower in host_var_map:
                            # Dimension is a host module variable; use its name directly
                            dim_exprs.append(host_var_map[sn_lower][0])
                        else:
                            valid = False
                            break
                if not valid:
                    continue

                host_ref_result = host_var_ref_results[arg_name]
                conv_op = RowMajorConvertOp(host_ref_result, dim_exprs, arg_type)
                conv_op.res.name_hint = f"{bare}_col"
                row_major_convert_ops.append(conv_op)
                host_var_ref_results[arg_name] = conv_op.res

                if intent in ("inout", "out"):
                    row_major_write_back_pairs.append((conv_op, host_ref_result, dim_exprs))

            # ── Build call args in callee order ───────────────────────────
            call_args = []
            call_arg_bare_names = []
            for i, arg_name in enumerate(callee_input_names):
                op = resolved_arg_ops[i]
                if op.source_kind.data in (
                    ArgSourceKind.Host, ArgSourceKind.DdtMember, ArgSourceKind.CapVar
                ):
                    call_args.append(host_var_ref_results[arg_name])
                else:
                    # Block arg: use canonical name if this arg was deduplicated
                    bare = _bare(arg_name)
                    std = std_name_of.get(bare, bare)
                    canonical = non_host_std_to_canonical.get(std, arg_name)
                    # Fall back to arg_name if canonical not in block_arg_map
                    key = canonical if canonical in block_arg_map else arg_name
                    call_args.append(block_arg_map[key])
                call_arg_bare_names.append(_bare(arg_name))

            # ── Verify argument count matches callee signature ─────────────
            _assert_call_arg_count_matches_signature(
                suite_callee, call_args, callee_input_names, callee_input_types
            )

            # ── Inner if for suite_part ───────────────────────────────────
            suite_part_eq = StrCmpOp(trim_suite_part.res, literal=suite_part)

            # Use keyword-argument call when any suite cap input is optional
            # so that Fortran correctly forwards the OPTIONAL absence status.
            suite_has_optional = any(n.endswith("__opt") for n in callee_input_names)
            if suite_has_optional:
                # Derive result keyword names from output types
                _result_names = [
                    "errmsg" if rt == errmsg_type
                    else "errflg" if rt == errflg_type
                    else f"_out_{_i}"
                    for _i, rt in enumerate(callee_output_types)
                ]
                call_op = KeywordCallOp(
                    suite_callee,
                    ArrayAttr([StringAttr(n) for n in call_arg_bare_names]),
                    ArrayAttr([StringAttr(n) for n in _result_names]),
                    DictionaryAttr({}),
                    call_args,
                    callee_output_types,
                )
            else:
                call_op = func.CallOp(suite_callee, call_args, callee_output_types)

            # CapVarRefOps for inout-echo returns must be placed BEFORE the call
            # so the printer can resolve their names when processing return positions.
            #
            # Use _get_suite_lifecycle_ret_info to get std_names for alloc returns
            # (intent=out scalars).  Suite cap returns: inout_vals first, then
            # alloc_vals.  Compute the offset so alloc positions are matched by
            # standard_name rather than type, preventing false errflg matches when
            # another intent=out scalar (e.g. const_index) has the same MLIR type.
            _run_ret_alloc = _get_suite_lifecycle_ret_info(
                scheme_names, meta_data, "_run"
            )
            _n_inout_ret = len(callee_output_types) - len(_run_ret_alloc)

            cap_var_inout_refs: list = []
            copy_ops = []
            for idx, ret_type in enumerate(callee_output_types):
                result = call_op.results[idx]
                if idx < _n_inout_ret:
                    # inout return vals: type-match only (no positional info available)
                    if ret_type == errmsg_type:
                        copy_ops.append(memref.CopyOp(result, errmsg_arg))
                    elif ret_type == errflg_type:
                        copy_ops.append(memref.CopyOp(result, errflg_arg))
                    elif (
                        ccpp_t_type is not None
                        and hasattr(ret_type, "element_type")
                        and hasattr(ret_type.element_type, "type_name")
                        and ret_type.element_type.type_name.data == "ccpp_t"
                    ):
                        # ccpp_t is intent(inout) — mirror back to the block arg
                        # so the printer's inout-echo detection fires.
                        copy_ops.append(memref.CopyOp(result, ccpp_data_block_arg))
                else:
                    ri_idx = idx - _n_inout_ret
                    ret_std_name = _run_ret_alloc[ri_idx][2]
                    ret_local_name = _run_ret_alloc[ri_idx][1]
                    if ret_std_name == CCPP_ERROR_MESSAGE:
                        copy_ops.append(memref.CopyOp(result, errmsg_arg))
                    elif ret_std_name == CCPP_ERROR_CODE:
                        copy_ops.append(memref.CopyOp(result, errflg_arg))
                    else:
                        # Non-error scalar out (e.g. const_index).
                        # 1) block arg (e.g. when not host-matched)
                        canonical = non_host_std_to_canonical.get(
                            ret_std_name, ret_local_name
                        ) if ret_std_name else ret_local_name
                        if canonical and canonical in block_arg_map:
                            copy_ops.append(
                                memref.CopyOp(result, block_arg_map[canonical])
                            )
                        elif ret_std_name and ret_std_name in host_var_map:
                            # 2) host module var: write result back to the host.
                            # (intent=out scalars are not in callee_input_names so
                            # no HostVarRefOp exists yet — create one here.)
                            hv_name, hv_module = host_var_map[ret_std_name]
                            hv_ref = HostVarRefOp(hv_name, hv_module, ret_type)
                            cap_var_inout_refs.append(hv_ref)
                            copy_ops.append(memref.CopyOp(result, hv_ref.res))
                            hv_key = (hv_name, hv_module)
                            if hv_key not in seen_host_globals:
                                seen_host_globals.add(hv_key)
                                hv_glob = llvm.GlobalOp(
                                    llvm.LLVMArrayType.from_size_and_type(1, i8),
                                    hv_name, "external",
                                )
                                hv_glob.attributes["module"] = StringAttr(hv_module)
                                chain_global_ops.append(hv_glob)
                        elif cap_var_map:
                            # 3) cap_var inout echo: suite cap returns cap-owned scalar.
                            for i, (a_name, a_type) in enumerate(
                                zip(callee_input_names, callee_input_types)
                            ):
                                if (a_type == ret_type
                                        and resolved_arg_ops[i].source_kind.data
                                        == ArgSourceKind.CapVar):
                                    std_name_cv = resolved_arg_ops[i].std_name.data
                                    cv_name, cv_type, _ = cap_var_map[std_name_cv]
                                    cap_ref = CapVarRefOp(cv_name, a_type)
                                    cap_var_inout_refs.append(cap_ref)
                                    copy_ops.append(memref.CopyOp(result, cap_ref.res))
                                    break

            # Build write-back ops for row-major arrays (inout/out only).
            row_major_write_back_ops: list = []
            for conv_op, host_ref_result, dim_exprs in row_major_write_back_pairs:
                wb_op = RowMajorWriteBackOp(conv_op.res, host_ref_result, dim_exprs)
                row_major_write_back_ops.append(wb_op)

            inner_if_true = (
                cap_var_inout_refs
                + row_major_convert_ops
                + [call_op]
                + copy_ops
                + row_major_write_back_ops
            )

            inner_if = scf.IfOp(
                suite_part_eq.res,
                [],
                [*inner_if_true, scf.YieldOp()],
                part_inner_false,
            )
            part_inner_false = [suite_part_eq, inner_if, scf.YieldOp()]
            suite_host_refs.extend(host_var_ref_ops)
            suite_array_secs.extend(array_section_ops)

            decl = func.FuncOp.external(
                suite_callee, callee_input_types, callee_output_types
            )
            decl.attributes["module"] = StringAttr(callee_module)
            decls.append(decl)

        # Outer if for suite_name (after processing all groups).
        # suite_host_refs and suite_array_secs are placed here (before the
        # suite-part dispatch) so GPUCcppCapPass can find them in true_block.
        true_branch_ops = [trim_suite_part, *suite_host_refs, *suite_array_secs, *part_inner_false[:-1], scf.YieldOp()]
        strcmp_op = StrCmpOp(trim_suite_name.res, literal=suite_name)
        if_op = scf.IfOp(
            strcmp_op.res,
            [],
            true_branch_ops,
            current_false_ops,
        )
        current_false_ops = [strcmp_op, if_op, scf.YieldOp()]

    main_chain_ops = current_false_ops[:-1]
    return main_chain_ops, decls, chain_global_ops

def _assemble_run_fn(
    fn_name: str,
    sig: "_RunBlockSignature",
    pre: "_RunChainPreamble",
    main_chain_ops: list,
    errmsg_type,
    errflg_type,
):
    """Assemble the FuncOp from the block signature, preamble ops, and dispatch chain.

    Determines the return type and preamble based on the host framework
    pattern (ccpp_info_t, ccpp_t, or standard capgen), fills new_block
    with all ops in execution order, and returns a public FuncOp.
    """
    if sig.ccpp_info_type is not None:
        ret_op = func.ReturnOp(sig.ccpp_info_block_arg)  # ccpp_info is inout
        fn_type = builtin.FunctionType.from_lists(
            sig.all_block_types, [sig.ccpp_info_type]
        )
        # Place col_start/col_end/errmsg/errflg HostVarRefOps before dispatch
        preamble_ops = [sig.col_start_ref, sig.col_end_ref, sig.errmsg_alloc, sig.errflg_alloc]
    elif sig.ccpp_t_type is not None:
        ret_op = func.ReturnOp(sig.ccpp_data_block_arg, sig.errmsg_arg, sig.errflg_arg)
        fn_type = builtin.FunctionType.from_lists(
            sig.all_block_types, [sig.ccpp_t_type, errmsg_type, errflg_type]
        )
        preamble_ops = []
    else:
        ret_op = func.ReturnOp(sig.errmsg_arg, sig.errflg_arg)
        fn_type = builtin.FunctionType.from_lists(
            sig.all_block_types, [errmsg_type, errflg_type]
        )
        preamble_ops = []

    sig.new_block.add_ops(
        [
            *preamble_ops,
            pre.err_const,
            pre.store_errflg,
            pre.trim_suite_name,
            *main_chain_ops,
            ret_op,
        ]
    )

    body = Region()
    body.add_block(sig.new_block)
    return func.FuncOp(fn_name, fn_type, body, visibility="public")

def _generate_run_fn(
    fn_name,
    suite_run_entries,
    suite_name_type,
    errmsg_type,
    errflg_type,
    char_base,
    int_base,
    public_fns,
    meta_data,
    cap_var_map=None,
    seen_host_globals=None,
    **kwargs,
):
    """Build the combined CCPP cap physics run FuncOp dispatching over all suites.

    ``suite_run_entries`` is a list of
    ``(suite_name, suite_part, suite_callee, scheme_names)`` tuples.

    The generated function signature uses the union of non-host physics args
    across all suites.  A nested if/else chain on ``suite_name`` dispatches to
    the appropriate suite; each matching branch has an inner if/else on
    ``suite_part``.  Host variable references and array sections are placed
    inside each suite's branch.

    Returns ``(FuncOp, [external_decl_FuncOp, ...], host_global_ops)``.
    """
    for _, _, suite_callee, _ in suite_run_entries:
        assert suite_callee in public_fns, (
            f"Suite callee '{suite_callee}' not found; available: {sorted(public_fns)}"
        )

    suite_part_type = suite_name_type

    # ── Build host variable maps from metadata ─────────────────────────────
    _maps = _build_run_metadata_maps(meta_data)
    host_var_map = _maps.host_var_map
    host_block_std_names = _maps.host_block_std_names
    constituent_std_names = _maps.constituent_std_names
    ddt_type_names = _maps.ddt_type_names
    ddt_instance_map = _maps.ddt_instance_map
    ddt_parent_map = _maps.ddt_parent_map

    # ── Per-suite information ──────────────────────────────────────────────
    # Use the caller-provided seen_host_globals set so GlobalOps are deduplicated
    # across all functions (lifecycle + run) in the same cap module.
    if seen_host_globals is None:
        seen_host_globals = set()
    per_suite, all_host_global_ops = _build_per_suite_run_info(
        suite_run_entries, public_fns, meta_data, _maps, cap_var_map,
        seen_host_globals,
    )

    # ── Block signature ────────────────────────────────────────────────────
    _sig = _build_run_block_signature(
        per_suite, meta_data, kwargs,
        suite_name_type, suite_part_type, errmsg_type, errflg_type, int_base,
    )
    new_block = _sig.new_block
    all_block_types = _sig.all_block_types
    block_arg_map = _sig.block_arg_map
    non_host_std_to_canonical = _sig.non_host_std_to_canonical
    suite_name_arg = _sig.suite_name_arg
    suite_part_arg = _sig.suite_part_arg
    errmsg_arg = _sig.errmsg_arg
    errflg_arg = _sig.errflg_arg
    col_start_ref = _sig.col_start_ref
    col_end_ref = _sig.col_end_ref
    errmsg_alloc = _sig.errmsg_alloc
    errflg_alloc = _sig.errflg_alloc
    ccpp_info_block_arg = _sig.ccpp_info_block_arg
    ccpp_data_block_arg = _sig.ccpp_data_block_arg
    ccpp_info_type = _sig.ccpp_info_type
    ccpp_t_type = _sig.ccpp_t_type

    # ── Dispatch chain preamble ────────────────────────────────────────────
    _pre = _build_run_chain_preamble(
        per_suite, suite_name_arg, errmsg_arg, errflg_arg,
    )
    err_const = _pre.err_const
    store_errflg = _pre.store_errflg
    trim_suite_name = _pre.trim_suite_name
    current_false_ops = _pre.current_false_ops
    all_decls = _pre.all_decls
    per_suite_grouped = _pre.per_suite_grouped

    # ── Build nested if/else chain from inside out ─────────────────────────
    main_chain_ops, all_decls, chain_global_ops = _build_run_dispatch_chain(
        per_suite_grouped=per_suite_grouped,
        trim_suite_name=trim_suite_name,
        suite_part_arg=suite_part_arg,
        errmsg_arg=errmsg_arg,
        errflg_arg=errflg_arg,
        errmsg_type=errmsg_type,
        errflg_type=errflg_type,
        block_arg_map=block_arg_map,
        non_host_std_to_canonical=non_host_std_to_canonical,
        host_var_map=host_var_map,
        meta_data=meta_data,
        cap_var_map=cap_var_map,
        seen_host_globals=seen_host_globals,
        current_false_ops=current_false_ops,
        ccpp_t_type=ccpp_t_type,
        ccpp_data_block_arg=ccpp_data_block_arg,
    )
    all_host_global_ops.extend(chain_global_ops)

    # ── Assemble the function ──────────────────────────────────────────────
    cap_fn = _assemble_run_fn(
        fn_name, _sig, _pre, main_chain_ops, errmsg_type, errflg_type
    )
    return cap_fn, all_decls, all_host_global_ops

def _generate_suite_part_list_fn(
    suite_part_entries,
    inner_char_type,
    allocatable_type,
    suite_name_type,
    errmsg_type,
    errflg_type,
    char_base,
    int_base,
):
    """Build the ccpp_physics_suite_part_list FuncOp for all suites.

    ``suite_part_entries`` is a list of ``(suite_name, [part_names])`` tuples.
    Generates a subroutine with a nested if/else chain that checks suite_name
    and fills part_list with the matching suite's part names.

    Returns (FuncOp, list[llvm.GlobalOp]).
    """
    # Collect ALL unique part names for shared global string constants.
    all_part_names = list(
        dict.fromkeys(
            pn for _, part_names in suite_part_entries for pn in part_names
        )
    )

    part_global_ops = []
    part_global_names: dict = {}
    for pn in all_part_names:
        str_global_name = f"str_{pn}"
        arr_type = llvm.LLVMArrayType.from_size_and_type(len(pn), i8)
        part_global_ops.append(
            llvm.GlobalOp(
                arr_type,
                str_global_name,
                "internal",
                constant=True,
                value=StringAttr(pn),
            )
        )
        part_global_names[pn] = (str_global_name, arr_type)

    new_block = Block(arg_types=[suite_name_type, allocatable_type])
    new_block.args[0].name_hint = "suite_name"
    new_block.args[1].name_hint = "part_list"

    errmsg_alloc = memref.AllocaOp.get(char_base, shape=[CCPP_ERRMSG_LEN])
    errmsg_alloc.memref.name_hint = "errmsg"
    errflg_alloc = memref.AllocaOp.get(int_base, shape=[])
    errflg_alloc.memref.name_hint = "errflg"

    err_const = arith.ConstantOp.from_int_and_width(0, 32)
    store_errflg = memref.StoreOp.get(err_const, errflg_alloc, [])

    trim_suite_name = TrimOp(new_block.args[0])

    # Innermost else: no suite matched
    # Build chain from inside out
    current_false_ops = _build_no_suite_matched_false_ops(
        errmsg_alloc, trim_suite_name.res, errflg_alloc
    )

    for suite_name, part_names in reversed(suite_part_entries):
        strcmp_op = StrCmpOp(trim_suite_name.res, literal=suite_name)

        true_ops = []
        for pn in part_names:
            str_global_name, arr_type = part_global_names[pn]
            str_len_const = arith.ConstantOp(
                IntegerAttr(len(pn), IndexType()), IndexType()
            )
            str_alloc = memref.AllocOp([str_len_const.result], [], inner_char_type)
            addr_op = llvm.AddressOfOp(str_global_name, llvm.LLVMPointerType())
            load_op = llvm.LoadOp(addr_op, arr_type)
            set_str_op = SetStringOp(str_alloc.memref, load_op.dereferenced_value)
            store_ref_op = memref.StoreOp.get(
                str_alloc.memref, new_block.args[1], []
            )
            true_ops.extend(
                [
                    str_len_const,
                    str_alloc,
                    addr_op,
                    load_op,
                    set_str_op,
                    store_ref_op,
                ]
            )
        true_ops.append(scf.YieldOp())

        if_op = scf.IfOp(strcmp_op.res, [], true_ops, current_false_ops)
        current_false_ops = [strcmp_op, if_op, scf.YieldOp()]

    main_chain_ops = current_false_ops[:-1]
    ret_op = func.ReturnOp(errmsg_alloc, errflg_alloc)

    new_block.add_ops(
        [
            errmsg_alloc,
            errflg_alloc,
            err_const,
            store_errflg,
            trim_suite_name,
            *main_chain_ops,
            ret_op,
        ]
    )

    body = Region()
    body.add_block(new_block)

    fn_type = builtin.FunctionType.from_lists(
        [suite_name_type, allocatable_type],
        [errmsg_type, errflg_type],
    )
    suite_part_list_fn = func.FuncOp(
        "ccpp_physics_suite_part_list", fn_type, body, visibility="public"
    )
    return suite_part_list_fn, part_global_ops
