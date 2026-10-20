"""Suite subroutine dummy arguments: block signature, name hints, kind/unit casts and error arguments."""

from __future__ import annotations


from xdsl.dialects import arith, memref
from xdsl.dialects.builtin import (
    FloatAttr,
)
from xdsl.ir import Block, BlockArgument

from xdsl_ccpp.dialects.ccpp_utils import (
    KindCastOp,
    KindWriteBackOp,
    UnitConvertOp,
    UnitWriteBackOp,
)
from xdsl_ccpp.transforms.util.typing import TypeConversions
from xdsl_ccpp.util.ccpp_conventions import (
    CCPP_ERRMSG_LEN,
    CCPP_ERROR_CODE,
    CCPP_ERROR_MESSAGE,
    UNIT_CONVERSIONS,
    is_vertical_dimension,
    real_kind_width,
)


def _std_key(arg) -> str:
    """Return the standard_name (lowercase) if set, otherwise the local arg name."""
    if arg.hasAttr("standard_name"):
        return arg.getAttr("standard_name").lower()
    return arg.name


def _vertical_dim_index(fn_arg) -> "int | None":
    """Return the 1-based index of fn_arg's vertical dimension, or None.

    Uses the scheme's own dim_names order, so it is per-scheme.
    """
    if not fn_arg.hasAttr("dim_names"):
        return None
    for idx, dim_name in enumerate(fn_arg.getAttr("dim_names")):
        if is_vertical_dimension(dim_name):
            return idx + 1
    return None


def _has_dims(a) -> bool:
    return a.hasAttr("dimensions") and a.getAttr("dimensions") > 0


def _arg_dims(a) -> int:
    """Return the dimension count to use for the block arg type.

    Promoted args get scheme_rank + 1: the suite receives the full host
    array, not the scheme's slice.
    """
    base = a.getAttr("dimensions") if a.hasAttr("dimensions") else 0
    if a.hasAttr("is_promoted"):
        return base + 1
    return base


def _block_arg_kind(a):
    """Return the kind for the suite block arg (the HOST kind when kind-mismatched)."""
    if a.hasAttr("model_var_kind_mismatch"):
        return a.getAttr("model_var_kind_mismatch").split(":")[1]
    return a.getAttr("kind") if a.hasAttr("kind") else None


def _build_block_and_name_hints(input_arg_list) -> tuple:
    """Build the Block and resolve each input arg's dummy-argument name hint.

    Name collisions are disambiguated via model_var_name.
    Returns (new_block, input_arg_types, data_ops, final_values).
    """
    input_arg_types = [
        TypeConversions.convert(a.getAttr("type"), _block_arg_kind(a), _arg_dims(a))
        for a in input_arg_list
    ]

    new_block = Block(arg_types=input_arg_types)

    def _hint_for(fn_arg, base_name: str) -> str:
        if fn_arg.hasAttr("allocatable"):
            return base_name + "__alloc"
        if fn_arg.hasAttr("optional"):
            return base_name + "__opt"
        if _has_dims(fn_arg) and fn_arg.getAttr("intent") == "in":
            # __in makes the printer emit intent(in) instead of inout.
            return base_name + "__in"
        return base_name

    def _printed_name(hint: str) -> str:
        # print_ftn.py strips these suffixes, so collisions must be
        # detected on the stripped (printed) form.
        if hint.endswith("__alloc"):
            return hint[: -len("__alloc")]
        if hint.endswith("__opt"):
            return hint[: -len("__opt")]
        if hint.endswith("__in"):
            return hint[: -len("__in")]
        return hint

    # Each entry is a distinct standard_name. Use the scheme's local name;
    # only when two standard_names share a local name (e.g.
    # examples/var_compat) fall back to the host's model_var_name.
    default_hints = [_hint_for(fn_arg, fn_arg.name) for fn_arg in input_arg_list]
    collision_counts: dict[str, int] = {}
    for h in default_hints:
        printed = _printed_name(h)
        collision_counts[printed] = collision_counts.get(printed, 0) + 1

    data_ops = {}
    printed_seen: dict[str, str] = {}  # printed dummy-arg name -> the fn_arg.name that claimed it
    for idx, fn_arg in enumerate(input_arg_list):
        hint = default_hints[idx]
        printed = _printed_name(hint)
        if collision_counts[printed] > 1:
            if not fn_arg.hasAttr("model_var_name"):
                raise ValueError(
                    f"Suite dummy-argument name collision on {printed!r}: "
                    f"scheme argument {fn_arg.name!r} shares this local name "
                    f"with another, unrelated standard_name, and has no "
                    f"host-matched canonical name (model_var_name) to "
                    f"disambiguate with. Give the host a distinct local "
                    f"name for this standard_name, or rename one of the "
                    f"colliding schemes' arguments."
                )
            hint = _hint_for(fn_arg, fn_arg.getAttr("model_var_name"))
            printed = _printed_name(hint)
            if printed in printed_seen:
                raise ValueError(
                    f"Suite dummy-argument name collision: both "
                    f"{printed_seen[printed]!r} and {fn_arg.name!r} (different "
                    f"standard_names) resolve to the same dummy-argument "
                    f"name {printed!r} even after preferring model_var_name. "
                    f"Give the host a distinct local name for one of these "
                    f"standard_names."
                )
        printed_seen[printed] = fn_arg.name
        new_block.args[idx].name_hint = hint
        data_ops[fn_arg.name] = new_block.args[idx]

    # Index-keyed resolved values: fn_arg.name is not unique for colliding
    # args, so the name-keyed data_ops can't be relied on for them.
    final_values: list = [new_block.args[idx] for idx in range(len(input_arg_list))]

    return new_block, input_arg_types, data_ops, final_values


