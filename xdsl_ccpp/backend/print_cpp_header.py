from __future__ import annotations

from typing import IO

from xdsl.dialects import builtin, func, memref
from xdsl.dialects.builtin import (
    DYNAMIC_INDEX,
    Float32Type,
    Float64Type,
    IntAttr,
    IntegerType,
    MemRefType,
    ModuleOp,
)
from xdsl.utils.hints import isa

from xdsl_ccpp.dialects.ccpp_utils import CHostCapOp
from xdsl_ccpp.dialects.ccpp_utils import KindDefOp
from xdsl_ccpp.dialects.ccpp_utils import RealKindType as CCPPRealKindType


# ISO_FORTRAN_ENV constant → C++ type
_ISO_TO_CPP: dict[str, str] = {
    "REAL64":  "double",
    "REAL32":  "float",
    "INT64":   "long long",
    "INT32":   "int",
    "INT16":   "short",
    "INT8":    "signed char",
}


def _is_char_memref(mlir_type: object) -> bool:
    """True for any memref<...xi8> (character scalar or string buffer)."""
    return (
        isinstance(mlir_type, MemRefType)
        and isinstance(mlir_type.element_type, IntegerType)
        and mlir_type.element_type.width.data == 8
    )


def _is_allocatable_char(mlir_type: object) -> bool:
    """True for memref<memref<?xi8>> (allocatable character array)."""
    return (
        isinstance(mlir_type, MemRefType)
        and isinstance(mlir_type.element_type, MemRefType)
        and isinstance(mlir_type.element_type.element_type, IntegerType)
        and mlir_type.element_type.element_type.width.data == 8
    )


def _has_array_dims(mlir_type: object) -> bool:
    """Return True when the type has at least one dynamic array dimension.

    For character memrefs the last dim is the string length; only the
    preceding dims (if any) count as array dimensions.
    """
    if not isinstance(mlir_type, MemRefType):
        return False
    if _is_char_memref(mlir_type):
        n_array_dims = len(list(mlir_type.shape)) - 1
        return n_array_dims > 0
    return any(d.data == DYNAMIC_INDEX for d in mlir_type.shape)


def _is_scalar_memref(mlir_type: object) -> bool:
    """True for memrefs with no dynamic dimensions (zero-dim or all-static).

    These correspond to Fortran scalars declared with VALUE in BIND(C), which
    C++ receives by value rather than by pointer.
    """
    return (
        isinstance(mlir_type, MemRefType)
        and not _is_char_memref(mlir_type)
        and not any(d.data == DYNAMIC_INDEX for d in mlir_type.shape)
    )


def _cpp_type(mlir_type: object, intent: str) -> str:
    """Map an MLIR type and intent string to a C++ type.

    Character memrefs and scalar memrefs with intent(in) map to pass-by-value
    types matching the Fortran BIND(C) VALUE attribute; all other memrefs and
    output scalars map to pointer types.
    """
    if isinstance(mlir_type, MemRefType):
        elem = mlir_type.element_type
        if _is_char_memref(mlir_type):
            return "const char*" if intent == "in" else "char*"
        # Scalar (no dynamic dims) with intent(in) → Fortran VALUE → C++ by-value
        if _is_scalar_memref(mlir_type) and intent == "in":
            if isinstance(elem, IntegerType):
                return "int"
            if isinstance(elem, Float32Type):
                return "float"
            return "double"
        # Array or non-in scalar → by pointer
        if isinstance(elem, IntegerType):
            return "int*"
        if isinstance(elem, Float32Type):
            return "float*"
        return "double*"
    if isinstance(mlir_type, IntegerType):
        return "int" if intent == "in" else "int*"
    if isinstance(mlir_type, Float32Type):
        return "float" if intent == "in" else "float*"
    # Float64Type, CCPPRealKindType, etc.
    return "double" if intent == "in" else "double*"


def _rank_comment(mlir_type: object) -> str:
    """Return a comment like '/* rank-2 column-major */' for multi-dim array args."""
    if not isinstance(mlir_type, MemRefType):
        return ""
    if _is_char_memref(mlir_type):
        return ""
    n_dyn = sum(1 for d in mlir_type.shape if d.data == DYNAMIC_INDEX)
    if n_dyn >= 2:
        return f"  /* rank-{n_dyn} column-major */"
    return ""


def _intent_from_arg(arg: object, inout_block_args: set) -> str:
    """Replicate the intent logic from print_ftn._print_fn for a block argument."""
    mlir_type = arg.type
    if _is_allocatable_char(mlir_type):
        return "out"
    if arg.name_hint and arg.name_hint.endswith("__in"):
        return "in"
    if _has_array_dims(mlir_type):
        return "inout"
    if arg in inout_block_args:
        return "inout"
    return "in"


