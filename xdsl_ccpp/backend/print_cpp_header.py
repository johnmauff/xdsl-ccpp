from __future__ import annotations

from typing import IO

from xdsl.dialects import arith, builtin, func, math, memref
from xdsl.dialects.builtin import (
    DYNAMIC_INDEX,
    Float32Type,
    FloatAttr,
    IntAttr,
    IntegerAttr,
    IntegerType,
    MemRefType,
    ModuleOp,
)
from xdsl.ir import BlockArgument, SSAValue
from xdsl.utils.hints import isa

from xdsl_ccpp.backend import expr_precedence
from xdsl_ccpp.backend.print_ftn import classify_arg_intent, wrap_paren_list
from xdsl_ccpp.dialects.ccpp_utils import (
    ArrayConstructorExprOp,
    CallExprOp,
    CFunctionSigOp,
    CHostCapOp,
    CppBraceInitCallOp,
    CppCallStatementOp,
    CppConstructorOp,
    CppFieldDeclOp,
    CppIncludeOp,
    CppNamespaceOp,
    CppStructDefOp,
    ExternCGuardOp,
    IndexExprOp,
    KindDefOp,
    MemberAccessExprOp,
    RawCppLinesOp,
    SliceExprOp,
    StrCmpOp,
    StringConcatExprOp,
    StringLiteralExprOp,
    TrimOp,
    VarRefExprOp,
)

# op.name -> C++ infix token, paralleling print_ftn.py's _binops. Built
# independently (not derived from print_ftn's own table) since this file
# has its own correctness requirements -- e.g. Fortran's AndIOp/OrIOp
# tokens are the logical words ".and."/".or."; C++'s are "&&"/"||".
_CPP_BINOPS: dict[str, str] = {
    arith.AddfOp.name: "+",
    arith.AddiOp.name: "+",
    arith.MulfOp.name: "*",
    arith.MuliOp.name: "*",
    arith.DivfOp.name: "/",
    arith.DivSIOp.name: "/",
    arith.DivUIOp.name: "/",
    arith.SubfOp.name: "-",
    arith.SubiOp.name: "-",
    arith.AndIOp.name: "&&",
    arith.OrIOp.name: "||",
}

# op.name -> predicate-name -> C++ comparison token, paralleling
# print_ftn.py's _cmp_ops. None marks a predicate with no C++ rendering --
# for CmpfOp, that's every predicate except the "ordered" ones
# (oeq/ogt/oge/olt/ole): C++'s own comparison operators are always
# ordered (false whenever either operand is NaN), so mapping "one"
# (ordered-not-equal, must be false for a NaN operand) to C++'s "!="
# (true for a NaN operand) or any "unordered" predicate to its
# seemingly-matching C++ operator would silently change NaN semantics --
# marked unsupported instead (not exercised by any real call site yet).
_CPP_CMP_OPS: dict[str, dict[str, str | None]] = {
    arith.CmpiOp.name: {
        "eq": "==", "ne": "!=",
        "slt": "<", "sle": "<=", "sgt": ">", "sge": ">=",
        "ult": "<", "ule": "<=", "ugt": ">", "uge": ">=",
    },
    arith.CmpfOp.name: {
        "false": None,
        "oeq": "==", "ogt": ">", "oge": ">=", "olt": "<", "ole": "<=",
        "one": None, "ord": None,
        "ueq": None, "ugt": None, "uge": None, "ult": None, "ule": None, "une": None,
        "uno": None, "true": None,
    },
}


def _cpp_string_literal(s: str) -> str:
    """Encode s as a double-quoted C++ string literal, escaping
    backslashes, double quotes, and control characters -- the one shared
    encoder for every site that turns arbitrary text into C++ source
    (previously each site embedded text unescaped, so e.g. a quote or
    backslash in the text could break or silently change the generated
    source)."""
    out = []
    for ch in s:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\r":
            out.append("\\r")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def _is_true_literal(const_op: object) -> bool:
    """True if const_op is an arith.ConstantOp holding a nonzero (True)
    value -- used to detect the XOR-as-NOT idiom correctly: XOR(x, true)
    is NOT x, but XOR(x, false) is just x unchanged, and a value-blind
    "is it a constant" check (print_ftn.py's own pre-existing idiom)
    wrongly treats both the same way."""
    match const_op.value:
        case IntegerAttr(value=v):
            return bool(v.data)
        case _:
            return False


