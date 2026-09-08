"""Constituent-API generation.

Extracted from ccpp_cap.py's CCPPCAP pass (Phase 2 of the restructuring plan):
builds the runtime constituent registration/query API for a suite. Kept as a
plain importable module (not a registered pass) per the phase plan -- called
directly from generate-ccpp-cap's final module assembly.
"""

from xdsl.dialects import llvm
from xdsl.dialects.builtin import StringAttr, i8

from xdsl_ccpp.dialects.ccpp_utils import (
    CamHostConstituentApiOp,
    ConstituentApiOp,
    ConstituentFunctionOp,
    ModuleVarOp,
    NonCamHostConstituentApiOp,
    RawFortranLinesOp,
)
from xdsl_ccpp.transforms.util.cap_shared import _CCPP_CONSTITUENT_MOD, _bare
from xdsl_ccpp.transforms.util.ccpp_descriptors import CCPPType
from xdsl_ccpp.util.ccpp_conventions import CCPP_ERRMSG_LEN


def _collect_constituent_info(meta_data):
    """Extract constituent info from scheme metadata.

    Scans all SCHEME tables to find:
      - dynamic_array_names: bare arg names in _register tables with
        allocatable=True, type=ccpp_constituent_properties_t
      - fixed_advected: list of (std_name, units, default_val, local_name) for args
        with advected=.true. in non-register scheme tables
      - references_count: True if any scheme arg anywhere declares
        standard_name=number_of_ccpp_constituents. Needed as its own signal
        (not folded into dynamic_array_names/fixed_advected, which this
        value doesn't overlap with in general) because
        FRAMEWORK_STD_NAME_TO_CAP_VAR (cap_shared.py) resolves that
        standard_name to size(lc_all_constituents) unconditionally --
        ccpp_cap.py's own constituent-API emission gate needs to know to
        emit lc_all_constituents whenever that resolution could actually be
        used, even for a hypothetical suite referencing the count with no
        dynamic registration or fixed-advected constituent of its own
        (Copilot review comment on PR #67, 2026-08-14: confirmed this gate
        previously had no such check, so that suite would silently reference
        an undeclared Fortran symbol and fail to compile).

    Returns (dynamic_array_names, fixed_advected, references_count).
    """
    dynamic_array_names: list = []
    fixed_advected: list = []
    seen_fixed: set = set()
    references_count = False

    for _scheme_name, props in meta_data.items():
        if props.getAttr("type") != CCPPType.SCHEME:
            continue
        for table_name, arg_table in props.arg_tables.items():
            is_register = table_name.endswith("_register")
            for fn_arg in arg_table.getFunctionArguments():
                if (
                    fn_arg.hasAttr("standard_name")
                    and fn_arg.getAttr("standard_name").lower()
                        == "number_of_ccpp_constituents"
                ):
                    references_count = True
                if (
                    is_register
                    and fn_arg.hasAttr("allocatable")
                    and fn_arg.hasAttr("type")
                    and fn_arg.getAttr("type").lower() == "ccpp_constituent_properties_t"
                ):
                    bare = _bare(fn_arg.name)
                    if bare not in dynamic_array_names:
                        dynamic_array_names.append(bare)
                elif (
                    not is_register
                    and fn_arg.hasAttr("advected")
                    and fn_arg.hasAttr("standard_name")
                ):
                    std_name = fn_arg.getAttr("standard_name").lower()
                    units = (
                        fn_arg.getAttr("units")
                        if fn_arg.hasAttr("units")
                        else "kg kg-1"
                    )
                    default_val = (
                        fn_arg.getAttr("default_value")
                        if fn_arg.hasAttr("default_value")
                        else None
                    )
                    # Use local variable name as diagnostic name, matching
                    # capgen-v1's local_name_to_diag_name default.
                    local_name = _bare(fn_arg.name)
                    if std_name not in seen_fixed:
                        seen_fixed.add(std_name)
                        fixed_advected.append((std_name, units, default_val, local_name))

    # Filter: drop wrt_dry_air constituents when the corresponding
    # wrt_moist_air_and_condensed_water form is also registered.  In
    # CAM-SIMA the dry-air form is a derived representation (produced by
    # wet_to_dry_* converter schemes) not an independent advected tracer;
    # keeping both would register duplicate constituent slots and pass a
    # blank diag_name for the dry form to sima_state_diagnostics, causing
    # a runtime crash.  This matches capgen-v1 behavior, which derives the
    # constituent list from the host model registry (moist forms only).
    moist_names = {
        s for s, *_ in fixed_advected
        if "_wrt_moist_air_and_condensed_water" in s
    }
    fixed_advected = [
        entry for entry in fixed_advected
        if not (
            entry[0].endswith("_wrt_dry_air")
            and entry[0].replace("_wrt_dry_air",
                                 "_wrt_moist_air_and_condensed_water")
            in moist_names
        )
    ]

    return dynamic_array_names, fixed_advected, references_count


