"""Suite subroutine dummy arguments: block signature, name hints, kind/unit casts and error arguments."""

from __future__ import annotations


from xdsl.dialects import memref
from xdsl.dialects.builtin import (
    DYNAMIC_INDEX,
    i8,
)
from xdsl.ir import Block

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


def _block_arg_type(a):
    """Type of the suite block arg. An unmatched ``len=*`` character arg
    (a package-cap segment's interface) stays assumed-length, so the caller's
    length passes through instead of CCPP_ERRMSG_LEN."""
    kind = _block_arg_kind(a)
    if a.getAttr("type") == "character" and (kind or "").replace(" ", "") == "len=*":
        return memref.MemRefType(i8, [DYNAMIC_INDEX] * (_arg_dims(a) + 1))
    return TypeConversions.convert(a.getAttr("type"), kind, _arg_dims(a))


def _build_block_and_name_hints(input_arg_list) -> tuple:
    """Build the Block and resolve each input arg's dummy-argument name.

    Each entry is a distinct standard_name and is named by the scheme's
    local name; only when two standard_names share a local name (e.g.
    examples/var_compat) is the host's model_var_name used instead. The
    names are returned for the suite subroutine's arg_attrs
    (suite_arg_attrs), which is where later passes and the printers read
    them -- a block argument's name_hint is only a hint (xDSL drops a
    trailing "_<digits>" from it).
    Returns (new_block, input_arg_types, data_ops, final_values, names).
    """
    input_arg_types = [_block_arg_type(a) for a in input_arg_list]

    new_block = Block(arg_types=input_arg_types)

    collision_counts: dict[str, int] = {}
    for fn_arg in input_arg_list:
        collision_counts[fn_arg.name] = collision_counts.get(fn_arg.name, 0) + 1

    data_ops = {}
    names: list[str] = []
    name_seen: dict[str, str] = {}  # dummy-arg name -> the fn_arg.name that claimed it
    for idx, fn_arg in enumerate(input_arg_list):
        name = fn_arg.name
        if collision_counts[name] > 1:
            if not fn_arg.hasAttr("model_var_name"):
                raise ValueError(
                    f"Suite dummy-argument name collision on {name!r}: "
                    f"scheme argument {fn_arg.name!r} shares this local name "
                    f"with another, unrelated standard_name, and has no "
                    f"host-matched canonical name (model_var_name) to "
                    f"disambiguate with. Give the host a distinct local "
                    f"name for this standard_name, or rename one of the "
                    f"colliding schemes' arguments."
                )
            name = fn_arg.getAttr("model_var_name")
            if name in name_seen:
                raise ValueError(
                    f"Suite dummy-argument name collision: both "
                    f"{name_seen[name]!r} and {fn_arg.name!r} (different "
                    f"standard_names) resolve to the same dummy-argument "
                    f"name {name!r} even after preferring model_var_name. "
                    f"Give the host a distinct local name for one of these "
                    f"standard_names."
                )
        name_seen[name] = fn_arg.name
        names.append(name)
        new_block.args[idx].name_hint = name
        data_ops[fn_arg.name] = new_block.args[idx]

    # Index-keyed resolved values: fn_arg.name is not unique for colliding
    # args, so the name-keyed data_ops can't be relied on for them.
    final_values: list = [new_block.args[idx] for idx in range(len(input_arg_list))]

    return new_block, input_arg_types, data_ops, final_values, names


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
            to_scheme, to_host = UNIT_CONVERSIONS[(scheme_units, host_units)]
            kind_str = fn_arg.getAttr("kind") if fn_arg.hasAttr("kind") else None
            arg_type = TypeConversions.convert(
                fn_arg.getAttr("type"), kind_str, _arg_dims(fn_arg),
            )
            # intent(out): the scheme does not read the value, so no conversion in.
            conv_op = UnitConvertOp(cur, arg_type, *(() if intent == "out" else to_scheme))
            conv_op.res.name_hint = f"{fn_arg.name}_unit_conv"
            unit_convert_ops.append(conv_op)
            chain.append(("unit", conv_op.res, cur, to_host))
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
                    writeback_ops.append(UnitWriteBackOp(result_ssa, source_ssa, *param))

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