def _is_i1(val: "SSAValue") -> bool:
    """True if val's type is i1 -- AndIOp/OrIOp only have a valid C++
    rendering (&&/||) when both operands are logical (i1); for a wider
    integer type, &&/|| would silently treat it as a logical-truthiness
    check instead of the real bitwise AND/OR a wider-int AndIOp/OrIOp
    means (Copilot PR #109 review, 2026-10-05)."""
    return isa(val.type, IntegerType) and val.type.width.data == 1


def _cpp_literal_str(attr: object) -> str:
    """Render an arith.ConstantOp's value attribute as a C++ literal --
    C++ sibling of print_ftn.py's attribute_value_to_str, minus the
    Fortran-specific kind-suffix/logical-literal spelling."""
    match attr:
        case IntegerAttr(value=val, type=IntegerType(width=IntAttr(data=1))):
            return "true" if bool(val.data) else "false"
        case IntegerAttr(value=val):
            return str(val.data)
        # Float32Type needs an "f" suffix -- without it, C++ treats the
        # literal as `double`, silently promoting surrounding f32
        # arithmetic and changing its rounding result (e.g. the f32 tree
        # (16777216 + 1) - 16777216 should be 0, not 1) (Copilot PR #109
        # review, 2026-10-05).
        case FloatAttr(value=val, type=Float32Type()) if val.data == 0:
            return "0.0f"
        case FloatAttr(value=val, type=Float32Type()):
            return f"{val.data}f"
        case FloatAttr(value=val) if val.data == 0:
            return "0.0"
        case FloatAttr(value=val):
            return str(val.data)
        case builtin.StringAttr() as s:
            return _cpp_string_literal(s.data)
        case _:
            return f"<!unknown value {attr}>"