_UNIT_CONV_OP_MAP = {"+": arith.AddfOp, "-": arith.SubfOp, "*": arith.MulfOp}


def _parse_unit_conversion(expr: str) -> "tuple | None":
    """Split a UNIT_CONVERSIONS value ("+ 273.15") into (arith op class, float).

    Returns None if the literal doesn't round-trip through str(float)
    (e.g. "1.0E6"), so output stays byte-identical to the opaque-text path.
    An unknown operator (e.g. '/') raises KeyError rather than mis-parsing.
    """
    op_str, value_str = expr.split(" ", 1)
    value = float(value_str)
    if str(value) != value_str:
        return None
    return _UNIT_CONV_OP_MAP[op_str], value


def _apply_kind_and_unit_casts(
    input_arg_list, new_block, data_ops, final_values, divergent_std_keys,
) -> tuple:
    """Insert KindCastOps/UnitConvertOps for kind- and unit-mismatched input args.

    Divergent standard_names are skipped; they are marshaled per call site
    instead (see _apply_divergent_marshaling). An arg with both mismatches
    chains kind cast -> unit convert, and its write-backs run in reverse
    order (unit first, then kind) so they don't corrupt each other.

    Mutates data_ops/final_values in place; returns (kind_cast_ops,
    unit_convert_ops, writeback_ops).
    """
    kind_cast_ops: list = []
    unit_convert_ops: list = []
    writeback_ops: list = []
    for idx, fn_arg in enumerate(input_arg_list):
        if _std_key(fn_arg) in divergent_std_keys:
            continue
        intent = fn_arg.getAttr("intent") if fn_arg.hasAttr("intent") else "in"
        cur = new_block.args[idx]
        chain: list = []  # (kind/unit, result_ssa, source_ssa, param)

        # Character length mismatches need no cast: the block arg uses the host length.
        if (
            fn_arg.hasAttr("model_var_kind_mismatch")
            and fn_arg.getAttr("type") != "character"
        ):
            scheme_kind, host_kind = fn_arg.getAttr("model_var_kind_mismatch").split(":")
            scheme_type = TypeConversions.convert(
                fn_arg.getAttr("type"), scheme_kind, _arg_dims(fn_arg)
            )
            cast_op = KindCastOp(cur, scheme_kind, scheme_type)
            cast_op.res.name_hint = f"{fn_arg.name}_kind_cast"
            kind_cast_ops.append(cast_op)
            chain.append(("kind", cast_op.res, cur, host_kind))
            cur = cast_op.res

        if fn_arg.hasAttr("model_var_unit_mismatch"):
            scheme_units, host_units = fn_arg.getAttr("model_var_unit_mismatch").split(":", 1)
            to_scheme_expr, to_host_expr = UNIT_CONVERSIONS[(scheme_units, host_units)]
            kind_str = fn_arg.getAttr("kind") if fn_arg.hasAttr("kind") else None
            arg_type = TypeConversions.convert(
                fn_arg.getAttr("type"), kind_str, _arg_dims(fn_arg),
            )
            pre_expr = "" if intent == "out" else to_scheme_expr
            # Structured arith conversion only for scalars with a bare-digit
            # kind (an arith-compatible float); otherwise opaque text. `cur`
            # must be a plain block arg, or _single_op_region would pull an
            # unattached KindCastOp into this op's region (double-attach).
            structured_conv = None
            if (
                kind_str is not None
                and real_kind_width(kind_str) is not None
                and _arg_dims(fn_arg) == 0
                and intent != "out"
                and isinstance(cur, BlockArgument)
            ):
                structured_conv = _parse_unit_conversion(to_scheme_expr)
            if structured_conv is not None:
                op_cls, value = structured_conv
                load_op = memref.LoadOp.get(cur, [])
                const_op = arith.ConstantOp(FloatAttr(value, arg_type.element_type))
                conv_arith_op = op_cls(load_op, const_op)
                conv_op = UnitConvertOp(cur, result_type=arg_type, conversion_op=conv_arith_op)
            else:
                conv_op = UnitConvertOp(cur, pre_expr, arg_type)
            conv_op.res.name_hint = f"{fn_arg.name}_unit_conv"
            unit_convert_ops.append(conv_op)
            chain.append(("unit", conv_op.res, cur, to_host_expr))
            cur = conv_op.res

        if not chain:
            continue

        data_ops[fn_arg.name] = cur
        final_values[idx] = cur

        if intent in ("inout", "out"):
            for kind_or_unit, result_ssa, source_ssa, param in reversed(chain):
                if kind_or_unit == "kind":
                    writeback_ops.append(KindWriteBackOp(result_ssa, source_ssa, param))
                else:
                    writeback_ops.append(UnitWriteBackOp(result_ssa, source_ssa, param))

    return kind_cast_ops, unit_convert_ops, writeback_ops


