"""Constituent-API generation.

Extracted from ccpp_cap.py's CCPPCAP pass: builds the runtime constituent
registration/query API for a suite. Kept as a plain importable module (not
a registered pass) -- called directly from generate-ccpp-cap's final
module assembly.
"""

from xdsl.dialects import arith, llvm, memref
from xdsl.dialects.builtin import DYNAMIC_INDEX, IntegerAttr, StringAttr, i1, i8, i32

from xdsl_ccpp.dialects.ccpp_utils import (
    AccEnterDataOp,
    ActiveCheckOp,
    AllocateOp,
    ArrayConstructorExprOp,
    AssignOp,
    CallExprOp,
    CallStatementOp,
    ClearErrStateOp,
    DdtComponentDeclOp,
    DdtMethodCallOp,
    DerivedType,
    DerivedTypeDefOp,
    DoLoopOp,
    ErrorExitOp,
    ErrorGuardOp,
    ErrorPropagateOp,
    HostVarRefOp,
    IndexExprOp,
    KeywordArgExprOp,
    MetadataLiteralExprOp,
    MethodCallExprOp,
    MemberAccessExprOp,
    ModuleVarOp,
    ConstituentApiOp,
    NullifyPointerOp,
    PointerAssignOp,
    ReturnStmtOp,
    SafeDeallocOp,
    ScopedBlockOp,
    SliceExprOp,
    StringConcatExprOp,
    StringLiteralExprOp,
    VarRefExprOp,
    WriteStmtOp,
    ZeroFillOp,
)
from xdsl_ccpp.transforms.capgen_api import capgen_constituent_routines
from xdsl_ccpp.transforms.util.cap_shared import (
    _CCPP_CONSTITUENT_MOD,
    InstancePair,
    _allocated_cond,
    _assign_const,
    _int_var_cmp_zero,
    _not_allocated_cond,
    _scf_if,
    fixed_interface_fn,
    _trim_eq_cond,
    constituents_obj_name,
)
from xdsl_ccpp.transforms.util.ccpp_descriptors import CCPPType
from xdsl_ccpp.transforms.util.typing import TypeConversions
from xdsl_ccpp.util.ccpp_conventions import (
    CCPP_ERRMSG_LEN,
    CCPP_HORIZ_DIM_STD_NAME,
    CCPP_LOOP_EXTENT_STD_NAME,
    CCPP_VERT_DIM_STD_NAME,
    mark_pointer_local,
    name_local,
)


def _errcode_errmsg_kwargs(
    errcode_name: str = "errcode", errmsg_name: str = "errmsg"
) -> "list[KeywordArgExprOp]":
    """The recurring errcode=<errcode_name>, errmsg=<errmsg_name> trailing
    keyword-arg pair shared by almost every DdtMethodCallOp in this
    module."""
    return [
        KeywordArgExprOp("errcode", VarRefExprOp(errcode_name)),
        KeywordArgExprOp("errmsg", VarRefExprOp(errmsg_name)),
    ]


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
                    if fn_arg.name not in dynamic_array_names:
                        dynamic_array_names.append(fn_arg.name)
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
                    local_name = fn_arg.name
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


def host_bound_constituent_std_names(meta_data) -> frozenset:
    """Std names of the advected scheme args the host cap passes in.

    These are the fixed-advected constituents the cap registers itself
    (_collect_constituent_info, after its dry-air filter). As in capgen, a
    scheme arg with one of these names is a view of the host cap's
    constituent array in every phase, never storage of the suite cap. An
    advected arg whose name was filtered out (a *_wrt_dry_air form produced
    by wet_to_dry_* schemes) stays suite-owned.
    """
    _, fixed_advected, _ = _collect_constituent_info(meta_data)
    return frozenset(std_name for std_name, *_ in fixed_advected)