def expr_to_cpp_str(op: object, variables: "dict[SSAValue, str] | None" = None) -> str:
    """Render op as a C++ sub-expression string.

    print_cpp_header.py's first-ever expression printer (lang-neutral-
    expr-ir Stage 2) -- mirrors print_ftn.py's _render_expr over the
    *same* arith/math/StrCmpOp/TrimOp/ccpp_utils expr-op tree, targeting
    C++ spelling and the shared xdsl_ccpp/backend/expr_precedence table
    instead of Fortran's.

    ``variables`` resolves a memref.LoadOp/StrCmpOp/TrimOp operand's name
    the same way print_ftn.py's ftnPrintContext.variables does; omit it
    when every leaf is one of the new ops that carries its own name as a
    property (VarRefExprOp) rather than a real compiled SSA load.
    """
    variables = variables if variables is not None else {}

    def var_name(val: SSAValue) -> str:
        return variables.get(val, val.name_hint or "<unnamed>")

    def render_value(val: SSAValue) -> str:
        """Render an SSA value used as an operand: resolve it by name
        first (covers function block arguments, whose owner is a Block,
        not an Operation -- render()'s own match must never recurse into
        val.owner blindly for those), falling back to recursively
        rendering its defining operation."""
        if val in variables:
            return variables[val]
        if isinstance(val, BlockArgument):
            return val.name_hint or "<unnamed>"
        return render(val.owner)

    def cmp_token(cmp_op, predicate_name: str) -> str:
        tok = _CPP_CMP_OPS[cmp_op.name][predicate_name]
        if tok is None:
            raise AssertionError(
                f"expr_to_cpp_str: predicate {predicate_name!r} on {cmp_op.name} "
                "has no C++ rendering"
            )
        return tok

    def render_binop(bin_op, l: SSAValue, r: SSAValue, token: str) -> str:
        my_level = expr_precedence.level_of(bin_op)
        my_assoc = expr_precedence.assoc_of(bin_op)
        lhs_str = expr_precedence.parenthesize(
            render_value(l), expr_precedence.level_of(l.owner), my_level, "lhs", my_assoc
        )
        rhs_str = expr_precedence.parenthesize(
            render_value(r), expr_precedence.level_of(r.owner), my_level, "rhs", my_assoc
        )
        return f"{lhs_str} {token} {rhs_str}"

    def render_base(region) -> str:
        base_op = region.block.last_op
        return expr_precedence.parenthesize(
            render(base_op), expr_precedence.level_of(base_op),
            expr_precedence.ATOM_LEVEL, "lhs", "left",
        )

    def render(o: object) -> str:
        match o:
            case arith.ConstantOp(value=v):
                return _cpp_literal_str(v)
            case memref.LoadOp(memref=arr):
                return var_name(arr)
            case arith.CmpiOp(predicate=v, lhs=l, rhs=r):
                str_pred = arith.CMPI_COMPARISON_OPERATIONS[v.value.data]
                return render_binop(o, l, r, cmp_token(o, str_pred))
            case arith.CmpfOp(predicate=v, lhs=l, rhs=r):
                str_pred = arith.CMPF_COMPARISON_OPERATIONS[v.value.data]
                return render_binop(o, l, r, cmp_token(o, str_pred))
            case arith.XOrIOp():
                # XOR(x, true) is NOT x; XOR(x, false) is x unchanged --
                # value-aware, unlike print_ftn.py's pre-existing (and
                # deliberately not touched here) constant-VALUE-blind
                # idiom. See _is_true_literal's own docstring.
                l, r = o.lhs, o.rhs
                if isa(r.owner, arith.ConstantOp):
                    return f"!({render_value(l)})" if _is_true_literal(r.owner) else render_value(l)
                elif isa(l.owner, arith.ConstantOp):
                    return f"!({render_value(r)})" if _is_true_literal(l.owner) else render_value(r)
                else:
                    # General XOR -- C++'s logical-inequality spelling is
                    # "!=" between bools. NOT rendered via the shared
                    # render_binop/expr_precedence table: that table's
                    # LEVEL_EQV entry for XOrIOp is correct for Fortran's
                    # ".neqv." (binds loosest of all logical operators),
                    # but C++'s "!=" binds TIGHTER than &&/|| -- the
                    # opposite. Using LEVEL_EQV as "my_level" here would
                    # leave a compound AND/OR child unparenthesized
                    # (XOR(AND(a,b), c) -> "a && b != c", which C++ parses
                    # as "a && (b != c)" instead of the intended "(a && b)
                    # != c"). Parenthesize any non-atomic child
                    # unconditionally instead -- always correct, since
                    # "!=" binds tighter than every other operator this
                    # renderer emits (Copilot PR #109 review, 2026-10-05).
                    def _paren_if_compound(val: SSAValue) -> str:
                        text = render_value(val)
                        if expr_precedence.level_of(val.owner) < expr_precedence.ATOM_LEVEL:
                            return f"({text})"
                        return text
                    return f"{_paren_if_compound(l)} != {_paren_if_compound(r)}"
            case TrimOp():
                # Fortran trim() strips trailing blanks from a fixed-
                # width character buffer -- that is NOT the same thing as
                # "the C++ representation already knows its own length"
                # (a space-padded fixed-size char[N] buffer, mirroring
                # Fortran's own storage, would still need the padding
                # stripped for a content comparison/concatenation to be
                # correct). No real C++ call site has settled that buffer
                # convention yet, so reject rather than silently return
                # the padded name unchanged.
                raise AssertionError(
                    "expr_to_cpp_str: TrimOp has no settled C++ lowering yet "
                    "-- the trailing-blank-trimming semantics depend on a "
                    "buffer convention not yet decided"
                )
            case StrCmpOp():
                # _cpp_type maps a character buffer to char*/const char*;
                # "==" on those compares addresses, not contents, and the
                # two-buffer form ignores StrCmpOp.length entirely. No
                # real C++ call site needs this yet -- reject rather than
                # silently compare addresses.
                raise AssertionError(
                    "expr_to_cpp_str: StrCmpOp has no C++ content-comparison "
                    "lowering yet -- naive '==' on a char*/const char* buffer "
                    "compares addresses, not contents"
                )
            case arith.AndIOp() | arith.OrIOp():
                # &&/|| are only valid C++ between LOGICAL (i1) operands
                # -- a wider integer AndIOp/OrIOp (real bitwise AND/OR)
                # needs &/| instead, not implemented here. Reject rather
                # than silently emit a logical-truthiness check instead
                # of the real bitwise result (Copilot PR #109 review,
                # 2026-10-05).
                if not (_is_i1(o.lhs) and _is_i1(o.rhs)):
                    raise AssertionError(
                        f"expr_to_cpp_str: {o.name} on non-i1 operands has "
                        "no C++ lowering yet -- &&/|| are logical-only; "
                        "integer bitwise and/or needs &/|, not implemented"
                    )
                return render_binop(o, o.lhs, o.rhs, _CPP_BINOPS[o.name])
            case (
                arith.AddiOp() | arith.SubiOp()
                | arith.MuliOp() | arith.DivSIOp() | arith.DivUIOp()
                | arith.AddfOp() | arith.SubfOp() | arith.MulfOp() | arith.DivfOp()
            ):
                return render_binop(o, o.lhs, o.rhs, _CPP_BINOPS[o.name])
            case math.PowFOp() | math.FPowIOp():
                # C++ has no native ** operator -- std::pow() instead.
                # Safe for these two: both are float-result ops already.
                return f"std::pow({render_value(o.lhs)}, {render_value(o.rhs)})"
            case math.IPowIOp():
                # std::pow always returns a floating-point value, which
                # would silently lose IPowIOp's integer result semantics
                # (e.g. under a later integer division) -- reject rather
                # than silently truncate/convert. Not exercised by any
                # real call site yet.
                raise AssertionError(
                    "expr_to_cpp_str: math.IPowIOp (integer power) has no "
                    "C++ lowering yet -- std::pow always returns a "
                    "floating-point result, losing IPowIOp's integer "
                    "semantics"
                )
            case StringLiteralExprOp():
                return _cpp_string_literal(o.text.data)
            case VarRefExprOp():
                return o.var_name.data
            case StringConcatExprOp():
                # Two StringLiteralExprOp/char*-buffer pieces joined with
                # '+' is not valid C++ (neither operand is a string
                # object); needs a chosen string representation
                # (std::string vs. raw buffer) before this can lower
                # correctly. Not exercised by any real call site yet --
                # reject rather than emit invalid C++.
                raise AssertionError(
                    "expr_to_cpp_str: StringConcatExprOp has no C++ lowering "
                    "yet -- naive '+' on string-literal/char* pieces is not "
                    "valid C++"
                )
            case MemberAccessExprOp():
                base_str = render_base(o.base)
                sep = "->" if (o.via is not None and o.via.data == "pointer") else "."
                return f"{base_str}{sep}{o.member.data}"
            case IndexExprOp():
                base_str = render_base(o.base)
                idx_strs = []
                for r in o.indices:
                    i = r.block.last_op
                    if isa(i, SliceExprOp):
                        raise AssertionError(
                            "expr_to_cpp_str: array slicing is unsupported in C++"
                        )
                    idx_strs.append(render(i))
                return base_str + "".join(f"[{s}]" for s in idx_strs)
            case CallExprOp():
                if any(True for _ in o.kwargs):
                    raise AssertionError(
                        "expr_to_cpp_str: C++ has no keyword-argument call syntax"
                    )
                pos = [render(r.block.last_op) for r in o.args]
                return f"{o.callee.data}({', '.join(pos)})"
            case ArrayConstructorExprOp():
                elems = [render(r.block.last_op) for r in o.elements]
                return "{ " + ", ".join(elems) + " }"
            case _:
                raise AssertionError(f"Unhandled op in expr_to_cpp_str: {type(o)}")

    return render(op)

