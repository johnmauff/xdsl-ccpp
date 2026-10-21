"""`active` conditions on scheme arguments."""

from __future__ import annotations

import re

from xdsl.dialects import llvm
from xdsl.dialects.builtin import (
    StringAttr,
    i8,
)

from xdsl_ccpp.transforms.util.cap_shared import (
    _build_ddt_resolution_maps,
    _resolve_ddt_access_path,
    classify_host_table_vars,
)
from xdsl_ccpp.util.ccpp_conventions import (
    CCPP_SCALAR_INDEX_DIMS,
    is_dispatch_scalar_std_name,
)


def _active_expr_var_indexes(meta_data) -> dict:
    """Return use_associated_index for resolving 'active = <expr>' property
    text: standard_name.lower() -> (local_name, table_name, ftn_type).

    Covers MODULE-type vars and 'state'-classified HOST-type vars (both
    resolved via a USE stub). 'dispatch_scalar' HOST vars (loop bounds,
    error handling) have no backing module and are excluded;
    _resolve_active_condition raises if one is referenced.
    """
    from xdsl_ccpp.transforms.util.ccpp_descriptors import CCPPType

    host_classification = classify_host_table_vars(meta_data)
    use_associated_index: dict = {}
    for tbl_name, props in meta_data.items():
        tbl_type = props.getAttr("type")
        if tbl_type not in (CCPPType.MODULE, CCPPType.HOST):
            continue
        if tbl_name not in props.arg_tables:
            continue
        for var in props.getArgTable(tbl_name).getFunctionArguments():
            if not var.hasAttr("standard_name"):
                continue
            std_name = var.getAttr("standard_name").lower()
            if tbl_type == CCPPType.MODULE or host_classification.get(std_name) == "state":
                use_associated_index[std_name] = (var.name, tbl_name, var.getAttr("type"))
    return use_associated_index


# Identifier-like tokens in an 'active = <expr>' expression; see
# _resolve_active_condition.
_ACTIVE_EXPR_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _active_expr_ddt_member_indexes(meta_data) -> dict:
    """Return standard_name.lower() -> (member_local_name, ddt_type_name)
    for every member of every DDT-type table.

    Lets an 'active = <expr>' token reference a DDT member (e.g.
    examples/instances' flag_for_opt_array in instance_type).
    """
    from xdsl_ccpp.transforms.util.ccpp_descriptors import CCPPType

    ddt_member_index: dict = {}
    for tbl_name, props in meta_data.items():
        if props.getAttr("type") != CCPPType.DDT:
            continue
        if tbl_name not in props.arg_tables:
            continue
        for var in props.getArgTable(tbl_name).getFunctionArguments():
            if not var.hasAttr("standard_name"):
                continue
            ddt_member_index[var.getAttr("standard_name").lower()] = (var.name, tbl_name)
    return ddt_member_index


def _resolve_active_condition(
    meta_data, raw_expr: str, suite_use_stubs: list, arg_table=None,
) -> str:
    """Resolve a host/module var's 'active = <expr>' property text into a
    valid Fortran expression at the suite-cap call site, emitting any USE
    stubs needed.

    The raw text is in standard-name space (like default_value/dimension
    expressions), so each token must be mapped to its local name:
    - MODULE or 'state' HOST var: local name plus a USE stub.
    - 'dispatch_scalar' HOST var: raises (see _active_expr_var_indexes).
    - DDT member: resolved via _resolve_ddt_access_path, as in
      run_dispatch.py. If the DDT instance is a HOST-owned array of model
      instances (capgen-v1's multi-instance model), <arg_table> (the
      scheme's _run table) must have a sibling instance_number arg to index
      by; raises otherwise.
    - Unknown tokens are left as-is (Fortran keywords/operators).
    """
    use_associated_index = _active_expr_var_indexes(meta_data)
    ddt_member_index = _active_expr_ddt_member_indexes(meta_data)

    def _resolve_ddt_member(std_name: str, member_local_name: str, ddt_type_name: str) -> str:
        ddt_instance_map, ddt_parent_map = _build_ddt_resolution_maps(meta_data)
        result = _resolve_ddt_access_path(ddt_type_name, ddt_instance_map, ddt_parent_map)
        if result is None:
            raise ValueError(
                f"'active = {raw_expr}' references {std_name!r}, a member "
                f"of DDT type {ddt_type_name!r} with no reachable "
                f"module-level instance -- cannot resolve to a real "
                f"Fortran reference."
            )
        instance_var, instance_module, path_prefix, instance_array_dim = result
        member_ref = path_prefix + member_local_name
        if instance_array_dim is not None:
            expected_index_std_name = CCPP_SCALAR_INDEX_DIMS.get(instance_array_dim)
            index_local_name = None
            if expected_index_std_name is not None and arg_table is not None:
                for arg in arg_table.getFunctionArguments():
                    if (
                        arg.hasAttr("standard_name")
                        and arg.getAttr("standard_name").lower()
                            == expected_index_std_name
                    ):
                        index_local_name = arg.name
                        break
            if index_local_name is None:
                raise ValueError(
                    f"'active = {raw_expr}' references {std_name!r}, a "
                    f"member of {instance_var!r}, a HOST-owned array of "
                    f"model instances -- but this scheme's own call has "
                    f"no sibling {expected_index_std_name!r} arg to "
                    f"index it by, so there is no way to know which "
                    f"instance's value to test."
                )
            base_name = f"{instance_var}({index_local_name})"
        else:
            base_name = instance_var
        if not any(
            isinstance(existing, llvm.GlobalOp)
            and existing.sym_name.data == instance_var
            and existing.attributes.get("module") == StringAttr(instance_module)
            for existing in suite_use_stubs
        ):
            stub = llvm.GlobalOp(
                llvm.LLVMArrayType.from_size_and_type(1, i8),
                instance_var, "external",
            )
            stub.attributes["module"] = StringAttr(instance_module)
            suite_use_stubs.append(stub)
        return f"{base_name}%{member_ref}"

    def _substitute(match: "re.Match") -> str:
        token = match.group(0)
        std_name = token.lower()
        entry = use_associated_index.get(std_name)
        if entry is not None:
            local_name, module_name, _ftn_type = entry
            already_stubbed = any(
                isinstance(existing, llvm.GlobalOp)
                and existing.sym_name.data == local_name
                and existing.attributes.get("module") == StringAttr(module_name)
                for existing in suite_use_stubs
            )
            if not already_stubbed:
                stub = llvm.GlobalOp(
                    llvm.LLVMArrayType.from_size_and_type(1, i8),
                    local_name, "external",
                )
                stub.attributes["module"] = StringAttr(module_name)
                suite_use_stubs.append(stub)
            return local_name
        ddt_entry = ddt_member_index.get(std_name)
        if ddt_entry is not None:
            member_local_name, ddt_type_name = ddt_entry
            return _resolve_ddt_member(std_name, member_local_name, ddt_type_name)
        if is_dispatch_scalar_std_name(std_name):
            raise ValueError(
                f"'active = {raw_expr}' references {std_name!r}, a CCPP "
                f"dispatch-scalar standard name (loop bounds/error "
                f"handling) with no backing Fortran module to "
                f"use-associate from. Gating an optional arg's presence "
                f"on one isn't supported -- no example does this, and it "
                f"has no clear Fortran realization. Give the host a real "
                f"state variable to gate on instead."
            )
        return token

    return _ACTIVE_EXPR_TOKEN_RE.sub(_substitute, raw_expr)
