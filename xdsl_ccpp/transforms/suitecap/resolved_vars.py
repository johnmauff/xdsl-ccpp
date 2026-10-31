"""Resolved-variable records written to --emit-resolved-vars JSON."""

from __future__ import annotations



from xdsl_ccpp.frontend.meta_expr import parse_local_name, standard_names
from xdsl_ccpp.transforms.util.cap_shared import (
    _resolve_ddt_access_path,
    host_ref_key,
    resolve_member,
)
from xdsl_ccpp.util.ccpp_conventions import (
    CCPP_DEPRECATED_STD_NAMES,
)


# CCPP phase names (capgen-v1 CCPP_STATE_MACH naming), keyed by
# (tgt_subroutine_postfix, column_range); column_range=True is always "run".
_PHASE_NAMES: dict = {
    ("_register", False): "register",
    ("_init", False): "initialize",
    ("_finalize", False): "finalize",
    ("_timestep_initialize", False): "timestep_initial",
    ("_timestep_finalize", False): "timestep_final",
}


def _normalize_std_name(name: str) -> str:
    """Map a deprecated CCPP standard name to its modern replacement (e.g.
    horizontal_loop_extent -> horizontal_dimension), else return it
    unchanged. Matches capgen-v1's normalized output.
    """
    return CCPP_DEPRECATED_STD_NAMES.get(name.lower(), name)


def _resolved_var_record(arg) -> "dict | None":
    """Extract a JSON-safe resolved-variable record from a descriptor/IR arg.

    Returns None for args with no standard_name (e.g. synthetic
    col_start/col_end loop bounds), which have no CCPP metadata identity.
    """
    if not arg.hasAttr("standard_name"):
        return None
    dim_names = list(arg.getAttr("dim_names")) if arg.hasAttr("dim_names") else []
    return {
        "standard_name": _normalize_std_name(arg.getAttr("standard_name")),
        "intent": arg.getAttr("intent") if arg.hasAttr("intent") else None,
        "is_advected": arg.hasAttr("advected"),
        "is_constituent": arg.hasAttr("constituent"),
        # Scheme args carry protection via model_var_is_protected (set by
        # HostVariableMatchPass); 'protected' covers a host/module arg.
        "is_protected": arg.hasAttr("protected") or arg.hasAttr("model_var_is_protected"),
        "is_optional": arg.hasAttr("optional"),
        "is_host_table_var": arg.hasAttr("model_var_is_host_table"),
        # Scheme's own arg name: local_name fallback for args with no host
        # match (e.g. constituents), matching capgen-v1; see
        # resolved_var_xdsl_ccpp.py.
        "arg_name": arg.name,
        "model_var_name": arg.getAttr("model_var_name") if arg.hasAttr("model_var_name") else None,
        "model_module_name": arg.getAttr("model_module_name") if arg.hasAttr("model_module_name") else None,
        # Plain (non-DDT) defaults; _apply_ddt_chain overwrites import_name,
        # call_expr and model_module_name for a DDT member match.
        "import_name": arg.getAttr("model_var_name") if arg.hasAttr("model_var_name") else None,
        "call_expr": arg.getAttr("model_var_name") if arg.hasAttr("model_var_name") else None,
        "array_ref_dims": [],
        "dim_names": [_normalize_std_name(d) for d in dim_names],
        "ownership_kind": str(arg.getAttr("ownership_kind")) if arg.hasAttr("ownership_kind") else None,
    }


def _apply_ddt_chain(record: dict, arg, ddt_resolution_maps) -> None:
    """Patch <record> in place for a DDT member match, resolving the DDT
    type name left in model_module_name into the real Fortran chain, e.g.
    model_module_name="physics_state" becomes "physics_types_ddt",
    import_name="phys_state", call_expr="phys_state%theta".

    No-op if <arg> isn't a DDT member match, <ddt_resolution_maps> is None,
    or no module-level instance is reachable (soft-fail like
    run_dispatch.py). An instance in a HOST-type table also sets
    is_host_table_var, so consumers don't treat it as use-associable
    (mirrors run_dispatch.py's ArgSourceKind.Block branch).
    """
    if ddt_resolution_maps is None or not arg.hasAttr("model_var_is_ddt"):
        return
    ddt_instance_map, ddt_parent_map, ddt_host_var_map, host_table_names = ddt_resolution_maps
    ddt_type_name = record["model_module_name"]
    result = _resolve_ddt_access_path(ddt_type_name, ddt_instance_map, ddt_parent_map)
    if result is None:
        return
    instance_var, instance_module, ddt_path, _instance_array_dim = result
    member, _sub_vars = resolve_member(ddt_path, record["model_var_name"], ddt_host_var_map)
    record["model_module_name"] = instance_module
    record["import_name"] = instance_var
    # The JSON's Fortran reference (read by CAM's write_init_files).
    record["call_expr"] = host_ref_key(instance_var, member)
    # The subscripts' standard names, as the .meta file names them.
    record["array_ref_dims"] = standard_names(parse_local_name(record["model_var_name"]))
    if instance_module in host_table_names:
        record["is_host_table_var"] = True


def _write_resolved_vars(resolved_vars: dict, path: str, host_vars: dict = None) -> None:
    """Serialize per-phase resolved-variable records to JSON at *path*.

    Records are deduped by standard_name within each phase (first wins),
    matching capgen-v1's one combined call_list per phase.

    <host_vars>, if given, is cap_shared.py's _build_host_var_map result,
    written as a top-level "host_vars" key so consumers can resolve host
    variables that are never scheme args (e.g. DDT array_ref_dims indices).
    """
    import json

    deduped: dict = {}
    for phase_name, records in resolved_vars.items():
        seen: set = set()
        phase_list = []
        for record in records:
            sn = record["standard_name"]
            if sn in seen:
                continue
            seen.add(sn)
            phase_list.append(record)
        deduped[phase_name] = phase_list

    out = {"phases": deduped}
    if host_vars:
        out["host_vars"] = {
            std_name: list(entry) for std_name, entry in host_vars.items()
        }

    with open(path, "w") as f:
        json.dump(out, f, indent=2)
