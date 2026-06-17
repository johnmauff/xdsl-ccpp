"""fir-to-meta: Generate CCPP dialect metadata from FIR (Flang/HLFIR) MLIR.

This pass reads ``func.func`` operations whose symbol names follow the Flang
mangling convention ``_QM{module}P{procedure}`` and synthesises equivalent
``ccpp.table_properties`` / ``ccpp.arg_table`` / ``ccpp.arg`` operations.

Information that can be derived from FIR:
- Argument names (from ``fir.bindc_name`` entries in ``arg_attrs``)
- Argument types and array dimensions (from the FIR function type)
- Intent (from ``hlfir.declare`` ops in the function body)
- Optional flag (from ``hlfir.declare`` ``fortran_attrs``)
- Character length (from the type-parameter operand of ``hlfir.declare``)

Information NOT available from FIR that is silently omitted:
- ``standard_name`` / ``long_name``
- ``units``

FIR type mapping
----------------
``!fir.ref<i32>``                          → ``integer`` (scalar)
``!fir.ref<f32>`` / ``!fir.ref<f64>``     → ``real`` (scalar)
``!fir.boxchar<1>``                        → ``character`` (length from body)
``!fir.box<!fir.array<?x?xf64>>``         → ``real`` (2-D array)
``!fir.ref<!fir.array<?xi32>>``            → ``integer`` (1-D array)

The pass handles two parsing scenarios:

1. **Registered FIR/HLFIR dialects** (the normal case when running through
   ``ccpp_opt``): ``hlfir.declare`` is a ``DeclareOp`` with
   ``FortranVariableFlagsAttr`` for intent.

2. **Unregistered / generic form** (e.g. when parsing with
   ``allow_unregistered`` only): ``hlfir.declare`` appears as
   ``UnregisteredOpWithNameOp`` with an ``UnregisteredAttrWithName`` for
   the ``fortran_attrs`` property.
"""

from __future__ import annotations

import re
import struct
from collections import defaultdict
from dataclasses import dataclass

from xdsl.context import Context
from xdsl.dialects import builtin
from xdsl.dialects import func as func_dialect
from xdsl.dialects.arith import ConstantOp
from xdsl.dialects.builtin import StringAttr
from xdsl.ir import Block, Operation
from xdsl.passes import ModulePass

from xdsl_ccpp.dialects.ccpp import ArgumentOp, ArgumentTableOp, TablePropertiesOp

# Flang mangling: _QM<module>P<procedure>
_FIR_MANGLE_RE = re.compile(r"^_QM([A-Za-z_][A-Za-z0-9_]*)P([A-Za-z_][A-Za-z0-9_]*)$")

# FIR → CCPP base type
_SCALAR_TYPE_MAP = {
    "i32": "integer",
    "i64": "integer",
    "f32": "real",
    "f64": "real",
}

# intent string → CCPP intent
_INTENT_MAP = {
    "intent_in": "in",
    "intent_out": "out",
    "intent_inout": "inout",
}


def _parse_fir_type(fir_type) -> tuple[str, int]:
    """Convert a FIR MLIR type to a (ccpp_type_str, num_dimensions) pair.

    The returned type string is one of ``'integer'``, ``'real'``,
    ``'character'``, or ``'unknown'``.  Array dimensions are counted from
    the ``?x`` prefixes in ``!fir.array<…>`` types.
    """
    t = str(fir_type)

    # !fir.boxchar<N> → character scalar (length extracted from body)
    if t.startswith("!fir.boxchar"):
        return "character", 0

    # !fir.box<!fir.array<?x...xT>>
    m = re.match(r"!fir\.box<!fir\.array<((?:\?x)*)([^>]+(?:>)*)>>$", t)
    if m:
        dims = m.group(1).count("?")
        return _elem_to_ccpp(m.group(2)), dims

    # !fir.ref<!fir.array<?x...xT>>
    m = re.match(r"!fir\.ref<!fir\.array<((?:\?x)*)([^>]+(?:>)*)>>$", t)
    if m:
        dims = m.group(1).count("?")
        return _elem_to_ccpp(m.group(2)), dims

    # !fir.ref<T>
    m = re.match(r"!fir\.ref<(.+)>$", t)
    if m:
        return _elem_to_ccpp(m.group(1)), 0

    return "unknown", 0