def _alloc_output_error_args(output_arg_list, data_ops) -> dict:
    """Allocate every output arg, plus fallback errflg/errmsg if not already present.

    Mutates data_ops (adds each fn_arg.name plus "errflg"/"errmsg"
    aliases); returns alloc_ops.
    """
    alloc_ops = {}
    # Detect by standard_name, not local name (schemes may call it e.g.
    # "errcode"); otherwise a spurious second allocation/return value results.
    has_errflg_std = False
    has_errmsg_std = False
    for fn_arg in output_arg_list:
        arg_type = fn_arg.getAttr("type")
        kind = fn_arg.getAttr("kind") if fn_arg.hasAttr("kind") else None
        full_type = TypeConversions.convert(arg_type, kind, 0)
        alloc_op = memref.AllocaOp.get(
            full_type.element_type, shape=list(full_type.shape.data)
        )
        alloc_op.memref.name_hint = fn_arg.name
        alloc_ops[fn_arg.name] = alloc_op
        data_ops[fn_arg.name] = alloc_op
        std_name = (
            fn_arg.getAttr("standard_name").lower()
            if fn_arg.hasAttr("standard_name") else None
        )
        if std_name == CCPP_ERROR_CODE:
            has_errflg_std = True
            data_ops["errflg"] = alloc_op  # canonical internal alias
        elif std_name == CCPP_ERROR_MESSAGE:
            has_errmsg_std = True
            data_ops["errmsg"] = alloc_op  # canonical internal alias

    if not has_errflg_std:
        alloc_op = memref.AllocaOp.get(
            TypeConversions.getBaseType("integer"), shape=[]
        )
        alloc_op.memref.name_hint = "errflg"
        alloc_ops["errflg"] = alloc_op
        data_ops["errflg"] = alloc_op
    if not has_errmsg_std:
        alloc_op = memref.AllocaOp.get(
            TypeConversions.getBaseType("character"), shape=[CCPP_ERRMSG_LEN]
        )
        alloc_op.memref.name_hint = "errmsg"
        alloc_ops["errmsg"] = alloc_op
        data_ops["errmsg"] = alloc_op

    return alloc_ops


def _tag_data_ops_by_std_name(input_arg_list, final_values, data_ops) -> None:
    """Register every input arg under ("std_name", ...) in data_ops.

    generateSchemeSubroutineCallOps prefers this key, so schemes that share
    a local name for different standard_names get the right value. Sourced
    from index-keyed final_values, since fn_arg.name isn't unique for them.
    """
    for idx, fn_arg in enumerate(input_arg_list):
        data_ops[("std_name", _std_key(fn_arg))] = final_values[idx]


def _find_producer_scheme(matching_arg, arg_tables) -> "str | None":
    """Return the scheme name whose arg table declares matching_arg (by identity)."""
    for scheme_name, table in arg_tables.items():
        for candidate in table.getFunctionArguments():
            if candidate is matching_arg:
                return scheme_name
    return None


def _alias_canonical_data_ops(arg_tables, all_args, data_ops) -> None:
    """Alias data_ops under each scheme's non-canonical local name for a standard_name."""
    for _scheme_name in arg_tables:
        for _fn_arg in arg_tables[_scheme_name].getFunctionArguments():
            _sk = _std_key(_fn_arg)
            _canonical = all_args.get(_sk)
            if _canonical is not None and _fn_arg.name != _canonical.name:
                if _fn_arg.name not in data_ops and _canonical.name in data_ops:
                    data_ops[_fn_arg.name] = data_ops[_canonical.name]
