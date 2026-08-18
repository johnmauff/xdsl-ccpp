"""Constituent-API generation.

Extracted from ccpp_cap.py's CCPPCAP pass (Phase 2 of the restructuring plan):
builds the runtime constituent registration/query API for a suite. Kept as a
plain importable module (not a registered pass) per the phase plan -- called
directly from generate-ccpp-cap's final module assembly.
"""

from xdsl.dialects import llvm
from xdsl.dialects.builtin import StringAttr, i8

from xdsl_ccpp.dialects.ccpp_utils import ConstituentApiOp, ModuleVarOp
from xdsl_ccpp.transforms.util.cap_shared import _CCPP_CONSTITUENT_MOD, _bare
from xdsl_ccpp.transforms.util.ccpp_descriptors import CCPPType
from xdsl_ccpp.util.ccpp_conventions import CCPP_ERRMSG_LEN


def _collect_constituent_info(meta_data):
    """Extract constituent info from scheme metadata.

    Scans all SCHEME tables to find:
      - dynamic_array_names: bare arg names in _register tables with
        allocatable=True, type=ccpp_constituent_properties_t
      - fixed_advected: list of (std_name, units, default_val) for args
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
                    and fn_arg.getAttr("type") == "ccpp_constituent_properties_t"
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
                    if std_name not in seen_fixed:
                        seen_fixed.add(std_name)
                        fixed_advected.append((std_name, units, default_val))

    return dynamic_array_names, fixed_advected, references_count



def _generate_constituent_api(
    camel_name: str,
    dynamic_array_names: list,
    fixed_advected: list,
    scratch_vars: list | None = None,
    framework_var_residency: dict | None = None,
    instance_local_name: "str | None" = None,
    ninstances_local_name: "str | None" = None,
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
                ftn_attrs="target",
                rank=1,
            )
        )
        module_var_ops.append(
            ModuleVarOp("lc_constituent_array", "real", kind="kind_phys", ftn_attrs="target", rank=3)
        )
        module_var_ops.append(
            ModuleVarOp("lc_const_tend", "real", kind="kind_phys", ftn_attrs="target", rank=3)
        )
        module_var_ops.append(
            ModuleVarOp("lc_const_props", "type", ddt_name="ccpp_constituent_prop_ptr_t", ftn_attrs="target", rank=1)
        )
        for lc_name, rank, _alloc_dims, _cst_std, _needs_gpu in scratch_vars:
            module_var_ops.append(
                ModuleVarOp(lc_name, "real", kind="kind_phys",
                            ftn_attrs="pointer" if _cst_std else None, rank=rank)
            )
    else:
        type_def_lines.append(f"type :: {instance_type_name}")
        for n in dynamic_array_names:
            type_def_lines.append(
                f"  type(ccpp_constituent_properties_t), allocatable :: lc_{n}(:)"
            )
        type_def_lines.append(
            "  type(ccpp_constituent_properties_t), allocatable, target :: lc_all_constituents(:)"
        )
        type_def_lines.append(
            "  real(kind=kind_phys), allocatable, target :: lc_constituent_array(:, :, :)"
        )
        type_def_lines.append(
            "  real(kind=kind_phys), allocatable, target :: lc_const_tend(:, :, :)"
        )
        type_def_lines.append(
            "  type(ccpp_constituent_prop_ptr_t), allocatable, target :: lc_const_props(:)"
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
            ModuleVarOp("lc_instances", "type", ddt_name=instance_type_name, rank=1)
        )
    type_defs_text = "\n".join(type_def_lines) if type_def_lines else None

    # ── Helper: dedup fragment ───────────────────────────────────────────
    def _dedup_block(src_sname, src_units, src_assign, dst_tmp, indent="    "):
        lines = []
        lines.append(f"{indent}lc_found = .false.")
        lines.append(f"{indent}do lc_j = 1, lc_num")
        lines.append(f"{indent}  if (trim({dst_tmp}(lc_j)%std_name) == trim({src_sname})) then")
        lines.append(f"{indent}    lc_found = .true.")
        lines.append(f"{indent}    if (trim({dst_tmp}(lc_j)%units) /= trim({src_units})) then")
        lines.append(
            f"{indent}      write(errmsg, '(3a)') 'ccp_model_const_add_metadata ERROR: "
            f"Trying to add constituent ', trim({src_sname}), &"
        )
        lines.append(
            f"{indent}        ' but an incompatible constituent with this name already exists'"
        )
        lines.append(f"{indent}      errflg = 1")
        lines.append(f"{indent}      return")
        lines.append(f"{indent}    end if")
        lines.append(f"{indent}    exit")
        lines.append(f"{indent}  end if")
        lines.append(f"{indent}end do")
        lines.append(f"{indent}if (.not. lc_found) then")
        lines.append(f"{indent}  lc_num = lc_num + 1")
        lines.append(f"{indent}  {dst_tmp}(lc_num) = {src_assign}")
        lines.append(f"{indent}end if")
        return lines

    _instance_arg = f", {instance_local_name}" if multi_instance else ""
    _instance_decl = (
        [f"    integer, intent(in) :: {instance_local_name}"] if multi_instance else []
    )

    # ── 1. is_scheme_constituent ─────────────────────────────────────────
    fixed_names_str = ", ".join(f"'{s}'" for s, _u, _d in fixed_advected)
    isc_lines = [
        f"  subroutine {h}_ccpp_is_scheme_constituent(std_name, is_const, errflg, errmsg{_instance_arg})",
        f"    character(len=*), intent(in) :: std_name",
        f"    logical, intent(out) :: is_const",
        f"    integer, intent(out) :: errflg",
        f"    character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
        *_instance_decl,
        f"    integer :: lc_idx",
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
            f"{indent}    if (trim({dyn_ref}(lc_idx)%std_name) == trim(std_name)) then",
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
        f"  subroutine {h}_ccpp_register_constituents(host_constituents, errmsg, errflg{rc_sig_extra})",
        f"    use ccpp_scheme_utils, only: ccpp_scheme_utils_set_constituents",
        f"    type(ccpp_constituent_properties_t), intent(in) :: host_constituents(:)",
        f"    character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
        f"    integer, intent(out) :: errflg",
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
        f"    errflg = 0",
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
            f"{dyn_ref}(lc_i)%std_name",
            f"{dyn_ref}(lc_i)%units",
            f"{dyn_ref}(lc_i)",
            "lc_tmp",
            indent="        ",
        )
        rc_lines += [f"      end do", f"    end if"]
    for std_name_f, units_f, default_val_f in fixed_advected:
        rc_lines += [
            f"    lc_found = .false.",
            f"    do lc_j = 1, lc_num",
            f"      if (trim(lc_tmp(lc_j)%std_name) == '{std_name_f}') then",
            f"        lc_found = .true.",
            f"        if (trim(lc_tmp(lc_j)%units) /= '{units_f}') then",
            f"          write(errmsg, '(3a)') 'ccp_model_const_add_metadata ERROR: "
            f"Trying to add constituent ', '{std_name_f}', &",
            f"            ' but an incompatible constituent with this name already exists'",
            f"          errflg = 1",
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
            f"units='{units_f}', errcode=errflg, errmsg=errmsg, advected=.true."
        )
        if default_val_f is not None:
            inst_args += f", default_value={default_val_f}"
        rc_lines += [
            f"      call lc_tmp(lc_num)%instantiate({inst_args})",
            f"      if (errflg /= 0) return",
            f"    end if",
        ]
    rc_lines += [f"    do lc_i = 1, size(host_constituents)"]
    rc_lines += _dedup_block(
        "host_constituents(lc_i)%std_name",
        "host_constituents(lc_i)%units",
        "host_constituents(lc_i)",
        "lc_tmp",
        indent="      ",
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
        f"      {_lc_props}(lc_i)%ptr => {_lc_all}(lc_i)",
        f"    end do",
        f"    call ccpp_scheme_utils_set_constituents({_lc_all})",
        f"  end subroutine {h}_ccpp_register_constituents",
    ]

    # ── 4. number_constituents ───────────────────────────────────────────
    nc_lines = [
        f"  subroutine {h}_ccpp_number_constituents(num_advected, errmsg, errflg{_instance_arg})",
        f"    integer, intent(out) :: num_advected",
        f"    character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
        f"    integer, intent(out) :: errflg",
        *_instance_decl,
        f"    errflg = 0",
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
        f"    errflg = 0",
        f"    errmsg = ''",
    ]
    if multi_instance:
        ic_lines += [
            f"    if (.not. allocated(lc_instances)) then",
            f"      errflg = 1",
            f"      errmsg = 'ccpp_initialize_constituents: register_constituents not called'",
            f"      return",
            f"    end if",
        ]
    ic_lines += [
        f"    if (.not. allocated({ref('lc_all_constituents')})) then",
        f"      errflg = 1",
        f"      errmsg = 'ccpp_initialize_constituents: register_constituents not called'",
        f"      return",
        f"    end if",
        f"    lc_num = size({ref('lc_all_constituents')})",
        f"    if (allocated({ref('lc_constituent_array')})) deallocate({ref('lc_constituent_array')})",
        f"    allocate({ref('lc_constituent_array')}(ncols, pver, lc_num))",
        f"    {ref('lc_constituent_array')} = 0.0_kind_phys",
        f"    do lc_i = 1, lc_num",
        f"      if ({ref('lc_all_constituents')}(lc_i)%default_val_set) then",
        f"        {ref('lc_constituent_array')}(:, :, lc_i) = {ref('lc_all_constituents')}(lc_i)%default_val",
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
                f"      if (trim({ref('lc_all_constituents')}(lc_i)%std_name) == '{_cst_std}') then",
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
        f"  function {h}_constituents_array({instance_local_name if multi_instance else ''}) result(ptr)",
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
        f"    errflg = 0",
        f"    errmsg = ''",
        f"    index = -1",
    ]
    if multi_instance:
        ci_lines += [
            f"    if (.not. allocated(lc_instances)) then",
            f"      errflg = 1",
            f"      errmsg = 'const_get_index: constituents not registered'",
            f"      return",
            f"    end if",
        ]
    ci_lines += [
        f"    if (.not. allocated({ref('lc_all_constituents')})) then",
        f"      errflg = 1",
        f"      errmsg = 'const_get_index: constituents not registered'",
        f"      return",
        f"    end if",
        f"    do lc_i = 1, size({ref('lc_all_constituents')})",
        f"      if (trim({ref('lc_all_constituents')}(lc_i)%std_name) == trim(std_name)) then",
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
        f"  function {h}_model_const_properties({instance_local_name if multi_instance else ''}) result(ptr)",
        *_instance_decl,
        f"    type(ccpp_constituent_prop_ptr_t), pointer :: ptr(:)",
        f"    ptr => {ref('lc_const_props')}",
        f"  end function {h}_model_const_properties",
    ]

    all_lines = (
        isc_lines + [""]
        + da_lines + [""]
        + rc_lines + [""]
        + nc_lines + [""]
        + ic_lines + [""]
        + ca_lines + [""]
        + ci_lines + [""]
        + mp_lines
    )
    body_text = "\n".join(all_lines)

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

    api_op = ConstituentApiOp(body_text, public_names_list, type_defs=type_defs_text)

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