# Fixed boilerplate shared by every generated C++-interop header -- was
# independently hand-duplicated between _emit_cap_header (below) and
# cpp_interop.py's _build_chost_cpp_text.
_CPP_HEADER_BANNER = (
    "// Generated by xdsl-ccpp. Array arguments are column-major (Fortran order).\n"
    "// Pass Kokkos::View with LayoutLeft, or transpose before calling.\n"
    "#pragma once\n"
)


def _cpp_wrapper_banner(mod_name: str) -> str:
    """Fixed boilerplate for the C++ ergonomics wrapper (.hpp), 100%
    derivable from ``mod_name`` alone -- not modeled as ops in
    ``CHostCapOp.wrapper_body``, same reasoning as ``_CPP_HEADER_BANNER``
    for the C header.
    """
    return (
        f"// Generated by xdsl-ccpp. C++ ergonomics wrapper for {mod_name}.\n"
        "// Array arguments are column-major (Fortran order).\n"
        "#pragma once\n"
        "#include <string>\n"
        "#include <vector>\n"
        f'#include "{mod_name}.h"\n'
        "\n"
    )

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


def _char_buffer_comment(mlir_type: object, intent: str) -> str:
    """Return a comment documenting the required caller-allocated buffer
    size for a character (char*) BIND(C) parameter.

    The CCPP specification only covers Fortran host models -- there is no
    external convention governing how a C++ caller's buffer must be sized,
    so xdsl-ccpp's own generated header is the sole documentation of the
    actual contract here. For intent(out)/intent(inout), the Fortran side
    writes a null terminator immediately after the string content, so the
    caller's buffer must be declared_len + 1 bytes even when the string
    fully fills the declared length (see Copilot review, PR #80: the
    generated Fortran code has no way to verify the caller followed this,
    since the BIND(C) parameter is an assumed-size c_char(*) with no size
    info at all -- getting this documented, not just assumed, is the fix).
    For intent(in), the string must be null-terminated within declared_len
    characters (the Fortran side reads up to declared_len bytes looking for
    the terminator).

    A dynamic (assumed-length, ``character(len=*)``) declared_len -- e.g.
    the suite/suite-part name arguments -- has no fixed bound to report; the
    caller may pass a string of any length as long as it's null-terminated.
    """
    if not _is_char_memref(mlir_type):
        return ""
    declared_len = list(mlir_type.shape)[-1].data
    if declared_len == DYNAMIC_INDEX:
        return "  /* null-terminated string, any length */"
    if intent == "in":
        return f"  /* null-terminated string, max {declared_len} chars */"
    return f"  /* caller must allocate >= {declared_len + 1} bytes ({declared_len} + null terminator) */"