def _elem_to_ccpp(elem: str) -> str:
    """Map a scalar FIR element type string to a CCPP type string."""
    if elem in _SCALAR_TYPE_MAP:
        return _SCALAR_TYPE_MAP[elem]
    if elem.startswith("!fir.char") or elem.startswith("!fir.boxchar"):
        return "character"
    return "unknown"


def _is_declare_op(op: Operation) -> bool:
    """Return True if *op* is a hlfir.declare in either registered or generic form."""
    # Registered form (xdsl.dialects.experimental.hlfir.DeclareOp)
    if type(op).__name__ == "DeclareOp" and "hlfir" in type(op).__module__:
        return True
    # Unregistered / generic form
    op_name_attr = getattr(op, "op_name", None)
    if op_name_attr is not None and hasattr(op_name_attr, "data"):
        return op_name_attr.data == "hlfir.declare"
    return False


def _get_uniq_name(op: Operation) -> str | None:
    """Return the ``uniq_name`` string from a hlfir.declare op, or None."""
    uniq = op.properties.get("uniq_name")
    if uniq is not None and hasattr(uniq, "data"):
        return uniq.data
    return None


def _get_optional_flag(op: Operation) -> bool:
    """Return True if the hlfir.declare op carries the Fortran OPTIONAL attribute."""
    fortran_attrs = op.properties.get("fortran_attrs")
    if fortran_attrs is None:
        return False
    # Registered form: FortranVariableFlagsAttr with .flags set
    flags = getattr(fortran_attrs, "flags", None)
    if flags is not None:
        for flag in flags:
            if getattr(flag, "value", None) == "optional":
                return True
        return False
    # Unregistered form: raw string in .data
    value = getattr(fortran_attrs, "value", None)
    if value is not None and hasattr(value, "data"):
        return "optional" in value.data
    return False


def _get_intent_str(op: Operation) -> str | None:
    """Extract the intent string (``'in'``, ``'out'``, ``'inout'``) from a
    hlfir.declare op, or return None when no intent is specified.

    Handles both the registered ``FortranVariableFlagsAttr`` (set of
    ``FortranVariableFlags`` enum values) and the unregistered
    ``UnregisteredAttrWithName`` form.
    """
    fortran_attrs = op.properties.get("fortran_attrs")
    if fortran_attrs is None:
        return None

    # Registered form: FortranVariableFlagsAttr with .flags set
    flags = getattr(fortran_attrs, "flags", None)
    if flags is not None:
        for flag in flags:
            flag_val = getattr(flag, "value", None)
            if flag_val in _INTENT_MAP:
                return _INTENT_MAP[flag_val]
        return None

    # Unregistered form: UnregisteredAttrWithName with .value.data string
    value = getattr(fortran_attrs, "value", None)
    if value is not None and hasattr(value, "data"):
        return _INTENT_MAP.get(value.data)

    return None


def _get_typeparam_operand_index(op: Operation) -> int:
    """Return the operand index of the type-parameter (character length) for a
    hlfir.declare op, or -1 if no type parameter is present.

    The ``operandSegmentSizes`` property encodes four i32 counts:
    ``[base, extra, typeparam, dummy_scope]``.  When ``typeparam > 0`` the
    type-parameter operand starts at index ``base + extra``.
    """
    seg_sizes = op.properties.get("operandSegmentSizes")
    if seg_sizes is None:
        return -1
    raw = getattr(seg_sizes, "data", None)
    if raw is None:
        return -1
    raw_bytes = getattr(raw, "data", None)
    if raw_bytes is None or len(raw_bytes) < 12:
        return -1
    typeparam_count = struct.unpack_from("<i", raw_bytes, 8)[0]
    if typeparam_count == 0:
        return -1
    base_count = struct.unpack_from("<i", raw_bytes, 0)[0]
    extra_count = struct.unpack_from("<i", raw_bytes, 4)[0]
    return base_count + extra_count


