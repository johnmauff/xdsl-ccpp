"""Original capgen's host API, generated with --capgen-api (formerly
--cam-host).

xdsl-ccpp's own host cap API is capgen-v1's (ccpp_register/ccpp_init/
ccpp_final, ccpp_physics_*), which the examples call. CAM-SIMA calls
original capgen's API instead: <host>_ccpp_physics_<stage>, which reads
errmsg/errcode and the column bounds from the host's module variables, and
the <host>_ccpp_gather/update_constituents routines. This module builds
that layer on top of the capgen-v1 dispatchers.
"""

from __future__ import annotations

from xdsl.dialects import builtin, func, llvm, memref
from xdsl.dialects.builtin import DYNAMIC_INDEX, StringAttr
from xdsl.ir import Block, Region

from xdsl_ccpp.dialects.ccpp_utils import (
    CamDirectCallOp,
    CamQminPostambleOp,
    CamQminPreambleOp,
    CamSuiteDispatchOp,
    ClearErrStateOp,
    DdtMethodCallOp,
    ErrorPropagateOp,
    KeywordArgExprOp,
    VarRefExprOp,
)
from xdsl_ccpp.transforms.util.cap_shared import (
    FRAMEWORK_STD_NAME_TO_CAP_VAR,
    fixed_interface_fn,
    framework_cap_var_ref,
)
from xdsl_ccpp.transforms.util.typing import TypeConversions
from xdsl_ccpp.util.ccpp_conventions import (
    CCPP_ERRMSG_LEN,
    CCPP_ERROR_CODE,
    CCPP_ERROR_MESSAGE,
    SUITE_ARG_NAME,
    arg_attr_values,
)


def capgen_constituent_routines(h: str, const_obj: str) -> tuple:
    """(public names, FuncOps) of original capgen's constituent routines
    that capgen-v1's API lacks: <h>_ccpp_gather_constituents and
    <h>_ccpp_update_constituents, copying a host array into or out of the
    constituents object *const_obj*. Never multi-instance (refused for
    --capgen-api), so *const_obj* is a plain module variable."""
    char = TypeConversions.getBaseType("character")
    errmsg = memref.MemRefType(char, [CCPP_ERRMSG_LEN])
    errcode = memref.MemRefType(TypeConversions.getBaseType("integer"), [])
    real3 = TypeConversions.convert("real", "kind_phys", 3)

    def routine(name, intent, method):
        return fixed_interface_fn(
            name,
            [("const_array", real3, intent, ()),
             ("errcode", errcode, "out", ()),
             ("errmsg", errmsg, "out", ())],
            [DdtMethodCallOp(
                obj_expr_op=VarRefExprOp(const_obj), method=method,
                arg_ops=[VarRefExprOp("const_array")],
                kwarg_ops=[KeywordArgExprOp("errcode", VarRefExprOp("errcode")),
                           KeywordArgExprOp("errmsg", VarRefExprOp("errmsg"))],
            )],
        )

    names = [f"{h}_ccpp_gather_constituents", f"{h}_ccpp_update_constituents"]
    return names, [routine(names[0], "out", "copy_in"), routine(names[1], "in", "copy_out")]