def _intent_from_arg(arg: object, inout_block_args: set) -> str:
    """Return the intent for a block argument via print_ftn.py's shared
    classify_arg_intent -- see that function's own docstring for why this
    must go through the shared decision tree rather than its own copy."""
    mlir_type = arg.type
    return classify_arg_intent(
        is_allocatable_char=_is_allocatable_char(mlir_type),
        is_alloc=bool(arg.name_hint and arg.name_hint.endswith("__alloc")),
        is_in=bool(arg.name_hint and arg.name_hint.endswith("__in")),
        has_array_dims=_has_array_dims(mlir_type),
        is_inout_return=arg in inout_block_args,
    )


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
        comment = _rank_comment(arg.type) or _char_buffer_comment(arg.type, intent)
        params.append((name, _cpp_type(arg.type, intent), comment))

    for ret_val in output_rets:
        name = ret_val.name_hint or f"out_{len(params)}"
        comment = _rank_comment(ret_val.type) or _char_buffer_comment(ret_val.type, "out")
        params.append((name, _cpp_type(ret_val.type, "out"), comment))

    return params


def _print_cpp_params(
    params: list[tuple[str, str, str]], output: IO[str], empty_paren: str = "(void)",
    single_line: bool = False,
) -> None:
    """Write a parenthesized parameter list (or ``empty_paren`` when there
    are no params), matching this module's established prototype
    formatting. ``empty_paren`` is ``"(void)"`` for free C
    functions/prototypes (the default) but plain ``"()"`` for a struct
    member function (``_print_cpp_method`` passes that).

    ``single_line`` prints ``(type name, type name, ...)`` on one line
    regardless of param count -- the shape every C++ wrapper-function
    signature needs (``const FooArgs& a``, or the State-overloads'
    ``const State& s, int col_start, int col_end``), vs. a plain C
    prototype, which always uses the one-per-line declaration form below
    regardless of count. The ``CFunctionSigOp`` branch of ``_print_cpp_op``
    passes ``single_line=is_inline`` (inline C++ functions want one line;
    bare C prototypes don't, see that branch); ``_print_cpp_method``
    always passes ``single_line=True``.
    """
    if not params:
        output.write(empty_paren)
        return
    if single_line:
        parts = [f"{cpp_t} {name}{comment}" for name, cpp_t, comment in params]
        output.write(f"({', '.join(parts)})")
        return
    output.write("(\n")
    for i, (name, cpp_t, comment) in enumerate(params):
        comma = "," if i < len(params) - 1 else " "
        output.write(f"    {cpp_t:<16} {name}{comma}{comment}\n")
    output.write(")")


