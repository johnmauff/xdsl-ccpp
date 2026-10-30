"""`active` conditions on scheme arguments."""

from __future__ import annotations

from xdsl.dialects import arith, llvm
from xdsl.dialects.builtin import (
    FloatAttr,
    IntegerAttr,
    StringAttr,
    f64,
    i1,
    i8,
    i32,
)

from xdsl_ccpp.dialects.ccpp_utils import (
    IndexExprOp,
    MemberAccessExprOp,
    VarRefExprOp,
)
from xdsl_ccpp.frontend.meta_expr import (
    Binary,
    IntLiteral,
    LogicalLiteral,
    Name,
    Not,
    parse_active_expr,
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


def _active_expr_ddt_member_indexes(meta_data) -> dict:
    """Return standard_name.lower() -> (member_local_name, ddt_type_name,
    ftn_type) for every member of every DDT-type table.

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
            ddt_member_index[var.getAttr("standard_name").lower()] = (
                var.name, tbl_name, var.getAttr("type"),
            )
    return ddt_member_index


# Fortran type of a variable an 'active' expression references -> the
# MLIR type of its value in the condition.
_ACTIVE_VAR_TYPES = {"logical": i1, "integer": i32, "real": f64}

_INT_PREDICATES = {"eq": "eq", "ne": "ne", "lt": "slt", "le": "sle", "gt": "sgt", "ge": "sge"}
_FLOAT_PREDICATES = {"eq": "oeq", "ne": "une", "lt": "olt", "le": "ole", "gt": "ogt", "ge": "oge"}


def _true():
    return arith.ConstantOp(IntegerAttr.from_int_and_width(1, 1))


def _not(value_op):
    return arith.XOrIOp(value_op, _true())


def _resolve_active_condition(
    meta_data, raw_expr: str, suite_use_stubs: list, arg_table=None,
):
    """Build a host/module var's 'active = <expr>' property as an i1
    expression op at the suite-cap call site, emitting any USE stubs
    needed.

    The expression is in standard-name space (like default_value/dimension
    expressions); each name becomes a reference to its variable:
    - MODULE or 'state' HOST var: its local name, plus a USE stub.
    - 'dispatch_scalar' HOST var: raises (see _active_expr_var_indexes).
    - DDT member: resolved via _resolve_ddt_access_path, as in
      run_dispatch.py. If the DDT instance is a HOST-owned array of model
      instances (capgen-v1's multi-instance model), <arg_table> (the
      scheme's _run table) must have a sibling instance_number arg to index
      by; raises otherwise.
    Each reference is typed from its metadata (logical, integer or real),
    so comparisons and logical operators get operands of the right type.
    """
    use_associated_index = _active_expr_var_indexes(meta_data)
    ddt_member_index = _active_expr_ddt_member_indexes(meta_data)

    def _use_stub(local_name: str, module_name: str) -> None:
        if not any(
            isinstance(existing, llvm.GlobalOp)
            and existing.sym_name.data == local_name
            and existing.attributes.get("module") == StringAttr(module_name)
            for existing in suite_use_stubs
        ):
            stub = llvm.GlobalOp(
                llvm.LLVMArrayType.from_size_and_type(1, i8),
                local_name, "external",
            )
            stub.attributes["module"] = StringAttr(module_name)
            suite_use_stubs.append(stub)

    def _var_type(std_name: str, ftn_type: str):
        mlir_type = _ACTIVE_VAR_TYPES.get(str(ftn_type).lower())
        if mlir_type is None:
            raise ValueError(
                f"'active = {raw_expr}' references {std_name!r}, of type "
                f"{ftn_type!r}; only logical, integer and real variables "
                f"can appear in an active condition."
            )
        return mlir_type

    def _ddt_member_ref(std_name: str, member_local_name: str, ddt_type_name: str,
                        result_type):
        ddt_instance_map, ddt_parent_map = _build_ddt_resolution_maps(meta_data)
        result = _resolve_ddt_access_path(ddt_type_name, ddt_instance_map, ddt_parent_map)
        if result is None:
            raise ValueError(
                f"'active = {raw_expr}' references {std_name!r}, a member "
                f"of DDT type {ddt_type_name!r} with no reachable "
                f"module-level instance -- cannot resolve to a real "
                f"Fortran reference."
            )
        instance_var, instance_module, ddt_path, instance_array_dim = result
        ref = VarRefExprOp(instance_var)
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
            ref = IndexExprOp(ref, [VarRefExprOp(index_local_name)])
        _use_stub(instance_var, instance_module)
        for member in ddt_path:
            ref = MemberAccessExprOp(ref, member)
        return MemberAccessExprOp(ref, member_local_name, result_type=result_type)

    def _name(std_name: str):
        entry = use_associated_index.get(std_name)
        if entry is not None:
            local_name, module_name, ftn_type = entry
            _use_stub(local_name, module_name)
            return VarRefExprOp(local_name, result_type=_var_type(std_name, ftn_type))
        ddt_entry = ddt_member_index.get(std_name)
        if ddt_entry is not None:
            member_local_name, ddt_type_name, ftn_type = ddt_entry
            return _ddt_member_ref(
                std_name, member_local_name, ddt_type_name, _var_type(std_name, ftn_type),
            )
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
        raise ValueError(
            f"'active = {raw_expr}' references {std_name!r}, which is not a "
            f"host or module variable."
        )

    def _type_of(op):
        return op.results[0].type

    def _logical(op):
        if _type_of(op) != i1:
            raise ValueError(f"'active = {raw_expr}': a logical operand is not logical.")
        return op

    def _build(node):
        if isinstance(node, Name):
            return _name(node.std_name)
        if isinstance(node, LogicalLiteral):
            return arith.ConstantOp(IntegerAttr.from_int_and_width(int(node.value), 1))
        if isinstance(node, IntLiteral):
            return arith.ConstantOp(IntegerAttr.from_int_and_width(node.value, 32))
        if isinstance(node, Not):
            return _not(_logical(_build(node.operand)))
        assert isinstance(node, Binary)
        if node.op in ("eqv", "neqv"):
            return _equivalence(node)
        lhs, rhs = _build(node.lhs), _build(node.rhs)
        if node.op == "and":
            return arith.AndIOp(_logical(lhs), _logical(rhs))
        if node.op == "or":
            return arith.OrIOp(_logical(lhs), _logical(rhs))
        return _compare(node.op, lhs, rhs)

    def _equivalence(node):
        # A logical literal operand folds away (x .eqv. .true. is x), since
        # the printer reads any XOrIOp with a constant operand as .not.
        negate = node.op == "neqv"
        operands = []
        for side in (node.lhs, node.rhs):
            if isinstance(side, LogicalLiteral):
                negate ^= not side.value
            else:
                operands.append(_logical(_build(side)))
        if not operands:
            return arith.ConstantOp(IntegerAttr.from_int_and_width(int(not negate), 1))
        result = operands[0] if len(operands) == 1 else arith.XOrIOp(*operands)
        if len(operands) == 2:
            negate = not negate  # XOrIOp is .neqv.
        return _not(result) if negate else result

    def _compare(op, lhs, rhs):
        types = {_type_of(lhs), _type_of(rhs)}
        if i1 in types:
            if types != {i1} or op not in ("eq", "ne"):
                raise ValueError(
                    f"'active = {raw_expr}': cannot compare a logical with "
                    f"'{op}'; use .eqv./.neqv."
                )
            same = arith.XOrIOp(lhs, rhs)
            return _not(same) if op == "eq" else same
        if f64 in types:
            lhs, rhs = (_as_real(v) for v in (lhs, rhs))
            return arith.CmpfOp(lhs, rhs, _FLOAT_PREDICATES[op])
        return arith.CmpiOp(lhs, rhs, _INT_PREDICATES[op])

    def _as_real(op):
        if _type_of(op) == f64:
            return op
        if isinstance(op, arith.ConstantOp):
            return arith.ConstantOp(FloatAttr(float(op.value.value.data), f64))
        raise ValueError(
            f"'active = {raw_expr}': cannot compare an integer variable with a real one."
        )

    return _build(parse_active_expr(raw_expr))