def _build_intent_map(
    func_body: Block, module_name: str, func_name: str
) -> dict[str, str]:
    """Scan ``hlfir.declare`` ops to build an arg_name → intent dict."""
    prefix = f"_QM{module_name}F{func_name}E"
    intent_map: dict[str, str] = {}

    for op in func_body.ops:
        if not _is_declare_op(op):
            continue
        uid = _get_uniq_name(op)
        if uid is None or not uid.startswith(prefix):
            continue
        arg_name = uid[len(prefix) :]
        if not arg_name:
            continue
        intent = _get_intent_str(op)
        if intent:
            intent_map[arg_name] = intent

    return intent_map


def _build_optional_map(
    func_body: Block, module_name: str, func_name: str
) -> set[str]:
    """Scan ``hlfir.declare`` ops to build a set of arg names with OPTIONAL."""
    prefix = f"_QM{module_name}F{func_name}E"
    optional_set: set[str] = set()

    for op in func_body.ops:
        if not _is_declare_op(op):
            continue
        uid = _get_uniq_name(op)
        if uid is None or not uid.startswith(prefix):
            continue
        arg_name = uid[len(prefix) :]
        if not arg_name:
            continue
        if _get_optional_flag(op):
            optional_set.add(arg_name)

    return optional_set


def _build_char_length_map(
    func_body: Block, module_name: str, func_name: str
) -> dict[str, str]:
    """Scan ``hlfir.declare`` ops to find character argument lengths.

    For a character argument the ``hlfir.declare`` may carry a type-parameter
    operand (an ``arith.constant`` index).  When present its integer value
    gives the fixed length; otherwise ``len=*`` (assumed-length) is used.
    """
    prefix = f"_QM{module_name}F{func_name}E"
    length_map: dict[str, str] = {}

    for op in func_body.ops:
        if not _is_declare_op(op):
            continue
        uid = _get_uniq_name(op)
        if uid is None or not uid.startswith(prefix):
            continue
        arg_name = uid[len(prefix) :]
        if not arg_name:
            continue

        typeparam_idx = _get_typeparam_operand_index(op)
        if typeparam_idx < 0:
            # No type-parameter operand → assumed-length
            length_map[arg_name] = "len=*"
            continue

        if len(op.operands) <= typeparam_idx:
            length_map[arg_name] = "len=*"
            continue

        typeparam_operand = op.operands[typeparam_idx]
        owner = typeparam_operand.owner
        if isinstance(owner, ConstantOp):
            value_attr = owner.value
            int_val = getattr(value_attr, "value", None)
            if int_val is not None and hasattr(int_val, "data"):
                length_map[arg_name] = f"len={int_val.data}"
            else:
                length_map[arg_name] = "len=*"
        else:
            length_map[arg_name] = "len=*"

    return length_map


def _build_arg_table(
    fn_op: func_dialect.FuncOp,
    table_name: str,
    module_name: str,
    func_name: str,
) -> ArgumentTableOp:
    """Build a ``ccpp.arg_table`` for one FIR subroutine."""
    arg_attrs_list = fn_op.properties.get("arg_attrs")
    function_type = fn_op.function_type
    body_blocks = list(fn_op.body.blocks)
    func_body = body_blocks[0] if body_blocks else None

    intent_map: dict[str, str] = {}
    char_len_map: dict[str, str] = {}
    optional_set: set[str] = set()
    if func_body is not None:
        intent_map = _build_intent_map(func_body, module_name, func_name)
        char_len_map = _build_char_length_map(func_body, module_name, func_name)
        optional_set = _build_optional_map(func_body, module_name, func_name)

    arg_ops: list[Operation] = []
    for i, fir_type in enumerate(function_type.inputs):
        # Get argument name from arg_attrs
        arg_name = f"arg{i}"
        if arg_attrs_list is not None and hasattr(arg_attrs_list, "data"):
            dict_attr = arg_attrs_list.data[i] if i < len(arg_attrs_list.data) else None
            if dict_attr is not None and hasattr(dict_attr, "data"):
                bindc = dict_attr.data.get("fir.bindc_name")
                if bindc is not None and hasattr(bindc, "data"):
                    arg_name = bindc.data

        ccpp_type, dims = _parse_fir_type(fir_type)
        if ccpp_type == "unknown":
            continue

        attr_dict: dict[str, object] = {"type": ccpp_type}

        intent = intent_map.get(arg_name)
        if intent:
            attr_dict["intent"] = intent

        if dims > 0:
            dim_names = ", ".join(f"dim{j + 1}" for j in range(dims))
            attr_dict["dimensions"] = f"({dim_names})"

        if ccpp_type == "character":
            char_len = char_len_map.get(arg_name, "len=*")
            attr_dict["kind"] = char_len

        if arg_name in optional_set:
            attr_dict["optional"] = "True"

        arg_ops.append(ArgumentOp(arg_name, ccpp_type, attr_dict))

    return ArgumentTableOp(table_name, "scheme", arg_ops)


