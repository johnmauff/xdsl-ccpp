from dataclasses import dataclass

from xdsl.context import Context
from xdsl.dialects import arith, builtin, func, llvm, memref
from xdsl.dialects.builtin import (
    DYNAMIC_INDEX,
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
    DerivedType,
    SetStringOp,
    SuiteVariablesOp,
)
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
    CCPP_ERROR_STD_NAMES,
    CCPP_ERRMSG_LEN,
    CCPP_FRAMEWORK_STD_NAMES,
    CCPP_HORIZ_DIM_STD_NAME,
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






def _build_cap_var_map(meta_data, suite_descriptions, public_fns) -> "tuple[dict, dict, list]":
    """Build cap_var_map: interstitial DDT values returned from lifecycle.

    These need module-level storage in the cap so they persist between calls.
    Pre-populates cap_var_map for framework-managed arrays (ccpp_constituents,
    ccpp_constituent_tendencies) and scheme-scratch arrays with no host
    metadata match (e.g. tendency_of_cloud_liquid_dry_mixing_ratio) -- both
    are allocated at cap module scope so they never appear as physics_run
    block arguments.

    This is a separate, later-stage heuristic from suite_cap.py's
    _is_framework_managed: that one decides the suite's own subroutine
    signature (by is_interstitial/advected/allocatable attributes) *before*
    the signature exists; this one re-scans the suite's already-built public
    signature (public_fns) and catches whatever's left unresolved once
    host-var matching has also run. The two are not meant to compute the
    same thing -- see the Phase 4 plan notes for why they aren't merged.

    Returns:
        (cap_var_map, host_var_map_lc, scratch_var_list):
          - cap_var_map: standard_name -> (var_name, mlir_type, fortran_type_str)
          - host_var_map_lc: standard_name -> (var_name, table_name), MODULE tables only
          - scratch_var_list: [(var_name, rank, alloc_dims_str, const_std_name_or_None)]
    """
    cap_var_map: dict = {}
    # MODULE only: write-back targets (like num_model_times) live in MODULE
    # tables.  HOST-type tables are caller-provided interfaces, not modules.
    host_var_map_lc = _build_host_var_map(meta_data, include_host=False)

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
            _grp_schemes = [_s.attributes["name"] for _s in _iter_schemes(_grp_cv)]
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

    return cap_var_map, host_var_map_lc, scratch_var_list


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

        cap_var_map, host_var_map_lc, scratch_var_list = _build_cap_var_map(
            meta_data, suite_descriptions, public_fns
        )

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

                cap_fn, decls, host_global_ops = _generate_run_fn(
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
