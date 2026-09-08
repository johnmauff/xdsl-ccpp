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


def _error_guard(condition: str, errmsg_text: str) -> list:
    """Return a 5-line 'if not <condition>, set errflg/errmsg and return' guard block."""
    return [
        f"if (.not. {condition}) then",
        f"  errflg = 1",
        f"  errmsg = '{errmsg_text}'",
        f"  return",
        f"end if",
    ]



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
    subsystem builds Fortran source as raw text (the constituent API op body is
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

    if cam_host and instance_local_name is not None:
        raise ValueError(
            "cam_host=True with multi-instance metadata is not supported; "
            "CAM does not use per-instance constituent containers"
        )

    h = camel_name
    n_fixed = len(fixed_advected)
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
        # cam_constituents_obj: scalar ccpp_model_constituents_t with target
        # (so that field_data_ptr() and constituent_props_ptr() pointer results
        # remain valid as long as this module-level variable lives).
        module_var_ops.append(
            ModuleVarOp("cam_constituents_obj", "type",
                        ddt_name="ccpp_model_constituents_t", is_target=True, rank=0)
        )
        for n in dynamic_array_names:
            # target needed so register_constituents can pointer-associate
            # const_prop => lc_{n}(lc_i) before passing to new_field.
            module_var_ops.append(
                ModuleVarOp(f"lc_{n}", "type", ddt_name="ccpp_constituent_properties_t",
                            is_target=True, rank=1)
            )
        # lc_all_constituents: integer size-proxy; allocated in register_constituents
        # to signal that registration is complete; used as guard in
        # initialize_constituents and number_constituents.
        module_var_ops.append(ModuleVarOp("lc_all_constituents", "integer", rank=1))
        # lc_constituent_array: pointer into cam_constituents_obj internal storage
        # (set by field_data_ptr() in initialize_constituents; must be pointer not
        # allocatable because the memory is owned by cam_constituents_obj).
        module_var_ops.append(
            ModuleVarOp("lc_constituent_array", "real", kind="kind_phys", is_pointer=True, rank=3)
        )
        if needs_const_tend:
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
        if n_fixed > 0:
            _max_std_len = max(len(s) for s, *_ in fixed_advected)
            _names_parts = [f"'{s}'" for s, *_ in fixed_advected]
            _names_str = (_names_parts[0] if n_fixed == 1
                          else ", &\n      ".join(_names_parts))
            module_var_ops.append(ModuleVarOp(
                "cam_model_const_stdnames", "character",
                kind=str(_max_std_len),
                fixed_dim=n_fixed,
                init_value=f"[ character(len={_max_std_len}) :: {_names_str} ]",
            ))
            module_var_ops.append(ModuleVarOp(
                "cam_model_const_indices", "integer",
                fixed_dim=n_fixed,
                init_value="-1",
            ))
    else:
        type_def_lines.append(f"type :: {instance_type_name}")
        # cam_constituents_obj as a non-pointer, non-target DDT component.
        # TARGET is NOT allowed on derived-type components (gfortran: "Attribute
        # at (1) is not allowed in a TYPE definition").  TARGET instead goes on
        # the lc_instances(:) module variable itself below -- the standard's
        # rule that TARGET propagates from a variable to all subobjects
        # (including allocatable/ordinary components) is what makes the
        # field_data_ptr() and constituent_props_ptr() pointer results valid.
        type_def_lines.append(
            f"  type(ccpp_model_constituents_t) :: cam_constituents_obj"
        )
        for n in dynamic_array_names:
            type_def_lines.append(
                f"  type(ccpp_constituent_properties_t), allocatable :: lc_{n}(:)"
            )
        type_def_lines.append(
            "  integer, allocatable :: lc_all_constituents(:)"
        )
        # lc_constituent_array: pointer component (points into cam_constituents_obj
        # internal storage after lock_data; TARGET propagates from lc_instances).
        type_def_lines.append(
            "  real(kind=kind_phys), pointer :: lc_constituent_array(:, :, :) => null()"
        )
        if needs_const_tend:
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
        if n_fixed > 0:
            _max_std_len = max(len(s) for s, *_ in fixed_advected)
            _names_parts = [f"'{s}'" for s, *_ in fixed_advected]
            _names_str = (_names_parts[0] if n_fixed == 1
                          else ", &\n      ".join(_names_parts))
            type_def_lines.append(
                f"  character(len={_max_std_len}) :: "
                f"cam_model_const_stdnames({n_fixed}) = "
                f"[ character(len={_max_std_len}) :: {_names_str} ]"
            )
            type_def_lines.append(
                f"  integer :: cam_model_const_indices({n_fixed}) = -1"
            )
        type_def_lines.append(f"end type {instance_type_name}")
        module_var_ops.append(
            ModuleVarOp("lc_instances", "type", ddt_name=instance_type_name,
                        is_target=True, rank=1)
        )
    type_defs_text = "\n".join(type_def_lines) if type_def_lines else None

    _instance_arg = f", {instance_local_name}" if multi_instance else ""
    _instance_decl = (
        [f"    integer, intent(in) :: {instance_local_name}"] if multi_instance else []
    )
    # Sole-arg form (no leading comma): shared by constituents_array/
    # model_const_properties below, the only two subroutines here with a
    # single, optional instance parameter and no other args to comma-append
    # after -- everything else uses _instance_arg's comma-prefixed form.
    _instance_sole_arg = instance_local_name if multi_instance else ""

    # ── 1. is_scheme_constituent ─────────────────────────────────────────
    isc_arg_decls = [
        "character(len=*), intent(in) :: std_name",
        "logical, intent(out) :: is_const",
        "integer, intent(out) :: errflg",
        f"character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
    ] + ([f"integer, intent(in) :: {instance_local_name}"] if multi_instance else [])
    isc_body = ["errflg = 0", "errmsg = ''", "is_const = .false."]
    if n_fixed > 0:
        if multi_instance:
            # ref() expands to lc_instances(instance)%... — guard allocated(lc_instances)
            # before dereferencing, matching the same guard the dynamic-name loops use.
            isc_body += [
                "if (allocated(lc_instances)) then",
                f"  if (any({ref('cam_model_const_stdnames')} == std_name)) then",
                "    is_const = .true.",
                "    return",
                "  end if",
                "end if",
            ]
        else:
            isc_body += [
                f"if (any({ref('cam_model_const_stdnames')} == std_name)) then",
                "  is_const = .true.",
                "  return",
                "end if",
            ]
    for n in dynamic_array_names:
        dyn_ref = ref(f"lc_{n}")
        guard_open = ["if (allocated(lc_instances)) then"] if multi_instance else []
        indent = "  " if multi_instance else ""
        guard_close = ["end if"] if multi_instance else []
        isc_body += guard_open + [
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
    isc_op = ConstituentFunctionOp(
        fn_name=f"{h}_ccpp_is_scheme_constituent",
        is_function=False,
        args=["std_name", "is_const", "errflg", "errmsg"]
            + ([instance_local_name] if multi_instance else []),
        use_stmts=[],
        arg_decls=isc_arg_decls,
        local_decls=["integer :: lc_idx", "character(len=256) :: lc_std_name"],
        body_ops=[RawFortranLinesOp("\n".join(isc_body))],
    )

    # ── 2. deallocate_dynamic_constituents ───────────────────────────────
    da_body = []
    if multi_instance:
        da_body.append("if (.not. allocated(lc_instances)) return")
    for n in dynamic_array_names:
        dyn_ref = ref(f"lc_{n}")
        da_body.append(f"if (allocated({dyn_ref})) deallocate({dyn_ref})")
    da_body += [
        f"if (allocated({ref('lc_all_constituents')})) deallocate({ref('lc_all_constituents')})",
        f"if (allocated({ref('lc_const_props')})) deallocate({ref('lc_const_props')})",
        # lc_constituent_array is a pointer into cam_constituents_obj storage;
        # nullify it before reset() to avoid a dangling pointer.
        f"if (associated({ref('lc_constituent_array')})) nullify({ref('lc_constituent_array')})",
    ]
    if needs_const_tend:
        da_body.append(
            f"if (allocated({ref('lc_const_tend')})) deallocate({ref('lc_const_tend')})"
        )
    for lc_name, _rank, _alloc_dims, _cst_std, _needs_gpu in scratch_vars:
        lc_ref = ref(lc_name)
        if _cst_std:
            da_body.append(f"nullify({lc_ref})")
        else:
            da_body.append(f"if (allocated({lc_ref})) deallocate({lc_ref})")
    da_body.append(f"call {ref('cam_constituents_obj')}%reset()")
    da_op = ConstituentFunctionOp(
        fn_name=f"{h}_ccpp_deallocate_dynamic_constituents",
        is_function=False,
        args=[instance_local_name] if multi_instance else [],
        use_stmts=[],
        arg_decls=[f"integer, intent(in) :: {instance_local_name}"] if multi_instance else [],
        local_decls=[],
        body_ops=[RawFortranLinesOp("\n".join(da_body))] if da_body else [],
    )

    # ── 3. register_constituents ─────────────────────────────────────────
    # Uses ccpp_model_constituents_t (new_field handles dedup internally).
    _lc_all = ref("lc_all_constituents")
    _lc_props = ref("lc_const_props")
    _cam_obj = ref("cam_constituents_obj")
    if cam_host:
        # CAM callers use (host_constituents, errcode, errmsg) positional order;
        # preserve it so existing callers that don't use keyword args still compile.
        rc_arg_decls = [
            f"type(ccpp_constituent_properties_t), target, intent(in) :: host_constituents(:)",
            "integer, intent(out) :: errcode",
            f"character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
        ]
    else:
        rc_arg_decls = [
            f"type(ccpp_constituent_properties_t), target, intent(in) :: host_constituents(:)",
            f"character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
            "integer, intent(out) :: errcode",
        ]
        if multi_instance:
            rc_arg_decls += [
                f"integer, intent(in) :: {instance_local_name}",
                f"integer, intent(in) :: {ninstances_local_name}",
            ]
    rc_body = ["errcode = 0", "errmsg = ''"]
    if multi_instance:
        rc_body += [
            "if (.not. allocated(lc_instances)) then",
            f"  allocate(lc_instances({ninstances_local_name}))",
            "end if",
        ]
    # Count total constituents (upper bound for initialize_table)
    rc_body.append("lc_num_consts = size(host_constituents)")
    for n in dynamic_array_names:
        dyn_ref = ref(f"lc_{n}")
        rc_body.append(f"if (allocated({dyn_ref})) lc_num_consts = lc_num_consts + size({dyn_ref})")
    rc_body.append(f"lc_num_consts = lc_num_consts + {n_fixed}")
    rc_body.append(f"call {_cam_obj}%initialize_table(lc_num_consts)")
    # Host constituents
    rc_body += [
        "do lc_i = 1, size(host_constituents)",
        "  allocate(const_prop, stat=errcode)",
        "  if (errcode /= 0) then",
        "    errmsg = 'ERROR allocating const_prop'",
        "    return",
        "  end if",
        "  const_prop = host_constituents(lc_i)",
        f"  call {_cam_obj}%new_field(const_prop, errcode=errcode, errmsg=errmsg)",
        "  nullify(const_prop)",
        "  if (errcode /= 0) return",
        "end do",
    ]
    # Dynamic scheme arrays
    for n in dynamic_array_names:
        dyn_ref = ref(f"lc_{n}")
        rc_body += [
            f"if (allocated({dyn_ref})) then",
            f"  do lc_i = 1, size({dyn_ref})",
            f"    allocate(const_prop, stat=errcode)",
            f"    if (errcode /= 0) then",
            f"      errmsg = 'ERROR allocating const_prop'",
            f"      return",
            f"    end if",
            f"    const_prop = {dyn_ref}(lc_i)",
            f"    call {_cam_obj}%new_field(const_prop, errcode=errcode, errmsg=errmsg)",
            f"    nullify(const_prop)",
            f"    if (errcode /= 0) return",
            f"  end do",
            f"end if",
        ]
    # Fixed advected constituents
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
            f"call {_cam_obj}%new_field(const_prop, errcode=errcode, errmsg=errmsg)",
            "nullify(const_prop)",
            "if (errcode /= 0) return",
        ]
    rc_body += [
        f"call {_cam_obj}%lock_table(errcode=errcode, errmsg=errmsg)",
        "if (errcode /= 0) return",
        f"lc_props_ptr => {_cam_obj}%constituent_props_ptr()",
        f"if (allocated({_lc_props})) deallocate({_lc_props})",
        f"allocate({_lc_props}(size(lc_props_ptr)))",
        f"{_lc_props} = lc_props_ptr",
        "nullify(lc_props_ptr)",
    ]
    if cam_host:
        rc_body.append(f"call ccpp_initialize_constituent_ptr({_cam_obj})")
    else:
        rc_body.append(f"call ccpp_scheme_utils_set_constituents({_lc_props})")
    rc_body += [
        f"call {_cam_obj}%num_constituents(lc_num_consts, errcode=errcode, errmsg=errmsg)",
        "if (errcode /= 0) return",
        f"if (allocated({_lc_all})) deallocate({_lc_all})",
        f"allocate({_lc_all}(lc_num_consts))",
    ]
    if n_fixed > 0:
        _cmi = ref("cam_model_const_indices")
        _cms = ref("cam_model_const_stdnames")
        rc_body += [
            f"do lc_i = 1, size({_cmi})",
            f"  call {_cam_obj}%const_index(field_ind, {_cms}(lc_i), &",
            "      errcode=errcode, errmsg=errmsg)",
            "  if (errcode /= 0) return",
            "  if (field_ind > 0) then",
            f"    {_cmi}(lc_i) = field_ind",
            "  else",
            "    errcode = 1",
            f"    errmsg = 'No field index for '//trim({_cms}(lc_i))",
            "    return",
            "  end if",
            "end do",
        ]
    rc_local_decls = [
        "integer :: lc_i, lc_num_consts" + (", field_ind" if n_fixed > 0 else ""),
        "type(ccpp_constituent_properties_t), pointer :: const_prop",
        "type(ccpp_constituent_prop_ptr_t), pointer :: lc_props_ptr(:)",
    ]
    rc_op = ConstituentFunctionOp(
        fn_name=f"{h}_ccpp_register_constituents",
        is_function=False,
        args=(["host_constituents", "errcode", "errmsg"] if cam_host
              else ["host_constituents", "errmsg", "errcode"]
                   + ([instance_local_name, ninstances_local_name] if multi_instance else [])),
        use_stmts=[
            "use ccpp_constituent_prop_mod, only: ccpp_constituent_properties_t, ccpp_constituent_prop_ptr_t",
            "use ccpp_scheme_utils, only: ccpp_initialize_constituent_ptr" if cam_host
            else "use ccpp_scheme_utils, only: ccpp_scheme_utils_set_constituents",
        ],
        arg_decls=rc_arg_decls,
        local_decls=rc_local_decls,
        body_ops=[RawFortranLinesOp("\n".join(rc_body))],
    )

    # ── 4. number_constituents ───────────────────────────────────────────
    # The optional `advected` arg is declared for API compatibility but is not used
    # to filter the count: every constituent registered through this API is advected
    # (fixed_advected contains only advected=.true. entries; host_constituents and
    # dynamic scheme arrays are required to be advected by the CAM-SIMA contract).
    # size(lc_all_constituents) therefore equals the advected-only count.
    nc_arg_decls = [
        "integer, intent(out) :: num_advected",
        f"character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
        "integer, intent(out) :: errcode",
        "logical, optional, intent(in) :: advected",
    ] + ([f"integer, intent(in) :: {instance_local_name}"] if multi_instance else [])
    nc_body = ["errcode = 0", "errmsg = ''"]
    if multi_instance:
        nc_body += [
            "if (allocated(lc_instances)) then",
            f"  if (allocated({ref('lc_all_constituents')})) then",
            f"    num_advected = size({ref('lc_all_constituents')})",
            "  else",
            "    num_advected = 0",
            "  end if",
            "else",
            "  num_advected = 0",
            "end if",
        ]
    else:
        nc_body += [
            "if (allocated(lc_all_constituents)) then",
            "  num_advected = size(lc_all_constituents)",
            "else",
            "  num_advected = 0",
            "end if",
        ]
    nc_op = ConstituentFunctionOp(
        fn_name=f"{h}_ccpp_number_constituents",
        is_function=False,
        args=["num_advected", "errmsg", "errcode", "advected"]
            + ([instance_local_name] if multi_instance else []),
        use_stmts=[],
        arg_decls=nc_arg_decls,
        local_decls=[],
        body_ops=[RawFortranLinesOp("\n".join(nc_body))],
    )

    # ── 5. initialize_constituents ───────────────────────────────────────
    _cam_obj = ref("cam_constituents_obj")
    _lc_all = ref("lc_all_constituents")
    _lc_props = ref("lc_const_props")
    ic_arg_decls = [
        "integer, intent(in) :: ncols",
        "integer, intent(in) :: pver",
        "integer, intent(out) :: errflg",
        f"character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
    ] + ([f"integer, intent(in) :: {instance_local_name}"] if multi_instance else [])
    ic_body = ["errflg = 0", "errmsg = ''"]
    if multi_instance:
        ic_body += _error_guard(
            "allocated(lc_instances)",
            "ccpp_initialize_constituents: register_constituents not called",
        )
    ic_body += _error_guard(
        f"allocated({_lc_all})",
        "ccpp_initialize_constituents: register_constituents not called",
    )
    # lock_data allocates the internal data array and applies defaults.
    ic_body += [
        f"call {_cam_obj}%lock_data(ncols, pver, errcode=errflg, errmsg=errmsg)",
        "if (errflg /= 0) return",
        f"{ref('lc_constituent_array')} => {_cam_obj}%field_data_ptr()",
    ]
    if framework_var_residency.get("lc_constituent_array"):
        ic_body += [
            "#ifdef USE_GPU",
            f"!$acc enter data copyin({ref('lc_constituent_array')})",
            "#endif",
        ]
    if needs_const_tend:
        ic_body += [
            f"if (allocated({ref('lc_const_tend')})) deallocate({ref('lc_const_tend')})",
            f"allocate({ref('lc_const_tend')}(ncols, pver, size({_lc_all})))",
            f"{ref('lc_const_tend')} = 0.0_kind_phys",
        ]
        if framework_var_residency.get("lc_const_tend"):
            ic_body += [
                "#ifdef USE_GPU",
                f"!$acc enter data copyin({ref('lc_const_tend')})",
                "#endif",
            ]
    for lc_name, _rank, alloc_dims, _cst_std, needs_gpu in scratch_vars:
        lc_ref = ref(lc_name)
        if _cst_std:
            # Use cam_constituents_obj%const_index for hash lookup instead of
            # linear scan; block construct avoids polluting outer scope.
            ic_body += [
                "block",
                "  integer :: lc_tend_idx",
                "  character(len=512) :: lc_tend_errmsg",
                f"  nullify({lc_ref})",
                f"  call {_cam_obj}%const_index(lc_tend_idx, '{_cst_std}', &",
                f"      errcode=errflg, errmsg=lc_tend_errmsg)",
                f"  if (errflg == 0 .and. lc_tend_idx > 0) then",
                f"    {lc_ref} => {ref('lc_const_tend')}(:, :, lc_tend_idx)",
                "  else",
                "    errflg = 0",
                "  end if",
                "end block",
            ]
            # No separate enter-data here: lc_name is a pointer slice into
            # lc_const_tend, already made resident above -- OpenACC tracks
            # residency by the underlying array's actual memory, not the
            # pointer name used to reference a slice of it.
        else:
            # alloc_dims may reference lc_num; replace with size(lc_all_constituents)
            alloc_str = alloc_dims.replace("lc_num", f"size({_lc_all})")
            ic_body += [
                f"if (allocated({lc_ref})) deallocate({lc_ref})",
                f"allocate({lc_ref}({alloc_str}))",
                f"{lc_ref} = 0.0_kind_phys",
            ]
            if needs_gpu:
                ic_body += [
                    "#ifdef USE_GPU",
                    f"!$acc enter data copyin({lc_ref})",
                    "#endif",
                ]
    ic_op = ConstituentFunctionOp(
        fn_name=f"{h}_ccpp_initialize_constituents",
        is_function=False,
        args=["ncols", "pver", "errflg", "errmsg"]
            + ([instance_local_name] if multi_instance else []),
        use_stmts=[],
        arg_decls=ic_arg_decls,
        local_decls=[],
        body_ops=[RawFortranLinesOp("\n".join(ic_body))],
    )

    # ── 6. constituents_array ────────────────────────────────────────────
    ca_op = ConstituentFunctionOp(
        fn_name=f"{h}_constituents_array",
        is_function=True,
        args=[instance_local_name] if multi_instance else [],
        use_stmts=[],
        arg_decls=[f"integer, intent(in) :: {instance_local_name}"] if multi_instance else [],
        local_decls=[],
        result_name="ptr",
        result_decl="real(kind=kind_phys), pointer :: ptr(:, :, :)",
        body_ops=[RawFortranLinesOp(f"ptr => {ref('lc_constituent_array')}")],
    )

    # ── 7. const_get_index ───────────────────────────────────────────────
    # Delegate to cam_constituents_obj%const_index (hash lookup) instead of
    # linear scan.  Hash keys are stored lowercase, so pass to_lower(std_name).
    ci_arg_decls = [
        "character(len=*), intent(in) :: std_name",
        "integer, intent(out) :: index",
        "integer, intent(out) :: errflg",
        f"character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
    ] + ([f"integer, intent(in) :: {instance_local_name}"] if multi_instance else [])
    ci_body = ["errflg = 0", "errmsg = ''", "index = -1"]
    if multi_instance:
        ci_body += _error_guard(
            "allocated(lc_instances)",
            "const_get_index: constituents not registered",
        )
    ci_body += _error_guard(
        f"allocated({ref('lc_all_constituents')})",
        "const_get_index: constituents not registered",
    )
    ci_body += [
        f"call {ref('cam_constituents_obj')}%const_index(index, to_lower(std_name), &",
        f"    errcode=errflg, errmsg=errmsg)",
        "if (errflg /= 0 .or. index <= 0) then",
        "  errflg = 1",
        "  write(errmsg, '(3a)') 'const_get_index: constituent ', trim(std_name), ' not found'",
        "end if",
    ]
    ci_op = ConstituentFunctionOp(
        fn_name=f"{h}_const_get_index",
        is_function=False,
        args=["std_name", "index", "errflg", "errmsg"]
            + ([instance_local_name] if multi_instance else []),
        use_stmts=["use ccpp_constituent_prop_mod, only: to_lower"],
        arg_decls=ci_arg_decls,
        local_decls=[],
        body_ops=[RawFortranLinesOp("\n".join(ci_body))],
    )

    # ── 8. model_const_properties ────────────────────────────────────────
    mp_op = ConstituentFunctionOp(
        fn_name=f"{h}_model_const_properties",
        is_function=True,
        args=[instance_local_name] if multi_instance else [],
        use_stmts=[],
        arg_decls=[f"integer, intent(in) :: {instance_local_name}"] if multi_instance else [],
        local_decls=[],
        result_name="ptr",
        result_decl="type(ccpp_constituent_prop_ptr_t), pointer :: ptr(:)",
        body_ops=[RawFortranLinesOp(f"ptr => {ref('lc_const_props')}")],
    )

    # ── 9. gather_constituents / 10. update_constituents (cam_host only) ──
    if cam_host:
        # cam_host never supports multi-instance (asserted above), so bypass ref()
        # to avoid a latent reference to lc_instances(instance)%cam_constituents_obj
        # in a subroutine that has no instance argument.
        _cam_obj_ref = "cam_constituents_obj"
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
                f"call {_cam_obj_ref}%copy_in(const_array, errcode=errcode, errmsg=errmsg)"
            )],
        )
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
                f"call {_cam_obj_ref}%copy_out(const_array, errcode=errcode, errmsg=errmsg)"
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
    ]
    if cam_host:
        public_names_list += [
            f"{h}_ccpp_gather_constituents",
            f"{h}_ccpp_update_constituents",
        ]

    if cam_host:
        api_op = CamHostConstituentApiOp(
            public_names_list,
            [isc_op, da_op, rc_op, nc_op, ic_op, ca_op, ci_op, mp_op, gc_op, uc_op],
        )
    else:
        api_op = NonCamHostConstituentApiOp(
            public_names_list,
            type_defs_text,
            [isc_op, da_op, rc_op, nc_op, ic_op, ca_op, ci_op, mp_op],
        )

    # ── USE stubs for ccpp_constituent_prop_mod ──────────────────────────
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