def _print_cpp_method(op: "CFunctionSigOp", output: IO[str]) -> None:
    """Print a ``CFunctionSigOp`` nested inside a ``CppStructDefOp``'s
    ``methods`` region -- a distinct code path from this op's own
    top-level printing (the ``CFunctionSigOp`` branch of ``_print_cpp_op``
    below): never ``inline`` even if ``is_inline`` happens to be set,
    ``()`` not ``(void)`` for empty params, and a single-line body
    (exactly one simple-statement ``RawCppLinesOp`` child) prints inline
    on the signature's own line rather than as a multi-line brace block
    (e.g. ``bool ok() const { return code == 0; }``).
    """
    params = list(zip(
        (n.data for n in op.param_names.data),
        (t.data for t in op.param_types.data),
        (c.data for c in op.param_comments.data),
    ))
    const_suffix = " const" if (op.is_const is not None and op.is_const.value.data) else ""
    output.write(f"    {op.return_type.data} {op.fn_name.data}")
    _print_cpp_params(params, output, empty_paren="()", single_line=True)
    output.write(const_suffix)
    body_ops = list(op.body.block.ops)
    body_is_single_line = (
        len(body_ops) == 1
        and isinstance(body_ops[0], RawCppLinesOp)
        and len(body_ops[0].lines.data.splitlines()) == 1
    )
    if body_is_single_line:
        output.write(f" {{ {body_ops[0].lines.data.strip()} }}\n")
    else:
        output.write(" {\n")
        for child in body_ops:
            _print_cpp_op(child, output)
        output.write("    }\n")


def _print_cpp_constructor(struct_name: str, op: "CppConstructorOp", output: IO[str]) -> None:
    """Print a ``CppConstructorOp`` nested inside a ``CppStructDefOp``'s
    ``methods`` region. ``struct_name`` is supplied by the containing
    struct (this op stores no name of its own -- see its docstring).
    """
    params = list(zip(
        (n.data for n in op.param_names.data),
        (t.data for t in op.param_types.data),
        (d.data for d in op.param_defaults.data),
    ))
    param_str = ", ".join(f"{t} {n} = {d}" for n, t, d in params)
    output.write(f"    {struct_name}({param_str})\n")
    inits = ", ".join(
        f"{m.data}({e.data})"
        for m, e in zip(op.init_members.data, op.init_exprs.data)
    )
    body_ops = list(op.body.block.ops)
    if body_ops:
        output.write(f"        : {inits} {{\n")
        for child in body_ops:
            _print_cpp_op(child, output)
        output.write("        }\n")
    else:
        output.write(f"        : {inits} {{}}\n")