def _generate_constituent_api(
    camel_name: str,
    dynamic_array_names: list,
    fixed_advected: list,
    scratch_vars: list | None = None,
    framework_var_residency: dict | None = None,
    instances: "InstancePair | None" = None,
    capgen_api: bool = False,
    needs_const_tend: bool = False,
    ddt_source_module: dict | None = None,
):
    """Generate constituent registration API as raw Fortran text.

    framework_var_residency: cap var name ("lc_constituent_array",
    "lc_const_tend") -> True if CapScratch GPU residency should be
    established for it (see ccpp_cap.py's _build_cap_var_map): an
    AccEnterDataOp copyin directly after the array's allocate-and-initialize
    block in initialize_constituents (scratch vars with needs_gpu likewise),
    balanced by the AccExitDataOp ccpp_cap.py's _inject_capscratch_gpu_exit
    emits in ccpp_final. `copyin`, not `create`: each array is
    host-initialized (a default-value loop or a `= 0.0_kind_phys` fill)
    immediately before, and `create` would allocate uninitialized device
    memory without transferring that initialized state -- caught by Copilot
    review on PR #38.

    instances -- real capgen-v1's multi-instance model: when set (the host declares
    instance_number/number_of_instances), every module-level array this API
    owns (lc_all_constituents, lc_constituent_array, lc_const_tend,
    lc_const_props, each scheme's own dynamic-array, and any scratch var)
    becomes one member of a new per-instance bundle type
    (<camel_name>_lc_instance_t), collected into a single allocatable
    lc_instances(:) array -- the same "array-of-DDT-instance" idiom
    examples/instances' own host-declared instance_data already establishes
    for this codebase, just cap-owned/generated here instead of
    host-declared. lc_instances is lazily allocated (sized by
    instances.count) inside register_constituents only -- the one
    entry point the driver always calls first, with ninstances, before any
    other constituent-API call for a given instance; every other subroutine
    treats "lc_instances not yet allocated" as "register_constituents not
    called," matching the existing single-instance code's own precondition
    checks. When None (a non-multi-instance host, by far the common
    case), every array stays a plain module-scope variable exactly as
    before -- this whole codepath is unreachable and output is
    byte-identical to before this feature existed.

    ddt_source_module -- DDT type name -> Fortran module name, from the
    generic ddt_source_module mechanism (collect_ddt_source_modules,
    reflecting a real .meta module_name override if the host declares
    one). Consulted for this function's own 3 hardcoded constituent DDT
    stub types, falling back to _CCPP_CONSTITUENT_MOD when absent/None or
    when a given type isn't a key (e.g. ccpp_model_constituents_t, which
    is never a parsed argument type anywhere and so never appears in this
    dict regardless of how complete it is).

    Returns (module_var_ops, constituent_api_op, global_stub_ops).
    """
    instance_local_name = instances.instance if instances else None
    ninstances_local_name = instances.count if instances else None

    if capgen_api and instance_local_name is not None:
        raise ValueError(
            "capgen_api=True with multi-instance metadata is not supported; "
            "CAM does not use per-instance constituent containers"
        )

    h = camel_name
    n_fixed = len(fixed_advected)
    framework_var_residency = framework_var_residency or {}
    scratch_vars = scratch_vars or []
    multi_instance = instance_local_name is not None
    instance_type_name = f"{h}_lc_instance_t"
    # Module variables named after the host, as capgen names them.
    const_obj = constituents_obj_name(h)
    const_stdnames = f"{h}_model_const_stdnames"
    const_indices = f"{h}_model_const_indices"

    def _ref_expr(name: str, result_type=None):
        """A reference to module-level variable `name`: a plain
        VarRefExprOp when not multi-instance, else a MemberAccessExprOp
        chained on a fresh lc_instances(instance) IndexExprOp. Each call
        builds new ops, so call it once per use."""
        if multi_instance:
            idx = IndexExprOp(VarRefExprOp("lc_instances"), [VarRefExprOp(instance_local_name)])
            return MemberAccessExprOp(idx, name, result_type=result_type)
        return VarRefExprOp(name, result_type=result_type)

    def _size_of(name: str):
        """size(<reference to name>), a default integer."""
        return CallExprOp("size", [_ref_expr(name)], result_type=i32)

    def _alloc_extent(dim_std_name: str):
        """The extent this API allocates a scratch array with along the
        dimension named dim_std_name; 1 for one it has no extent for."""
        if dim_std_name in (CCPP_LOOP_EXTENT_STD_NAME, CCPP_HORIZ_DIM_STD_NAME):
            return VarRefExprOp("ncols")
        if dim_std_name == CCPP_VERT_DIM_STD_NAME:
            return VarRefExprOp("pver")
        if dim_std_name == "number_of_ccpp_constituents":
            return _size_of("lc_all_constituents")
        return arith.ConstantOp(IntegerAttr.from_int_and_width(1, 32))

    def _allocated(name: str):
        """allocated(<reference to name>), an i1 condition."""
        return CallExprOp("allocated", [_ref_expr(name)], result_type=i1)

    def _enter_data_copyin(name: str, rank: int) -> list:
        """Make module-level real array `name` device-resident: a reference
        to it (the same lc_instances(instance)%name form _ref_expr() gives
        when multi-instance) and an AccEnterDataOp copyin. ccpp_cap.py's
        _inject_capscratch_gpu_exit emits the matching AccExitDataOp."""
        var_type = TypeConversions.convert("real", "kind_phys", rank)
        if multi_instance:
            ref_op = HostVarRefOp("lc_instances", "", var_type,
                                  member_path=name, index_expr=instance_local_name)
        else:
            ref_op = HostVarRefOp(name, "", var_type)
        return [ref_op, AccEnterDataOp(copyin=[ref_op.res])]

    # ── Module-level variable declarations ──────────────────────────────
    # Non-multi-instance: unchanged -- one plain ModuleVarOp per array.
    # Multi-instance: every one of these becomes a DdtComponentDeclOp
    # component of a new DerivedTypeDefOp bundle type instead (built below,
    # wired into ConstituentApiOp's body), and the only actual
    # module variable is the single lc_instances(:) array.
    # The fixed-advected constituents' standard names, as the initial value
    # of <host>_model_const_stdnames: [ character(len=<longest>) :: 'a', ... ].
    _max_std_len = max((len(s) for s, *_ in fixed_advected), default=0)

    def _std_names_init():
        return ArrayConstructorExprOp(
            [StringLiteralExprOp(s) for s, *_ in fixed_advected],
            elem_type=memref.MemRefType(i8, [_max_std_len]),
        )

    module_var_ops: list = []
    component_ops: list = []
    if not multi_instance:
        # <host>_constituents_obj: scalar ccpp_model_constituents_t with target
        # (so that field_data_ptr() and constituent_props_ptr() pointer results
        # remain valid as long as this module-level variable lives).
        module_var_ops.append(
            ModuleVarOp(const_obj, "type",
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
        # lc_constituent_array: pointer into <host>_constituents_obj internal storage
        # (set by field_data_ptr() in initialize_constituents; must be pointer not
        # allocatable because the memory is owned by <host>_constituents_obj).
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
        for lc_name, rank, _alloc_dims, _cst_std, _needs_gpu, _base in scratch_vars:
            module_var_ops.append(
                ModuleVarOp(lc_name, "real", kind="kind_phys",
                            is_pointer=bool(_cst_std), rank=rank)
            )
        if n_fixed > 0:
            module_var_ops.append(ModuleVarOp(
                const_stdnames, "character",
                char_len=_max_std_len,
                fixed_dim=n_fixed,
                init_value_op=_std_names_init(),
            ))
            module_var_ops.append(ModuleVarOp(
                const_indices, "integer",
                fixed_dim=n_fixed,
                init_value_op=arith.ConstantOp(IntegerAttr.from_int_and_width(-1, 32)),
            ))
    else:
        # <host>_constituents_obj as a non-pointer, non-target DDT component.
        # TARGET is NOT allowed on derived-type components (gfortran: "Attribute
        # at (1) is not allowed in a TYPE definition").  TARGET instead goes on
        # the lc_instances(:) module variable itself below -- the standard's
        # rule that TARGET propagates from a variable to all subobjects
        # (including allocatable/ordinary components) is what makes the
        # field_data_ptr() and constituent_props_ptr() pointer results valid.
        component_ops.append(
            DdtComponentDeclOp(const_obj, "type",
                               ddt_name="ccpp_model_constituents_t", rank=0)
        )
        for n in dynamic_array_names:
            component_ops.append(
                DdtComponentDeclOp(f"lc_{n}", "type",
                                   ddt_name="ccpp_constituent_properties_t", rank=1)
            )
        component_ops.append(DdtComponentDeclOp("lc_all_constituents", "integer", rank=1))
        # lc_constituent_array: pointer component (points into <host>_constituents_obj
        # internal storage after lock_data; TARGET propagates from lc_instances).
        component_ops.append(
            DdtComponentDeclOp("lc_constituent_array", "real", kind="kind_phys",
                               is_pointer=True, rank=3)
        )
        if needs_const_tend:
            component_ops.append(
                DdtComponentDeclOp("lc_const_tend", "real", kind="kind_phys", rank=3)
            )
        component_ops.append(
            DdtComponentDeclOp("lc_const_props", "type",
                               ddt_name="ccpp_constituent_prop_ptr_t", rank=1)
        )
        for lc_name, rank, _alloc_dims, _cst_std, _needs_gpu, _base in scratch_vars:
            component_ops.append(
                DdtComponentDeclOp(lc_name, "real", kind="kind_phys",
                                   is_pointer=bool(_cst_std), rank=rank)
            )
        if n_fixed > 0:
            component_ops.append(DdtComponentDeclOp(
                const_stdnames, "character",
                char_len=_max_std_len,
                fixed_dim=n_fixed,
                init_value_op=_std_names_init(),
            ))
            component_ops.append(DdtComponentDeclOp(
                const_indices, "integer",
                fixed_dim=n_fixed,
                init_value_op=arith.ConstantOp(IntegerAttr.from_int_and_width(-1, 32)),
            ))
        module_var_ops.append(
            ModuleVarOp("lc_instances", "type", ddt_name=instance_type_name,
                        is_target=True, rank=1)
        )

    # Argument and local types of the API functions (fixed_interface_fn).
    _char = TypeConversions.getBaseType("character")
    _string = memref.MemRefType(_char, [DYNAMIC_INDEX])          # character(len=*)
    _errmsg = memref.MemRefType(_char, [CCPP_ERRMSG_LEN])
    _int = memref.MemRefType(TypeConversions.getBaseType("integer"), [])
    _logical = memref.MemRefType(i1, [])
    _real3 = TypeConversions.convert("real", "kind_phys", 3)
    _props = DerivedType("ccpp_constituent_properties_t")
    _prop_ptr = DerivedType("ccpp_constituent_prop_ptr_t")
    _instance_args = (
        [(instance_local_name, _int, "in", ())] if multi_instance else []
    )

    def _local(name: str, elem, shape=(), pointer: bool = False):
        """A named local; a pointer array's shape gives only its rank."""
        alloca = memref.AllocaOp.get(elem, shape=list(shape))
        (mark_pointer_local if pointer else name_local)(alloca, name)
        return alloca

    # ── 1. is_scheme_constituent ─────────────────────────────────────────
    isc_body_ops: list = [
        ClearErrStateOp("errflg", "errmsg"),
        _assign_const("is_const", False),
    ]
    if n_fixed > 0:
        any_eq = arith.CmpiOp(
            _ref_expr(const_stdnames, result_type=i32),
            VarRefExprOp("std_name", result_type=i32),
            "eq",
        )
        fixed_check_ops = _scf_if(
            CallExprOp("any", [any_eq], result_type=i1),
            [_assign_const("is_const", True), ReturnStmtOp()],
        )
        # The reference is lc_instances(instance)%... -- guard allocated(lc_instances)
        # before dereferencing, matching the same guard the dynamic-name loops use.
        if multi_instance:
            isc_body_ops.extend(_scf_if(_allocated_cond("lc_instances"), fixed_check_ops))
        else:
            isc_body_ops.extend(fixed_check_ops)
    for n in dynamic_array_names:
        inner_trim_check_ops = _scf_if(
            _trim_eq_cond("lc_std_name", "std_name"),
            [_assign_const("is_const", True), ReturnStmtOp()],
        )
        dyn_check_ops = _scf_if(
            _allocated(f"lc_{n}"),
            [DoLoopOp(
                "lc_idx", _size_of(f"lc_{n}"),
                [
                    DdtMethodCallOp(
                        obj_expr_op=IndexExprOp(_ref_expr(f"lc_{n}"), [VarRefExprOp("lc_idx")]),
                        method="standard_name",
                        arg_ops=[VarRefExprOp("lc_std_name")],
                    ),
                    *inner_trim_check_ops,
                ],
            )],
        )
        if multi_instance:
            isc_body_ops.extend(_scf_if(_allocated_cond("lc_instances"), dyn_check_ops))
        else:
            isc_body_ops.extend(dyn_check_ops)
    isc_op = fixed_interface_fn(
        f"{h}_ccpp_is_scheme_constituent",
        [("std_name", _string, "in", ()),
         ("is_const", _logical, "out", ()),
         ("errflg", _int, "out", ()),
         ("errmsg", _errmsg, "out", ()),
         *_instance_args],
        isc_body_ops,
        locals_=[_local("lc_idx", i32), _local("lc_std_name", i8, [256])],
    )

    # ── 2. deallocate_dynamic_constituents ───────────────────────────────
    da_body_ops: list = []
    if multi_instance:
        da_body_ops.append(ReturnStmtOp(_not_allocated_cond("lc_instances")))
    for n in dynamic_array_names:
        da_body_ops.append(SafeDeallocOp(target_op=_ref_expr(f"lc_{n}")))
    da_body_ops += [
        SafeDeallocOp(target_op=_ref_expr("lc_all_constituents")),
        SafeDeallocOp(target_op=_ref_expr("lc_const_props")),
        # lc_constituent_array is a pointer into <host>_constituents_obj storage;
        # nullify it before reset() to avoid a dangling pointer.
        NullifyPointerOp(target_op=_ref_expr("lc_constituent_array"), if_associated=True),
    ]
    if needs_const_tend:
        da_body_ops.append(SafeDeallocOp(target_op=_ref_expr("lc_const_tend")))
    for lc_name, _rank, _alloc_dims, _cst_std, _needs_gpu, _base in scratch_vars:
        if _cst_std:
            da_body_ops.append(NullifyPointerOp(target_op=_ref_expr(lc_name)))
        else:
            da_body_ops.append(SafeDeallocOp(target_op=_ref_expr(lc_name)))
    da_body_ops.append(DdtMethodCallOp(
        obj_expr_op=_ref_expr(const_obj), method="reset",
    ))
    da_op = fixed_interface_fn(
        f"{h}_ccpp_deallocate_dynamic_constituents", _instance_args, da_body_ops,
    )

    # ── 3. register_constituents ─────────────────────────────────────────
    # Uses ccpp_model_constituents_t (new_field handles dedup internally).
    _host_constituents = (
        "host_constituents", memref.MemRefType(_props, [DYNAMIC_INDEX]), "in", ("target",),
    )
    # One argument order for every host (CAM-SIMA's cam_comp.F90 passes
    # errcode/errmsg by keyword).
    rc_args = [_host_constituents, ("errmsg", _errmsg, "out", ()),
               ("errcode", _int, "out", ())]
    if multi_instance:
        rc_args += [*_instance_args, (ninstances_local_name, _int, "in", ())]
    rc_body_ops: list = [ClearErrStateOp("errcode", "errmsg")]
    if multi_instance:
        rc_body_ops.extend(_scf_if(
            _not_allocated_cond("lc_instances"),
            [AllocateOp("lc_instances", dim_ops=[VarRefExprOp(ninstances_local_name)])],
        ))
    # Count total constituents (upper bound for initialize_table)
    def _add_to_num_consts(term_op) -> AssignOp:
        """lc_num_consts = lc_num_consts + <term_op>."""
        return AssignOp(
            lhs_op=VarRefExprOp("lc_num_consts"),
            rhs_op=arith.AddiOp(VarRefExprOp("lc_num_consts", result_type=i32), term_op),
        )

    rc_body_ops.append(AssignOp(
        lhs_op=VarRefExprOp("lc_num_consts"),
        rhs_op=CallExprOp("size", [VarRefExprOp("host_constituents")], result_type=i32),
    ))
    for n in dynamic_array_names:
        rc_body_ops.extend(_scf_if(
            CallExprOp("allocated", [_ref_expr(f"lc_{n}")], result_type=i1),
            [_add_to_num_consts(
                CallExprOp("size", [_ref_expr(f"lc_{n}")], result_type=i32)
            )],
        ))
    rc_body_ops.append(_add_to_num_consts(
        arith.ConstantOp(IntegerAttr.from_int_and_width(n_fixed, 32))
    ))
    rc_body_ops.append(DdtMethodCallOp(
        obj_expr_op=_ref_expr(const_obj), method="initialize_table",
        arg_ops=[VarRefExprOp("lc_num_consts")],
    ))

    def _new_field_from(const_prop_op) -> list:
        """The recurring 'allocate const_prop, copy in, register, nullify'
        idiom -- identical across host constituents, each dynamic array,
        and each fixed-advected constituent below. const_prop_op is the
        expression for the properties copied in."""
        return [
            AllocateOp("const_prop", stat_var="errcode"),
            *_scf_if(_int_var_cmp_zero("errcode", "ne"), [
                ErrorExitOp("ERROR allocating const_prop"),
            ]),
            AssignOp(lhs_op=VarRefExprOp("const_prop"), rhs_op=const_prop_op),
            DdtMethodCallOp(
                obj_expr_op=_ref_expr(const_obj), method="new_field",
                arg_ops=[VarRefExprOp("const_prop")], kwarg_ops=_errcode_errmsg_kwargs(),
            ),
            NullifyPointerOp("const_prop"),
            ErrorPropagateOp("errcode"),
        ]

    # Host constituents
    rc_body_ops.append(DoLoopOp(
        "lc_i",
        CallExprOp("size", [VarRefExprOp("host_constituents")], result_type=i32),
        _new_field_from(
            IndexExprOp(VarRefExprOp("host_constituents"), [VarRefExprOp("lc_i")])
        ),
    ))
    # Dynamic scheme arrays
    for n in dynamic_array_names:
        rc_body_ops.extend(_scf_if(
            _allocated(f"lc_{n}"),
            [DoLoopOp(
                "lc_i", _size_of(f"lc_{n}"), _new_field_from(
                    IndexExprOp(_ref_expr(f"lc_{n}"), [VarRefExprOp("lc_i")])
                ),
            )],
        ))
    # Fixed advected constituents
    for std_name_f, units_f, default_val_f, local_name_f in fixed_advected:
        long_name_f = std_name_f.replace('_', ' ').capitalize()
        instantiate_kwargs = [
            KeywordArgExprOp("std_name", StringLiteralExprOp(std_name_f)),
            KeywordArgExprOp("long_name", StringLiteralExprOp(long_name_f)),
            KeywordArgExprOp("diag_name", StringLiteralExprOp(local_name_f)),
            KeywordArgExprOp("units", StringLiteralExprOp(units_f)),
            KeywordArgExprOp("vertical_dim", StringLiteralExprOp("vertical_layer_dimension")),
            KeywordArgExprOp("advected", arith.ConstantOp(IntegerAttr.from_int_and_width(1, 1))),
        ]
        if default_val_f is not None:
            instantiate_kwargs.append(
                KeywordArgExprOp("default_value", MetadataLiteralExprOp(default_val_f))
            )
        instantiate_kwargs += _errcode_errmsg_kwargs()
        rc_body_ops += [
            AllocateOp("const_prop", stat_var="errcode"),
            *_scf_if(_int_var_cmp_zero("errcode", "ne"), [
                ErrorExitOp("ERROR allocating const_prop"),
            ]),
            DdtMethodCallOp(
                obj_expr_op=VarRefExprOp("const_prop"), method="instantiate",
                kwarg_ops=instantiate_kwargs,
            ),
            ErrorPropagateOp("errcode"),
            DdtMethodCallOp(
                obj_expr_op=_ref_expr(const_obj), method="new_field",
                arg_ops=[VarRefExprOp("const_prop")], kwarg_ops=_errcode_errmsg_kwargs(),
            ),
            NullifyPointerOp("const_prop"),
            ErrorPropagateOp("errcode"),
        ]
    rc_body_ops += [
        DdtMethodCallOp(
            obj_expr_op=_ref_expr(const_obj), method="lock_table",
            kwarg_ops=_errcode_errmsg_kwargs(),
        ),
        ErrorPropagateOp("errcode"),
        PointerAssignOp(
            "lc_props_ptr",
            rhs_expr_op=MethodCallExprOp(
                _ref_expr(const_obj), "constituent_props_ptr"
            ),
        ),
        SafeDeallocOp(target_op=_ref_expr("lc_const_props")),
        AllocateOp(target_op=_ref_expr("lc_const_props"),
                   dim_ops=[CallExprOp("size", [VarRefExprOp("lc_props_ptr")])]),
        AssignOp(lhs_op=_ref_expr("lc_const_props"), rhs_op=VarRefExprOp("lc_props_ptr")),
        NullifyPointerOp("lc_props_ptr"),
    ]
    # Hand the constituents to the schemes' ccpp_scheme_utils: original
    # capgen's (CAM-SIMA's framework) takes the constituents object, the
    # bundled framework the property array.
    if capgen_api:
        set_constituents, set_constituents_arg = "ccpp_initialize_constituent_ptr", const_obj
    else:
        set_constituents, set_constituents_arg = "ccpp_scheme_utils_set_constituents", "lc_const_props"
    rc_body_ops.append(CallStatementOp(
        set_constituents, arg_ops=[_ref_expr(set_constituents_arg)],
    ))
    rc_body_ops += [
        DdtMethodCallOp(
            obj_expr_op=_ref_expr(const_obj), method="num_constituents",
            arg_ops=[VarRefExprOp("lc_num_consts")], kwarg_ops=_errcode_errmsg_kwargs(),
        ),
        ErrorPropagateOp("errcode"),
        SafeDeallocOp(target_op=_ref_expr("lc_all_constituents")),
        AllocateOp(target_op=_ref_expr("lc_all_constituents"),
                   dim_ops=[VarRefExprOp("lc_num_consts")]),
    ]
    if n_fixed > 0:
        rc_body_ops.append(DoLoopOp(
            "lc_i", _size_of(const_indices),
            [
                DdtMethodCallOp(
                    obj_expr_op=_ref_expr(const_obj), method="const_index",
                    arg_ops=[
                        VarRefExprOp("field_ind"),
                        IndexExprOp(_ref_expr(const_stdnames), [VarRefExprOp("lc_i")]),
                    ],
                    kwarg_ops=_errcode_errmsg_kwargs(),
                ),
                ErrorPropagateOp("errcode"),
                ActiveCheckOp(
                    condition_op=_int_var_cmp_zero("field_ind", "sgt"),
                    with_body_ops=[AssignOp(
                        lhs_op=IndexExprOp(_ref_expr(const_indices),
                                           [VarRefExprOp("lc_i")]),
                        rhs_op=VarRefExprOp("field_ind"),
                    )],
                    without_body_ops=[ErrorExitOp(
                        message_op=StringConcatExprOp([
                            StringLiteralExprOp("No field index for "),
                            CallExprOp("trim", [IndexExprOp(
                                _ref_expr(const_stdnames),
                                [VarRefExprOp("lc_i")],
                            )]),
                        ]),
                        errflg_var="errcode",
                    )],
                ),
            ],
        ))
    rc_op = fixed_interface_fn(
        f"{h}_ccpp_register_constituents",
        rc_args,
        rc_body_ops,
        locals_=[
            _local("lc_i", i32),
            _local("lc_num_consts", i32),
            *([_local("field_ind", i32)] if n_fixed > 0 else []),
            _local("const_prop", _props, pointer=True),
            _local("lc_props_ptr", _prop_ptr, [0], pointer=True),
        ],
        uses={
            _CCPP_CONSTITUENT_MOD: ["ccpp_constituent_properties_t",
                                    "ccpp_constituent_prop_ptr_t"],
            "ccpp_scheme_utils": [set_constituents],
        },
    )

    # ── 4. number_constituents ───────────────────────────────────────────
    # Mirrors capgen-v1's own num_const_funcname body exactly
    # (ccpp_framework/scripts/constituents.py: "call {const_obj_name}%
    # num_constituents(num_flds, advected=advected, ...)") -- delegate the
    # `advected` filter to ccpp_model_constituents_t%num_constituents
    # (ccp_model_const_num_match in ccpp_constituent_prop_mod.F90), which
    # already filters correctly on each constituent's real is_advected()
    # property. A prior version of this function instead assumed every
    # registered constituent is advected and returned size(lc_all_constituents)
    # unconditionally -- false whenever a scheme registers non-advected
    # constituents through the dynamic-array path (e.g. RRTMGP's
    # rrtmgp_constituents.F90 registers 'N'/'Z' rad_climate gases with
    # advected=.false.). That mismatch produced a too-large num_advected,
    # which downstream (MPAS's dyn_comp_impl.F90::dyn_inquire_advected_
    # constituent_index) over-allocated advected_constituent_index(:) and
    # left its tail uninitialized, crashing with a garbage out-of-bounds
    # index -- confirmed on a real QPC4 (RRTMGP + non-advected rad_climate
    # gases) MPAS case.
    _nc_call = DdtMethodCallOp(
        obj_expr_op=_ref_expr(const_obj), method="num_constituents",
        arg_ops=[VarRefExprOp("num_advected")],
        kwarg_ops=[KeywordArgExprOp("advected", VarRefExprOp("advected"))]
        + _errcode_errmsg_kwargs(),
    )
    nc_body_ops: list = [ClearErrStateOp("errcode", "errmsg")]
    if multi_instance:
        nc_body_ops.append(ActiveCheckOp(
            condition_op=_allocated_cond("lc_instances"),
            with_body_ops=[_nc_call],
            without_body_ops=[_assign_const("num_advected", 0)],
        ))
    else:
        nc_body_ops.append(_nc_call)
    nc_op = fixed_interface_fn(
        f"{h}_ccpp_number_constituents",
        [("num_advected", _int, "out", ()),
         ("errmsg", _errmsg, "out", ()),
         ("errcode", _int, "out", ()),
         ("advected", _logical, "in", ("optional",)),
         *_instance_args],
        nc_body_ops,
    )

    # ── 5. initialize_constituents ───────────────────────────────────────
    ic_body_ops: list = [ClearErrStateOp("errflg", "errmsg")]
    if multi_instance:
        ic_body_ops.append(ErrorGuardOp(
            condition_op=_allocated_cond("lc_instances"),
            errmsg_text="ccpp_initialize_constituents: register_constituents not called",
        ))
    ic_body_ops.append(ErrorGuardOp(
        condition_op=_allocated("lc_all_constituents"),
        errmsg_text="ccpp_initialize_constituents: register_constituents not called",
    ))
    # lock_data allocates the internal data array and applies defaults.
    ic_body_ops += [
        DdtMethodCallOp(
            obj_expr_op=_ref_expr(const_obj), method="lock_data",
            arg_ops=[VarRefExprOp("ncols"), VarRefExprOp("pver")],
            kwarg_ops=_errcode_errmsg_kwargs("errflg", "errmsg"),
        ),
        ErrorPropagateOp("errflg"),
        PointerAssignOp(
            target_op=_ref_expr("lc_constituent_array"),
            rhs_expr_op=MethodCallExprOp(
                _ref_expr(const_obj), "field_data_ptr"
            ),
        ),
    ]
    if framework_var_residency.get("lc_constituent_array"):
        ic_body_ops += _enter_data_copyin("lc_constituent_array", 3)
    if needs_const_tend:
        ic_body_ops += [
            SafeDeallocOp(target_op=_ref_expr("lc_const_tend")),
            AllocateOp(target_op=_ref_expr("lc_const_tend"), dim_ops=[
                VarRefExprOp("ncols"), VarRefExprOp("pver"),
                CallExprOp("size", [_ref_expr("lc_all_constituents")]),
            ]),
            ZeroFillOp(target_op=_ref_expr("lc_const_tend")),
        ]
        if framework_var_residency.get("lc_const_tend"):
            ic_body_ops += _enter_data_copyin("lc_const_tend", 3)
    for lc_name, rank, alloc_dims, _cst_std, needs_gpu, base in scratch_vars:
        if _cst_std:
            # A constituent view: a pointer slice of its base array
            # (lc_constituent_array for an advected arg, lc_const_tend for a
            # tendency), found with <host>_constituents_obj%const_index; the
            # block construct avoids polluting the outer scope. A missing
            # constituent is an error: otherwise the view stays null and a
            # scheme writing through it fails later, far from the cause.
            what = "constituent" if base == "lc_constituent_array" else "constituent for tendency"
            not_found_ops = [ErrorExitOp(
                f"ccpp_initialize_constituents: no {what} {_cst_std}",
                errflg_var="errflg",
            )]
            ic_body_ops.append(ScopedBlockOp(
                [_local("lc_tend_idx", i32), _local("lc_tend_errmsg", i8, [CCPP_ERRMSG_LEN])],
                [
                    NullifyPointerOp(target_op=_ref_expr(lc_name)),
                    DdtMethodCallOp(
                        obj_expr_op=_ref_expr(const_obj), method="const_index",
                        arg_ops=[VarRefExprOp("lc_tend_idx"), StringLiteralExprOp(_cst_std)],
                        kwarg_ops=_errcode_errmsg_kwargs("errflg", "lc_tend_errmsg"),
                    ),
                    ActiveCheckOp(
                        condition_op=arith.AndIOp(
                            _int_var_cmp_zero("errflg", "eq"),
                            _int_var_cmp_zero("lc_tend_idx", "sgt"),
                        ),
                        with_body_ops=[PointerAssignOp(
                            target_op=_ref_expr(lc_name),
                            rhs_expr_op=IndexExprOp(_ref_expr(base), [
                                SliceExprOp(), SliceExprOp(), VarRefExprOp("lc_tend_idx"),
                            ]),
                        )],
                        without_body_ops=not_found_ops,
                    ),
                ],
            ))
            # No separate enter-data here: lc_name is a pointer slice into
            # its base array, already made resident above -- OpenACC tracks
            # residency by the underlying array's actual memory, not the
            # pointer name used to reference a slice of it.
        else:
            ic_body_ops += [
                SafeDeallocOp(target_op=_ref_expr(lc_name)),
                AllocateOp(target_op=_ref_expr(lc_name),
                           dim_ops=[_alloc_extent(d) for d in alloc_dims]),
                ZeroFillOp(target_op=_ref_expr(lc_name)),
            ]
            if needs_gpu:
                ic_body_ops += _enter_data_copyin(lc_name, rank)
    ic_op = fixed_interface_fn(
        f"{h}_ccpp_initialize_constituents",
        [("ncols", _int, "in", ()),
         ("pver", _int, "in", ()),
         ("errflg", _int, "out", ()),
         ("errmsg", _errmsg, "out", ()),
         *_instance_args],
        ic_body_ops,
    )

    # ── 6. constituents_array ────────────────────────────────────────────
    ca_op = fixed_interface_fn(
        f"{h}_constituents_array", _instance_args,
        [PointerAssignOp("ptr", rhs_expr_op=_ref_expr("lc_constituent_array"))],
        result=_local("ptr", _real3.element_type, [0, 0, 0], pointer=True),
    )

    # ── 6b. advected_constituents_array ──────────────────────────────────
    # Mirrors capgen-v1's own constituent_model_advected_consts accessor
    # (ccpp_framework/scripts/constituents.py: "function {advect_array_func}()
    # result(const_ptr) ... const_ptr => {const_obj_name}%advected_constituents_ptr()").
    # Needed by MPAS's dyn_coupling_impl.F90 ("use cam_ccpp_cap, only:
    # cam_advected_constituents_array"), which xdsl_ccpp never generated --
    # confirmed missing by a MODEL_BUILD failure on real MPAS aux_sima cases
    # (SHAREDLIB_BUILD/cap generation itself already passes). The underlying
    # capability already exists (ccpp_constituent_prop_mod.F90's
    # ccpp_model_constituents_t already has advected_constituents_ptr, bound
    # as ccp_advected_data_ptr) -- only this thin public wrapper was absent.
    #
    # Deliberately a direct call in the function body (no pre-cached
    # module-level pointer, unlike ca_op/lc_constituent_array) -- matches
    # capgen-v1's own simpler direct-call shape, and nothing else in this
    # generator currently needs an advected-only view cached anywhere else.
    aca_op = fixed_interface_fn(
        f"{h}_advected_constituents_array", _instance_args,
        [PointerAssignOp(
            "ptr",
            rhs_expr_op=MethodCallExprOp(
                _ref_expr(const_obj), "advected_constituents_ptr"
            ),
        )],
        result=_local("ptr", _real3.element_type, [0, 0, 0], pointer=True),
    )

    # ── 7. const_get_index ───────────────────────────────────────────────
    # Delegate to <host>_constituents_obj%const_index (hash lookup) instead of
    # linear scan.  Hash keys are stored lowercase, so pass to_lower(std_name).
    ci_body_ops: list = [ClearErrStateOp("errflg", "errmsg"), _assign_const("index", -1)]
    if multi_instance:
        ci_body_ops.append(ErrorGuardOp(
            condition_op=_allocated_cond("lc_instances"),
            errmsg_text="const_get_index: constituents not registered",
        ))
    ci_body_ops.append(ErrorGuardOp(
        condition_op=_allocated("lc_all_constituents"),
        errmsg_text="const_get_index: constituents not registered",
    ))
    ci_body_ops += [
        DdtMethodCallOp(
            obj_expr_op=_ref_expr(const_obj), method="const_index",
            arg_ops=[
                VarRefExprOp("index"),
                CallExprOp("to_lower", [VarRefExprOp("std_name")]),
            ],
            kwarg_ops=_errcode_errmsg_kwargs("errflg", "errmsg"),
        ),
        *_scf_if(
            arith.OrIOp(
                _int_var_cmp_zero("errflg", "ne"),
                _int_var_cmp_zero("index", "sle"),
            ),
            [
                _assign_const("errflg", 1),
                WriteStmtOp(VarRefExprOp("errmsg"), [
                    StringLiteralExprOp("const_get_index: constituent "),
                    CallExprOp("trim", [VarRefExprOp("std_name")]),
                    StringLiteralExprOp(" not found"),
                ]),
            ],
        ),
    ]
    ci_op = fixed_interface_fn(
        f"{h}_const_get_index",
        [("std_name", _string, "in", ()),
         ("index", _int, "out", ()),
         ("errflg", _int, "out", ()),
         ("errmsg", _errmsg, "out", ()),
         *_instance_args],
        ci_body_ops,
        uses={_CCPP_CONSTITUENT_MOD: ["to_lower"]},
    )

    # ── 8. model_const_properties ────────────────────────────────────────
    mp_op = fixed_interface_fn(
        f"{h}_model_const_properties", _instance_args,
        [PointerAssignOp("ptr", rhs_expr_op=_ref_expr("lc_const_props"))],
        result=_local("ptr", _prop_ptr, [0], pointer=True),
    )

    public_names_list = [
        f"{h}_ccpp_is_scheme_constituent",
        f"{h}_ccpp_deallocate_dynamic_constituents",
        f"{h}_ccpp_register_constituents",
        f"{h}_ccpp_number_constituents",
        f"{h}_ccpp_initialize_constituents",
        f"{h}_constituents_array",
        f"{h}_advected_constituents_array",
        f"{h}_const_get_index",
        f"{h}_model_const_properties",
    ]
    api_fn_ops = [isc_op, da_op, rc_op, nc_op, ic_op, ca_op, aca_op, ci_op, mp_op]
    if capgen_api:
        capgen_names, capgen_fns = capgen_constituent_routines(h, const_obj)
        public_names_list += capgen_names
        api_fn_ops += capgen_fns
    if multi_instance:
        api_fn_ops = [DerivedTypeDefOp(instance_type_name, component_ops)] + api_fn_ops
    api_op = ConstituentApiOp(public_names_list, api_fn_ops)

    # ── USE stubs for ccpp_constituent_prop_mod ──────────────────────────
    # Module name resolved via the generic ddt_source_module mechanism
    # (the real .meta's module_name, if the host overrides it) when
    # available, falling back to the historical constant otherwise --
    # these 3 types can't be *discovered* by the generic per-arg-type scan
    # (ccpp_model_constituents_t in particular is never a parsed argument
    # type anywhere, only a cap-internal module variable's type), so the
    # fixed list stays, but the module name it resolves to no longer
    # silently diverges from reality if the backing .meta is ever renamed.
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
        _mod = (
            ddt_source_module.get(type_name, _CCPP_CONSTITUENT_MOD)
            if ddt_source_module else _CCPP_CONSTITUENT_MOD
        )
        _g.attributes["module"] = StringAttr(_mod)
        global_stubs.append(_g)

    return module_var_ops, api_op, global_stubs