def _find_ccpp_module(op: builtin.ModuleOp) -> builtin.ModuleOp | None:
    """Return the first named sub-``ModuleOp`` that contains CCPP ops, or None."""
    for child in op.body.block.ops:
        if not isinstance(child, builtin.ModuleOp):
            continue
        for grandchild in child.body.block.ops:
            if isinstance(grandchild, TablePropertiesOp):
                return child
    return None


@dataclass(frozen=True)
class FIRToMeta(ModulePass):
    """Generate CCPP metadata (table_properties / arg_table / arg) from FIR.

    Scans all ``func.func`` operations in the module whose symbol name follows
    the Flang mangling pattern ``_QM<module>P<procedure>`` and emits one
    ``ccpp.table_properties`` block per unique Fortran module, containing one
    ``ccpp.arg_table`` per procedure.

    The generated CCPP ops are placed in a named ``@ccpp_meta`` sub-module (or
    appended to an existing sub-module that already contains CCPP ops).  All
    FIR content in the top-level module is then removed, leaving only the CCPP
    sub-module.
    """

    name = "fir-to-meta"

    def apply(self, ctx: Context, op: builtin.ModuleOp) -> None:
        # Find any existing CCPP sub-module before scanning, so we can exclude
        # it from the FIR-removal step.
        existing_ccpp_mod = _find_ccpp_module(op)

        # Record all ops that are NOT the existing CCPP sub-module; these are
        # the FIR ops to remove after the metadata has been extracted.
        fir_ops = [
            child for child in op.body.block.ops if child is not existing_ccpp_mod
        ]

        # Collect all mangled func ops grouped by Fortran module name.
        # module_name → [(proc_name, FuncOp), ...]
        by_module: dict[str, list[tuple[str, func_dialect.FuncOp]]] = defaultdict(list)

        for fn_op in fir_ops:
            if not isinstance(fn_op, func_dialect.FuncOp):
                continue
            sym_name_attr = fn_op.sym_name
            if not hasattr(sym_name_attr, "data"):
                continue
            sym_name = sym_name_attr.data
            m = _FIR_MANGLE_RE.match(sym_name)
            if m is None:
                continue
            module_name = m.group(1)
            proc_name = m.group(2)
            by_module[module_name].append((proc_name, fn_op))

        # Build one ccpp.table_properties per Fortran module.
        new_table_props: list[Operation] = []
        for module_name, procs in by_module.items():
            arg_tables: list[Operation] = []
            for proc_name, fn_op in procs:
                arg_table = _build_arg_table(fn_op, proc_name, module_name, proc_name)
                arg_tables.append(arg_table)
            new_table_props.append(TablePropertiesOp(module_name, "scheme", arg_tables))

        # Use the existing CCPP sub-module or create a new one.
        ccpp_mod = existing_ccpp_mod
        if ccpp_mod is None:
            ccpp_mod = builtin.ModuleOp([], sym_name=StringAttr("ccpp_meta"))
            op.body.block.add_op(ccpp_mod)

        for table_props in new_table_props:
            ccpp_mod.body.block.add_op(table_props)

        # Remove all FIR ops that were present before this pass ran.
        for fir_op in fir_ops:
            fir_op.detach()

        # Strip FIR-origin module-level attributes (dlti, llvm, fir.*) so the
        # output is clean CCPP IR.
        fir_attr_prefixes = ("dlti.", "fir.", "llvm.", "hlfir.")
        to_remove = [
            k for k in op.attributes if any(k.startswith(p) for p in fir_attr_prefixes)
        ]
        for k in to_remove:
            op.attributes.pop(k)