def _print_cpp_op(op: object, output: IO[str]) -> None:
    """Op-dispatch printer for ``CHostCapOp.cpp_body``/``wrapper_body`` --
    this module's counterpart to ``print_ftn.py``'s ``print_op``/``print_block``.
    """
    if isinstance(op, ExternCGuardOp):
        output.write("#ifdef __cplusplus\n")
        output.write('extern "C" {\n')
        output.write("#endif\n\n")
        for child in op.body.block.ops:
            _print_cpp_op(child, output)
        output.write("#ifdef __cplusplus\n")
        output.write("}\n")
        output.write("#endif\n")
    elif isinstance(op, CFunctionSigOp):
        params = list(zip(
            (n.data for n in op.param_names.data),
            (t.data for t in op.param_types.data),
            (c.data for c in op.param_comments.data),
        ))
        is_inline = op.is_inline is not None and op.is_inline.value.data
        prefix = "inline " if is_inline else ""
        output.write(f"{prefix}{op.return_type.data} {op.fn_name.data}")
        # C prototypes (Stage 2, always a declaration) spell zero params as
        # "(void)"; C++ inline functions (Stage 3) spell it "()" -- is_inline
        # is exactly the Stage-2-vs-Stage-3 switch, since every Stage 2
        # CFunctionSigOp is a bare (non-inline) prototype and every Stage 3
        # free function in the wrapper is inline.
        empty_paren = "()" if is_inline else "(void)"
        _print_cpp_params(params, output, empty_paren=empty_paren, single_line=is_inline)
        if len(op.body.block.ops) == 0:
            output.write(";\n\n")
        else:
            output.write(" {\n")
            for child in op.body.block.ops:
                _print_cpp_op(child, output)
            # No trailing blank line here (unlike the declaration branch
            # above): every section in the wrapper supplies its own leading
            # separator blank instead (see cpp_interop.py's _build_chost_
            # wrapper_body) -- this branch is unreachable from Stage 2
            # (every Stage 2 CFunctionSigOp is a declaration, body always
            # empty), so this doesn't touch Stage 2's own verified output.
            output.write("}\n")
    elif isinstance(op, CppStructDefOp):
        output.write(f"struct {op.struct_name.data} {{\n")
        for child in op.members.block.ops:
            _print_cpp_op(child, output)
        method_ops = list(op.methods.block.ops)
        if method_ops:
            # Exactly one fixed blank line between fields and the first
            # method; any further separation between methods is baked into
            # each method chunk's own leading text (e.g. a comment
            # RawCppLinesOp starting with "\n"), same convention the
            # top-level namespace body already uses -- not auto-inserted
            # here, since a comment immediately preceding the method it
            # describes must NOT get a blank line of its own.
            output.write("\n")
            for child in method_ops:
                if isinstance(child, CppConstructorOp):
                    _print_cpp_constructor(op.struct_name.data, child, output)
                elif isinstance(child, CFunctionSigOp):
                    _print_cpp_method(child, output)
                else:
                    _print_cpp_op(child, output)
        private_ops = list(op.private_members.block.ops)
        if private_ops:
            output.write("\nprivate:\n")
            for child in private_ops:
                _print_cpp_op(child, output)
        output.write("};\n")
    elif isinstance(op, CppFieldDeclOp):
        suffix = op.array_suffix.data if op.array_suffix is not None else ""
        width = op.type_width.value.data if op.type_width is not None else 8
        if op.init_expr is not None:
            init = f" = {op.init_expr.data}"
        elif op.init_expr_region is not None:
            init = f" = {expr_to_cpp_str(op.init_expr_region.block.last_op)}"
        else:
            init = ""
        output.write(f"    {op.cpp_type.data:<{width}} {op.field_name.data}{suffix}{init};\n")
    elif isinstance(op, CppIncludeOp):
        if op.local is not None and op.local.value.data:
            output.write(f'#include "{op.header.data}"\n')
        else:
            output.write(f"#include <{op.header.data}>\n")
    elif isinstance(op, RawCppLinesOp):
        for line in op.lines.data.splitlines():
            output.write(line + "\n")
    elif isinstance(op, CppNamespaceOp):
        output.write(f"namespace {op.ns_name.data} {{\n")
        for child in op.body.block.ops:
            _print_cpp_op(child, output)
        output.write(f"}} // namespace {op.ns_name.data}\n")
    elif isinstance(op, CppCallStatementOp):
        if op.call_args is not None:
            call_args = [a.data for a in op.call_args.data]
        else:
            call_args = [expr_to_cpp_str(r.block.last_op) for r in op.call_args_region]
        lines = wrap_paren_list(
            f"    {op.callee.data}(", call_args, ");", 80, "        ", cont_marker="",
        )
        for line in lines:
            output.write(line + "\n")
    elif isinstance(op, CppBraceInitCallOp):
        output.write(f"    return {op.callee.data}({{\n")
        if op.field_values is not None:
            values = [v.data for v in op.field_values.data]
        else:
            values = [expr_to_cpp_str(r.block.last_op) for r in op.field_values_region]
        for name, value in zip(op.field_names.data, values):
            output.write(f"        .{name.data}={value},\n")
        output.write("    });\n")
    else:
        raise NotImplementedError(
            f"print_cpp_header: no printer for {type(op).__name__}"
        )


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

    output.write(_CPP_HEADER_BANNER)

    proto_ops = []
    for fn_op in bind_c_fns:
        params = _fn_params(fn_op)
        proto_ops.append(CFunctionSigOp(
            fn_name=fn_op.sym_name.data,
            param_names=[p[0] for p in params],
            param_types=[p[1] for p in params],
            param_comments=[p[2] for p in params],
            body_ops=[],
        ))
    _print_cpp_op(ExternCGuardOp(body_ops=proto_ops), output)


