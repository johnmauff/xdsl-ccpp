import sys
from dataclasses import dataclass

from xdsl.context import Context
from xdsl.dialects import arith, builtin, func, llvm, memref, scf
from xdsl.dialects.builtin import (
    DYNAMIC_INDEX,
    ArrayAttr,
    DictionaryAttr,
    IndexType,
    IntegerAttr,
    StringAttr,
    UnitAttr,
    i8,
)
from xdsl.ir import Block, Region
from xdsl.passes import ModulePass
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects import ccpp
from xdsl_ccpp.dialects.ccpp_utils import (
    ArraySectionOp,
    CapVarRefOp,
    DerivedType,
    HostVarRefOp,
    KeywordCallOp,
    RowMajorConvertOp,
    RowMajorWriteBackOp,
    SetStringOp,
    StrCmpOp,
    SuiteVariablesOp,
    TrimOp,
    WriteErrMsgOp,
)
from xdsl_ccpp.transforms.constituent_cap import (
    _collect_constituent_info,
    _generate_constituent_api,
)
from xdsl_ccpp.transforms.lifecycle_cap import _generate_lifecycle_fn
from xdsl_ccpp.transforms.util.cap_shared import (
    _bare,
    _build_host_var_map,
    _get_suite_lifecycle_ret_info,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import (
    BuildMetaDataDescriptions,
    BuildSchemeDescription,
    CCPPType,
    collect_ddt_source_modules,
)
from xdsl_ccpp.transforms.util.ir_utils import find_ccpp_module
from xdsl_ccpp.transforms.util.typing import TypeConversions
from xdsl_ccpp.transforms.util.ccpp_descriptors import XMLSubcycle as _XMLSubcycle
from xdsl_ccpp.util.ccpp_conventions import (
    CCPP_ERROR_CODE,
    CCPP_ERROR_MESSAGE,
    CCPP_ERROR_STD_NAMES,
    CCPP_ERRMSG_LEN,
    CCPP_FRAMEWORK_STD_NAMES,
    CCPP_HORIZ_DIM_STD_NAME,
    CCPP_LOOP_BEGIN_STD_NAME,
    CCPP_LOOP_END_STD_NAME,
    CCPP_LOOP_EXTENT_STD_NAME,
    CCPP_VERT_DIM_STD_NAME,
)


def _iter_schemes(group):
    """Yield all XMLScheme leaves from a group, descending into XMLSubcycle nodes."""
    for child in group:
        if isinstance(child, _XMLSubcycle):
            yield from child
        else:
            yield child


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


def _collect_public_suite_functions(ops):
    """Scan all named ModuleOps in ops and return a map of public function info.

    Returns:
        dict mapping function_name → (module_name, output_types,
        input_types, input_names).
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
                public_fns[child.sym_name.data] = (
                    mod_name,
                    list(child.function_type.outputs),
                    list(child.function_type.inputs),
                    [arg.name_hint for arg in child.body.block.args],
                )
    return public_fns




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


    def _derive_camel_case_name(self, suite_name: str) -> str:
        """Convert a snake_case suite name to CamelCase, stripping any '_suite' suffix."""
        name = suite_name
        if name.endswith("_suite"):
            name = name[:-6]
        return "".join(word.capitalize() for word in name.split("_"))

    def _build_suite_variables_fn(self, suite_descriptions, ccpp_mod,
                                   host_std_names, protected_std_names) -> "SuiteVariablesOp":
        """Build the ccpp_physics_suite_variables subroutine for all suites.

        Scans the MLIR IR directly (ArgumentOp properties) rather than going
        through the descriptor layer, avoiding subtle descriptor-build issues.

        Filtering rules (applied per ArgumentOp):
        - Skip if standard_name belongs to ANY interstitial arg (producer or
          consumer) — collected in a first pass across all scheme tables
        - Skip if standard_name is in _INTERNAL (horizontal_loop_extent only;
          ccpp_constituents / ccpp_constituent_tendencies are physics arrays
          and must appear in the list)
        - Skip if standard_name is in protected_std_names (dimension params)
        - ccpp_error_code/ccpp_error_message always go to output-only
        - advected=.true. args go to both input and output regardless of intent
        - state_variable=true args go to both if scheme units == host units;
          if units differ (unit conversion needed), intent-based rules apply
        - All others go to input/output by declared intent
        - After the main scan a dimension-name sweep adds vars that appear only
          as array dimension sizes (e.g. number_of_ccpp_constituents)
        - Union across all entry points (_init, _run, _finalize, etc.)
        """
        _CCPP_ERR = CCPP_ERROR_STD_NAMES
        # Only the loop-extent scalar is truly framework-internal and excluded.
        # The constituent-array names are real physics arrays and must appear.
        _INTERNAL = frozenset({CCPP_LOOP_EXTENT_STD_NAME})
        CM = 36  # character length matching cm=36 in test driver

        suite_vars: dict = {}
        for suite_name, suite_desc in suite_descriptions.items():
            # Collect the set of scheme names belonging to this suite
            scheme_names: set = set()
            for group in suite_desc:
                for scheme in _iter_schemes(group):
                    scheme_names.add(scheme.attributes["name"])

            # Pass 1a: collect every standard_name that is marked is_interstitial
            # on ANY occurrence.  host_var_match_pass marks the CONSUMER (_run)
            # but not the PRODUCER (_init), so we need the full set to exclude
            # both sides of an intra-suite interstitial (e.g. tcld).
            #
            # Pass 1b: collect state_variable args where ANY scheme in this
            # suite declares the variable in different units than the host.
            # When a unit mismatch exists, the suite cap converts the value
            # in-place (e.g. Pa→hPa) — the host should not treat the returned
            # value as a meaningful physics output.
            interstitial_std_names: set = set()
            state_var_unit_mismatch: set = set()
            for tbl_op in ccpp_mod.body.ops:
                if not isa(tbl_op, ccpp.TablePropertiesOp):
                    continue
                if tbl_op.table_type.data != "scheme":
                    continue
                if tbl_op.table_name.data not in scheme_names:
                    continue
                for arg_table_op in tbl_op.body.ops:
                    if not isa(arg_table_op, ccpp.ArgumentTableOp):
                        continue
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

            input_vars: set = set()
            output_vars: set = set()
            all_dim_names: set = set()

            # Pass 2: build input/output variable sets
            for tbl_op in ccpp_mod.body.ops:
                if not isa(tbl_op, ccpp.TablePropertiesOp):
                    continue
                if tbl_op.table_type.data != "scheme":
                    continue
                if tbl_op.table_name.data not in scheme_names:
                    continue

                # Iterate all entry-point arg tables (_init, _run, _finalize …)
                for arg_table_op in tbl_op.body.ops:
                    if not isa(arg_table_op, ccpp.ArgumentTableOp):
                        continue

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
                        if std_name in _INTERNAL:
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
                        if std_name in _CCPP_ERR:
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

            # Pass 3: add dimension standard names not already covered.
            # Picks up vars like number_of_ccpp_constituents that appear only as
            # array dimension sizes, never as explicit scheme arguments.
            for dim_name in all_dim_names:
                if (dim_name not in _INTERNAL
                        and dim_name not in protected_std_names
                        and dim_name not in interstitial_std_names
                        and dim_name not in input_vars
                        and dim_name not in output_vars
                        and dim_name not in _CCPP_ERR):
                    input_vars.add(dim_name)

            required_vars = input_vars | output_vars
            suite_vars[suite_name] = (
                sorted(input_vars),
                sorted(output_vars),
                sorted(required_vars),
            )

        # Build the complete Fortran subroutine as a Python string
        lines: list[str] = []
        lines.append(
            "subroutine ccpp_physics_suite_variables"
            "(suite_name, var_list, errmsg, errflg, input_vars, output_vars)"
        )
        lines.append("  character(len=*), intent(in) :: suite_name")
        lines.append("  character(len=*), allocatable, intent(out) :: var_list(:)")
        lines.append(f"  character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg")
        lines.append("  integer, intent(out) :: errflg")
        lines.append("  logical, optional, intent(in) :: input_vars")
        lines.append("  logical, optional, intent(in) :: output_vars")
        lines.append("  logical :: do_input, do_output")
        lines.append("  errmsg = ''")
        lines.append("  errflg = 0")
        lines.append("  do_input = .true.")
        lines.append("  do_output = .true.")
        lines.append("  if (present(input_vars)) do_input = input_vars")
        lines.append("  if (present(output_vars)) do_output = output_vars")

        for idx, (suite_name, (in_v, out_v, req_v)) in enumerate(suite_vars.items()):
            kw = "if" if idx == 0 else "else if"
            lines.append(f"  {kw} (trim(suite_name) .eq. '{suite_name}') then")
            for branch_name, var_list in (
                ("input only",  "do_input .and. .not. do_output"),
                ("output only", ".not. do_input .and. do_output"),
                ("required",    None),
            ):
                if branch_name == "input only":
                    lines.append(f"    if ({var_list}) then")
                    vlist = in_v
                elif branch_name == "output only":
                    lines.append(f"    else if ({var_list}) then")
                    vlist = out_v
                else:
                    lines.append("    else")
                    vlist = req_v
                lines.append(f"      allocate(var_list({len(vlist)}))")
                for j, v in enumerate(vlist):
                    lines.append(f"      var_list({j + 1}) = '{v:<{CM}}'")
            lines.append("    end if")

        lines.append("  else")
        lines.append(
            '    write(errmsg, \'(3a)\') "No suite named ", trim(suite_name), " found"'
        )
        lines.append("    errflg = 1")
        lines.append("  end if")
        lines.append("end subroutine ccpp_physics_suite_variables")

        return SuiteVariablesOp("\n".join(lines))


    def _build_run_metadata_maps(self, meta_data) -> "_RunMetadataMaps":
        """Build all host/DDT lookup maps needed by _generate_run_fn.

        Pure read of meta_data — no IR ops created, no side effects.
        """
        host_var_map = _build_host_var_map(meta_data, include_host=False)

        host_block_std_names: set = set()
        for tbl_name, props in meta_data.items():
            if props.getAttr("type") != CCPPType.HOST:
                continue
            if tbl_name not in props.arg_tables:
                continue
            for var in props.getArgTable(tbl_name).getFunctionArguments():
                if var.hasAttr("standard_name"):
                    host_block_std_names.add(var.getAttr("standard_name").lower())

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

        return _RunMetadataMaps(
            host_var_map=host_var_map,
            host_block_std_names=host_block_std_names,
            constituent_std_names=constituent_std_names,
            ddt_type_names=ddt_type_names,
            ddt_instance_map=ddt_instance_map,
            ddt_parent_map=ddt_parent_map,
        )

    def _build_per_suite_run_info(
        self,
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
            physics_arg_sources = []
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
                                physics_arg_sources.append(("block",))
                            else:
                                physics_arg_sources.append(
                                    ("ddt_member", instance_var, instance_module, full_member)
                                )
                        else:
                            print(
                                f"Warning: '{suite_callee}' arg '{arg_name}' "
                                f"(standard_name='{std_name}') matched DDT type "
                                f"'{ddt_type_name}' but no module-level instance was "
                                f"found — treating as a host-caller block argument.",
                                file=sys.stderr,
                            )
                            physics_arg_sources.append(("block",))
                    else:
                        physics_arg_sources.append(("host", host_var, host_mod))
                elif std_name and cap_var_map and std_name in cap_var_map:
                    # Cap-owned module variable (e.g. vmr interstitial DDT)
                    physics_arg_sources.append(("cap_var", std_name))
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
                    physics_arg_sources.append(("block",))

            non_host_args = [
                (callee_input_names[i], callee_input_types[i],
                 std_name_of.get(_bare(callee_input_names[i]),
                                 callee_input_names[i]))
                for i, src in enumerate(physics_arg_sources)
                if src[0] == "block"
                # cap_var sources are cap-internal; don't expose as block args
            ]

            # Collect module-level host global stubs (shared across all suites).
            for i, (_arg_name, _arg_type) in enumerate(
                zip(callee_input_names, callee_input_types)
            ):
                src = physics_arg_sources[i]
                if src[0] == "host":
                    _, host_var_name, host_module_name = src
                    stub_name, stub_module = host_var_name, host_module_name
                elif src[0] == "ddt_member":
                    _, instance_var, instance_module, _member = src
                    stub_name, stub_module = instance_var, instance_module
                elif src[0] == "cap_var":
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
                    "physics_arg_sources": physics_arg_sources,
                    "non_host_args": non_host_args,
                    "std_name_of": std_name_of,
                    "scheme_names": scheme_names,
                    "local_to_array_layout": local_to_array_layout,
                }
            )

        return per_suite, host_global_ops

    def _build_run_block_signature(
        self,
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

    @staticmethod
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

        write_suite_name_err = WriteErrMsgOp(
            errmsg_arg, trim_suite_name.res, "No suite named ", "found"
        )
        one_outer_err = arith.ConstantOp.from_int_and_width(1, 32)
        store_outer_err = memref.StoreOp.get(one_outer_err, errflg_arg, [])

        current_false_ops = [
            write_suite_name_err,
            one_outer_err,
            store_outer_err,
            scf.YieldOp(),
        ]

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
        self,
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
                physics_arg_sources = info["physics_arg_sources"]
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
                    src = physics_arg_sources[i]
                    if src[0] == "host":
                        _, host_var_name, host_module_name = src
                        ref_op = HostVarRefOp(host_var_name, host_module_name, arg_type)
                        host_var_ref_ops.append(ref_op)
                        host_var_ref_results[arg_name] = ref_op.res
                        host_name_to_ref_result[host_var_name] = ref_op.res
                    elif src[0] == "ddt_member":
                        _, instance_var, instance_module, member_name = src
                        # Resolve std_name tokens in subscript to local variable names
                        resolved_member, sub_vars = self._resolve_member_subscripts(
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
                    elif src[0] == "cap_var":
                        _, std_name_cv = src
                        cv_name, cv_type, _ftn = cap_var_map[std_name_cv]
                        _cv_dims = cap_var_std_to_dims.get(std_name_cv, [])
                        if _cv_dims and _cv_dims[0].lower() == CCPP_LOOP_EXTENT_STD_NAME:
                            _cv_rank = (
                                len(list(arg_type.shape.data))
                                if hasattr(arg_type, "shape") else 0
                            )
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
                    src = physics_arg_sources[i]
                    if src[0] == "host":
                        _, host_var_name, host_module_name = src
                        lookup_var, lookup_mod = host_var_name, host_module_name
                    elif src[0] == "ddt_member":
                        _, instance_var, instance_module, member_name = src
                        # For nested paths like "b%x" or "b%x(ncol)", strip the
                        # chain prefix and any array subscripts to get the leaf
                        # member name for the var descriptor lookup.
                        leaf = member_name.rsplit("%", 1)[-1].split("(")[0]
                        lookup_var, lookup_mod = leaf, instance_module
                    elif src[0] == "cap_var":
                        _, std_name_cv = src
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
                    src = physics_arg_sources[i]
                    if src[0] != "host":
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
                    src = physics_arg_sources[i]
                    if src[0] in ("host", "ddt_member", "cap_var"):
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
                if len(call_args) != len(callee_input_types):
                    raise ValueError(
                        f"Signature mismatch for '{suite_callee}': "
                        f"generated {len(call_args)} input arg(s) but callee expects "
                        f"{len(callee_input_types)}.\n"
                        f"  Callee inputs:   {callee_input_names}\n"
                        f"  Generated args:  {[str(a) for a in call_args]}"
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
                                            and physics_arg_sources[i][0] == "cap_var"):
                                        _, std_name_cv = physics_arg_sources[i]
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

    @staticmethod
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

    @staticmethod
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

    def _generate_run_fn(
        self,
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
        _maps = self._build_run_metadata_maps(meta_data)
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
        per_suite, all_host_global_ops = self._build_per_suite_run_info(
            suite_run_entries, public_fns, meta_data, _maps, cap_var_map,
            seen_host_globals,
        )

        # ── Block signature ────────────────────────────────────────────────────
        _sig = self._build_run_block_signature(
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
        _pre = self._build_run_chain_preamble(
            per_suite, suite_name_arg, errmsg_arg, errflg_arg,
        )
        err_const = _pre.err_const
        store_errflg = _pre.store_errflg
        trim_suite_name = _pre.trim_suite_name
        current_false_ops = _pre.current_false_ops
        all_decls = _pre.all_decls
        per_suite_grouped = _pre.per_suite_grouped

        # ── Build nested if/else chain from inside out ─────────────────────────
        main_chain_ops, all_decls, chain_global_ops = self._build_run_dispatch_chain(
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
        cap_fn = self._assemble_run_fn(
            fn_name, _sig, _pre, main_chain_ops, errmsg_type, errflg_type
        )
        return cap_fn, all_decls, all_host_global_ops

    def _generate_suite_part_list_fn(
        self,
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
        write_err = WriteErrMsgOp(
            errmsg_alloc, trim_suite_name.res, "No suite named ", " found"
        )
        one_err = arith.ConstantOp.from_int_and_width(1, 32)
        store_errflg_err = memref.StoreOp.get(one_err, errflg_alloc, [])

        # Build chain from inside out
        current_false_ops = [write_err, one_err, store_errflg_err, scf.YieldOp()]

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

        lifecycle_specs = [
            ("_ccpp_physics_register", "_register", "_suite_register", None),
            ("_ccpp_physics_initialize", "_init", "_suite_initialize", None),
            ("_ccpp_physics_finalize", "_finalize", "_suite_finalize", None),
            ("_ccpp_physics_timestep_initial", "_timestep_initialize", "_suite_timestep_initial", None),
            ("_ccpp_physics_timestep_final", "_timestep_finalize", "_suite_timestep_final", None),
            # Run: per-group dispatch — each group calls its own suite cap function.
            ("_ccpp_physics_run", None, "_suite_", "__per_group__"),
        ]

        all_globals: list = []
        all_definitions: list = []
        all_declarations: list = []
        # Shared across ALL function calls (lifecycle AND run) to avoid duplicate GlobalOps.
        # Both lifecycle and run functions can reference the same host variables (e.g.
        # a DDT instance used in the run function may also appear in lifecycle functions).
        shared_seen_host_globals: set = set()

        # ── Build cap_var_map: interstitial DDT values returned from lifecycle ──
        # These need module-level storage in the cap so they persist between calls.
        # Format: standard_name → (var_name, mlir_type, fortran_type_str)
        # Also build host_var_map_lc for identifying host-var returns (write-back).
        cap_var_map: dict = {}
        # MODULE only: write-back targets (like num_model_times) live in MODULE
        # tables.  HOST-type tables are caller-provided interfaces, not modules.
        host_var_map_lc = _build_host_var_map(meta_data, include_host=False)

        # ── Pre-populate cap_var_map for framework-managed and scheme-scratch arrays ──
        # Framework arrays (ccpp_constituents, ccpp_constituent_tendencies) are owned by
        # the cap module.  Scheme-specific scratch arrays with no host metadata match
        # (e.g. tendency_of_cloud_liquid_dry_mixing_ratio) are also allocated at cap
        # module scope so they never appear as physics_run block arguments.
        _FRAMEWORK_TO_CAP_VAR = {
            "ccpp_constituents": "lc_constituent_array",
            "ccpp_constituent_tendencies": "lc_const_tend",
        }
        _host_block_std: set = set()
        for _tbl_cv, _props_cv in meta_data.items():
            if _props_cv.getAttr("type") != CCPPType.HOST:
                continue
            if _tbl_cv not in _props_cv.arg_tables:
                continue
            for _var_cv in _props_cv.getArgTable(_tbl_cv).getFunctionArguments():
                if _var_cv.hasAttr("standard_name"):
                    _host_block_std.add(_var_cv.getAttr("standard_name").lower())
        _DIM_TO_ALLOC = {
            CCPP_LOOP_EXTENT_STD_NAME: "ncols",
            CCPP_HORIZ_DIM_STD_NAME: "ncols",
            CCPP_VERT_DIM_STD_NAME: "pver",
            "number_of_ccpp_constituents": "lc_num",
        }
        scratch_var_list: list = []
        scratch_var_seen: set = set()
        for _sn_cv, _sd_cv in suite_descriptions.items():
            for _grp_cv in _sd_cv:
                _grp_name_cv = _grp_cv.attributes["name"]
                _callee_cv = _sn_cv + "_suite_" + _grp_name_cv
                if _callee_cv not in public_fns:
                    continue
                _, _, _ci_types, _ci_names = public_fns[_callee_cv]
                _grp_schemes = [_s.attributes["name"] for _s in _grp_cv]
                _sno_cv: dict = {}
                _dno_cv: dict = {}
                _cno_cv: dict = {}  # bare_name → True when constituent=True
                _matched_cv: set = set()
                for _scheme_cv in _grp_schemes:
                    _run_tbl_cv = _scheme_cv + "_run"
                    if _scheme_cv not in meta_data:
                        continue
                    if _run_tbl_cv not in meta_data[_scheme_cv].arg_tables:
                        continue
                    for _fa_cv in (
                        meta_data[_scheme_cv].getArgTable(_run_tbl_cv).getFunctionArguments()
                    ):
                        _bn_cv = _bare(_fa_cv.name)
                        if _bn_cv not in _sno_cv and _fa_cv.hasAttr("standard_name"):
                            _sno_cv[_bn_cv] = _fa_cv.getAttr("standard_name").lower()
                        if _bn_cv not in _dno_cv and _fa_cv.hasAttr("dim_names"):
                            _dno_cv[_bn_cv] = _fa_cv.getAttr("dim_names")
                        if _fa_cv.hasAttr("constituent"):
                            _cno_cv[_bn_cv] = True
                        if _fa_cv.hasAttr("model_var_name"):
                            _matched_cv.add(_bn_cv)
                for _an_cv, _at_cv in zip(_ci_names, _ci_types):
                    _bn_cv = _bare(_an_cv)
                    if _bn_cv in _matched_cv:
                        continue  # host-matched (including DDT members)
                    _std_cv = _sno_cv.get(_bn_cv)
                    if not _std_cv:
                        continue
                    if _std_cv in _FRAMEWORK_TO_CAP_VAR:
                        if _std_cv not in cap_var_map:
                            cap_var_map[_std_cv] = (_FRAMEWORK_TO_CAP_VAR[_std_cv], None, None)
                        continue
                    if (_std_cv in CCPP_FRAMEWORK_STD_NAMES
                            or _std_cv in CCPP_ERROR_STD_NAMES
                            or _std_cv in _host_block_std
                            or _std_cv in host_var_map_lc):
                        continue
                    if _std_cv not in scratch_var_seen:
                        scratch_var_seen.add(_std_cv)
                        _lc_cv = f"lc_{_bn_cv}"
                        _rank_cv = (
                            len(list(_at_cv.shape.data))
                            if hasattr(_at_cv, "shape") else 0
                        )
                        _dims_cv = _dno_cv.get(_bn_cv, [])
                        _alloc_cv = ", ".join(
                            _DIM_TO_ALLOC.get(_d.lower(), "1") for _d in _dims_cv
                        ) if _dims_cv else "ncols, pver"
                        # Constituent-tendency scratch vars (constituent=True in meta)
                        # are pointer slices into lc_const_tend, not separate allocatables.
                        _const_std_name = None
                        if _cno_cv.get(_bn_cv) and _std_cv.startswith("tendency_of_"):
                            _const_std_name = _std_cv[len("tendency_of_"):]
                        cap_var_map[_std_cv] = (_lc_cv, None, None)
                        scratch_var_list.append((_lc_cv, _rank_cv, _alloc_cv, _const_std_name))

        # Detect the ccpp_info_t pattern: HOST table contains a variable with
        # standard_name = host_standard_ccpp_type (e.g. ddthost).  When present,
        # lifecycle and run functions accept a single ccpp_info_t inout arg that
        # bundles errmsg/errflg and (for run) col_start/col_end.
        ccpp_info_type = None
        ccpp_info_module_name = None
        for _tbl, _props in meta_data.items():
            if _props.getAttr("type") != CCPPType.HOST:
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

        # Detect CcppHandleOp for ccpp_t threading through generated subroutines.
        ccpp_t_type = None
        ccpp_t_var_name = None
        if ccpp_mod is not None and ccpp_info_type is None:
            for _op in ccpp_mod.body.block.ops:
                if isa(_op, ccpp.CcppHandleOp):
                    ccpp_t_type = memref.MemRefType(DerivedType("ccpp_t"), [])
                    ccpp_t_var_name = _op.var_name.data
                    break

        errmsg_type_tmp = memref.MemRefType(
            TypeConversions.getBaseType("character"), [CCPP_ERRMSG_LEN]
        )
        errflg_type_tmp = memref.MemRefType(
            TypeConversions.getBaseType("integer"), []
        )
        for _, table_postfix, callee_suffix, suite_part in lifecycle_specs:
            if suite_part is not None or table_postfix is None:
                continue  # only init/finalize produce cap-owned returns
            for suite_name, suite_desc in suite_descriptions.items():
                suite_callee = suite_name + callee_suffix
                if suite_callee not in public_fns:
                    continue
                scheme_names_lc = [
                    s.attributes["name"]
                    for g in suite_desc for s in g
                ]
                ret_info = _get_suite_lifecycle_ret_info(
                    scheme_names_lc, meta_data, table_postfix
                )
                for ret_type, arg_name, std_name in ret_info:
                    if ret_type in (errmsg_type_tmp, errflg_type_tmp):
                        continue
                    if std_name in host_var_map_lc:
                        continue  # host var — will be written back, not cap-owned
                    # DDT interstitials (e.g. vmr_type) are now declared at suite
                    # cap module scope by generateSuiteModuleOp.  The top-level cap
                    # no longer needs to track or pass them via cap_var_map.

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
                        # Per-group callee: e.g. temp_suite_suite_physics1
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

                cap_fn, decls, host_global_ops = self._generate_run_fn(
                    fn_name=camel_name + fn_suffix,
                    suite_run_entries=suite_run_entries,
                    meta_data=meta_data,
                    cap_var_map=cap_var_map,
                    seen_host_globals=shared_seen_host_globals,
                    ccpp_info_type=ccpp_info_type,
                    ccpp_info_module=ccpp_info_module_name,
                    ccpp_t_type=ccpp_t_type,
                    ccpp_t_var_name=ccpp_t_var_name,
                    **common,
                )
                all_globals.extend(host_global_ops)
                all_declarations.extend(decls)
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
                            _, call_ret_types, _, _ = public_fns[suite_callee]
                            ret_info = [(t, None, None) for t in call_ret_types]
                    else:
                        _, call_ret_types, _, _ = public_fns[suite_callee]
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
                    fn_name=camel_name + fn_suffix,
                    suite_entries=suite_entries,
                    meta_data=meta_data,
                    seen_host_globals=shared_seen_host_globals,
                    cap_var_map=cap_var_map,
                    host_var_map_lc=host_var_map_lc,
                    ccpp_info_type=ccpp_info_type,
                    ccpp_info_module=ccpp_info_module_name,
                    ccpp_t_type=ccpp_t_type,
                    ccpp_t_var_name=ccpp_t_var_name,
                    **common,
                )
                all_globals.extend(lc_host_ops)
                all_declarations.extend(decls)

            all_definitions.append(cap_fn)
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

        suite_part_list_fn, part_global_ops = self._generate_suite_part_list_fn(
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

        # Generate constituent registration API if any scheme has constituent arrays
        # or if there are cap-owned scratch arrays (framework-managed or scheme-scratch).
        dyn_names, fixed_adv = _collect_constituent_info(meta_data)
        if dyn_names or fixed_adv or scratch_var_list:
            const_var_ops, const_api_op, const_global_stubs = _generate_constituent_api(
                camel_name, dyn_names, fixed_adv, scratch_vars=scratch_var_list
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

        # Emit USE-association stubs for DDT types used in any scheme across all suites.
        if ddt_source_module:
            primitive_types = {"real", "integer", "character", "logical", "complex"}
            seen_type_imports: set[str] = set()
            for props in meta_data.values():
                for arg_table in props.arg_tables.values():
                    for arg in arg_table.getFunctionArguments():
                        if not arg.hasAttr("type"):
                            continue
                        arg_type = arg.getAttr("type")
                        if arg_type in primitive_types or arg_type in seen_type_imports:
                            continue
                        mod = ddt_source_module.get(arg_type)
                        if mod is None:
                            continue
                        seen_type_imports.add(arg_type)
                        stub = llvm.GlobalOp(
                            llvm.LLVMArrayType.from_size_and_type(0, i8),
                            arg_type,
                            "internal",
                        )
                        stub.attributes["module"] = StringAttr(mod)
                        all_globals.append(stub)

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
        host_std_names: dict[str, str | None] = {}
        for tbl_op in ccpp_mod.body.ops:
            if not isa(tbl_op, ccpp.TablePropertiesOp):
                continue
            if tbl_op.table_type.data == "scheme":
                continue
            for arg_table_op in tbl_op.body.ops:
                if not isa(arg_table_op, ccpp.ArgumentTableOp):
                    continue
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
        protected_std_names: set[str] = set()
        for tbl_op in ccpp_mod.body.ops:
            if not isa(tbl_op, ccpp.TablePropertiesOp):
                continue
            if tbl_op.table_type.data not in ("module", "host", "ddt"):
                continue
            for arg_table_op in tbl_op.body.ops:
                if not isa(arg_table_op, ccpp.ArgumentTableOp):
                    continue
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
