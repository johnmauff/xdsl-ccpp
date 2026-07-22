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

    Returns (dynamic_array_names, fixed_advected).
    """
    dynamic_array_names: list = []
    fixed_advected: list = []
    seen_fixed: set = set()

    for _scheme_name, props in meta_data.items():
        if props.getAttr("type") != CCPPType.SCHEME:
            continue
        for table_name, arg_table in props.arg_tables.items():
            is_register = table_name.endswith("_register")
            for fn_arg in arg_table.getFunctionArguments():
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

    return dynamic_array_names, fixed_advected



def _generate_constituent_api(
    camel_name: str,
    dynamic_array_names: list,
    fixed_advected: list,
    scratch_vars: list | None = None,
    framework_var_residency: dict | None = None,
):
    """Generate constituent registration API as raw Fortran text.

    framework_var_residency: cap var name ("lc_constituent_array",
    "lc_const_tend") -> True if CapScratch GPU residency should be
    established for it (see ccpp_cap.py's _build_cap_var_map) -- emitted as
    plain text (`#ifdef USE_GPU` / `!$acc enter data create(...)` /
    `#endif`) directly after each array's existing allocate block in
    ic_lines, matching the surrounding generation style: this whole
    subsystem builds Fortran source as raw text (ConstituentApiOp's body is
    a plain StringAttr), there's no IR op to attach a residency property to
    the way SuiteOwned's LazyAllocOp allowed.

    Returns (module_var_ops, constituent_api_op, global_stub_ops).
    """
    h = camel_name
    framework_var_residency = framework_var_residency or {}
    dyn_lc = [f"lc_{n}" for n in dynamic_array_names]

    # ── Module-level variable declarations ──────────────────────────────
    module_var_ops: list = []
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
    for lc_name, rank, _alloc_dims, _cst_std, _needs_gpu in (scratch_vars or []):
        module_var_ops.append(
            ModuleVarOp(lc_name, "real", kind="kind_phys",
                        ftn_attrs="pointer" if _cst_std else None, rank=rank)
        )

    # ── Helper: dedup fragment ───────────────────────────────────────────
    def _dedup_block(src_sname, src_units, src_assign, indent="    "):
        lines = []
        lines.append(f"{indent}lc_found = .false.")
        lines.append(f"{indent}do lc_j = 1, lc_num")
        lines.append(f"{indent}  if (trim(lc_tmp(lc_j)%std_name) == trim({src_sname})) then")
        lines.append(f"{indent}    lc_found = .true.")
        lines.append(f"{indent}    if (trim(lc_tmp(lc_j)%units) /= trim({src_units})) then")
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
        lines.append(f"{indent}  lc_tmp(lc_num) = {src_assign}")
        lines.append(f"{indent}end if")
        return lines

    # ── 1. is_scheme_constituent ─────────────────────────────────────────
    fixed_names_str = ", ".join(f"'{s}'" for s, _u, _d in fixed_advected)
    isc_lines = [
        f"  subroutine {h}_ccpp_is_scheme_constituent(std_name, is_const, errflg, errmsg)",
        f"    character(len=*), intent(in) :: std_name",
        f"    logical, intent(out) :: is_const",
        f"    integer, intent(out) :: errflg",
        f"    character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
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
    for dyn_var in dyn_lc:
        isc_lines += [
            f"      if (allocated({dyn_var})) then",
            f"        do lc_idx = 1, size({dyn_var})",
            f"          if (trim({dyn_var}(lc_idx)%std_name) == trim(std_name)) then",
            f"            is_const = .true.",
            f"            return",
            f"          end if",
            f"        end do",
            f"      end if",
        ]
    isc_lines += [
        f"    end select",
        f"  end subroutine {h}_ccpp_is_scheme_constituent",
    ]

    # ── 2. deallocate_dynamic_constituents ───────────────────────────────
    da_lines = [f"  subroutine {h}_ccpp_deallocate_dynamic_constituents()"]
    for dyn_var in dyn_lc:
        da_lines.append(f"    if (allocated({dyn_var})) deallocate({dyn_var})")
    da_lines += [
        f"    if (allocated(lc_all_constituents)) deallocate(lc_all_constituents)",
        f"    if (allocated(lc_const_props)) deallocate(lc_const_props)",
        f"    if (allocated(lc_constituent_array)) deallocate(lc_constituent_array)",
        f"    if (allocated(lc_const_tend)) deallocate(lc_const_tend)",
    ]
    for lc_name, _rank, _alloc_dims, _cst_std, _needs_gpu in (scratch_vars or []):
        if _cst_std:
            da_lines.append(f"    nullify({lc_name})")
        else:
            da_lines.append(f"    if (allocated({lc_name})) deallocate({lc_name})")
    da_lines.append(f"  end subroutine {h}_ccpp_deallocate_dynamic_constituents")

    # ── 3. register_constituents ─────────────────────────────────────────
    n_fixed = len(fixed_advected)
    rc_lines = [
        f"  subroutine {h}_ccpp_register_constituents(host_constituents, errmsg, errflg)",
        f"    use ccpp_scheme_utils, only: ccpp_scheme_utils_set_constituents",
        f"    type(ccpp_constituent_properties_t), intent(in) :: host_constituents(:)",
        f"    character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
        f"    integer, intent(out) :: errflg",
        f"    integer :: lc_max, lc_num, lc_i, lc_j",
        f"    logical :: lc_found",
        f"    type(ccpp_constituent_properties_t), allocatable :: lc_tmp(:)",
        f"    errflg = 0",
        f"    errmsg = ''",
        f"    lc_max = 0",
    ]
    for dyn_var in dyn_lc:
        rc_lines.append(f"    if (allocated({dyn_var})) lc_max = lc_max + size({dyn_var})")
    rc_lines += [
        f"    lc_max = lc_max + {n_fixed}",
        f"    lc_max = lc_max + size(host_constituents)",
        f"    allocate(lc_tmp(lc_max))",
        f"    lc_num = 0",
    ]
    for dyn_var in dyn_lc:
        rc_lines += [
            f"    if (allocated({dyn_var})) then",
            f"      do lc_i = 1, size({dyn_var})",
        ]
        rc_lines += _dedup_block(
            f"{dyn_var}(lc_i)%std_name",
            f"{dyn_var}(lc_i)%units",
            f"{dyn_var}(lc_i)",
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
        indent="      ",
    )
    rc_lines += [
        f"    end do",
        f"    if (allocated(lc_all_constituents)) deallocate(lc_all_constituents)",
        f"    allocate(lc_all_constituents(lc_num))",
        f"    lc_all_constituents(1:lc_num) = lc_tmp(1:lc_num)",
        f"    deallocate(lc_tmp)",
        f"    if (allocated(lc_const_props)) deallocate(lc_const_props)",
        f"    allocate(lc_const_props(lc_num))",
        f"    do lc_i = 1, lc_num",
        f"      lc_const_props(lc_i)%ptr => lc_all_constituents(lc_i)",
        f"    end do",
        f"    call ccpp_scheme_utils_set_constituents(lc_all_constituents)",
        f"  end subroutine {h}_ccpp_register_constituents",
    ]

    # ── 4. number_constituents ───────────────────────────────────────────
    nc_lines = [
        f"  subroutine {h}_ccpp_number_constituents(num_advected, errmsg, errflg)",
        f"    integer, intent(out) :: num_advected",
        f"    character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
        f"    integer, intent(out) :: errflg",
        f"    errflg = 0",
        f"    errmsg = ''",
        f"    if (allocated(lc_all_constituents)) then",
        f"      num_advected = size(lc_all_constituents)",
        f"    else",
        f"      num_advected = 0",
        f"    end if",
        f"  end subroutine {h}_ccpp_number_constituents",
    ]

    # ── 5. initialize_constituents ───────────────────────────────────────
    ic_lines = [
        f"  subroutine {h}_ccpp_initialize_constituents(ncols, pver, errflg, errmsg)",
        f"    integer, intent(in) :: ncols",
        f"    integer, intent(in) :: pver",
        f"    integer, intent(out) :: errflg",
        f"    character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
        f"    integer :: lc_num, lc_i",
        f"    errflg = 0",
        f"    errmsg = ''",
        f"    if (.not. allocated(lc_all_constituents)) then",
        f"      errflg = 1",
        f"      errmsg = 'ccpp_initialize_constituents: register_constituents not called'",
        f"      return",
        f"    end if",
        f"    lc_num = size(lc_all_constituents)",
        f"    if (allocated(lc_constituent_array)) deallocate(lc_constituent_array)",
        f"    allocate(lc_constituent_array(ncols, pver, lc_num))",
        f"    lc_constituent_array = 0.0_kind_phys",
        f"    do lc_i = 1, lc_num",
        f"      if (lc_all_constituents(lc_i)%default_val_set) then",
        f"        lc_constituent_array(:, :, lc_i) = lc_all_constituents(lc_i)%default_val",
        f"      end if",
        f"    end do",
    ]
    if framework_var_residency.get("lc_constituent_array"):
        ic_lines += [
            f"#ifdef USE_GPU",
            f"    !$acc enter data create(lc_constituent_array)",
            f"#endif",
        ]
    ic_lines += [
        f"    if (allocated(lc_const_tend)) deallocate(lc_const_tend)",
        f"    allocate(lc_const_tend(ncols, pver, lc_num))",
        f"    lc_const_tend = 0.0_kind_phys",
    ]
    if framework_var_residency.get("lc_const_tend"):
        ic_lines += [
            f"#ifdef USE_GPU",
            f"    !$acc enter data create(lc_const_tend)",
            f"#endif",
        ]
    for lc_name, _rank, alloc_dims, _cst_std, needs_gpu in (scratch_vars or []):
        if _cst_std:
            ic_lines += [
                f"    nullify({lc_name})",
                f"    do lc_i = 1, lc_num",
                f"      if (trim(lc_all_constituents(lc_i)%std_name) == '{_cst_std}') then",
                f"        {lc_name} => lc_const_tend(:, :, lc_i)",
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
                f"    if (allocated({lc_name})) deallocate({lc_name})",
                f"    allocate({lc_name}({alloc_dims}))",
                f"    {lc_name} = 0.0_kind_phys",
            ]
            if needs_gpu:
                ic_lines += [
                    f"#ifdef USE_GPU",
                    f"    !$acc enter data create({lc_name})",
                    f"#endif",
                ]
    ic_lines.append(f"  end subroutine {h}_ccpp_initialize_constituents")

    # ── 6. constituents_array ────────────────────────────────────────────
    ca_lines = [
        f"  function {h}_constituents_array() result(ptr)",
        f"    real(kind=kind_phys), pointer :: ptr(:, :, :)",
        f"    ptr => lc_constituent_array",
        f"  end function {h}_constituents_array",
    ]

    # ── 7. const_get_index ───────────────────────────────────────────────
    ci_lines = [
        f"  subroutine {h}_const_get_index(std_name, index, errflg, errmsg)",
        f"    character(len=*), intent(in) :: std_name",
        f"    integer, intent(out) :: index",
        f"    integer, intent(out) :: errflg",
        f"    character(len={CCPP_ERRMSG_LEN}), intent(out) :: errmsg",
        f"    integer :: lc_i",
        f"    errflg = 0",
        f"    errmsg = ''",
        f"    index = -1",
        f"    if (.not. allocated(lc_all_constituents)) then",
        f"      errflg = 1",
        f"      errmsg = 'const_get_index: constituents not registered'",
        f"      return",
        f"    end if",
        f"    do lc_i = 1, size(lc_all_constituents)",
        f"      if (trim(lc_all_constituents(lc_i)%std_name) == trim(std_name)) then",
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
        f"  function {h}_model_const_properties() result(ptr)",
        f"    type(ccpp_constituent_prop_ptr_t), pointer :: ptr(:)",
        f"    ptr => lc_const_props",
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

    api_op = ConstituentApiOp(body_text, public_names_list)

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