def _generate_constituent_api_cam_host(
    camel_name: str,
    dynamic_array_names: list,
    fixed_advected: list,
    scratch_vars: "list | None" = None,
    needs_const_tend: bool = False,
):
    """Generate constituent API using the real ccpp_model_constituents_t container.

    Used when cam_host=True. Generates subroutines that delegate to
    ccpp_model_constituents_t methods (initialize_table, new_field, lock_table,
    lock_data, field_data_ptr, constituent_props_ptr, num_constituents,
    const_index, copy_in, copy_out) instead of the raw-array approach used for
    non-CAM builds.

    scratch_vars: list of (lc_name, rank, alloc_dims_str, const_std_name, needs_gpu)
        tuples for CapScratch variables that are not framework-managed (e.g. lc_qtnd).
        These are declared as module-level allocatable arrays and allocated in
        initialize_constituents.  const_std_name is non-None only for constituent-
        tendency pointer slices (which resolve into lc_const_tend, not a separate array).
    needs_const_tend: True when the suite uses ccpp_constituent_tendencies (lc_const_tend);
        declares and allocates the 3-D tendency array alongside lc_constituent_array.
    """
    h = camel_name
    n_fixed = len(fixed_advected)

    # ── Module-level variable declarations ──────────────────────────────
    module_var_ops: list = []
    module_var_ops.append(
        ModuleVarOp(
            "cam_constituents_obj", "type",
            ddt_name="ccpp_model_constituents_t", is_target=True, rank=0
        )
    )
    for n in dynamic_array_names:
        module_var_ops.append(
            ModuleVarOp(
                f"lc_{n}", "type",
                ddt_name="ccpp_constituent_properties_t", is_target=True, rank=1
            )
        )
    # lc_const_props is referenced by the lifecycle wrappers (ccpp_physics_run,
    # ccpp_physics_init, etc.) and must exist as a module-level variable.  Populated
    # in initialize_constituents from cam_constituents_obj%constituent_props_ptr().
    module_var_ops.append(
        ModuleVarOp(
            "lc_const_props", "type",
            ddt_name="ccpp_constituent_prop_ptr_t", is_target=True, rank=1
        )
    )

    # lc_all_constituents is referenced as size(lc_all_constituents) by lifecycle
    # wrappers for the number_of_ccpp_constituents argument.  A plain integer array
    # (allocated to the constituent count) satisfies the size() expression without
    # needing the full ccpp_constituent_properties_t type.
    # lc_constituent_array is referenced by the ccpp_physics_run dispatcher as the
    # constituent data slice; must be a pointer into cam_constituents_obj storage.
    # Also emit the fixed constituent name/index arrays when present.
    module_var_ops.append(ModuleVarOp("lc_all_constituents", "integer", rank=1))
    module_var_ops.append(
        ModuleVarOp("lc_constituent_array", "real", kind="kind_phys", is_pointer=True, rank=3)
    )
    if needs_const_tend:
        module_var_ops.append(
            ModuleVarOp("lc_const_tend", "real", kind="kind_phys", is_target=True, rank=3)
        )
    for lc_name, rank, _alloc_dims, const_std_name, _needs_gpu in (scratch_vars or []):
        if const_std_name is None:  # non-constituent scratch: allocatable
            module_var_ops.append(ModuleVarOp(lc_name, "real", kind="kind_phys", rank=rank))
        else:  # constituent-tendency scratch: pointer slice into lc_const_tend
            module_var_ops.append(
                ModuleVarOp(lc_name, "real", kind="kind_phys", is_pointer=True, rank=rank)
            )
    if n_fixed > 0:
        max_std_len = max(len(s) for s, *_ in fixed_advected)
        names_parts = [f"'{s}'" for s, *_ in fixed_advected]
        names_str = (names_parts[0] if n_fixed == 1
                     else ", &\n      ".join(names_parts))
        module_var_ops.append(ModuleVarOp(
            "cam_model_const_stdnames", "character",
            kind=str(max_std_len),
            fixed_dim=n_fixed,
            init_value=f"[ character(len={max_std_len}) :: {names_str} ]",
        ))
        module_var_ops.append(ModuleVarOp(
            "cam_model_const_indices", "integer",
            fixed_dim=n_fixed,
            init_value="-1",
        ))

    # ── 1. is_scheme_constituent ─────────────────────────────────────────
    isc_body = [
        "errflg = 0",
        "errmsg = ''",
        "is_const = .false.",
    ]
    if n_fixed > 0:
        isc_body += [
            "if (any(cam_model_const_stdnames == std_name)) then",
            "  is_const = .true.",
            "end if",
        ]
    isc_op = ConstituentFunctionOp(
        fn_name=f"{h}_ccpp_is_scheme_constituent",
        is_function=False,
        args=["std_name", "is_const", "errflg", "errmsg"],
        use_stmts=[],
        arg_decls=[
            "character(len=*), intent(in) :: std_name",
            "logical, intent(out) :: is_const",
            "integer, intent(out) :: errflg",
            f"character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
        ],
        local_decls=[],
        body_ops=[RawFortranLinesOp("\n".join(isc_body))],
    )

    # ── 2. deallocate_dynamic_constituents ───────────────────────────────
    da_body = []
    for n in dynamic_array_names:
        da_body.append(f"if (allocated(lc_{n})) deallocate(lc_{n})")
    if needs_const_tend:
        da_body.append("if (allocated(lc_const_tend)) deallocate(lc_const_tend)")
    for lc_name, _, _, const_std_name, _ in (scratch_vars or []):
        if const_std_name is None:
            da_body.append(f"if (allocated({lc_name})) deallocate({lc_name})")
        else:
            da_body.append(f"nullify({lc_name})")
    da_body.append("call cam_constituents_obj%reset()")
    da_op = ConstituentFunctionOp(
        fn_name=f"{h}_ccpp_deallocate_dynamic_constituents",
        is_function=False,
        args=[],
        use_stmts=[],
        arg_decls=[],
        local_decls=[],
        body_ops=[RawFortranLinesOp("\n".join(da_body))] if da_body else [],
    )

    # ── 3. register_constituents ─────────────────────────────────────────
    rc_body = [
        "errcode = 0",
        "errmsg = ''",
        "lc_num_consts = size(host_constituents, 1)",
    ]
    for n in dynamic_array_names:
        rc_body.append(
            f"if (allocated(lc_{n})) lc_num_consts = lc_num_consts + size(lc_{n})"
        )
    rc_body += [
        f"lc_num_consts = lc_num_consts + {n_fixed}",
        "call cam_constituents_obj%initialize_table(lc_num_consts)",
        "do lc_i = 1, size(host_constituents, 1)",
        "  const_prop => host_constituents(lc_i)",
        "  call cam_constituents_obj%new_field(const_prop, errcode=errcode, errmsg=errmsg)",
        "  nullify(const_prop)",
        "  if (errcode /= 0) return",
        "end do",
    ]
    for n in dynamic_array_names:
        rc_body += [
            f"if (allocated(lc_{n})) then",
            f"  do lc_i = 1, size(lc_{n})",
            f"    const_prop => lc_{n}(lc_i)",
            f"    call cam_constituents_obj%new_field(const_prop, errcode=errcode, errmsg=errmsg)",
            f"    nullify(const_prop)",
            f"    if (errcode /= 0) return",
            f"  end do",
            f"end if",
        ]
    for std_name_f, units_f, default_val_f, local_name_f in fixed_advected:
        long_name_f = std_name_f.replace('_', ' ').capitalize()
        extra = f", default_value={default_val_f}" if default_val_f is not None else ""
        rc_body += [
            "allocate(const_prop, stat=errcode)",
            "if (errcode /= 0) then",
            "  errmsg = 'ERROR allocating const_prop'",
            "  return",
            "end if",
            f"call const_prop%instantiate( &",
            f"    std_name='{std_name_f}', &",
            f"    long_name='{long_name_f}', &",
            f"    diag_name='{local_name_f}', units='{units_f}', &",
            f"    vertical_dim='vertical_layer_dimension', &",
            f"    advected=.true.{extra}, errcode=errcode, errmsg=errmsg)",
            "if (errcode /= 0) return",
            "call cam_constituents_obj%new_field(const_prop, errcode=errcode, errmsg=errmsg)",
            "nullify(const_prop)",
            "if (errcode /= 0) return",
        ]
    rc_body += [
        "call cam_constituents_obj%lock_table(errcode=errcode, errmsg=errmsg)",
        "if (errcode /= 0) return",
    ]
    if n_fixed > 0:
        rc_body += [
            "do lc_i = 1, size(cam_model_const_indices)",
            "  call cam_constituents_obj%const_index(field_ind, cam_model_const_stdnames(lc_i), &",
            "      errcode=errcode, errmsg=errmsg)",
            "  if (errcode /= 0) return",
            "  if (field_ind > 0) then",
            "    cam_model_const_indices(lc_i) = field_ind",
            "  else",
            "    errcode = 1",
            "    errmsg = 'No field index for '//trim(cam_model_const_stdnames(lc_i))",
            "    return",
            "  end if",
            "end do",
        ]
    rc_op = ConstituentFunctionOp(
        fn_name=f"{h}_ccpp_register_constituents",
        is_function=False,
        args=["host_constituents", "errcode", "errmsg"],
        use_stmts=["use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t"],
        arg_decls=[
            "type(ccpp_constituent_properties_t), target, intent(in) :: host_constituents(:)",
            "integer, intent(out) :: errcode",
            f"character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
        ],
        local_decls=[
            "integer :: lc_i, lc_num_consts, field_ind",
            "type(ccpp_constituent_properties_t), pointer :: const_prop",
        ],
        body_ops=[RawFortranLinesOp("\n".join(rc_body))],
    )

    # ── 4. number_constituents ───────────────────────────────────────────
    nc_op = ConstituentFunctionOp(
        fn_name=f"{h}_ccpp_number_constituents",
        is_function=False,
        args=["num_advected", "errmsg", "errcode", "advected"],
        use_stmts=[],
        arg_decls=[
            "integer, intent(out) :: num_advected",
            f"character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
            "integer, intent(out) :: errcode",
            "logical, optional, intent(in) :: advected",
        ],
        local_decls=[],
        body_ops=[RawFortranLinesOp(
            "call cam_constituents_obj%num_constituents(num_advected, advected=advected, &\n"
            "    errcode=errcode, errmsg=errmsg)"
        )],
    )

    # ── 5. initialize_constituents ───────────────────────────────────────
    ic_body = [
        "call cam_constituents_obj%lock_data(ncols, pver, errcode=errflg, errmsg=errmsg)",
        "if (errflg /= 0) return",
        "call ccpp_initialize_constituent_ptr(cam_constituents_obj)",
        "lc_constituent_array => cam_constituents_obj%field_data_ptr()",
        "lc_const_props = cam_constituents_obj%constituent_props_ptr()",
        "if (allocated(lc_all_constituents)) deallocate(lc_all_constituents)",
        "allocate(lc_all_constituents(size(lc_const_props)))",
    ]
    if needs_const_tend:
        ic_body += [
            "if (allocated(lc_const_tend)) deallocate(lc_const_tend)",
            "allocate(lc_const_tend(ncols, pver, size(lc_const_props)))",
            "lc_const_tend = 0.0_kind_phys",
        ]
    for lc_name, rank, alloc_dims_str, const_std_name, _ in (scratch_vars or []):
        if const_std_name is None:
            alloc_str = alloc_dims_str.replace("lc_num", "size(lc_const_props)")
            ic_body += [
                f"if (allocated({lc_name})) deallocate({lc_name})",
                f"allocate({lc_name}({alloc_str}))",
            ]
        else:
            # Constituent-tendency scratch: pointer slice into lc_const_tend.
            ic_body += [
                "block",
                "  integer :: lc_tend_idx",
                "  character(len=512) :: lc_tend_errmsg",
                f"  nullify({lc_name})",
                f"  call cam_constituents_obj%const_index(lc_tend_idx, '{const_std_name}', &",
                "      errcode=errflg, errmsg=lc_tend_errmsg)",
                "  if (errflg == 0 .and. lc_tend_idx > 0) then",
                f"    {lc_name} => lc_const_tend(:, :, lc_tend_idx)",
                "  else",
                "    errflg = 0",
                "  end if",
                "end block",
            ]
    ic_op = ConstituentFunctionOp(
        fn_name=f"{h}_ccpp_initialize_constituents",
        is_function=False,
        args=["ncols", "pver", "errflg", "errmsg"],
        use_stmts=["use ccpp_scheme_utils, only: ccpp_initialize_constituent_ptr"],
        arg_decls=[
            "integer, intent(in) :: ncols",
            "integer, intent(in) :: pver",
            "integer, intent(out) :: errflg",
            f"character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
        ],
        local_decls=[],
        body_ops=[RawFortranLinesOp("\n".join(ic_body))],
    )

    # ── 6. constituents_array ────────────────────────────────────────────
    ca_op = ConstituentFunctionOp(
        fn_name=f"{h}_constituents_array",
        is_function=True,
        args=[],
        use_stmts=[],
        arg_decls=[],
        local_decls=[],
        result_name="ptr",
        result_decl="real(kind=kind_phys), pointer :: ptr(:, :, :)",
        body_ops=[RawFortranLinesOp("ptr => cam_constituents_obj%field_data_ptr()")],
    )

    # ── 7. const_get_index ───────────────────────────────────────────────
    ci_op = ConstituentFunctionOp(
        fn_name=f"{h}_const_get_index",
        is_function=False,
        args=["std_name", "index", "errflg", "errmsg"],
        use_stmts=["use ccpp_constituent_prop_mod, only: to_lower"],
        arg_decls=[
            "character(len=*), intent(in) :: std_name",
            "integer, intent(out) :: index",
            "integer, intent(out) :: errflg",
            f"character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
        ],
        local_decls=[],
        body_ops=[RawFortranLinesOp(
            "call cam_constituents_obj%const_index(index, to_lower(std_name), &\n"
            "    errcode=errflg, errmsg=errmsg)"
        )],
    )

    # ── 8. model_const_properties ────────────────────────────────────────
    mp_op = ConstituentFunctionOp(
        fn_name=f"{h}_model_const_properties",
        is_function=True,
        args=[],
        use_stmts=["use ccpp_constituent_prop_mod, only: ccpp_constituent_prop_ptr_t"],
        arg_decls=[],
        local_decls=[],
        result_name="ptr",
        result_decl="type(ccpp_constituent_prop_ptr_t), pointer :: ptr(:)",
        body_ops=[RawFortranLinesOp("ptr => cam_constituents_obj%constituent_props_ptr()")],
    )

    # ── 9. gather_constituents ───────────────────────────────────────────
    gc_op = ConstituentFunctionOp(
        fn_name=f"{h}_ccpp_gather_constituents",
        is_function=False,
        args=["const_array", "errcode", "errmsg"],
        use_stmts=[],
        arg_decls=[
            "real(kind=kind_phys), intent(out) :: const_array(:, :, :)",
            "integer, intent(out) :: errcode",
            f"character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
        ],
        local_decls=[],
        body_ops=[RawFortranLinesOp(
            "call cam_constituents_obj%copy_in(const_array, errcode=errcode, errmsg=errmsg)"
        )],
    )

    # ── 10. update_constituents ──────────────────────────────────────────
    uc_op = ConstituentFunctionOp(
        fn_name=f"{h}_ccpp_update_constituents",
        is_function=False,
        args=["const_array", "errcode", "errmsg"],
        use_stmts=[],
        arg_decls=[
            "real(kind=kind_phys), intent(in) :: const_array(:, :, :)",
            "integer, intent(out) :: errcode",
            f"character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
        ],
        local_decls=[],
        body_ops=[RawFortranLinesOp(
            "call cam_constituents_obj%copy_out(const_array, errcode=errcode, errmsg=errmsg)"
        )],
    )

    public_names_list = [
        f"{h}_ccpp_is_scheme_constituent",
        f"{h}_ccpp_deallocate_dynamic_constituents",
        f"{h}_ccpp_register_constituents",
        f"{h}_ccpp_number_constituents",
        f"{h}_ccpp_initialize_constituents",
        f"{h}_constituents_array",
        f"{h}_const_get_index",
        f"{h}_model_const_properties",
        f"{h}_ccpp_gather_constituents",
        f"{h}_ccpp_update_constituents",
    ]

    api_op = CamHostConstituentApiOp(
        public_names_list,
        [isc_op, da_op, rc_op, nc_op, ic_op, ca_op, ci_op, mp_op, gc_op, uc_op],
    )

    # Global USE stubs — need all three types from ccpp_constituent_prop_mod.
    global_stubs: list = []
    for type_name in (
        "ccpp_constituent_properties_t",
        "ccpp_constituent_prop_ptr_t",
        "ccpp_model_constituents_t",
    ):
        _g = llvm.GlobalOp(
            llvm.LLVMArrayType.from_size_and_type(1, i8),
            type_name,
            "external",
        )
        _g.attributes["module"] = StringAttr(_CCPP_CONSTITUENT_MOD)
        global_stubs.append(_g)

    return module_var_ops, api_op, global_stubs