def _fn_params(fn_op: func.FuncOp) -> list[tuple[str, str, str]]:
    """Return (name, cpp_type, comment) tuples for every argument of a BIND(C) function.

    Includes both input block arguments and output (AllocaOp-result) return values,
    in the same order the Fortran printer lists them.
    """
    block = fn_op.body.block

    # Find inout block args: block args that appear directly in a ReturnOp
    inout_block_args: set = set()
    output_rets: list = []
    for op in block.ops:
        if isa(op, func.ReturnOp):
            for ret_val in op.arguments:
                if isa(ret_val.owner, memref.AllocaOp):
                    output_rets.append(ret_val)
                else:
                    inout_block_args.add(ret_val)
            break

    params: list[tuple[str, str, str]] = []

    for arg in block.args:
        hint = arg.name_hint or f"arg_{arg.index}"
        if hint.endswith("__alloc"):
            name = hint[:-7]
        elif hint.endswith("__opt"):
            name = hint[:-5]
        elif hint.endswith("__in"):
            name = hint[:-4]
        else:
            name = hint
        intent = _intent_from_arg(arg, inout_block_args)
        params.append((name, _cpp_type(arg.type, intent), _rank_comment(arg.type)))

    for ret_val in output_rets:
        name = ret_val.name_hint or f"out_{len(params)}"
        params.append((name, _cpp_type(ret_val.type, "out"), _rank_comment(ret_val.type)))

    return params


def _emit_cap_header(cap_module: ModuleOp, output: IO[str]) -> None:
    """Write the <HostName>_ccpp_cap.h extern "C" declaration block."""
    bind_c_fns = [
        op for op in cap_module.body.ops
        if isa(op, func.FuncOp)
        and not op.is_declaration
        and "bind_c" in op.attributes
    ]
    if not bind_c_fns:
        return

    output.write("// Generated by xdsl-ccpp."
                 " Array arguments are column-major (Fortran order).\n")
    output.write("// Pass Kokkos::View with LayoutLeft,"
                 " or transpose before calling.\n")
    output.write("#pragma once\n")
    output.write("#ifdef __cplusplus\n")
    output.write('extern "C" {\n')
    output.write("#endif\n\n")

    for fn_op in bind_c_fns:
        fn_name = fn_op.sym_name.data
        params = _fn_params(fn_op)
        if not params:
            output.write(f"void {fn_name}(void);\n\n")
            continue
        output.write(f"void {fn_name}(\n")
        for i, (name, cpp_t, comment) in enumerate(params):
            comma = "," if i < len(params) - 1 else " "
            output.write(f"    {cpp_t:<16} {name}{comma}{comment}\n")
        output.write(");\n\n")

    output.write("#ifdef __cplusplus\n")
    output.write("}\n")
    output.write("#endif\n")


def _emit_kinds_header(kinds_module: ModuleOp, output: IO[str]) -> None:
    """Write the ccpp_kinds.h typedef file."""
    kind_ops = [op for op in kinds_module.body.ops if isa(op, KindDefOp)]
    output.write("// Generated by xdsl-ccpp. Kind aliases match ccpp_kinds.F90.\n")
    output.write("#pragma once\n")
    for op in kind_ops:
        kind_name = op.kind_name.data
        kind_value = op.kind_value.data
        cpp_type = _ISO_TO_CPP.get(kind_value, "double")
        output.write(f"typedef {cpp_type:<8}  {kind_name}_t;\n")


def print_to_cpp_headers(prog: ModuleOp, output: IO[str]) -> None:
    """Emit C++ header sections for all BIND(C) cap modules in *prog*.

    Emits up to three ``// FILE:``-delimited sections:

    - ``<HostName>_ccpp_cap.h`` — ``extern "C"`` declarations for each BIND(C)
      subroutine, using ISO-C-compatible types.
    - ``ccpp_kinds.h`` — ``typedef`` aliases for every CCPP kind name.
    - ``<mod_name>.h`` — verbatim ``cpp_text`` from each ``CHostCapOp`` (one
      section per op, emitted after the standard cap/kinds headers).

    Sections are separated by ``// -----`` so ``split_fortran_output`` in the
    driver can write them as individual files alongside the ``.F90`` outputs.

    Nothing is written when no BIND(C) functions and no CHostCapOps are found.
    """
    cap_module = None
    kinds_module = None
    chost_ops: list[CHostCapOp] = []
    for sub in prog.body.ops:
        if isinstance(sub, builtin.ModuleOp):
            name = sub.sym_name.data if sub.sym_name else ""
            if name.endswith("_ccpp_cap"):
                cap_module = sub
            elif name == "ccpp_kinds":
                kinds_module = sub
        elif isinstance(sub, CHostCapOp):
            chost_ops.append(sub)

    wrote = False

    if cap_module is not None:
        bind_c_present = any(
            isa(op, func.FuncOp) and not op.is_declaration and "bind_c" in op.attributes
            for op in cap_module.body.ops
        )
        if bind_c_present:
            output.write(f"// FILE: {cap_module.sym_name.data}.h\n")
            _emit_cap_header(cap_module, output)
            wrote = True

    if kinds_module is not None and wrote:
        output.write("// -----\n")
        output.write("// FILE: ccpp_kinds.h\n")
        _emit_kinds_header(kinds_module, output)

    for op in chost_ops:
        if wrote:
            output.write("// -----\n")
        output.write(f"// FILE: {op.mod_name.data}.h\n")
        output.write(op.cpp_text.data)
        wrote = True
        if op.wrapper_text.data:
            wrapper_file = (
                op.mod_name.data.replace("_ccpp_chost_cap", "_chost") + ".hpp"
            )
            output.write("// -----\n")
            output.write(f"// FILE: {wrapper_file}\n")
            output.write(op.wrapper_text.data)