def _emit_kinds_header(kinds_module: ModuleOp, output: IO[str]) -> None:
    """Write the ccpp_kinds.h typedef file.

    Raises ValueError for any kind resolved via a metadata kind_spec (module
    != 'iso_fortran_env') rather than the ISO_FORTRAN_ENV table: kind_spec
    only names a symbol (e.g. 'temp_r8'), not a byte width, so there is
    nothing here to map to a C++ type from -- defaulting to "double" would
    silently risk a wrong-width typedef, a real correctness bug across the
    C++/BIND(C) boundary. See cpp_interop.py's _real_width_from_iso for the
    matching check on the Fortran-cap side.
    """
    kind_ops = [op for op in kinds_module.body.ops if isa(op, KindDefOp)]
    output.write("// Generated by xdsl-ccpp. Kind aliases match ccpp_kinds.F90.\n")
    output.write("#pragma once\n")
    for op in kind_ops:
        kind_name = op.kind_name.data
        kind_value = op.kind_value.data
        kind_module = op.kind_module.data
        if kind_module != "iso_fortran_env":
            raise ValueError(
                f"C++ kinds header: kind '{kind_name}' was resolved via a "
                f"metadata kind_spec ('{kind_module}:{kind_value}'), not "
                f"ISO_FORTRAN_ENV -- there is no known C++ type/width to "
                f"typedef it to. Give this kind name an explicit mapping "
                f"before using it in a C++/chost host."
            )
        cpp_type = _ISO_TO_CPP.get(kind_value, "double")
        output.write(f"typedef {cpp_type:<8}  {kind_name}_t;\n")


def print_to_cpp_headers(prog: ModuleOp, output: IO[str]) -> None:
    """Emit C++ header sections for all BIND(C) cap modules in *prog*.

    Emits up to three ``// FILE:``-delimited sections:

    - ``<HostName>_ccpp_cap.h`` — ``extern "C"`` declarations for each BIND(C)
      subroutine, using ISO-C-compatible types.
    - ``ccpp_kinds.h`` — ``typedef`` aliases for every CCPP kind name.
    - ``<mod_name>.h`` — the typed ``cpp_body`` op sequence from each
      ``CHostCapOp``, printed via ``_print_cpp_op`` (one section per op,
      emitted after the standard cap/kinds headers).

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
        output.write(_CPP_HEADER_BANNER)
        for child in op.cpp_body.block.ops:
            _print_cpp_op(child, output)
            output.write("\n")
        wrote = True
        wrapper_ops = list(op.wrapper_body.block.ops)
        if wrapper_ops:
            wrapper_file = (
                op.mod_name.data.replace("_ccpp_chost_cap", "_chost") + ".hpp"
            )
            output.write("// -----\n")
            output.write(f"// FILE: {wrapper_file}\n")
            output.write(_cpp_wrapper_banner(op.mod_name.data))
            for child in wrapper_ops:
                _print_cpp_op(child, output)
                output.write("\n")