def _generate_constituent_api(
    camel_name: str,
    dynamic_array_names: list,
    fixed_advected: list,
    scratch_vars: list | None = None,
    framework_var_residency: dict | None = None,
    instance_local_name: "str | None" = None,
    ninstances_local_name: "str | None" = None,
    cam_host: bool = False,
    needs_const_tend: bool = False,
):
    """Generate constituent registration API as raw Fortran text.

    framework_var_residency: cap var name ("lc_constituent_array",
    "lc_const_tend") -> True if CapScratch GPU residency should be
    established for it (see ccpp_cap.py's _build_cap_var_map) -- emitted as
    plain text (`#ifdef USE_GPU` / `!$acc enter data copyin(...)` /
    `#endif`) directly after each array's existing allocate-and-initialize
    block in ic_lines, matching the surrounding generation style: this whole
    subsystem builds Fortran source as raw text (ConstituentApiOp's body is
    a plain StringAttr), there's no IR op to attach a residency property to
    the way SuiteOwned's LazyAllocOp allowed. `copyin`, not `create`: each
    array is host-initialized (a default-value loop or a `= 0.0_kind_phys`
    fill) immediately before this directive, and `create` would allocate
    uninitialized device memory without transferring that initialized state
    -- caught by Copilot review on PR #38.

    instance_local_name/ninstances_local_name -- real capgen-v1's
    multi-instance model (ccpp_cap_refactor_plan.md's "instances/
    instances_advection" entry, task #35): when set (the host declares
    instance_number/number_of_instances), every module-level array this API
    owns (lc_all_constituents, lc_constituent_array, lc_const_tend,
    lc_const_props, each scheme's own dynamic-array, and any scratch var)
    becomes one member of a new per-instance bundle type
    (<camel_name>_lc_instance_t), collected into a single allocatable
    lc_instances(:) array -- the same "array-of-DDT-instance" idiom
    examples/instances' own host-declared instance_data already establishes
    for this codebase, just cap-owned/generated here instead of
    host-declared. lc_instances is lazily allocated (sized by
    ninstances_local_name) inside register_constituents only -- the one
    entry point the driver always calls first, with ninstances, before any
    other constituent-API call for a given instance; every other subroutine
    treats "lc_instances not yet allocated" as "register_constituents not
    called," matching the existing single-instance code's own precondition
    checks. When both are None (a non-multi-instance host, by far the common
    case), every array stays a plain module-scope variable exactly as
    before -- this whole codepath is unreachable and output is
    byte-identical to before this feature existed.

    Returns (module_var_ops, constituent_api_op, global_stub_ops).
    """
    # instance_local_name/ninstances_local_name are a paired contract, not
    # two independent optionals -- multi_instance below gates the whole
    # per-instance bundle (declarations, register_constituents' own
    # allocate(lc_instances(ninstances)), every other subroutine's `instance`
    # arg) on instance_local_name alone; if ninstances_local_name were ever
    # missing while instance_local_name was set, that allocate call would
    # get a literal "None" spliced into generated Fortran. ccpp_cap.py's own
    # resolution site normalizes both to None together, but assert the
    # invariant here too, matching this codebase's existing
    # _assert_call_arg_count_matches_signature precedent for guarding a
    # coupled-parameter contract at the point that actually relies on it.
    # Caught by Copilot review on PR #77.
    assert (instance_local_name is None) == (ninstances_local_name is None), (
        "instance_local_name and ninstances_local_name must both be set or "
        "both be None -- got "
        f"instance_local_name={instance_local_name!r}, "
        f"ninstances_local_name={ninstances_local_name!r}"
    )

    if cam_host:
        return _generate_constituent_api_cam_host(
            camel_name, dynamic_array_names, fixed_advected,
            scratch_vars=scratch_vars,
            needs_const_tend=needs_const_tend,
        )

    h = camel_name
    framework_var_residency = framework_var_residency or {}
    scratch_vars = scratch_vars or []
    dyn_lc = [f"lc_{n}" for n in dynamic_array_names]
    multi_instance = instance_local_name is not None
    instance_type_name = f"{h}_lc_instance_t"

    def ref(name: str) -> str:
        """Return the reference text for module-level array `name` --
        lc_instances(<instance>)%name when multi-instance, else the bare
        module-var name unchanged."""
        if multi_instance:
            return f"lc_instances({instance_local_name})%{name}"
        return name

    # ── Module-level variable declarations ──────────────────────────────
    # Non-multi-instance: unchanged -- one plain ModuleVarOp per array.
    # Multi-instance: every one of these becomes a *component* of a new
    # bundle type instead (see type_defs_text below), and the only actual
    # module variable is the single lc_instances(:) array.
    module_var_ops: list = []
    type_def_lines: list = []
    if not multi_instance:
        for n in dynamic_array_names:
            module_var_ops.append(
                ModuleVarOp(f"lc_{n}", "type", ddt_name="ccpp_constituent_properties_t", rank=1)
            )
        module_var_ops.append(
            ModuleVarOp(
                "lc_all_constituents",
                "type",
                ddt_name="ccpp_constituent_properties_t",
                is_target=True,
                rank=1,
            )
        )
        module_var_ops.append(
            ModuleVarOp("lc_constituent_array", "real", kind="kind_phys", is_target=True, rank=3)
        )
        module_var_ops.append(
            ModuleVarOp("lc_const_tend", "real", kind="kind_phys", is_target=True, rank=3)
        )
        module_var_ops.append(
            ModuleVarOp("lc_const_props", "type", ddt_name="ccpp_constituent_prop_ptr_t", is_target=True, rank=1)
        )
        for lc_name, rank, _alloc_dims, _cst_std, _needs_gpu in scratch_vars:
            module_var_ops.append(
                ModuleVarOp(lc_name, "real", kind="kind_phys",
                            is_pointer=bool(_cst_std), rank=rank)
            )
    else:
        type_def_lines.append(f"type :: {instance_type_name}")
        for n in dynamic_array_names:
            type_def_lines.append(
                f"  type(ccpp_constituent_properties_t), allocatable :: lc_{n}(:)"
            )
        # NOT ", target" here -- Fortran forbids the TARGET attribute on a
        # derived-type COMPONENT (gfortran: "Attribute at (1) is not
        # allowed in a TYPE definition"), confirmed the hard way in real
        # CI: gfortran's own parse of the (invalid) type block corrupts its
        # symbol table for these specific components, cascading into
        # dozens of unrelated "not a member of the structure" errors
        # everywhere else they're referenced. TARGET instead goes on the
        # lc_instances(:) module variable itself below -- the standard's
        # own rule that TARGET propagates from a variable to all of its
        # subobjects (including allocatable components) is exactly what
        # these pointer associations (lc_const_props(i)%ptr,
        # lc_cld_liq_tend) need.
        type_def_lines.append(
            "  type(ccpp_constituent_properties_t), allocatable :: lc_all_constituents(:)"
        )
        type_def_lines.append(
            "  real(kind=kind_phys), allocatable :: lc_constituent_array(:, :, :)"
        )
        type_def_lines.append(
            "  real(kind=kind_phys), allocatable :: lc_const_tend(:, :, :)"
        )
        type_def_lines.append(
            "  type(ccpp_constituent_prop_ptr_t), allocatable :: lc_const_props(:)"
        )
        for lc_name, rank, _alloc_dims, _cst_std, _needs_gpu in scratch_vars:
            shape = ", ".join([":"] * rank)
            if _cst_std:
                type_def_lines.append(
                    f"  real(kind=kind_phys), pointer :: {lc_name}({shape}) => null()"
                )
            else:
                type_def_lines.append(
                    f"  real(kind=kind_phys), allocatable :: {lc_name}({shape})"
                )
        type_def_lines.append(f"end type {instance_type_name}")
        module_var_ops.append(
            ModuleVarOp("lc_instances", "type", ddt_name=instance_type_name,
                        is_target=True, rank=1)
        )
    type_defs_text = "\n".join(type_def_lines) if type_def_lines else None

    # ── Helper: dedup fragment ───────────────────────────────────────────
    # src_obj: a Fortran expression for the source element (e.g. "lc_dyn(lc_i)").
    # Callers must have declared lc_src_std_name, lc_dst_std_name,
    # lc_src_units, lc_dst_units (all character(len=256)) as local variables.
    def _dedup_block(src_obj, dst_tmp, indent="    ", err_var="errflg"):
        lines = []
        lines.append(f"{indent}call {src_obj}%standard_name(lc_src_std_name)")
        lines.append(f"{indent}call {src_obj}%units(lc_src_units)")
        lines.append(f"{indent}lc_found = .false.")
        lines.append(f"{indent}do lc_j = 1, lc_num")
        lines.append(f"{indent}  call {dst_tmp}(lc_j)%standard_name(lc_dst_std_name)")
        lines.append(f"{indent}  if (trim(lc_dst_std_name) == trim(lc_src_std_name)) then")
        lines.append(f"{indent}    lc_found = .true.")
        lines.append(f"{indent}    call {dst_tmp}(lc_j)%units(lc_dst_units)")
        lines.append(f"{indent}    if (trim(lc_dst_units) /= trim(lc_src_units)) then")
        lines.append(
            f"{indent}      write(errmsg, '(3a)') 'ccp_model_const_add_metadata ERROR: "
            f"Trying to add constituent ', trim(lc_src_std_name), &"
        )
        lines.append(
            f"{indent}        ' but an incompatible constituent with this name already exists'"
        )
        lines.append(f"{indent}      {err_var} = 1")
        lines.append(f"{indent}      return")
        lines.append(f"{indent}    end if")
        lines.append(f"{indent}    exit")
        lines.append(f"{indent}  end if")
        lines.append(f"{indent}end do")
        lines.append(f"{indent}if (.not. lc_found) then")
        lines.append(f"{indent}  lc_num = lc_num + 1")
        lines.append(f"{indent}  {dst_tmp}(lc_num) = {src_obj}")
        lines.append(f"{indent}end if")
        return lines

    _instance_arg = f", {instance_local_name}" if multi_instance else ""
    _instance_decl = (
        [f"    integer, intent(in) :: {instance_local_name}"] if multi_instance else []
    )
    # Sole-arg form (no leading comma): shared by constituents_array/
    # model_const_properties below, the only two subroutines here with a
    # single, optional instance parameter and no other args to comma-append
    # after -- everything else uses _instance_arg's comma-prefixed form.
    _instance_sole_arg = instance_local_name if multi_instance else ""

    def _error_guard(condition: str, errmsg_text: str) -> list:
        """Return a 5-line 'if not <condition>, set errflg/errmsg and
        return' guard block.

        Shared by the 4 identically-shaped full-error-return sites in
        ic_lines/ci_lines below (complexity-audit Tier 2 finding, task #49)
        -- confirmed byte-for-byte identical apart from condition/message
        text. Do NOT reuse this for this file's other 3 precondition-guard
        shapes (a silent-skip with no errflg/errmsg touched, in isc_lines/
        nc_lines; a bare `return` with no message, in da_lines; and rc_lines'
        own lazy-*allocate* guard, which has the opposite polarity -- it
        creates lc_instances rather than rejecting the call) -- collapsing
        those into this same helper would paper over a real semantic
        difference, the same bug class Copilot's PR #77 review caught.
        """
        return [
            f"    if (.not. {condition}) then",
            f"      errflg = 1",
            f"      errmsg = '{errmsg_text}'",
            f"      return",
            f"    end if",
        ]

    # ── 1. is_scheme_constituent ─────────────────────────────────────────
    fixed_names_str = ", ".join(f"'{s}'" for s, _u, _d, _ln in fixed_advected)
    isc_lines = [
        f"  subroutine {h}_ccpp_is_scheme_constituent(std_name, is_const, errflg, errmsg{_instance_arg})",
        f"    character(len=*), intent(in) :: std_name",
        f"    logical, intent(out) :: is_const",
        f"    integer, intent(out) :: errflg",
        f"    character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
        *_instance_decl,
        f"    integer :: lc_idx",
        f"    character(len=256) :: lc_std_name",
        f"    errflg = 0",
        f"    errmsg = ''",
        f"    is_const = .false.",
        f"    select case (trim(std_name))",
    ]
    if fixed_names_str:
        isc_lines += [
            f"    case ({fixed_names_str})",
            f"      is_const = .true.",
        ]
    isc_lines.append(f"    case default")
    for n in dynamic_array_names:
        dyn_ref = ref(f"lc_{n}")
        guard_open = ["      if (allocated(lc_instances)) then"] if multi_instance else []
        indent = "        " if multi_instance else "      "
        guard_close = ["      end if"] if multi_instance else []
        isc_lines += guard_open + [
            f"{indent}if (allocated({dyn_ref})) then",
            f"{indent}  do lc_idx = 1, size({dyn_ref})",
            f"{indent}    call {dyn_ref}(lc_idx)%standard_name(lc_std_name)",
            f"{indent}    if (trim(lc_std_name) == trim(std_name)) then",
            f"{indent}      is_const = .true.",
            f"{indent}      return",
            f"{indent}    end if",
            f"{indent}  end do",
            f"{indent}end if",
        ] + guard_close
    isc_lines += [
        f"    end select",
        f"  end subroutine {h}_ccpp_is_scheme_constituent",
    ]

    # ── 2. deallocate_dynamic_constituents ───────────────────────────────
    da_lines = [f"  subroutine {h}_ccpp_deallocate_dynamic_constituents{'(' + instance_local_name + ')' if multi_instance else '()'}"]
    da_lines += _instance_decl
    if multi_instance:
        da_lines.append(f"    if (.not. allocated(lc_instances)) return")
    for n in dynamic_array_names:
        dyn_ref = ref(f"lc_{n}")
        da_lines.append(f"    if (allocated({dyn_ref})) deallocate({dyn_ref})")
    da_lines += [
        f"    if (allocated({ref('lc_all_constituents')})) deallocate({ref('lc_all_constituents')})",
        f"    if (allocated({ref('lc_const_props')})) deallocate({ref('lc_const_props')})",
        f"    if (allocated({ref('lc_constituent_array')})) deallocate({ref('lc_constituent_array')})",
        f"    if (allocated({ref('lc_const_tend')})) deallocate({ref('lc_const_tend')})",
    ]
    for lc_name, _rank, _alloc_dims, _cst_std, _needs_gpu in scratch_vars:
        lc_ref = ref(lc_name)
        if _cst_std:
            da_lines.append(f"    nullify({lc_ref})")
        else:
            da_lines.append(f"    if (allocated({lc_ref})) deallocate({lc_ref})")
    da_lines.append(f"  end subroutine {h}_ccpp_deallocate_dynamic_constituents")

    # ── 3. register_constituents ─────────────────────────────────────────
    n_fixed = len(fixed_advected)
    _lc_all = ref("lc_all_constituents")
    _lc_props = ref("lc_const_props")
    rc_sig_extra = f", {instance_local_name}, {ninstances_local_name}" if multi_instance else ""
    rc_lines = [
        f"  subroutine {h}_ccpp_register_constituents(host_constituents, errmsg, errcode{rc_sig_extra})",
        f"    use ccpp_scheme_utils, only: ccpp_scheme_utils_set_constituents",
        f"    type(ccpp_constituent_properties_t), intent(in) :: host_constituents(:)",
        f"    character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
        f"    integer, intent(out) :: errcode",
    ]
    if multi_instance:
        rc_lines += [
            f"    integer, intent(in) :: {instance_local_name}",
            f"    integer, intent(in) :: {ninstances_local_name}",
        ]
    rc_lines += [
        f"    integer :: lc_max, lc_num, lc_i, lc_j",
        f"    logical :: lc_found",
        f"    type(ccpp_constituent_properties_t), allocatable :: lc_tmp(:)",
        f"    character(len=256) :: lc_src_std_name",
        f"    character(len=256) :: lc_dst_std_name",
        f"    character(len=256) :: lc_src_units",
        f"    character(len=256) :: lc_dst_units",
        f"    type(ccpp_constituent_properties_t), pointer :: lc_tmp_ptr",
        f"    errcode = 0",
        f"    errmsg = ''",
    ]
    if multi_instance:
        rc_lines += [
            f"    if (.not. allocated(lc_instances)) then",
            f"      allocate(lc_instances({ninstances_local_name}))",
            f"    end if",
        ]
    rc_lines.append(f"    lc_max = 0")
    for n in dynamic_array_names:
        dyn_ref = ref(f"lc_{n}")
        rc_lines.append(f"    if (allocated({dyn_ref})) lc_max = lc_max + size({dyn_ref})")
    rc_lines += [
        f"    lc_max = lc_max + {n_fixed}",
        f"    lc_max = lc_max + size(host_constituents)",
        f"    allocate(lc_tmp(lc_max))",
        f"    lc_num = 0",
    ]
    for n in dynamic_array_names:
        dyn_ref = ref(f"lc_{n}")
        rc_lines += [
            f"    if (allocated({dyn_ref})) then",
            f"      do lc_i = 1, size({dyn_ref})",
        ]
        rc_lines += _dedup_block(
            f"{dyn_ref}(lc_i)",
            "lc_tmp",
            indent="        ",
            err_var="errcode",
        )
        rc_lines += [f"      end do", f"    end if"]
    for std_name_f, units_f, default_val_f, local_name_f in fixed_advected:
        rc_lines += [
            f"    lc_found = .false.",
            f"    do lc_j = 1, lc_num",
            f"      call lc_tmp(lc_j)%standard_name(lc_dst_std_name)",
            f"      if (trim(lc_dst_std_name) == '{std_name_f}') then",
            f"        lc_found = .true.",
            f"        call lc_tmp(lc_j)%units(lc_dst_units)",
            f"        if (trim(lc_dst_units) /= '{units_f}') then",
            f"          write(errmsg, '(3a)') 'ccp_model_const_add_metadata ERROR: "
            f"Trying to add constituent ', '{std_name_f}', &",
            f"            ' but an incompatible constituent with this name already exists'",
            f"          errcode = 1",
            f"          return",
            f"        end if",
            f"        exit",
            f"      end if",
            f"    end do",
            f"    if (.not. lc_found) then",
            f"      lc_num = lc_num + 1",
        ]
        long_name_f = std_name_f.replace('_', ' ').capitalize()
        inst_args = (
            f"std_name='{std_name_f}', long_name='{long_name_f}', "
            f"units='{units_f}', diag_name='{local_name_f}', "
            f"vertical_dim='vertical_layer_dimension', "
            f"errcode=errcode, errmsg=errmsg, advected=.true."
        )
        if default_val_f is not None:
            inst_args += f", default_value={default_val_f}"
        rc_lines += [
            f"      call lc_tmp(lc_num)%instantiate({inst_args})",
            f"      if (errcode /= 0) return",
            f"    end if",
        ]
    rc_lines += [f"    do lc_i = 1, size(host_constituents)"]
    rc_lines += _dedup_block(
        "host_constituents(lc_i)",
        "lc_tmp",
        indent="      ",
        err_var="errcode",
    )
    rc_lines += [
        f"    end do",
        f"    if (allocated({_lc_all})) deallocate({_lc_all})",
        f"    allocate({_lc_all}(lc_num))",
        f"    {_lc_all}(1:lc_num) = lc_tmp(1:lc_num)",
        f"    deallocate(lc_tmp)",
        f"    if (allocated({_lc_props})) deallocate({_lc_props})",
        f"    allocate({_lc_props}(lc_num))",
        f"    do lc_i = 1, lc_num",
        f"      lc_tmp_ptr => {_lc_all}(lc_i)",
        f"      call {_lc_props}(lc_i)%set(lc_tmp_ptr)",
        f"    end do",
        f"    call ccpp_scheme_utils_set_constituents({_lc_all})",
        f"  end subroutine {h}_ccpp_register_constituents",
    ]

    # ── 4. number_constituents ───────────────────────────────────────────
    nc_lines = [
        f"  subroutine {h}_ccpp_number_constituents(num_advected, errmsg, errcode, advected{_instance_arg})",
        f"    integer, intent(out) :: num_advected",
        f"    character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
        f"    integer, intent(out) :: errcode",
        f"    logical, optional, intent(in) :: advected",
        *_instance_decl,
        f"    errcode = 0",
        f"    errmsg = ''",
    ]
    if multi_instance:
        nc_lines += [
            f"    if (allocated(lc_instances)) then",
            f"      if (allocated({ref('lc_all_constituents')})) then",
            f"        num_advected = size({ref('lc_all_constituents')})",
            f"      else",
            f"        num_advected = 0",
            f"      end if",
            f"    else",
            f"      num_advected = 0",
            f"    end if",
        ]
    else:
        nc_lines += [
            f"    if (allocated(lc_all_constituents)) then",
            f"      num_advected = size(lc_all_constituents)",
            f"    else",
            f"      num_advected = 0",
            f"    end if",
        ]
    nc_lines.append(f"  end subroutine {h}_ccpp_number_constituents")

    # ── 5. initialize_constituents ───────────────────────────────────────
    ic_lines = [
        f"  subroutine {h}_ccpp_initialize_constituents(ncols, pver, errflg, errmsg{_instance_arg})",
        f"    integer, intent(in) :: ncols",
        f"    integer, intent(in) :: pver",
        f"    integer, intent(out) :: errflg",
        f"    character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
        *_instance_decl,
        f"    integer :: lc_num, lc_i",
        f"    logical :: lc_has_def",
        f"    real(kind=kind_phys) :: lc_def_val",
        f"    character(len=256) :: lc_std_name",
        f"    errflg = 0",
        f"    errmsg = ''",
    ]
    if multi_instance:
        ic_lines += _error_guard(
            "allocated(lc_instances)",
            "ccpp_initialize_constituents: register_constituents not called",
        )
    ic_lines += _error_guard(
        f"allocated({ref('lc_all_constituents')})",
        "ccpp_initialize_constituents: register_constituents not called",
    )
    ic_lines += [
        f"    lc_num = size({ref('lc_all_constituents')})",
        f"    if (allocated({ref('lc_constituent_array')})) deallocate({ref('lc_constituent_array')})",
        f"    allocate({ref('lc_constituent_array')}(ncols, pver, lc_num))",
        f"    {ref('lc_constituent_array')} = 0.0_kind_phys",
        f"    do lc_i = 1, lc_num",
        f"      call {ref('lc_all_constituents')}(lc_i)%has_default(lc_has_def, errflg, errmsg)",
        f"      if (lc_has_def) then",
        f"        call {ref('lc_all_constituents')}(lc_i)%default_value(lc_def_val, errflg, errmsg)",
        f"        {ref('lc_constituent_array')}(:, :, lc_i) = lc_def_val",
        f"      end if",
        f"    end do",
    ]
    if framework_var_residency.get("lc_constituent_array"):
        ic_lines += [
            f"#ifdef USE_GPU",
            f"    !$acc enter data copyin({ref('lc_constituent_array')})",
            f"#endif",
        ]
    ic_lines += [
        f"    if (allocated({ref('lc_const_tend')})) deallocate({ref('lc_const_tend')})",
        f"    allocate({ref('lc_const_tend')}(ncols, pver, lc_num))",
        f"    {ref('lc_const_tend')} = 0.0_kind_phys",
    ]
    if framework_var_residency.get("lc_const_tend"):
        ic_lines += [
            f"#ifdef USE_GPU",
            f"    !$acc enter data copyin({ref('lc_const_tend')})",
            f"#endif",
        ]
    for lc_name, _rank, alloc_dims, _cst_std, needs_gpu in scratch_vars:
        lc_ref = ref(lc_name)
        if _cst_std:
            ic_lines += [
                f"    nullify({lc_ref})",
                f"    do lc_i = 1, lc_num",
                f"      call {ref('lc_all_constituents')}(lc_i)%standard_name(lc_std_name)",
                f"      if (trim(lc_std_name) == '{_cst_std}') then",
                f"        {lc_ref} => {ref('lc_const_tend')}(:, :, lc_i)",
                f"        exit",
                f"      end if",
                f"    end do",
            ]
            # No separate enter-data here: lc_name is a pointer slice into
            # lc_const_tend, already made resident above -- OpenACC tracks
            # residency by the underlying array's actual memory, not the
            # pointer name used to reference a slice of it.
        else:
            ic_lines += [
                f"    if (allocated({lc_ref})) deallocate({lc_ref})",
                f"    allocate({lc_ref}({alloc_dims}))",
                f"    {lc_ref} = 0.0_kind_phys",
            ]
            if needs_gpu:
                ic_lines += [
                    f"#ifdef USE_GPU",
                    f"    !$acc enter data copyin({lc_ref})",
                    f"#endif",
                ]
    ic_lines.append(f"  end subroutine {h}_ccpp_initialize_constituents")

    # ── 6. constituents_array ────────────────────────────────────────────
    ca_lines = [
        f"  function {h}_constituents_array({_instance_sole_arg}) result(ptr)",
        *_instance_decl,
        f"    real(kind=kind_phys), pointer :: ptr(:, :, :)",
        f"    ptr => {ref('lc_constituent_array')}",
        f"  end function {h}_constituents_array",
    ]

    # ── 7. const_get_index ───────────────────────────────────────────────
    ci_lines = [
        f"  subroutine {h}_const_get_index(std_name, index, errflg, errmsg{_instance_arg})",
        f"    character(len=*), intent(in) :: std_name",
        f"    integer, intent(out) :: index",
        f"    integer, intent(out) :: errflg",
        f"    character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
        *_instance_decl,
        f"    integer :: lc_i",
        f"    character(len=256) :: lc_std_name",
        f"    errflg = 0",
        f"    errmsg = ''",
        f"    index = -1",
    ]
    if multi_instance:
        ci_lines += _error_guard(
            "allocated(lc_instances)",
            "const_get_index: constituents not registered",
        )
    ci_lines += _error_guard(
        f"allocated({ref('lc_all_constituents')})",
        "const_get_index: constituents not registered",
    )
    ci_lines += [
        f"    do lc_i = 1, size({ref('lc_all_constituents')})",
        f"      call {ref('lc_all_constituents')}(lc_i)%standard_name(lc_std_name)",
        f"      if (trim(lc_std_name) == trim(std_name)) then",
        f"        index = lc_i",
        f"        return",
        f"      end if",
        f"    end do",
        f"    errflg = 1",
        f"    write(errmsg, '(3a)') 'const_get_index: constituent ', trim(std_name), ' not found'",
        f"  end subroutine {h}_const_get_index",
    ]

    # ── 8. model_const_properties ────────────────────────────────────────
    mp_lines = [
        f"  function {h}_model_const_properties({_instance_sole_arg}) result(ptr)",
        *_instance_decl,
        f"    type(ccpp_constituent_prop_ptr_t), pointer :: ptr(:)",
        f"    ptr => {ref('lc_const_props')}",
        f"  end function {h}_model_const_properties",
    ]

    import re as _re

    def _lines_to_fn_op(lines):
        """Convert a full subroutine/function line list into a ConstituentFunctionOp."""
        header = lines[0].strip()
        is_function = header.startswith("function ")
        m = _re.match(r"(?:function|subroutine)\s+(\w+)\s*\(([^)]*)\)", header)
        fn_name = m.group(1)
        args_str = m.group(2).strip()
        args = [a.strip() for a in args_str.split(",")] if args_str else []
        result_name = None
        rm = _re.search(r"result\((\w+)\)", header)
        if rm:
            result_name = rm.group(1)

        use_stmts: list = []
        arg_decls: list = []
        local_decls: list = []
        body_lines: list = []
        result_decl = None
        in_decls = True

        for line in lines[1:-1]:
            stripped = line.strip()
            if in_decls:
                if stripped.startswith("use "):
                    use_stmts.append(stripped)
                elif "::" in stripped:
                    if "intent(" in stripped:
                        arg_decls.append(stripped)
                    elif result_name and f":: {result_name}" in stripped:
                        result_decl = stripped
                    else:
                        local_decls.append(stripped)
                else:
                    in_decls = False
                    body_lines.append(line.rstrip())
            else:
                body_lines.append(line.rstrip())

        # Strip 4-space subroutine indent from each body line.
        # Lines starting with '#' (preprocessor) have no leading spaces — keep as-is.
        body_text_inner = "\n".join(
            (l[4:] if len(l) >= 4 and l[:4] == "    " else l) for l in body_lines
        )
        body_ops = [RawFortranLinesOp(body_text_inner)] if body_text_inner.strip() else []
        return ConstituentFunctionOp(
            fn_name=fn_name,
            is_function=is_function,
            args=args,
            use_stmts=use_stmts,
            arg_decls=arg_decls,
            local_decls=local_decls,
            body_ops=body_ops,
            result_name=result_name,
            result_decl=result_decl,
        )

    public_names_list = [
        f"{h}_ccpp_is_scheme_constituent",
        f"{h}_ccpp_deallocate_dynamic_constituents",
        f"{h}_ccpp_register_constituents",
        f"{h}_ccpp_number_constituents",
        f"{h}_ccpp_initialize_constituents",
        f"{h}_constituents_array",
        f"{h}_const_get_index",
        f"{h}_model_const_properties",
    ]

    api_op = NonCamHostConstituentApiOp(
        public_names_list,
        type_defs_text,
        [
            _lines_to_fn_op(isc_lines),
            _lines_to_fn_op(da_lines),
            _lines_to_fn_op(rc_lines),
            _lines_to_fn_op(nc_lines),
            _lines_to_fn_op(ic_lines),
            _lines_to_fn_op(ca_lines),
            _lines_to_fn_op(ci_lines),
            _lines_to_fn_op(mp_lines),
        ],
    )

    # ── USE stubs for ccpp_constituent_prop_mod ──────────────────────────
    global_stubs: list = []
    for type_name in ("ccpp_constituent_properties_t", "ccpp_constituent_prop_ptr_t"):
        _g = llvm.GlobalOp(
            llvm.LLVMArrayType.from_size_and_type(1, i8),
            type_name,
            "external",
        )
        _g.attributes["module"] = StringAttr(_CCPP_CONSTITUENT_MOD)
        global_stubs.append(_g)

    return module_var_ops, api_op, global_stubs