def generate_capgen_api_wrappers(
    host, suite_descriptions, public_fns, meta_data, lifecycle_fns=None, host_var_map_lc=None,
):
    """Generate original capgen's <host>_ccpp_physics_* lifecycle wrapper
    FuncOps (--capgen-api), named after the host as capgen names them.

    CAM-SIMA's phys_comp.F90 calls these with a simplified signature -- just suite_name
    (and suite_part for _run) -- reading errmsg/errcode from the host's
    module variables (CAM-SIMA: physics_types) rather than receiving them
    as dummy arguments.

    Returns (wrappers, globals) where:
      wrappers: list[func.FuncOp]  -- 6 public wrapper subroutines
      globals:  list[llvm.GlobalOp] -- USE-association stubs for module scope

    Arg resolution is metadata-driven: lifecycle_fns carries the
    canonical_arg_name to standard_name mapping from _generate_run_fn.
    Each dispatcher block arg is looked up in _CAM_STD_EXPRS to obtain the
    reference passed in CamDirectCallOp / CamSuiteDispatchOp args.
    """
    char_base = TypeConversions.getBaseType("character")
    suite_name_type  = memref.MemRefType(char_base, [DYNAMIC_INDEX])

    # Cap-local framework variables: standard_name -> (reference, None,
    # qmin_needed); reference is an identifier or a CapVarRef. Every other
    # argument (the loop bounds, errmsg/errcode, ...) is a host variable,
    # looked up in the host's MODULE-type metadata (host_var_map_lc) and
    # use-associated from its module, as original capgen does.
    _CAM_STD_EXPRS = {
        "ccpp_constituent_properties":     ("lc_const_props", None, False),
        "ccpp_constituent_minimum_values": ("lc_qmin",        None, True),
    }
    for _std in FRAMEWORK_STD_NAME_TO_CAP_VAR:
        assert _std not in _CAM_STD_EXPRS, f"_CAM_STD_EXPRS collision for '{_std}'"
        _CAM_STD_EXPRS[_std] = (framework_cap_var_ref(_std), None, False)

    def _make_use_global(var_name, module_name):
        g = llvm.GlobalOp(
            llvm.LLVMArrayType.from_size_and_type(1, char_base),
            var_name,
            "external",
        )
        g.attributes["module"] = StringAttr(module_name)
        return g

    # Accumulated USE-stub globals, deduped by (var_name, module_name).
    _seen_globals: dict[tuple, llvm.GlobalOp] = {}

    def _add_globals(global_specs):
        for var_name, mod_name in global_specs:
            key = (var_name, mod_name)
            if key not in _seen_globals:
                _seen_globals[key] = _make_use_global(var_name, mod_name)

    def _build_dispatcher_call(fn_suffix):
        """Return (call_args, global_specs, qmin_needed) for one dispatcher.

        call_args:    list -- an expression op for each positional arg, and
                      None for the suite part (the caller supplies it).
        global_specs: list[(var_name, module_name)] -- vars needing USE stubs.
        qmin_needed:  bool -- True when ccpp_constituent_minimum_values is used.

        Returns (None, [], False) when the dispatcher is absent from lifecycle_fns.

        arg_to_std is keyed by the dispatcher's dummy-argument names,
        which _build_run_block_signature records in its arg_attrs
        (SUITE_ARG_NAME).
        """
        if lifecycle_fns is None:
            return None, [], False
        entry = lifecycle_fns.get(fn_suffix)
        if entry is None:
            return None, [], False

        fn, arg_to_std = entry
        call_args  = []
        gspecs     = []
        qmin_needed = False

        for a, attrs in zip(fn.args, arg_attr_values(fn)):
            arg_name = attrs.get(SUITE_ARG_NAME, a.name_hint or "")
            if arg_name == "suite_name":
                call_args.append(VarRefExprOp("suite_name"))
                continue
            if arg_name == "suite_part":
                call_args.append(None)
                continue

            std_name = arg_to_std.get(arg_name)
            if std_name is None:
                raise ValueError(
                    f"generate_capgen_api_wrappers: no standard_name for "
                    f"dispatcher '{fn_suffix}' block arg '{arg_name}'. "
                    f"Ensure _generate_run_fn returns non_host_std_to_canonical "
                    f"and ccpp_cap.py stores it in lifecycle_fns."
                )
            cam_entry = _CAM_STD_EXPRS.get(std_name)
            if cam_entry is None and host_var_map_lc is not None:
                hv = host_var_map_lc.get(std_name.lower())
                if hv is not None:
                    var_name, module_name = hv
                    cam_entry = (var_name, module_name, False)
            if cam_entry is None:
                raise ValueError(
                    f"generate_capgen_api_wrappers: no host variable for "
                    f"standard_name '{std_name}' (dispatcher '{fn_suffix}', "
                    f"arg '{arg_name}'): declare it in a MODULE-type host "
                    f"metadata table."
                )
            ref, mod, qmin = cam_entry
            call_args.append(VarRefExprOp(ref) if isinstance(ref, str) else ref.expr_op())
            if mod:
                gspecs.append((ref, mod))
            if qmin:
                qmin_needed = True

        return call_args, gspecs, qmin_needed

    def _build_suite_groups(infix):
        """Return list of (suite_name, group_names) for CamSuiteDispatchOp."""
        groups = []
        for sn, sd in suite_descriptions.items():
            gs = [
                grp.attributes["name"] for grp in sd
                if f"{sn}_{infix}_{grp.attributes['name']}" in public_fns
            ]
            if gs:
                groups.append((sn, gs))
        return groups

    def _names(*names):
        return [VarRefExprOp(n) for n in names]

    def _suite_dispatch(dispatcher, wrapper, infix, call_args):
        """The suite-group dispatch chain; call_args holds None where the
        group name goes."""
        part_at = call_args.index(None)
        return CamSuiteDispatchOp(
            dispatcher, wrapper, errcode, errmsg, _build_suite_groups(infix),
            [a for a in call_args if a is not None], part_at,
        )

    def _build_funcop(fn_name, arg_names, arg_types, body_ops):
        block = Block(arg_types=arg_types)
        for arg, name in zip(block.args, arg_names):
            arg.name_hint = name
        block.add_ops(body_ops)
        body = Region()
        body.add_block(block)
        fn_type = builtin.FunctionType.from_lists(arg_types, [])
        return func.FuncOp(fn_name, fn_type, body, visibility="public")

    _lf = lifecycle_fns or {}
    has_physics_init  = "ccpp_physics_init"           in _lf
    has_physics_final = "ccpp_physics_final"          in _lf
    has_tsinit        = "ccpp_physics_timestep_init"   in _lf
    has_tsfinal       = "ccpp_physics_timestep_final"  in _lf

    # The wrappers report errors through the host's own errmsg/errcode
    # module variables (CAM-SIMA: physics_types), as original capgen does.
    def _host_var(std_name):
        hv = (host_var_map_lc or {}).get(std_name.lower())
        if hv is None:
            raise ValueError(
                f"--capgen-api: the host must declare '{std_name}' in a "
                f"MODULE-type metadata table"
            )
        return hv
    errmsg, errmsg_module = _host_var(CCPP_ERROR_MESSAGE)
    errcode, errcode_module = _host_var(CCPP_ERROR_CODE)
    _add_globals([(errmsg, errmsg_module), (errcode, errcode_module)])

    wrappers = []

    # --- cam_ccpp_physics_register ---
    wrappers.append(_build_funcop(
        f"{host}_ccpp_physics_register",
        ["suite_name"],
        [suite_name_type],
        [
            CamDirectCallOp("ccpp_register", _names("suite_name", errmsg, errcode)),
            func.ReturnOp(),
        ],
    ))

    # --- cam_ccpp_physics_initialize ---
    _init_body = [
        CamDirectCallOp("ccpp_init", _names("suite_name", errmsg, errcode)),
        ErrorPropagateOp(errcode),
    ]
    if has_physics_init:
        _init_args, _init_gspecs, _ = _build_dispatcher_call("ccpp_physics_init")
        _add_globals(_init_gspecs)
        _init_body.append(_suite_dispatch(
            "ccpp_physics_init", f"{host}_ccpp_physics_initialize", "init", _init_args,
        ))
    _init_body.append(func.ReturnOp())
    wrappers.append(_build_funcop(
        f"{host}_ccpp_physics_initialize",
        ["suite_name"],
        [suite_name_type],
        _init_body,
    ))

    # --- cam_ccpp_physics_finalize ---
    _final_body = []
    if has_physics_final:
        _final_args, _final_gspecs, _ = _build_dispatcher_call("ccpp_physics_final")
        _add_globals(_final_gspecs)
        _final_body += [
            _suite_dispatch(
                "ccpp_physics_final", f"{host}_ccpp_physics_finalize", "final", _final_args,
            ),
            ErrorPropagateOp(errcode),
        ]
    _final_body += [
        CamDirectCallOp("ccpp_final", _names("suite_name", errmsg, errcode)),
        func.ReturnOp(),
    ]
    wrappers.append(_build_funcop(
        f"{host}_ccpp_physics_finalize",
        ["suite_name"],
        [suite_name_type],
        _final_body,
    ))

    # --- cam_ccpp_physics_timestep_initial ---
    if has_tsinit:
        _tsinit_args, _tsinit_gspecs, _ = _build_dispatcher_call("ccpp_physics_timestep_init")
        _add_globals(_tsinit_gspecs)
        _tsinit_body = [
            _suite_dispatch(
                "ccpp_physics_timestep_init", f"{host}_ccpp_physics_timestep_initial",
                "timestep_init", _tsinit_args,
            ),
        ]
    else:
        _tsinit_body = [ClearErrStateOp(errcode, errmsg)]
    _tsinit_body.append(func.ReturnOp())
    wrappers.append(_build_funcop(
        f"{host}_ccpp_physics_timestep_initial",
        ["suite_name"],
        [suite_name_type],
        _tsinit_body,
    ))

    # --- cam_ccpp_physics_run ---
    _run_call_args, _run_gspecs, _run_has_qmin = _build_dispatcher_call("ccpp_physics_run")
    if _run_call_args is None:
        _run_call_args = _names("suite_name", "suite_part", errmsg, errcode)
    else:
        _run_call_args = [VarRefExprOp("suite_part") if a is None else a
                          for a in _run_call_args]
    _add_globals(_run_gspecs)
    if _run_has_qmin:
        _add_globals([("kind_phys", "ccpp_kinds")])
    _run_body = []
    if _run_has_qmin:
        _run_body.append(CamQminPreambleOp(errcode, errmsg))
    _run_body.append(CamDirectCallOp("ccpp_physics_run", _run_call_args))
    if _run_has_qmin:
        _run_body.append(CamQminPostambleOp())
    _run_body.append(func.ReturnOp())
    wrappers.append(_build_funcop(
        f"{host}_ccpp_physics_run",
        ["suite_name", "suite_part"],
        [suite_name_type, suite_name_type],
        _run_body,
    ))

    # --- cam_ccpp_physics_timestep_final ---
    if has_tsfinal:
        _tsfinal_args, _tsfinal_gspecs, _ = _build_dispatcher_call(
            "ccpp_physics_timestep_final"
        )
        _add_globals(_tsfinal_gspecs)
        _tsfinal_body = [
            _suite_dispatch(
                "ccpp_physics_timestep_final", f"{host}_ccpp_physics_timestep_final",
                "timestep_final", _tsfinal_args,
            ),
        ]
    else:
        _tsfinal_body = [ClearErrStateOp(errcode, errmsg)]
    _tsfinal_body.append(func.ReturnOp())
    wrappers.append(_build_funcop(
        f"{host}_ccpp_physics_timestep_final",
        ["suite_name"],
        [suite_name_type],
        _tsfinal_body,
    ))

    return wrappers, list(_seen_globals.values())
